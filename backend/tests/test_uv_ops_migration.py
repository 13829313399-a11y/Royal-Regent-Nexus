"""Upgrade populated frozen UV schema, preserving original facts and checks."""
import importlib.util
from pathlib import Path
from uuid import uuid4
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session
from test_uv_ops import client, setup_task, confirm, post
from app.models import uv_operations as m


def revision(name):
    path=next((Path(__file__).parents[1]/'alembic/versions').glob(name+'*'))
    spec=importlib.util.spec_from_file_location('uv_migration_'+name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_populated_0121_to_0127_preserves_history_and_constraints(client,tmp_path):
    data=setup_task(client,quantity=12)
    post(client,'schedule/commit',blocks=[dict(task_id=data['task']['id'],machine_id=data['machine']['id'],task_version=data['task']['version'],machine_version=1,block_version=0,start_at='2026-09-23T08:00:00+08:00',end_at='2026-09-23T09:00:00+08:00')])
    confirm(client,data,good=12,rework=0)
    post(client,'participations',task_id=data['task']['id'],shift_id=data['shift']['id'],employee_id='OLD-WORKER',employee_name='原始合成员工',start_at='2026-09-23T08:00:00+08:00',end_at='2026-09-23T09:00:00+08:00')
    post(client,'wages/confirm',task_id=data['task']['id'],shift_id=data['shift']['id'])
    postgres=client.uv_engine.dialect.name=='postgresql'
    schema='uvmigration_'+uuid4().hex
    if postgres:
        with client.uv_engine.begin() as db: db.execute(sa.text(f'CREATE SCHEMA "{schema}"'))
        engine=sa.create_engine(client.uv_engine.url,connect_args={'options':f'-csearch_path={schema}'})
    else:
        # Dedicated migration connection, never an app writer. FK restoration is
        # checked after the parent-table batch rebuild, before any app access.
        engine=sa.create_engine('sqlite:///'+str(tmp_path/'old-uv.db'))
    try:
        from app.models.auth import AuthPermission, AuthPermissionMetadata
        m.Base.metadata.create_all(engine,tables=[AuthPermission.__table__,AuthPermissionMetadata.__table__])
        with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
            revision('20260923_0121_uv_ops').upgrade()
        metadata=sa.MetaData();metadata.reflect(engine)
        before={}
        with engine.begin() as target,client.uv_engine.connect() as source:
            for table in metadata.sorted_tables:
                if not table.name.startswith('uv_ops_') or table.name=='uv_ops_settings': continue
                current=m.Base.metadata.tables[table.name]
                rows=[dict(row) for row in source.execute(sa.select(*(current.c[x.name] for x in table.columns))).mappings()]
                if rows: target.execute(table.insert(),rows)
                before[table.name]=rows
        with engine.begin() as db, Operations.context(MigrationContext.configure(db)):
            revision('20260929_0127').upgrade()
        with engine.connect() as db:
            for name,rows in before.items():
                actual=[dict(row) for row in db.execute(sa.select(metadata.tables[name])).mappings()]
                assert sorted(actual,key=lambda x:x['id'])==sorted(rows,key=lambda x:x['id']),name
            old=db.execute(sa.text('SELECT batch_id,estimate_basis FROM uv_ops_schedule_blocks')).one()
            assert old==(None,'standard')
            assert db.scalar(sa.text('SELECT active_key FROM uv_ops_wage_accruals'))==1
            if not postgres:
                assert db.exec_driver_sql('PRAGMA integrity_check').scalar()=='ok'
                assert db.exec_driver_sql('PRAGMA foreign_key_check').all()==[]
        for table,sql in [('uv_ops_schedule_blocks',"end_at=start_at"),('uv_ops_wage_accruals','payroll_amount=-1')]:
            with pytest.raises(sa.exc.IntegrityError):
                with engine.begin() as db: db.execute(sa.text(f'UPDATE {table} SET {sql}'))
        for table,expected in [('uv_ops_schedule_blocks','end_at > start_at'),('uv_ops_wage_accruals','payroll_amount >= 0'),('uv_ops_run_costs','cost_amount >= 0')]:
            checks={x['sqltext'] for x in sa.inspect(engine).get_check_constraints(table)}
            assert any(expected.replace(' ','') in x.replace('::text','').replace('::numeric','').replace(' ','').replace('(','').replace(')','') for x in checks),(table,checks)
            assert any("factory_id" in x and 'huakang-a' in x for x in checks)
    finally:
        engine.dispose()
        if postgres:
            with client.uv_engine.begin() as db: db.execute(sa.text(f'DROP SCHEMA "{schema}" CASCADE'))
