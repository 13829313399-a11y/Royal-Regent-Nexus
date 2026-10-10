import importlib
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from types import SimpleNamespace
from uuid import UUID, uuid4, uuid5

import pytest
import sqlalchemy as sa
from fastapi import HTTPException
from sqlalchemy.orm import Session
from test_fabric_procurement import BASE, book, row, stored
from test_fabric_procurement_tracking import save
from test_molding_sample_api import login_as
from warehouse_location_fixtures import make_client, seed_fabric_locations


@pytest.fixture
def warehouse(tmp_path):
    source = importlib.import_module("app.services.fabric_procurement")
    receiving = importlib.import_module("app.services.fabric_receiving")
    parser = importlib.import_module("app.services.fabric_procurement_parser")
    procurement = importlib.import_module("app.models.fabric_procurement")
    master = importlib.import_module("app.models.fabric_master")
    dbm = importlib.import_module("app.db")
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "batch.db"), connect_args={"check_same_thread": False})
    models = (procurement.FabricProcurementState, procurement.FabricProcurementLine, procurement.FabricProcurementImport, procurement.FabricProcurementEvidence,
              *receiving.MODELS, master.FabricMasterRecord, master.FabricMasterChange, master.FabricChaseResolution)
    dbm.Base.metadata.create_all(engine, tables=[model.__table__ for model in models])
    actor = SimpleNamespace(id="A", display_name="Warehouse")
    with Session(engine) as db:
        seed_fabric_locations(db)
        parsed = parser.parse_workbook("source.xlsx", book([row(), row(订单号="PO2", 物料编码="M2", 基本单位="个", 入库数量="#VALUE!", 交货明细="")]))
        token = source.preview(db, parsed, actor.id)["preview_token"]
        source.apply(db, parsed, actor, "source.xlsx", str(uuid4()), token, confirmed=True, acknowledge_excluded=True)
        lines = sorted(source.list_lines(db)["items"], key=lambda item: item["facts"]["order_no"])
    yield engine, actor, lines, receiving
    engine.dispose()


def body(lines):
    return {"factory_id": "huakang-c", "request_id": str(uuid4()), "receipt_date": "2026-09-16", "delivery_reference": "DN-BATCH",
            "confirmed": True, "items": [{"source_line_id": line["id"], "expected_source_revision": line["revision"], "expected_receipt_count": 0,
            "material_category": "FABRIC" if index == 0 else "ACCESSORY", "batches": [{"quantity": "10.125", "location": "A01", "location_id": "fabric-A01",
            "dye_lot": "0001" if index == 0 else "", "roll_no": "0002" if index == 0 else ""}]} for index, line in enumerate(lines)]}


def post(db, receiving, actor, data):
    schema = importlib.import_module("app.schemas.fabric_receiving")
    return receiving.receive_many(db, actor, schema.ReceiveSourcesRequest(**data))


@pytest.mark.parametrize("failure", ["location", "dye", "overage", "revision", "count", "withdrawn", "missing", "duplicate", "unconfirmed"])
def test_entire_batch_rolls_back_on_any_invalid_item(warehouse, failure):
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    if failure == "location": data["items"][1]["batches"][0]["location"] = " "
    if failure == "dye": data["items"][1]["material_category"] = "FABRIC"
    if failure == "overage": data["items"][1]["batches"][0]["quantity"] = "1000000000000"
    if failure == "revision": data["items"][1]["expected_source_revision"] += 1
    if failure == "count": data["items"][1]["expected_receipt_count"] = 1
    if failure == "duplicate": data["items"][1]["source_line_id"] = data["items"][0]["source_line_id"]
    if failure == "unconfirmed": data["confirmed"] = False
    if failure == "missing": data["items"][1]["source_line_id"] = "missing-source"
    if failure == "withdrawn":
        model = importlib.import_module("app.models.fabric_procurement").FabricProcurementLine
        with Session(engine) as db:
            line = db.get(model, lines[1]["id"])
            line.status = "WITHDRAWN"
            db.commit()
    state = importlib.import_module("app.models.fabric_procurement").FabricProcurementState
    with Session(engine) as db:
        revision = db.get(state, "huakang-c").revision
        with pytest.raises(HTTPException): post(db, receiving, actor, data)
        for model in receiving.MODELS:
            assert db.scalar(sa.select(sa.func.count()).select_from(model)) == 0
        assert db.get(state, "huakang-c").revision == revision


def test_replay_binds_whole_selection_actor_and_content_and_preserves_unknown(warehouse):
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    with Session(engine) as db:
        result = post(db, receiving, actor, data)
        assert len(result["receipts"]) == 2
        assert [item["unit"] for item in result["receipts"]] == ["码", "个"]
        assert result["receipts"][1]["prior_received_quantity"] is None
        assert result["receipts"][0]["batches"][0]["dye_lot"] == "0001"
        assert post(db, receiving, actor, data) == result
        for change in ("subset", "quantity", "actor", "reorder"):
            changed = deepcopy(data)
            if change == "subset": changed["items"].pop()
            if change == "quantity": changed["items"][1]["batches"][0]["quantity"] = "11"
            if change == "reorder": changed["items"].reverse()
            who = SimpleNamespace(id="OTHER", display_name="Other") if change == "actor" else actor
            with pytest.raises(HTTPException) as exc: post(db, receiving, who, changed)
            assert exc.value.status_code == 409
        assert receiving.list_stock(db)["total"] == 2
        assert receiving.list_receipts(db)["total"] == 2
        schemas = importlib.import_module("app.schemas.fabric_receiving")
        single = schemas.ReceiveSourceRequest(**{**{key: value for key, value in data.items() if key != "items"}, "delivery_reference": "ANOTHER-NOTE"},
            **{**{key: value for key, value in data["items"][0].items() if key != "source_line_id"}, "expected_receipt_count": 1})
        with pytest.raises(HTTPException) as exc: receiving.receive(db, actor, lines[0]["id"], single)
        assert exc.value.status_code == 409
        db.rollback()
        assert receiving.list_receipts(db)["total"] == 2


