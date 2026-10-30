"""QC execution tasks. Authoritative Sales rows are read-only; legacy QC stores are untouched."""
from contextlib import contextmanager
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO, StringIO
from pathlib import Path
from uuid import uuid4
import base64
import csv
import html
import json
import sqlite3
import time
import zipfile

from fastapi import HTTPException
from sqlalchemy import select
from app.core.config import settings
from app.models.customer_order_ledger import OrderLedgerLine

EDITABLE = {'waiting', 'draft', 'returned'}
STATES = {'waiting': '待验货', 'draft': '验货中', 'pending': '待审核', 'returned': '退回修改', 'approved': '已审核'}
METHODS = {'internal': '行验', 'external': '客验'}
RESULTS = {'', 'PASS', 'REJ', 'COND', 'HOLD'}
MAX_FILE = 10 * 1024 * 1024
MAX_TASK_FILES = 100 * 1024 * 1024
SCHEMA = '''
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, source_id TEXT NOT NULL,
 method TEXT NOT NULL, batch TEXT NOT NULL, state TEXT NOT NULL, revision INTEGER NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 UNIQUE(factory,source_id,method,batch));
CREATE INDEX IF NOT EXISTS task_factory ON tasks(factory,state);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL REFERENCES tasks(id),
 action TEXT NOT NULL, actor_id TEXT NOT NULL, actor_name TEXT NOT NULL,
 created_at TEXT NOT NULL, snapshot TEXT NOT NULL, reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
 id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), name TEXT NOT NULL,
 mime TEXT NOT NULL, size INTEGER NOT NULL, digest TEXT NOT NULL, content BLOB NOT NULL,
 caption TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, removed INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS receipts (
 factory TEXT NOT NULL, actor TEXT NOT NULL, request_key TEXT NOT NULL, digest TEXT NOT NULL,
 task_ids TEXT NOT NULL, PRIMARY KEY(factory,actor,request_key));
CREATE TABLE IF NOT EXISTS exports (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, actor TEXT NOT NULL,
 expires INTEGER NOT NULL, content BLOB NOT NULL);
'''


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds')


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


@contextmanager
def store(write=False):
    path = Path(settings.qc_department_data_dir).resolve() / '_workflow' / 'workflow.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def text(value, limit=4000):
    if not isinstance(value, str) or len(value) > limit:
        raise HTTPException(422, '文本字段类型不正确或过长')
    return value.strip()


def number(value, *, positive=False, optional=True):
    if value in ('', None) and optional:
        return None
    if isinstance(value, bool):
        raise HTTPException(422, '数量必须是数字')
    try:
        n = Decimal(str(value))
        if not n.is_finite() or n < 0 or n > Decimal('1000000000000') or (positive and n <= 0) or n.as_tuple().exponent < -4:
            raise ValueError()
        return format(n, 'f')
    except (InvalidOperation, ValueError):
        raise HTTPException(422, '数量需为有效非负数，最多四位小数') from None


def day(value, required=False):
    if value in ('', None) and not required:
        return ''
    if not isinstance(value, str):
        raise HTTPException(422, '日期格式不正确')
    try:
        result = date.fromisoformat(value).isoformat()
        if result != value:
            raise ValueError()
        return result
    except ValueError:
        raise HTTPException(422, '请填写有效的完整日期') from None


def source_date(value):
    try:
        return day(value)
    except HTTPException:
        return ''


def source_row(line):
    data = line.data or {}
    scalar = lambda key: str(data[key]) if isinstance(data.get(key), (str, int, float)) else ''
    planned = source_date(data.get('planned_inspection_date')) or source_date(data.get('inspection_date'))
    return {'id': line.id, 'sourceRevision': line.revision, 'sourceVersion': line.version,
            'factory': line.factory_id, 'customerCode': line.customer_code, 'customer': line.customer_name,
            'poNo': line.reference_no, 'customerPo': scalar('po_no'), 'contractNo': scalar('contract_no'),
            'productNo': line.product_no, 'productName': scalar('product_name_zh') or scalar('product_name_en'),
            'country': scalar('country'), 'quantity': number(line.quantity),
            'unitsPerCarton': scalar('units_per_carton'), 'cartonCount': scalar('carton_count'),
            'production': scalar('production_department'), 'agency': scalar('inspection_agency'),
            'dateFrom': planned, 'dateTo': (source_date(data.get('planned_inspection_date_to')) or planned) if planned else '', 'shipDate': source_date(data.get('requested_ship_date')),
            'shippedQuantity': number(line.shipped_quantity), 'sourceStatus': line.status,
            'sourceNote': scalar('note'), 'completion': '', 'remark': scalar('note')}


