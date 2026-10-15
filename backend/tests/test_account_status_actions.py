import importlib

import pytest
from fastapi.testclient import TestClient

from test_identity_changes import client, confirm
from test_iam_api import create_user, login


@pytest.fixture(autouse=True)
def seeds(monkeypatch):
    monkeypatch.setenv('SEED_DEFAULT_ACCOUNTS', 'true')


@pytest.mark.parametrize('formal_identity', [False, True])
def test_direct_stop_and_restore_revoke_sessions_and_preserve_sources(client, monkeypatch, formal_identity):
    target = create_user('status-target', 'engineer', 'huakang-a', 'engineering')
    if formal_identity:
        confirm(client, target)
    monkeypatch.setattr(importlib.import_module('app.core.config').settings, 'iam_identity_writes_enabled', False)
    browser = TestClient(client.app)
    login(browser, 'status-target')
    before = client.get(f'/api/system/users/{target}/identity').json()
    stopped = client.patch(f'/api/system/users/{target}/status', json={'status': 'suspended'})
    assert stopped.status_code == 200, stopped.text
    assert browser.get('/api/auth/me').status_code == 401
    assert browser.post('/api/auth/login', json={'username': 'status-target', 'password': '123456'}).status_code == 401
    current = client.get(f'/api/system/users/{target}/identity').json()
    assert current['status'] == 'suspended' and current['employment_status'] == 'frozen'
    # An exact repeat does not create more revisions or authorization changes.
    assert client.patch(f'/api/system/users/{target}/status', json={'status': 'suspended'}).status_code == 200
    repeated = client.get(f'/api/system/users/{target}/identity').json()
    assert repeated['identity_version'] == current['identity_version']
    assert repeated['authorization_version'] == current['authorization_version']
    assert client.patch(f'/api/system/users/{target}/status', json={'status': 'active'}).status_code == 200
    assert browser.get('/api/auth/me').status_code == 401
    login(browser, 'status-target')
    after = client.get(f'/api/system/users/{target}/identity').json()
    assert after['assignments'] == before['assignments']
    assert after['role_bindings'] == before['role_bindings']
    browser.close()


@pytest.mark.parametrize('status', ['pending', 'rejected', 'retired'])
def test_direct_status_cannot_bypass_registration_or_retirement(client, status):
    target = create_user('invalid-status', 'engineer', 'huakang-a', 'engineering')
    models, dbm = importlib.import_module('app.models.auth'), importlib.import_module('app.db')
    with dbm.SessionLocal() as db:
        db.get(models.AuthUser, target).status = status
        db.commit()
    for desired in ('active', 'suspended'):
        response = client.patch(f'/api/system/users/{target}/status', json={'status': desired})
        assert response.status_code == 409, response.text
    with dbm.SessionLocal() as db:
        assert db.get(models.AuthUser, target).status == status


def test_last_admin_and_out_of_scope_stops_are_blocked(client):
    response = client.patch('/api/system/users/user-admin/status', json={'status': 'suspended'})
    assert response.status_code in (400, 409), response.text
    local = create_user('status-manager', 'engineer', 'huakang-a', 'engineering')
    local_target = create_user('status-local', 'engineer', 'huakang-a', 'engineering')
    foreign = create_user('status-foreign', 'engineer', 'huakang-b', 'engineering')
    models, dbm = importlib.import_module('app.models.auth'), importlib.import_module('app.db')
    with dbm.SessionLocal() as db:
        permission = db.query(models.AuthPermission).filter_by(code='system:user_manage').one()
        db.add(models.AuthUserPermissionOverride(id='status-manager-grant', user_id=local, permission_id=permission.id,
            effect='allow', factory_id='huakang-a', department='engineering', status='active'))
        db.commit()
    login(client, 'status-manager')
    assert client.patch(f'/api/system/users/{local_target}/status', json={'status': 'suspended'}).status_code == 200
    assert client.patch(f'/api/system/users/{foreign}/status', json={'status': 'suspended'}).status_code == 403
