"""Real isolated SQLite/SQLAlchemy coverage; no daily/production data is used."""
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
import importlib.util
import json
import sqlite3
import time

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
import pytest
from sqlalchemy import select,func
from app.models.qc_dossier import QcDossierOutbox
from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.services import qc_dossier as dossier,qc_dossier_worker as worker,qc_dossier_read as reader
from app.services.qc_dossier_events import install
from app.services import qc_workflow as wf,qc_inspection_sheet as sheet,qc_inspection_summary as summary,qc_approved_statistics as stats,qc_weekly_templates as weekly
from test_customer_order_ledger import engine,db,ingest,preview,service,ship_body
from test_qc_workflow import ACTOR

@pytest.fixture(autouse=True)
def isolated(monkeypatch,tmp_path,engine):
    monkeypatch.setattr(dossier.settings,'qc_department_data_dir',str(tmp_path/'companies'))
    monkeypatch.setattr(dossier.settings,'qc_dossier_enabled',True)
    monkeypatch.setattr(dossier.settings,'qc_dossier_factories','huaxing')
    QcDossierOutbox.__table__.create(engine)
    dossier.migrate();install()


def source(db):
    p=preview();p['rows'][0].update(customer_q='2026-11-06',line_q='2026-11-07',product_name_zh='示例产品',product_name_en='Demo product',remarks='电池：AA（2pcs）',note='订单原备注',standard='示例标准',date_code='00123',label='标签',customer_label='外箱贴纸',contact='受限联系人',extra_business={'enabled':False,'count':0,'value':None,'empty':''},password='never-archive',planned_inspection_date='2026-11-06',inspection_agency='客验')
    return ingest(db,p)


def push(db,line,batch='首验'):
    return wf.create_tasks(db,'huaxing',dict(requestKey=uuid4().hex,items=[dict(sourceId=line.id,sourceRevision=line.revision,method='external',batch=batch,plannedDate='2026-11-06',plannedQuantity='20')]),ACTOR)['items'][0]


def entry(db,task):
    rows=sheet.candidates('huaxing',[],wf.list_tasks(db,'huaxing')['items'],wf.sources(db,'huaxing')['items'])
    return sheet.sync('huaxing',rows)['items'][0]


def approve(db,line):
    task=push(db,line);r=entry(db,task)
    r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='QC真实手填'),ACTOR)
    r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
    r=sheet.review_batch('huaxing','confirm',dict(entries=[dict(id=r['id'],revision=r['revision'])],requestKey=uuid4().hex),ACTOR)['results'][0]['item']
    sid=summary.listing('huaxing',{})['items'][0]['id']
    return task,r,sid


def test_transaction_outbox_preserves_fields_types_and_sources(db):
    line=source(db);events=db.scalars(select(QcDossierOutbox)).all();assert len(events)==1
    raw=events[0].payload
    assert raw['data']['remarks']=='电池：AA（2pcs）' and raw['data']['note']=='订单原备注'
    assert raw['data']['customer_q']!=raw['data']['line_q']
    assert raw['data']['extra_business']=={'enabled':False,'count':0,'value':None,'empty':''}
    assert 'password' not in raw['data'] and 'content' not in raw['sources'][0]
    assert raw['record']['quantity']=='10000.0000' or Decimal(raw['record']['quantity'])==10000
    assert worker.drain_sales(db)==1
    with dossier.connect() as c:
        saved=json.loads(c.execute('SELECT payload FROM source_captures').fetchone()[0]);assert saved==raw
        assert c.execute('SELECT count(*) FROM source_captures').fetchone()[0]==1


def test_rollback_emits_no_source_event(db):
    p=preview();service.import_preview(db,preview=p,files=[],source_kind='formal',actor='test',reason='',controls={});db.rollback()
    assert db.scalar(select(func.count()).select_from(QcDossierOutbox))==0


