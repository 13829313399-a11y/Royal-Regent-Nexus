import runpy
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_additive_migration_preserves_existing_rows_and_blocks_evidence_downgrade(tmp_path):
    engine=sa.create_engine("sqlite:///"+str(tmp_path/"migration.db"))
    migration=runpy.run_path(str(Path(__file__).resolve().parents[1]/"alembic/versions/20261019_0168_carton_special_requests.py"))
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("CREATE TABLE carton_suppliers (id TEXT, factory_id TEXT, UNIQUE(id,factory_id))")
        connection.exec_driver_sql("CREATE TABLE carton_receipt_lines (id TEXT, factory_id TEXT, UNIQUE(id,factory_id))")
        connection.exec_driver_sql("INSERT INTO carton_suppliers VALUES ('vendor','huaxing')")
        before=connection.exec_driver_sql("SELECT * FROM carton_suppliers").all()
        with Operations.context(MigrationContext.configure(connection)):
            migration["upgrade"]()
        assert connection.exec_driver_sql("SELECT * FROM carton_suppliers").all()==before
        assert "version" in {column["name"] for column in sa.inspect(connection).get_columns("carton_special_attachments")}
        assert connection.exec_driver_sql("SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'carton_special_%'").scalar()==12
        connection.exec_driver_sql("INSERT INTO carton_special_requests VALUES ('request','huaxing','vendor','SP-1','SAMPLE','sample','person','','','','purpose','2026-10-20','SUBMITTED',1,'','','PENDING_QUOTE','','actor','2026-10-19','2026-10-19')")
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError,match="must be preserved"): migration["downgrade"]()
        assert connection.exec_driver_sql("SELECT count(*) FROM carton_special_requests").scalar()==1
