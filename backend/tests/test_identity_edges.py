import importlib
import pytest
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import select
from test_identity_changes import client, engineer, identity, draft, preview, commit
from test_identity_lifecycle_contract import modules, add_assignment
from test_iam_api import create_user, login


def test_delegation_is_a_ceiling_not_an_authority_and_revocation_invalidates_preview(client):
    target = engineer(client)
    manager = create_user('delegation-manager', 'engineer', 'huakang-a', 'engineering')
    payload = dict(expected_revision=0, org_unit_id='huakang-a', department='engineering',
                   role_ids=['engineer'], factory_ids=['huakang-a'], reason='登记转授范围')
    url = f'/api/iam/users/{manager}/delegations/delegation-test'
    assert client.put(url, json={**payload, 'role_ids': ['admin']}).status_code == 422
    assert client.put(url, json=payload).status_code == 200
    assert client.put(url, json=payload).status_code == 409
    login(client, 'delegation-manager')
    assert client.get('/api/system/people').status_code == 403
    assert client.put(url, json={**payload, 'expected_revision': 1}).status_code == 403
    login(client, 'admin')
    dbm, authm, _, _, _ = modules()
    with dbm.SessionLocal() as db:
        for code in ('system:user_manage', 'system:access_manage'):
            permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == code))
            db.add(authm.AuthUserPermissionOverride(id=uuid4().hex, user_id=manager, permission_id=permission.id,
                effect='allow', factory_id='huakang-a', department='engineering', status='active'))
        db.commit()
    login(client, 'delegation-manager')
    row = draft(client, target, 'profile_correction', official_position_title='范围内更正')
    plan = preview(client, row)
    login(client, 'admin')
    assert client.put(url, json={**payload, 'expected_revision': 1, 'status': 'revoked'}).status_code == 200
    login(client, 'delegation-manager')
    assert commit(client, row, plan).status_code in (403, 409)
    login(client, 'admin')
    assert identity(client, target)['position'] != '范围内更正'


def test_transfer_preserves_independent_denies_supplier_and_retained_sources(client):
    user_id = engineer(client)
    dbm, authm, _, auth, _ = modules()
    with dbm.SessionLocal() as db:
        for code, effect in [('molding_sample:create', 'deny'), ('carton_supplier:read', 'allow')]:
            permission = db.scalar(select(authm.AuthPermission).where(authm.AuthPermission.code == code))
            assert permission
            db.add(authm.AuthUserPermissionOverride(id=uuid4().hex, user_id=user_id, permission_id=permission.id,
                effect=effect, factory_id='*', department='*', status='active', source_type='individual_exception', employment_epoch=1))
        db.commit()
    same = add_assignment(client, user_id, factory='huakang-a', department='engineering', role='engineer')
    assert commit(client, same).status_code == 200
    current = identity(client, user_id)
    row = draft(client, user_id, 'primary_assignment_transfer', source_assignment_id=current['primary_assignment']['id'],
        new_assignment={'org_unit_id':'huaxing','department_code':'pmc-warehouse','official_position_title':'仓管'},
        exception_decisions=[{'override_id':o['id'],'decision':'keep_original_scope'} for o in current['overrides']])
    plan = preview(client, row)
    assert plan['permission_diffs']['source_changed']
    assert not any(t['permission_code']=='carton_supplier:read' for t in plan['permission_diffs']['removed'])
    assert commit(client, row, plan).status_code == 200
    with dbm.SessionLocal() as db:
        context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
        assert not auth.can(context, 'molding_sample:create', 'huakang-a', 'engineering')
        assert auth.can(context, 'carton_supplier:read', '*', '*')


def test_old_future_assignment_never_revives_after_leave_and_rehire(client, monkeypatch):
    user_id = engineer(client)
    dbm, authm, _, auth, clock = modules()
    monkeypatch.setattr(importlib.import_module('app.core.config').settings, 'iam_identity_scheduling_enabled', True)
    boundary = clock.utc_now() + timedelta(days=1)
    row = add_assignment(client, user_id)
    data = {**row['payload'], 'effective_at':clock.stamp(boundary)}
    response = client.patch(f"/api/iam/identity-changes/{row['id']}", json={'expected_request_revision':row['revision'],'change':data})
    assert response.status_code == 200, response.text
    assert commit(client, response.json()).status_code == 200
    assert commit(client, draft(client, user_id, 'leave')).status_code == 200
    assert commit(client, draft(client, user_id, 'rehire', new_assignment={'org_unit_id':'huaxing','department_code':'engineering','official_position_title':'重新入职'})).status_code == 200
    with dbm.SessionLocal() as db:
        context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id), at=boundary + timedelta(days=1))
        assert not auth.can(context, 'internal_quote:sales_review', 'huakang-b', 'sales-business', at=boundary + timedelta(days=1))
        assert context.profile.primary_factory_id == 'huaxing'


def test_preview_cannot_be_borrowed_expired_or_used_after_role_edit(client):
    user_id = engineer(client)
    row = draft(client, user_id, 'profile_correction', official_position_title='有效预览才可更正')
    plan = preview(client, row)
    create_user('other-preview-admin', 'admin', '*', '*')
    login(client, 'other-preview-admin')
    assert commit(client, row, plan).status_code == 404
    login(client, 'admin')
    dbm, authm, _, _, _ = modules()
    with dbm.SessionLocal() as db:
        token = db.scalar(select(authm.AuthAuthorizationPreview).where(authm.AuthAuthorizationPreview.target_id == row['id']))
        token.expires_at = '2000-01-01 00:00:00'
        db.commit()
    assert commit(client, row, plan).status_code == 410
    package = add_assignment(client, user_id, department='engineering', role='engineer')
    package_plan = preview(client, package)
    with dbm.SessionLocal() as db:
        db.get(authm.AuthRole, 'engineer').name = '模板发布新版本'
        db.commit()
    assert commit(client, package, package_plan).status_code == 409
    assert identity(client, user_id)['position'] != '有效预览才可更正'


def test_all_current_is_frozen_and_future_admin_gap_is_rejected(client):
    user_id = engineer(client)
    row = add_assignment(client, user_id, department='pmc-warehouse', role='position_warehouse_manager',
        role_bindings=[{'role_id':'position_warehouse_manager','department':'pmc-warehouse','factory_scope':{'kind':'all_current'}}])
    assert commit(client, row).status_code == 200
    dbm, authm, identitym, auth, clock = modules()
    with dbm.SessionLocal() as db:
        db.add(identitym.IamOrgUnit(id='future-test-factory', name='隔离新增组织', kind='factory', legacy_factory_id='future-test-factory'))
        db.flush()
        context = auth.build_auth_context(db, db.get(authm.AuthUser, user_id))
        assert auth.can(context, 'carton_procurement:read', 'huakang-d', 'pmc-warehouse')
        assert not auth.can(context, 'carton_procurement:read', 'future-test-factory', 'pmc-warehouse')
        admin_binding = db.scalar(select(authm.AuthUserRole).where(authm.AuthUserRole.user_id == 'user-admin'))
        db.get(authm.AuthRoleBindingMetadata, admin_binding.id).valid_until = clock.stamp(clock.utc_now() + timedelta(days=1))
        db.flush()
        policy = importlib.import_module('app.services.identity_policy')
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as failure:
            policy.ensure_admin_survives(db)
        assert failure.value.detail['code'] == 'LAST_ADMINISTRATOR'
        db.rollback()