def sources(db, factory):
    # A single factory-scoped query avoids duplicating partially shipped rows across Sales sections.
    rows = [source_row(line) for line in db.scalars(select(OrderLedgerLine).where(
        OrderLedgerLine.factory_id == factory).order_by(OrderLedgerLine.id))]
    with store() as conn:
        tasks = [unpack(conn, r, history=False) for r in conn.execute('SELECT * FROM tasks WHERE factory=?', (factory,))]
    by_source = {}
    for task in tasks:
        by_source.setdefault(task['sourceId'], []).append({'id': task['id'], 'method': task['method'],
            'batch': task['batch'], 'state': task['state'], 'revision': task['revision'],
            'result': task['execution'].get('result', '')})
    for row in rows:
        row['tasks'] = by_source.get(row['id'], [])
        row['completion'] = '；'.join(f"{METHODS[t['method']]} {t['batch']}：{'已退回' if t['state'] == 'returned' else STATES[t['state']]}" for t in row['tasks']) or '未推送'

    return {'contract_version': '2', 'factory_id': factory, 'status': 'ready', 'mapping_version': 'qc-task-v1',
            'source': 'sales.customer-order-ledger.schedule', 'source_available': True, 'import_enabled': False,
            'items': rows, 'message': '读取业务部已保存订单；无明确验货日期的订单在推送时确认，不使用走货日期代替。'}


def get(conn, factory, task_id):
    row = conn.execute('SELECT * FROM tasks WHERE factory=? AND id=?', (factory, task_id)).fetchone()
    if row is None:
        raise HTTPException(404, '验货任务不存在')
    return row


def attachments(conn, task_id, removed=False):
    clause = '' if removed else ' AND removed=0'
    return [dict(r) for r in conn.execute('SELECT id,name,mime,size,digest,caption,actor,created_at,removed FROM files WHERE task_id=?'+clause,
                                        (task_id,))]


def unpack(conn, row, history=True):
    task = json.loads(row['payload'])
    task.update(id=row['id'], sourceId=row['source_id'], factory=row['factory'], method=row['method'],
                batch=row['batch'], state=row['state'], revision=row['revision'], createdAt=row['created_at'], updatedAt=row['updated_at'])
    task['attachments'] = attachments(conn, row['id'])
    if history:
        task['history'] = [dict(r) | {'snapshot': json.loads(r['snapshot'])} for r in conn.execute(
            'SELECT id,action,actor_id,actor_name,created_at,snapshot,reason FROM events WHERE task_id=? ORDER BY id', (row['id'],))]
    return task


def event(conn, row, action, actor, reason=''):
    snapshot = unpack(conn, row, history=False)
    conn.execute('INSERT INTO events(task_id,action,actor_id,actor_name,created_at,snapshot,reason) VALUES(?,?,?,?,?,?,?)',
                 (row['id'], action, actor['id'], actor['name'], now(), dump(snapshot), reason))


def revision(row, body):
    if type(body.get('revision')) is not int or row['revision'] != body['revision']:
        raise HTTPException(409, '记录已变化，请刷新核对后再操作；当前填写内容请先保留')


def update(conn, row, payload, state=None):
    conn.execute('UPDATE tasks SET payload=?,state=?,revision=revision+1,updated_at=? WHERE id=?',
                 (dump(payload), state or row['state'], now(), row['id']))
    return get(conn, row['factory'], row['id'])


def source_check(db, factory, snapshot):
    if snapshot.get('kind') in {'manual', 'legacy'}:
        return snapshot, False
    line = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.factory_id == factory, OrderLedgerLine.id == snapshot['id']))
    current = source_row(line) if line else None
    return current, current is None or current['sourceRevision'] != snapshot['sourceRevision'] or current['sourceStatus'] != 'active'


def list_tasks(db, factory):
    with store() as conn:
        tasks = [unpack(conn, row, history=False) for row in conn.execute('SELECT * FROM tasks WHERE factory=? ORDER BY updated_at DESC,id', (factory,))]
    for task in tasks:
        current, changed = source_check(db, factory, task['source'])
        task['sourceChanged'] = changed
        task['currentSource'] = current if changed else None
    return {'items': tasks, 'states': STATES, 'methods': METHODS}


