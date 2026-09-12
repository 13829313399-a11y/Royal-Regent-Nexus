import json
from sqlalchemy import delete, select
from test_molding_sample_api import make_client, login_as

BASE = '/api/carton-procurement'


def test_warehouse_roles_maintain_own_factory_without_individual_grants(monkeypatch):
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    with make_client(monkeypatch) as client:
        profile = login_as(client, 'warehouse_keeper')
        from app.db import SessionLocal
        from app.models.auth import AuthUser, AuthUserRole
        from app.services.auth import build_auth_context, has_permission_in_scope
        from app.services.carton_master import can_manage
        roles = [('warehouse_keeper', 'pmc-warehouse'), ('carton_warehouse_keeper', 'carton'),
                 ('position_warehouse_keeper', 'pmc-warehouse'), ('position_warehouse_supervisor', 'pmc-warehouse'),
                 ('position_warehouse_manager', 'pmc-warehouse'), ('position_carton_warehouse_keeper', 'carton'),
                 ('position_carton_supervisor', 'carton')]
        for index, (role, department) in enumerate(roles):
            with SessionLocal() as db:
                db.execute(delete(AuthUserRole).where(AuthUserRole.user_id == profile['id']))
                db.add(AuthUserRole(id=f'test-master-{index}', user_id=profile['id'], role_id=role,
                                   factory_id='huaxing', department=department))
                db.commit()
                context = build_auth_context(db, db.get(AuthUser, profile['id']))
                assert can_manage(context, 'huaxing'), role
                assert not can_manage(context, 'huadeng'), role
                assert not has_permission_in_scope(context, 'system:access_manage', 'huaxing', department)
            workspace = client.get(BASE+'/master-data', params={'factory_id':'huaxing'})
            assert workspace.status_code == 200 and workspace.json()['can_manage'], (role, workspace.text)
            result = client.post(BASE+'/master-data', json={'factory_id':'huaxing','kind':'WORKSHOP',
                'code':f'TEST-ROLE-{index}','data':{},'reason':'测试岗位资料维护'})
            assert result.status_code == 201, (role,result.text)
            assert client.post(BASE+'/master-data',json={'factory_id':'huadeng','kind':'WORKSHOP',
                'code':'FOREIGN','data':{},'reason':'验证厂区边界'}).status_code == 403
            assert client.post(BASE+'/master-data',json={'factory_id':'huaxing','kind':'ACCESS',
                'code':profile['id'],'data':{'warehouses':['A']},'reason':'旧授权入口已撤回'}).status_code == 422
        # A retained legacy grant must not bypass an explicit master-data deny.
        from app.models.auth import AuthPermission, AuthUserPermissionOverride
        from app.models.carton_master import CartonMasterRecord
        with SessionLocal() as db:
            permission = db.scalar(select(AuthPermission).where(AuthPermission.code == 'carton_procurement:master_manage'))
            db.add(AuthUserPermissionOverride(id='test-master-deny', user_id=profile['id'],
                permission_id=permission.id, effect='deny', factory_id='huaxing', department='*'))
            db.add(CartonMasterRecord(id='test-legacy-grant', factory_id='huaxing', kind='ACCESS',
                identity='test-legacy-grant', code=profile['id'], data_json=json.dumps({'warehouses':['A']})))
            db.commit()
        denied = client.get(BASE+'/master-data', params={'factory_id':'huaxing'}).json()
        assert not denied['can_manage'] and denied['warehouses'] == []
        assert client.post(BASE+'/inventory/locations', json={'factory_id':'huaxing', 'warehouse':'A',
            'bin_code':'DENIED','reason':'旧授权不能绕过禁用'}).status_code == 403
        login_as(client, 'engineer')
        assert client.post(BASE+'/master-data',json={'factory_id':'huaxing','kind':'WORKSHOP',
            'code':'NO-ACCESS','data':{},'reason':'非仓务角色测试'}).status_code == 403


def test_legacy_role_upgrade_is_once_only_and_preserves_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        from app.db import SessionLocal
        from app.models.auth import AuthRolePermission, AuthPermission, AuthUserRole
        from app.services.auth import AuthIamState, seed_carton_master_default_grants_once
        with SessionLocal() as db:
            permission=db.scalar(select(AuthPermission).where(AuthPermission.code=='carton_procurement:master_manage'))
            roles=['warehouse_keeper','carton_warehouse_keeper']
            db.execute(delete(AuthRolePermission).where(AuthRolePermission.role_id.in_(roles),AuthRolePermission.permission_id==permission.id))
            db.delete(db.get(AuthIamState,'carton_master_operator_grants_v1'))
            before=[(r.id,r.factory_id,r.department) for r in db.scalars(select(AuthUserRole).order_by(AuthUserRole.id))]
            db.flush()
            assert seed_carton_master_default_grants_once(db,'2026-09-12T10:00:00') == 2
            db.flush()
            assert seed_carton_master_default_grants_once(db,'2026-09-12T10:00:01') == 0
            assert before == [(r.id,r.factory_id,r.department) for r in db.scalars(select(AuthUserRole).order_by(AuthUserRole.id))]
