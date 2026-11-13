"""Inline inspection journal; additive storage, no writes to Sales or reviewed history."""
import base64
import binascii
from contextlib import contextmanager
from datetime import date
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import re
import sqlite3
from uuid import uuid4
import warnings

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import settings
from app.services import qc_workflow as wf
from app.services import qc_photo_assets as photo_assets
from app.services.qc_inspection_results import RESULTS, EDITABLE_RESULTS, ALLOWED_INSPECTION_RESULTS

# Shared Excel MIME for summary/report downloads.
MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
# Keep the template business fields; the final editing columns follow the requested result / remark / photos order.
COLUMNS = [('date', '日期'), ('customer', '客户'), ('poNo', 'PO#'), ('country', '出口国'),
           ('productNo', '货号'), ('productName', '产品名称'), ('quantity', '数量'),
           ('unitsPerCarton', '装箱'), ('cartonCount', '箱数'), ('production', '生产'),
           ('agency', '机构'), ('customerPo', '客PO#'), ('completion', '完成情况'),
           ('result', '验货结果'), ('remark', '备注'), ('photos', '照片'), ('improvement', '改进措施'), ('submit', '提交')]
SCHEMA = '''
CREATE TABLE IF NOT EXISTS entries (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, source_key TEXT NOT NULL,
 base TEXT NOT NULL, result TEXT NOT NULL CHECK(result IN ('','PASS','FAIL','PENDING','REJ','COND','HOLD','LG')),
 remark TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0, edited INTEGER NOT NULL DEFAULT 0,
 updated_at TEXT NOT NULL, UNIQUE(factory,source_key));
CREATE TABLE IF NOT EXISTS photos (
 id TEXT PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES entries(id), name TEXT NOT NULL,
 content BLOB NOT NULL, digest TEXT NOT NULL, origin TEXT, removed INTEGER NOT NULL DEFAULT 0,
 created_at TEXT NOT NULL, UNIQUE(entry_id,origin));
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY, entry_id TEXT NOT NULL REFERENCES entries(id), revision INTEGER NOT NULL,
 action TEXT NOT NULL, actor TEXT NOT NULL, created_at TEXT NOT NULL, snapshot TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS exports (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, actor TEXT NOT NULL, expires INTEGER NOT NULL, content BLOB NOT NULL);
'''


@contextmanager
def store(write=False, review=False):
    path = Path(settings.qc_department_data_dir).resolve() / '_inspection_sheet' / 'inspections.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    new_files=[]
    file_token=photo_assets.created_files.set(new_files)
    try:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.executescript(SCHEMA + photo_assets.SCHEMA)
        migrate_pending(conn)
        conn.execute("CREATE TABLE IF NOT EXISTS entry_details (entry_id TEXT PRIMARY KEY REFERENCES entries(id), improvement TEXT NOT NULL DEFAULT '', submitted_at TEXT NOT NULL DEFAULT '', submitted_snapshot TEXT NOT NULL DEFAULT '');")
        migrate_review(conn)
        if review:
            from app.services import qc_inspection_summary as summary
            with summary.store():pass
            target=Path(settings.qc_department_data_dir).resolve() / '_summary' / 'summaries.sqlite3'
            conn.execute('ATTACH DATABASE ? AS qsum',(str(target),))
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        for file in new_files:file.unlink(missing_ok=True)
        raise
    finally:
        photo_assets.created_files.reset(file_token)
        conn.close()


REVIEW_FIELDS = {'responsible': ('responsible', 200), 'firstResponsible': ('first_responsible', 200),
    'secondResponsible': ('second_responsible', 200), 'otherRemark': ('other_remark', 20000),
    'inspectionFactory': ('inspection_factory', 200), 'reportStatus': ('report_status', 200), 'customerRequirements': ('customer_requirements', 20000), 'shipDate': ('ship_date', 10),
    'contractNo': ('contract_no', 200), 'customerCode': ('customer_code', 200), 'shippedQuantity': ('shipped_quantity', 32)}
REVIEW_EXECUTION_FIELDS = ('actualDate','actualQuantity','sampleQuantity','inspector','institution','reportNo',
    'reportMissingReason','resultExplanation','defects','measurements')


def clean_review_execution(raw):
    if not isinstance(raw,dict) or set(raw)-set(REVIEW_EXECUTION_FIELDS):
        raise HTTPException(422,'验货补录字段不正确')
    # Reuse existing date, quantity and structured-detail validation. Only supplied
    # fields override the immutable source; result/remark have their own editors.
    defaults={k:[] if k in {'defects','measurements'} else '' for k in REVIEW_EXECUTION_FIELDS}
    clean=wf.clean_execution({**defaults,**raw,'result':'PENDING','remark':''})
    return {k:clean[k] for k in raw}


