"""Bounded synthetic production/material/finance load; never opens the original DB."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from decimal import Decimal
from queue import Queue, Empty
from threading import Barrier, Event
from time import perf_counter, process_time
from uuid import uuid4
import json
import os

import httpx
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session

from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order, BASE, command
from test_cutting_http_soak import Diagnostics, awake_system
from test_cutting_http_capacity import isolated_http, add_dispatched_orders, login_http, projection, validate_workbook, endpoint_metrics
from test_cutting_p5c import evidence
from cutting_capacity_fixture import expand_chains
from cutting_financial_capacity_fixture import (
    expand_financial_chains, assert_payment_balances, verify_payment_book, validate_settlement_workbook,
)
from app.models.cutting_ops import CuttingProductionEvent
from app.models.cutting_material_usage import CuttingMaterialEvent
from app.models.cutting_payment import CuttingPaymentEvent


REQUIRED = {'planning', 'tasks', 'inventory', 'costs', 'period', 'settlement', 'payments',
    'export_preview', 'export_download', 'fee_export_preview', 'fee_export_download',
    'handover_basis', 'handover', 'handover_retry', 'usage_basis', 'usage', 'usage_retry',
    'payment_basis', 'payment_save', 'payment_save_retry', 'payment_read', 'payment_submit',
    'payment_submit_retry', 'payment_confirm', 'payment_confirm_retry', 'payment_reverse', 'payment_reverse_retry'}


def configuration():
    result = {key: int(os.environ.get('CUTTING_FINANCE_SOAK_'+key.upper(), default)) for key, default in
              [('orders','3'), ('chains','3'), ('finance_chains','2'), ('workers','5'), ('seconds','3')]}
    assert 3 <= result['chains'] <= min(result['orders'], 100)
    assert 2 <= result['finance_chains'] <= min(result['chains'], 20)
    assert result['orders'] <= 500 and 5 <= result['workers'] <= 10
    assert 3 <= result['seconds'] <= 600
    result['workload'] = os.environ.get('CUTTING_FINANCE_SOAK_WORKLOAD', 'paced')
    assert result['workload'] in ('paced', 'burst')
    return result


def check_live(name, value, expected, config):
    count = config['chains']
    if name == 'payments':
        assert_payment_balances(value, config['finance_chains'], active=True)
    elif name == 'inventory':
        assert value['total'] == count*2 and set(value['units']) == {'米'}
        total = {k: Decimal(v) for k,v in value['units']['米'].items()}
        assert total['received_quantity'] == count*6
        assert total['returned_quantity'] == total['unsigned_quantity'] == 0
        assert total['loss_quantity'] == Decimal('.5')*count
        assert total['consumed_quantity']-count*2 in {Decimal(0), Decimal('.1'), Decimal('.2')}
        assert total['remaining_quantity'] == total['received_quantity']-total['consumed_quantity']-total['loss_quantity']
        for row in value['data']:
            received, consumed, loss, remaining = (Decimal(row[k]) for k in
                ('received_quantity','consumed_quantity','loss_quantity','remaining_quantity'))
            assert received-consumed-loss-Decimal(row['returned_quantity']) == remaining >= 0
            assert received in (2,4)
    elif name == 'costs':
        assert value['total'] == count and value['pending_pricing'] == 0
        assert set(value['currencies']) == {'HKD'}
        cost = value['currencies']['HKD']
        delta = Decimal(cost['normal'])-count*8
        assert delta in {Decimal(0), Decimal('.4'), Decimal('.8')}
        assert Decimal(cost['loss']) == count*2
        if delta:
            # New use invalidates the previous live allocation; it must not
            # silently keep an apparently confirmed completed/WIP amount.
            assert cost['completed'] is None and cost['wip'] is None
        else:
            assert cost == expected[name][1]['HKD']
    else:
        assert projection(name, value) == expected[name], name


def test_live_payment_balance_checks_reject_duplicate_posting():
    def value(paid='10.00'):
        return dict(rows=[dict(currency='CNY', payable='30.00', paid='5.00', pending='0.00', unpaid='25.00', available='25.00')]*2,
            totals=[dict(currency='CNY', payable='60.00', paid=paid, pending='0.00', unpaid=str(60-Decimal(paid)), available=str(60-Decimal(paid)))])
    assert_payment_balances(value(), 2, active=True)
    with pytest.raises(AssertionError):
        assert_payment_balances(value('12.00'), 2, active=True)


def test_expanded_financial_mixed_http(role_flow, tmp_path):
    report = dict(config=configuration(), automated_status='failed', release_ready=False,
                  production_capacity_accepted=False, original_database_accessed=False)
    try:
        run(role_flow, tmp_path, report)
        report['automated_status'] = 'passed'
    except Exception as error:
        report['error'] = dict(type=type(error).__name__, detail=str(error)[:1000])
        raise
    finally:
        (evidence(tmp_path)/'financial-soak.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def run(p, tmp_path, report):
    config = report['config']
    prepare_closed_order(p)
    add_dispatched_orders(p, config['orders'])
    issues = expand_chains(p, config['chains'])
    statements = expand_financial_chains(p, config['finance_chains'])
    verify_payment_book(p, statements)
    report['financial_samples'] = statements
    p.app.middleware_stack = None
    diagnostic = Diagnostics(p)
    samples, failures, records, runs = [], [], [], []
    report.update(samples=samples, failures=failures, write_records=records, worker_runs=runs,
                  server_requests=diagnostic.rows, heartbeat_gaps=diagnostic.gaps, lock_spans=diagnostic.lock_spans)
    endpoints = [('planning','/workspace/planning',{}), ('tasks','/workspace/tasks',{'day':'2026-10-15'}),
        ('inventory','/workspace/inventory',{}), ('costs','/workspace/costs',{}), ('period','/periods/2026-10',{}),
        ('settlement','/settlements/2026-10',{'document_id':p.one}), ('payments','/payments/2026-11',{})]
    try:
        with awake_system(), isolated_http(p, tmp_path) as url, ExitStack() as stack:
            sessions = [stack.enter_context(httpx.Client(base_url=url, timeout=30, trust_env=False)) for _ in range(config['workers'])]
            for index, session in enumerate(sessions):
                login_http(session, 'clerk' if index < 2 else 'registrar' if index == 2 else 'reviewer')
            registrar_access = sessions[2].get(BASE+'/access', params={'factory_id':'huakang-c'}).json()
            assert 'payment_prepare' in registrar_access['permissions'] and 'payment_confirm' not in registrar_access['permissions']
            def read(path, **params):
                response = sessions[-1].get(BASE+path, params={'factory_id':'huakang-c', **params})
                assert response.status_code == 200, response.text
                return response.json()
            expected = {name:projection(name, read(path, **params)) for name,path,params in endpoints}
            assert expected['planning'][0] == config['orders']
            assert expected['tasks'][1] == 2*config['chains'] and expected['tasks'][2]['completed'] == 25*config['chains']
            frozen = read('/periods/2026-10')['data']['snapshot']
            period_body = dict(factory_id='huakang-c',kind='period',month='2026-10',event_id=expected['period'][1])
            abort, registrar_done = Event(), Event()
            reviews = Queue(maxsize=1)
            barrier = Barrier(config['workers'], timeout=30)

            def worker(index):
                session, local, errors, posted = sessions[index], [], [], []
                active_name = ''
                def request(name, method, path, **kwargs):
                    nonlocal active_name
                    active_name, began, identifier = name, perf_counter(), uuid4().hex
                    status, size = 0, 0
                    try:
                        response = session.request(method, BASE+path, headers={'X-Test-Request-ID':identifier}, **kwargs)
                        status, size = response.status_code, len(response.content)
                        assert status == 200, f'{name}: {status}: {response.text[:300]}'
                        return response
                    finally:
                        local.append(dict(endpoint=name, seconds=perf_counter()-began, status=status, bytes=size, request_id=identifier))
                def get(name, path, **params):
                    return request(name,'GET',path,params={'factory_id':'huakang-c',**params}).json()
                def post(name, path, body):
                    result = request(name,'POST',path,json=body).json()
                    assert request(name+'_retry','POST',path,json=body).json() == result
                    return result
                def payment_action(identifier, action):
                    current = get('payment_read','/payments/2026-11',document_id=identifier)
                    return post('payment_'+action,'/payments/'+action,command(expected_version=current['revision'],document_id=identifier))
                began, cycles, usage_document, export_count = perf_counter(), 0, None, 0
                deadline, last_progress = began+config['seconds'], began
                next_export = began+max(0,index-4)*7
                paced = config['workload'] == 'paced'
                try:
                    barrier.wait()
                    began = perf_counter()
                    deadline, last_progress = began+config['seconds'], began
                    next_export = began+max(0,index-4)*7
                    while not abort.is_set() and (cycles == 0 or perf_counter() < deadline or (index == 3 and not registrar_done.is_set())):
                        if index == 0:
                            path = '/orders/http-capacity-1/reports'
                            current = get('handover_basis',path,history_page=1)
                            task = next(t for t in current['tasks'] if t['task_id']=='task-1')
                            body = command(expected_version=current['version'],document_id='financial-soak-handover',entry=dict(
                                task_id='task-1',plan_version=task['plan_version'],day='2026-12-14',mode='sets',kind='handover',
                                sets=1+cycles%2,rejected=0,scrap=0,parts=[],evidence=f'合成混合写入{cycles}',exception_reason=''))
                            post('handover',path+'/post',body)
                            posted.append(dict(kind='handover',sets=1+cycles%2,operation_id=body['operation_id']))
                        elif index == 1:
                            path = '/orders/http-capacity-2/usage'
                            current = get('usage_basis',path)
                            consumed = Decimal('.1')*(1+cycles%2)
                            body = command(expected_version=current['revision'],issue_id=issues[2],day='2026-12-14',
                                consumed_quantity=str(consumed),loss_quantity='0',counted_remaining=str(Decimal('1.5')-consumed))
                            if usage_document:
                                body['document_id'] = usage_document
                            result = post('usage',path+('/correct' if usage_document else '/post'),body)
                            posted.append(dict(kind='usage',document_id=result['document_id'],replaces=usage_document,consumed=str(consumed)))
                            usage_document = result['document_id']
                        elif index == 2:
                            current = get('payment_basis','/payment-basis')
                            statement = statements[cycles % len(statements)]
                            identifier = uuid4().hex
                            body = command(expected_version=current['revision'],base_event_id=None,document_id=identifier,
                                day='2026-11-04',voucher_no='SOAK-'+identifier,method='bank',evidence='合成付款凭证',currency='CNY',
                                amount='1.00',basis_token=current['basis_token'],allocations=[dict(settlement_id=statement['document_id'],amount='1.00')],replaces_document_id=None)
                            post('payment_save','/payments/save',body)
                            payment_action(identifier,'submit')
                            done = Event()
                            reviews.put((identifier,done), timeout=30)
                            while not done.wait(.2):
                                assert not abort.is_set(), 'Independent payment reviewer failed'
                            posted.append(dict(kind='payment',document_id=identifier,settlement_id=statement['document_id']))
                        elif index == 3:
                            try:
                                identifier, done = reviews.get(timeout=.5)
                            except Empty:
                                if registrar_done.is_set():
                                    break
                                continue
                            try:
                                payment_action(identifier,'confirm')
                                value = get('payment_read','/payments/2026-11',document_id=identifier)
                                assert value['state']=='confirmed' and value['data']['prepared_by']=='registrar'
                                assert value['history'][-1]['actor']=='reviewer' and not value['data']['local_admin_acceptance']
                                payment_action(identifier,'reverse')
                                posted.append(dict(kind='review',document_id=identifier,event_id=value['event_id']))
                            finally:
                                done.set()
                        else:
                            selected = [endpoints[(cycles+index-4)%len(endpoints)]] if paced else endpoints
                            for name,path,params in selected:
                                check_live(name,get(name,path,**params),expected,config)
                            if not paced or perf_counter() >= next_export:
                                fee = (export_count+index)%2 == 1
                                statement = statements[(export_count+index-4)%len(statements)]
                                body = dict(factory_id='huakang-c',kind='settlement',month='2026-10',
                                    document_id=statement['document_id'],event_id=statement['event_id']) if fee else period_body
                                prefix = 'fee_' if fee else ''
                                preview = request(prefix+'export_preview','POST','/exports/preview',json=body).json()
                                downloaded = request(prefix+'export_download','POST','/exports/download',json=body|{'token':preview['token']})
                                if fee:
                                    validate_settlement_workbook(downloaded,statement)
                                else:
                                    validate_workbook(downloaded,multiplier=config['chains'],expected_delivery=preview['delivery'])
                                export_count += 1
                                next_export = perf_counter()+60
                        cycles += 1
                        if index == 0 and perf_counter()-last_progress >= 60:
                            print(f'financial soak elapsed {perf_counter()-began:.0f}s; handover cycles {cycles}',flush=True)
                            last_progress = perf_counter()
                        if index != 3:
                            abort.wait(2 if paced else (1 if index < 4 else .2))
                except Exception as error:
                    errors.append(dict(worker=index,endpoint=active_name,type=type(error).__name__,detail=str(error)[:700]))
                    abort.set()
                finally:
                    if index == 2:
                        registrar_done.set()
                return local,errors,posted,dict(worker=index,seconds=perf_counter()-began,cycles=cycles,role='clerk' if index<2 else 'registrar' if index==2 else 'reviewer')

            diagnostic.start()
            began,cpu = perf_counter(),process_time()
            with ThreadPoolExecutor(max_workers=config['workers']) as pool:
                futures = [pool.submit(worker,index) for index in range(config['workers'])]
                for future in as_completed(futures):
                    try:
                        rows,errors,posted,worker_run = future.result()
                        samples.extend(rows); failures.extend(errors); records.extend(posted); runs.append(worker_run)
                    except Exception as error:
                        abort.set()
                        failures.append(dict(endpoint='worker',type=type(error).__name__,detail=str(error)[:700]))
            elapsed,cpu = perf_counter()-began,process_time()-cpu
            report.update(elapsed_seconds=elapsed,process_cpu_seconds=cpu,requests=len(samples),
                scope='API-created synthetic chains; 2 clerk sessions, coordinated registrar/reviewer pair, remaining reader sessions')
            report['per_endpoint'] = {name:endpoint_metrics([s for s in samples if s['endpoint']==name],elapsed,
                [e for e in failures if e['endpoint']==name]) for name in sorted({s['endpoint'] for s in samples})}
            # An aborted workflow can legitimately leave a pending document.
            # Preserve that evidence and report the original failing request.
            assert not failures, failures
            report['frozen_snapshot_unchanged'] = read('/periods/2026-10')['data']['snapshot']==frozen
            assert report['frozen_snapshot_unchanged']
            for statement in statements:
                current = read('/settlements/2026-10',document_id=statement['document_id'])
                assert current['event_id']==statement['event_id'] and current['data']['snapshot']==statement['snapshot']
                current = read('/payments/2026-11',document_id=statement['payment_id'])
                assert current['state']=='confirmed' and current['event_id']==statement['payment_event_id']
                assert current['data']['snapshot']==statement['payment_snapshot']
            assert_payment_balances(read('/payments/2026-11'),config['finance_chains'])
            handovers = [r for r in records if r['kind']=='handover']
            usages = [r for r in records if r['kind']=='usage']
            payments = [r for r in records if r['kind']=='payment']
            reviews = [r for r in records if r['kind']=='review']
            report['mixed_payment_statement_ids'] = sorted({r['settlement_id'] for r in payments})
            report['mixed_payment_statement_count'] = len(report['mixed_payment_statement_ids'])
            if handovers:
                current = read('/orders/http-capacity-1/reports')
                assert current['summary']['completed']==25 and current['summary']['actual_delivery']==22+handovers[-1]['sets']
                document = next(d for d in current['documents'] if d['document_id']=='financial-soak-handover')
                assert len(document['history'])==len(handovers)
            if usages:
                current = read('/orders/http-capacity-2/usage',with_costs=True)
                row = next(r for r in current['issues'] if r['issue_id']==issues[2])
                assert Decimal(row['consumed_quantity'])==2+Decimal(usages[-1]['consumed'])
                assert Decimal(row['remaining_quantity'])==Decimal('1.5')-Decimal(usages[-1]['consumed'])
                documents = {d['id']:d for d in current['documents']}
                for i,entry in enumerate(usages):
                    doc = documents[entry['document_id']]
                    assert doc['voided']==(i<len(usages)-1) and doc['replaces_document_id']==entry['replaces']
                    assert doc['replaced_by_document_id']==(usages[i+1]['document_id'] if i<len(usages)-1 else None)
            assert {r['document_id'] for r in payments}=={r['document_id'] for r in reviews}
            for entry in reviews:
                current = read('/payments/2026-11',document_id=entry['document_id'],event_id=entry['event_id'])
                assert current['state']=='reversed' and current['selected_state']=='confirmed'
                assert [h['action'] for h in current['history']]==['save','submit','confirm','reverse']
            # Full final pagination, independent from first-page traffic above.
            def all_pages(path, identifier, **params):
                first = read(path,**params)
                rows = list(first['data'])
                pages = (first['total']+first['page_size']-1)//first['page_size']
                for page in range(2,pages+1):
                    value = read(path,page=page,**params)
                    assert value['total']==first['total']
                    rows.extend(value['data'])
                assert len(rows)==len({r[identifier] for r in rows})==first['total']
                return rows,first
            inventory,inventory_view = all_pages('/workspace/inventory','issue_id')
            costs,cost_view = all_pages('/workspace/costs','line_id')
            assert len(inventory)==config['chains']*2 and len(costs)==config['chains']
            for key,total in inventory_view['units']['米'].items():
                assert sum(Decimal(r[key]) for r in inventory)==Decimal(total)
            if usages:
                last = Decimal(usages[-1]['consumed'])
                assert Decimal(inventory_view['units']['米']['consumed_quantity'])==2*config['chains']+last
                assert Decimal(inventory_view['units']['米']['remaining_quantity'])==Decimal('3.5')*config['chains']-last
                assert Decimal(cost_view['currencies']['HKD']['normal'])==8*config['chains']+4*last
                assert cost_view['currencies']['HKD']['completed'] is None and cost_view['currencies']['HKD']['wip'] is None
            assert sum(Decimal(r['normal']['HKD']) for r in costs)==Decimal(cost_view['currencies']['HKD']['normal'])
            assert sum(Decimal(r['loss']['HKD']) for r in costs)==Decimal(cost_view['currencies']['HKD']['loss'])
            report['final_pagination_reconciled'] = dict(inventory_rows=len(inventory),cost_rows=len(costs))
            with Session(p.engine) as db:
                production_count = db.scalar(select(func.count()).select_from(CuttingProductionEvent).where(CuttingProductionEvent.document_id=='financial-soak-handover',CuttingProductionEvent.action=='post'))
                usage_count = db.scalar(select(func.count()).select_from(CuttingMaterialEvent).where(CuttingMaterialEvent.document_id.in_([r['document_id'] for r in usages])))
                payment_count = db.scalar(select(func.count()).select_from(CuttingPaymentEvent).where(CuttingPaymentEvent.document_id.in_([r['document_id'] for r in payments])))
                integrity = db.execute(text('PRAGMA integrity_check')).scalar()
                foreign_keys = db.execute(text('PRAGMA foreign_key_check')).all()
            report.update(persisted=dict(handover_posts=production_count,usage_events=usage_count,payment_events=payment_count),
                writes=dict(handover=len(handovers),usage=len(usages),payment_cycles=len(payments)),integrity=integrity,
                foreign_key_errors=len(foreign_keys),financial_snapshots_unchanged=True)
            assert not failures, failures
            assert production_count==len(handovers)>=1 and usage_count==len(usages)*2-1>=1
            assert payment_count==len(payments)*4>=4
            assert integrity=='ok' and not foreign_keys and not diagnostic.gaps
            assert len(runs)==config['workers'] and all(r['seconds']>=config['seconds'] and r['cycles'] for r in runs)
            if config['seconds']>=120:
                assert not REQUIRED-{s['endpoint'] for s in samples}, 'Incomplete expanded workload endpoint coverage'
            if config['seconds']>=600:
                assert report['mixed_payment_statement_count']==config['finance_chains'], 'Not every financial chain received a mixed payment cycle'
            # Stream every exported row after the timed workload, so client-side
            # XLSX parsing does not inflate the API latency measurements.
            preview = sessions[-1].post(BASE+'/exports/preview',json=period_body)
            assert preview.status_code == 200, preview.text
            preview = preview.json()
            downloaded = sessions[-1].post(BASE+'/exports/download',json=period_body|{'token':preview['token']})
            assert downloaded.status_code == 200, downloaded.text
            validate_workbook(downloaded,multiplier=config['chains'],expected_delivery=preview['delivery'],full_readback=True)
            report.update(final_period_full_readback=True,final_period_volumes=preview['delivery']['volumes'])
        verify_payment_book(p,statements)
        report['final_payment_workbook_reconciled'] = True
    finally:
        diagnostic.close()
