"""At-least-once delivery and reconciliation; only this worker repairs associations."""
import asyncio
import json
import logging
import sqlite3
from uuid import uuid4
from sqlalchemy import select
from app.core.config import settings
from app.models.customer_order_ledger import OrderLedgerLine
from app.models.qc_dossier import QcDossierOutbox
from app.services import qc_dossier as archive

log=logging.getLogger(__name__)


def drain_sales(db,limit=100):
    done=0
    events=db.scalars(select(QcDossierOutbox).where(QcDossierOutbox.delivered_at=='',QcDossierOutbox.factory.in_(archive.factories())).order_by(QcDossierOutbox.attempts,QcDossierOutbox.created_at,QcDossierOutbox.id).limit(limit)).all()
    for event in events:
        try:
            with archive.connect(True) as conn:
                archive.capture(conn,event.payload,event.created_at,'sales:'+event.id)
            event.delivered_at=archive.now();event.last_error='';done+=1
        except (sqlite3.Error,ValueError,KeyError,TypeError):
            # Do not persist driver errors containing payloads, paths or credentials.
            event.last_error='资料保存失败，保留原事件等待重试'
            log.warning('qc_dossier_delivery_failed event=%s',event.id)
        event.attempts+=1
        db.commit()
    return done


def reconcile_sources(db):
    """Full paged reconciliation includes all authorised customers/statuses, not UI filters."""
    count=0;failed=0;after='';run=uuid4().hex
    while True:
        rows=db.scalars(select(OrderLedgerLine).where(OrderLedgerLine.factory_id.in_(archive.factories()),OrderLedgerLine.id>after).order_by(OrderLedgerLine.id).limit(100)).all()
        if not rows:break
        for line in rows:
            try:
                payload=archive.snapshot(db,line)
                with archive.connect(True) as conn:
                    archive.capture(conn,payload,archive.now(),'reconcile:'+run+':'+line.id,'reconcile')
                count+=1
            except (sqlite3.Error,ValueError,KeyError,TypeError):
                failed+=1
                log.warning('qc_dossier_reconcile_failed source=%s',line.id)
        record_state('collection',{'status':'collecting','stage':'sources','sources':count,'failed':failed})
        after=rows[-1].id
        # Bound SQL identity-map and read transaction lifetime between batches.
        db.rollback()
    if failed:raise RuntimeError(f'QC source reconciliation incomplete: {failed} records')
    return count