def detail(db, factory, task_id):
    with store() as conn:
        task = unpack(conn, get(conn, factory, task_id))
    current, changed = source_check(db, factory, task['source'])
    return task | {'sourceChanged': changed, 'currentSource': current if changed else None}


def create_tasks(db, factory, body, actor):
    if set(body) != {'requestKey', 'items'} or not isinstance(body['items'], list) or not 1 <= len(body['items']) <= 200:
        raise HTTPException(422, '请选择 1 至 200 条正式排期')
    key = text(body['requestKey'], 100)
    if len(key) < 8:
        raise HTTPException(422, '缺少操作编号')
    digest = sha256(dump(body['items']).encode()).hexdigest()
    with store(True) as conn:
        receipt = conn.execute('SELECT * FROM receipts WHERE factory=? AND actor=? AND request_key=?', (factory, actor['id'], key)).fetchone()
        if receipt:
            if receipt['digest'] != digest:
                raise HTTPException(409, '操作编号已经用于不同内容')
            return {'items': [unpack(conn, get(conn, factory, i)) for i in json.loads(receipt['task_ids'])], 'replayed': True}
        ids = []
        seen = set()
        for item in body['items']:
            if not isinstance(item, dict) or set(item) != {'sourceId','sourceRevision','method','batch','plannedDate','plannedQuantity'}:
                raise HTTPException(422, '推送字段不正确')
            item_id = text(item['sourceId'], 64)
            method, batch = text(item['method'], 20), text(item['batch'], 100)
            if method not in METHODS or not batch:
                raise HTTPException(422, '请确认验货方式及批次／次数标识')
            identity = (item_id, method, batch)
            if identity in seen:
                raise HTTPException(422, '同一订单、方式和批次重复选择')
            seen.add(identity)
            line = db.scalar(select(OrderLedgerLine).where(OrderLedgerLine.factory_id == factory, OrderLedgerLine.id == item['sourceId']))
            if not line:
                raise HTTPException(404, '正式订单不存在；示例不能推送为真实验货')
            src = source_row(line)
            if type(item['sourceRevision']) is not int or src['sourceRevision'] != item['sourceRevision'] or src['sourceStatus'] != 'active':
                raise HTTPException(409, '订单已变更或取消，请重新读取排期')
            plan_date, qty = day(item['plannedDate'], True), number(item['plannedQuantity'], positive=True, optional=False)
            if src['quantity'] is not None and Decimal(qty) > Decimal(src['quantity']):
                raise HTTPException(422, '本次计划验货数量超过订单数量')
            existing = conn.execute('SELECT * FROM tasks WHERE factory=? AND source_id=? AND method=? AND batch=?', (factory, *identity)).fetchone()
            if existing:
                prev = json.loads(existing['payload'])
                if (prev['plannedDate'],prev['plannedQuantity'],prev['source']['sourceRevision']) != (plan_date,qty,src['sourceRevision']):
                    raise HTTPException(409, '该批次已存在且安排不同，请查看原任务；分批或重验请使用新批次')
                ids.append(existing['id'])
                continue
            task_id, stamp = uuid4().hex, now()
            payload = {'source': src, 'plannedDate': plan_date, 'plannedQuantity': qty,
                'createdBy': actor, 'execution': {'actualDate':'','actualQuantity':None,'sampleQuantity':None,
                'inspector':'','institution':'','reportNo':'','reportMissingReason':'','result':'','remark':'',
                'defects':[], 'measurements':[], 'resultExplanation':''}}
            conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)', (task_id,factory,src['id'],method,batch,'waiting',1,dump(payload),stamp,stamp))
            event(conn,get(conn,factory,task_id),'create',actor)
            ids.append(task_id)
        conn.execute('INSERT INTO receipts VALUES(?,?,?,?,?)', (factory,actor['id'],key,digest,dump(ids)))
        return {'items':[unpack(conn,get(conn,factory,i)) for i in ids], 'replayed':False}



# Extra legacy fields are stored alongside execution, never written back over the
# original record. Keeping full structured measurements avoids a lossy migration.
def clean_record(raw):
    if not isinstance(raw, dict) or len(dump(raw).encode()) > 256 * 1024:
        raise HTTPException(422, '记录资料格式不正确或过大')
    allowed = {'date','inspDate','supplier','client','processType','productNo','productName',
        'deliveryNo','orderNo','type','qty','sampleQty','pass','fail','defectRate','result',
        'aqlLevel','defect','qc','remark','defects','measurements'}
    if set(raw) - allowed:
        raise HTTPException(422, '记录包含未知字段')
    for k in allowed - {'qty','sampleQty','pass','fail','defects','measurements'}:
        if k in raw and not (k in {'date','inspDate'} and raw[k] is None): text(raw[k], 4000)
    for k in {'qty','sampleQty','pass','fail'}:
        if k in raw: number(raw[k])
    for k in {'defects','measurements'}:
        if k in raw and (not isinstance(raw[k], list) or len(raw[k]) > 200):
            raise HTTPException(422, '明细最多 200 行')
    return json.loads(dump(raw))


