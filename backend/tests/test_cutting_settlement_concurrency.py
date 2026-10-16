"""Cutting transaction-lock races, with optional dedicated PostgreSQL coverage."""
from test_cutting_usage_concurrency import race_engine, client, race
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_reporting import production, send
from test_cutting_settlement import fees, price, save, record, URL
from test_cutting_ops import command
from dataclasses import replace
from uuid import uuid4
from test_cutting_ops import user
from test_cutting_settlement import ACTIONS, basis


def test_price_revision_and_confirmation_serialize(fees):
    p=fees;price(p,value='2');did=save(p,sets=3)
    p.post(URL+'/submit',json=command(expected_version=record(p)['revision'],document_id=did)).raise_for_status()
    p.cutting_auth['user']=replace(user(*ACTIONS),id='independent-reviewer')
    b=basis(p);row=b['rows'][0]
    quote=command(expected_version=b['revision'],line_id='line-1',task_id='external',context_token=row['context_token'],unit_price='4',currency='CNY',evidence='Revised quote')
    confirm=command(expected_version=b['revision'],document_id=did)
    responses=race(lambda:p.post(URL+'/price',json=quote),lambda:p.post(URL+'/confirm',json=confirm))
    assert sorted(r.status_code for r in responses)==[200,409]
    result=record(p,did)
    assert result['data']['snapshot']['total']=='6.00'
    if responses[0].status_code==200:
        confirm.update(operation_id=uuid4().hex,expected_version=result['revision'])
        assert p.post(URL+'/confirm',json=confirm).status_code==409
        assert result['state']=='submitted'
    else:assert result['state']=='confirmed'


def test_return_and_new_reservation_preserve_rounding_dependency(fees):
    p=fees;price(p);one=save(p)
    p.post(URL+'/submit',json=command(expected_version=record(p)['revision'],document_id=one)).raise_for_status()
    two=save(p)
    p.cutting_auth['user']=replace(user(*ACTIONS),id='independent-reviewer')
    revision=record(p)['revision']
    responses=race(lambda:p.post(URL+'/return',json=command(expected_version=revision,document_id=one)),lambda:p.post(URL+'/submit',json=command(expected_version=revision,document_id=two)))
    assert sorted(r.status_code for r in responses)==[200,409]
    if responses[0].status_code==200:
        assert p.post(URL+'/submit',json=command(expected_version=record(p)['revision'],document_id=two)).status_code==409
        assert basis(p)['rows'][0]['reserved_sets']==0
    else:
        assert p.post(URL+'/return',json=command(expected_version=record(p)['revision'],document_id=one)).status_code==409
        assert basis(p)['rows'][0]['reserved_sets']==2


def test_acceptance_correction_and_reservation_serialize(fees):
    p=fees;price(p);did=save(p,sets=10)
    body=command(expected_version=record(p)['revision'],document_id=did)
    responses=race(lambda:p.post(URL+'/submit',json=body),lambda:send(p,'void',document_id=p.acceptance))
    assert sorted(r.status_code for r in responses)==[200,409]


def test_same_unknown_retry_creates_one_reservation(fees):
    p=fees;price(p);did=save(p,sets=10)
    body=command(expected_version=record(p)['revision'],document_id=did)
    responses=race(*[lambda:p.post(URL+'/submit',json=body)]*2)
    assert [r.status_code for r in responses]==[200,200]
    assert responses[0].json()==responses[1].json()
    assert len(record(p,did)['history'])==2
