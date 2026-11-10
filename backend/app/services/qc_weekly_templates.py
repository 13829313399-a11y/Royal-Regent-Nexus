"""Three verified weekly layouts; approved records read-only, weekly supplements separate."""
from contextlib import contextmanager, closing
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from fastapi import HTTPException
from app.core.config import settings
from app.services import qc_approved_statistics as approved, qc_daily_report as daily
from app.services.qc_inspection_summary import confirmed_date, report_date, dump, text

TEMPLATES = json.loads((Path(__file__).resolve().parents[1] / 'templates/qc-weekly/templates.json').read_text())
FIELDS = {'returns', 'returnReason', 'hongKongContact', 'weeklyRemark', 'reworkA0D', 'handling'}
DETAIL_FIELDS = {
    3: 'contractNo', 4: 'country', 5: 'productNo', 6: 'productName',
    7: 'quantity', 8: 'unitsPerCarton', 9: 'cartonCount', 11: 'reportStatus',
    12: 'production', 13: 'institution', 14: 'inspectionProblem',
    15: 'firstResponsible', 16: 'secondResponsible', 17: 'remark',
}
DETAIL_FIELD = re.compile(r'detail:([a-f0-9]{32}):([a-zA-Z]+)')
SCHEMA = '''
CREATE TABLE IF NOT EXISTS cells (
 factory TEXT NOT NULL, week TEXT NOT NULL, customer TEXT NOT NULL, field TEXT NOT NULL,
 value TEXT NOT NULL, version INTEGER NOT NULL, actor TEXT NOT NULL, updated_at TEXT NOT NULL,
 PRIMARY KEY(factory,week,customer,field));
CREATE TABLE IF NOT EXISTS writes (
 factory TEXT NOT NULL, actor TEXT NOT NULL, request_key TEXT NOT NULL, fingerprint TEXT NOT NULL,
 response TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(factory,actor,request_key));
CREATE TABLE IF NOT EXISTS changes (
 id INTEGER PRIMARY KEY, factory TEXT NOT NULL, week TEXT NOT NULL, customer TEXT NOT NULL,
 field TEXT NOT NULL, old_value TEXT NOT NULL, new_value TEXT NOT NULL, version INTEGER NOT NULL,
 actor TEXT NOT NULL, created_at TEXT NOT NULL);
'''


def _factory(factory):
    if factory != 'huaxing':
        raise HTTPException(404, '当前厂区未配置华兴周报模板')


def _path():
    return Path(settings.qc_department_data_dir).resolve() / '_weekly_reports' / 'weekly.sqlite3'


@contextmanager
def _store():
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        conn.execute('BEGIN IMMEDIATE')
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _supplements(factory, week):
    path = _path()
    if not path.exists():
        return {}
    try:
        with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=10)) as conn:
            conn.row_factory = sqlite3.Row
            return {(r['customer'], r['field']): dict(value=r['value'], version=r['version'])
                    for r in conn.execute('SELECT * FROM cells WHERE factory=? AND week=?', (factory, week))}
    except sqlite3.Error as exc:
        raise HTTPException(503, '周报补充数据读取失败，请重试；未返回空白覆盖已保存内容') from exc


def _source(factory, day, period='weekly'):
    _factory(factory)
    start, end = daily.period_bounds(day, period)
    snapshots = []
    source = approved.query(factory, {'from': start, 'to': end}, _report_snapshots=snapshots)
    if source['excluded'].get('missingProjection') or source['excluded'].get('invalidLineage'):
        raise HTTPException(503, '已审核记录与验货汇总未对齐，请核对后重试')
    # Preserve precisely the existing daily/weekly report population.
    snapshots = [(item, marker) for item, marker in snapshots
                 if not (item.get('reference') or item.get('referenceData') or item.get('testData'))]
    snapshots.sort(key=lambda pair: (text(pair[0].get('customer')), report_date(pair[0], confirmed_date(pair[0]))[0],
                                    text(pair[0].get('poNo')), pair[0]['id']))
    revision = sha256(dump([factory, start, end, snapshots]).encode()).hexdigest()
    return start, end, snapshots, revision