def test_reconciliation_is_full_and_repeated_content_is_bounded(db):
    a=source(db);p=preview(reference='OTHER');p['customer_code']='other';ingest(db,p)
    assert worker.reconcile_sources(db)==2
    with dossier.connect() as c:before=c.execute('SELECT count(*) FROM source_observations').fetchone()[0]
    for _ in range(3):assert worker.reconcile_sources(db)==2
    with dossier.connect() as c:
        assert c.execute('SELECT count(*) FROM source_captures').fetchone()[0]==2
        assert c.execute('SELECT count(*) FROM source_observations').fetchone()[0]==before


def test_changed_source_revision_cancel_restore_shipping_and_same_version(db):
    line=source(db);worker.drain_sales(db)
    service.ship(db,line,ship_body(line),'业务测试');db.commit();worker.drain_sales(db)
    line.status='cancelled';line.revision+=1;db.commit();worker.drain_sales(db)
    line.status='active';line.revision+=1;db.commit();worker.drain_sales(db)
    line.data={**line.data,'packaging':'新包装'};db.commit();worker.drain_sales(db)
    with dossier.connect() as c:
        assert c.execute('SELECT count(*) FROM source_captures').fetchone()[0]==5
        assert c.execute("SELECT count(*) FROM source_observations WHERE warning<>''").fetchone()[0]>=1
        states=[json.loads(r[0])['record']['status'] for r in c.execute('SELECT payload FROM source_captures ORDER BY captured_at')]
        assert 'cancelled' in states and states[-1]=='active'
        assert Decimal(json.loads(c.execute('SELECT payload FROM source_captures ORDER BY captured_at DESC LIMIT 1').fetchone()[0])['record']['shipped_quantity'])==3000


def test_delivery_failure_retries_exact_original_payload(db,monkeypatch):
    line=source(db);original=db.scalars(select(QcDossierOutbox)).first().payload
    real=dossier.capture
    monkeypatch.setattr(dossier,'capture',lambda *a,**k:(_ for _ in ()).throw(sqlite3.OperationalError('offline')))
    assert worker.drain_sales(db)==0
    event=db.scalars(select(QcDossierOutbox)).first();assert event.attempts==1 and not event.delivered_at
    line.data={**line.data,'packaging':'later'};line.revision+=1;db.commit()
    monkeypatch.setattr(dossier,'capture',real);assert worker.drain_sales(db)==2
    with dossier.connect() as c:
        assert any(json.loads(x[0])==original for x in c.execute('SELECT payload FROM source_captures'))


def test_task_outbox_same_transaction_batches_and_duplicate_request(db):
    line=source(db);a=push(db,line);b=push(db,line,'第二批');again=push(db,line)
    assert a['id']==again['id'] and b['id']!=a['id']
    with wf.store() as c:assert c.execute('SELECT count(*) FROM dossier_outbox').fetchone()[0]==2
    assert worker.drain_tasks()==2 and worker.drain_tasks()==0
    with dossier.connect() as c:assert c.execute("SELECT count(*) FROM dossier_links WHERE phase='task'").fetchone()[0]==2


def test_source_archive_does_not_change_draft_revision_or_old_projection(db):
    line=source(db);task=push(db,line);r=entry(db,task);before=deepcopy(r);projection=deepcopy(wf.source_row(line))
    worker.drain_sales(db);worker.drain_tasks();worker.reconcile_sources(db)
    assert entry(db,task)==before and wf.source_row(line)==projection
    line.data={**line.data,'future_extension':False};db.commit();worker.drain_sales(db)
    assert entry(db,task)==before and wf.source_row(line)==projection


