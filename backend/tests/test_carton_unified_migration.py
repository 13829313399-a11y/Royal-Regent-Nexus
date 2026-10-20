import runpy
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_unified_marks_migration_preserves_populated_immutable_evidence(tmp_path):
    root = Path(__file__).resolve().parents[1] / "alembic/versions"
    first = runpy.run_path(str(root / "20261019_0168_carton_special_requests.py"))
    second = runpy.run_path(str(root / "20261019_0169_carton_unified_delivery_marks.py"))
    engine = sa.create_engine("sqlite:///" + str(tmp_path / "migration.db"))
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE carton_suppliers (id TEXT, factory_id TEXT, UNIQUE(id,factory_id))")
        connection.exec_driver_sql("CREATE TABLE carton_receipt_lines (id TEXT, factory_id TEXT, UNIQUE(id,factory_id))")
        connection.exec_driver_sql("INSERT INTO carton_suppliers VALUES ('vendor','huaxing')")
        with Operations.context(MigrationContext.configure(connection)): first["upgrade"]()
        connection.exec_driver_sql("INSERT INTO carton_special_requests VALUES ('request','huaxing','vendor','SP-1','SAMPLE','sample','person','','','','purpose','2026-10-20','SENT',1,'version','','PENDING_QUOTE','','actor','2026-10-19','2026-10-19')")
        connection.exec_driver_sql("INSERT INTO carton_special_lines VALUES ('line','huaxing','request',1,'','box','A','20*10*8','cm',10,'pcs',2)")
        connection.exec_driver_sql("INSERT INTO carton_special_versions VALUES ('version','huaxing','request',1,'SEND','actor','person','2026-10-19','{}')")
        connection.exec_driver_sql("INSERT INTO carton_special_shipments VALUES ('shipment','huaxing','vendor','request','version','note','2026-10-19','actor','2026-10-19')")
        connection.exec_driver_sql("INSERT INTO carton_special_shipment_lines VALUES ('paper','huaxing','shipment','line',5,'{}')")
        before = connection.exec_driver_sql("SELECT * FROM carton_special_shipments").all()
        with Operations.context(MigrationContext.configure(connection)): second["upgrade"]()
        assert connection.exec_driver_sql("SELECT * FROM carton_special_shipments").all() == before
        assert connection.exec_driver_sql("SELECT mark_mode FROM carton_special_lines").scalar() == "PENDING"
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()
        with pytest.raises(sa.exc.IntegrityError, match="immutable"):
            connection.exec_driver_sql("UPDATE carton_special_shipments SET delivery_note_no='rewrite'")
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match="must be preserved"): second["downgrade"]()