def migrate_review(conn):
    # Additive migration: old submissions keep flow_version=0 and their original timestamps.
    # Serialize first-open additive DDL across concurrent requests.
    conn.execute('BEGIN IMMEDIATE')
    fields={'flow_version':"INTEGER NOT NULL DEFAULT 0",'review_state':"TEXT NOT NULL DEFAULT ''",
        'inspection_problem':"TEXT DEFAULT NULL",'review_execution':"TEXT DEFAULT NULL",'confirmed_at':"TEXT NOT NULL DEFAULT ''",
        'confirmed_by':"TEXT NOT NULL DEFAULT ''",'approved_snapshot':"TEXT NOT NULL DEFAULT ''",
        'last_actor':"TEXT NOT NULL DEFAULT '{}'",'last_location':"TEXT NOT NULL DEFAULT ''",'last_changed_at':"TEXT NOT NULL DEFAULT ''"}
    fields.update({column: 'TEXT DEFAULT NULL' for column, _ in REVIEW_FIELDS.values()})
    present={r['name'] for r in conn.execute('PRAGMA table_info(entry_details)')}
    for key,ddl in fields.items():
        if key not in present:conn.execute('ALTER TABLE entry_details ADD COLUMN '+key+' '+ddl)
    present={r['name'] for r in conn.execute('PRAGMA table_info(changes)')}
    for key,ddl in {'location':"TEXT NOT NULL DEFAULT ''",'diff':"TEXT NOT NULL DEFAULT '{}'",'request_key':"TEXT NOT NULL DEFAULT ''",'notification_seen_by':"TEXT NOT NULL DEFAULT '{}'"}.items():
        if key not in present:conn.execute('ALTER TABLE changes ADD COLUMN '+key+' '+ddl)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS inspection_request_keys ON changes(entry_id,request_key) WHERE request_key<>''")
    conn.commit()


def scalar(value):
    return '' if value is None else str(value)


def base_fields(source):
    result = {key: source.get(key, '') for key, _ in COLUMNS if key not in {'date', 'remark', 'result', 'photos', 'submit', 'improvement'}}
    start, end = wf.source_date(source.get('dateFrom')), wf.source_date(source.get('dateTo'))
    result.update(dateFrom=start, dateTo=end or start, sourceRevision=source.get('sourceRevision'),
                  sourceNote=scalar(source.get('sourceRemark', source.get('remark', ''))))
    result['sourceRecord'] = {k:v for k,v in source.items() if k not in {'input','tasks'}}
    result['actualDate'] = wf.source_date(source.get('actualDate'))
    for key in ('inspectionProblem','otherRemark','inspectionFactory','reportStatus','responsible','firstResponsible','secondResponsible'):
        if key in source:result[key]=source[key]
    result['referenceData']=bool(source.get('reference'))
    return result


def legacy_fields(factory, record, examples):
    base = base_fields({'customer':record.get('client'), 'poNo':record.get('orderNo'),
        'productNo':record.get('productNo'), 'productName':record.get('productName'),
        'quantity':record.get('qty'), 'remark':record.get('remark'),'actualDate':record.get('inspDate')})
    # Exact saved provenance + allowlisted full snapshot; never join by name or row position.
    match = re.search(r'^来源：[^\n]*；(schedule-example-row-\d+)\s*$', record.get('remark') or '', re.M)
    source = examples.get(match.group(1)) if match and wf.test_entry_allowed(factory, record) else None
    if source and all(scalar(record.get(a)).strip() == scalar(source.get(b)).strip()
                      for a,b in [('client','customer'),('orderNo','poNo'),('productNo','productNo')]):
        base = base_fields(source)
        base['testData'] = True
    base['actualDate']=wf.source_date(record.get('inspDate'))
    base['testData']=bool(base.get('testData') or wf.test_entry_allowed(factory,record))
    return base


def candidates(factory, records, tasks, sources, examples=(), references=()):
    """Use explicit source IDs. Distinct batches and duplicate SKUs remain independent."""
    example_map = {r['id']:r for r in examples}
    source_map = {r['id']:r for r in sources}
    linked = {t['legacyId'] for t in tasks if t.get('legacyId') is not None}
    result = []
    for record in records:
        if record['id'] in linked:
            continue
        base = legacy_fields(factory, record, example_map)
        base['legacyId'] = record['id']
        base['legacyReviewState']=record.get('status','')
        base['legacySubmittedAt']=record.get('submittedAt','')
        base['legacyConfirmedAt']=record.get('reviewAt','')
        base['referenceData']=record['id'] in references
        result.append(('legacy:'+str(record['id']), base, record.get('result',''),
                       base['sourceNote'], []))
    for task in tasks:
        source = source_map.get(task['sourceId'], task['source'])
        base = base_fields(source)
        if task.get('legacyId') is not None:
            base = legacy_fields(factory, task.get('legacyOriginal') or {}, example_map)
            base['legacyId'] = task['legacyId']
        else:
            base['quantity'] = task.get('plannedQuantity') if task.get('plannedQuantity') is not None else base['quantity']
            if not base['dateFrom']:
                base['dateFrom'] = base['dateTo'] = wf.source_date(task.get('plannedDate'))
        base.update(workflowId=task['id'], batch=task['batch'], sourceId=task['sourceId'])
        execution = task['execution']
        if task.get('state') in {'pending','approved','returned'}:
            base['legacyReviewState']=task['state']
            base['legacySubmittedAt']=task.get('submittedAt','')
            base['legacyConfirmedAt']=task.get('approvedAt','')
        base['inspectionExecution']=execution
        base['actualQuantity']=execution.get('actualQuantity')
        base['inspector']=execution.get('inspector','')
        base['actualDate']=wf.source_date(execution.get('actualDate'))
        base['referenceData']=bool(task.get('reference') or task.get('legacyId') in references)
        remark = execution.get('remark','')
        if base.get('testData') and remark == (task.get('legacyOriginal') or {}).get('remark'):
            remark = base['sourceNote']
        base['testData'] = bool(base.get('testData') or task.get('testEntry'))
        key = 'legacy:'+str(task['legacyId']) if task.get('legacyId') is not None else 'workflow:'+task['id']
        result.append((key,base,execution.get('result',''),remark or base['sourceNote'],task['attachments']))
    # Sales schedules enter this journal only through an explicitly created task.
    return result