def test_known_overage_requires_reason_and_failed_request_can_be_corrected(warehouse):
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    data["items"][0]["batches"][0]["quantity"] = "51"
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc: post(db, receiving, actor, data)
        assert exc.value.status_code == 422
        assert receiving.list_stock(db)["total"] == 0
        data["items"][0]["difference_reason"] = "供应商多送1码"
        result = post(db, receiving, actor, data)
        assert result["receipts"][0]["quantity"] == "51"
        assert receiving.list_stock(db)["total"] == 2


def test_batch_bounds_reject_excess_sources_splits_and_duplicate_single_request(warehouse):
    from pydantic import ValidationError
    schemas = importlib.import_module("app.schemas.fabric_receiving")
    engine, actor, lines, receiving = warehouse
    data = body(lines)
    with pytest.raises(ValidationError): schemas.ReceiveSourcesRequest(**{**data, "items": data["items"][:1] * 51})
    oversized = deepcopy(data)
    oversized["items"] = [deepcopy(data["items"][0]) for _ in range(3)]
    for index, item in enumerate(oversized["items"]):
        item["source_line_id"] = str(index)
        item["batches"] *= 200
    with Session(engine) as db:
        with pytest.raises(HTTPException) as exc: post(db, receiving, actor, oversized)
        assert exc.value.status_code == 422
        single = schemas.ReceiveSourceRequest(**{key: value for key, value in data.items() if key != "items"},
            **{key: value for key, value in data["items"][0].items() if key != "source_line_id"})
        receiving.receive(db, actor, lines[0]["id"], single)
        with pytest.raises(HTTPException) as exc: post(db, receiving, actor, data)
        assert exc.value.status_code == 409
        assert receiving.list_receipts(db)["total"] == 1


def test_child_uuid_cannot_reuse_another_batch_root(warehouse):
    engine, actor, lines, receiving = warehouse
    first = body(lines); first["items"] = first["items"][:1]
    second = body(lines); second["items"] = second["items"][1:]
    second["request_id"] = str(uuid5(UUID(first["request_id"]), first["items"][0]["source_line_id"]))
    with Session(engine) as db:
        post(db, receiving, actor, second)
        with pytest.raises(HTTPException) as exc: post(db, receiving, actor, first)
        assert exc.value.status_code == 409
        assert receiving.list_receipts(db)["total"] == 1


@pytest.mark.parametrize("same_request", [True, False])
def test_concurrent_batch_posts_once(warehouse, same_request):
    engine, actor, lines, receiving = warehouse
    data = body(lines); barrier = Barrier(2)
    def run(second):
        changed = deepcopy(data)
        if second and not same_request: changed["request_id"] = str(uuid4())
        with Session(engine) as db:
            barrier.wait()
            try: return post(db, receiving, actor, changed)
            except HTTPException as exc: return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(run, [False, True]))
    assert sum(isinstance(result, dict) for result in results) == (2 if same_request else 1)
    with Session(engine) as db:
        assert receiving.list_stock(db)["total"] == 2
        assert receiving.list_receipts(db)["total"] == 2


def test_single_and_batch_cannot_share_request_identity_concurrently(warehouse):
    engine, actor, lines, receiving = warehouse
    schemas = importlib.import_module("app.schemas.fabric_receiving")
    data = body(lines); barrier = Barrier(2)
    single = schemas.ReceiveSourceRequest(**{key: value for key, value in data.items() if key != "items"},
        **{key: value for key, value in data["items"][0].items() if key != "source_line_id"})
    def run(batch):
        with Session(engine) as db:
            barrier.wait()
            try: return post(db, receiving, actor, data) if batch else receiving.receive(db, actor, lines[0]["id"], single)
            except HTTPException as exc: db.rollback(); return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool: results = list(pool.map(run, [False, True]))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert 409 in results
    with Session(engine) as db:
        assert receiving.list_stock(db)["total"] == (2 if isinstance(results[1], dict) else 1)


def test_batch_api_uses_receive_authority_and_rejects_other_factory(monkeypatch):
    from dataclasses import replace
    with make_client(monkeypatch) as client:
        assert client.post(BASE + "/receipts/batch", json=body([])).status_code == 401
        login_as(client, "admin")
        save(client, book([row(), row(订单号="PO2", 物料编码="M2")]))
        data = body(sorted(stored(client)["items"], key=lambda item: item["facts"]["order_no"]))
        assert client.post(BASE + "/receipts/batch", json={**data, "factory_id": "huakang-d"}).status_code == 422
        auth = importlib.import_module("app.services.auth")
        main = importlib.import_module("app.main")
        dbm = importlib.import_module("app.db")
        models = importlib.import_module("app.models.auth")
        with dbm.SessionLocal() as db:
            actor = auth.build_auth_context(db, db.scalar(sa.select(models.AuthUser).where(models.AuthUser.username == "admin")))
        for code in ("fabric_warehouse:read", "fabric_warehouse:receive"):
            denied = replace(actor, overrides=(auth.AuthOverrideContext(id="deny", permission_code=code, effect="deny", factory_id="huakang-c", department="pmc-warehouse"),))
            main.app.dependency_overrides[auth.get_current_user] = lambda: denied
            assert client.post(BASE + "/receipts/batch", json=data).status_code == 403
        main.app.dependency_overrides.pop(auth.get_current_user, None)
        assert client.post(BASE + "/receipts/batch", json=data).status_code == 200
        assert client.post(BASE + "/receipts/batch", json=data).status_code == 200
