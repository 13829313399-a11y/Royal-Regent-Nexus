"""Recoverable QC archive projection; never changes inspection/workbook sources.

Committed workbook versions and immutable approval events are the source of truth.
The separate SQLite projection can always be reconciled after an interrupted hook.
History imports retain original bytes, preview receipts and reversible membership.
"""
from collections import Counter
from contextlib import contextmanager
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import base64
import binascii
import calendar
import json
import logging
import sqlite3

from fastapi import HTTPException
from openpyxl.utils.datetime import from_excel
from openpyxl.utils.cell import range_boundaries, get_column_letter

from app.core.config import settings
from app.services import qc_cumulative as cumulative, qc_workflow as workflow
from app.services import qc_workbook_upload as upload, qc_workbook_xml as xml

SHANGHAI = ZoneInfo('Asia/Shanghai')
STATUS = {'approved':'已审核', 'completed':'已完成', 'archived': '已归档', 'unverified': '历史待核实', 'withdrawn': '归档已撤回'}
SCHEMA = '''
CREATE TABLE IF NOT EXISTS records (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, source_key TEXT NOT NULL,
 inspection_date TEXT NOT NULL, customer TEXT NOT NULL, stock_no TEXT NOT NULL,
 product_no TEXT NOT NULL, order_no TEXT NOT NULL, inspection_type TEXT NOT NULL,
 result TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
 fingerprint TEXT NOT NULL DEFAULT '', batch_id TEXT, active INTEGER NOT NULL DEFAULT 1,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(factory,source_key));
CREATE INDEX IF NOT EXISTS summary_dates ON records(factory,active,inspection_date,stock_no,id);
CREATE INDEX IF NOT EXISTS summary_identity ON records(factory,active,customer,stock_no,order_no);
CREATE INDEX IF NOT EXISTS summary_fingerprint ON records(factory,fingerprint,active);
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY, record_id TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS batches (
 id TEXT PRIMARY KEY, factory TEXT NOT NULL, actor TEXT NOT NULL, filename TEXT NOT NULL,
 digest TEXT NOT NULL, document_key TEXT NOT NULL, original BLOB NOT NULL, preview TEXT NOT NULL,
 status TEXT NOT NULL, created_at TEXT NOT NULL, committed_at TEXT, rolled_back_at TEXT);
CREATE INDEX IF NOT EXISTS summary_batches ON batches(factory,created_at);
'''


def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return '' if value is None else str(value)


def digest(value):
    return sha256(dump(value).encode()).hexdigest()


def business_date(value):
    """Date-only values stay dates; timestamps use the Shanghai business day."""
    if not value:
        return ''
    try:
        raw = text(value)
        if len(raw) == 10:
            return date.fromisoformat(raw).isoformat()
        moment = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=SHANGHAI)
        return moment.astimezone(SHANGHAI).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        return ''


