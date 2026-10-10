"""Actual cookie login + current IAM evaluation using synthetic users in temporary SQLite."""
from sqlalchemy import delete
from sqlalchemy.orm import Session
import pytest
from app.api import auth as auth_api
from app.models.auth import AuthUser, AuthRole, AuthPermission, AuthRolePermission, AuthUserRole, AuthUserPermissionOverride, EmployeeProfile, AuthIamState
from app.services.auth import get_current_user, hash_password
from test_cutting_ops import client, command, BASE
from test_cutting_orders import flow, submitted


@pytest.fixture
def session_flow(flow, monkeypatch):
    submitted(flow)
    AuthUser.metadata.create_all(flow.engine)
    flow.app.include_router(auth_api.router)
    flow.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(auth_api.settings, 'session_cookie_secure', False)
    actions = ['read', 'order_receive', 'bom_write', 'requisition_submit', 'eta_write', 'requisition_reconcile', 'plan_write', 'plan_publish', 'report_write', 'report_review', 'handover_write', 'acceptance_write']
    with Session(flow.engine) as db:
        # Required IAM invariant row, seeded by the real migration in deployed databases.
        db.add(AuthIamState(key='identity_mutation_lock', value_json='{}'))
        for action in actions:
            db.add(AuthPermission(id='cutting_ops:'+action, code='cutting_ops:'+action, name=action))
        for name, dept, factory in [('production', 'production', 'huakang-c'), ('engineering', 'engineering', 'huakang-c'),
                                    ('procurement', 'pmc-warehouse', 'huakang-c'), ('reader', 'production', 'huakang-c'),
                                    ('foreign', 'production', 'huakang-d'), ('ungranted', 'production', 'huakang-c')]:
            db.add(AuthUser(id=name, username='cutting-test-'+name, display_name=name, password_salt='synthetic-salt', password_hash=hash_password('SyntheticPassword123!', 'synthetic-salt'), status='active'))
            db.add(AuthRole(id=name, code='cutting-test-'+name, name=name))
        db.flush()
        for name, dept, factory in [('production', 'production', 'huakang-c'), ('engineering', 'engineering', 'huakang-c'),
                                    ('procurement', 'pmc-warehouse', 'huakang-c'), ('reader', 'production', 'huakang-c'),
                                    ('foreign', 'production', 'huakang-d'), ('ungranted', 'production', 'huakang-c')]:
            db.add(EmployeeProfile(user_id=name, primary_factory_id=factory, primary_department=dept, confirmation_status='confirmed'))
            db.add(AuthUserRole(id=name, user_id=name, role_id=name, factory_id=factory, department=dept))
            granted = ['read'] if name == 'reader' else [] if name == 'ungranted' else actions
            for action in granted:
                db.add(AuthRolePermission(id=name+':'+action, role_id=name, permission_id='cutting_ops:'+action))
        db.commit()
    yield flow


def login(client, name):
    client.cookies.clear()
    response = client.post('/api/auth/login', json={'username': 'cutting-test-'+name, 'password': 'SyntheticPassword123!'})
    assert response.status_code == 200, response.text
    assert 'HttpOnly' in response.headers['set-cookie']


@pytest.mark.parametrize('name,action,payload,expected', [
    ('engineering', 'withdraw', {'requisition_version': 3}, 200),
    ('production', 'withdraw', {'requisition_version': 3}, 403),
    ('procurement', 'eta', {'requisition_version': 3, 'batches': []}, 200),
    ('engineering', 'eta', {'requisition_version': 3, 'batches': []}, 403),
    ('reader', 'eta', {'requisition_version': 3, 'batches': []}, 403),
    ('foreign', 'withdraw', {'requisition_version': 3}, 403),
    ('ungranted', 'withdraw', {'requisition_version': 3}, 403),
])
def test_real_session_factory_and_department_isolation(session_flow, name, action, payload, expected):
    login(session_flow, name)
    response = session_flow.post(BASE+'/orders/line-1/'+action, json=command(expected_version=3, **payload))
    assert response.status_code == expected, response.text


def test_real_session_observes_revocation_deny_logout_and_suspension(session_flow):
    login(session_flow, 'procurement')
    url = BASE+'/orders/line-1/eta'
    def eta():
        return session_flow.post(url, json=command(expected_version=3, requisition_version=3, batches=[]))
    with Session(session_flow.engine) as db:
        db.add(AuthUserPermissionOverride(id='explicit-deny', user_id='procurement', permission_id='cutting_ops:eta_write', effect='deny', factory_id='huakang-c', department='pmc-warehouse'))
        db.commit()
    assert eta().status_code == 403
    with Session(session_flow.engine) as db:
        db.execute(delete(AuthUserPermissionOverride))
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id == 'procurement:eta_write'))
        db.commit()
    assert eta().status_code == 403
    assert session_flow.get(BASE+'/orders?factory_id=huakang-c').status_code == 200
    assert session_flow.post('/api/auth/logout').status_code == 204
    assert session_flow.get(BASE+'/orders?factory_id=huakang-c').status_code == 401
    login(session_flow, 'procurement')
    with Session(session_flow.engine) as db:
        db.get(AuthUser, 'procurement').status = 'suspended'; db.commit()
    assert session_flow.get(BASE+'/orders?factory_id=huakang-c').status_code == 401


@pytest.mark.parametrize('name,expected', [('production',409),('engineering',403),('procurement',403),('reader',403),('foreign',403)])
def test_real_session_plan_publish_scope(session_flow,name,expected):
    login(session_flow,name)
    response=session_flow.post(BASE+'/orders/line-1/plan-publish',json=command(expected_version=3,draft_version=3))
    # Production passes authorization, but cannot publish a nonexistent draft.
    assert response.status_code==expected,response.text


@pytest.mark.parametrize('name,expected', [('production',True),('engineering',False),('procurement',False),('reader',False),('foreign',False)])
def test_real_session_reporting_access_is_explicit_production(session_flow,name,expected):
    login(session_flow,name)
    response=session_flow.get(BASE+'/access?factory_id=huakang-c')
    if name=='foreign':
        assert response.status_code==403
    else:
        assert response.status_code==200
        assert all((action in response.json()['permissions'])==expected for action in ('report_write','report_review','handover_write','acceptance_write'))
