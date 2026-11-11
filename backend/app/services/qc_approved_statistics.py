"""Read-only statistics over the current inline approval and its summary projection.

No store(), reconciliation, migration, historical fallback or legacy-record writes.
The stable counting unit is an approved entry, not an inferred inspection event.
"""
from collections import Counter, defaultdict
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import re
import sqlite3

from fastapi import HTTPException
from app.core.config import settings
from app.services import qc_inspection_summary as summary

MAX_ROWS = 50000
MAX_CUSTOMERS = 1000
MAX_SNAPSHOT_BYTES = 64 * 1024 * 1024


def _date(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return ''
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        return ''


def _filters(params):
    if set(params) - {'from', 'to', 'customer', 'company'}:
        raise HTTPException(422, '统计筛选参数不正确')
    start, end, customer = (params.get(k, '') for k in ('from', 'to', 'customer'))
    if any(v and not _date(v) for v in (start, end)) or (start and end and start > end):
        raise HTTPException(422, '请提供有效的最终验货日期范围')
    if customer and not re.fullmatch(r'[a-f0-9]{64}', customer):
        raise HTTPException(422, '客户筛选不正确')
    return start, end, customer


def _totals(counts):
    decided = counts['PASS'] + counts['FAIL']
    return dict(total=sum(counts.values()), PASS=counts['PASS'], FAIL=counts['FAIL'],
                PENDING=counts['PENDING'], LG=counts['LG'], decided=decided,
                other={k: v for k, v in sorted(counts.items()) if k not in {'PASS', 'FAIL', 'PENDING', 'LG'}},
                passRate=round(100 * counts['PASS'] / decided, 4) if decided else None)


def _customer(item):
    source = item.get('sourceRecord') or {}
    if not isinstance(source, dict):
        raise ValueError('sourceRecord')
    # Same captured source identity as the accepted workbench, never fuzzy matching.
    code = str(source.get('customerCode') or '').strip()
    name = str(item.get('customer') or '').strip()
    key = sha256(summary.dump([code, name]).encode()).hexdigest()
    return key, dict(key=key, name=name, code=code, label=(name or '未填写客户') + ' · ' + (code or '未编码'))


def _valid(row, factory):
    """Fail closed on broken lineage; never repair a read or infer missing provenance."""
    item, payload, base = (json.loads(row[k]) for k in ('approved_snapshot', 'payload', 'base'))
    if not all(isinstance(v, dict) for v in (item, payload, base)):
        raise ValueError('snapshot shape')
    key = 'entry:' + row['entry_id']
    identity = sha256((factory + '\0' + key).encode()).hexdigest()[:32]
    if (row['source_key'] != key or row['id'] != identity or item.get('id') != row['entry_id']
            or item.get('sourceKey') != row['entry_source_key'] or item.get('reviewState') != 'approved'
            or item.get('revision') != row['revision'] or item.get('result') != row['entry_result']):
        raise ValueError('current identity')
    # Use the existing pure projection constructor, without its store/recovery path.
    try:
        expected = summary.review_item(item)
    except HTTPException as exc:
        raise ValueError('invalid frozen date') from exc
    expected.update(id=identity, factory=factory, firstSeenAt=payload.get('firstSeenAt'))
    if expected != payload or any(row[column] != expected.get(field, '') for column, field in (
            ('inspection_date', 'inspectionDate'), ('result', 'result'), ('customer', 'customer'))):
        raise ValueError('projection mismatch')
    final = expected['inspectionDate']
    if final and _date(final) != final:
        raise ValueError('invalid frozen date')
    if 'inspectionDateSource' in item:
        marker = item['inspectionDateSource']
        actual, planned = _date(item.get('actualDate')), _date(item.get('dateFrom'))
        if not ((marker == 'qc_manual' and actual and final == actual)
                or (marker == 'schedule' and not actual and planned and final == planned)
                or (marker is None and not final and not actual and not planned)):
            raise ValueError('frozen date source')
    # Match all current valid summary records, including test/reference-labelled
    # entries. Their source labels do not change whether an inspection occurred.
    for source in (item, base, item.get('sourceRecord', {}), base.get('sourceRecord', {})):
        if not isinstance(source, dict):
            raise ValueError('source shape')
    result = item.get('result')
    if not isinstance(result, str) or len(result) > 64:
        raise ValueError('result shape')
    return item, final, result or '(空值)'


def query(factory, params, *, _records=None, _report_snapshots=None):
    start, end, wanted = _filters(params)
    root = Path(settings.qc_department_data_dir).resolve()
    journal = root / '_inspection_sheet' / 'inspections.sqlite3'
    projection = root / '_summary' / 'summaries.sqlite3'
    counts, months, customers, excluded = Counter(), defaultdict(Counter), {}, Counter()
    unknown_date = candidates = eligible = snapshot_bytes = 0
    # A new factory may have no approvals yet. Missing stores are not initialized by GET.
    if not journal.exists() and not projection.exists():
        return _response(factory, start, end, wanted, counts, months, customers, excluded, 0, 0, 0, False)
    if not journal.is_file() or not projection.is_file():
        raise HTTPException(503, '批准记录与汇总尚未就绪，请先核对汇总；统计未自动修复数据')
    conn = None
    try:
        conn = sqlite3.connect(journal.as_uri() + '?mode=ro', uri=True, timeout=5)
        conn.row_factory = sqlite3.Row
        conn.execute('ATTACH DATABASE ? AS qsum', (projection.as_uri() + '?mode=ro',))
        conn.execute('PRAGMA query_only=ON')
        conn.execute('BEGIN')
        missing = conn.execute('''SELECT count(*) FROM entries e JOIN entry_details d ON d.entry_id=e.id
            WHERE e.factory=? AND d.flow_version=2 AND d.review_state='approved'
            AND NOT EXISTS (SELECT 1 FROM qsum.records s WHERE s.factory=e.factory
              AND s.source_key='entry:'||e.id AND s.active=1 AND s.status='approved')''', (factory,)).fetchone()[0]
        if missing:
            excluded['missingProjection'] = missing
        # One joined read holds both stores in the same read transaction. Only one
        # current row per entry is possible; events and historical changes never join.
        rows = conn.execute('''SELECT s.*, e.id AS entry_id, e.base, e.revision,
            e.result AS entry_result, e.source_key AS entry_source_key,
            d.approved_snapshot, d.review_state, d.flow_version
            FROM qsum.records s LEFT JOIN entries e
              ON s.source_key='entry:'||e.id AND s.factory=e.factory
            LEFT JOIN entry_details d ON d.entry_id=e.id
            WHERE s.factory=? AND s.active=1 AND s.status='approved'
            ORDER BY s.id LIMIT ?''', (factory, MAX_ROWS + 1))
        for row in rows:
            candidates += 1
            if candidates > MAX_ROWS:
                raise HTTPException(503, '统计范围超过试点容量，未返回部分统计；请评估服务端聚合后再扩容')
            snapshot_bytes += sum(len((row[k] or '').encode('utf-8')) for k in ('payload','base','approved_snapshot'))
            if snapshot_bytes > MAX_SNAPSHOT_BYTES:
                raise HTTPException(503, '统计快照超过试点读取容量，未返回部分统计')
            if row['flow_version'] != 2 or row['review_state'] != 'approved' or not row['approved_snapshot']:
                excluded['notCurrentInlineApproval'] += 1
                continue
            try:
                valid = _valid(row, factory)
                item, final, result = valid
                key, customer = _customer(item)
            except (ValueError, TypeError, KeyError):
                excluded['invalidLineage'] += 1
                continue
            eligible += 1
            customers[key] = customer
            if _records is not None or _report_snapshots is not None:
                report_date, date_source = summary.report_date(item, final)
            if _records is not None:
                _records.append(dict(id=item['id'], date=report_date,
                    usesScheduleDate=date_source == 'schedule',
                    customerKey=key,
                    customer=customer['name'], customerCode=customer['code'], result=result,
                    poNo=str(item.get('poNo') or ''), productName=str(item.get('productName') or ''),
                    inspectionProblem=str(item.get('inspectionProblem') or ''), remark=str(item.get('remark') or '')))
            if len(customers) > MAX_CUSTOMERS:
                raise HTTPException(503, '客户数量超过试点容量，未返回部分统计')
            scoped_date = report_date if _report_snapshots is not None else final
            if (wanted and key != wanted) or ((start or end) and not scoped_date):
                continue
            if (start and scoped_date < start) or (end and scoped_date > end):
                continue
            if _report_snapshots is not None:
                _report_snapshots.append((item, date_source))
            counts[result] += 1
            if scoped_date:
                months[scoped_date[:7]][result] += 1
            else:
                unknown_date += 1
        conn.rollback()
    except sqlite3.Error as exc:
        raise HTTPException(503, '只读统计暂不可用，请核对汇总状态后重试；未自动迁移或修复数据') from exc
    finally:
        if conn is not None:
            conn.close()
    return _response(factory, start, end, wanted, counts, months, customers, excluded,
                     unknown_date, candidates, eligible, True)


def _response(factory, start, end, wanted, counts, months, customers, excluded,
              unknown_date, candidates, eligible, ready):
    return dict(factory=factory, ready=ready, source='current-inline-approved-summary-v1',
                countingUnit='approved-entry', formula='PASS / (PASS + FAIL)',
                filters={'from': start, 'to': end, 'customer': wanted}, totals=_totals(counts),
                months=[dict(month=k, **_totals(v)) for k, v in sorted(months.items())],
                customers=sorted(customers.values(), key=lambda x: (x['name'], x['code'])),
                missingDate=unknown_date, candidates=candidates, eligible=eligible, excluded=dict(excluded),
                customerUnavailable=bool(wanted and wanted not in customers))


def report(factory, params):
    """One validated read snapshot supplies facets, aggregates and paged details.

    Result/page affect details only; no client-side page can change the denominator.
    Existing query() callers and their date-range contract remain unchanged.
    """
    if set(params) - {'year', 'month', 'day', 'customer', 'result', 'page', 'company'}:
        raise HTTPException(422, '统计筛选参数不正确')
    year, month, day, customer = (params.get(k, '') for k in ('year', 'month', 'day', 'customer'))
    if year and (not re.fullmatch(r'[0-9]{4}', year) or not 1 <= int(year) <= 9999):
        raise HTTPException(422, '年份不正确')
    for value, limit in ((month, 12), (day, 31)):
        if value and (not re.fullmatch(r'[0-9]{1,2}', value) or not 1 <= int(value) <= limit):
            raise HTTPException(422, '月份或日期不正确')
    if (month and not year) or (day and not month):
        raise HTTPException(422, '请按年、月、日选择')
    if month:
        month = str(int(month))
    if day:
        day = str(int(day))
        if not _date(f'{year}-{int(month):02d}-{int(day):02d}'):
            raise HTTPException(422, '日期不存在')
    if customer and not re.fullmatch(r'[a-f0-9]{64}', customer):
        raise HTTPException(422, '客户筛选不正确')
    result = params.get('result', 'FAIL')
    if result not in {'ALL', 'PASS', 'FAIL', 'PENDING', 'LG', 'OTHER'}:
        raise HTTPException(422, '结果筛选不正确')
    page = params.get('page', '1')
    if not re.fullmatch(r'[1-9][0-9]{0,6}', page):
        raise HTTPException(422, '页码不正确')
    rows = []
    source = query(factory, {}, _records=rows)
    notices = []
    years = sorted({r['date'][:4] for r in rows if r['date']}, reverse=True)
    if year and year not in years:
        notices.append('原年份已无数据，已切换到最近有数据的年份。')
        year, month, day = '', '', ''
    year = year or (years[0] if years else '')
    year_rows = [r for r in rows if not year or r['date'].startswith(year + '-')]
    if customer and not any(r['customerKey'] == customer for r in year_rows):
        notices.append('该年份已无所选客户的数据，已重置客户筛选。')
        customer = ''
    customer_rows = [r for r in year_rows if not customer or r['customerKey'] == customer]
    months = sorted({str(int(r['date'][5:7])) for r in customer_rows if r['date']}, key=int)
    if month and month not in months:
        notices.append('所选月份已无数据，已重置为全年。')
        month, day = '', ''
    month_rows = [r for r in customer_rows if not month or r['date'][5:7] == month.zfill(2)]
    days = sorted({str(int(r['date'][8:10])) for r in month_rows if r['date']}, key=int) if month else []
    if day and day not in days:
        notices.append('所选日期已无数据，已重置为全部日期。')
        day = ''
    selected = [r for r in month_rows if not day or r['date'][8:10] == day.zfill(2)]
    # Customer options reflect the selected date scope, not a master-data catalogue.
    available_customers = {r['customerKey'] for r in year_rows
        if (not month or r['date'][5:7] == month.zfill(2))
        and (not day or r['date'][8:10] == day.zfill(2))}
    customers = [c for c in source['customers'] if c['key'] in available_customers]
    grouped = defaultdict(Counter)
    for row in selected:
        if row['date']:
            grouped[row['date'][:7]][row['result']] += 1
    details = [r for r in selected if result == 'ALL' or r['result'] == result
        or (result == 'OTHER' and r['result'] not in {'PASS', 'FAIL', 'PENDING', 'LG'})]
    details.sort(key=lambda r: (r['date'], r['id']), reverse=True)
    page_size = 5
    pages = max(1, (len(details) + page_size - 1) // page_size)
    page = min(int(page), pages)
    return dict(factory=factory, source=source['source'], ready=source['ready'],
        filters=dict(year=year, month=month, day=day, customer=customer, result=result),
        options=dict(years=years, months=months, days=days, customers=customers),
        totals=_totals(Counter(r['result'] for r in selected)),
        months=[dict(month=k, **_totals(v)) for k, v in sorted(grouped.items())],
        details=dict(items=details[(page-1)*page_size:page*page_size], total=len(details),
            page=page, pageSize=page_size, pages=pages),
        scheduleDateCount=sum(r['usesScheduleDate'] for r in selected),
        missingDate=sum(not r['date'] for r in rows), excluded=source['excluded'], notices=notices)