def test_full_flow_links_frozen_and_latest_without_changing_statistics(db):
    line=source(db);worker.drain_sales(db);task,r,sid=approve(db,line)
    before_stats=stats.query('huaxing',{});before_week=weekly.query('huaxing','2026-11-06')
    worker.drain_tasks();worker.reconcile_approvals()
    first=reader.detail('huaxing',sid,full_business=True)
    assert first['business']['status']=='linked'
    assert first['business']['frozen']['data']['packaging']=='客户指定箱唛'
    line.data={**line.data,'packaging':'验货后更新'};line.revision+=1;line.version+=1;db.commit();worker.drain_sales(db)
    second=reader.detail('huaxing',sid,full_business=True)
    assert second['business']['frozen']==first['business']['frozen']
    assert second['business']['latest']['data']['packaging']=='验货后更新'
    assert second['qc']['remark']=='QC真实手填' and second['remarkOrigin']=='qc-edited'
    assert stats.query('huaxing',{})==before_stats and weekly.query('huaxing','2026-11-06')==before_week
    with sheet.store() as c:
        assert json.loads(c.execute('SELECT approved_snapshot FROM entry_details WHERE entry_id=?',(r['id'],)).fetchone()[0])==r


def test_field_policy_unknown_extensions_secrets_and_cross_factory(db):
    line=source(db);task,r,sid=approve(db,line);worker.drain_tasks();worker.reconcile_approvals()
    public=reader.detail('huaxing',sid);private=reader.detail('huaxing',sid,full_business=True)
    assert 'contact' not in public['business']['frozen']['data'] and 'unit_price_hkd' not in public['business']['frozen']['data']
    assert public['business']['frozen']['restricted']
    assert private['business']['frozen']['data']['contact']=='受限联系人'
    assert private['business']['frozen']['data']['extra_business']['enabled'] is False
    assert 'never-archive' not in json.dumps(private)
    with pytest.raises(HTTPException) as e:reader.detail('huadeng',sid,full_business=True)
    assert e.value.status_code==404


def test_same_po_different_source_never_joined(db):
    a=source(db);p=preview();p['rows'][0]['product_no']='OTHER-PRODUCT';b=ingest(db,p)
    ta=push(db,a);tb=push(db,b);worker.drain_tasks()
    with dossier.connect() as c:
        links=c.execute('SELECT * FROM dossier_links ORDER BY task_id').fetchall()
        assert {r['source_id'] for r in links}=={a.id,b.id}


def test_get_is_read_only_even_without_archive_schema(db):
    line=source(db);task,r,sid=approve(db,line)
    with sqlite3.connect(dossier.path()) as c:
        for table in ['dossier_events','source_observations','source_captures']:
            for action in ['update','delete']:c.execute(f'DROP TRIGGER {table}_no_{action}')
        for table in ['dossier_links','source_heads','dossier_events','source_observations','source_captures','qc_dossier_schema','dossier_worker_state']:c.execute('DROP TABLE '+table)
    before=dossier.path().read_bytes()
    result=reader.detail('huaxing',sid)
    assert result['business']['status']=='not_initialized' and result['qc']['result']=='PASS'
    assert dossier.path().read_bytes()==before


def test_missing_historical_source_cannot_bind_latest(db,monkeypatch):
    line=source(db)
    monkeypatch.setattr(dossier.settings,'qc_dossier_enabled',False)
    task,r,sid=approve(db,line)
    monkeypatch.setattr(dossier.settings,'qc_dossier_enabled',True)
    worker.reconcile_sources(db);worker.reconcile_approvals()
    result=reader.detail('huaxing',sid)
    assert result['business']['status']=='missing' and result['business']['frozen'] is None
    assert result['business']['latest'] is not None