def get(conn, factory, entry_id):
    row = conn.execute('SELECT * FROM entries WHERE id=? AND factory=?',(entry_id,factory)).fetchone()
    if row is None:
        raise HTTPException(404,'验货任务不存在')
    return row


def reversal_metadata(event):
    snapshot=json.loads(event['snapshot'])
    return {'eventId':event['id'],'entryId':event['entry_id'],'customer':snapshot.get('customer',''),'poNo':snapshot.get('poNo',''),
            'at':event['created_at'],'actor':json.loads(event['actor']),'location':event['location'],
            'reason':json.loads(event['diff']).get('reason','')}


def review_notifications(factory, actor, body=None, *, action):
    """Read unseen audit events for the destination page and authenticated user."""
    destination = {'revoke': 'pending', 'return-to-inspection': 'returned_to_inspection'}[action]
    user=str(actor['id'])
    if body is not None and (set(body)!={'eventIds'} or not isinstance(body['eventIds'],list)
            or any(type(i) is not int or i<1 for i in body['eventIds'])):
        raise HTTPException(422,'通知事件编号不正确')
    with store(body is not None) as conn:
        events = list(conn.execute("""
            SELECT c.* FROM changes c
            JOIN entries e ON e.id=c.entry_id
            JOIN entry_details d ON d.entry_id=e.id
            WHERE e.factory=? AND c.action=? AND d.review_state=?
              AND (c.action='revoke' OR c.id=(
                  SELECT max(previous.id) FROM changes previous
                  WHERE previous.entry_id=c.entry_id AND previous.action=c.action))
            ORDER BY c.id
        """, (factory, action, destination)))
        if body is None:
            items = []
            for event in events:
                if user in json.loads(event['notification_seen_by']):
                    continue
                item = reversal_metadata(event)
                if action == 'return-to-inspection':
                    item['productNo'] = json.loads(event['snapshot']).get('productNo', '')
                items.append(item)
            return {'items': items}
        wanted=set(body['eventIds']);seen=[]
        # Only acknowledgment metadata changes; original event/snapshot stays immutable.
        for event in events:
            if event['id'] not in wanted:continue
            users=json.loads(event['notification_seen_by'])
            users.setdefault(user,wf.now())
            conn.execute('UPDATE changes SET notification_seen_by=? WHERE id=?',(wf.dump(users),event['id']))
            seen.append(event['id'])
        return {'shown':seen}


def reversal_notifications(factory, actor, body=None):
    return review_notifications(factory, actor, body, action='revoke')


def unpack(conn, row, include_photos=True):
    photos = [dict(f) for f in conn.execute('SELECT id,name FROM photos WHERE entry_id=? AND removed=0 ORDER BY created_at,id',(row['id'],))] if include_photos else []
    extension=conn.execute('SELECT * FROM entry_details WHERE entry_id=?',(row['id'],)).fetchone()
    base=json.loads(row['base'])
    base.update(improvement=extension['improvement'] if extension else '',submittedAt=extension['submitted_at'] if extension else '')
    base.update(flowVersion=extension['flow_version'] if extension else 0,
        reviewState=extension['review_state'] if extension else '',
        confirmedAt=extension['confirmed_at'] if extension else '',confirmedBy=extension['confirmed_by'] if extension else '',
        lastActor=json.loads(extension['last_actor']) if extension else {},
        lastLocation=extension['last_location'] if extension else '',lastChangedAt=extension['last_changed_at'] if extension else '')
    if extension and extension['inspection_problem'] is not None:base['inspectionProblem']=extension['inspection_problem']
    for key, (column, _) in REVIEW_FIELDS.items():
        if extension and extension[column] is not None:base[key]=extension[column]
    if base['submittedAt']:base['completion']='待审核' if base['reviewState']=='pending' else '已完成'
    base['legacyCompleted']=bool(not base['flowVersion'] and (base['submittedAt'] or base.get('legacyReviewState')=='approved'))
    if not base['flowVersion'] and base.get('legacyReviewState') in {'pending','returned'}:base['reviewState']='pending'
    if extension and extension['submitted_snapshot']:
        base['submittedBy']=json.loads(extension['submitted_snapshot']).get('submittedBy','')
    reversal=conn.execute("SELECT * FROM changes WHERE entry_id=? AND action='revoke' ORDER BY id DESC LIMIT 1",(row['id'],)).fetchone()
    base['lastReversal']=reversal_metadata(reversal) if reversal else None
    if extension and extension['review_execution'] is not None:
        base['inspectionExecution']={**(base.get('inspectionExecution') or {}),**json.loads(extension['review_execution'])}
        for key in ('actualDate','actualQuantity','inspector'):
            if key in json.loads(extension['review_execution']):base[key]=base['inspectionExecution'][key]
    if extension and base['reviewState']=='approved' and extension['approved_snapshot']:
        confirmed=json.loads(extension['approved_snapshot'])
        if 'inspectionDateSource' in confirmed:
            # Only expose the already-confirmed decision; reads never resolve a date.
            from app.services.qc_inspection_summary import confirmed_date
            base.update(inspectionDate=confirmed_date(confirmed),inspectionDateSource=confirmed['inspectionDateSource'])
    if not extension or extension['ship_date'] is None:base['shipDate']=(base.get('sourceRecord') or {}).get('shipDate','')
    if not extension or extension['customer_requirements'] is None:base['customerRequirements']=(base.get('sourceRecord') or {}).get('customerRequirements','')
    # Review supplements never rewrite the captured upstream order identity.
    for key in ('contractNo','customerCode','shippedQuantity'):
        if not extension or extension[REVIEW_FIELDS[key][0]] is None:
            base[key]=scalar((base.get('sourceRecord') or {}).get(key))
    if base['reviewState']=='returned_to_inspection':base['completion']='退回重新验货'
    raw=base.get('sourceResult','')
    cumulative_result=raw if raw in {'REJ','COND','HOLD'} and not base.get('resultOverride') else row['result']
    return {**base, 'id':row['id'], 'sourceKey':row['source_key'], 'cumulativeResult':cumulative_result,
            'result':row['result'], 'remark':row['remark'], 'revision':row['revision'],
            'updatedAt':row['updated_at'], 'photos':photos}


