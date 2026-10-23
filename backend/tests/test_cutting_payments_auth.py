"""Actual cookie sessions and independent accounting payment approval."""
from sqlalchemy import delete
from sqlalchemy.orm import Session
from app.api import auth as auth_api
from app.models.auth import AuthUser, AuthRole, AuthPermission, AuthRolePermission, AuthUserRole, AuthUserPermissionOverride, EmployeeProfile, AuthIamState
from app.services.auth import get_current_user, hash_password
from app.services import cutting_exports
from test_cutting_ops import client, command, BASE
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees
from test_cutting_payments import paid_setup, save, read, decision, body, ACTIONS, URL


def test_real_accounting_sessions_enforce_independence_and_revocation(paid_setup,monkeypatch):
    p=paid_setup;AuthUser.metadata.create_all(p.engine, tables=[t for t in AuthUser.metadata.tables.values() if not t.name.startswith('cutting_ops_')])
    p.app.include_router(auth_api.router);p.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(auth_api.settings,'session_cookie_secure',False)
    with Session(p.engine) as db:
        db.add(AuthIamState(key='identity_mutation_lock',value_json='{}'))
        for a in ACTIONS:db.add(AuthPermission(id='cutting_ops:'+a,code='cutting_ops:'+a,name=a))
        for name in ('registrar','reviewer','production'):
            db.add(AuthUser(id=name,username='payment-test-'+name,display_name=name,password_salt='salt',password_hash=hash_password('SyntheticPass123!','salt'),status='active'))
            db.add(AuthRole(id=name,code='payment-test-'+name,name=name))
        db.flush()
        for name in ('registrar','reviewer','production'):
            dept='production' if name=='production' else 'accounting'
            db.add(EmployeeProfile(user_id=name,primary_factory_id='huakang-c',primary_department=dept,confirmation_status='confirmed'))
            db.add(AuthUserRole(id=name,user_id=name,role_id=name,factory_id='huakang-c',department=dept))
            for a in ACTIONS:db.add(AuthRolePermission(id=name+':'+a,role_id=name,permission_id='cutting_ops:'+a))
        db.commit()
    def login(name):
        p.cookies.clear();ok(p.post('/api/auth/login',json={'username':'payment-test-'+name,'password':'SyntheticPass123!'}))
    login('production');assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==403
    login('registrar');saved=body(p);ok(p.post(URL+'/save',json=saved));did=saved['document_id'];ok(decision(p,did,'submit'))
    assert decision(p,did,'confirm').status_code==409
    with Session(p.engine) as db:
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id=='registrar:payment_prepare'));db.commit()
    assert p.post(URL+'/save',json=saved).status_code==403  # Even an exact committed receipt needs current authority.
    login('reviewer');ok(decision(p,did,'confirm'))
    assert read(p,did)['data']['prepared_by']=='registrar'
    assert read(p,did)['history'][-1]['actor']=='reviewer'
    export_body=dict(factory_id='huakang-c',kind='payments',month='2026-10')
    export_preview=ok(p.post(BASE+'/exports/preview',json=export_body))
    exported=p.post(BASE+'/exports/download',json=export_body|{'token':export_preview['token']})
    assert exported.status_code==200 and exported.content.startswith(b'PK')
    with Session(p.engine) as db:
        db.add(AuthUserPermissionOverride(id='deny-reverse',user_id='reviewer',permission_id='cutting_ops:payment_reverse',effect='deny',factory_id='huakang-c',department='accounting'));db.commit()
    assert decision(p,did,'reverse').status_code==403
    with Session(p.engine) as db:
        db.execute(delete(AuthUserPermissionOverride).where(AuthUserPermissionOverride.id=='deny-reverse'));db.commit()
    ok(decision(p,did,'reverse'))
    export_preview=ok(p.post(BASE+'/exports/preview',json=export_body))
    render=cutting_exports.package_isolated
    def revoke_during_render(report,context):
        content=render(report,context)
        with Session(p.engine) as db:
            db.execute(delete(AuthRolePermission).where(AuthRolePermission.id=='reviewer:payment_read'));db.commit()
        return content
    monkeypatch.setattr(cutting_exports,'package_isolated',revoke_during_render)
    assert p.post(BASE+'/exports/download',json=export_body|{'token':export_preview['token']}).status_code==403
    with Session(p.engine) as db:
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id=='reviewer:payment_read'));db.commit()
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==403
    assert p.get(BASE+'/payment-basis',params={'factory_id':'huakang-c'}).status_code==403