def record_execution(record):
    fields = {'date','inspDate','supplier','client','processType','productNo','productName',
        'deliveryNo','orderNo','type','qty','sampleQty','pass','fail','defectRate','result',
        'aqlLevel','defect','qc','remark','defects','measurements'}
    return {'actualDate': source_date(record.get('inspDate')), 'actualQuantity': number(record.get('qty')),
        'sampleQuantity': number(record.get('sampleQty')), 'inspector': record.get('qc') or '',
        'institution':'','reportNo':'','reportMissingReason':'','result':('REJ' if record.get('result')=='FAIL' else record.get('result') or ''),
        'remark':record.get('remark') or '', 'resultExplanation':'',
        'defects':[{'desc':d.get('desc',''),'qty':number(d.get('qty',0)), 'level':d.get('level',''),'remark':d.get('remark','')} for d in record.get('defects',[])],
        'measurements':[{'item':m.get('item',''),'standard':m.get('standard',''),
            'values':dump(m.get('values',[])) if isinstance(m.get('values'),list) else str(m.get('values','')),
            'result':m.get('result',''),'remark':m.get('remark','')} for m in record.get('measurements',[])],
        'record':{k:v for k,v in record.items() if k in fields}}


def bind_inspector(payload, actor):
    """Only the authenticated writer supplies inspector identity; reviews never call this."""
    payload['inspectorAccount'] = {'id': actor['id'], 'name': actor['name']}
    payload['execution']['inspector'] = actor['name']
    if 'record' in payload['execution']:
        payload['execution']['record']['qc'] = actor['name']


def test_entry_allowed(factory, record):
    """Local operator-approved exact snapshots only; no public API can grant this exception."""
    if record.get('status') or record.get('result') or record.get('qc'):
        return False
    path = Path(settings.qc_department_data_dir).resolve() / '_workflow' / 'test-entry-allowlist.json'
    try:
        grants = json.loads(path.read_text())
        expected = grants.get(factory, {}).get(str(record['id']))
        return bool(expected) and expected == sha256(dump(record).encode()).hexdigest()
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return False


def create_entry(factory, body, actor, legacy=None, reference=False):
    expected = {'recordId'} if legacy is not None else {'requestKey','method','execution'}
    if set(body) != expected:
        raise HTTPException(422, '新增记录字段不正确')
    test_entry = legacy is not None and test_entry_allowed(factory, legacy)
    if legacy is not None:
        # Only authoritative server records returned by a supervisor may be edited.
        if legacy.get('status', 'approved') != 'rejected' and not test_entry:
            raise HTTPException(409, '历史记录需先由主管反审核退回')
        identity='legacy-'+str(legacy['id']); method=legacy.get('inspectionMethod') if legacy.get('inspectionMethod') in METHODS else 'internal'
        execution=record_execution(legacy)
    else:
        key=text(body['requestKey'],100)
        if len(key)<8: raise HTTPException(422,'缺少操作编号')
        identity='manual-'+sha256((actor['id']+':'+key).encode()).hexdigest()[:40]
        method=text(body['method'],20)
        if method not in METHODS: raise HTTPException(422,'请选择行验或客验')
        execution=clean_execution(body['execution'])
    r=execution.get('record',{})
    source={'id':identity,'kind':'legacy' if legacy is not None else 'manual','sourceRevision':1,'sourceVersion':1,
        'factory':factory,'sourceStatus':'active','customer':r.get('client',''),'poNo':r.get('orderNo',''),
        'customerPo':'','productNo':r.get('productNo',''),'productName':r.get('productName',''),'quantity':execution['actualQuantity']}
    with store(True) as conn:
        found=conn.execute('SELECT * FROM tasks WHERE factory=? AND source_id=?', (factory,identity)).fetchone()
        if found:
            previous=unpack(conn,found)
            if legacy is None and previous.get('creationDigest') != sha256(dump(body).encode()).hexdigest():
                raise HTTPException(409, '这次新增已保存，请刷新后打开原草稿，不要重复新增')
            return previous
        stamp=now();task_id=uuid4().hex
        payload={'source':source,'plannedDate':'','plannedQuantity':None,'createdBy':actor,'execution':execution,'creationDigest':sha256(dump(body).encode()).hexdigest()}
        if legacy is None or test_entry: bind_inspector(payload, actor)
        if test_entry: payload['testEntry'] = True
        if legacy is not None:
            payload.update(legacyId=legacy['id'],legacyOriginal=legacy,reference=reference or test_entry,
                reviewReason=legacy.get('rejectReason',''),methodConfirmed=legacy.get('inspectionMethod') in METHODS)
        conn.execute('INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)',
            (task_id,factory,identity,method,'历史修订' if legacy is not None else '手工录入',
             'returned' if legacy is not None and not test_entry else 'draft',1,dump(payload),stamp,stamp))
        event(conn,get(conn,factory,task_id),'create',actor)
        return unpack(conn,get(conn,factory,task_id))


