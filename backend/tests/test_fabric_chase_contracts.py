"""Small durable migration/calculation checks, independent of the full app startup."""
import importlib
import json
from decimal import Decimal
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_fabric_procurement import book, row


def migration(filename):
    spec = spec_from_file_location(filename, Path(__file__).parents[1] / "alembic/versions" / filename)
    module = module_from_spec(spec); spec.loader.exec_module(module); return module


def test_additive_upgrade_preserves_old_receipt_stock_and_protects_unknown_downgrade(tmp_path):
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    versions = [migration(name) for name in ("20261005_0131_fabric_procurement.py", "20261006_0135_fabric_receiving.py", "20261007_0138_fabric_master_chase.py")]
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        versions[0].upgrade(); versions[1].upgrade()
        connection.execute(sa.text("INSERT INTO fabric_procurement_lines VALUES ('L','huakang-c','KEY',1,'PENDING','PO','Supplier','MAT','P','{}',1,'NOW')"))
        connection.execute(sa.text("INSERT INTO fabric_receipts VALUES ('R','huakang-c','L',1,'REQ','HASH','DN','2026-09-16','2026-09','10','码','50','{}','{}','A','Warehouse','NOW')"))
        connection.execute(sa.text("INSERT INTO fabric_stock_batches VALUES ('B','huakang-c','R','A1','001','002','FABRIC','PENDING_INSPECTION')"))
        connection.execute(sa.text("INSERT INTO fabric_inventory_movements VALUES ('M','huakang-c','R','B','RECEIPT','10')"))
        versions[2].upgrade()
        assert connection.execute(sa.text("SELECT quantity,prior_received_quantity,baseline_known FROM fabric_receipts")).first() == ("10", "50", 1)
        assert connection.execute(sa.text("SELECT quantity FROM fabric_inventory_movements")).scalar_one() == "10"
        assert not connection.execute(sa.text("PRAGMA foreign_key_check")).all()
        connection.execute(sa.text("UPDATE fabric_receipts SET baseline_known = 0"))
        with pytest.raises(RuntimeError, match="数量未知"):
            versions[2].downgrade()
        connection.execute(sa.text("UPDATE fabric_receipts SET baseline_known = 1"))
        versions[2].downgrade(); versions[2].upgrade()
        assert connection.execute(sa.text("SELECT quantity FROM fabric_inventory_movements")).scalar_one() == "10"
    engine.dispose()


def test_order_changes_require_chase_confirmation_and_old_schema_still_protects_receipts(tmp_path):
    receiving = importlib.import_module("app.services.fabric_receiving")
    context = {"receipt_count": 1, "prior_received_quantity": Decimal("50"),
               "warehouse_received_quantity": Decimal("10"), "source_facts": {"ordered_quantity": "100", "reported_received_quantity": "50", "material_code": "M", "material_name": "N", "unit": "码", "supplier": "S"}}
    current = {**context["source_facts"], "ordered_quantity": "120"}
    result = receiving.receipt_progress(current, context)
    assert result["warehouse_outstanding_quantity"] is None and result["receipt_quantity_conflict"]
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "old.db"))
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration("20261005_0131_fabric_procurement.py").upgrade(); migration("20261006_0135_fabric_receiving.py").upgrade()
        connection.execute(sa.text("INSERT INTO fabric_procurement_lines VALUES ('L','huakang-c','KEY',1,'PENDING','PO','Supplier','MAT','P','{}',1,'NOW')"))
        connection.execute(sa.text("INSERT INTO fabric_receipts VALUES ('R','huakang-c','L',1,'REQ','HASH','DN','2026-09-16','2026-09','10','码','50',:facts,'{}','A','Warehouse','NOW')"), {"facts": json.dumps(context["source_facts"])})
    with Session(engine) as db:
        assert not receiving.schema_ready(db)
        assert receiving.receipt_context(db)["L"]["warehouse_received_quantity"] == 10
        with pytest.raises(Exception) as blocked:
            receiving.guard_source_withdrawal(db, ["L"])
        assert blocked.value.status_code == 409
    engine.dispose()


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_start_confirmations_are_serialized(tmp_path, same_request):
    source = importlib.import_module("app.services.fabric_procurement")
    receiving = importlib.import_module("app.services.fabric_receiving")
    parser = importlib.import_module("app.services.fabric_procurement_parser")
    schemas = importlib.import_module("app.schemas.fabric_master")
    procurement = importlib.import_module("app.models.fabric_procurement")
    master = importlib.import_module("app.models.fabric_master")
    dbm = importlib.import_module("app.db")
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "concurrency.db"), connect_args={"check_same_thread": False})
    models = (procurement.FabricProcurementState, procurement.FabricProcurementLine, procurement.FabricProcurementImport, procurement.FabricProcurementEvidence,
              *receiving.MODELS, master.FabricMasterRecord, master.FabricMasterChange, master.FabricChaseResolution)
    dbm.Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    actor = SimpleNamespace(id="A", display_name="Manager")
    with Session(engine) as db:
        parsed = parser.parse_workbook("source.xlsx", book([row(入库数量=None, 交货明细="")]))
        token = source.preview(db, parsed, actor.id)["preview_token"]
        source.apply(db, parsed, actor, "source.xlsx", str(uuid4()), token, confirmed=True, acknowledge_excluded=True)
        line = source.list_lines(db)["items"][0]
    body = dict(factory_id="huakang-c", request_id=uuid4(), expected_source_revision=line["revision"], expected_receipt_count=0, expected_resolution_revision=0, starting_quantity="37", evidence="原始欠数已核对", confirmed_start=True)
    barrier = Barrier(2)
    def post(other):
        payload = schemas.ResolveChaseRequest(**{**body, "request_id": uuid4() if other and not same_request else body["request_id"]})
        with Session(engine) as db:
            barrier.wait()
            try: return receiving.resolve_chase(db, actor, line["id"], payload)
            except Exception as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(post, [False, True]))
    assert sum(isinstance(result, dict) for result in results) == (2 if same_request else 1)
    with Session(engine) as db:
        assert db.scalar(sa.select(sa.func.count()).select_from(master.FabricChaseResolution)) == 1
    engine.dispose()
