"""Same month/price races on SQLite and optional dedicated PostgreSQL."""
from dataclasses import replace
from test_cutting_usage_concurrency import race_engine, client, race
from test_cutting_periods import month_client, accounting, custody, bridge, flow, planned, actor, ACTIONS, draft, act, get, URL
from test_cutting_usage import read as usage_read, URL as USAGE_URL
from test_cutting_ops import command


def test_two_reviewers_lock_exactly_once(month_client):
    p=month_client
    draft(p);act(p,'submit')
    p.cutting_auth['user']=replace(actor(*ACTIONS),id='reviewer')
    revision=get(p)['revision']
    bodies=[command(month='2026-10',expected_version=revision) for _ in range(2)]
    results=race(*[lambda b=b:p.post(URL+'/lock',json=b) for b in bodies])
    assert sorted(r.status_code for r in results)==[200,409]
    assert len([e for e in get(p)['history'] if e['action']=='lock'])==1


def test_price_change_and_lock_share_one_evidence_basis(month_client):
    p=month_client
    draft(p);act(p,'submit')
    p.cutting_auth['user']=replace(actor(*ACTIONS),id='reviewer')
    lock_body=command(month='2026-10',expected_version=get(p)['revision'])
    price_body=command(expected_version=usage_read(p)['revision'],day='2026-11-10',issue_id=p.issue_id,unit_cost='4',currency='HKD',price_reference='并发成本凭据')
    results=race(lambda:p.post(URL+'/lock',json=lock_body),lambda:p.post(USAGE_URL+'/price',json=price_body))
    assert sorted(r.status_code for r in results)==[200,409]
    value=get(p)
    if value['state']=='locked':
        assert value['data']['snapshot']['costs']['HKD']['ending_normal']=='6.25'