def legacy_links(factory):
    with store() as conn:
        return {p['legacyId']:r['id'] for r in conn.execute('SELECT id,payload FROM tasks WHERE factory=?',(factory,))
                if 'legacyId' in (p:=json.loads(r['payload']))}


def clean_execution(raw):
    keys = {'actualDate','actualQuantity','sampleQuantity','inspector','institution','reportNo','reportMissingReason',
            'result','remark','defects','measurements','resultExplanation'}
    if not isinstance(raw,dict) or not keys <= set(raw) or set(raw)-keys-{'record'}:
        raise HTTPException(422, '验货填写字段不正确')
    clean = {k:text(raw[k], 4000 if k in {'remark','resultExplanation','reportMissingReason'} else 255)
             for k in keys-{'actualDate','actualQuantity','sampleQuantity','defects','measurements'}}
    if clean['result'] not in RESULTS:
        raise HTTPException(422, '请选择有效检验判定')
    clean.update(actualDate=day(raw['actualDate']),actualQuantity=number(raw['actualQuantity']),sampleQuantity=number(raw['sampleQuantity']))
    for key in ['defects','measurements']:
        if not isinstance(raw[key],list) or len(raw[key]) > 200:
            raise HTTPException(422, '明细最多 200 行')
        clean[key]=[]
        for row in raw[key]:
            expected = {'desc','qty','level','remark'} if key=='defects' else {'item','standard','values','result','remark'}
            if not isinstance(row,dict) or set(row)!=expected:
                raise HTTPException(422, '明细字段不正确')
            item={k:(number(v,optional=False) if k=='qty' else text(v,1000)) for k,v in row.items()}
            if key=='defects' and (not item['desc'] or item['level'] not in {'CR','MAJ 0.65','MAJ 1.0','MIN 2.5',''}):
                raise HTTPException(422, '请填写不良描述和有效等级')
            if key=='measurements' and (not item['item'] or item['result'] not in {'','PASS','FAIL','NA'}):
                raise HTTPException(422, '请填写测量项目和有效结果')
            clean[key].append(item)
    if 'record' in raw:
        clean['record'] = clean_record(raw['record'])
    return clean


def warnings(execution):
    notes=[]
    if execution['result']=='PASS' and any(m['result']=='FAIL' for m in execution['measurements']):
        notes.append('测量含 FAIL，但最终结论为 PASS；请核对原报告并说明')
    sample=execution['sampleQuantity']
    failures=sum(Decimal(d['qty']) for d in execution['defects'])
    if sample is not None and failures>Decimal(sample):
        notes.append('不良项数量合计超过抽查数量，可能包含一件多个问题，请说明统计口径')
    if sample is not None and execution['actualQuantity'] is not None and Decimal(sample)>Decimal(execution['actualQuantity']):
        notes.append('抽查数量超过实际验货数量，请核对并说明')
    return notes