def sync(factory, rows, copy_photos=True):
    ids = [];photo_warnings=set()
    with store(True) as conn:
        source_counts={}
        for _,base,_,_,_ in rows:
            if base.get('sourceId'):source_counts[base['sourceId']]=source_counts.get(base['sourceId'],0)+1
        for key,base,result,remark,attachments in rows:
            entry_id = sha256((factory+'\0'+key).encode()).hexdigest()[:32]
            previous = conn.execute('SELECT * FROM entries WHERE factory=? AND source_key=?',(factory,key)).fetchone()
            # A scheduled source becoming its first workflow keeps the same business identity.
            # Subsequent batches remain independent; never join on customer/PO/SKU.
            if not previous and base.get('workflowId'):
                linked=list(conn.execute("SELECT * FROM entries WHERE factory=? AND json_extract(base,'$.workflowId')=?",(factory,base['workflowId'])))
                source=conn.execute('SELECT * FROM entries WHERE factory=? AND source_key=?',(factory,'source:'+str(base.get('sourceId','')))).fetchone()
                if not linked and source:
                    if source_counts.get(base.get('sourceId'))==1:linked=[source]
                    else:base['lineageConflict']='原排期已拆为多个批次，无法自动归属先前填写的验货记录'
                if len(linked)==1:
                    previous=linked[0]
                    conn.execute('UPDATE entries SET source_key=? WHERE id=?',(key,previous['id']))
                elif len(linked)>1:base['lineageConflict']='同一流程关联了多个验货记录，需要核对'
            if previous:entry_id=previous['id']
            ids.append(entry_id)
            if previous and conn.execute("SELECT 1 FROM entry_details WHERE entry_id=? AND submitted_at<>''",(entry_id,)).fetchone():
                continue  # Submitted fields/photos are frozen; source status refresh must not bump revision.
            base['historicalResult'] = result if result not in (None,'',*RESULTS) else ''
            base['sourceResult']=result or ''
            base['resultOverride']=False
            if previous:
                old_base=json.loads(previous['base'])
                if 'resultOverride' in old_base:base['resultOverride']=old_base['resultOverride']
                else:
                    # Old entries already have immutable save receipts; photo/remark-only saves do not change judgment.
                    prior='FAIL' if result in ('FAIL','REJ') else result if result in ('PASS','PENDING') else ''
                    for change in conn.execute("SELECT snapshot FROM changes WHERE entry_id=? AND action='save' ORDER BY revision",(entry_id,)):
                        value=json.loads(change['snapshot']).get('result','')
                        if value!=prior:base['resultOverride']=True
                        prior=value
                stale=isinstance(base.get('sourceRevision'),int) and isinstance(old_base.get('sourceRevision'),int) and base['sourceRevision']<old_base['sourceRevision']
                if previous['base'] != wf.dump(base) and not stale:
                    conn.execute('UPDATE entries SET base=?,revision=revision+1 WHERE id=?',(wf.dump(base),entry_id))
            else:
                normalized = result if result in RESULTS else ''
                conn.execute('INSERT INTO entries VALUES(?,?,?,?,?,?,0,0,?)',
                    (entry_id,factory,key,wf.dump(base),normalized,remark or '',wf.now()))
                conn.execute('INSERT INTO entry_details(entry_id,flow_version) VALUES(?,?)',(entry_id,0 if base.get('legacyReviewState') in {'pending','approved','returned'} else 2))
            # Preserve existing photos as independent copies. Original reviewed evidence is immutable.
            for attachment in attachments if copy_photos else []:
                origin = base.get('workflowId','')+':'+attachment['id']
                if not attachment['mime'].startswith('image/') or conn.execute('SELECT 1 FROM photos WHERE entry_id=? AND origin=?',(entry_id,origin)).fetchone():
                    continue
                try:
                    content = wf.read_file(factory,base['workflowId'],attachment['id'])['content']
                    details=photo_assets.inspect(content)
                except (HTTPException,OSError):
                    # Keep the original attachment untouched and retry on a later ordinary page refresh.
                    # An unavailable historical photo must not hide readable inspection text.
                    photo_warnings.add(entry_id);continue
                photo_id=uuid4().hex
                conn.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,0,?)',
                    (photo_id,entry_id,attachment['name'],b'',sha256(content).hexdigest(),origin,wf.now()))
                photo_assets.save(conn,photo_id,content,details=details)
                conn.execute('UPDATE entries SET revision=revision+1 WHERE id=?',(entry_id,))
        # Preserve existing inspection history. Pre-push source caches stay hidden until
        # a confirmed task adopts them above, including any previously saved input.
        retained=[]
        for row in conn.execute('SELECT * FROM entries WHERE factory=?',(factory,)):
            if row['id'] in ids:
                item=unpack(conn,row,copy_photos)
                if row['id'] in photo_warnings:item['photoWarning']='来源照片暂不可用；刷新可重试，文字仍可保存和导入'
                retained.append(item)
            elif row['edited'] and not row['source_key'].startswith('source:'):
                item=unpack(conn,row,copy_photos)
                item['sourceWarning']='来源已移除、取消或生成了新批次；保留原验货记录，未自动合并。'
                retained.append(item)
        return {'items':retained, 'results':list(ALLOWED_INSPECTION_RESULTS), 'columns':[{'key':key,'label':label} for key,label in COLUMNS]}