def test_migration_idempotent_immutable_and_outbox_rollback_protected(engine):
    dossier.migrate();dossier.migrate()
    with dossier.connect() as c:assert c.execute('SELECT version FROM qc_dossier_schema').fetchone()[0]==1
    path=Path(__file__).parents[1]/'alembic/versions/20261110_0194_qc_dossier_outbox.py'
    spec=importlib.util.spec_from_file_location('dossier_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as c:
        QcDossierOutbox.__table__.drop(c)
        with Operations.context(MigrationContext.configure(c)):
            migration.upgrade();migration.downgrade();migration.upgrade()
            c.execute(QcDossierOutbox.__table__.insert().values(id='retained',factory='huaxing',source_id='historical',payload={'evidence':'keep'},created_at=dossier.now(),delivered_at='',attempts=0,last_error=''))
            with pytest.raises(RuntimeError,match='不允许删除历史证据'):migration.downgrade()
            assert c.execute(select(func.count()).select_from(QcDossierOutbox)).scalar()==1


def test_capture_hash_corruption_is_not_displayed(db):
    line=source(db);task,r,sid=approve(db,line);worker.drain_tasks();worker.reconcile_approvals()
    with sqlite3.connect(dossier.path()) as c:
        with pytest.raises(sqlite3.IntegrityError):c.execute("UPDATE source_captures SET payload='{}'")
        c.execute('DROP TRIGGER source_captures_no_update');c.execute("UPDATE source_captures SET payload_hash='invalid'")
    with pytest.raises(HTTPException) as e:reader.detail('huaxing',sid)
    assert e.value.status_code==503


def test_approval_retry_rotates_past_unresolved_history(db):
    line=source(db);task,r,sid=approve(db,line)
    with sheet.store(True) as c:
        event=c.execute("SELECT * FROM changes WHERE action='confirm'").fetchone()
        columns=[k for k in event.keys() if k!='id']
        values=[event[k] for k in columns]
        for i in range(5):
            values[columns.index('request_key')]=uuid4().hex
            c.execute('INSERT INTO changes('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',values)
    visited=[]
    for i in range(3):
        assert worker.reconcile_approvals(limit=2)==2
        with dossier.connect() as c:visited.append(c.execute("SELECT value FROM dossier_worker_state WHERE key='approval_cursor'").fetchone()[0])
    assert len(set(visited))==3
    worker.drain_tasks()
    for _ in range(3):worker.reconcile_approvals(limit=2)
    with dossier.connect() as c:assert c.execute("SELECT count(*) FROM dossier_links WHERE phase='approval' AND status='linked'").fetchone()[0]==6


def test_task_delivery_outage_keeps_exact_event_and_qc_flow(db,monkeypatch):
    line=source(db);task,r,sid=approve(db,line)
    real=dossier.capture
    monkeypatch.setattr(dossier,'capture',lambda *a,**kw:(_ for _ in ()).throw(sqlite3.OperationalError('busy')))
    assert worker.drain_tasks()==0
    with wf.store() as c:
        event=c.execute('SELECT * FROM dossier_outbox').fetchone();original=event['payload']
        assert event['attempts']==1 and not event['delivered_at']
    assert summary.listing('huaxing',{})['total']==1
    line.data={**line.data,'packaging':'later'};line.revision+=1;db.commit()
    monkeypatch.setattr(dossier,'capture',real);assert worker.drain_tasks()==1
    worker.reconcile_approvals()
    assert reader.detail('huaxing',sid,full_business=True)['business']['frozen']['data']==json.loads(original)['data']


def test_revoke_return_reapprove_preserves_existing_workflow_and_evidence(db):
    line=source(db);task,r,sid=approve(db,line);worker.drain_tasks();worker.reconcile_approvals()
    first=reader.detail('huaxing',sid)['business']['frozen']['id']
    def command(r,action):
        return sheet.review_batch('huaxing',action,dict(entries=[dict(id=r['id'],revision=r['revision'])],reason='复核',requestKey=uuid4().hex),ACTOR)['results'][0]['item']
    r=command(r,'revoke')
    with pytest.raises(HTTPException) as e:reader.detail('huaxing',sid)
    assert e.value.status_code==404
    r=sheet.return_to_inspection('huaxing',r['id'],{'revision':r['revision'],'requestKey':uuid4().hex},ACTOR)['item'];assert r['reviewState']=='returned_to_inspection'
    r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='FAIL',remark='复验手填'),ACTOR)
    r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR);r=command(r,'confirm');worker.reconcile_approvals()
    detail=reader.detail('huaxing',sid)
    assert detail['business']['frozen']['id']==first and detail['qc']['remark']=='复验手填'
    assert [x['action'] for x in detail['audit']].count('confirm')==2
    with dossier.connect() as c:assert c.execute("SELECT count(*) FROM dossier_links WHERE phase='approval'").fetchone()[0]==2