@contextmanager
def store(write=False):
    path = Path(settings.qc_department_data_dir).resolve() / '_summary' / 'summaries.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=20)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert(conn, factory, key, item, *, batch=None, fingerprint='', schema=''):
    if schema not in {'','qsum.'}:raise ValueError('Invalid summary schema')
    identity = sha256((factory + '\0' + key).encode()).hexdigest()[:32]
    existing = conn.execute('SELECT * FROM '+schema+'records WHERE id=?', (identity,)).fetchone()
    # Explicitly cleared workbook projections stay recoverable but hidden.
    # History-import rollback/reimport keeps its separate existing behavior.
    if existing and not existing['active'] and key.startswith('entry:') and not (item.get('sourceKind')=='review' and json.loads(existing['payload']).get('sourceKind') in {'review','submission'}):
        return identity
    stamp = workflow.now()
    item = {**item, 'id': identity, 'factory': factory}
    if existing:
        previous = json.loads(existing['payload'])
        if (previous.get('sourceKind') == 'review' and 'inspectionDateSource' in previous
                and item.get('sourceKind') == 'review' and 'inspectionDateSource' not in item):
            raise HTTPException(409, '审核日期快照版本不兼容，已保留原汇总；请核对审核历史')
        if previous.get('sourceKind') in {'submission','review'} and item.get('sourceKind')=='workbook':return identity
        item['firstSeenAt'] = previous.get('firstSeenAt', existing['created_at'])
        if item['status'] == 'archived':
            item['archivedAt'] = (previous.get('archivedAt') if previous.get('status') == 'archived'
                                  and previous.get('approvalEventId') == item.get('approvalEventId')
                                  else stamp)
        if dump(item) == existing['payload'] and existing['active']:
            return identity
        conn.execute('INSERT INTO '+schema+'changes(record_id,created_at,payload) VALUES(?,?,?)',
                     (identity, stamp, existing['payload']))
    else:
        item['firstSeenAt'] = stamp
        item['archivedAt'] = stamp if item['status'] == 'archived' else ''
    values = (identity, factory, key, item.get('inspectionDate', ''), item.get('customer', ''),
              item.get('stockNo', ''), item.get('productNo', ''), item.get('poNo', ''),
              item.get('inspectionType', '待确认'), item.get('result', ''), item['status'], dump(item),
              fingerprint, batch, 1, existing['created_at'] if existing else stamp, stamp)
    conn.execute('INSERT INTO '+schema+'''records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET inspection_date=excluded.inspection_date,
        customer=excluded.customer,stock_no=excluded.stock_no,product_no=excluded.product_no,
        order_no=excluded.order_no,inspection_type=excluded.inspection_type,result=excluded.result,
        status=excluded.status,payload=excluded.payload,fingerprint=excluded.fingerprint,
        batch_id=excluded.batch_id,active=1,updated_at=excluded.updated_at''', values)
    return identity


def canonical_result(value):
    # Existing workflow and inspection-sheet explicitly map REJ <-> FAIL.
    return 'FAIL' if value == 'REJ' else value


def resolve_inspection_date(item):
    """Called only by explicit confirmation, using the task's captured plan."""
    actual = workflow.source_date(item.get('actualDate'))
    planned = workflow.source_date(item.get('dateFrom'))
    return {'inspectionDate': actual or planned,
            'inspectionDateSource': 'qc_manual' if actual else 'schedule' if planned else None}


def confirmed_date(item):
    """Read a frozen decision, refusing malformed markers before projection writes."""
    if 'inspectionDateSource' not in item:
        return business_date(item.get('actualDate'))
    value = item.get('inspectionDate')
    origin = item['inspectionDateSource']
    if (not isinstance(value, str) or origin not in ('qc_manual', 'schedule', None)
            or (origin is None and value != '')
            or (origin is not None and (not value or workflow.source_date(value) != value))):
        raise HTTPException(409, '已确认日期快照不完整，已保留原记录；请核对审核历史后重试')
    return value


def report_date(item, final):
    """Use the captured plan for older approvals that lack a frozen date."""
    if final or 'inspectionDateSource' in item:
        return final, item.get('inspectionDateSource') or ''
    planned = workflow.source_date(item.get('dateFrom'))
    return planned, 'schedule' if planned else ''


def review_item(item):
    # Absence of the marker means a historical confirmation: retain its old semantics.
    # In particular, recovery must not call the resolver or backfill historical blanks.
    final_date = confirmed_date(item)
    return {**item,'entryId':item['id'],'inspectionDate':final_date,
        'stockNo':'','inspectionType':item.get('agency') or '待确认','status':'approved',
        'sourceKind':'review','sourceLabel':'审核中心确认','verificationIssues':[],'archivedAt':''}