def act(db, factory, task_id, action, body, actor):
    with store(True) as conn:
        row=get(conn,factory,task_id);revision(row,body);payload=json.loads(row['payload'])
        reason=text(body.get('reason',''))
        if action=='save':
            if not {'revision','execution'} <= set(body) or set(body)-{'revision','execution','method'} or row['state'] not in EDITABLE:
                raise HTTPException(409,'记录已提交并锁定，主管退回后才可修改')
            if 'method' in body:
                if payload['source'].get('kind') not in {'manual','legacy'} or body['method'] not in METHODS:
                    raise HTTPException(422,'请选择有效验货方式；排期任务的方式不能在表单中改写')
                conn.execute('UPDATE tasks SET method=? WHERE id=?',(body['method'],task_id))
                payload['methodConfirmed']=True
            payload['execution']=clean_execution(body['execution']);payload['lastEditedBy']=actor
            bind_inspector(payload, actor)
            e=payload['execution']
            if 'record' in e:
                e['record'].update(inspDate=e['actualDate'],qty=e['actualQuantity'],sampleQty=e['sampleQuantity'],
                    qc=e['inspector'],result=e['result'],remark=e['remark'])
            row=update(conn,row,payload,'draft')
        elif action=='submit':
            if set(body)!={'revision'} or row['state'] not in EDITABLE:
                raise HTTPException(409,'当前状态不能提交')
            bind_inspector(payload, actor)
            e=payload['execution']
            if payload.get('methodConfirmed') is False: raise HTTPException(422,'请确认本条历史记录是行验还是客验')
            if not e['actualDate'] or not e['inspector'] or not e['result'] or e['actualQuantity'] is None or Decimal(e['actualQuantity'])<=0:
                raise HTTPException(422,'请填写实际检验日期、实际验货数量、检验人员和最终判定')
            _,changed=source_check(db,factory,payload['source'])
            if changed:
                raise HTTPException(409,'来源订单已变化或取消，请先核对来源并填写变更说明')
            if (warnings(e) or e['result'] in {'COND','HOLD'}) and not e['resultExplanation']:
                raise HTTPException(422,'请填写判定／数量差异说明')
            if row['method']=='external' and not attachments(conn,task_id) and not e['reportMissingReason']:
                raise HTTPException(422,'客验请附原报告；暂缺时需填写报告缺失说明供主管审核')
            payload['submittedBy']=actor;payload['submittedAt']=now()
            row=update(conn,row,payload,'pending')
        elif action in {'approve','return','reopen'}:
            expected='approved' if action=='reopen' else 'pending'
            if set(body)!={'revision','reason'} or row['state']!=expected:
                raise HTTPException(409,'当前状态不能执行此审核操作')
            if action!='approve' and not reason:
                raise HTTPException(422,'请填写退回原因')
            if action=='approve':
                _,changed=source_check(db,factory,payload['source'])
                if changed:
                    raise HTTPException(409,'提交后来源订单已变化，请退回核对')
            payload['reviewedBy']=actor;payload['reviewedAt']=now();payload['reviewReason']=reason
            row=update(conn,row,payload,'approved' if action=='approve' else 'returned')
        elif action=='ack-source':
            if set(body)!={'revision','reason','sourceRevision'} or row['state'] not in EDITABLE or not reason:
                raise HTTPException(422,'只能在可编辑状态核对来源，并需填写原因')
            current,_=source_check(db,factory,payload['source'])
            if not current or current['sourceStatus']!='active' or current['sourceRevision']!=body['sourceRevision']:
                raise HTTPException(409,'来源已取消、不存在或再次变化；请联系业务部核对')
            payload['source']=current
            row=update(conn,row,payload)
        else:
            raise HTTPException(404,'未知操作')
        event(conn,row,action,actor,reason)
        return unpack(conn,row)