def drain_tasks():
    target=archive.workflow_path()
    if not target.exists():return 0
    delivered=0
    with sqlite3.connect(target.as_uri()+'?mode=rw',uri=True,timeout=.25) as workflow:
        workflow.row_factory=sqlite3.Row
        tables={r[0] for r in workflow.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'dossier_outbox' not in tables:return 0
        events=workflow.execute("SELECT * FROM dossier_outbox WHERE delivered_at='' ORDER BY attempts,observed_at,id LIMIT 100").fetchall()
        for event in events:
            if event['factory'] not in archive.factories():continue
            try:
                payload=json.loads(event['payload'])
                if payload['record']['factory_id']!=event['factory'] or payload['record']['id']!=event['source_id']:
                    raise ValueError('task envelope mismatch')
                with archive.connect(True) as conn:
                    identity=archive.capture(conn,payload,event['observed_at'],event['id'],'task-source')
                    archive.link(conn,event_key=event['id'],factory=event['factory'],source_id=event['source_id'],task_id=event['task_id'],capture_id=identity,phase='task',status='linked',evidence={'method':'task-transaction-outbox'},event_at=event['observed_at'])
                workflow.execute('UPDATE dossier_outbox SET delivered_at=?,attempts=attempts+1,last_error=\'\' WHERE id=?',(archive.now(),event['id']))
                delivered+=1
            except (sqlite3.Error,ValueError,KeyError,TypeError):
                workflow.execute("UPDATE dossier_outbox SET attempts=attempts+1,last_error='资料关联失败，等待重试' WHERE id=?",(event['id'],))
            workflow.commit()
    return delivered


def reconcile_approvals(limit=100):
    """changes is the existing durable approval outbox. Never alter it or its snapshot.

    Late deliveries retain original observation timestamps. Only evidence actually
    observed before that approval, matching its captured source contract, can link.
    """
    count=0
    with archive.connect(True) as conn:
        tables={r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {'entries','changes'}<=tables:return 0
        # Rotate across missing historical evidence; old gaps must not starve new approvals.
        cursor=conn.execute("SELECT value FROM dossier_worker_state WHERE key='approval_cursor'").fetchone()
        after=int(cursor[0]) if cursor else 0
        query="SELECT c.*,e.factory FROM changes c JOIN entries e ON e.id=c.entry_id LEFT JOIN dossier_links l ON l.event_key='approval:'||c.id WHERE c.action='confirm' AND (l.event_key IS NULL OR l.status<>'linked') AND c.id>? ORDER BY c.id LIMIT ?"
        events=conn.execute(query,(after,limit)).fetchall()
        if not events and after:events=conn.execute(query,(0,limit)).fetchall()
        conn.execute('INSERT INTO dossier_worker_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at',('approval_cursor',str(events[-1]['id'] if events else 0),archive.now()))
        for event in events:
            if event['factory'] not in archive.factories():continue
            item=json.loads(event['snapshot']);src=item.get('sourceRecord') or {}
            source=src.get('id');factory=event['factory']
            candidates=[]
            if source and src.get('factory')==factory:
                for row in conn.execute('SELECT DISTINCT c.* FROM source_captures c JOIN source_observations o ON o.capture_id=c.id WHERE c.factory=? AND c.source_id=? AND c.source_version=? AND c.source_revision=? AND o.observed_at<=?',(factory,source,src.get('sourceVersion'),src.get('sourceRevision'),event['created_at'])):
                    payload=json.loads(row['payload'])
                    if archive.digest(payload)!=row['payload_hash']:continue
                    projection=payload['legacyProjection']
                    if all(src.get(k)==v for k,v in projection.items() if k not in {'completion','remark'}):candidates.append(row)
            # The same-transaction task outbox is stronger evidence than a version label.
            # It records the exact business payload observed when this task was created.
            task_link=conn.execute("SELECT capture_id FROM dossier_links WHERE factory=? AND task_id=? AND source_id=? AND phase='task' AND status='linked' AND event_at<=?",(factory,item.get('workflowId',''),source or '',event['created_at'])).fetchone()
            exact=[r for r in candidates if task_link and r['id']==task_link['capture_id']]
            if exact:candidates=exact
            # Without an exact task link, conflicting raw business content is never guessed.
            hashes={archive.digest({'record':json.loads(r['payload'])['record'],'data':json.loads(r['payload'])['data']}) for r in candidates}
            chosen=candidates[0]['id'] if len(hashes)==1 else None
            archive.link(conn,event_key='approval:'+str(event['id']),factory=factory,source_id=source or '',task_id=item.get('workflowId',''),entry_id=event['entry_id'],audit_id=event['id'],capture_id=chosen,phase='approval',status='linked' if chosen else 'ambiguous' if candidates else 'missing',evidence={'method':'task-transaction-outbox' if exact else 'source-contract-and-observation-before-approval','candidateCount':len(candidates),'revision':event['revision']},event_at=event['created_at'])
            count+=1
    return count


def record_state(key, value):
    with archive.connect(True) as conn:
        conn.execute('INSERT INTO dossier_worker_state VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at', (key, archive.dump(value), archive.now()))


def cycle(session_factory):
    record_state('collection', {'status':'collecting','stage':'tasks','sources':0})
    try:
        tasks=drain_tasks()
        approvals=reconcile_approvals()
        with session_factory() as db:
            sales=drain_sales(db)
            sources=reconcile_sources(db)
            pending_sales=db.query(QcDossierOutbox).filter(QcDossierOutbox.factory.in_(archive.factories()),QcDossierOutbox.delivered_at=='').count()
        approvals+=reconcile_approvals()
        with sqlite3.connect(archive.workflow_path().as_uri()+'?mode=ro',uri=True) as conn:
            pending_tasks=sum(r[1] for r in conn.execute("SELECT factory,count(*) FROM dossier_outbox WHERE delivered_at='' GROUP BY factory") if r[0] in archive.factories())
        result=dict(sales=sales,sources=sources,tasks=tasks,approvals=approvals,pendingSales=pending_sales,pendingTasks=pending_tasks)
        if pending_sales or pending_tasks:
            record_state('collection',dict(result,status='failed',stage='retry',error='仍有原始事件等待重试'))
            raise RuntimeError('QC dossier pending delivery; retry required')
        record_state('last_success',result)
        record_state('collection',dict(result,status='ready',stage='complete'))
        return result
    except Exception:
        record_state('collection',{'status':'failed','stage':'retry','error':'采集未完成，保留原资料与待重试事件'})
        raise


async def worker():
    from app.db import SessionLocal
    while True:
        try:
            await asyncio.to_thread(cycle,SessionLocal)
        except asyncio.CancelledError:raise
        except Exception:
            # Existing QC reads/writes do not depend on this background task.
            log.error('qc_dossier_worker_failed; pending evidence retained')
        await asyncio.sleep(max(10,settings.qc_dossier_poll_seconds))


def validate_installed(engine):
    """Read-only activation gate, before launching any worker. Never auto-migrate."""
    from sqlalchemy import inspect
    if 'qc_dossier_outbox' not in inspect(engine).get_table_names():
        raise RuntimeError('QC 完整资料采集尚未执行主库 outbox 迁移；请关闭开关或先完成显式迁移。')
    with archive.connect() as conn:
        conn.execute('SELECT event_key FROM dossier_links LIMIT 0')
    with sqlite3.connect(archive.workflow_path().as_uri()+'?mode=ro',uri=True) as conn:
        conn.execute('SELECT id FROM dossier_outbox LIMIT 0')


def recover_retained_events(db):
    """Explicit post-restore replay of retained receipts, including acknowledged ones.

    Never read current orders to reconstruct old facts. Neither source/QC rows nor
    original delivery timestamps are rewritten. Safe to repeat after interruption.
    """
    sales=tasks=0;after=''
    while True:
        events=db.scalars(select(QcDossierOutbox).where(QcDossierOutbox.factory.in_(archive.factories()),QcDossierOutbox.id>after).order_by(QcDossierOutbox.id).limit(100)).all()
        if not events:break
        for event in events:
            with archive.connect(True) as conn:archive.capture(conn,event.payload,event.created_at,'sales:'+event.id)
            sales+=1
        after=events[-1].id
        db.rollback()
    with sqlite3.connect(archive.workflow_path().as_uri()+'?mode=ro',uri=True) as workflow:
        workflow.row_factory=sqlite3.Row;after=''
        while True:
            events=workflow.execute('SELECT * FROM dossier_outbox WHERE id>? ORDER BY id LIMIT 100',(after,)).fetchall()
            if not events:break
            for event in events:
                if event['factory'] not in archive.factories():continue
                payload=json.loads(event['payload'])
                if payload['record']['factory_id']!=event['factory'] or payload['record']['id']!=event['source_id']:raise ValueError('task envelope mismatch')
                with archive.connect(True) as conn:
                    identity=archive.capture(conn,payload,event['observed_at'],event['id'],'task-source')
                    archive.link(conn,event_key=event['id'],factory=event['factory'],source_id=event['source_id'],task_id=event['task_id'],capture_id=identity,phase='task',status='linked',evidence={'method':'task-transaction-outbox'},event_at=event['observed_at'])
                tasks+=1
            after=events[-1]['id']
    return dict(sales=sales,tasks=tasks)