def reconcile(factory):
    """Idempotent recovery. Only committed current/archived workbook versions count."""
    with cumulative.store() as conn:
        versions = conn.execute('''SELECT id,snapshot,metadata,created_at FROM versions
            WHERE factory=? AND (id IN (SELECT current_id FROM heads WHERE factory=?)
            OR id IN (SELECT version_id FROM archives WHERE factory=?)) ORDER BY id''',
            (factory, factory, factory)).fetchall()
    with workflow.store() as conn:
        tasks = {r['id']: dict(r) for r in conn.execute('SELECT * FROM tasks WHERE factory=?', (factory,))}
        approvals = {r['task_id']: dict(r) for r in conn.execute('''SELECT e.* FROM events e
            JOIN tasks t ON e.task_id=t.id WHERE t.factory=? AND e.action='approve' ORDER BY e.id''', (factory,))}
    candidates = {}
    for version in versions:
        metadata = json.loads(version['metadata'])
        for entry_id, row in json.loads(version['snapshot']).items():
            binding = metadata.get('bindings', {}).get(entry_id)
            if binding:
                candidates[entry_id] = (row, binding, version)
    # Read authoritative inline states before acquiring the projection write lock.
    from app.services import qc_inspection_sheet as sheet
    with sheet.store(True) as journal:
        details={r['entry_id']:dict(r) for r in journal.execute('SELECT d.* FROM entry_details d JOIN entries e ON e.id=d.entry_id WHERE e.factory=?',(factory,))}
        seen = set()
        with store(True) as conn:
            for entry_id, (row, binding, version) in candidates.items():
                if details.get(entry_id,{}).get('flow_version')==2:continue
                task_row = tasks.get(row.get('workflowId'))
                task = json.loads(task_row['payload']) if task_row else {}
                event = approvals.get(row.get('workflowId'))
                approved = json.loads(event['snapshot']) if event else {}
                execution = approved.get('execution', {})
                issues = []
                actual = business_date(row.get('actualDate'))
                if not task_row or task_row['state'] != 'approved' or not event:
                    issues.append('缺少有效的主管审核通过凭据')
                if event and (approved.get('revision') != task_row['revision'] or approved.get('state') != 'approved'):
                    issues.append('审核凭据不是当前版本')
                if not actual:
                    issues.append('缺少实际验货日期；未使用排期日期代替')
                if event and (business_date(execution.get('actualDate')) != actual
                              or canonical_result(execution.get('result')) != canonical_result(row.get('result'))
                              or text(execution.get('remark')) != text(row.get('remark'))):
                    issues.append('工作簿中的日期、结果或备注与已审核内容不一致')
                if event and text(approved.get('source', {}).get('sourceRevision')) != text(row.get('sourceRevision')):
                    issues.append('来源订单版本与审核快照不一致')
                method = task_row['method'] if task_row else ''
                item = {**row, 'entryId': entry_id, 'inspectionDate': actual, 'stockNo': '',
                        'inspectionType': workflow.METHODS.get(method, '待确认'),
                        'status': 'unverified' if issues else 'archived', 'verificationIssues': issues,
                        'sourceKind': 'workbook', 'sourceLabel': '已持久化工作簿',
                        'workbookVersionId': version['id'], 'workbookSavedAt': version['created_at'],
                        'sourceSheet': binding['sheet'], 'sourceRow': binding['row'],
                        'confirmedAt': event['created_at'] if event else '',
                        'confirmedBy': event['actor_name'] if event else '',
                        'approvalEventId': event['id'] if event else None,
                        'archivedAt': '', 'approvalSnapshot': approved,
                        'actualQuantity': task.get('execution', {}).get('actualQuantity'),
                        'inspectionExecution': task.get('execution', {}),
                        'inspector': task.get('execution', {}).get('inspector', ''),
                        'sourceRecord': task.get('source', {}),
                        'isTest': bool(task.get('testEntry') or '【QC隔离验收测试】' in text(task.get('source', {}).get('remark')))}
                seen.add(upsert(conn, factory, 'entry:' + entry_id, item))
            for existing in conn.execute("SELECT id,payload FROM records WHERE factory=? AND source_key LIKE 'entry:%' AND active=1", (factory,)).fetchall():
                if existing['id'] not in seen:
                    item = json.loads(existing['payload'])
                    if item.get('sourceKind') in {'submission','review'}:continue
                    item.update(status='withdrawn', archivedAt='', verificationIssues=['工作簿交接已撤销；保留原记录及恢复凭据'])
                    upsert(conn, factory, 'entry:' + item['entryId'], item)
        with store(True) as conn:
            for saved in details.values():
                if saved['flow_version']==2:
                    if saved['review_state']=='approved' and saved['approved_snapshot']:
                        item=review_item(json.loads(saved['approved_snapshot']))
                        upsert(conn,factory,'entry:'+item['entryId'],item)
                    continue
                if not saved['submitted_at'] or not saved['submitted_snapshot']:continue
                item=json.loads(saved['submitted_snapshot'])
                item.update(entryId=item['id'],inspectionDate=business_date(item.get('actualDate')),stockNo='',
                    inspectionType=item.get('agency','待确认'),status='completed',sourceKind='submission',
                    sourceLabel='验货台提交',verificationIssues=[],archivedAt='')
                upsert(conn,factory,'entry:'+item['entryId'],item)
    return len(seen)


