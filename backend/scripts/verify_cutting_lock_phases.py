"""Profile owned synthetic SQLite copies via an independent API subprocess.

Accepts only a previously passed synthetic 500/100/20 soak fixture. No business
DB, configured application startup, external URL or original data is accepted.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from queue import Queue, Empty
import sqlite3
import sys
from threading import Barrier, Event
from time import perf_counter
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[2]


def diagnostics_summary(diagnostic, samples):
    from cutting_mix_audit import segmented_diagnostics
    assert not diagnostic['heartbeat_gaps'], 'Run interrupted by a heartbeat gap'
    assert not any(r['failed_sql'] for r in diagnostic['requests']), 'SQL failure during probe'
    retries = {r['request_id'] for r in samples if r['endpoint'].startswith('payment_') and r['endpoint'].endswith('_retry')}
    measured = [r for r in diagnostic['requests'] if r['request_id'] in retries]
    assert retries and {r['request_id'] for r in measured} == retries, 'Missing payment retry diagnostics'
    assert all(r['lock_seconds'] == 0 for r in measured), 'Committed payment retry reserved the writer'
    assert all(r.get('admission_seconds',0.) == 0 for r in measured), 'Committed payment retry entered writer admission'
    phases = {}
    for span in diagnostic['lock_spans']:
        group = phases.setdefault(span['phase'], dict(count=0, hold_seconds=0., max_hold_seconds=0., max_wait_seconds=0.))
        group['count'] += 1
        group['hold_seconds'] += span['hold_seconds']
        group['max_hold_seconds'] = max(group['max_hold_seconds'], span['hold_seconds'])
        group['max_wait_seconds'] = max(group['max_wait_seconds'], span['wait_seconds'])
    return dict(payment_retries=len(measured), payment_retry_write_lock_seconds=0, phases=phases,
                segmented=segmented_diagnostics(diagnostic, samples),
                total_admission_seconds=sum(r.get('admission_seconds',0.) for r in diagnostic['requests']),
                max_request_admission_seconds=max((r.get('admission_seconds',0.) for r in diagnostic['requests']),default=0.),
                boundary='Lock hold ends at connection return; upper bound, not exact DBAPI release instant')


def seed_file(path, *, root=ROOT):
    path=Path(path).resolve()
    if not path.is_relative_to((root/'.tmp/cutting-http-soak').resolve()) or path.name!='cutting.db' or not path.is_file():
        raise ValueError('Only a previous isolated synthetic soak fixture is accepted')
    run=path.parent.parent.parent
    if path.parent.parent.name!='databases':
        raise ValueError('Invalid fixture provenance path')
    outer=json.loads((run/'report.json').read_text(encoding='utf-8'))
    inner=json.loads((run/'evidence/financial-soak.json').read_text(encoding='utf-8'))
    if outer['automated_status']!='passed' or inner['automated_status']!='passed' or any(
        inner['config'][key]!=expected for key,expected in dict(orders=500,chains=100,finance_chains=20,workers=10).items()):
        raise ValueError('Seed requires passed 500-order/100-production/20-finance provenance')
    return path


def run_probe(database, seconds, report, *, server_context=None, cycle_pause=.2, production_write_orders=0, workflow_probes=False):
    # Defensive environment fence before importing any app/test package.
    os.environ.update(DATABASE_URL='sqlite://', SEED_DEFAULT_ACCOUNTS='false')
    sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'backend/tests')]
    import httpx
    from cutting_http_process import independent_http
    from test_cutting_http_soak import awake_system
    from test_cutting_http_capacity import login_http, endpoint_metrics, projection, validate_workbook
    from cutting_financial_capacity_fixture import validate_settlement_workbook, assert_payment_balances
    from cutting_production_mix import ProductionMix, reconcile_totals

    base='/api/cutting-operations'
    samples=[];failures=[];payments=[];payment_statements=[]
    abort=Event();registrar_done=Event();barrier=Barrier(10,timeout=30);reviews=Queue(maxsize=1)
    report.update(samples=samples,failures=failures,payment_documents=payments,payment_statement_ids=payment_statements)
    with awake_system(), (server_context or independent_http)(database) as url, ExitStack() as stack:
        sessions=[stack.enter_context(httpx.Client(base_url=url,trust_env=False,timeout=30)) for _ in range(10)]
        for i,session in enumerate(sessions):login_http(session,'clerk' if i<2 else 'registrar' if i==2 else 'reviewer')
        def read(path,**params):
            value=sessions[-1].get(base+path,params={'factory_id':'huakang-c',**params})
            assert value.status_code==200,(path,value.status_code)
            return value.json()
        assert sessions[0].get(base+'/workspace/costs',params={'factory_id':'huakang-c'}).status_code==403
        assert sessions[0].get(base+'/workspace/planning',params={'factory_id':'huakang-d'}).status_code==422
        initial_payments=read('/payments/2026-11')
        assert_payment_balances(initial_payments,20)
        statements=[]
        for row in initial_payments['rows']:
            value=read('/settlements/2026-10',document_id=row['settlement_id'])
            item=value['data']['snapshot']['rows'][0]
            statements.append(dict(document_id=row['settlement_id'],event_id=value['event_id'],
                line_id=item['line_id'],acceptance_id=item['acceptance_id'],snapshot=value['data']['snapshot']))
        initial_period=read('/periods/2026-10')
        frozen=initial_period['data']['snapshot']
        period_body=dict(factory_id='huakang-c',kind='period',month='2026-10',event_id=initial_period['event_id'])
        endpoints=[('planning','/workspace/planning',{}),('tasks','/workspace/tasks',{'day':'2026-10-15'}),
            ('inventory','/workspace/inventory',{}),('costs','/workspace/costs',{}),('period','/periods/2026-10',{}),
            ('settlement','/settlements/2026-10',{'document_id':statements[0]['document_id']}),('payments','/payments/2026-11',{})]
        expected={name:projection(name,read(path,**params)) for name,path,params in endpoints}
        assert expected['planning'][0]==500
        def all_rows(path):
            first=read(path)
            rows=list(first['data'])
            for page in range(2,(first['total']+first['page_size']-1)//first['page_size']+1):
                value=read(path,page=page)
                assert value['total']==first['total']
                rows.extend(value['data'])
            assert len(rows)==first['total']
            return rows
        inventory=all_rows('/workspace/inventory');costs=all_rows('/workspace/costs')
        assert len(inventory)==200 and len(costs)==100
        mix = ProductionMix(read, inventory, costs, production_write_orders) if production_write_orders else None
        if mix:
            report['production_write_records'] = mix.records
        initial_basis=sessions[2].get(base+'/payment-basis',params={'factory_id':'huakang-c'}).json()
        baseline_revision=initial_basis['revision']
        def worker(index):
            local=[];errors=[];posted=[];cycles=0;active='';session=sessions[index]
            def request(name,method,path,**kwargs):
                nonlocal active
                active=name;identifier=uuid4().hex;began=perf_counter();status=0;size=0
                try:
                    response=session.request(method,base+path,headers={'X-Test-Request-ID':identifier},**kwargs)
                    status=response.status_code;size=len(response.content)
                    assert status==200,f'{name}: HTTP {status}; {response.text[:250]}'
                    return response
                finally:
                    local.append(dict(endpoint=name,seconds=perf_counter()-began,started_seconds=began,
                                      status=status,bytes=size,request_id=identifier))
            def get(name,path,**params):return request(name,'GET',path,params={'factory_id':'huakang-c',**params}).json()
            def post(name,path,body):
                result=request(name,'POST',path,json=body).json()
                assert request(name+'_retry','POST',path,json=body).json()==result
                return result
            def action(identifier,name):
                current=get('payment_read','/payments/2026-12',document_id=identifier)
                return post('payment_'+name,'/payments/'+name,dict(factory_id='huakang-c',operation_id=uuid4().hex,
                    expected_version=current['revision'],reason='Synthetic isolated lock-phase probe',document_id=identifier))
            began=perf_counter();last_progress=began
            try:
                barrier.wait();began=perf_counter();deadline=began+seconds
                while not abort.is_set() and (cycles==0 or perf_counter()<deadline or (index==3 and not registrar_done.is_set())):
                    if index<2:
                        if mix:
                            mix.write(index,cycles,get,post)
                        else:
                            get('clerk_inventory','/workspace/inventory')
                    elif index==2:
                        value=get('payment_basis','/payment-basis')
                        identifier=uuid4().hex
                        body=dict(factory_id='huakang-c',operation_id=uuid4().hex,expected_version=value['revision'],
                            reason='Synthetic isolated lock-phase probe',document_id=identifier,base_event_id=None,
                            day='2026-12-14',voucher_no='LOCK-PROBE-'+identifier,method='bank',evidence='Synthetic payment evidence',
                            currency='CNY',amount='1.00',basis_token=value['basis_token'],replaces_document_id=None,
                            allocations=[dict(settlement_id=statements[cycles%20]['document_id'],amount='1.00')])
                        post('payment_save','/payments/save',body);action(identifier,'submit')
                        done=Event();reviews.put((identifier,done),timeout=30)
                        while not done.wait(.1):assert not abort.is_set(),'Reviewer did not finish'
                        posted.append(identifier)
                        payment_statements.append(body['allocations'][0]['settlement_id'])
                    elif index==3:
                        try:identifier,done=reviews.get(timeout=.25)
                        except Empty:
                            if registrar_done.is_set():break
                            continue
                        try:
                            action(identifier,'confirm')
                            current=get('payment_read','/payments/2026-12',document_id=identifier)
                            assert current['data']['prepared_by']=='registrar' and current['history'][-1]['actor']=='reviewer'
                            assert not current['data']['local_admin_acceptance']
                            action(identifier,'reverse')
                        finally:done.set()
                    else:
                        for name,path,params in endpoints:
                            value=get(name,path,**params)
                            if name=='payments':assert_payment_balances(value,20,active=True)
                            elif mix and name in {'inventory','costs'}:mix.validate_live(name,value,expected)
                            else:assert projection(name,value)==expected[name],name
                        fee=(cycles+index)%2==1;statement=statements[(cycles+index)%20]
                        body=dict(factory_id='huakang-c',kind='settlement',month='2026-10',
                            document_id=statement['document_id'],event_id=statement['event_id']) if fee else period_body
                        prefix='fee_' if fee else ''
                        preview=request(prefix+'export_preview','POST','/exports/preview',json=body).json()
                        content=request(prefix+'export_download','POST','/exports/download',json=body|{'token':preview['token']})
                        if fee:validate_settlement_workbook(content,statement)
                        else:validate_workbook(content,multiplier=100,expected_delivery=preview['delivery'])
                    cycles+=1
                    if index==0 and perf_counter()-last_progress>=30:
                        print(f'Full probe {perf_counter()-began:.0f}s; first reader completed {cycles} cycles',flush=True)
                        last_progress=perf_counter()
                    if index!=3:abort.wait(cycle_pause)
            except Exception as error:
                errors.append(dict(endpoint=active,type=type(error).__name__,detail=str(error)[:500]));abort.set()
            finally:
                if index==2:registrar_done.set()
            return local,errors,posted,dict(index=index,cycles=cycles,seconds=perf_counter()-began)
        began=perf_counter()
        with ThreadPoolExecutor(max_workers=10) as pool:
            futures=[pool.submit(worker,i) for i in range(10)]
            runs=[]
            for future in as_completed(futures):
                rows,errors,posted,worker_run=future.result();samples.extend(rows);failures.extend(errors);payments.extend(posted);runs.append(worker_run)
        elapsed=perf_counter()-began
        report.update(elapsed_seconds=elapsed,requests=len(samples),worker_runs=runs,
            per_endpoint={name:{key:val for key,val in endpoint_metrics([s for s in samples if s['endpoint']==name],elapsed,
                [f for f in failures if f['endpoint']==name]).items() if key!='samples'} for name in sorted({s['endpoint'] for s in samples})})
        assert not failures,failures
        assert len(runs)==10 and all(r['cycles'] and r['seconds']>=seconds for r in runs)
        assert read('/periods/2026-10')['data']['snapshot']==frozen
        for statement in statements:
            current=read('/settlements/2026-10',document_id=statement['document_id'])
            assert current['event_id']==statement['event_id'] and current['data']['snapshot']==statement['snapshot']
        assert_payment_balances(read('/payments/2026-11'),20)
        assert read('/payments/2026-11')['totals']==initial_payments['totals']
        assert read('/payments/2026-12')['revision']==baseline_revision+4*len(payments)
        final_inventory=all_rows('/workspace/inventory');final_costs=all_rows('/workspace/costs')
        if mix:
            report['production_reconciliation'] = mix.reconcile(read,final_inventory,final_costs,seconds)
            from cutting_mix_audit import audit_history
            report['production_history_reconciliation'] = audit_history(read, database, mix.records)
            reconcile_totals(read('/workspace/inventory'),final_inventory,read('/workspace/costs'),final_costs)
            report['production_aggregate_headers_reconciled']=True
            if seconds>=600:
                assert len(set(payment_statements))==20, 'Incomplete rotating payment statement coverage'
        else:
            assert final_inventory==inventory
            assert final_costs==costs
        preview=sessions[-1].post(base+'/exports/preview',json=period_body)
        assert preview.status_code==200
        exported=sessions[-1].post(base+'/exports/download',json=period_body|{'token':preview.json()['token']})
        assert exported.status_code==200
        validate_workbook(exported,multiplier=100,expected_delivery=preview.json()['delivery'],full_readback=True)
        report.update(frozen_facts_unchanged=True,baseline_balances_unchanged=True,payment_cycles=len(payments))
        report.update(inventory_rows=len(inventory),cost_rows=len(costs),final_month_full_readback=True)
        assert len(payments)>0
        # Logouts affect synthetic sessions only, not business facts.
        for session in sessions:assert session.post('/api/auth/logout').status_code==204
        if workflow_probes:
            from cutting_workflow_mix import run_workflows
            report['workflow_probes']={}
            run_workflows(url,database,report['workflow_probes'])
    with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
        report['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
        report['foreign_key_errors']=len(db.execute('PRAGMA foreign_key_check').fetchall())
        assert report['integrity']=='ok' and not report['foreign_key_errors']
        for identifier in payments:
            assert [row[0] for row in db.execute('SELECT action FROM cutting_ops_payment_events WHERE document_id=? ORDER BY version',(identifier,))]==['save','submit','confirm','reverse']
        if mix:
            report['production_persisted'] = mix.verify_persisted(db)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed',required=True)
    parser.add_argument('--seconds',type=int,default=120)
    args=parser.parse_args()
    if not 10<=args.seconds<=180:parser.error('Use 10–180 seconds')
    source=seed_file(args.seed)
    output=ROOT/'.tmp/cutting-lock-phases'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:8])
    output.mkdir(parents=True,exist_ok=False);database=output/'cutting.db'
    before=sha256(source.read_bytes()).hexdigest()
    with sqlite3.connect(source.as_uri()+'?mode=ro',uri=True) as src,sqlite3.connect(database) as dst:src.backup(dst)
    (output/'fixture.json').write_text(json.dumps(dict(kind='cutting-synthetic-copy',source_sha256=before)),encoding='utf-8')
    from verify_cutting_p5b import source_state
    initial=source_state()
    report=dict(status='failed',seconds=args.seconds,source=initial,seed_sha256=before,release_ready=False,
        scope='Synthetic subset API in an independent process; not full-app startup, target hardware or production capacity')
    print(str(output),flush=True)
    try:
        run_probe(database,args.seconds,report)
        report['diagnostic_summary']=diagnostics_summary(json.loads((output/'diagnostics.json').read_text(encoding='utf-8')),report['samples'])
        report['status']='passed'
    except Exception as error:
        report['error']=dict(type=type(error).__name__,detail=str(error)[:1000])
    finally:
        report['source_after']=source_state()
        report['source_unchanged']=initial==report['source_after']
        report['seed_unchanged']=before==sha256(source.read_bytes()).hexdigest()
        if not report['source_unchanged'] or not report['seed_unchanged']:report['status']='failed'
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=report['status'],error=report.get('error'),release_ready=False)),flush=True)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
