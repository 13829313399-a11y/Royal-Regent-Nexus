import importlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException

from test_iam_api import create_user, login, make_client


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv('SEED_DEFAULT_ACCOUNTS', 'true')
    monkeypatch.setenv('IAM_IDENTITY_WRITES_ENABLED', 'false')
    monkeypatch.setenv('IAM_IDENTITY_SCHEDULING_ENABLED', 'false')
    with make_client(monkeypatch) as api:
        yield api


def registration(username, **kwargs):
    return dict(username=username, display_name='同名员工', password='TestPass123!', confirm_password='TestPass123!',
        phone=kwargs.get('phone', '13800001234'), email=kwargs.get('email', ''),
        factory_id='huaxing', department='engineering', position='工程师')


def modules():
    return importlib.import_module('app.db'), importlib.import_module('app.models.auth')


@pytest.mark.parametrize('first,second,field', [
    ({'phone': '138 0000-1234'}, {'phone': '+86 (138) 0000 1234'}, 'phone'),
    ({'phone': '0086 13800001234'}, {'phone': '１３８００００１２３４'}, 'phone'),
    ({'phone': '', 'email': ' Employee@Example.com '}, {'phone': '', 'email': 'employee@example.com'}, 'email'),
])
def test_pending_contact_reuse_is_rejected_before_creating_another_account(client, first, second, field):
    assert client.post('/api/auth/register', json=registration('first', **first)).status_code == 200
    response = client.post('/api/auth/register', json=registration('second', **second))
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'AUTH_REGISTRATION_CONTACT_CONFLICT'
    assert response.json()['field_errors'][0]['field'] == field
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        assert db.query(models.AuthUser).filter_by(username='second').count() == 0
        assert db.query(models.AuthRegistrationRequest).filter_by(username='second').count() == 0


@pytest.mark.parametrize('status', ['active', 'suspended', 'pending'])
def test_current_profile_contacts_are_reserved_for_existing_accounts(client, status):
    target = create_user('existing', 'engineer', 'huaxing', 'engineering')
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        db.get(models.AuthUser, target).status = status
        db.get(models.EmployeeProfile, target).phone = '13800001234'
        db.commit()
    response = client.post('/api/auth/register', json=registration('another'))
    assert response.status_code == 409, response.text


def test_same_name_different_contacts_and_rejected_reapplication(client):
    first = client.post('/api/auth/register', json=registration('first')).json()
    assert client.post('/api/auth/register', json=registration('same-name', phone='13900001234')).status_code == 200
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        request = db.get(models.AuthRegistrationRequest, first['request_id'])
        request.status = 'rejected'
        target = request.user_id
        db.get(models.AuthUser, target).status = 'rejected'
        db.commit()
    # Reapplication reuses the account, but its current pending contacts take precedence.
    response = client.post('/api/auth/register', json=registration('first', phone='13700001234'))
    assert response.status_code == 200, response.text
    assert client.post('/api/auth/register', json=registration('reuse-old', phone='13800001234')).status_code == 200
    assert client.post('/api/auth/register', json=registration('duplicate-new', phone='13700001234')).status_code == 409
    with dbm.SessionLocal() as db:
        assert db.query(models.AuthUser).filter_by(username='first').one().id == target


def test_approval_cannot_correct_contacts_to_another_current_account(client):
    target = create_user('existing', 'engineer', 'huaxing', 'engineering')
    dbm, models = modules()
    with dbm.SessionLocal() as db:
        db.get(models.EmployeeProfile, target).phone = '13800001234'
        db.commit()
    payload = registration('applicant', phone='13900001234')
    registered = client.post('/api/auth/register', json=payload).json()
    login(client, 'admin')
    profile = {key: payload[key] for key in ('display_name', 'phone', 'email', 'factory_id', 'department', 'position')}
    response = client.post(f"/api/system/registration-requests/{registered['request_id']}/approve", json={
        'system_position_role_id': 'position_engineering_engineer', 'profile': {**profile, 'phone': '13800001234'}})
    assert response.status_code == 409, response.text
    with dbm.SessionLocal() as db:
        request = db.get(models.AuthRegistrationRequest, registered['request_id'])
        assert request.status == 'pending'
        assert db.get(models.AuthUser, request.user_id).status == 'pending'
        assert db.query(models.AuthUserRole).filter_by(user_id=request.user_id).count() == 0


def test_concurrent_duplicate_registration_has_only_one_winner(client):
    dbm, models = modules()
    auth = importlib.import_module('app.services.auth')
    schema = importlib.import_module('app.schemas.auth')
    ready = Barrier(2)
    def register(username):
        with dbm.SessionLocal() as db:
            ready.wait(timeout=10)
            try:
                auth.register_user(db, schema.RegisterRequest(**registration(username)))
                return 200
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(register, ['race-one', 'race-two']))
    assert sorted(results) == [200, 409]
    with dbm.SessionLocal() as db:
        assert db.query(models.AuthUser).filter(models.AuthUser.username.in_(['race-one', 'race-two'])).count() == 1
