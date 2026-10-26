"""Optional transition probes under concurrent reads on an owned synthetic API.

Called only after the main profile reconciles, using the same exclusive copy.
These finite races are not a sustained ten-writer capacity claim.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from decimal import Decimal as D
import json
import sqlite3
from threading import Barrier, Event, Lock
from time import perf_counter
from uuid import uuid4


BASE = '/api/cutting-operations'
FACTORY = 'huakang-c'


def conserved_payments(value):
    for row in [*value['rows'], *value['totals']]:
        assert D(row['unpaid']) == D(row['payable'])-D(row['paid'])
        assert D(row['available']) == D(row['unpaid'])-D(row['pending']) >= 0
    for total in value['totals']:
        for field in ('payable','paid','pending','unpaid','available'):
            assert D(total[field]) == sum((D(r[field]) for r in value['rows'] if r['currency']==total['currency']),D(0))


def race(functions):
    barrier = Barrier(len(functions), timeout=30)
    def call(fn):
        barrier.wait()
        return fn()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:
        return list(pool.map(call, functions))


def verify_commands(db, commands, denied):
    """Each accepted transition has one receipt/event; rejected ones have none."""
    checked={}
    for item in commands:
        body,result,path,actor=(item[k] for k in ('body','result','path','actor'))
        identifier=body.get('operation_id',body.get('request_id'))
        if identifier in checked:
            assert checked[identifier]==item
            continue
        checked[identifier]=item
        if 'operation_id' in body:
            row=db.execute('SELECT actor_id,action,result FROM cutting_ops_commands WHERE operation_id=?',(identifier,)).fetchone()
            assert row and row[0]==actor and json.loads(row[2])==result
            action=path.rsplit('/',1)[-1]
            if '/materials/' in path:
                assert row[1]=='material-'+action+':'+path.split('/orders/')[1].split('/')[0]
            else:
                kind='period' if '/periods/' in path else 'payment'
                assert row[1]==kind+'-'+action
                table='cutting_ops_period_events' if kind=='period' else 'cutting_ops_payment_events'
                event=db.execute('SELECT action,actor_id,version,data FROM '+table+' WHERE id=?',(result['id'],)).fetchone()
                assert event and event[:3]==(action,actor,result['version'])
                if kind=='period' and action=='save':
                    assert json.loads(event[3])['input']==body
        if '/materials/' in path or '/warehouse-operations/' in path:
            row=db.execute('SELECT actor_id,kind,business_date,payload_json FROM warehouse_operations_documents WHERE id=?',(result['id'],)).fetchone()
            assert row and row[0]==actor and row[2]==body['business_date']
            payload=json.loads(row[3])
            assert row[1]==(body['kind'] if 'kind' in body else 'REQUEST' if path.endswith('/request') else 'CUTTING_RECEIPT')
            for key in ('quantity','original_id','batch_id','location_id'):
                if key in body:assert payload[key]==body[key]
    for item in denied:
        body=item['body']
        if 'operation_id' in body:
            assert not db.execute('SELECT 1 FROM cutting_ops_commands WHERE operation_id=?',(body['operation_id'],)).fetchone()
        else:
            assert not db.execute('SELECT 1 FROM warehouse_operations_documents WHERE request_id=?',(body['request_id'],)).fetchone()
    return dict(unique_committed_commands=len(checked),rejected_commands_without_facts=len(denied))


def run_workflows(url, database, report, *, line='http-capacity-90', chains=100):
    import httpx
    from test_cutting_http_capacity import login_http, validate_workbook
    stop, guard = Event(), Lock()
    samples, commands, failures, actors, denied = [], [], [], {}, []
    report.update(status='failed', samples=samples, failures=failures,
        scope='Finite transition races plus three read/export workers; ten synthetic sessions, not ten simultaneous writers or a sustained capacity pass')
    def request(session, name, method, path, *, expected=200, **kwargs):
        identifier, began = uuid4().hex, perf_counter()
        response = None
        try:
            response = session.request(method,path,headers={'X-Test-Request-ID':identifier},**kwargs)
            allowed = expected if isinstance(expected,tuple) else (expected,)
            assert response.status_code in allowed, (name,response.status_code,response.text[:500])
            if response.status_code==409:
                denied.append(dict(path=path,body=kwargs['json'],detail=response.json()['detail']))
            return response
        finally:
            with guard:
                samples.append(dict(endpoint=name, request_id=identifier, started_seconds=began,
                    seconds=perf_counter()-began,status=response.status_code if response is not None else 0,
                    expected_statuses=list(expected if isinstance(expected,tuple) else (expected,))))
    def get(session,path,**params):
        return request(session,'read:'+path,'GET',BASE+path,params=dict(factory_id=FACTORY,**params)).json()
    def post(session,name,path,body,expected=200):
        response=request(session,name,'POST',path,json=body,expected=expected)
        if response.status_code==200:
            replay=request(session,name+'_retry','POST',path,json=body)
            assert replay.json()==response.json(), 'Retry changed committed receipt'
            commands.append(dict(path=path,body=body,result=response.json(),actor=actors[id(session)]))
        return response
    def command(**data):
        return dict(factory_id=FACTORY,operation_id=uuid4().hex,reason='Synthetic workflow race',**data)
    with ExitStack() as stack:
        sessions=[stack.enter_context(httpx.Client(base_url=url,timeout=45,trust_env=False)) for _ in range(10)]
        for session, role in zip(sessions,['registrar','registrar','reviewer','reviewer','clerk','warehouse','supervisor','reviewer','reviewer','reviewer']):
            login_http(session,role)
            actors[id(session)]=role
        a,b,reviewer,reviewer2,clerk,warehouse,supervisor=sessions[:7]
        baseline=get(reviewer,'/payments/2026-12')
        conserved_payments(baseline)
        frozen=get(reviewer,'/periods/2026-10')
        export_body=dict(factory_id=FACTORY,kind='period',month='2026-10',event_id=frozen['event_id'])
        reader_cycles=[0,0,0]
        def reader(index,session):
            try:
                while not stop.is_set():
                    if index==2:
                        preview=request(session,'workflow_export_preview','POST',BASE+'/exports/preview',json=export_body).json()
                        response=request(session,'workflow_export_download','POST',BASE+'/exports/download',json=export_body|{'token':preview['token']})
                        validate_workbook(response,multiplier=chains,expected_delivery=preview['delivery'])
                    else:
                        for path in ['/workspace/planning','/workspace/inventory','/workspace/costs']:
                            get(session,path)
                        conserved_payments(get(session,'/payments/2026-12'))
                        assert get(session,'/periods/2026-10')['data']['snapshot']==frozen['data']['snapshot']
                    reader_cycles[index]+=1
                    stop.wait(.2)
            except Exception as error:
                failures.append(dict(type=type(error).__name__,detail=str(error)[:1000]));stop.set()
        with ThreadPoolExecutor(max_workers=3) as pool:
            readers=[pool.submit(reader,i,sessions[7+i]) for i in range(3)]
            try:
                target=baseline['rows'][0]['settlement_id']
                documents=[]
                for session in (a,b):
                    basis=get(session,'/payment-basis');identifier=uuid4().hex
                    body=command(document_id=identifier,expected_version=basis['revision'],base_event_id=None,
                        day='2026-12-14',voucher_no='RACE-'+identifier,method='bank',evidence='Synthetic actual receipt',
                        currency='CNY',amount='20.00',basis_token=basis['basis_token'],replaces_document_id=None,
                        allocations=[dict(settlement_id=target,amount='20.00')])
                    post(session,'competing_save',BASE+'/payments/save',body);documents.append(identifier)
                revision=get(a,'/payments/2026-12')['revision']
                bodies=[command(document_id=did,expected_version=revision) for did in documents]
                results=race([lambda i=i:post(sessions[i],'competing_submit',BASE+'/payments/submit',bodies[i],(200,409)) for i in (0,1)])
                assert sorted(r.status_code for r in results)==[200,409]
                win=0 if results[0].status_code==200 else 1; lose=1-win
                stale=results[lose].json()['detail']
                assert '更新' in stale or '变化' in stale, stale
                fresh=command(document_id=documents[lose],expected_version=get(b,'/payments/2026-12')['revision'])
                rejected=post(b,'overspend_fresh_basis',BASE+'/payments/submit',fresh,409)
                assert '余额' in rejected.json()['detail']
                pending=get(reviewer,'/payments/2026-12');conserved_payments(pending)
                selected=next(r for r in pending['rows'] if r['settlement_id']==target)
                assert (D(selected['pending']),D(selected['available']))==(D(20),D(5))
                confirm=command(document_id=documents[win],expected_version=pending['revision'])
                confirmed=race([lambda s=s:post(s,'confirm_duplicate',BASE+'/payments/confirm',confirm) for s in (reviewer,reviewer2)])
                assert confirmed[0].json()==confirmed[1].json()
                value=get(reviewer,'/payments/2026-12',document_id=documents[win]);conserved_payments(value)
                assert value['data']['prepared_by']=='registrar' and not value['data']['local_admin_acceptance']
                reverse=command(document_id=documents[win],expected_version=value['revision'])
                reversed_results=race([lambda s=s:post(s,'reverse_duplicate',BASE+'/payments/reverse',reverse) for s in (reviewer,reviewer2)])
                assert reversed_results[0].json()==reversed_results[1].json()
                assert get(reviewer,'/payments/2026-12')['rows']==baseline['rows']
                report['finance']=dict(documents=documents,winner=documents[win],loser=documents[lose],
                    stale_rejection=stale,balance_rejection=rejected.json()['detail'],same_balance_protected=True)

                materials='/orders/'+line+'/materials'
                order=get(clerk,'/orders/'+line)['current']
                plan=order['data']['planning']['published']
                body=command(expected_version=order['version'],task_id='task-1',plan_version=plan['version'],row=0,
                    material_id='fabric-mat',material_revision=1,quantity='1',business_date='2026-11-01',mapping_basis='Synthetic same material/unit')
                req=post(clerk,'material_request',BASE+materials+'/request',body).json()
                def warehouse_get():
                    return request(warehouse,'warehouse_read','GET','/api/warehouse-operations/fabric',params={'factory_id':FACTORY}).json()
                def warehouse_post(kind,day='2026-11-03',expected=200,**data):
                    body=dict(factory_id=FACTORY,request_id=str(uuid4()),expected_revision=warehouse_get()['revision'],
                              kind=kind,business_date=day,reason='Synthetic workflow race',**data)
                    return post(warehouse,'warehouse_'+kind,'/api/warehouse-operations/fabric/documents',body,expected)
                stock=warehouse_get()
                issue_basis=next(r for r in get(reviewer,'/orders/'+line+'/usage',with_costs=True)['issues'] if r['context']['execution']=='internal')
                root=issue_basis['context']['root_batch_id']
                batch=next(r for r in stock['stock'] if r['original_batch_id']==root and D(r['quantity'])>=1)
                issued=warehouse_post('ISSUE',day='2026-11-01',original_id=req['id'],batch_id=batch['id'],quantity='1',counterparty='R01').json()
                revision=get(clerk,materials)['revision']
                receipt_bodies=[command(expected_version=revision,original_id=issued['id'],quantity='0.4',business_date='2026-11-02') for _ in range(2)]
                # Separate client objects, same least-privilege clerk identity.
                assert b.post('/api/auth/logout').status_code==204
                second=b;login_http(second,'clerk')
                actors[id(second)]='clerk'
                received=race([lambda i=i:post([clerk,second][i],'receipt_race',BASE+materials+'/receive',receipt_bodies[i],(200,409)) for i in (0,1)])
                assert sorted(r.status_code for r in received)==[200,409]
                conflict=next(r for r in received if r.status_code==409).json()['detail']
                assert '变化' in conflict or '更新' in conflict, conflict
                returned=warehouse_post('RETURN',original_id=issued['id'],quantity='0.1',location_id='bin').json()
                warehouse_post('CORRECTION',day='2026-11-04',original_id=returned['id'])
                final_receipt=command(expected_version=get(clerk,materials)['revision'],original_id=issued['id'],quantity='0.6',business_date='2026-11-04')
                post(clerk,'receipt_remaining',BASE+materials+'/receive',final_receipt)
                def period_action(session,action):
                    value=get(session,'/periods/2026-11')
                    return post(session,'period_'+action,BASE+'/periods/'+action,command(month='2026-11',expected_version=value['revision']))
                basis=get(supervisor,'/periods/2026-11/basis')
                assert not basis['blockers'], basis['blockers']
                allocations=[dict(issue_id=r['issue_id'],opening_completed_quantity=r['carried_completed_quantity'] or '0',
                                  completed_quantity=r['carried_completed_quantity'] or '0') for r in basis['rows']]
                save=command(month='2026-11',expected_version=basis['revision'],basis_token=basis['basis_token'],allocations=allocations,
                    materials_complete=True,public_material_pending=False,opening_verified=True,unrecorded_opening=False,exceptions_reviewed=True)
                post(supervisor,'period_save',BASE+'/periods/save',save)
                period_action(supervisor,'submit');period_action(reviewer,'lock')
                locked=get(reviewer,'/periods/2026-11');assert locked['state']=='locked'
                before_denial=warehouse_get()['revision']
                locked_denial=warehouse_post('RETURN',day='2026-11-05',expected=409,original_id=issued['id'],quantity='0.1',location_id='bin')
                assert '锁' in locked_denial.json()['detail']
                assert warehouse_get()['revision']==before_denial
                period_action(reviewer,'reopen')
                old=get(reviewer,'/periods/2026-11',event_id=locked['event_id'])
                assert old['selected_state']=='locked' and old['state']=='reopened'
                assert old['data']['snapshot']==locked['data']['snapshot']
                warehouse_post('RETURN',day='2026-11-05',original_id=issued['id'],quantity='0.1',location_id='bin')
                current=get(clerk,materials)
                row=next(i for r in current['requests'] for i in r['issues'] if i['id']==issued['id'])
                assert D(row['received_quantity'])==1 and D(row['returned_quantity'])==D('.1')
                report['materials']=dict(line_id=line,issue_id=issued['id'],received='1',returned='0.1',
                    receipt_race_protected=True,return_correction_preserved=True)
                report['period']=dict(month='2026-11',frozen_event=locked['event_id'],independent_review=True,
                    locked_write_rejected=True,historical_snapshot_unchanged=True,final_state='reopened')
            finally:
                stop.set()
                for future in readers:future.result(timeout=90)
        assert not failures, failures
        assert all(reader_cycles), 'Every background reader/exporter must execute'
        report['reader_cycles']=reader_cycles
        with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as db:
            report['command_event_reconciliation']=verify_commands(db,commands,denied)
            for identifier in documents:
                expected=['save','submit','confirm','reverse'] if identifier==documents[win] else ['save']
                events=db.execute('SELECT action,actor_id FROM cutting_ops_payment_events WHERE document_id=? ORDER BY version',(identifier,)).fetchall()
                assert [e[0] for e in events]==expected
                assert [e[1] for e in events]==(['registrar','registrar','reviewer','reviewer'] if identifier==documents[win] else ['registrar'])
            report['integrity']=db.execute('PRAGMA integrity_check').fetchone()[0]
            report['foreign_key_errors']=len(db.execute('PRAGMA foreign_key_check').fetchall())
            assert report['integrity']=='ok' and report['foreign_key_errors']==0
        for session in sessions:
            assert session.post('/api/auth/logout').status_code==204
        report.update(status='passed',successful_requests_idempotently_replayed=len(commands))