def revision(row, body):
    if type(body.get('revision')) is not int or body['revision'] != row['revision']:
        raise HTTPException(409,'记录已更新，填写内容已保留；请重新读取服务器版本后重试')


def changed(conn, row, action, actor, *, before=None, location='验货台', request_key='', extra=None):
    stamp=wf.now()
    conn.execute("INSERT INTO entry_details(entry_id,last_actor,last_location,last_changed_at) VALUES(?,?,?,?) ON CONFLICT(entry_id) DO UPDATE SET last_actor=excluded.last_actor,last_location=excluded.last_location,last_changed_at=excluded.last_changed_at",(row['id'],wf.dump(actor),location,stamp))
    conn.execute('UPDATE entries SET revision=revision+1,edited=1,updated_at=? WHERE id=?',(stamp,row['id']))
    current=get(conn,row['factory'],row['id']);item=unpack(conn,current)
    fields=('result','remark','improvement','inspectionProblem','photos','reviewState','submittedAt','confirmedAt','confirmedBy',*REVIEW_FIELDS)
    delta={k:{'before':before.get(k),'after':item.get(k)} for k in fields if before is not None and (before.get(k) or '')!=(item.get(k) or '')}
    if before is not None:
        for key in REVIEW_EXECUTION_FIELDS:
            old=(before.get('inspectionExecution') or {}).get(key)
            new=(item.get('inspectionExecution') or {}).get(key)
            if old!=new:delta['inspectionExecution.'+key]={'before':old,'after':new}
    if extra:delta.update(extra)
    if action=='revoke':
        item['lastReversal']={'entryId':row['id'],'customer':item.get('customer',''),'poNo':item.get('poNo',''),
            'at':stamp,'actor':actor,'location':location,'reason':(extra or {}).get('reason','')}
    event=conn.execute('INSERT INTO changes(entry_id,revision,action,actor,created_at,snapshot,location,diff,request_key) VALUES(?,?,?,?,?,?,?,?,?)',
        (row['id'],current['revision'],action,wf.dump(actor),stamp,wf.dump(item),location,wf.dump(delta),request_key))
    if action=='revoke':
        item['lastReversal']['eventId']=event.lastrowid
        conn.execute('UPDATE changes SET snapshot=? WHERE id=?',(wf.dump(item),event.lastrowid))
    return item


def save(factory, entry_id, body, actor, review=False):
    allowed={'revision','result','remark','improvement','inspectionProblem','inspectionExecution'} | (set(REVIEW_FIELDS) if review else set())
    if not {'revision','result','remark'} <= set(body) or set(body)-allowed or body['result'] not in EDITABLE_RESULTS:
        raise HTTPException(422,'验货结果只接受空草稿、PASS、FAIL、PENDING、LG')
    for key in ('remark','improvement','inspectionProblem',*REVIEW_FIELDS):
        if key in body and (not isinstance(body[key],str) or len(body[key])>REVIEW_FIELDS.get(key, ('',20000))[1] or any(ord(c)<32 and c not in '\n\r\t' for c in body[key])):
            raise HTTPException(422,'文本过长或包含控制字符；责任人和验货工厂最多200字，备注最多20000字')
        if key in body and key in REVIEW_FIELDS and REVIEW_FIELDS[key][1]==200 and any(c in body[key] for c in '\n\r\t'):
            raise HTTPException(422,'此字段请填写单行文字')
    if 'shipDate' in body:wf.day(body['shipDate'])
    if 'shippedQuantity' in body:wf.number(body['shippedQuantity'])
    if not review and 'inspectionExecution' in body and (not isinstance(body['inspectionExecution'],dict) or set(body['inspectionExecution'])-{'actualDate'}):
        raise HTTPException(422,'验货台只允许补充实际验货日期')
    execution_patch=clean_review_execution(body['inspectionExecution']) if 'inspectionExecution' in body else {}
    with store(True) as conn:
        row=get(conn,factory,entry_id);ensure_editable(conn,row,review)
        revision(row,body)
        before=unpack(conn,row)
        if all(body.get(k,before.get(k,''))==before.get(k,'') for k in ('result','remark','improvement','inspectionProblem',*REVIEW_FIELDS)) and all((before.get('inspectionExecution') or {}).get(k)==v for k,v in execution_patch.items()):return before
        conn.execute("INSERT INTO entry_details(entry_id,improvement,inspection_problem) VALUES(?,?,?) ON CONFLICT(entry_id) DO UPDATE SET improvement=excluded.improvement,inspection_problem=excluded.inspection_problem",
            (entry_id,body.get('improvement',before['improvement']),body.get('inspectionProblem',before.get('inspectionProblem'))))
        for key, (column, _) in REVIEW_FIELDS.items():
            if key in body:conn.execute('UPDATE entry_details SET '+column+'=? WHERE entry_id=?',(body[key],entry_id))
        if execution_patch:
            saved=conn.execute('SELECT review_execution FROM entry_details WHERE entry_id=?',(entry_id,)).fetchone()[0]
            merged={**json.loads(saved or '{}'),**execution_patch}
            conn.execute('UPDATE entry_details SET review_execution=? WHERE entry_id=?',(wf.dump(merged),entry_id))
        if body['result']!=row['result']:
            base=json.loads(row['base']);base['resultOverride']=True
            conn.execute('UPDATE entries SET base=? WHERE id=?',(wf.dump(base),entry_id))
        conn.execute('UPDATE entries SET result=?,remark=? WHERE id=?',(body['result'],body['remark'],entry_id))
        return changed(conn,row,'save',actor,before=before,location='审核中心 · 待审核' if review else '验货台')