def add_file(factory, task_id, body, actor):
    if set(body)!={'revision','name','content','caption'}:
        raise HTTPException(422,'附件字段不正确')
    name=text(body['name'],255)
    if not name or any(c in name for c in ('/','\\','\x00','\r','\n')):
        raise HTTPException(422,'文件名不正确')
    try:
        content=base64.b64decode(body['content'],validate=True)
    except (ValueError,TypeError):
        raise HTTPException(422,'附件内容不正确') from None
    if not content or len(content)>MAX_FILE:
        raise HTTPException(413,'单个附件必须小于等于 10 MB')
    suffix=Path(name).suffix.lower(); mime=''
    if suffix=='.pdf' and content.startswith(b'%PDF-'):
        mime='application/pdf'
    elif suffix in {'.png','.jpg','.jpeg','.webp'}:
        from PIL import Image, UnidentifiedImageError
        try:
            with Image.open(BytesIO(content)) as im:
                if im.width*im.height>40_000_000:
                    raise ValueError()
                actual=im.format;im.verify()
            mime={'PNG':'image/png','JPEG':'image/jpeg','WEBP':'image/webp'}[actual]
            if suffix not in {'PNG':{'.png'},'JPEG':{'.jpg','.jpeg'},'WEBP':{'.webp'}}[actual]:
                raise ValueError()
        except (UnidentifiedImageError,ValueError,KeyError,OSError,Image.DecompressionBombError):
            raise HTTPException(422,'图片损坏或格式与文件名不一致') from None
    if not mime:
        raise HTTPException(422,'支持真实 JPG、PNG、WebP 图片和 PDF 报告')
    with store(True) as conn:
        row=get(conn,factory,task_id);revision(row,body)
        if row['state'] not in EDITABLE:
            raise HTTPException(409,'已提交记录的附件已锁定')
        count,total=conn.execute('SELECT count(*),coalesce(sum(size),0) FROM files WHERE task_id=?', (task_id,)).fetchone()
        if count>=50 or total+len(content)>MAX_TASK_FILES:
            raise HTTPException(413,'本次验货附件含历史版本上限为 50 个、100 MB')
        digest = sha256(content).hexdigest()
        duplicate = conn.execute('SELECT id FROM files WHERE task_id=? AND name=? AND digest=? AND caption=? AND removed=0', (task_id,name,digest,text(body['caption'],1000))).fetchone()
        if duplicate:
            return unpack(conn,row)
        conn.execute('INSERT INTO files VALUES(?,?,?,?,?,?,?,?,?,?,0)', (uuid4().hex,task_id,name,mime,len(content),sha256(content).hexdigest(),content,text(body['caption'],1000),actor['name'],now()))
        row=update(conn,row,json.loads(row['payload']),'draft')
        event(conn,row,'attach',actor)
        return unpack(conn,row)


def remove_file(factory, task_id, file_id, body, actor):
    if set(body)!={'revision'}:
        raise HTTPException(422,'字段不正确')
    with store(True) as conn:
        row=get(conn,factory,task_id);revision(row,body)
        if row['state'] not in EDITABLE:
            raise HTTPException(409,'已提交记录的附件已锁定')
        found=conn.execute('SELECT id FROM files WHERE id=? AND task_id=? AND removed=0',(file_id,task_id)).fetchone()
        if not found:
            raise HTTPException(404,'附件不存在')
        conn.execute('UPDATE files SET removed=1 WHERE id=?',(file_id,))
        row=update(conn,row,json.loads(row['payload']))
        event(conn,row,'remove-attachment',actor,file_id)
        return unpack(conn,row)


def read_file(factory, task_id, file_id):
    with store() as conn:
        get(conn,factory,task_id)
        row=conn.execute('SELECT * FROM files WHERE task_id=? AND id=?',(task_id,file_id)).fetchone()
        if not row:
            raise HTTPException(404,'附件不存在')
        return dict(row)


def ledger_records(db,factory,approved_only=False):
    rows=[]
    for t in list_tasks(db,factory)['items']:
        if approved_only and t['state']!='approved':continue
        plan_source = (t.get('currentSource') or t['source']) if t['source'].get('kind') not in {'manual','legacy'} else {}
        e,s=t['execution'],t['source'];sample=float(e['sampleQuantity']) if e['sampleQuantity'] is not None else None
        fail=sum(float(d['qty']) for d in e['defects'])
        r=dict(e.get('record',{}))
        r.update({'id':'wf-'+t['id'],'workflowId':t['id'],'legacyId':t.get('legacyId'),
            'inspectionPlan':{'from':plan_source.get('dateFrom',''),'to':plan_source.get('dateTo') or plan_source.get('dateFrom','')},
            'reference':t.get('reference',False),'date':r.get('date',e['actualDate']),'inspDate':e['actualDate'],
            'supplier':r.get('supplier',''),'client':r.get('client',s['customer']),
            'productNo':r.get('productNo',s['productNo']),'productName':r.get('productName',s['productName']),
            'orderNo':r.get('orderNo',s['poNo']),'type':r.get('type',''),
            'qty':float(e['actualQuantity']) if e['actualQuantity'] is not None else None,'sampleQty':sample,'fail':r.get('fail',fail),
            'pass':r.get('pass',max(0,(sample or 0)-fail)),
            'defectRate':r.get('defectRate',f'{fail/sample*100:.2f}%' if sample else ''),
            'result':e['result'],'qc':e['inspector'],'remark':e['remark'],
            'defect':r.get('defect','；'.join(d['desc'] for d in e['defects'])),
            'defects':r.get('defects',e['defects']),'measurements':r.get('measurements',e['measurements']),
            'status':{'waiting':'waiting','draft':'draft','pending':'pending','returned':'rejected','approved':'approved'}[t['state']],'inspectionMethod':t['method'],'updatedAt':t['updatedAt']})
        rows.append(r)
    return rows


