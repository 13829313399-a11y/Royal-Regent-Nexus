"""Canonical supplier material authorization in a legacy deployment."""
import pytest
from test_molding_sample_api import make_client, login_as
from test_carton_supplier_portal import setup_portal, supplier_login, revoke_supplier_permission


BASE = '/api/iam/users/supplier-test/access'


def preview(client, code='carton_asset:read', factory='*', department='*'):
    current = client.get(BASE).json()
    return client.post(BASE + '/preview', json={
        'base_revision': current['authorization_version'], 'reason': '验证供应商资料权限边界',
        'overrides': [dict(permission_code=code, effect='allow', factory_id=factory, department=department)]})


def commit(client, response):
    assert response.status_code == 200, response.text
    return client.post(BASE + '/commit', json={
        'preview_token': response.json()['preview_token'], 'confirm_high_risk': True})


def environment(monkeypatch):
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('AUTHZ_MODE', 'legacy')
    monkeypatch.setenv('AUTHZ_WRITES_ENABLED', 'false')
    return make_client(monkeypatch)


def test_supplier_material_grant_is_audited_scoped_and_restart_safe(monkeypatch):
    with environment(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        for code in ('carton_asset:read', 'carton_asset:manage'):
            result = commit(client, preview(client, code))
            assert result.status_code == 200, result.text
        from app.db import SessionLocal
        from app.models.auth import AuthUser, AuthAuthorizationEvent
        from app.services.auth import build_auth_context, ensure_authz_startup_safety
        from app.services.carton_asset_access import allowed, DEPARTMENTS
        from app.services.carton_supplier_portal import supplier_permission
        with SessionLocal() as db:
            user = build_auth_context(db, db.get(AuthUser, 'supplier-test'))
            assert allowed(user, 'huaxing', 'supplier', 'read')
            assert allowed(user, 'huaxing', 'supplier', 'manage')
            assert not allowed(user, 'huaxing', 'supplier', 'confirm')
            for department in DEPARTMENTS:
                for action in ('read', 'manage', 'confirm'):
                    assert not allowed(user, 'huaxing', department, action)
            assert db.query(AuthAuthorizationEvent).filter_by(
                target_user_id='supplier-test', event_type='permission_override_set').count() == 2
            ensure_authz_startup_safety(db)
            from app.services.internal_members import is_internal, eligible_member_ids
            assert not is_internal(user)
            assert user.id not in eligible_member_ids(db)
        supplier_login(client)
        assert client.get('/api/auth/me').json()['internal_member'] is False
        assert client.get('/api/directory/summary').status_code == 403
        assert client.get('/api/directory/members').status_code == 403
        assert client.post('/api/directory/presence/heartbeat').status_code == 403
        # Revoking the supplier gate disables access; dormant asset grants must
        # not make the next application startup fail.
        revoke_supplier_permission('carton_supplier:read')
        supplier_login(client, expect_read=False)
        assert client.get('/api/carton-supplier/carton-mark/assets',
                          params={'factory_id': 'huaxing'}).status_code == 403
        with SessionLocal() as db:
            user = build_auth_context(db, db.get(AuthUser, 'supplier-test'))
            assert not supplier_permission(user, 'carton_supplier:read', 'huaxing')
            ensure_authz_startup_safety(db)


def test_supplier_dependency_is_rechecked_at_commit(monkeypatch):
    with environment(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        draft = preview(client)
        revoke_supplier_permission('carton_supplier:read')
        assert commit(client, draft).status_code == 409
        assert preview(client).status_code == 409
        supplier_login(client, expect_read=False)
        assert client.post(BASE + '/preview', json={
            'base_revision': 1, 'reason': '不能自行授权', 'overrides': [dict(
                permission_code='carton_asset:manage', effect='allow', factory_id='*', department='*')]
        }).status_code == 403


@pytest.mark.parametrize('code,factory,department', [
    ('carton_asset:confirm', '*', '*'),
    ('carton_asset:read', 'huaxing', 'sales-business'),
    ('carton_asset:manage', '*', 'pmc-warehouse'),
])
def test_supplier_exception_does_not_open_internal_or_confirmation_grants(monkeypatch, code, factory, department):
    with environment(monkeypatch) as client:
        setup_portal(client)
        login_as(client, 'admin')
        assert commit(client, preview(client, code, factory, department)).status_code == 503
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        from app.services.auth import ensure_authz_startup_safety
        with SessionLocal() as db:
            permission = db.query(AuthPermission).filter_by(code=code).one()
            db.add(AuthUserPermissionOverride(id='unsafe-grant', user_id='supplier-test',
                permission_id=permission.id, effect='allow', factory_id=factory,
                department=department, status='active', source_type='manual'))
            db.flush()
            with pytest.raises(RuntimeError, match='AUTHZ_MODE must remain enforce'):
                ensure_authz_startup_safety(db)
            db.rollback()