def _detail(item, marker, index):
    source, execution = item.get('sourceRecord') or {}, item.get('inspectionExecution') or {}
    day, _ = report_date(item, confirmed_date(item))
    values = [index, day, text(item.get('customer')), text(item.get('contractNo', source.get('contractNo'))),
              text(item.get('country')), text(item.get('productNo')), text(item.get('productName')),
              daily._quantity(item.get('quantity')), text(item.get('unitsPerCarton')), text(item.get('cartonCount')),
              text(item.get('result')), text(item.get('reportStatus')), text(item.get('production')),
              text(execution.get('institution') or item.get('agency')), text(item.get('inspectionProblem')),
              text(item.get('firstResponsible')), text(item.get('secondResponsible')),
              text(item.get('otherRemark') or item.get('remark'))]
    return dict(id=item['id'], customerKey=approved._customer(item)[0], revision=item.get('revision'), values=values, dateSource=marker,
                actualDate=text(item.get('actualDate')), plannedDate=text(item.get('dateFrom')),
                poNo=text(item.get('poNo')))


def _blank_detail_fields(row):
    return {index: f'detail:{row["id"]}:{field}' for index, field in DETAIL_FIELDS.items()
            if isinstance(row['values'][index], str) and not row['values'][index].strip()}


def _owners(items):
    names = (text(item.get(field)).strip() for item, _ in items
             for field in ('firstResponsible', 'secondResponsible'))
    return ' / '.join(dict.fromkeys(name for name in names if name))


def _rate(returns, count, qualified=False):
    if returns in ('', None, '待补全') or not count:
        return ''
    return f'{(1 - int(returns)/count if qualified else int(returns)/count)*100:.1f}%'


def _totals(headers, rows):
    values = [''] * len(headers)
    values[headers.index('客户')] = '合计'
    count_index, return_index = headers.index('本周验货次数'), headers.index('退货次数')
    count = sum(row['values'][count_index] for row in rows)
    returns = (sum(int(row['values'][return_index]) for row in rows)
               if all(row['values'][return_index] != '' for row in rows) else '待补全')
    values[count_index], values[return_index] = count, returns
    rate_index = headers.index('合格率' if '合格率' in headers else '退货率')
    values[rate_index] = _rate(returns, count, '合格率' in headers)
    return values


def query(factory, day, customer=''):
    if customer and (not isinstance(customer, str) or not re.fullmatch('[a-f0-9]{64}', customer)):
        raise HTTPException(422, '客户筛选不正确')
    start, end, snapshots, revision = _source(factory, day)
    saved = _supplements(factory, start)
    groups = {}
    for item, marker in snapshots:
        key, info = approved._customer(item)
        groups.setdefault(key, {**info, 'items': []})['items'].append((item, marker))
    details, grouped, internal, footer = [], [], [], []
    fields = {}
    customers = sorted(groups.values(), key=lambda g: (g['name'], g['code']))
    for group in customers:
        key, items = group['key'], group['items']
        if customer and customer != key:
            continue
        def supplement(field):
            return saved.get((key, field), dict(value='', version=0))

        supplements = {field: supplement(field) for field in sorted(FIELDS)}
        fields[key] = supplements
        val = lambda field: supplements[field]['value']
        count, returns = len(items), val('returns')
        owners = _owners(items)
        owner_fields = {} if owners else {5: 'responsible'}
        if owner_fields:
            supplements['responsible'] = supplement('responsible')
            owners = val('responsible')
        for item, marker in items:
            row = _detail(item, marker, len(details)+1)
            row['editableFields'] = _blank_detail_fields(row)
            for index, field in row['editableFields'].items():
                supplements[field] = supplement(field)
                value = val(field)
                row['values'][index] = daily._quantity(value) if index == 7 else value
            details.append(row)
        common = ['华兴', group['name'], count, returns, _rate(returns, count), val('returnReason'), val('hongKongContact')]
        grouped.append(dict(id=key, values=common + [val('weeklyRemark')]))
        footer.append(dict(id=key, values=common + [val('reworkA0D'), val('weeklyRemark')]))
        internal.append(dict(id=key, values=[group['name'], count, returns, _rate(returns, count, True),
                        val('returnReason'), owners, val('handling'), val('weeklyRemark')], editableFields=owner_fields))
    specifications = deepcopy(TEMPLATES)
    tables = dict(detail=details, group=grouped, internal=internal, footer=footer)
    totals = {spec['id']: _totals(spec['headers'], tables[spec['id']]) for spec in specifications if spec['id'] != 'detail'}
    return dict(date=day, dateFrom=start, dateTo=end, sourceRevision=revision, templates=specifications,
                customers=[{k: g[k] for k in ('key', 'name', 'code', 'label')} for g in customers],
                customer=customer, tables=tables, totals=totals, fields=fields, total=len(details),
                scheduleCount=sum(r['dateSource'] == 'schedule' for r in details),
                countingUnit='approved-entry', recordFieldsReadOnly=True)