def projections(db,factory):
    return ledger_records(db,factory,approved_only=True)


def export_packet(db,factory,body):
    if set(body)!={'ids','formal'} or type(body['formal']) is not bool or not isinstance(body['ids'],list) or not 1<=len(body['ids'])<=200 or any(not isinstance(i,str) or len(i)>64 for i in body['ids']) or len(set(body['ids']))!=len(body['ids']):
        raise HTTPException(422,'请选择 1 至 200 条记录导出')
    with store() as conn:
        tasks=[unpack(conn,get(conn,factory,i)) for i in body['ids']]
        if body['formal'] and any(t['state']!='approved' for t in tasks):
            raise HTTPException(409,'正式资料包只能包含已审核记录')
        total=0
        for task in tasks:
            total+=conn.execute('SELECT coalesce(sum(size),0) FROM files WHERE task_id=?',(task['id'],)).fetchone()[0]
        if total>200*1024*1024:
            raise HTTPException(413,'附件总量超过 200 MB，请分批导出')
        output=BytesIO(); table=StringIO(newline='');writer=csv.writer(table)
        header=['验货编号','客户','PO','客PO','货号','名称','验货方式','批次','状态','计划验货日期','实际检验日期','实际验货数量','抽查数量','结果','检验人员','机构','报告编号','备注','附件数']
        writer.writerow(header)
        safe=lambda v: ("'"+str(v)) if str(v).lstrip().startswith(('=','+','-','@')) else str(v)
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for t in tasks:
                s,e=t['source'],t['execution']
                writer.writerow([safe(v if v is not None else '') for v in [t['id'],s['customer'],s['poNo'],s['customerPo'],s['productNo'],s['productName'],METHODS[t['method']],t['batch'],STATES[t['state']],t['plannedDate'],e['actualDate'],e['actualQuantity'],e['sampleQuantity'],e['result'],e['inspector'],e['institution'],e['reportNo'],e['remark'],len(t['attachments'])]])
                archive.writestr(t['id']+'/完整记录及历史.json',dump(t))
                archive.writestr(t['id']+'/验货资料.html','<!doctype html><meta charset="utf-8"><title>验货资料</title><h1>'+html.escape(s['productNo']+' '+s['productName'])+'</h1><p>'+html.escape(METHODS[t['method']]+' · '+STATES[t['state']])+'</p><pre style="white-space:pre-wrap">'+html.escape(json.dumps(t,ensure_ascii=False,indent=2))+'</pre>')
                for f in conn.execute('SELECT * FROM files WHERE task_id=?',(t['id'],)):
                    archive.writestr(t['id']+'/附件/'+f['id']+'_'+f['name'],f['content'])
            archive.writestr('验货明细.csv','\ufeff'+table.getvalue())
            archive.writestr('汇总口径.txt',f"{'正式已审核资料' if body['formal'] else '工作清单（含过程记录，非正式统计）'}\n验货次数：{len(tasks)}\n来源订单数（去重）：{len({t['sourceId'] for t in tasks})}\n实际验货数量是各次检验覆盖数量，不代表去重货物量或出货量。\n附件含历史保留文件，当前附件以完整记录的 attachments 为准。")
        return output.getvalue()


def prepare_export(db, factory, body, actor):
    content = export_packet(db, factory, body)
    token, stamp = uuid4().hex, int(time.time())
    with store(True) as conn:
        conn.execute('DELETE FROM exports WHERE expires<?', (stamp,))
        total = conn.execute('SELECT coalesce(sum(length(content)),0) FROM exports').fetchone()[0]
        if total + len(content) > 500 * 1024 * 1024:
            raise HTTPException(503, '资料下载缓存繁忙，请稍后重试或减少导出记录')
        conn.execute('INSERT INTO exports VALUES(?,?,?,?,?)', (token,factory,actor,stamp+600,content))
    return {'url':'api/workflow/exports/'+token, 'filename':'QC已审核资料.zip' if body['formal'] else 'QC工作清单.zip'}


def download_export(factory, actor, token):
    with store() as conn:
        row=conn.execute('SELECT content,expires FROM exports WHERE id=? AND factory=? AND actor=?', (token,factory,actor)).fetchone()
        if row is None:
            raise HTTPException(404,'下载不存在')
        if row['expires']<int(time.time()):
            raise HTTPException(410,'下载已过期，请重新导出')
        return row['content']
