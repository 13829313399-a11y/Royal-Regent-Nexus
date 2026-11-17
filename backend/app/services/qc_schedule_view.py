"""Date-scoped schedule display; historical task sources remain unrestricted."""
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException

from app.services import qc_workflow


def business_date():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat()


def listing(db, factory, *, date_from='', date_to=''):
    start = qc_workflow.day(date_from)
    end = qc_workflow.day(date_to)
    if start and end and start > end:
        raise HTTPException(422, '开始日期不能晚于结束日期')
    today = business_date()
    explicit = bool(start or end)
    lower = start if explicit else today
    payload = qc_workflow.sources(db, factory)
    rows = []
    for row in payload['items']:
        first = qc_workflow.source_date(row.get('dateFrom'))
        last = qc_workflow.source_date(row.get('dateTo') or row.get('dateFrom'))
        if not first or not last or first > last:
            continue
        if (lower and last < lower) or (end and first > end):
            continue
        rows.append(row)
    return {**payload, 'items': rows,
            'dateScope': {'mode': 'range' if explicit else 'upcoming',
                          'from': lower, 'to': end, 'businessDate': today,
                          'timezone': 'Asia/Shanghai'}}
