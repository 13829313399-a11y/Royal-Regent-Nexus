"""Actual Alembic upgrade in an isolated file; never use the configured database."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect


@pytest.mark.parametrize('starting_revision', ['20261009_0150', '20261015_0163', '20261016_0163'])
def test_upgrade_preserves_existing_tables_and_matches_models(tmp_path, starting_revision):
    backend = Path(__file__).resolve().parents[1]
    expected_head = ScriptDirectory(str(backend / 'alembic')).get_current_head()
    assert expected_head is not None
    database = tmp_path / 'cutting-migration.db'
    env = dict(os.environ, DATABASE_URL='sqlite:///' + database.as_posix(), SEED_DEFAULT_ACCOUNTS='false', PYTHONUTF8='1', CUTTING_OPS_ENABLED='false')
    def upgrade(revision):
        result = subprocess.run([sys.executable, '-m', 'alembic', 'upgrade', revision], cwd=backend, env=env, capture_output=True, text=True, encoding='utf-8', timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
    upgrade(starting_revision)
    with sqlite3.connect(database) as db:
        db.execute('CREATE TABLE cutting_preservation_probe (id TEXT PRIMARY KEY, value TEXT)')
        db.execute("INSERT INTO cutting_preservation_probe VALUES ('00001', '真实格式保留')")
        old_tables = db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version'").fetchall()
        old_rows = {name: db.execute('SELECT * FROM "' + name + '"').fetchall() for name, _ in old_tables}
        old_columns = {name: [row[1] for row in db.execute('PRAGMA table_info("' + name + '")')] for name, _ in old_tables}
    # Both published branches join without replaying applied DDL; repeating is a no-op.
    upgrade('head'); upgrade('head')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchall() == [(expected_head,)]
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []
        for name, ddl in old_tables:
            if name == 'carton_order_lines' and 'quantity_rule_json' not in old_columns[name]:
                columns = list(db.execute('PRAGMA table_info(carton_order_lines)'))
                assert [row[1] for row in columns] == old_columns[name] + ['quantity_rule_json']
                assert columns[-1][2:5] == ('TEXT', 0, None)
                assert db.execute('SELECT COUNT(*) FROM carton_order_lines WHERE quantity_rule_json IS NOT NULL').fetchone()[0] == 0
            else:
                assert db.execute('SELECT sql FROM sqlite_master WHERE name=?', (name,)).fetchone()[0] == ddl
            fields = ','.join('"' + column + '"' for column in old_columns[name])
            assert db.execute('SELECT ' + fields + ' FROM "' + name + '"').fetchall() == old_rows[name]
    from app.services.cutting_ops import TABLES, schema_ready
    from app.services.cutting_orders import TABLES as ORDER_TABLES, schema_ready as orders_ready
    engine = create_engine('sqlite:///' + database.as_posix())
    assert schema_ready(engine)
    assert orders_ready(engine)
    from app.services.cutting_reporting import TABLE as PRODUCTION_TABLE, schema_ready as production_ready
    assert production_ready(engine)
    from app.services.cutting_usage import TABLE as USAGE_TABLE, schema_ready as usage_ready
    assert usage_ready(engine)
    from app.models.cutting_period import CuttingPeriodEvent
    from app.services.cutting_period_guards import schema_ready as periods_ready
    assert periods_ready(engine)
    from app.models.cutting_settlement import CuttingSettlementEvent
    from app.services.cutting_settlement import schema_ready as settlements_ready
    assert settlements_ready(engine)
    from app.models.cutting_payment import CuttingPaymentEvent
    from app.services.cutting_payments import schema_ready as payments_ready
    assert payments_ready(engine)
    for table in (*TABLES, *ORDER_TABLES, PRODUCTION_TABLE, USAGE_TABLE, CuttingPeriodEvent.__table__, CuttingSettlementEvent.__table__, CuttingPaymentEvent.__table__):
        actual = {column['name']: column for column in inspect(engine).get_columns(table.name)}
        assert set(actual) == {column.name for column in table.columns}
        for column in table.columns:
            assert actual[column.name]['nullable'] == column.nullable
    engine.dispose()
