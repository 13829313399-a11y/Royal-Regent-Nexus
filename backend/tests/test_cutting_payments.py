"""Actual-payment registration tests; isolated databases, no bank instructions."""
from dataclasses import replace
from datetime import date
from pathlib import Path
from uuid import uuid4
import runpy
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text
from test_cutting_ops import client, user, command, BASE
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees, price, save as fee_save, decision as fee_decision, accountant as fee_accountant

URL=BASE+'/payments'
ACTIONS=('read','payment_read','payment_prepare','payment_confirm','payment_reverse','settlement_read','settlement_reopen')

@pytest.fixture
def paid_setup(fees):
    p=fees;price(p,value='2')
    p.one=fee_save(p,sets=10);ok(fee_decision(p,p.one,'submit'))
    p.two=fee_save(p,sets=10);ok(fee_decision(p,p.two,'submit'))
    fee_accountant(p);ok(fee_decision(p,p.one,'confirm'));ok(fee_decision(p,p.two,'confirm'))
    migration=runpy.run_path(str(Path(__file__).parents[1]/'alembic/versions/20261016_0166_cutting_subcontract_payments.py'))
    with p.engine.begin() as db:
        with Operations.context(MigrationContext.configure(db)):migration['upgrade']()
    p.cutting_auth['user']=user(*ACTIONS,department='accounting')
    return p


def read(p,did=None,month='2026-10',**kwargs):
    return ok(p.get(URL+'/'+month,params={'factory_id':'huakang-c',**({'document_id':did} if did else {}),**kwargs}))


def basis(p,did=None):
    return ok(p.get(BASE+'/payment-basis',params={'factory_id':'huakang-c',**({'document_id':did} if did else {})}))


def body(p,**kwargs):
    value=basis(p,kwargs.get('document_id'))
    return command(expected_version=value['revision'],base_event_id=value['document']['event_id'] if value.get('document') else None,document_id=uuid4().hex,day='2026-10-16',voucher_no='PAY-'+uuid4().hex,method='bank',evidence='Synthetic actual bank payment receipt',currency='CNY',amount='5.00',basis_token=value['basis_token'],allocations=[dict(settlement_id=p.one,amount='5.00')],replaces_document_id=None)|kwargs


def save(p,**kwargs):
    data=body(p,**kwargs);ok(p.post(URL+'/save',json=data));return data['document_id']


def decision(p,did,action):
    return p.post(URL+'/'+action,json=command(expected_version=read(p)['revision'],document_id=did))


def reviewer(p):
    p.cutting_auth['user']=replace(user(*ACTIONS,department='accounting'),id='payment-reviewer')


def test_partial_multi_statement_payment_and_independent_review(paid_setup):
    p=paid_setup
    did=save(p,amount='12.50',allocations=[dict(settlement_id=p.one,amount='5.00'),dict(settlement_id=p.two,amount='7.50')])
    assert read(p)['totals'][0]['paid']=='0.00'
    ok(decision(p,did,'submit'))
    total=read(p)['totals'][0];assert total['pending']=='12.50' and total['unpaid']=='40.00' and total['available']=='27.50'
    assert decision(p,did,'confirm').status_code==409
    reviewer(p);ok(decision(p,did,'confirm'))
    total=read(p)['totals'][0];assert total['paid']=='12.50' and total['pending']=='0.00' and total['unpaid']=='27.50'
    assert read(p,did)['data']['local_admin_acceptance'] is False
    assert fee_decision(p,p.one,'reopen').status_code==409
    assert p.get(BASE+'/payment-basis',params={'factory_id':'huakang-c','document_id':did}).status_code==409


@pytest.mark.parametrize('changes',[{'amount':'6.00'},{'amount':'0'},{'amount':'-1'},{'amount':'NaN'},{'amount':'5.001'},{'day':'2099-01-01'}])
def test_invalid_or_future_payment_is_rejected(paid_setup,changes):
    p=paid_setup;assert p.post(URL+'/save',json=body(p,**changes)).status_code==422
    assert read(p)['documents']==[]


def test_overpayment_currency_and_preview_do_not_write(paid_setup):
    p=paid_setup
    assert p.post(URL+'/save',json=body(p,amount='21',allocations=[dict(settlement_id=p.one,amount='21')])).status_code==409
    assert p.post(URL+'/save',json=body(p,currency='USD')).status_code==409
    preview=ok(p.post(BASE+'/payment-preview',json=body(p)))
    assert preview['amount']=='5.00' and read(p)['revision']==0