def test_same_version_conflicting_evidence_is_ambiguous_and_late_old_event_not_latest(db):
    line=source(db);a=dossier.snapshot(db,line);b=deepcopy(a);b['data']['packaging']='冲突值'
    with dossier.connect(True) as c:
        dossier.capture(c,a,'2020-01-01T00:00:00+00:00','old')
        dossier.capture(c,b,'2020-01-02T00:00:00+00:00','conflict')
    task,r,sid=approve(db,line);worker.reconcile_approvals()
    assert reader.detail('huaxing',sid)['business']['status']=='ambiguous'
    newer=deepcopy(a);newer['record']['revision']+=1;newer['data']['packaging']='新值'
    with dossier.connect(True) as c:
        latest=dossier.capture(c,newer,dossier.now(),'new')
        dossier.capture(c,a,dossier.now(),'late-old')
        assert c.execute('SELECT capture_id FROM source_heads').fetchone()[0]==latest


def test_nested_sensitive_fields_are_not_exposed_as_public_work_fields(db):
    line=source(db);payload=dossier.snapshot(db,line);payload['data']['packaging']={'price':100,'contact':'private'}
    assert 'packaging' not in reader.public_source(payload,False)['data']
    assert reader.public_source(payload,True)['data']['packaging']['price']==100


def test_snapshot_metadata_and_link_identity_tampering_rejected(db):
    line=source(db);task,r,sid=approve(db,line);worker.drain_tasks();worker.reconcile_approvals()
    with sqlite3.connect(dossier.path()) as c:
        c.execute('DROP TRIGGER source_captures_no_update');c.execute('UPDATE source_captures SET source_revision=999')
    with pytest.raises(HTTPException) as e:reader.detail('huaxing',sid)
    assert e.value.status_code==503


def test_concurrent_idempotent_capture_and_qc_save(db):
    from concurrent.futures import ThreadPoolExecutor
    line=source(db);task=push(db,line);r=entry(db,task);payload=dossier.snapshot(db,line)
    def capture(i):
        with dossier.connect(True) as c:return dossier.capture(c,payload,dossier.now(),'race:'+str(i))
    def save():return sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='并发填写'),ACTOR)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(capture,i) for i in range(8)]+[pool.submit(save)]
        results=[f.result() for f in futures]
    assert len(set(results[:-1]))==1 and results[-1]['remark']=='并发填写'
    with dossier.connect() as c:assert c.execute('SELECT count(*) FROM source_captures').fetchone()[0]==1


def test_sql_outbox_failure_rolls_back_source_mutation(db):
    line=source(db);before=deepcopy(line.data)
    QcDossierOutbox.__table__.drop(db.get_bind())
    line.data={**line.data,'packaging':'must rollback'}
    from sqlalchemy.exc import OperationalError
    with pytest.raises(OperationalError):db.commit()
    db.rollback();assert db.get(Line,line.id).data==before


