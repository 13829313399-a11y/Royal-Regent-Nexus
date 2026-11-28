"""One approved, scoped photo-report projection for Monday weeks, months and years."""
from datetime import date
from hashlib import sha256
from fastapi import HTTPException
from app.services import qc_weekly_templates as weekly, qc_monthly_templates as monthly
from app.services.qc_inspection_summary import dump
from app.services.qc_approved_statistics import factory_label

MAX_REPORT_ROWS = 5000
def bounds(day, period, end_date=None):
    try:
        selected = date.fromisoformat(day)
        if selected.isoformat() != day or period not in ('weekly','monthly','yearly'):
            raise ValueError()
        if end_date is not None:
            end = date.fromisoformat(end_date)
            if period != 'weekly' or end.isoformat() != end_date or end < selected:
                raise ValueError()
            return day, end_date
    except (ValueError, TypeError):
        raise HTTPException(422, '请选择有效的报表周期和日期') from None
    if period in ('weekly','monthly'):
        return weekly.daily.period_bounds(day, period)
    return f'{selected.year:04}-01-01', f'{selected.year:04}-12-31'


def query(factory, day, period, customer='', *, workbook_preview=False, write_entry=None, end_date=None):
    factory_label(factory)
    start, end = bounds(day, period, end_date)
    # query streams a SQLite cursor; its existing 50k rows / 64MB snapshot guard
    # applies before any photos are read. Current lineage/approval rules are shared.
    snapshots = []
    source = weekly.approved.query(factory, {'from':start, 'to':end, 'customer':customer},
                                   _report_snapshots=snapshots)
    if source['excluded'].get('missingProjection') or source['excluded'].get('invalidLineage'):
        raise HTTPException(503, '已审核记录与验货汇总未对齐，请核对后重试')
    rows, customers, approved_versions = [], {}, []
    supplements = monthly.RecordSupplements(factory)
    for item, marker in snapshots:
        if item.get('reference') or item.get('referenceData') or item.get('testData'):
            continue
        row = monthly._detail(item, marker, len(rows)+1)
        key, info = weekly.approved._customer(item)
        record_day = row['values'][1]
        saved = supplements.month(record_day)
        approved_versions.append((item['id'], item['revision']))
        for index, field in row['editableFields'].items():
            value = saved.get((key, field), {}).get('value', '')
            row['values'][index] = weekly.daily._quantity(value) if index == 7 else value
        # A user's undo can clear the last supplemental issue in a row. Allow
        # redo against that same approved record without adding it to the export.
        previously_supplemented = item['id']==write_entry and any(
            saved.get((key, f'detail:{write_entry}:{field}'), {}).get('version', 0)
            for field in ('inspectionProblem','improvement','analysisReason'))
        tracking = monthly.design.tracking_row(row, include=previously_supplemented)
        if tracking is None:
            continue
        customers[key] = info
        rows.append(tracking)
        if len(rows) > MAX_REPORT_ROWS:
            raise HTTPException(422, '图文报表最多 5000 条，请指定客户或缩小周期后导出')
    rows.sort(key=lambda r:(r['values'][0], r['customerKey'], r['id']))
    revision = sha256(dump([factory, start, end, customer, rows]).encode()).hexdigest()
    workbook_revision = sha256(dump([factory, start, end, customer, approved_versions]).encode()).hexdigest()
    if workbook_preview:
        for row in rows:
            row['supplementCells'] = {
                col:supplements.cell(row['values'][0], row['customerKey'], row['revision'], field)
                for col,field in row['editableFields'].items()
            }
    return dict(date=day,dateFrom=start,dateTo=end,period=period,customer=customer,
                title=monthly.design.TRACKING_TITLE,sourceRevision=revision,workbookSourceRevision=workbook_revision,fields={},
                headers=monthly.design.TRACKING,groups=monthly.design.TRACKING_GROUPS,widths=monthly.design.TRACKING_WIDTHS,
                customers=sorted(customers.values(),key=lambda c:(c['name'],c['code'])),
                total=len(rows),tables={'issues':rows},maxRows=MAX_REPORT_ROWS,maxPhotoBytes=32*1024*1024)


def prepare(factory, owner, body):
    from app.services.qc_report_empty_cols import split_option
    body, enabled = split_option(body)
    from app.services import qc_monthly_excel as excel
    required={'date','period','customer','sourceRevision','photoQuality','allowPreviewFallback'}
    if (not isinstance(body,dict) or not required <= set(body) <= required | {'endDate'}
            or any(not isinstance(body[k],str) for k in set(body)-{'allowPreviewFallback'})
            or body['photoQuality'] not in {'preview','original'}
            or type(body['allowPreviewFallback']) is not bool):
        raise HTTPException(422,'图文导出参数不正确')
    data=query(factory,body['date'],body['period'],body['customer'],end_date=body.get('endDate'))
    data.update(hideEmptyCols=enabled, hiddenColumns=[])
    if data['sourceRevision']!=body['sourceRevision']:
        raise HTTPException(409,'验货记录或补录已变化，请刷新预览后重试')
    data.update(photoQuality=body['photoQuality'],allowPreviewFallback=body['allowPreviewFallback'],fallbackPhotos=[])
    content=excel.render(data,'issues',factory)
    fresh=query(factory,body['date'],body['period'],body['customer'],end_date=body.get('endDate'))
    if fresh['sourceRevision']!=data['sourceRevision']:
        raise HTTPException(409,'导出期间记录已变化，请刷新后重试')
    quality='mixed' if data['fallbackPhotos'] else body['photoQuality']
    result=excel.store_download(owner,content,'tracking',data['dateFrom'],data['dateTo'],quality,body['period'])
    result['fallbackCount']=len(data['fallbackPhotos'])
    result['hiddenColumns']=data['hiddenColumns']
    return result
