"""One approved, scoped photo-report projection for Sunday weeks, months and years."""
from datetime import date, timedelta
from hashlib import sha256
from fastapi import HTTPException
from app.services import qc_weekly_templates as weekly, qc_monthly_templates as monthly
from app.services.qc_inspection_summary import dump

MAX_REPORT_ROWS = 5000
PERIOD_TITLES = {'weekly':'每周验货问题图文记录表', 'monthly':'月度验货问题图文记录表',
                 'yearly':'年度验货问题图文记录表'}


def bounds(day, period):
    try:
        selected = date.fromisoformat(day)
        if selected.isoformat() != day or period not in PERIOD_TITLES:
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, '请选择有效的报表周期和日期') from None
    if period == 'weekly':
        start = selected - timedelta(days=(selected.weekday()+1) % 7)
        return start.isoformat(), (start+timedelta(days=6)).isoformat()
    if period == 'monthly':
        return weekly.daily.period_bounds(day, 'monthly')
    return f'{selected.year:04}-01-01', f'{selected.year:04}-12-31'


def query(factory, day, period, customer=''):
    weekly._factory(factory)
    start, end = bounds(day, period)
    # query streams a SQLite cursor; its existing 50k rows / 64MB snapshot guard
    # applies before any photos are read. Current lineage/approval rules are shared.
    snapshots = []
    source = weekly.approved.query(factory, {'from':start, 'to':end, 'customer':customer},
                                   _report_snapshots=snapshots)
    if source['excluded'].get('missingProjection') or source['excluded'].get('invalidLineage'):
        raise HTTPException(503, '已审核记录与验货汇总未对齐，请核对后重试')
    rows, customers, saved_months = [], {}, {}
    for item, marker in snapshots:
        if item.get('reference') or item.get('referenceData') or item.get('testData'):
            continue
        row = monthly._detail(item, marker, len(rows)+1)
        key, info = weekly.approved._customer(item)
        month = row['values'][1][:7]+'-01'
        if month not in saved_months:
            saved_months[month] = monthly._supplements(factory, month)
        saved = saved_months[month]
        for index, field in row['editableFields'].items():
            value = saved.get((key, field), {}).get('value', '')
            row['values'][index] = weekly.daily._quantity(value) if index == 7 else value
        if not str(row['values'][14]).strip():
            continue
        customers[key] = info
        rows.append(monthly._project(row, monthly.ISSUES))
        if len(rows) > MAX_REPORT_ROWS:
            raise HTTPException(422, '图文报表最多 5000 条，请指定客户或缩小周期后导出')
    rows.sort(key=lambda r:(r['values'][0], r['customerKey'], r['id']))
    revision = sha256(dump([factory, start, end, customer, rows]).encode()).hexdigest()
    return dict(date=day,dateFrom=start,dateTo=end,period=period,customer=customer,
                title=PERIOD_TITLES[period],sourceRevision=revision,fields={},
                headers=monthly.TEMPLATES[2]['headers'],
                customers=sorted(customers.values(),key=lambda c:(c['name'],c['code'])),
                total=len(rows),tables={'issues':rows},maxRows=MAX_REPORT_ROWS,maxPhotoBytes=32*1024*1024)


def prepare(factory, owner, body):
    from app.services import qc_monthly_excel as excel
    required={'date','period','customer','sourceRevision','photoQuality','allowPreviewFallback'}
    if (not isinstance(body,dict) or set(body)!=required
            or any(not isinstance(body[k],str) for k in required-{'allowPreviewFallback'})
            or body['photoQuality'] not in {'preview','original'}
            or type(body['allowPreviewFallback']) is not bool):
        raise HTTPException(422,'图文导出参数不正确')
    data=query(factory,body['date'],body['period'],body['customer'])
    if data['sourceRevision']!=body['sourceRevision']:
        raise HTTPException(409,'验货记录或补录已变化，请刷新预览后重试')
    data.update(photoQuality=body['photoQuality'],allowPreviewFallback=body['allowPreviewFallback'],fallbackPhotos=[])
    content=excel.render(data,'issues',factory)
    fresh=query(factory,body['date'],body['period'],body['customer'])
    if fresh['sourceRevision']!=data['sourceRevision']:
        raise HTTPException(409,'导出期间记录已变化，请刷新后重试')
    quality='mixed' if data['fallbackPhotos'] else body['photoQuality']
    result=excel.store_download(owner,content,'issues',data['dateFrom'],data['dateTo'],quality,body['period'])
    result['fallbackCount']=len(data['fallbackPhotos'])
    return result