def test_migration_backup_restore_and_failure_is_additive(db,monkeypatch):
    line=source(db);task=push(db,line);r=entry(db,task)
    with sqlite3.connect(dossier.path()) as c,sqlite3.connect(str(dossier.path())+'.backup') as b:c.backup(b)
    worker.drain_sales(db);worker.drain_tasks()
    with sqlite3.connect(str(dossier.path())+'.backup') as b,sqlite3.connect(dossier.path()) as c:b.backup(c)
    with sheet.store() as c:assert sheet.unpack(c,sheet.get(c,'huaxing',r['id']))==r
    recovered=worker.recover_retained_events(db)
    assert recovered=={'sales':1,'tasks':1}
    with dossier.connect() as c:assert c.execute("SELECT count(*) FROM dossier_links WHERE phase='task'").fetchone()[0]==1
    assert worker.recover_retained_events(db)==recovered
    monkeypatch.setattr(dossier,'SCHEMA',dossier.SCHEMA+'\nNOT VALID SQL;')
    with pytest.raises(sqlite3.OperationalError):dossier.migrate()
    with sheet.store() as c:assert sheet.unpack(c,sheet.get(c,'huaxing',r['id']))==r


def test_exact_task_evidence_resolves_same_version_raw_change(db):
    line=source(db);worker.drain_sales(db)
    line.data={**line.data,'future_extension':False};db.commit();worker.drain_sales(db)
    task,r,sid=approve(db,line);worker.drain_tasks();worker.reconcile_approvals()
    value=reader.detail('huaxing',sid,full_business=True)
    assert value['business']['status']=='linked'
    assert value['business']['frozen']['data']['future_extension'] is False


def test_decimal_persistence_scale_does_not_create_a_fake_revision(db):
    line=source(db);before=dossier.snapshot(db,line);identity=line.id;db.expire_all()
    after=dossier.snapshot(db,db.get(Line,identity));assert before==after


def test_full_scan_crosses_pages_and_failure_does_not_hide_other_customers(db,monkeypatch):
    base=source(db)
    for i in range(205):
        db.add(Line(id='page-'+str(i).zfill(4),factory_id='huaxing',customer_code='another',customer_name='Another',identity_key=str(i),reference_no='ref',product_no=str(i),quantity=Decimal('1'),shipped_quantity=Decimal('0'),status='active',version=1,revision=1,data={'packaging':'示例'},created_at=dossier.now(),updated_at=dossier.now()))
    db.commit();assert worker.reconcile_sources(db)==206
    with dossier.connect() as c:assert c.execute('SELECT count(*) FROM source_captures').fetchone()[0]==206
    real=dossier.snapshot
    def fail_one(db,line):
        if line.id==base.id:raise ValueError('invalid JSON')
        return real(db,line)
    monkeypatch.setattr(dossier,'snapshot',fail_one)
    with pytest.raises(RuntimeError,match='1 records'):worker.reconcile_sources(db)
    with dossier.connect() as c:assert c.execute('SELECT count(*) FROM source_heads').fetchone()[0]==206


def test_large_json_does_not_change_task_payload_or_qc_revision(db):
    line=source(db);task=push(db,line);r=entry(db,task)
    line.data={**line.data,'extended_requirements':'资料 '*150000};db.commit()
    assert worker.drain_sales(db)==2
    assert entry(db,task)==r
    with dossier.connect() as c:assert max(len(x[0]) for x in c.execute('SELECT payload FROM source_captures'))>400000


def test_legacy_summary_retains_read_only_improvement_fallback(db):
    line=source(db);task,r,sid=approve(db,line)
    with sheet.store(True) as c:c.execute('UPDATE entry_details SET improvement=? WHERE entry_id=?',('旧详情已有措施',r['id']))
    with summary.store(True) as c:
        payload=json.loads(c.execute('SELECT payload FROM records WHERE id=?',(sid,)).fetchone()[0]);payload.pop('improvement',None)
        c.execute('UPDATE records SET payload=? WHERE id=?',(json.dumps(payload),sid))
    before=dossier.path().read_bytes()
    assert reader.detail('huaxing',sid)['qc']['improvement']=='旧详情已有措施'
    assert dossier.path().read_bytes()==before


