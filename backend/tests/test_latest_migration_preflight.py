"""New canonical heads retain historical preflight guards and repeat safely."""
import sqlite3
import pytest
from test_cutting_jp_migration import BACKEND, base_database, clone, migrate, run_ddl, snapshot, version_snapshot

@pytest.fixture(scope='module')
def latest_database(base_database, tmp_path_factory):
    path = clone(base_database, tmp_path_factory.mktemp('latest-head-preflight'))
    migrate(path, '20261102_0189')
    for revision in ('20261104_0190', '20261104_0191', '20261104_0192', '20261107_0193', '20261110_0194', '20261116_0195', '20261119_0197', '20261121_inj_merge'):
        migrate(path, revision)
        before = snapshot(path)
        migrate(path, revision)
        assert snapshot(path) == before
        assert version_snapshot(path) == [(revision,)]
    return path

def test_latest_heads_repeat_without_rewriting_existing_rows(latest_database):
    before = snapshot(latest_database)
    migrate(latest_database, 'head')
    assert snapshot(latest_database) == before
    with sqlite3.connect(latest_database) as db:
        assert db.execute('PRAGMA integrity_check').fetchall() == [('ok',)]
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_carton_process_history_upgrades_with_its_original_note(base_database, tmp_path):
    from sqlalchemy import create_engine
    from app.models.carton_procurement import CartonOrder, CartonOrderLine

    path = clone(base_database, tmp_path)
    migrate(path, '20261110_0194')
    order = dict(factory_id='huaxing', customer_code='TEST', contract_no='TEST', item_no='PAPER')
    engine = create_engine('sqlite:///' + path.as_posix())
    with engine.begin() as conn:
        run_ddl(conn, BACKEND / 'alembic/legacy/20261119_0195_carton_paper_process_notes.py')
        conn.exec_driver_sql("UPDATE alembic_version SET version_num='20261119_0195'")
        conn.execute(CartonOrder.__table__.insert().values(
            **order, id='order', order_no='CT-TEST', customer_name='Test', supplier_id='supplier',
            supplier_name_snapshot='Test supplier', product_order_quantity=100,
            order_date='2026-11-19', due_date='2026-11-26', created_by='test', created_by_name='Test',
            updated_by='test', updated_by_name='Test', created_at='2026-11-19', updated_at='2026-11-19'))
        conn.execute(CartonOrderLine.__table__.insert().values(
            **order, id='line', order_id='order', line_no=1, packaging_type='压线卡',
            paper_quality='A33', specification='30*20', required_quantity=10, unit='张',
            usage_quantity=10, process_note='按样分段压线'))
    engine.dispose()

    current = snapshot(path)
    reconcile = ('-x', 'reconcile_carton_process=1')
    assert 'explicit upgrade' in migrate(path, 'head', success=False).stderr
    assert snapshot(path) == current and version_snapshot(path) == [('20261119_0195',)]
    damaged_dir = tmp_path / 'damaged'
    damaged_dir.mkdir()
    damaged = clone(path, damaged_dir)
    with sqlite3.connect(damaged) as db:
        db.execute('ALTER TABLE carton_order_lines RENAME COLUMN process_note TO unknown_note')
    before = snapshot(damaged)
    assert 'schema differs' in migrate(damaged, 'head', success=False, extra_args=reconcile).stderr
    assert snapshot(damaged) == before and version_snapshot(damaged) == [('20261119_0195',)]

    migrate(path, 'head', extra_args=reconcile)
    assert version_snapshot(path) == [('20261121_inj_merge',)]
    after = snapshot(path)
    retired_prefixes = ('injection_v3_', 'injection_schedule_', 'injection_scheduling_', 'injection_ops_')
    assert not any(name.startswith(retired_prefixes) for name in after)
    retired_permissions = {
        row[0] for row in current['auth_permissions'][1] if row[1].startswith(
            ('injection_schedule_center:', 'injection_scheduling:', 'production:injection_scheduling:', 'injection_ops:')
        )
    }
    assert len(retired_permissions) == 4
    for name, (schema, rows) in current.items():
        if name.startswith(retired_prefixes):
            continue
        if name in {'auth_permissions', 'auth_permission_metadata'}:
            rows = [row for row in rows if row[0] not in retired_permissions]
        assert after[name] == (schema, rows), name
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT process_note FROM carton_order_lines WHERE id=?', ('line',)).fetchone() == ('按样分段压线',)
        assert db.execute('SELECT count(*) FROM three_d_printing_telemetry_ticks').fetchone() == (0,)
        assert db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_published_retirement_upgrades_with_carton_and_3d_intact(base_database, tmp_path):
    path = clone(base_database, tmp_path)
    migrate(path, '20261116_inj_retire')
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO three_d_printing_retention_cursors VALUES ('huakang-a','test-printer','now','keep')")
    migrate(path, 'head')
    assert version_snapshot(path) == [('20261121_inj_merge',)]
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT event_id FROM three_d_printing_retention_cursors").fetchall() == [('keep',)]
        assert 'process_note' in {row[1] for row in db.execute("PRAGMA table_info(carton_order_lines)")}
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='injection_v3_demand'").fetchone()
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_inconsistent_retirement_label_is_rejected_before_writes(latest_database, tmp_path):
    path = clone(latest_database, tmp_path)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE alembic_version SET version_num='20261116_inj_retire'")
    before, versions = snapshot(path), version_snapshot(path)
    assert 'Unrecognized injection retirement history' in migrate(path, 'head', success=False).stderr
    assert (snapshot(path), version_snapshot(path)) == (before, versions)

@pytest.mark.parametrize('damage, message', [
    ('header_index', 'cutting header index is missing'),
    ('history_trigger', '0163 schema drift'),
    ('unknown_revision', 'Unknown 0163 collision history'),
])
def test_latest_head_still_rejects_damage_before_writes(latest_database, tmp_path, damage, message):
    path = clone(latest_database, tmp_path)
    with sqlite3.connect(path) as db:
        if damage == 'header_index':
            db.execute('DROP INDEX ix_cutting_period_headers')
        elif damage == 'history_trigger':
            db.execute('DROP TRIGGER cutting_period_no_update')
        else:
            db.execute("UPDATE alembic_version SET version_num='unknown-history'")
    before, versions = snapshot(path), version_snapshot(path)
    assert message in migrate(path, 'head', success=False).stderr
    assert snapshot(path) == before
    assert version_snapshot(path) == versions