def normalize_photo(content):
    if not content or len(content)>10*1024*1024:
        raise HTTPException(413,'单张照片须为 10 MB 以内的图片')
    try:
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError:
            pass
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as original:
                if original.format not in {'JPEG','PNG','WEBP','HEIF','HEIC'}:
                    raise ValueError()
                if original.width*original.height>40000000:
                    raise ValueError()
                original.load()
                photo=ImageOps.exif_transpose(original).convert('RGB')
                photo.thumbnail((2560,2560))
                output=BytesIO();photo.save(output,'JPEG',quality=90,optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise HTTPException(422,'图片损坏或格式不支持，请选择 JPG、PNG、WebP，或将手机照片转为 JPEG 后重试') from None


def add_photo(factory, entry_id, body, actor, review=False):
    if set(body) != {'revision','name','content','requestKey'} or not re.fullmatch(r'[a-f0-9-]{16,64}',str(body['requestKey'])):
        raise HTTPException(422,'照片提交字段不正确')
    name=body['name']
    if not isinstance(name,str) or not 1<=len(name)<=255:
        raise HTTPException(422,'照片名称不正确')
    try:
        content=base64.b64decode(body['content'],validate=True)
    except (ValueError,TypeError,binascii.Error):
        raise HTTPException(422,'照片内容无效') from None
    details=photo_assets.inspect(content)
    digest=details['sha256']
    with store(True) as conn:
        row=get(conn,factory,entry_id)
        origin='upload:'+body['requestKey']
        previous=conn.execute('SELECT digest FROM photos WHERE entry_id=? AND origin=?',(entry_id,origin)).fetchone()
        if previous:
            if previous['digest'] != digest and previous['digest'] != sha256(normalize_photo(content)).hexdigest():
                raise HTTPException(409,'同一上传编号不能用于不同照片')
            return unpack(conn,row)
        ensure_editable(conn,row,review)
        before=unpack(conn,row)
        revision(row,body)
        count,total=conn.execute('''SELECT count(*),coalesce(sum(coalesce(json_extract(a.metadata,'$.sourceSize'),
            json_extract(a.metadata,'$.original.size'),length(p.content))),0)
            FROM photos p LEFT JOIN photo_assets a ON a.photo_id=p.id WHERE p.entry_id=? AND p.removed=0''',(entry_id,)).fetchone()
        if count>=50 or total+len(content)>100*1024*1024:
            raise HTTPException(413,'每条任务最多 50 张、100 MB')
        photo_id=uuid4().hex
        conn.execute('INSERT INTO photos VALUES(?,?,?,?,?,?,0,?)',(photo_id,entry_id,name,b'',digest,origin,wf.now()))
        photo_assets.save(conn,photo_id,content,'preview-only',details=details)
        return changed(conn,row,'upload',actor,before=before,location='审核中心 · 待审核' if review else '验货台')


def remove_photo(factory, entry_id, body, actor, review=False):
    if set(body) != {'revision','photoId'}:
        raise HTTPException(422,'删除字段不正确')
    with store(True) as conn:
        row=get(conn,factory,entry_id);ensure_editable(conn,row,review);revision(row,body);before=unpack(conn,row)
        found=conn.execute('UPDATE photos SET removed=1 WHERE id=? AND entry_id=? AND removed=0',(body['photoId'],entry_id))
        if not found.rowcount:
            raise HTTPException(404,'照片不存在或已删除')
        return changed(conn,row,'remove-photo',actor,before=before,location='审核中心 · 待审核' if review else '验货台')


def read_photo_version(factory, entry_id, photo_id, variant='preview'):
    with store() as conn:
        get(conn,factory,entry_id)
        row=conn.execute('SELECT * FROM photos WHERE id=? AND entry_id=? AND removed=0',(photo_id,entry_id)).fetchone()
        if row is None:raise HTTPException(404,'照片不存在')
        return photo_assets.read(conn,row,variant)


def read_photo(factory, entry_id, photo_id):
    return read_photo_version(factory,entry_id,photo_id)[0]


def migrate_pending(conn):
    """Transactional CHECK expansion; retain row IDs and all child evidence."""
    if all("'"+value+"'" in conn.execute("SELECT sql FROM sqlite_master WHERE name='entries'").fetchone()[0] for value in RESULTS):return
    conn.execute('PRAGMA foreign_keys=OFF')
    try:
        conn.execute('BEGIN IMMEDIATE')
        if not all("'"+value+"'" in conn.execute("SELECT sql FROM sqlite_master WHERE name='entries'").fetchone()[0] for value in RESULTS):
            objects=[r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE tbl_name='entries' AND type IN ('index','trigger') AND sql IS NOT NULL")]
            ddl=SCHEMA.split(';')[0].replace('IF NOT EXISTS entries','entries_pending_upgrade')
            conn.execute(ddl)
            conn.execute('INSERT INTO entries_pending_upgrade SELECT * FROM entries')
            conn.execute('DROP TABLE entries')
            conn.execute('ALTER TABLE entries_pending_upgrade RENAME TO entries')
            for sql in objects:conn.execute(sql)
            if conn.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('Pending migration foreign-key validation failed')
        conn.commit()
    except Exception:conn.rollback();raise
    finally:conn.execute('PRAGMA foreign_keys=ON')


def ensure_editable(conn, row, review=False):
    item=unpack(conn,row,False)
    if review:
        if item['reviewState']!='pending':raise HTTPException(409,'只有待审核记录可编辑，请刷新核对状态')
    elif item['reviewState']!='returned_to_inspection' and (item['submittedAt'] or item['legacyCompleted']):
        raise HTTPException(409,'记录已提交审核或已完成，请在审核中心核对状态')


def workbench_items(items):
    """Submission state, independent of cumulative workbook merge/undo state."""
    return [r for r in items if r.get('reviewState')=='returned_to_inspection' or (not r.get('submittedAt') and not r.get('legacyCompleted')
            and r.get('reviewState') not in {'pending', 'approved'})]


def submit(factory, entry_id, body, actor):
    if set(body)!={'revision'}:raise HTTPException(422,'提交字段不正确')
    with store(True) as conn:
        row=get(conn,factory,entry_id);before=unpack(conn,row)
        if before['submittedAt'] and before['reviewState']!='returned_to_inspection':return before
        if before['legacyCompleted']:raise HTTPException(409,'历史已完成记录保持原状态，不能重复提交')
        revision(row,body)
        if before['result'] not in ALLOWED_INSPECTION_RESULTS:raise HTTPException(422,'请先选择 PASS、FAIL、PENDING 或 LG 并保存')
        previous=conn.execute('SELECT submitted_snapshot FROM entry_details WHERE entry_id=?',(entry_id,)).fetchone()
        previous_snapshot=json.loads(previous[0]) if previous and previous[0] and before['reviewState']=='returned_to_inspection' else None
        stamp=wf.now()
        conn.execute("INSERT INTO entry_details(entry_id,submitted_at,flow_version,review_state) VALUES(?,?,2,'pending') ON CONFLICT(entry_id) DO UPDATE SET submitted_at=excluded.submitted_at,flow_version=2,review_state='pending'",(entry_id,stamp))
        item=changed(conn,row,'submit',actor,before=before,extra={'resubmission':before['reviewState']=='returned_to_inspection',**({'previousSubmissionSnapshot':previous_snapshot} if previous_snapshot else {})})
        item['submittedBy']=actor['name']
        conn.execute("UPDATE changes SET snapshot=? WHERE entry_id=? AND revision=? AND action='submit'",(wf.dump(item),entry_id,item['revision']))
        conn.execute('UPDATE entry_details SET submitted_snapshot=? WHERE entry_id=?',(wf.dump(item),entry_id))
        return item


def audit(factory, entry_id):
    with store() as conn:
        get(conn,factory,entry_id)
        return {'items':[{'id':r['id'],'revision':r['revision'],'action':r['action'],
            'actor':json.loads(r['actor']),'at':r['created_at'],'location':r['location'],
            'changes':json.loads(r['diff'])} for r in conn.execute('SELECT * FROM changes WHERE entry_id=? ORDER BY id DESC',(entry_id,))]}


def review_batch(factory, action, body, actor):
    if action not in {'confirm','revoke'} or set(body)-{'entries','requestKey','reason'} or not isinstance(body.get('entries'),list) or not 1<=len(body['entries'])<=500 or not re.fullmatch(r'[a-f0-9-]{16,64}',str(body.get('requestKey',''))):
        raise HTTPException(422,'审核范围或请求编号不正确')
    entries=body['entries'];reason=body.get('reason','')
    if any(not isinstance(x,dict) or set(x)!={'id','revision'} or not isinstance(x['id'],str) or type(x['revision']) is not int for x in entries) or len({x['id'] for x in entries})!=len(entries):raise HTTPException(422,'审核记录重复或版本不正确')
    if not isinstance(reason,str) or len(reason)>20000 or any(ord(c)<32 and c not in '\n\r\t' for c in reason):raise HTTPException(422,'反审核说明最多20000字')
    from app.services import qc_inspection_summary as summary
    results=[]
    with store(True,review=True) as conn:
        for wanted in entries:
            conn.execute('SAVEPOINT review_item')
            try:
                row=get(conn,factory,wanted['id']);before=unpack(conn,row)
                receipt=conn.execute('SELECT * FROM changes WHERE entry_id=? AND request_key=?',(row['id'],body['requestKey'])).fetchone()
                if receipt:
                    previous=json.loads(receipt['diff'])
                    if json.loads(receipt['actor']).get('id')!=actor.get('id') or receipt['action']!=action or previous.get('reason','')!=reason or previous.get('expectedRevision')!=wanted['revision']:raise HTTPException(409,'同一请求编号不能用于不同操作')
                    item=before
                else:
                    revision(row,wanted)
                    expected='pending' if action=='confirm' else 'approved'
                    legacy_revoke=action=='revoke' and before['legacyCompleted']
                    if before['reviewState']!=expected and not legacy_revoke:raise HTTPException(409,'记录状态已变化，请刷新后重试')
                    conn.execute('INSERT OR IGNORE INTO entry_details(entry_id) VALUES(?)',(row['id'],))
                    if action=='confirm':
                        if before['result'] not in ALLOWED_INSPECTION_RESULTS:raise HTTPException(422,'请选择 PASS、FAIL、PENDING 或 LG 后重新审核')
                        conn.execute("UPDATE entry_details SET flow_version=2,review_state='approved',confirmed_at=?,confirmed_by=? WHERE entry_id=?",(wf.now(),actor['name'],row['id']))
                    else:
                        # An explicit revoke adopts the new review flow; never invent a historical confirmation time.
                        conn.execute("UPDATE entry_details SET flow_version=2,review_state='pending',approved_snapshot=CASE WHEN approved_snapshot='' THEN ? ELSE approved_snapshot END WHERE entry_id=?",(wf.dump(before),row['id']))
                    item=changed(conn,row,action,actor,before=before,
                        location='审核中心 · 待审核' if action=='confirm' else '审核中心 · 已审核',request_key=body['requestKey'],extra={'reason':reason,'expectedRevision':wanted['revision'],**({'legacyCompleted':True} if legacy_revoke else {})})
                    if action=='confirm':
                        # Decide once in this confirmation transaction. Never fill the QC input.
                        item.update(summary.resolve_inspection_date(item))
                        conn.execute("UPDATE changes SET snapshot=? WHERE entry_id=? AND revision=? AND action='confirm'",(wf.dump(item),row['id'],item['revision']))
                        conn.execute('UPDATE entry_details SET approved_snapshot=? WHERE entry_id=?',(wf.dump(item),row['id']))
                        summary.upsert(conn,factory,'entry:'+row['id'],summary.review_item(item),schema='qsum.')
                    else:
                        identity=sha256((factory+'\0entry:'+row['id']).encode()).hexdigest()[:32]
                        conn.execute('INSERT INTO qsum.changes(record_id,created_at,payload) SELECT id,?,payload FROM qsum.records WHERE id=? AND factory=? AND active=1',(wf.now(),identity,factory))
                        conn.execute('UPDATE qsum.records SET active=0,updated_at=? WHERE id=? AND factory=?',(wf.now(),identity,factory))
                result={'id':row['id'],'ok':True,'item':item}
                if action=='revoke':
                    event=receipt or conn.execute('SELECT * FROM changes WHERE entry_id=? AND request_key=?',(row['id'],body['requestKey'])).fetchone()
                    result['reversal']=reversal_metadata(event)
                results.append(result)
                conn.execute('RELEASE review_item')
            except HTTPException as error:
                conn.execute('ROLLBACK TO review_item');conn.execute('RELEASE review_item')
                results.append({'id':wanted['id'],'ok':False,'status':error.status_code,'message':error.detail})
    return {'results':results,'succeeded':sum(r['ok'] for r in results),'failed':sum(not r['ok'] for r in results)}


def return_to_inspection(factory, entry_id, body, actor, sources=None):
    if not {'revision','requestKey'} <= set(body) or set(body)-{'revision','requestKey','reason'} or type(body['revision']) is not int or not re.fullmatch(r'[a-f0-9-]{16,64}',str(body['requestKey'])):
        raise HTTPException(422,'退回请求或版本不正确')
    reason = body.get('reason', '')
    if not isinstance(reason, str) or len(reason)>20000 or any(ord(c)<32 and c not in '\n\r\t' for c in reason):
        raise HTTPException(422,'退回原因最多20000字')
    with store(True,review=True) as conn:
        row=get(conn,factory,entry_id);before=unpack(conn,row)
        receipt=conn.execute('SELECT * FROM changes WHERE entry_id=? AND request_key=?',(entry_id,body['requestKey'])).fetchone()
        if receipt:
            previous = json.loads(receipt['diff'])
            if (receipt['action'] != 'return-to-inspection' or json.loads(receipt['actor']).get('id') != actor['id']
                    or previous.get('expectedRevision') != body['revision'] or previous.get('reason', '') != reason):
                raise HTTPException(409,'同一请求编号不能用于不同操作')
            return {'item':before,'eventId':receipt['id'],'replayed':True}
        revision(row,body)
        if before['reviewState']!='pending':raise HTTPException(409,'只有待审核记录可以退回验货台，请刷新核对')
        source=next((s for s in sources or [] if s['id']==before.get('sourceId')),before.get('sourceRecord') or {})
        if source.get('sourceStatus')=='cancelled':raise HTTPException(409,'来源订单已取消，不能退回重新验货')
        conn.execute("UPDATE entry_details SET review_state='returned_to_inspection',flow_version=2 WHERE entry_id=?",(entry_id,))
        item=changed(conn,row,'return-to-inspection',actor,before=before,location='审核中心 · 待审核',request_key=body['requestKey'],extra={'expectedRevision':body['revision'],'reason':reason})
        # Defensive deactivation preserves the existing archive and all past payloads.
        identity=sha256((factory+'\0entry:'+entry_id).encode()).hexdigest()[:32]
        conn.execute('INSERT INTO qsum.changes(record_id,created_at,payload) SELECT id,?,payload FROM qsum.records WHERE id=? AND factory=? AND active=1',(wf.now(),identity,factory))
        conn.execute('UPDATE qsum.records SET active=0,updated_at=? WHERE id=? AND factory=?',(wf.now(),identity,factory))
        event=conn.execute('SELECT id FROM changes WHERE entry_id=? AND request_key=?',(entry_id,body['requestKey'])).fetchone()
        return {'item':item,'eventId':event['id'],'replayed':False}
