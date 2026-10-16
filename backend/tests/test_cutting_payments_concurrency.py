"""Shared-lock payment allocation races on SQLite and optional PostgreSQL."""
from test_cutting_usage_concurrency import race_engine, client, race
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, ok
from test_cutting_settlement import fees, decision as fee_decision, record as fee_record
from test_cutting_payments import paid_setup, body, save, read, decision, reviewer, URL
from test_cutting_ops import command


def test_two_payments_cannot_overspend_same_payable(paid_setup):
    p=paid_setup
    one=save(p,amount='15',allocations=[dict(settlement_id=p.one,amount='15')])
    two=save(p,amount='15',allocations=[dict(settlement_id=p.one,amount='15')])
    rev=read(p)['revision']
    responses=race(*[lambda did=did:p.post(URL+'/submit',json=command(expected_version=rev,document_id=did)) for did in (one,two)])
    assert sorted(r.status_code for r in responses)==[200,409]
    loser=two if responses[0].status_code==200 else one
    assert decision(p,loser,'submit').status_code==409
    assert read(p)['totals'][0]['pending']=='15.00'


def test_duplicate_actual_voucher_reserves_only_once(paid_setup):
    p=paid_setup;one=save(p,voucher_no='BANK-ONLY-ONCE');two=save(p,voucher_no='bank-only-once',allocations=[dict(settlement_id=p.two,amount='5')])
    rev=read(p)['revision']
    responses=race(*[lambda did=did:p.post(URL+'/submit',json=command(expected_version=rev,document_id=did)) for did in (one,two)])
    assert sorted(r.status_code for r in responses)==[200,409]
    loser=two if responses[0].status_code==200 else one
    assert decision(p,loser,'submit').status_code==409


def test_submission_and_settlement_reopen_serialize(paid_setup):
    p=paid_setup;did=save(p,allocations=[dict(settlement_id=p.two,amount='5')])
    payment=command(expected_version=read(p)['revision'],document_id=did)
    fees_body=command(expected_version=fee_record(p)['revision'],document_id=p.two)
    responses=race(lambda:p.post(URL+'/submit',json=payment),lambda:p.post('/api/cutting-operations/settlements/reopen',json=fees_body))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_confirm_retry_and_reverse_never_double_count(paid_setup):
    p=paid_setup;did=save(p);ok(decision(p,did,'submit'));reviewer(p)
    command_body=command(expected_version=read(p)['revision'],document_id=did)
    responses=race(*[lambda:p.post(URL+'/confirm',json=command_body)]*2)
    assert [r.status_code for r in responses]==[200,200]
    assert responses[0].json()==responses[1].json()
    assert read(p)['totals'][0]['paid']=='5.00'
    command_body=command(expected_version=read(p)['revision'],document_id=did)
    responses=race(*[lambda:p.post(URL+'/reverse',json=command_body)]*2)
    assert [r.status_code for r in responses]==[200,200]
    assert read(p)['totals'][0]['paid']=='0.00'
    assert len(read(p,did)['history'])==4


def test_competing_draft_edits_still_conflict_after_balance_refresh(paid_setup):
    from test_cutting_payments import basis
    p=paid_setup;did=save(p)
    one=body(p,document_id=did,evidence='edit A');two=body(p,document_id=did,evidence='edit B')
    responses=race(lambda:p.post(URL+'/save',json=one),lambda:p.post(URL+'/save',json=two))
    assert sorted(r.status_code for r in responses)==[200,409]
    loser=two if responses[0].status_code==200 else one
    newest=basis(p,did);loser.update(expected_version=newest['revision'],basis_token=newest['basis_token'])
    assert p.post(URL+'/save',json=loser).status_code==409
    assert len(read(p,did)['history'])==2
