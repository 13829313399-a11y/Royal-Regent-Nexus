"""Project record-linked report supplements without rewriting approval snapshots."""
from contextlib import closing
from datetime import date, timedelta
import logging
import re
import sqlite3

from app.services import qc_approved_statistics as approved
from app.services import qc_monthly_templates as monthly, qc_weekly_templates as weekly

log = logging.getLogger(__name__)
FIELD_LABELS = {
    'contractNo': '合同号', 'country': '出口国', 'productNo': '货号', 'productName': '产品名称',
    'quantity': '数量', 'unitsPerCarton': '每箱件数', 'cartonCount': '箱数', 'reportStatus': '报告状态',
    'production': '生产部门', 'institution': '验货机构', 'inspectionProblem': '验货问题',
    'firstResponsible': '第一责任人', 'secondResponsible': '第二责任人', 'remark': '报告备注 / 照片备注',
    'improvement': '改善措施', 'analysisReason': '分析原因', 'customerName': '报表补录客户名称',
    'returnReason': '单笔退货原因', 'correctiveCompletion': '整改完成情况',
    'traderQDate': '洋行Q货期', 'thirdPartyQDate': '第三方客Q货期',
}


def _scope(value):
    if not value:
        return '', ''
    day = date.fromisoformat(value)
    return (day - timedelta(days=day.weekday())).isoformat(), day.replace(day=1).isoformat()


def read(factory, entry_id, item, report_day):
    """Use an already verified entry ID and stored scope; never join by PO or row number."""
    if not re.fullmatch(r'[a-f0-9]{32}', entry_id):
        raise ValueError('invalid report supplement record identity')
    key, _ = approved._customer(item)
    week, month = _scope(report_day) if item.get('status') == 'approved' else ('', '')
    output = dict(status='ok', items=[], changes=[])
    prefix = f'detail:{entry_id}:'
    for period, path, current_start in (('week', weekly._path(), week), ('month', monthly._path(), month)):
        if not path.is_file():
            if path.exists():
                output['status'] = 'unavailable'
            continue
        items, changes = [], []
        root = '周报明细补录' if period == 'week' else '月度库补录（日 / 月 / 年及图文共用）'
        where = f"""factory=? AND field>=? AND field<? ORDER BY {period},customer,field"""
        args = (factory, prefix, prefix[:-1] + ';')
        try:
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True, timeout=.25)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute('PRAGMA query_only=ON')
                conn.execute('BEGIN')

                def metadata(row):
                    field = row['field'][len(prefix):]
                    label = FIELD_LABELS.get(field)
                    if not label:
                        return None
                    start = row[period]
                    caption = ('周起始 ' if period == 'week' else '') + (start if period == 'week' else start[:7])
                    return dict(field=field, label=label, period=period, periodStart=start, source=root, scope=caption,
                                current=start == current_start and row['customer'] == key,
                                actor=dict(id=row['actor']), version=row['version'])

                for row in conn.execute(f'SELECT * FROM cells WHERE {where}', args):
                    info = metadata(row)
                    if info and row['value'] != '':
                        items.append(dict(**info, value=row['value'], at=row['updated_at']))
                for row in conn.execute(f'SELECT * FROM changes WHERE {where},id', args):
                    info = metadata(row)
                    if info:
                        changes.append(dict(**info, id=f'{period}:{row["id"]}', before=row['old_value'],
                                            after=row['new_value'], at=row['created_at']))
        except sqlite3.Error:
            log.warning('qc_report_supplement_read_unavailable period=%s', period, exc_info=True)
            output['status'] = 'unavailable'
        else:
            output['items'].extend(items)
            output['changes'].extend(changes)
    output['changes'].sort(key=lambda row: (row['at'], row['id']), reverse=True)
    return output