def test_voucher_duplicate_reverse_and_linked_reregistration(paid_setup):
    p=paid_setup;one=save(p,voucher_no='PAY-ABC');ok(decision(p,one,'submit'))
    assert p.post(URL+'/save',json=body(p,voucher_no='ｐａｙ-ａｂｃ')).status_code==409
    assert decision(p,one,'reverse').status_code==409
    reviewer(p);ok(decision(p,one,'confirm'));frozen=read(p,one)['event_id'];ok(decision(p,one,'reverse'))
    assert read(p)['totals'][0]['paid']=='0.00'
    assert p.post(URL+'/save',json=body(p,voucher_no='PAY-ABC')).status_code==409
    p.cutting_auth['user']=user(*ACTIONS,department='accounting')
    replacement=save(p,voucher_no='PAY-ABC',replaces_document_id=one)
    assert read(p,one)['replacements'][0]['document_id']==replacement
    assert read(p,one,event_id=frozen)['selected_state']=='confirmed'
    assert read(p,one,event_id=frozen)['state']=='reversed'
    ok(decision(p,replacement,'submit'));reviewer(p);ok(decision(p,replacement,'confirm'))
    assert read(p)['totals'][0]['paid']=='5.00'
    assert decision(p,one,'submit').status_code==409


def test_pending_payment_fences_settlement_and_return_revalidates_source(paid_setup):
    p=paid_setup;did=save(p);ok(decision(p,did,'submit'))
    blocked=fee_decision(p,p.one,'reopen');assert blocked.status_code==409 and did in blocked.text
    reviewer(p);ok(decision(p,did,'return'))
    # The later same-acceptance settlement must reopen before the first.
    ok(fee_decision(p,p.two,'reopen'));ok(fee_decision(p,p.one,'reopen'))
    assert decision(p,did,'submit').status_code==409
    assert read(p)['totals']==[]


def test_receipts_are_actor_bound_and_unknown_requests_are_fenced(paid_setup):
    p=paid_setup;data=body(p);ok(p.post(URL+'/save',json=data));ok(p.post(URL+'/save',json=data))
    assert read(p)['revision']==1
    reviewer(p);assert p.post(URL+'/save',json=data).status_code==409
    another=body(p)
    p.cutting_auth['user']=user('read',department='accounting')
    assert ok(p.post(BASE+'/payment-operations/recover',json={'action':'save','command':another}))=={'state':'abandoned'}
    p.cutting_auth['user']=user(*ACTIONS,department='accounting')
    assert p.post(URL+'/save',json=another).status_code==409


@pytest.mark.parametrize('department,permissions,status',[('production',('read','payment_read'),403),('pmc-warehouse',('read','payment_read'),403),('accounting',('read','settlement_read','cost_read'),403),('accounting',('read','payment_read'),200)])
def test_payment_read_is_separate_accounting_permission(paid_setup,department,permissions,status):
    p=paid_setup;p.cutting_auth['user']=user(*permissions,department=department)
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==status
    assert p.get(BASE+'/payment-basis',params={'factory_id':'huakang-c'}).status_code==status


def test_immutable_schema_and_scope(paid_setup):
    p=paid_setup
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-d'}).status_code==422
    did=save(p)
    with p.engine.begin() as db:
        with pytest.raises(Exception):db.execute(text('DELETE FROM cutting_ops_payment_events'))
        db.execute(text('DROP TRIGGER cutting_payment_no_delete'))
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==503
    assert fee_decision(p,p.two,'reopen').status_code==503


def test_refresh_cannot_replace_newer_draft_without_document_base(paid_setup):
    p=paid_setup;did=save(p,evidence='A original')
    first=read(p,did);old=body(p,document_id=did,evidence='A retained')
    reviewer(p);ok(p.post(URL+'/save',json=body(p,document_id=did,evidence='B latest',amount='7',allocations=[dict(settlement_id=p.one,amount='7')])))
    p.cutting_auth['user']=user(*ACTIONS,department='accounting')
    assert p.post(URL+'/save',json=old).status_code==409
    value=basis(p,did)
    old.update(expected_version=value['revision'],basis_token=value['basis_token'],operation_id=uuid4().hex)
    assert p.post(URL+'/save',json=old).status_code==409
    assert read(p,did)['data']['snapshot']['evidence']=='B latest'
    old['base_event_id']=value['document']['event_id']
    ok(p.post(URL+'/save',json=old))
    assert read(p,did)['previous_compilation']['snapshot']['amount']=='7.00'
    assert read(p,did,event_id=first['event_id'])['previous_compilation'] is None


