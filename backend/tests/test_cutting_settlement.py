"""Settlement workflow on isolated migrated SQLite and real production evidence."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
from test_cutting_reporting import production, send, ok, doc

URL = BASE+'/settlements'
ACTIONS = ('read', 'settlement_read', 'settlement_price', 'settlement_prepare', 'settlement_confirm', 'settlement_reopen',
           'report_write', 'acceptance_write', 'report_review')


@pytest.fixture
def fees(production):
    p = production
    migration = runpy.run_path(str(Path(__file__).parents[1]/'alembic/versions/20261016_0165_cutting_subcontract_settlement.py'))
    with p.engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration['upgrade']()
    p.cutting_auth['user'] = user(*ACTIONS)
    ok(send(p, task_id='external', sets=30))
    ok(send(p, task_id='external', kind='return', sets=30))
    p.acceptance = doc(ok(send(p, task_id='external', kind='accept', sets=20)))
    return p


def basis(p, document_id=None):
    return ok(p.get(URL+'/2026-10/basis', params={'factory_id':'huakang-c', 'document_id':document_id} if document_id else {'factory_id':'huakang-c'}))


def record(p, document_id=None, **params):
    return ok(p.get(URL+'/2026-10', params={'factory_id':'huakang-c', **({'document_id':document_id} if document_id else {}), **params}))


def price(p, value='0.333333', currency='CNY'):
    b = basis(p); row = b['rows'][0]
    return ok(p.post(URL+'/price', json=command(expected_version=b['revision'], line_id='line-1', task_id='external',
        context_token=row['context_token'], unit_price=value, currency=currency, evidence='外厂盖章含税报价单')))


def save_body(p, sets=1, document_id=None, **changes):
    b = basis(p, document_id)
    body = command(expected_version=b['revision'], document_id=document_id or uuid4().hex, month='2026-10',
        basis_token=b['basis_token'], selections=[dict(line_id='line-1', acceptance_id=p.acceptance, sets=sets)], vendor_evidence='外厂已核对数量、单价及金额凭据') | changes
    if 'vendor_confirmation_token' not in changes:
        preview = p.post(BASE+'/settlement-preview', json=body)
        if preview.status_code == 200:
            body['vendor_confirmation_token'] = preview.json()['confirmation_token']
    return body


def save(p, **kwargs):
    body = save_body(p, **kwargs)
    ok(p.post(URL+'/save', json=body))
    return body['document_id']


def decision(p, document_id, action, **changes):
    return p.post(URL+'/'+action, json=command(expected_version=record(p)['revision'], document_id=document_id, **changes))


def accountant(p):
    p.cutting_auth['user'] = replace(user(*ACTIONS, department='accounting'), id='independent-accountant')


def test_partial_settlement_rounding_history_reopen_and_acceptance_fence(fees):
    p=fees; price(p)
    one=save(p); ok(decision(p,one,'submit'))
    two=save(p); ok(decision(p,two,'submit'))
    accountant(p)
    ok(decision(p,one,'confirm')); ok(decision(p,two,'confirm'))
    p.cutting_auth['user']=user(*ACTIONS)
    three=save(p); ok(decision(p,three,'submit')); accountant(p); ok(decision(p,three,'confirm'))
    assert [record(p,d)['data']['snapshot']['total'] for d in (one,two,three)] == ['0.33','0.34','0.33']
    assert decision(p,one,'reopen').status_code==409
    frozen=record(p,three)['event_id']
    p.cutting_auth['user']=user(*ACTIONS)
    assert send(p,'void',document_id=p.acceptance).status_code==409
    accountant(p); ok(decision(p,three,'reopen')); ok(decision(p,two,'reopen')); ok(decision(p,one,'reopen'))
    assert record(p,three,event_id=frozen)['selected_state']=='confirmed'
    assert basis(p)['rows'][0]['available_sets']==20
    p.cutting_auth['user']=user(*ACTIONS)
    ok(send(p,'void',document_id=p.acceptance))


def test_submit_reservation_return_dependencies_and_double_booking(fees):
    p=fees;price(p)
    one=save(p,sets=12); two=save(p,sets=12)
    ok(decision(p,one,'submit'))
    assert decision(p,two,'submit').status_code==409
    p.cutting_auth['user']=user(*ACTIONS)
    two=save(p,sets=8,document_id=two);ok(decision(p,two,'submit'))
    accountant(p)
    assert decision(p,one,'return').status_code==409
    ok(decision(p,two,'return'));ok(decision(p,one,'return'))
    assert basis(p)['rows'][0]['available_sets']==20


def test_requires_quote_vendor_evidence_and_independent_review(fees):
    p=fees
    assert p.post(URL+'/save',json=save_body(p)).status_code==409
    price(p,value='0')
    did=save(p,vendor_evidence='')
    assert decision(p,did,'submit').status_code==409
    save(p,document_id=did);ok(decision(p,did,'submit'))
    assert decision(p,did,'confirm').status_code==409
    accountant(p);ok(decision(p,did,'confirm'))
    assert record(p,did)['data']['snapshot']['total']=='0.00'


def test_price_changes_preserve_frozen_snapshot_and_stale_draft_requires_refresh(fees):
    p=fees;price(p,value='2')
    one=save(p,sets=3);ok(decision(p,one,'submit'));accountant(p);ok(decision(p,one,'confirm'))
    p.cutting_auth['user']=user(*ACTIONS)
    two=save(p,sets=2);price(p,value='4',currency='HKD')
    assert decision(p,two,'submit').status_code==409
    assert record(p,one)['data']['snapshot']['total']=='6.00'
    save(p,sets=2,document_id=two)
    assert record(p,two)['data']['snapshot']['currency']=='HKD'
    assert len(record(p,one)['price_history'])==2


def test_overproduction_cap_across_acceptances_and_draft_corrections(fees):
    p=fees;price(p)
    second=doc(ok(send(p,task_id='external',kind='accept',sets=10)))
    body=save_body(p,sets=20)
    body['selections'].append(dict(line_id='line-1',acceptance_id=second,sets=6))
    assert p.post(URL+'/save',json=body).status_code==409
    body['selections'][-1]['sets']=5
    body['vendor_confirmation_token']=ok(p.post(BASE+'/settlement-preview',json=body))['confirmation_token']
    ok(p.post(URL+'/save',json=body));ok(decision(p,body['document_id'],'submit'))
    assert all(r['available_sets']==0 for r in basis(p)['rows'])
    assert send(p,'save',document_id=p.acceptance,task_id='external',kind='accept',sets=19).status_code==409


def test_pending_correction_not_payable_and_internal_claims_not_eligible(fees):
    p=fees;price(p)
    assert len(basis(p)['rows'])==1
    ok(send(p,'save',document_id=p.acceptance,task_id='external',kind='accept',sets=19))
    assert p.post(URL+'/save',json=save_body(p)).status_code==409
    ok(send(p,'discard',document_id=p.acceptance))
    assert p.get(URL+'/2026-09/basis',params={'factory_id':'huakang-c'}).json()['rows']==[]
    assert p.get(URL+'/2099-01/basis',params={'factory_id':'huakang-c'}).status_code==422


def test_concurrent_submit_only_one_wins_and_retries_are_actor_bound(fees):
    p=fees;price(p);one=save(p,sets=15);two=save(p,sets=15)
    rev=record(p)['revision']
    bodies=[command(expected_version=rev,document_id=did) for did in (one,two)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses=list(pool.map(lambda body:p.post(URL+'/submit',json=body),bodies))
    assert sorted(r.status_code for r in responses)==[200,409]
    winner=next(body for body,response in zip(bodies,responses) if response.status_code==200)
    assert p.post(URL+'/submit',json=winner).status_code==200
    p.cutting_auth['user']=replace(user(*ACTIONS),id='different')
    assert p.post(URL+'/submit',json=winner).status_code==409


def test_recovery_without_fee_permission_returns_only_receipt_and_fences(fees):
    p=fees;price(p);body=save_body(p)
    p.cutting_auth['user']=user('read')
    response=p.post(BASE+'/settlement-operations/recover',json={'action':'save','command':body})
    assert response.status_code==200 and response.json()=={'state':'abandoned'}
    p.cutting_auth['user']=user(*ACTIONS)
    assert p.post(URL+'/save',json=body).status_code==409


@pytest.mark.parametrize('dept,actions,status', [('production',('read','settlement_read'),200),
    ('accounting',('read','settlement_read'),200),('pmc-warehouse',('read','settlement_read'),403),
    ('production',('read','cost_read'),403),('production',('settlement_read',),403)])
def test_prices_need_separate_read_and_department_grant(fees,dept,actions,status):
    fees.cutting_auth['user']=user(*actions,department=dept)
    assert fees.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==status


def test_schema_protection_and_factory_isolation(fees):
    p=fees;price(p)
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-d'}).status_code==422
    with p.engine.begin() as connection:
        with pytest.raises(Exception):
            connection.execute(text('DELETE FROM cutting_ops_settlement_events'))
        connection.execute(text('DROP TRIGGER cutting_settlement_no_delete'))
    assert p.get(URL+'/2026-10',params={'factory_id':'huakang-c'}).status_code==503
    assert send(p,task_id='external',kind='accept',sets=1).status_code==503
