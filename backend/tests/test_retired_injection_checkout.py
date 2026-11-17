import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("enabled", [False, True])
def test_retired_profiles_cannot_restore_tables_grants_routes_or_assistant(tmp_path, enabled):
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
assert not any(path.startswith(('/api/injection-scheduling/', '/api/injection-ops/')) for path in paths)
assert '/api/injection' in paths
assert 'injection-scheduling' not in registry.BY_MODULE
assert 'get_injection_overview' not in business.NAMES
prefixes = ('injection_scheduling:', 'injection_ops:')
assert not any(code.startswith(prefixes) for code in APPLICATION_PERMISSION_CODES)
assert not any(code.startswith(prefixes) for role in SYSTEM_POSITION_DEFINITIONS for code in role.permission_codes)
db.init_db()
db.init_db()
assert not any(t.startswith(('injection_v3_', 'injection_ops_')) for t in inspect(db.engine).get_table_names())
with db.engine.connect() as conn:
    assert not any(code.startswith(prefixes) for code in conn.scalars(text('SELECT code FROM auth_permissions')))
"""
    subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).resolve().parents[1],
                   env=environment, check=True, timeout=90)
