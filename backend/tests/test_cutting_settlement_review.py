from datetime import date
from uuid import uuid4
import pytest
from test_cutting_ops import client, command, user, BASE
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees, basis, price, save, save_body, decision, accountant, record, ACTIONS, URL
from app.services import cutting_ops as c, cutting_settlement_schemas as schemas, cutting_planning as planning


def test_legacy_recovery_fingerprint_is_unchanged():
    body=command(document_id=uuid4().hex,month='2026-10',basis_token='basis',selections=[dict(line_id='line',acceptance_id='accept',sets=1)],vendor_evidence='evidence')
    assert c.command_fingerprint(schemas.Save.model_validate(body),'settlement-save')==c.payload_fingerprint(body,'settlement-save')


@pytest.mark.parametrize('change',[{'sets':6},{'price':'4'},{'currency':'USD'},{'evidence':'new evidence'}])
def test_changed_basis_rejects_previous_vendor_confirmation(fees,change):
    p=fees;price(p,value='2');original=save_body(p,sets=5)
    if 'price' in change or 'currency' in change:price(p,value=change.get('price','2'),currency=change.get('currency','CNY'))
    body=save_body(p,sets=change.get('sets',5),document_id=original['document_id'],vendor_evidence=change.get('evidence',original['vendor_evidence']),vendor_confirmation_token=original['vendor_confirmation_token'])
    response=p.post(URL+'/save',json=body)
    assert response.status_code==409 and '重新预览' in response.text
    body['vendor_confirmation_token']=''
    ok(p.post(URL+'/save',json=body))
    assert decision(p,body['document_id'],'submit').status_code==409
    body['vendor_confirmation_token']=ok(p.post(BASE+'/settlement-preview',json=body))['confirmation_token']
    body['expected_version']=record(p)['revision'];body['operation_id']=uuid4().hex
    ok(p.post(URL+'/save',json=body));ok(decision(p,body['document_id'],'submit'))
    accountant(p);ok(decision(p,body['document_id'],'confirm'))
    assert record(p,body['document_id'])['data']['vendor_confirmation']['actor_id']=='test-user'


def test_revision_review_and_separate_totals(fees):
    p=fees;price(p,value='2');did=save(p,sets=5)
    price(p,value='4');save(p,sets=6,document_id=did)
    value=record(p,did)
    assert value['previous_snapshot']['total']=='10.00'
    assert value['data']['snapshot']['total']=='24.00'
    ok(decision(p,did,'submit'))
    other=save(p,sets=1);ok(decision(p,other,'submit'));accountant(p);ok(decision(p,did,'confirm'))
    totals={t['state']:t for t in record(p)['totals']}
    assert totals['confirmed']['total']=='24.00' and totals['submitted']['total']=='4.00'


def test_cross_month_dependencies_reverse_reopen_and_reclose(fees,monkeypatch):
    p=fees;price(p);one=save(p);ok(decision(p,one,'submit'));accountant(p);ok(decision(p,one,'confirm'))
    old_id=record(p,one)['event_id']
    monkeypatch.setattr(planning,'business_today',lambda:date(2026,11,16))
    p.cutting_auth['user']=user(*ACTIONS)
    b=ok(p.get(URL+'/2026-11/basis',params={'factory_id':'huakang-c'}))
    body=command(expected_version=b['revision'],document_id=uuid4().hex,month='2026-11',basis_token=b['basis_token'],selections=[dict(line_id='line-1',acceptance_id=p.acceptance,sets=1)],vendor_evidence='November confirmation')
    body['vendor_confirmation_token']=ok(p.post(BASE+'/settlement-preview',json=body))['confirmation_token']
    ok(p.post(URL+'/save',json=body));two=body['document_id'];ok(decision(p,two,'submit'));accountant(p);ok(decision(p,two,'confirm'))
    dependencies=record(p,one)['dependencies']
    assert dependencies[0]['document_id']==two and dependencies[0]['month']=='2026-11'
    response=decision(p,one,'reopen');assert response.status_code==409 and two in response.text
    ok(decision(p,two,'reopen'));ok(decision(p,one,'reopen'))
    assert record(p,one,event_id=old_id)['data']['snapshot']['total']=='0.33'
    assert record(p)['totals']==[]
    p.cutting_auth['user']=user(*ACTIONS)
    save(p,document_id=one);ok(decision(p,one,'submit'));accountant(p);ok(decision(p,one,'confirm'))
    assert record(p,one)['data']['snapshot']['total']=='0.33'


def test_real_cookie_two_person_fee_flow(fees,monkeypatch):
    from sqlalchemy.orm import Session
    from app.api import auth as auth_api
    from app.models.auth import AuthUser, AuthRole, AuthPermission, AuthRolePermission, AuthUserRole, EmployeeProfile, AuthIamState
    from app.services.auth import get_current_user, hash_password
    from test_cutting_session_auth import login
    p=fees
    AuthUser.metadata.create_all(p.engine, tables=[t for t in AuthUser.metadata.tables.values() if not t.name.startswith('cutting_ops_')])
    p.app.include_router(auth_api.router)
    p.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(auth_api.settings,'session_cookie_secure',False)
    with Session(p.engine) as db:
        db.add(AuthIamState(key='identity_mutation_lock',value_json='{}'))
        for action in ACTIONS:db.add(AuthPermission(id='cutting_ops:'+action,code='cutting_ops:'+action,name=action))
        for name in ('production','accounting'):
            db.add(AuthUser(id=name,username='cutting-test-'+name,display_name=name,password_salt='synthetic-salt',password_hash=hash_password('SyntheticPassword123!','synthetic-salt'),status='active'))
            db.add(AuthRole(id=name,code='cutting-test-'+name,name=name))
        db.flush()
        for name in ('production','accounting'):
            db.add(EmployeeProfile(user_id=name,primary_factory_id='huakang-c',primary_department=name,confirmation_status='confirmed'))
            db.add(AuthUserRole(id=name,user_id=name,role_id=name,factory_id='huakang-c',department=name))
            for action in ACTIONS:db.add(AuthRolePermission(id=name+':'+action,role_id=name,permission_id='cutting_ops:'+action))
        db.commit()
    login(p,'production');price(p,value='2');did=save(p,sets=5);ok(decision(p,did,'submit'))
    assert decision(p,did,'confirm').status_code==403
    login(p,'accounting');ok(decision(p,did,'confirm'))
    value=record(p,did)
    assert value['state']=='confirmed' and value['data']['snapshot']['total']=='10.00'
    assert value['data']['prepared_by']=='production' and value['history'][-1]['actor_id']=='accounting'
    assert value['data']['local_admin_acceptance'] is False
    ok(decision(p,did,'reopen'))
    login(p,'production');save(p,sets=4,document_id=did);ok(decision(p,did,'submit'))
    login(p,'accounting');ok(decision(p,did,'confirm'))
    assert record(p,did)['data']['snapshot']['total']=='8.00'
