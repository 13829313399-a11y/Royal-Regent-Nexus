"""Last-login display uses the existing personnel read boundary and stored data."""
import importlib
from datetime import datetime

import pytest

from test_iam_api import create_user, login, make_client


@pytest.fixture(autouse=True)
def seed_test_accounts(monkeypatch):
    monkeypatch.setenv('SEED_DEFAULT_ACCOUNTS', 'true')


def read_login_times(client, target):
    response = client.get('/api/system/people', params={'q': 'login-target'})
    assert response.status_code == 200, response.text
    person = next(item for item in response.json()['items'] if item['id'] == target)
    detail = client.get(f'/api/system/users/{target}/identity')
    assert detail.status_code == 200, detail.text
    return person['last_login_at'], detail.json()['last_login_at']


@pytest.mark.parametrize('stored,expected', [
    ('', ''),
    ('2026-10-14T02:05:09Z', '2026-10-14T02:05:09+00:00'),
    ('2026-10-14 10:05:09', datetime(2026, 10, 14, 10, 5, 9).astimezone().isoformat()),
])
def test_people_and_identity_serialize_last_login_without_rewriting_storage(monkeypatch, stored, expected):
    with make_client(monkeypatch) as client:
        target = create_user('login-target', 'engineer', 'huakang-a', 'engineering')
        models = importlib.import_module('app.models.auth')
        db_module = importlib.import_module('app.db')
        with db_module.SessionLocal() as db:
            db.get(models.AuthUser, target).last_login_at = stored
            db.commit()
        login(client, 'admin')
        assert read_login_times(client, target) == (expected, expected)
        with db_module.SessionLocal() as db:
            assert db.get(models.AuthUser, target).last_login_at == stored


def test_successful_login_updates_display_but_failed_login_does_not(monkeypatch):
    with make_client(monkeypatch) as client:
        target = create_user('login-target', 'engineer', 'huakang-a', 'engineering')
        login(client, 'admin')
        assert read_login_times(client, target) == ('', '')
        login(client, 'login-target')
        login(client, 'admin')
        listed, detail = read_login_times(client, target)
        assert listed == detail
        assert datetime.fromisoformat(listed).tzinfo is not None
        failed = client.post('/api/auth/login', json={'username': 'login-target', 'password': 'wrong-password'})
        assert failed.status_code == 401
        assert read_login_times(client, target) == (listed, listed)


def test_login_times_remain_limited_to_manageable_people(monkeypatch):
    with make_client(monkeypatch) as client:
        local = create_user('login-target-local', 'engineer', 'huakang-a', 'engineering')
        foreign = create_user('login-target-foreign', 'engineer', 'huakang-b', 'engineering')
        create_user('login-reader', 'position_engineering_engineer', 'huakang-a', 'engineering')
        models = importlib.import_module('app.models.auth')
        db_module = importlib.import_module('app.db')
        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(code='system:user_manage').one()
            db.add(models.AuthRolePermission(id=f'login-reader:{permission.id}',
                role_id='position_engineering_engineer', permission_id=permission.id))
            db.commit()
        login(client, 'login-reader')
        response = client.get('/api/system/people', params={'q': 'login-target'})
        assert response.status_code == 200, response.text
        assert [item['id'] for item in response.json()['items']] == [local]
        assert client.get(f'/api/system/users/{local}/identity').json()['last_login_at'] == ''
        denied = client.get(f'/api/system/users/{foreign}/identity')
        assert denied.status_code == 403
        assert 'last_login_at' not in denied.json()
        login(client, 'login-target-local')
        assert client.get('/api/system/people').status_code == 403
        assert client.get(f'/api/system/users/{local}/identity').status_code == 403
