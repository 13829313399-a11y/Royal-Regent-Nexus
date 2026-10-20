"""Reconcile the two historical meanings of 0163 without replacing evidence.

The canonical cutting revision and successors retain their identifiers. The
original JP script is frozen in legacy/. Existing complete schemas are adopted
only after exact inspection; missing groups are created from frozen scripts.
"""
from pathlib import Path
from uuid import uuid4
import runpy

from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

revision = '20261017_0167'
down_revision = '20261016_0166'
branch_labels = None
depends_on = None
ROOT = Path(__file__).resolve().parent
CUTTING = ROOT/'20261015_0163_cutting_internal_periods.py'
JP = ROOT.parent/'legacy/20261015_0163_huakang_b_jp_intake.py'
GROUPS = {
    'cutting': ('cutting_ops_period_events',),
    'jp': ('jp_intake_references', 'jp_intake_reference_events', 'jp_intake_counters',
           'jp_intake_exports', 'jp_intake_export_identities'),
}
VALID_VERSIONS = [{v} for v in ('20261015_0163', '20261016_0164', '20261016_0165', '20261016_0166', revision)] + [
    {'20261015_0163', '20261016_0163'}]
FUNCTIONS = {'cutting': 'cutting_period_immutable', 'jp': 'jp_intake_immutable'}


def _run(path, operation):
    function = runpy.run_path(str(path))['upgrade']
    function.__globals__['op'] = operation
    function()


def _sqlite_contract(bind, table):
    return [tuple(row) for row in bind.execute(sa.text(
        'SELECT type,name,sql FROM sqlite_master WHERE tbl_name=:table ORDER BY type,name'
    ), {'table': table})]


def _sqlite_expected():
    engine = sa.create_engine('sqlite://')
    try:
        with engine.begin() as conn:
            operation = Operations(MigrationContext.configure(conn))
            _run(CUTTING, operation); _run(JP, operation)
            return {name:_sqlite_contract(conn, name) for names in GROUPS.values() for name in names}
    finally:
        engine.dispose()


def _pg_contract(bind, schema, table, base_schema=None):
    inspector = sa.inspect(bind)
    invalid = bind.scalar(sa.text('''SELECT
        EXISTS(SELECT 1 FROM pg_constraint k JOIN pg_class c ON c.oid=k.conrelid
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=:schema AND c.relname=:table AND NOT k.convalidated)
        OR EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
               JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=:schema AND c.relname=:table AND (NOT i.indisvalid OR NOT i.indisready))
        OR EXISTS(SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
               WHERE n.nspname=:schema AND c.relname=:table AND (c.relrowsecurity OR c.relforcerowsecurity))
    '''), {'schema':schema, 'table':table})
    if invalid:
        raise RuntimeError(f'Unvalidated constraint, invalid index or unexpected row-security policy: {table}')
    # Reflect both sides using the same server, including checks, defaults,
    # foreign keys, indexes and all triggers, not just expected trigger names.
    columns = [(c['name'],str(c['type']),c['nullable'],c.get('default'),c.get('identity'),c.get('computed'))
               for c in inspector.get_columns(table, schema=schema)]
    foreign = inspector.get_foreign_keys(table, schema=schema, postgresql_ignore_search_path=True)
    for item in foreign:
        if item.get('referred_schema') in {schema, base_schema or schema}:
            item['referred_schema'] = '<local>'
    triggers = bind.execute(sa.text('''
        SELECT t.tgname, t.tgenabled, pg_get_triggerdef(t.oid), p.prosrc,
               p.prosecdef, p.provolatile, p.proconfig, l.lanname
        FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        JOIN pg_namespace n ON n.oid=c.relnamespace JOIN pg_proc p ON p.oid=t.tgfoid
        JOIN pg_language l ON l.oid=p.prolang
        WHERE n.nspname=:schema AND c.relname=:table AND NOT t.tgisinternal ORDER BY t.tgname
    '''), {'schema':schema, 'table':table}).all()
    normalized = [tuple(value.replace('"'+schema+'".', '<self>.').replace(schema+'.', '<self>.')
                        if isinstance(value, str) else value for value in row) for row in triggers]
    return (columns, inspector.get_pk_constraint(table,schema=schema),
            inspector.get_unique_constraints(table,schema=schema),
            inspector.get_check_constraints(table,schema=schema),
            inspector.get_indexes(table,schema=schema), foreign, normalized)


