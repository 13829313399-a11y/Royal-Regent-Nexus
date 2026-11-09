"""State-machine contracts against the packaged local SQLite API and actual file workers."""
from datetime import date
import json
import sqlite3
from fastapi.testclient import TestClient
import pytest
from app.main import create_app
from test_api import BASE,HEADERS,preview,fixtures

P='/api/customer-order-ledger'


def post(client,path,body=None,**kw):
    return client.post(P+path,headers=HEADERS,json=body,**kw)


def imported(client,factory='huaxing'):
    fields,files,parsed=preview(client,factory)
    r=client.post(P+'/imports/'+fields['customer_code'],headers=HEADERS,data=fields,files=files)
    assert r.status_code==200,r.text
    return r.json(),fields,files


@pytest.mark.parametrize('factory',['huakang-a','huakang-d','huaxing','huadeng'])
def test_each_factory_atomic_import_sources_and_restart(factory,tmp_path):
    with TestClient(create_app(tmp_path,factory_id=factory),base_url=BASE) as c:
        result,fields,files=imported(c,factory)
        assert result['created_count']>0 and result['local_only'] is True
        assert 'warehouse_sync' not in result
        r=c.post(P+'/imports/'+fields['customer_code'],headers=HEADERS,data=fields,files=files)
        assert r.status_code==200,r.text
        assert r.json()['created_count']==0 and r.json()['existing_count']==result['created_count']
        detail=c.get(P+'/lines/'+result['items'][0]['id'],params={'factory_id':factory}).json()
        assert len(detail['versions'])==1 and not detail['dispatches'] and not detail['shipments']
        source_bytes={pair[1][0]:pair[1][1] for pair in files}
        for source in detail['sources']:
            downloaded=c.get(P+'/sources/'+source['id'],params={'factory_id':factory})
            assert downloaded.content==source_bytes[source['file_name']]
        exported=c.get('/api/orders/exports/'+result['export_id']+'/download')
        assert exported.status_code==200
        assert exported.headers['X-Output-SHA256']==result['output_sha256']
        assert c.get(P+'/lines',params={'factory_id':'huakang-c'}).status_code==403
    with TestClient(create_app(tmp_path,factory_id=factory),base_url=BASE) as c:
        lines=c.get(P+'/lines',params={'factory_id':factory}).json()
        assert lines['total']==result['created_count']
        assert c.get('/api/orders/exports').json()['total']==1


@pytest.mark.parametrize('tamper',['fingerprint','confirmation','override','batch-error'])
def test_invalid_import_has_no_order_source_or_export(tamper,tmp_path):
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        fields,files,_=preview(c,'huaxing')
        if tamper=='fingerprint':fields['preview_fingerprint']='stale'
        elif tamper=='confirmation':fields['skipped_issue_keys']='["forged-key"]'
        elif tamper=='override':fields['manual_overrides']='[{"row_id":"bad","issue_key":"bad","field":"quantity","value":"10"}]'
        else:fields.update(reconcile_line_id='absent',reconciliation_reason='合成资料关联核对',expected_revision='1')
        r=c.post(P+'/imports/'+fields['customer_code'],headers=HEADERS,data=fields,files=files)
        assert r.status_code in {400,404,409},r.text
        assert c.get('/api/orders/exports').json()['total']==0
        assert c.get(P+'/lines?factory_id=huaxing').json()['total']==0
        with sqlite3.connect(tmp_path/'order_trial.sqlite3') as db:
            assert db.execute('SELECT count(*) FROM order_ledger_sources').fetchone()[0]==0