def test_unrelated_draft_refresh_preserves_document_base(paid_setup):
    p=paid_setup;did=save(p);mine=body(p,document_id=did,evidence='mine')
    save(p);value=basis(p,did)
    assert value['document']['event_id']==mine['base_event_id']
    mine.update(expected_version=value['revision'],basis_token=value['basis_token'])
    ok(p.post(URL+'/save',json=mine))


def test_cross_month_corrections_preserve_history_and_replacement(paid_setup):
    p=paid_setup;did=save(p,day='2026-10-01');old=read(p,did)['event_id']
    ok(p.post(URL+'/save',json=body(p,document_id=did,day='2026-09-30')))
    current=read(p,did)
    assert current['month']=='2026-09' and current['current_month']=='2026-09'
    assert not read(p)['documents']
    history=read(p,did,event_id=old)
    assert history['month']=='2026-10' and history['current_month']=='2026-09'
    assert history['history'][0]['month']=='2026-10'
    ok(decision(p,did,'submit'));reviewer(p);ok(decision(p,did,'return'))
    ok(p.post(URL+'/save',json=body(p,document_id=did,day='2026-10-02')))
    ok(decision(p,did,'submit'));p.cutting_auth['user']=user(*ACTIONS,department='accounting');ok(decision(p,did,'confirm'))
    assert p.post(URL+'/save',json=body(p,day='2026-09-30')|{'document_id':did}).status_code==409
    ok(decision(p,did,'reverse'));replacement=save(p,replaces_document_id=did)
    ok(p.post(URL+'/save',json=body(p,document_id=replacement,replaces_document_id=did,day='2026-09-30')))
    assert read(p,did)['replacements'][0]['day']=='2026-09-30'
    assert read(p,replacement)['original']['document_id']==did


def test_comparison_follows_selected_compilation(paid_setup):
    p=paid_setup;did=save(p);first=read(p,did)['event_id']
    second=ok(p.post(URL+'/save',json=body(p,document_id=did,amount='8',allocations=[dict(settlement_id=p.two,amount='8')],evidence='replacement')))
    ok(decision(p,did,'submit'));reviewer(p);ok(decision(p,did,'confirm'))
    r=read(p,did);assert r['previous_compilation']['event_id']==first
    assert r['previous_compilation']['snapshot']['allocations'][0]['settlement_id']==p.one
    assert r['data']['snapshot']['allocations'][0]['settlement_id']==p.two
    assert read(p,did,event_id=second['id'])['previous_compilation']['event_id']==first


def test_blocker_details_require_payment_read_and_follow_state(paid_setup):
    p=paid_setup;did=save(p,day='2026-09-30');ok(decision(p,did,'submit'))
    def fees_read():return ok(p.get(BASE+'/settlements/2026-10',params={'factory_id':'huakang-c','document_id':p.one}))
    blocker=fees_read()['payment_dependencies'][0]
    assert blocker==dict(document_id=did,month='2026-09',state='submitted',amount='5.00',currency='CNY',voucher_no=read(p,did)['data']['snapshot']['voucher_no'])
    p.cutting_auth['user']=user('read','settlement_read',department='accounting')
    assert 'payment_dependencies' not in fees_read()
    reviewer(p);ok(decision(p,did,'confirm'));assert fees_read()['payment_dependencies'][0]['state']=='confirmed'
    ok(decision(p,did,'reverse'));assert fees_read()['payment_dependencies']==[]


def test_legacy_receipt_fingerprint_and_cross_month_recovery(paid_setup):
    from app.services import cutting_ops as c, cutting_payment_schemas as pay
    p=paid_setup;old=body(p,day='2026-09-30');old.pop('base_event_id')
    assert c.command_fingerprint(pay.Save.model_validate(old),'payment-save')==c.payload_fingerprint(pay.Save.model_validate(old).model_dump(mode='json',exclude={'base_event_id'}),'payment-save')
    result=ok(p.post(URL+'/save',json=old))
    recovered=ok(p.post(BASE+'/payment-operations/recover',json={'action':'save','command':old}))
    assert recovered['result']==result and result['month']=='2026-09'
    assert read(p,result['document_id'],event_id=result['id'])['month']=='2026-09'
