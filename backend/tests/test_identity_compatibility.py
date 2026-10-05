"""Exercise the independently built fallback artifact against a synthetic copy."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from test_identity_acceptance import client
from test_identity_changes import commit, draft, engineer, identity
from test_identity_lifecycle_contract import modules
from test_iam_api import login


def test_built_fallback_keeps_revocation_sessions_and_timeline(client, tmp_path):
    configured = os.getenv("IAM_TEST_COMPAT_RELEASE")
    if not configured:
        pytest.skip("Build a separate artifact and set IAM_TEST_COMPAT_RELEASE")
    release = Path(configured).resolve()
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["kind"] == "iam-v2-compatible-fallback" and manifest["identity_ui"] is False
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((release / name).read_bytes()).hexdigest() == expected, name
    target = engineer(client)
    login(client, "identity-engineer")
    old_cookie = client.cookies.get("rr_session")
    login(client, "admin")
    for operation in ("freeze", "unfreeze"):
        assert commit(client, draft(client, target, operation)).status_code == 200
    row = draft(client, target, "primary_assignment_transfer", source_assignment_id=identity(client, target)["primary_assignment"]["id"],
        new_assignment={"org_unit_id": "huaxing", "department_code": "pmc-warehouse", "official_position_title": "兼容回退仓管",
                        "role_bindings": [{"role_id": "warehouse_keeper", "department": "pmc-warehouse"}]})
    assert commit(client, row).status_code == 200
    # Leave old bindings present: a raw V1 reader would wrongly re-enable A engineering.
    dbm, _, _, _, clock = modules()
    from datetime import timedelta
    boundary = clock.utc_now() + timedelta(days=1)
    future = draft(client, target, "primary_assignment_transfer", source_assignment_id=identity(client, target)["primary_assignment"]["id"],
        effective_at=clock.stamp(boundary), new_assignment={"org_unit_id": "huakang-b", "department_code": "engineering", "official_position_title": "预约工程师",
                        "role_bindings": [{"role_id": "engineer", "department": "engineering"}]})
    assert commit(client, future).status_code == 200
    database = tmp_path / "fallback.db"
    with sqlite3.connect(dbm.engine.url.database) as source, sqlite3.connect(database) as copy:
        source.backup(copy)
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps({"target": target, "old_cookie": old_cookie, "boundary": clock.stamp(boundary)}), encoding="utf-8")
    script = r'''
import json, os
from datetime import timedelta
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import select
from iam_compat_entrypoint import app
from app.core.config import settings
from app.db import SessionLocal
from app.models.auth import AuthUser, EmployeeProfile
from app.services import auth, identity_resolver as clock
data = json.loads(Path(os.environ['IAM_QA_FIXTURE']).read_text(encoding='utf-8'))
assert not settings.iam_identity_writes_enabled and not settings.iam_identity_scheduling_enabled
with TestClient(app) as api:
    api.cookies.set('rr_session', data['old_cookie'])
    assert api.get('/api/auth/me').status_code == 401
    api.cookies.clear()
    assert api.post('/api/auth/login', json={'username':'identity-engineer','password':'123456'}).status_code == 200
    boundary = clock.instant(data['boundary'])
    for at, factory in ((boundary-timedelta(microseconds=1),'huaxing'), (boundary,'huakang-b')):
        clock.utc_now = lambda: at
        response = api.get('/api/auth/me')
        assert response.status_code == 200, response.text
        assert response.json()['profile']['primary_factory_id'] == factory
        with SessionLocal() as db:
            context = auth.build_auth_context(db, db.get(AuthUser,data['target']))
            assert not auth.can(context, 'molding_sample:create', 'huakang-a', 'engineering')
            assert auth.can(context, 'molding_sample:create', 'huakang-b', 'engineering') == (at >= boundary)
            assert db.get(EmployeeProfile,data['target']).primary_factory_id == 'huaxing'
    api.cookies.clear()
    assert api.post('/api/auth/login', json={'username':'admin','password':'AdminSeed123!'}).status_code == 200
    assert api.get('/api/system/organization-catalog').json()['writes_enabled'] is False
    result = api.post('/api/iam/identity-changes', json={'request_type':'profile_correction','target_user_id':data['target'],
        'reason':'compatibility gate','base_identity_version':0,'base_authorization_version':0,'official_position_title':'forbidden'})
    assert result.status_code == 403 and result.json()['detail']['code'] == 'IDENTITY_WRITES_DISABLED', result.text
print(json.dumps({'mode':settings.authz_mode,'old_cookie':401,'old_source_allowed':False,'timeline_at_T':'huakang-b','new_writes':403}))
'''
    for mode in ("legacy", "shadow", "enforce"):
        env = dict(os.environ, DATABASE_URL=f"sqlite:///{database.as_posix()}", PYTHONPATH=str(release / "backend"),
            IAM_QA_FIXTURE=str(fixture), AUTHZ_MODE=mode, AUTHZ_WRITES_ENABLED="true" if mode == "enforce" else "false", IAM_IDENTITY_WRITES_ENABLED="true",
            SPRAY_OPS_ENABLED="false", UV_OPS_ENABLED="false", THREE_D_CONNECTOR_ENABLED="false")
        result = subprocess.run([sys.executable, "-c", script], cwd=release, env=env,
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        assert result.returncode == 0, result.stderr[-8000:]
        assert json.loads(result.stdout.splitlines()[-1])["old_source_allowed"] is False
