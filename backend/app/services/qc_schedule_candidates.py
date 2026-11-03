"""Read-only date gate for NEW automatic intake, never for historical lists/imports.

There is no scheduled QC intake worker. Its future caller can consume accepted,
pending and expired candidates without deleting or modifying the source records.
"""
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import re
from zoneinfo import ZoneInfo

from openpyxl.utils.datetime import from_excel, CALENDAR_WINDOWS_1900

SHANGHAI = ZoneInfo('Asia/Shanghai')


def business_day(value, epoch=CALENDAR_WINDOWS_1900):
    if isinstance(value, datetime):
        return (value.astimezone(SHANGHAI) if value.tzinfo else value).date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        try:
            parsed = from_excel(float(value), epoch)
            return parsed.date() if isinstance(parsed, datetime) else None
        except (ValueError, OverflowError, TypeError):
            return None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    match = re.fullmatch(r'(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?', raw)
    if match:
        try:
            return date(*map(int, match.groups()))
        except ValueError:
            return None
    try:
        moment = datetime.fromisoformat(raw.replace('Z', '+00:00'))
        return business_day(moment)
    except ValueError:
        return None


def filter_new_candidates(rows, *, today=None, epoch=CALENDAR_WINDOWS_1900):
    """A list of explicit dates is supported; ambiguous/partially expired ranges wait.

    Each result retains the full untouched source. eligibleDates tells the future
    intake caller which distinct dates are allowed; no task identities are invented.
    """
    current = today if isinstance(today, date) and not isinstance(today, datetime) else (
        business_day(today) if today is not None else datetime.now(SHANGHAI).date())
    if current is None:
        raise ValueError('Invalid Shanghai business date')
    result = {'businessDate': current.isoformat(), 'timezone': 'Asia/Shanghai',
              'accepted': [], 'pending': [], 'expired': []}
    for source in rows:
        raw = source.get('dateFrom')
        parts = re.split(r'[,，;；\n]+', raw) if isinstance(raw, str) else [raw]
        dates = [business_day(part, epoch) for part in parts]
        item = {'source': deepcopy(source), 'eligibleDates': [], 'reason': ''}
        end_raw = source.get('dateTo')
        # A copied multi-date string is not a range end.
        end = business_day(end_raw, epoch) if end_raw not in (None, '', raw) else None
        if not dates or any(d is None for d in dates) or (end_raw not in (None, '', raw) and end is None):
            item['reason'] = '验货日期为空或无法明确解析，待核对来源；未使用走货日期替代'
            result['pending'].append(item)
            continue
        if end and (len(dates) != 1 or end < dates[0]):
            item['reason'] = '多阶段日期与结束日期冲突，或日期范围倒置'
            result['pending'].append(item)
            continue
        if end and dates[0] < current <= end:
            item['reason'] = '日期范围跨越今天且包含过期日期，待明确本次验货日期'
            result['pending'].append(item)
            continue
        upcoming = sorted({d.isoformat() for d in dates if d >= current})
        if upcoming:
            item['eligibleDates'] = upcoming
            item['reason'] = '仅接收今天及未来的明确验货日期'
            result['accepted'].append(item)
        else:
            item['reason'] = '验货日期早于北京时间当天；仅跳过本次新候选，来源保留'
            result['expired'].append(item)
    return result