def after_change(factory):
    """The committed source remains recoverable even if projection storage is unavailable."""
    try:
        reconcile(factory)
        return {'status': 'synced'}
    except Exception:
        logging.getLogger(__name__).exception('QC summary projection deferred for %s', factory)
        return {'status': 'deferred', 'message': '交接凭据已保存，汇总同步待重试；打开验货汇总将自动恢复'}


def filters(params):
    allowed = {'year', 'month', 'day', 'search', 'type', 'status', 'page', 'pageSize', 'dateBasis'}
    if set(params) - allowed:
        raise HTTPException(422, '汇总筛选参数无效')
    out = {k: text(params.get(k)).strip() for k in allowed}
    if out['dateBasis'] not in ('','actual','schedule','report'):
        raise HTTPException(422, '汇总日期口径无效')
    if len(out['search']) > 200 or out['type'] not in ('', '客验', '行验', '待确认') or out['status'] not in ('', *STATUS):
        raise HTTPException(422, '汇总筛选参数无效')
    try:
        for key, low, high in [('year', 1900, 9999), ('month', 1, 12), ('day', 1, 31), ('page', 1, 1000000), ('pageSize', 1, 100)]:
            if out[key] and (not out[key].isdigit() or not low <= int(out[key]) <= high):
                raise ValueError()
        if out['month'] and not out['year'] or out['day'] and not out['month']:
            raise ValueError()
        if out['day']:
            date(int(out['year']), int(out['month']), int(out['day']))
    except ValueError:
        raise HTTPException(422, '日期或分页无效，请先选择有效的年、月、日') from None
    return out


def where(factory, f, date_column='inspection_date'):
    sql, args = ['factory=?', 'active=1'], [factory]
    if f['year']:
        start = date(int(f['year']), int(f['month'] or 1), int(f['day'] or 1))
        if f['day']:
            sql.append(f'{date_column}=?'); args.append(start.isoformat())
        else:
            month = int(f['month'] or 12)
            end = date(int(f['year']), month, calendar.monthrange(int(f['year']), month)[1])
            sql.append(f'{date_column} BETWEEN ? AND ?'); args.extend((start.isoformat(), end.isoformat()))
    for key, column in [('type', 'inspection_type'), ('status', 'status')]:
        if f[key]:
            sql.append(column + '=?'); args.append(f[key])
    if f['search']:
        sql.append("instr(lower(customer || char(10) || stock_no || char(10) || order_no || char(10) || product_no),?)>0")
        args.append(f['search'].lower())
    return ' AND '.join(sql), args


def summary_report_date(item, final):
    if item.get('status') == 'approved' and item.get('sourceKind') == 'review':
        return report_date(item, final)[0]
    return final