def save(factory, actor, body):
    _factory(factory)
    keys = {'date', 'customerKey', 'field', 'value', 'baseVersion', 'sourceRevision', 'requestKey'}
    if not isinstance(body, dict) or set(body) != keys:
        raise HTTPException(422, '周报保存参数不正确')
    field = body['field']
    detail = DETAIL_FIELD.fullmatch(field) if isinstance(field, str) else None
    if (not isinstance(field, str) or (field not in FIELDS and field != 'responsible'
            and not (detail and detail[2] in DETAIL_FIELDS.values())) or not isinstance(body['customerKey'], str)
            or not re.fullmatch('[a-f0-9]{64}', body['customerKey'])
            or type(body['baseVersion']) is not int or body['baseVersion'] < 0
            or not isinstance(body['requestKey'], str) or not re.fullmatch('[a-zA-Z0-9-]{16,80}', body['requestKey'])
            or not isinstance(body['sourceRevision'], str) or not re.fullmatch('[a-f0-9]{64}', body['sourceRevision'])
            or not isinstance(body['value'], str) or len(body['value']) > 4000):
        raise HTTPException(422, '周报字段或版本不正确')
    if body['field'] == 'returns' and not re.fullmatch(r'(?:0|[1-9][0-9]{0,8})?', body['value']):
        raise HTTPException(422, '退货次数须为空白或非负整数')
    if detail and detail[2] == 'quantity' and not re.fullmatch(r'(?:[0-9]{1,15}(?:\.[0-9]{1,4})?)?', body['value']):
        raise HTTPException(422, '数量须为空白或非负数字，最多四位小数')
    fingerprint = sha256(dump(body).encode()).hexdigest()
    start, _, snapshots, revision = _source(factory, body['date'])
    customer_items = [(item, marker) for item, marker in snapshots
                      if approved._customer(item)[0] == body['customerKey']]
    actor_id = str(actor['id'])
    with _store() as conn:
        old_request = conn.execute('SELECT * FROM writes WHERE factory=? AND actor=? AND request_key=?',
                                   (factory, actor_id, body['requestKey'])).fetchone()
        if old_request:
            if old_request['fingerprint'] != fingerprint:
                raise HTTPException(409, '保存请求标识已用于不同内容，请重新核对')
            return json.loads(old_request['response'])
        if revision != body['sourceRevision'] or not customer_items:
            raise HTTPException(409, dict(code='source_changed', message='本周验货记录已变化，请刷新核对后重试；补充草稿仍保留'))
        if detail:
            record = next(((item, marker) for item, marker in customer_items if item['id'] == detail[1]), None)
            if not record or field not in _blank_detail_fields(_detail(*record, 1)).values():
                raise HTTPException(422, '只能补录本客户的空白周报明细')
        if field == 'responsible' and _owners(customer_items):
            raise HTTPException(422, '已有审核责任人，不能在周报中覆盖')
        identity = (factory, start, body['customerKey'], field)
        previous = conn.execute('SELECT * FROM cells WHERE factory=? AND week=? AND customer=? AND field=?', identity).fetchone()
        current = dict(value=previous['value'], version=previous['version']) if previous else dict(value='', version=0)
        if current['version'] != body['baseVersion']:
            raise HTTPException(409, dict(code='cell_conflict', message='此单元格已被其他操作修改，请比较后选择保留内容', current=current))
        stamp = datetime.now(timezone.utc).isoformat()
        version = current['version'] + (body['value'] != current['value'])
        result = dict(customerKey=body['customerKey'], field=body['field'], value=body['value'], version=version)
        if body['value'] != current['value']:
            conn.execute('INSERT INTO cells VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(factory,week,customer,field) DO UPDATE SET value=excluded.value,version=excluded.version,actor=excluded.actor,updated_at=excluded.updated_at',
                         (*identity, body['value'], version, actor_id, stamp))
            conn.execute('INSERT INTO changes(factory,week,customer,field,old_value,new_value,version,actor,created_at) VALUES(?,?,?,?,?,?,?,?,?)',
                         (*identity, current['value'], body['value'], version, actor_id, stamp))
        conn.execute('INSERT INTO writes VALUES(?,?,?,?,?,?)', (factory, actor_id, body['requestKey'], fingerprint, dump(result), stamp))
        return result