def test_dispatch_receive_amend_ship_reverse_cancel_restore(tmp_path):
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        result,_,_=imported(c);line=result['items'][0];ident=line['id'];suffix='?factory_id=huaxing'
        def action(name,body):return post(c,'/lines/'+ident+'/'+name+suffix,body)
        r=action('dispatch',{'expected_revision':line['revision'],'recipients':['pmc','warehouse','injection']})
        assert r.status_code==200,r.text
        line=r.json()
        for recipient in ['pmc','warehouse','injection']:
            inbox=c.get(P+'/inbox',params={'factory_id':'huaxing','recipient':recipient}).json()
            assert inbox['total']==1 and inbox['items'][0]['status']=='sent'
        item=inbox['items'][0]
        r=post(c,'/inbox/'+item['id']+'/receive?factory_id=huaxing&recipient=pmc')
        assert r.status_code==404
        r=post(c,'/inbox/'+item['id']+'/receive?factory_id=huaxing&recipient=injection')
        assert r.status_code==200 and r.json()['status']=='received' and r.json()['received_at']
        assert post(c,'/inbox/'+item['id']+'/receive?factory_id=huaxing&recipient=injection').json()['received_at']==r.json()['received_at']
        # Stale revision cannot partially alter quantities or notifications.
        body={'expected_revision':1,'quantity':'500','requested_ship_date':'2026-12-01','note':'核对修改','reason':'合成资料变更测试'}
        assert action('amend',body).status_code==409
        body['expected_revision']=line['revision'];r=action('amend',body)
        assert r.status_code==200,r.text
        line=r.json();assert line['version']==2
        assert c.get(P+'/inbox?factory_id=huaxing&recipient=pmc').json()['total']==2
        assert action('dispatch',{'expected_revision':line['revision'],'recipients':['cutting']}).status_code==422
        shipping={'expected_revision':line['revision'],'quantity':'600','ship_date':'2026-01-01','document_no':'TRIAL-001','idempotency_key':'local-test-shipment-1','note':'实际合成走货'}
        assert action('shipments',shipping).status_code==409
        shipping['quantity']='25';r=action('shipments',shipping);assert r.status_code==200,r.text
        line=r.json();assert line['shipped_quantity']=='25'
        replay=action('shipments',shipping);assert replay.status_code==200 and replay.json()['shipped_quantity']=='25'
        assert action('shipments',{**shipping,'quantity':'26'}).status_code==409
        detail=c.get(P+'/lines/'+ident+suffix).json();assert len(detail['shipments'])==1
        r=post(c,'/shipments/'+detail['shipments'][0]['id']+'/reverse'+suffix,{'expected_revision':line['revision'],'reason':'合成走货数量冲销'})
        assert r.status_code==200,r.text
        line=r.json();assert line['shipped_quantity']=='0'
        r=action('cancel',{'expected_revision':line['revision'],'reason':'合成订单取消核对'})
        assert r.status_code==200;r=r.json();assert r['status']=='cancelled'
        body={'expected_revision':r['revision'],'reason':'合成订单恢复核对','confirmed':True,'notify_recipients':False}
        assert action('restore',body).status_code==400
        r=action('restore',{**body,'notify_recipients':True});assert r.status_code==200,r.text
        line=r.json();assert line['status']=='active'
        detail=c.get(P+'/lines/'+ident+suffix).json()
        assert len(detail['versions'])==4 and detail['shipments'][0]['reversed']
        for recipient in ['pmc','warehouse','injection']:
            assert c.get(P+'/inbox',params={'factory_id':'huaxing','recipient':recipient}).json()['total']==4
        schedule=c.get(P+'/schedule?factory_id=huaxing&customer_code=disney').json()
        assert schedule['summary']['order_count']==1 and schedule['summary']['shipped_quantity']=='0'
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        detail=c.get(P+'/lines/'+ident+suffix).json()
        assert detail['line']['status']=='active' and len(detail['versions'])==4
        inbox=c.get(P+'/inbox?factory_id=huaxing&recipient=injection').json()
        assert len([item for item in inbox['items'] if item['status']=='received'])==1


def test_history_opening_real_worker_and_correction(tmp_path):
    make=fixtures('test_customer_order_history.py',{'workbook'},date=date)['workbook']
    content=make()
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        data={'factory_id':'huaxing','customer_code':'buzzbee'};files={'schedule_file':('historical.xlsx',content)}
        r=c.post(P+'/history/preview',headers=HEADERS,data=data,files=files)
        assert r.status_code==200,r.text
        parsed=r.json();assert len(parsed['rows'])==3
        assert c.get(P+'/lines?factory_id=huaxing').json()['total']==0
        selections=[{'id':row['id'],'status':'cancelled' if row['section']=='cancelled' else 'active','opening_shipped_quantity':n} for row,n in zip(parsed['rows'],['20','10','80'])]
        data.update(fingerprint=parsed['fingerprint'],cutoff_date='2025-12-31',reason='合成历史期初核对',confirmed='true',selections=json.dumps(selections))
        r=c.post(P+'/history/confirm',headers=HEADERS,data=data,files=files)
        assert r.status_code==200,r.text
        result=r.json();assert result['created_count']==3
        first=result['items'][0];suffix='?factory_id=huaxing'
        detail=c.get(P+'/lines/'+first['id']+suffix).json()
        assert not detail['shipments'] and not detail['dispatches']
        r=post(c,'/lines/'+first['id']+'/history-opening'+suffix,{'expected_revision':first['revision'],'reason':'合成期初更正核对','opening_shipped_quantity':'30'})
        assert r.status_code==200,r.text
        assert r.json()['shipped_quantity']=='30'
        detail=c.get(P+'/lines/'+first['id']+suffix).json()
        assert len(detail['versions'])==2 and not detail['shipments']


