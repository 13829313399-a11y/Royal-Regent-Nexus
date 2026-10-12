import runpy
from io import StringIO
from pathlib import Path
import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.migration import MigrationContext


def migration():
    return runpy.run_path(str(Path(__file__).parents[1]/'alembic/versions/20261012_0156_handover_supplier_identity.py'))


def test_supplier_binding_migration_only_adds_tables_and_protects_identity(tmp_path,monkeypatch):
    script=migration();engine=sa.create_engine(f'sqlite:///{tmp_path/"supplier.db"}')
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.exec_driver_sql('CREATE TABLE material_handover_issuers(id TEXT, factory_id TEXT, PRIMARY KEY(id), UNIQUE(id,factory_id))')
        connection.exec_driver_sql('CREATE TABLE fabric_master_records(id TEXT, factory_id TEXT, PRIMARY KEY(id), UNIQUE(id,factory_id))')
        connection.exec_driver_sql("INSERT INTO material_handover_issuers VALUES ('I','huakang-c')")
        connection.exec_driver_sql("INSERT INTO fabric_master_records VALUES ('S','huakang-c')")
        op=Operations(MigrationContext.configure(connection));monkeypatch.setattr(script['op'],'get_bind',lambda:connection)
        monkeypatch.setattr(script['op'],'drop_table',op.drop_table)
        script['upgrade']()
        assert connection.exec_driver_sql('SELECT * FROM fabric_master_records').all()==[('S','huakang-c')]
        assert len(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").all())==4
        connection.exec_driver_sql("INSERT INTO material_handover_supplier_bindings VALUES ('I','huakang-c','S','{}','actor','now')")
        with pytest.raises(sa.exc.DBAPIError):connection.exec_driver_sql("UPDATE material_handover_supplier_bindings SET supplier_id='other'")
        with pytest.raises(RuntimeError,match='evidence is retained'):script['downgrade']()


def test_postgresql_supplier_identity_offline_ddl(monkeypatch):
    script=migration();stream=StringIO()
    op=Operations(MigrationContext.configure(dialect_name='postgresql',opts={'as_sql':True,'output_buffer':stream}))
    monkeypatch.setattr(script['op'],'get_bind',op.get_bind);script['upgrade']()
    text=stream.getvalue()
    assert text.count('CREATE TABLE material_handover_')==2 and text.count('CREATE TRIGGER')==2
    assert 'FOREIGN KEY(supplier_id, factory_id) REFERENCES fabric_master_records' in text


def test_blank_optional_fields_preserve_old_request_signature():
    import importlib
    schema=importlib.import_module('app.schemas.material_handover')
    service=importlib.import_module('app.services.material_handover')
    from app.services.fabric_procurement_parser import digest
    old={'request_id':'00000000-0000-4000-8000-000000000001','expected_revision':1,
        'acknowledge_warnings':True,'reason':''}
    assert service.request_signature('CONFIRM','old',schema.DocumentAction(**old))==digest(['CONFIRM','old',old])
