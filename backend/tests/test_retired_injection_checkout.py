import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

from tools.repair_retired_injection_bom import repair


@pytest.fixture
def retired(tmp_path):
    path = tmp_path / "retired.db"
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE alembic_version (version_num TEXT);
            INSERT INTO alembic_version VALUES ('20261104_0190');
            CREATE TABLE auth_permissions (code TEXT);
            INSERT INTO auth_permissions VALUES ('three_d_printing:read');
            CREATE TABLE internal_quote_pricing_baselines (id TEXT);
            INSERT INTO internal_quote_pricing_baselines VALUES ('baseline');
            CREATE TABLE nexus_assistant_run_metrics (run_id TEXT);
        """)
    return path


def test_bom_repair_reuses_0190_and_preserves_every_existing_row(retired):
    original = retired.read_bytes()
    assert repair(retired) == "repair_required"
    assert retired.read_bytes() == original
    assert repair(retired, apply=True) == "repaired"
    with closing(sqlite3.connect(retired)) as db:
        assert db.execute("SELECT * FROM alembic_version").fetchall() == [("20261104_0190",)]
        assert db.execute("SELECT * FROM internal_quote_pricing_baselines").fetchall() == [("baseline",)]
        db.execute("INSERT INTO engineering_bom_events VALUES ('e','huakang-c','op','hash','entity','test',1,'{}','actor','now','test')")
        for sql in ("UPDATE engineering_bom_events SET reason='edited'", "DELETE FROM engineering_bom_events"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable engineering evidence"):
                db.execute(sql)
        db.commit()
    snapshot = retired.read_bytes()
    assert repair(retired, apply=True) == "already_repaired"
    assert retired.read_bytes() == snapshot


@pytest.mark.parametrize(("damage", "message"), [
    ("CREATE TABLE injection_v3_demands (id TEXT)", "retired injection"),
    ("INSERT INTO auth_permissions VALUES ('injection_scheduling:plan')", "permissions"),
    ("UPDATE alembic_version SET version_num='20261105_0196'", "history"),
    ("UPDATE alembic_version SET version_num='20261107_0193'", "0191"),
    ("CREATE TABLE engineering_bom_documents (id TEXT)", "Partial"),
])
def test_unrecognized_state_is_rejected_before_writing(retired, damage, message):
    with closing(sqlite3.connect(retired)) as db:
        db.execute(damage)
        db.commit()
    before = retired.read_bytes()
    with pytest.raises(ValueError, match=message):
        repair(retired, apply=True)
    assert retired.read_bytes() == before


def test_collision_partway_through_ddl_rolls_back_both_tables(retired):
    with closing(sqlite3.connect(retired)) as db:
        db.execute("CREATE INDEX ix_engineering_bom_events_entity_id ON auth_permissions(code)")
        db.commit()
    with pytest.raises(OperationalError, match="already exists"):
        repair(retired, apply=True)
    assert repair(retired) == "repair_required"


@pytest.mark.parametrize("enabled", [False, True])
def test_scheduling_v3_remains_available_without_enabling_draft_ops(tmp_path, enabled):
    path = tmp_path / "profile.db"
    environment = dict(os.environ, DATABASE_URL="sqlite:///" + path.as_posix(),
                       INJECTION_SCHEDULING_V3_ENABLED=str(enabled), INJECTION_OPS_ENABLED=str(enabled),
                       QC_DEPARTMENT_MANAGED="false",
                       SEED_DEFAULT_ACCOUNTS="false", SEED_ADMIN_PASSWORD="")
    script = """
from sqlalchemy import inspect, text
from app import db
from app.main import app
from app.services.assistant import business, registry
from app.services.permission_codes import APPLICATION_PERMISSION_CODES
from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS

paths = app.openapi()['paths']
assert '/api/injection-scheduling/demands/query' in paths
assert '/api/injection' in paths
assert not any(path.startswith('/api/injection-ops/') for path in paths)
assert registry.resolve('injection-scheduling', 'demand') == 'get_injection_overview'
assert 'get_injection_overview' in business.NAMES
grants = {code for role in SYSTEM_POSITION_DEFINITIONS for code in role.permission_codes}
assert 'injection_scheduling:read' in APPLICATION_PERMISSION_CODES
assert 'injection_scheduling:read' in grants
assert not any(code.startswith('injection_ops:') for code in {*APPLICATION_PERMISSION_CODES, *grants})
db.init_db()
db.init_db()
tables = set(inspect(db.engine).get_table_names())
assert {'injection_v3_demand', 'injection_v3_machine', 'injection_v3_shift_report'} <= tables
assert not any(name.startswith('injection_ops_') for name in tables)
with db.engine.connect() as conn:
    stored = set(conn.scalars(text('SELECT code FROM auth_permissions')))
    assert 'injection_scheduling:read' in stored
    assert not any(code.startswith('injection_ops:') for code in stored)
"""
    subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                   env=environment, check=True, timeout=90)
