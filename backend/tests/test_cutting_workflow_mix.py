"""Finite real-cookie transition races on pytest-owned SQLite only."""
from contextlib import contextmanager
from time import perf_counter
from pathlib import Path
import json
import pytest
from cutting_workflow_mix import conserved_payments, race, run_workflows
from cutting_mix_audit import segmented_diagnostics
from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order
from test_cutting_http_capacity import add_dispatched_orders, isolated_http
from cutting_capacity_fixture import expand_chains
from cutting_financial_capacity_fixture import expand_financial_chains
from test_cutting_http_soak import Diagnostics, request_stats, awake_system
from test_cutting_p5c import evidence


def test_payment_conservation_rejects_inconsistent_rows_and_headers():
    row=dict(currency='CNY',payable='30',paid='5',pending='20',unpaid='25',available='5')
    value=dict(rows=[row],totals=[dict(row)])
    conserved_payments(value)
    value['totals'][0]['pending']='0'
    with pytest.raises(AssertionError):conserved_payments(value)


@pytest.mark.parametrize('fail_at',['none','entry','body'])
def test_context_measurement_preserves_release_and_exceptions(fail_at):
    diagnostic=Diagnostics.__new__(Diagnostics);diagnostic.origin=perf_counter()
    released=[]
    @contextmanager
    def resource():
        if fail_at=='entry':raise ValueError('entry')
        try:yield 'slot'
        finally:released.append(True)
    stats={'phases':[]};token=request_stats.set(stats)
    try:
        def invoke():
            with diagnostic.tracked_context(resource,'gate')() as value:
                assert value=='slot'
                if fail_at=='body':raise ValueError('body')
        if fail_at=='none':invoke()
        else:
            with pytest.raises(ValueError,match=fail_at):invoke()
        assert bool(released)==(fail_at!='entry')
        assert [p['name'] for p in stats['phases']]==(['gate.failed_wait'] if fail_at=='entry' else ['gate.wait','gate.held'])
    finally:request_stats.reset(token)


def test_real_cookie_material_finance_and_period_races(role_flow,tmp_path):
    p=role_flow
    prepare_closed_order(p)
    add_dispatched_orders(p,6)
    expand_chains(p,3)
    expand_financial_chains(p,2)
    report=dict(status='failed',scope='Six dispatches, three production chains, two finance chains; same-process subset API, not full-app capacity')
    p.app.middleware_stack=None
    diagnostic=Diagnostics(p)
    try:
        with awake_system(),isolated_http(p,tmp_path) as url:
            diagnostic.start()
            run_workflows(url, Path(p.engine.url.database).resolve(),report,line='http-capacity-2',chains=3)
        assert report['status']=='passed'
        assert report['finance']['same_balance_protected']
        assert report['period']['locked_write_rejected']
    finally:
        diagnostic.close()
        if report.get('samples'):
            report['diagnostic']=segmented_diagnostics(dict(requests=diagnostic.rows,lock_spans=diagnostic.lock_spans),report['samples'])
        (evidence(tmp_path)/'workflow-mix.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