def test_database_identity_and_atomic_evidence_failure(tmp_path,monkeypatch):
    path=tmp_path/'order_trial.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE production_orders (id TEXT)')
        db.execute("INSERT INTO production_orders VALUES ('existing')")
    before=path.read_bytes()
    with pytest.raises(RuntimeError,match='不是当前版本'):
        create_app(tmp_path)
    assert path.read_bytes()==before
    path.unlink()
    app=create_app(tmp_path)
    def fail(*args,**kwargs):raise RuntimeError('intentional local evidence failure')
    monkeypatch.setattr(app.state.history,'save_on',fail)
    with TestClient(app,base_url=BASE) as c:
        fields,files,_=preview(c,'huaxing')
        with pytest.raises(RuntimeError,match='intentional'):
            c.post(P+'/imports/'+fields['customer_code'],headers=HEADERS,data=fields,files=files)
        assert c.get(P+'/lines?factory_id=huaxing').json()['total']==0
        assert c.get('/api/orders/exports').json()['total']==0
    with sqlite3.connect(path) as db:
        for table in ['order_ledger_lines','order_ledger_versions','order_ledger_sources','order_ledger_line_sources','order_ledger_identities']:
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
        db.execute('PRAGMA user_version=999')
    with pytest.raises(RuntimeError,match='不是当前版本'):
        create_app(tmp_path)


def test_full_original_immutable_guards_and_dispatch_receipt(tmp_path):
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        result,_,_=imported(c);line=result['items'][0];ident=line['id'];suffix='?factory_id=huaxing'
        r=post(c,'/lines/'+ident+'/dispatch'+suffix,{'expected_revision':1,'recipients':['pmc']})
        assert r.status_code==200
        r=post(c,'/lines/'+ident+'/shipments'+suffix,{'expected_revision':r.json()['revision'],'quantity':'1',
          'ship_date':'2026-01-01','document_no':'GUARD-001','idempotency_key':'guard-shipment-001','note':''})
        assert r.status_code==200,r.text
        detail=c.get(P+'/lines/'+ident+suffix).json()
        r=post(c,'/shipments/'+detail['shipments'][0]['id']+'/reverse'+suffix,{'expected_revision':r.json()['revision'],'reason':'保护规则冲销测试'})
        assert r.status_code==200,r.text
    with sqlite3.connect(tmp_path/'order_trial.sqlite3') as db:
        guards=db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'order_ledger_%'").fetchall()
        assert len(guards)==14
        for table,field in [('order_ledger_versions','reason'),('order_ledger_sources','file_name'),
            ('order_ledger_line_sources','source_id'),('order_ledger_shipments','note'),
            ('order_ledger_shipment_reversals','reason'),('order_ledger_identities','identity_key')]:
            for sql in [f'UPDATE {table} SET {field}={field}',f'DELETE FROM {table}']:
                with pytest.raises(sqlite3.IntegrityError,match='immutable'):db.execute(sql)
        for sql in ['UPDATE order_ledger_dispatches SET snapshot=snapshot','DELETE FROM order_ledger_dispatches']:
            with pytest.raises(sqlite3.IntegrityError,match='immutable'):db.execute(sql)
        db.execute("UPDATE order_ledger_dispatches SET received_at='2026-11-09 12:00:00',received_by='本机PMC核对'")
    with TestClient(create_app(tmp_path),base_url=BASE) as c:
        inbox=c.get(P+'/inbox?factory_id=huaxing&recipient=pmc').json()
        assert inbox['items'][0]['status']=='received'
