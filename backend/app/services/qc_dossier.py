"""Independent, immutable Sales evidence. No read path initializes this schema."""
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
import json
import re
import sqlite3

from sqlalchemy import select
from app.core.config import settings
from app.models.customer_order_ledger import OrderLedgerLineSource, OrderLedgerSource

SYSTEM = 'sales.customer-order-ledger.schedule'
VERSION = 1
# Never archive credentials or attachment bodies. Unknown BUSINESS keys survive.
SECRET = re.compile(r'password|passwd|secret|token|credential|authorization|cookie|private.?key|access.?key|(?:^|_)blob$|file_content|attachment_content', re.I)
SCHEMA = '''
CREATE TABLE IF NOT EXISTS qc_dossier_schema(version INTEGER PRIMARY KEY);
INSERT OR IGNORE INTO qc_dossier_schema VALUES(1);
CREATE TABLE IF NOT EXISTS source_captures(
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, source_system TEXT NOT NULL, source_id TEXT NOT NULL,
 source_version INTEGER NOT NULL, source_revision INTEGER NOT NULL, payload TEXT NOT NULL,
 payload_hash TEXT NOT NULL, source_updated_at TEXT NOT NULL, captured_at TEXT NOT NULL,
 mapping_version INTEGER NOT NULL, UNIQUE(factory,source_id,payload_hash));
CREATE INDEX IF NOT EXISTS dossier_source_version ON source_captures(factory,source_id,source_revision,source_version);
CREATE TABLE IF NOT EXISTS source_observations(
 event_key TEXT PRIMARY KEY, factory TEXT NOT NULL, source_id TEXT NOT NULL, capture_id TEXT NOT NULL REFERENCES source_captures(id),
 observed_at TEXT NOT NULL, kind TEXT NOT NULL, changed INTEGER NOT NULL, warning TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dossier_observed_source ON source_observations(factory,source_id,observed_at);
CREATE TABLE IF NOT EXISTS source_heads(
 factory TEXT NOT NULL, source_id TEXT NOT NULL, capture_id TEXT NOT NULL REFERENCES source_captures(id),
 observed_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, PRIMARY KEY(factory,source_id));
CREATE TABLE IF NOT EXISTS dossier_links(
 event_key TEXT PRIMARY KEY, factory TEXT NOT NULL, source_id TEXT NOT NULL, task_id TEXT NOT NULL,
 entry_id TEXT NOT NULL, audit_id INTEGER, capture_id TEXT REFERENCES source_captures(id),
 phase TEXT NOT NULL, status TEXT NOT NULL, evidence TEXT NOT NULL, event_at TEXT NOT NULL, linked_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dossier_entry_links ON dossier_links(factory,entry_id,audit_id);
CREATE INDEX IF NOT EXISTS dossier_task_links ON dossier_links(factory,task_id);
CREATE TABLE IF NOT EXISTS dossier_events(
 event_key TEXT PRIMARY KEY, factory TEXT NOT NULL, source_id TEXT NOT NULL, entry_id TEXT NOT NULL,
 at TEXT NOT NULL, kind TEXT NOT NULL, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS dossier_events_source ON dossier_events(factory,source_id,at);
CREATE TABLE IF NOT EXISTS dossier_worker_state(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
'''
TASK_SCHEMA = '''CREATE TABLE IF NOT EXISTS dossier_outbox(
 id TEXT PRIMARY KEY,factory TEXT NOT NULL,task_id TEXT NOT NULL,source_id TEXT NOT NULL,
 payload TEXT NOT NULL,observed_at TEXT NOT NULL,delivered_at TEXT NOT NULL DEFAULT '',
 attempts INTEGER NOT NULL DEFAULT 0,last_error TEXT NOT NULL DEFAULT '');
CREATE INDEX IF NOT EXISTS dossier_task_pending ON dossier_outbox(delivered_at,id);'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(dump(value).encode()).hexdigest()


def capture_identity(factory, source, fingerprint):
    return sha256((factory+'\0'+source+'\0'+fingerprint).encode()).hexdigest()


def factories():
    allowed = {'huaxing','huadeng','huakang-a','huakang-b','huakang-c','huakang-d'}
    return set(settings.qc_dossier_factories.split(',')) & allowed


def enabled(factory):
    return settings.qc_dossier_enabled and factory in factories()


def path():
    return Path(settings.qc_department_data_dir).resolve() / '_inspection_sheet' / 'inspections.sqlite3'


def workflow_path():
    return Path(settings.qc_department_data_dir).resolve() / '_workflow' / 'workflow.sqlite3'


def archive_value(value):
    if isinstance(value, dict):
        return {k: archive_value(v) for k,v in value.items() if not SECRET.search(k)}
    if isinstance(value, list):
        return [archive_value(v) for v in value]
    if isinstance(value, Decimal):
        return format(value, 'f')
    if isinstance(value, (bytes, bytearray)):
        raise ValueError('附件内容不能进入业务资料 JSON')
    return value


def snapshot(db, line):
    """Same-transaction source read; never fetch a later value to repair an event."""
    from app.services.qc_workflow import source_row
    fields = ('id','factory_id','customer_code','customer_name','identity_key','reference_no','product_no',
              'quantity','shipped_quantity','status','version','revision','created_at','updated_at')
    record = {k: archive_value(getattr(line,k)) for k in fields}
    # SQL Numeric(18,4) has one canonical representation before and after reload.
    for field in ('quantity','shipped_quantity'):
        value=getattr(line,field)
        if value is not None:record[field]=format(Decimal(value).quantize(Decimal('0.0001')),'f')
    data = archive_value(line.data)
    refs = [dict(id=r.id, file_name=r.file_name, sha256=r.sha256, kind=r.kind) for r in db.execute(
        select(OrderLedgerSource.id,OrderLedgerSource.file_name,OrderLedgerSource.sha256,OrderLedgerSource.kind)
        .join(OrderLedgerLineSource,OrderLedgerLineSource.source_id==OrderLedgerSource.id)
        .where(OrderLedgerLineSource.line_id==line.id,OrderLedgerSource.factory_id==line.factory_id)
        .order_by(OrderLedgerSource.id))]
    return dict(schemaVersion=VERSION, sourceSystem=SYSTEM, record=record, data=data,
                sources=refs, legacyProjection=source_row(line))


def validate(payload):
    r=payload['record']
    if (payload.get('schemaVersion')!=VERSION or payload.get('sourceSystem')!=SYSTEM
        or r['factory_id'] not in factories() or not isinstance(r['id'],str)
        or type(r['revision']) is not int or type(r['version']) is not int
        or not isinstance(payload['data'],dict)):
        raise ValueError('业务资料身份或结构无效')
    # Fingerprints include exact JSON types and key presence.
    dump(payload)
    return r


def migrate():
    """Explicit additive migration; called by the maintenance command, never GET/worker."""
    for target, schema in ((path(), SCHEMA),(workflow_path(),TASK_SCHEMA)):
        target.parent.mkdir(parents=True,exist_ok=True)
        with sqlite3.connect(target,timeout=5) as conn:
            guards=''
            if target==path():
                for table in ('source_captures','source_observations','dossier_events'):
                    for action in ('UPDATE','DELETE'):
                        guards+=f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable dossier evidence'); END;\n"
            conn.executescript('BEGIN IMMEDIATE;\n'+schema+guards+'\nCOMMIT;')


@contextmanager
def connect(write=False):
    # URI rw/ro both refuse to create missing files. Short timeout protects QC writers.
    conn=sqlite3.connect(path().as_uri()+('?mode=rw' if write else '?mode=ro'),uri=True,timeout=.25)
    conn.row_factory=sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        if not write: conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        if conn.execute('SELECT version FROM qc_dossier_schema').fetchone()[0]!=VERSION:
            raise ValueError('资料结构版本不匹配')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def capture(conn,payload,observed_at,event_key,kind='source-change'):
    r=validate(payload);factory,source=r['factory_id'],r['id'];fingerprint=digest(payload)
    identity=capture_identity(factory,source,fingerprint)
    receipt=conn.execute('SELECT capture_id FROM source_observations WHERE event_key=?',(event_key,)).fetchone()
    if receipt:
        if receipt[0]!=identity: raise ValueError('资料事件编号与内容不一致')
        return identity
    old=conn.execute('SELECT c.*,h.observed_at FROM source_heads h JOIN source_captures c ON c.id=h.capture_id WHERE h.factory=? AND h.source_id=?',(factory,source)).fetchone()
    existed=conn.execute('SELECT 1 FROM source_captures WHERE id=?',(identity,)).fetchone()
    warning=''
    if conn.execute('SELECT 1 FROM source_captures WHERE factory=? AND source_id=? AND source_version=? AND source_revision=? AND payload_hash<>?',(factory,source,r['version'],r['revision'],fingerprint)).fetchone():
        warning='同一业务版本存在不同资料，请核对来源'
    conn.execute('INSERT OR IGNORE INTO source_captures VALUES(?,?,?,?,?,?,?,?,?,?,?)',
        (identity,factory,SYSTEM,source,r['version'],r['revision'],dump(payload),fingerprint,r['updated_at'],observed_at,VERSION))
    # Reconciliation is a heartbeat when content did not change, not an infinite audit log.
    if kind!='reconcile' or not existed:
        conn.execute('INSERT INTO source_observations VALUES(?,?,?,?,?,?,?,?)',(event_key,factory,source,identity,observed_at,kind,int(bool(old and old['id']!=identity)),warning))
        conn.execute('INSERT OR IGNORE INTO dossier_events VALUES(?,?,?,?,?,?,?)',(event_key,factory,source,'',observed_at,
            '首次观察到业务资料' if not old else '读取到业务资料更新',dump({'captureId':identity,'previousCaptureId':old['id'] if old else None,'warning':warning,'observationKind':kind})))
    order=(r['revision'],r['updated_at'],observed_at)
    if not old or order >= (old['source_revision'],old['source_updated_at'],old['observed_at']):
        conn.execute('INSERT INTO source_heads VALUES(?,?,?,?,?) ON CONFLICT(factory,source_id) DO UPDATE SET capture_id=excluded.capture_id,observed_at=excluded.observed_at,last_seen_at=excluded.last_seen_at',(factory,source,identity,observed_at,now()))
    else:
        conn.execute('UPDATE source_heads SET last_seen_at=? WHERE factory=? AND source_id=?',(now(),factory,source))
    return identity


def queue_task(conn, db, line, task_id, observed_at):
    if line is None or not enabled(line.factory_id):return
    payload=snapshot(db,line)
    conn.execute('INSERT INTO dossier_outbox(id,factory,task_id,source_id,payload,observed_at) VALUES(?,?,?,?,?,?)',
        ('task:'+task_id,line.factory_id,task_id,line.id,dump(payload),observed_at))


def link(conn, *, event_key, factory, source_id, task_id='', entry_id='', audit_id=None,
         capture_id=None, phase, status, evidence, event_at):
    previous=conn.execute('SELECT * FROM dossier_links WHERE event_key=?',(event_key,)).fetchone()
    if previous and previous['status']=='linked':
        if previous['capture_id']!=capture_id:raise ValueError('禁止替换已经确认的资料关联')
        return
    if previous and previous['status']==status and previous['capture_id']==capture_id:return
    conn.execute('INSERT INTO dossier_links VALUES(?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(event_key) DO UPDATE SET capture_id=excluded.capture_id,status=excluded.status,evidence=excluded.evidence,linked_at=excluded.linked_at',
        (event_key,factory,source_id,task_id,entry_id,audit_id,capture_id,phase,status,dump(evidence),event_at,now()))
    conn.execute('INSERT OR IGNORE INTO dossier_events VALUES(?,?,?,?,?,?,?)',
        ('link:'+event_key+':'+status,factory,source_id,entry_id,now(),'资料关联已恢复' if previous and capture_id else '资料已关联' if capture_id else '资料未关联',dump({'phase':phase,'status':status,'eventAt':event_at,'evidence':evidence})))