def _pg_expected(bind):
    # PostgreSQL reference DDL lives only in a private probe schema in a rolled
    # back savepoint. Existing business tables are never rewritten. CREATE
    # SCHEMA privilege is required; insufficient rights fail closed.
    schema = 'cutting_0167_probe_' + uuid4().hex
    original = bind.scalar(sa.text('SELECT current_schema()'))
    transaction = bind.begin_nested()
    try:
        bind.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        quoted_original = original.replace('"', '""')
        bind.execute(sa.text("SELECT set_config('search_path', :path, true)"), {'path':f'"{schema}","{quoted_original}"'})
        operation = Operations(MigrationContext.configure(bind))
        _run(CUTTING, operation); _run(JP, operation)
        return {name:_pg_contract(bind, schema, name, original) for names in GROUPS.values() for name in names}
    finally:
        transaction.rollback()


def preflight(bind):
    """Validate before any successor DDL, and again immediately before repair."""
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    present = {group:[name in tables for name in names] for group,names in GROUPS.items()}
    versions = set(bind.scalars(sa.text('SELECT version_num FROM alembic_version'))) if 'alembic_version' in tables else set()
    if versions not in VALID_VERSIONS or not any(any(p) for p in present.values()):
        raise RuntimeError('Unknown 0163 collision history; inspect version and schema before upgrading')
    for group, flags in present.items():
        if any(flags) and not all(flags):
            raise RuntimeError(f'Partial 0163 schema group: {group}; no repair was applied')
    if revision in versions and not all(all(flags) for flags in present.values()):
        raise RuntimeError('Reconciled 0167 schema is incomplete; refusing automatic repair')
    if bind.dialect.name == 'sqlite':
        expected = _sqlite_expected()
        for group, names in GROUPS.items():
            for name in names:
                actual = _sqlite_contract(bind, name)
                if all(present[group]) and actual != expected[name]:
                    raise RuntimeError(f'0163 schema drift: {name}; existing evidence was not changed')
                # An absent table can still have a reserved index/trigger name
                # attached to another table; fail before the first CREATE.
                if not any(present[group]):
                    for _, object_name, _ in expected[name]:
                        if bind.scalar(sa.text('SELECT count(*) FROM sqlite_master WHERE name=:name'), {'name':object_name}):
                            raise RuntimeError(f'Orphan/conflicting 0163 schema object: {object_name}')
        if bind.exec_driver_sql('PRAGMA quick_check').all() != [('ok',)] or bind.exec_driver_sql('PRAGMA foreign_key_check').first():
            raise RuntimeError('Existing database integrity damage; collision repair refused')
    elif bind.dialect.name == 'postgresql':
        schema = bind.scalar(sa.text('SELECT current_schema()'))
        expected = _pg_expected(bind)
        for group,names in GROUPS.items():
            if all(present[group]):
                for name in names:
                    if _pg_contract(bind, schema, name) != expected[name]:
                        raise RuntimeError(f'0163 PostgreSQL schema drift: {name}')
            else:
                function = bind.scalar(sa.text('SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=:schema AND p.proname=:name'), {'schema':schema,'name':FUNCTIONS[group]})
                reserved = set(names)
                for name in names:
                    reserved.update(i['name'] for i in expected[name][4])
                    reserved.add(expected[name][1]['name'])
                    reserved.update(i['name'] for i in expected[name][2])
                objects = set(bind.scalars(sa.text('SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema'), {'schema':schema}))
                trigger_names = {row[0] for name in names for row in expected[name][6]}
                actual_triggers = set(bind.scalars(sa.text('SELECT t.tgname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=:schema'), {'schema':schema}))
                if function or objects & reserved or actual_triggers & trigger_names:
                    raise RuntimeError(f'Orphan/conflicting PostgreSQL schema objects: {group}')
    else:
        raise RuntimeError('0163 reconciliation supports only SQLite and PostgreSQL')
    return {group:not any(flags) for group,flags in present.items()}


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError('0167 requires live schema inspection; offline SQL cannot reconcile legacy 0163')
    bind = op.get_bind()
    plan = preflight(bind)
    with bind.begin_nested():
        if plan['cutting']:
            _run(CUTTING, op)
        if plan['jp']:
            _run(JP, op)


def downgrade():
    raise RuntimeError('Reconciled cutting and JP evidence cannot be deleted; use verified backup recovery')