def test_concurrent_capture_and_approval_keep_atomic_summary(db):
    from concurrent.futures import ThreadPoolExecutor
    line=source(db);task=push(db,line);r=entry(db,task)
    r=sheet.save('huaxing',r['id'],dict(revision=r['revision'],result='PASS',remark='并发审核'),ACTOR)
    r=sheet.submit('huaxing',r['id'],{'revision':r['revision']},ACTOR)
    payload=dossier.snapshot(db,line)
    def capture(i):
        with dossier.connect(True) as c:return dossier.capture(c,payload,dossier.now(),'approval-race:'+str(i))
    def confirm():
        return sheet.review_batch('huaxing','confirm',dict(entries=[dict(id=r['id'],revision=r['revision'])],requestKey=uuid4().hex),ACTOR)
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(capture,i) for i in range(6)];approval=pool.submit(confirm)
        for future in futures:future.result()
        assert approval.result()['succeeded']==1
    worker.drain_tasks();worker.reconcile_approvals()
    sid=summary.listing('huaxing',{})['items'][0]['id']
    value=reader.detail('huaxing',sid)
    assert value['qc']['remark']=='并发审核' and value['business']['status']=='linked'
    assert stats.query('huaxing',{})['totals']['total']==1


def test_task_source_evidence_query_failure_does_not_rollback_inspection_task(db,monkeypatch):
    from sqlalchemy.exc import OperationalError
    line=source(db)
    def failed(*args,**kwargs):raise OperationalError('source reference read unavailable',{},None)
    monkeypatch.setattr(dossier,'snapshot',failed)
    task=push(db,line)
    assert task['id'] and entry(db,task)['sourceId']==line.id
    with wf.store() as c:assert c.execute('SELECT count(*) FROM dossier_outbox').fetchone()[0]==0
    with dossier.connect() as c:assert c.execute('SELECT count(*) FROM dossier_links').fetchone()[0]==0


def test_collection_state_distinguishes_disabled_pending_ready_and_failure(db, monkeypatch):
    from sqlalchemy.orm import Session
    line=source(db);_,_,sid=approve(db,line)
    assert reader.detail('huaxing',sid)['business']['collection']['status']=='pending'
    result=worker.cycle(lambda:Session(db.get_bind()))
    assert result['sources']==1 and not result['pendingSales']
    assert reader.detail('huaxing',sid)['business']['collection']['status']=='ready'
    monkeypatch.setattr(worker,'reconcile_sources',lambda db:(_ for _ in ()).throw(RuntimeError('private data must not leak')))
    with pytest.raises(RuntimeError):worker.cycle(lambda:Session(db.get_bind()))
    value=reader.detail('huaxing',sid)
    assert value['business']['collection']['status']=='failed'
    assert 'private data' not in json.dumps(value)
    assert value['business']['frozen'] is not None
    monkeypatch.setattr(dossier.settings,'qc_dossier_enabled',False)
    value=reader.detail('huaxing',sid)
    assert value['business']['collection']['status']=='disabled'
    assert value['business']['frozen'] is not None


def test_emergency_setting_disables_collector_without_deleting_archives():
    from app.core.config import Settings
    config=Settings(_env_file=None,qc_dossier_enabled=True,qc_dossier_emergency_disabled=True)
    assert config.qc_dossier_enabled is False


def test_collection_status_hides_other_factory_totals_and_reports_stale_worker(db):
    line=source(db);_,_,sid=approve(db,line)
    worker.record_state('collection',{'status':'ready','sources':999,'tasks':55,'stage':'complete'})
    value=reader.detail('huaxing',sid)['business']['collection']
    assert 'sources' not in value and 'tasks' not in value
    with dossier.connect(True) as conn:
        conn.execute("UPDATE dossier_worker_state SET updated_at='2000-01-01T00:00:00+00:00' WHERE key='collection'")
    assert reader.detail('huaxing',sid)['business']['collection']['status']=='failed'