def with_schedule_dates(factory, items):
    """Display-only schedule dates. Never rewrite actual dates or archive evidence."""
    path = Path(settings.qc_department_data_dir) / '_inspection_sheet' / 'inspections.sqlite3'
    linked = {}
    if path.exists():
        with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as journal:
            linked = {r[0]:json.loads(r[1]) for r in journal.execute('SELECT id,base FROM entries WHERE factory=?',(factory,))}
    for item in items:
        entry_id = item.get('entryId')
        # Prefer the confirmed source snapshot; use only a same-factory stable entry for old projections.
        source = item.get('sourceRecord') or {}
        start = business_date(item.get('dateFrom')) if entry_id else ''
        end = business_date(item.get('dateTo')) if entry_id else ''
        if not start and entry_id:
            start = business_date(source.get('dateFrom'))
            end = business_date(source.get('dateTo'))
        if not start and entry_id in linked:
            start = business_date(linked[entry_id].get('dateFrom'))
            end = business_date(linked[entry_id].get('dateTo'))
        item['scheduleDate'] = start
        item['scheduleDateTo'] = end or start
    return items


def schedule_listing(factory, f):
    # Existing SQL still handles factory, search and status; only the requested UI date basis changes.
    with store() as conn:
        all_items = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM records WHERE factory=? AND active=1',(factory,))]
        clause,args = where(factory,{**f,'year':'','month':'','day':''})
        selected_ids = {r[0] for r in conn.execute('SELECT id FROM records WHERE '+clause,args)}
    items = with_schedule_dates(factory,all_items)
    def matches(item):
        d = item['scheduleDate']
        return item['id'] in selected_ids and all(not f[key] or (d and int(d[part])==int(f[key]))
            for key,part in [('year',slice(0,4)),('month',slice(5,7)),('day',slice(8,10))])
    selected = sorted((i for i in items if matches(i)), key=lambda i:(not i['scheduleDate'],i['scheduleDate'],text(i.get('stockNo')).lower(),i['id']))
    total=len(selected);page_size=int(f['pageSize'] or 30)
    page=min(int(f['page'] or 1),max(1,(total+page_size-1)//page_size))
    return {'items':selected[(page-1)*page_size:page*page_size],
        'total':total,'page':page,'pageSize':page_size,'years':sorted({i['scheduleDate'][:4] for i in items if i['scheduleDate']}),
        'counts':dict(Counter(STATUS[i['status']] for i in items)),'unknownDates':sum(not i['scheduleDate'] for i in items),
        'timezone':'Asia/Shanghai','dateBasis':'schedule','filters':f}


def listing(factory, params):
    f = filters(params)
    reconcile(factory)
    if f['dateBasis']=='schedule':return schedule_listing(factory,f)
    using_report_date = f['dateBasis'] == 'report'
    date_column = ("(CASE WHEN inspection_date='' AND status='approved' "
                   "THEN report_date(payload) ELSE inspection_date END)") if using_report_date else 'inspection_date'
    clause, args = where(factory, f, date_column)
    with store() as conn:
        if using_report_date:
            conn.create_function('report_date', 1, lambda payload: summary_report_date(json.loads(payload), ''),
                                 deterministic=True)
        total = conn.execute('SELECT count(*) FROM records WHERE ' + clause, args).fetchone()[0]
        page_size = int(f['pageSize'] or 30)
        page = min(int(f['page'] or 1), max(1, (total + page_size - 1) // page_size))
        query = (f'SELECT payload, {date_column} AS display_date FROM records WHERE {clause} '
                 "ORDER BY display_date='' ASC,display_date ASC,stock_no COLLATE NOCASE ASC,id ASC")
        rows = conn.execute(query + ' LIMIT ? OFFSET ?',
                            [*args, page_size, (page - 1) * page_size]).fetchall()
        years = [r[0] for r in conn.execute(f"SELECT DISTINCT substr({date_column},1,4) FROM records WHERE factory=? AND active=1 AND {date_column}<>'' ORDER BY 1", (factory,))]
        counts = {STATUS[r[0]]: r[1] for r in conn.execute('SELECT status,count(*) FROM records WHERE factory=? AND active=1 GROUP BY status', (factory,))}
        unknown = conn.execute(f"SELECT count(*) FROM records WHERE factory=? AND active=1 AND {date_column}=''", (factory,)).fetchone()[0]
    items = [json.loads(r['payload']) for r in rows]
    if using_report_date:
        for item, row in zip(items, rows):
            item['reportDate'] = row['display_date']
    return {'items': items, 'total': total, 'page': page,
            'pageSize': page_size, 'years': years, 'counts': counts, 'unknownDates': unknown,
            'timezone': 'Asia/Shanghai', 'filters': f}


def detail(factory, identity):
    reconcile(factory)
    with store() as conn:
        row = conn.execute('SELECT payload FROM records WHERE factory=? AND id=? AND active=1', (factory, identity)).fetchone()
        if row is None:
            raise HTTPException(404, '汇总记录不存在或所属历史批次已回滚')
        item = json.loads(row['payload'])
        item['archiveHistory'] = [{'at': r['created_at'], 'record': json.loads(r['payload'])} for r in
                                 conn.execute('SELECT * FROM changes WHERE record_id=? ORDER BY id', (identity,))]
        from app.services import qc_inspection_sheet as sheet
        if item.get('entryId'):
            with sheet.store() as journal:
                entry=journal.execute('SELECT * FROM entries WHERE factory=? AND id=?',(factory,item['entryId'])).fetchone()
                if entry:
                    detail=sheet.unpack(journal,entry)
                    item.setdefault('improvement',detail['improvement'])
                    # Old text-only projections may omit references; recover only from this factory's stable entry.
                    item['photos']=item.get('photos') or detail['photos']
                else:
                    item['photos']=[]
        item['reportDate'] = summary_report_date(item, item.get('inspectionDate', ''))
        return with_schedule_dates(factory,[item])[0]


def parse_history(content):
    """Only established customer templates, with source coordinates retained for audit."""
    package = xml.Package(content)
    rows, warnings = [], []
    clients = package.client_names()
    for name in package.names():
        if name not in clients:
            warnings.append('未作为验货记录导入的工作表：' + name)
    for name in clients:
        second = package.second(name)
        group, header_seen = '', False
        source_rows = {int(r.get('r')): package.values(r) for r in package.rows(name)}
        shared = {}
        merges = package.sheet(name).find(xml.tag('mergeCells'))
        for merge in (() if merges is None else merges):
            c1, r1, c2, r2 = range_boundaries(merge.get('ref'))
            if c1 != c2 or c1 > 13 or r1 == r2:
                continue
            value = source_rows.get(r1, {}).get(c1, '')
            for number in source_rows:
                if r1 <= number <= r2:
                    shared.setdefault(number, {})[c1] = {'anchor': f'{get_column_letter(c1)}{r1}', 'range': merge.get('ref'), 'value': value}
        for row in sorted(package.rows(name), key=lambda r: int(r.get('r'))):
            vals = package.values(row)
            a = vals.get(1)
            if isinstance(a, (int, float)) and a > 30000 and not any(xml.normalized(vals.get(c)) for c in range(2, 14)):
                try:
                    group = from_excel(a, package.epoch).date().isoformat()
                except (ValueError, OverflowError, AttributeError):
                    group = ''
                header_seen = False
                continue
            if xml.normalized(a) == xml.normalized('Contract No.' if second else '客户'):
                header_seen = True
                continue
            if not header_seen:
                continue
            original_values = dict(vals)
            shared_cells = shared.get(int(row.get('r')), {})
            vals.update({column: cell['value'] for column, cell in shared_cells.items()})
            if not (vals.get(1 if second else 2) or vals.get(3 if second else 4)):
                continue
            # Never use a formula expression as an identity or guessed field value.
            formula_columns = [c.get('r') for c in row.findall(xml.tag('c')) if c.find(xml.tag('f')) is not None]
            customer = name.removesuffix('行验货') if second else text(vals.get(1)).strip()
            if second and name not in xml.TARGETS.values():
                warnings.append(f'{name}!{row.get("r")}：缺少明确客户映射，暂缓导入')
                continue
            item = {'inspectionDate': group, 'customer': customer, 'stockNo': '',
                    'poNo': text(vals.get(1 if second else 2)), 'country': text(vals.get(2 if second else 3)),
                    'productNo': text(vals.get(3 if second else 4)), 'productName': text(vals.get(4 if second else 5)),
                    'quantity': text(vals.get(5 if second else 6)), 'unitsPerCarton': text(vals.get(6 if second else 7)),
                    'cartonCount': text(vals.get(7 if second else 8)), 'result': text(vals.get(8 if second else 9)),
                    'remark': text(vals.get(11 if second else 10)), 'otherRemark': text(vals.get(13)),
                    'inspectionType': '待确认', 'status': 'unverified', 'sourceKind': 'history',
                    'sourceLabel': '历史工作簿', 'sourceSheet': name, 'sourceRow': int(row.get('r')),
                    'confirmedAt': '', 'confirmedBy': '', 'archivedAt': '',
                    'verificationIssues': ['历史资料没有可核验的审核/交接凭据', '来源未提供明确验货类型', '来源未提供库号'],
                    'originalCells': {str(k): v for k, v in original_values.items()}, 'formulaCells': formula_columns,
                    'sharedSourceCells': {str(k): v for k, v in shared_cells.items()}}
            if shared_cells:
                item['verificationIssues'].append('部分字段来自原表纵向合并单元格，为同组共享值，不能按明细重复累计')
            if not customer or not item['poNo'] or not item['productNo']:
                item['verificationIssues'].append('原表存在缺失身份字段，请按来源单元格核实')
            if not group:
                item['verificationIssues'].append('来源未提供可识别的验货日期')
            fingerprint = digest([name, group, {str(k): v for k, v in vals.items() if k <= 13}])
            rows.append({**item, 'fingerprint': fingerprint})
    if not rows:
        raise HTTPException(422, '没有识别到可导入的历史验货记录；原文件和现有汇总未改变')
    return rows, warnings


def preview(factory, actor, body):
    if not isinstance(body, dict) or set(body) != {'filename', 'content', 'mime'}:
        raise HTTPException(422, '历史导入参数无效')
    encoded = body['content']
    if not isinstance(encoded, str) or len(encoded) > 44 * 1024 * 1024:
        raise HTTPException(413, '历史文件过大，最多 32 MB')
    try:
        original = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise HTTPException(422, '历史文件内容无效') from None
    converted, receipt = upload.prepare(body['filename'], original, cumulative.template(factory), body['mime'])
    rows, warnings = parse_history(converted)
    # An exact known export already has immutable managed-row bindings. Reuse
    # those identities rather than importing the same entries as history again.
    with cumulative.store() as conn:
        known = conn.execute('SELECT content,metadata FROM versions WHERE factory=? AND length(content)=?', (factory, len(converted))).fetchall()
    for version in known:
        if bytes(version['content']) == converted:
            positions = {(b['sheet'], b['row']) for b in json.loads(version['metadata']).get('bindings', {}).values()}
            previous_count = len(rows)
            rows = [r for r in rows if (r['sourceSheet'], r['sourceRow']) not in positions]
            warnings.append(f'已识别系统管理记录 {previous_count-len(rows)} 条，由工作簿归档记录维护，未重复导入')
            break
    # Logical identity is independent of ZIP metadata, row positions and filename.
    document_key = digest(sorted(Counter(r['fingerprint'] for r in rows).items()))
    occurrences = Counter()
    for row in rows:
        occurrences[row['fingerprint']] += 1
        row['sourceKey'] = 'history:' + document_key + ':' + row['fingerprint'] + ':' + str(occurrences[row['fingerprint']])
    identity = uuid4().hex
    report = {'rows': rows, 'warnings': warnings, 'conversion': receipt, 'total': len(rows),
              'years': dict(sorted(Counter(r['inspectionDate'][:4] or '日期缺失' for r in rows).items())),
              'customers': sorted(set(r['customer'] for r in rows)), 'filename': body['filename']}
    with store(True) as conn:
        conn.execute('INSERT INTO batches VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                     (identity, factory, actor, body['filename'], sha256(original).hexdigest(), document_key,
                      original, dump(report), 'preview', workflow.now(), None, None))
    return batch_detail(factory, identity, actor)


def classify(conn, factory, report):
    existing = {r['source_key'] for r in conn.execute('SELECT source_key FROM records WHERE factory=? AND active=1', (factory,))}
    fingerprints = {r[0] for r in conn.execute("SELECT fingerprint FROM records WHERE factory=? AND active=1 AND fingerprint<>''", (factory,))}
    def business_identity(row):
        return tuple(text(row.get(k)) for k in ('customer', 'poNo', 'productNo')) + (row.get('inspectionDate') or row.get('archiveDate') or '',)
    identities = {business_identity(json.loads(r['payload'])) for r in conn.execute('SELECT payload FROM records WHERE factory=? AND active=1', (factory,))}
    counts = Counter()
    classified = []
    for row in report['rows']:
        state = 'duplicate' if row['sourceKey'] in existing else 'conflict' if row['fingerprint'] in fingerprints or business_identity(row) in identities else 'new'
        counts[state] += 1
        classified.append({**row, 'importState': state})
    return counts, classified


def batch_detail(factory, identity, actor=None):
    with store() as conn:
        batch = conn.execute('SELECT * FROM batches WHERE factory=? AND id=?', (factory, identity)).fetchone()
        if batch is None or actor is not None and batch['actor'] != actor:
            raise HTTPException(404, '历史预览不存在或不属于当前操作者')
        report = json.loads(batch['preview'])
        counts, rows = classify(conn, factory, report)
        return {'id': identity, 'filename': batch['filename'], 'status': batch['status'],
                'digest': batch['digest'], 'total': report['total'], 'years': report['years'],
                'customers': report['customers'], 'warnings': report['warnings'],
                'new': counts['new'], 'duplicate': counts['duplicate'], 'conflict': counts['conflict'],
                'samples': rows[:20], 'originalRetained': True}


def commit_history(factory, actor, identity):
    with store(True) as conn:
        batch = conn.execute('SELECT * FROM batches WHERE factory=? AND id=? AND actor=?', (factory, identity, actor)).fetchone()
        if batch is None:
            raise HTTPException(404, '历史预览不存在或不属于当前操作者')
        if batch['status'] == 'committed':
            return {'status': 'unchanged', 'id': identity, 'count': conn.execute('SELECT count(*) FROM records WHERE batch_id=? AND active=1', (identity,)).fetchone()[0]}
        if batch['status'] != 'preview':
            raise HTTPException(409, '该批次已回滚，请重新预览后导入')
        counts, rows = classify(conn, factory, json.loads(batch['preview']))
        for row in rows:
            if row['importState'] != 'new':
                continue
            item = {**row, 'sourceFilename': batch['filename'], 'sourceDigest': batch['digest'], 'historyBatchId': identity}
            upsert(conn, factory, row['sourceKey'], item, batch=identity, fingerprint=row['fingerprint'])
        conn.execute("UPDATE batches SET status='committed',committed_at=? WHERE id=?", (workflow.now(), identity))
        return {'status': 'committed', 'id': identity, 'count': counts['new'], 'duplicate': counts['duplicate'], 'conflict': counts['conflict']}
