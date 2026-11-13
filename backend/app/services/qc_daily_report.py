"""Huaxing daily report from the validated current approval snapshot."""
from copy import deepcopy
from datetime import date, timedelta
from calendar import monthrange
from hashlib import sha256
from pathlib import Path
import re
import math
import unicodedata
from lxml import etree as E

from fastapi import HTTPException
from openpyxl.utils import get_column_letter

from app.services import qc_approved_statistics as approved
from app.services.qc_inspection_summary import dump
from app.services.qc_workbook_xml import Package, tag


TEMPLATE = Path(__file__).resolve().parents[1] / 'templates/qc-daily/每日验货情况统计表.xlsx'
HEADERS = ['贸易商  （洋行）', '合同号', '出口国（客户）', '货号', '產品名称', 'PO数量',
           '洋行Q货期', '第三方客Q货期', '验货结果', '验货问题', '第一责任人', '第二责任人', '备注']


def _text(value):
    return '' if value is None else str(value)


def _quantity(value):
    value = _text(value).strip()
    return float(value) if re.fullmatch(r'[0-9]{1,15}(?:\.[0-9]{1,4})?', value) else value


def _report_row(item, date_source):
    source = item.get('sourceRecord') or {}
    result = _text(item.get('result')).strip().upper()
    problem = item.get('inspectionProblem')
    remark = item.get('otherRemark') or item.get('remark')
    # The approved source does not independently identify the two Q dates.
    values = [_text(item.get('customer')), _text(item.get('contractNo', source.get('contractNo'))),
              _text(item.get('country')), _text(item.get('productNo')), _text(item.get('productName')),
              _quantity(item.get('quantity')), '', '', result, _text(problem),
              _text(item.get('firstResponsible')), _text(item.get('secondResponsible')), _text(remark)]
    return dict(values=values, improvement=_text(item.get('improvement')), dateSource=date_source)


def period_bounds(day, period='daily'):
    if not approved._date(day) or period not in {'daily', 'weekly', 'monthly'}:
        raise HTTPException(422, '请选择有效的报告日期和周期')
    selected = date.fromisoformat(day)
    if period == 'weekly':
        start = selected - timedelta(days=selected.weekday())
        try:
            end = start + timedelta(days=6)
        except OverflowError as exc:
            raise HTTPException(422, '报告周期超出有效日期范围') from exc
    elif period == 'monthly':
        start = selected.replace(day=1)
        end = selected.replace(day=monthrange(selected.year, selected.month)[1])
    else:
        start = end = selected
    return start.isoformat(), end.isoformat()


def report(factory, day, period='daily'):
    if factory != 'huaxing':
        raise HTTPException(404, '当前厂区未配置华兴日报模板')
    start, end = period_bounds(day, period)
    snapshots = []
    source = approved.query(factory, {'from': start, 'to': end}, _report_snapshots=snapshots)
    if source['excluded'].get('missingProjection') or source['excluded'].get('invalidLineage'):
        raise HTTPException(503, '已审核记录与汇总未对齐，请核对后再生成日报')
    rows = [_report_row(item, date_source) for item, date_source in snapshots if not (
        item.get('reference') or item.get('referenceData') or item.get('testData'))]
    total = len(rows)
    passed = sum(row['values'][8] == 'PASS' for row in rows)
    failed = sum(row['values'][8] in {'FAIL', 'REJ'} for row in rows)
    revision = sha256(dump([day, period, start, end, rows]).encode()).hexdigest()
    return dict(date=day, period=period, dateFrom=start, dateTo=end, headers=HEADERS, rows=rows, revision=revision,
                total=total, passed=passed, failed=failed, other=total-passed-failed,
                rate=round(passed/total*100, 1) if total else None,
                scheduleCount=sum(row['dateSource'] == 'schedule' for row in rows))


def workbook(report_data):
    package = Package(TEMPLATE.read_bytes())
    name = package.names()[0]
    sheet_name = '.'.join(str(int(part)) for part in report_data['date'][5:].split('-'))
    if report_data.get('period') in {'weekly', 'monthly'}:
        sheet_name = ('周报' if report_data['period'] == 'weekly' else '月报') + report_data['dateFrom']
    package.sheets[0].set('name', sheet_name)
    package.original_order = [sheet_name]
    sheet = package.sheet(sheet_name)
    sheet_rows = package.rows(sheet_name)
    by_number = {int(row.get('r')): row for row in sheet_rows}
    if [package.values(by_number[3]).get(col) for col in range(1, 14)] != HEADERS:
        raise HTTPException(503, '华兴日报模板表头不匹配')
    merges = sheet.find(tag('mergeCells'))
    # J4:J5 came from a historical two-row problem description. Daily rows are independent.
    for merge in list(merges):
        if merge.get('ref') == 'J4:J5':
            merges.remove(merge)
    merges.set('count', str(len(merges)))
    base = deepcopy(by_number[6])
    for cell in list(base):
        if len(cell.get('r').rstrip('0123456789')) > 1 or cell.get('r')[0] > 'M':
            base.remove(cell)
    for number, item in enumerate(report_data['rows'], 4):
        target = by_number.get(number)
        if target is None:
            target = deepcopy(base)
            target.set('r', str(number))
            for cell in target:
                cell.set('r', re.sub(r'\d+$', str(number), cell.get('r')))
            sheet_rows.append(target)
        cells = {cell.get('r'): cell for cell in target}
        for col, value in enumerate(item['values'], 1):
            if value == '':
                continue
            ref = get_column_letter(col) + str(number)
            old = cells.get(ref)
            style = old.get('s', '0') if old is not None else '0'
            if old is not None:
                position = target.index(old)
                target.remove(old)
            else:
                position = next((i for i, cell in enumerate(target)
                                 if len(cell.get('r').rstrip('0123456789')) > 1
                                 or cell.get('r').rstrip('0123456789') > get_column_letter(col)), len(target))
            target.insert(position, package.cell(target, col, value, style))
    _format_daily_sheet(package, sheet, sheet_rows, sheet_name, report_data)
    return package.finish()


def _format_daily_sheet(package, sheet, rows, name, data):
    # The source template includes formatted empty rows and columns through IT.
    last = 3 + len(data['rows'])
    for row in list(rows):
        if int(row.get('r')) > last:
            rows.remove(row)
            continue
        for cell in list(row):
            if cell.get('r').rstrip('0123456789') not in list('ABCDEFGHIJKLM'):
                row.remove(cell)
    cols = sheet.find(tag('cols'))
    cols.clear()
    widths = [18, 18, 15, 20, 30, 12, 14, 14, 12, 42, 16, 16, 36]
    for index, width in enumerate(widths, 1):
        E.SubElement(cols, tag('col'), min=str(index), max=str(index),
                     width=str(width), customWidth='1')
    styles = package.styles.find(tag('cellXfs'))
    body_styles = []
    for col in range(13):
        style = deepcopy(styles[13])
        alignment = style.find(tag('alignment'))
        if alignment is None:
            alignment = E.SubElement(style, tag('alignment'))
        alignment.attrib.clear()
        alignment.set('horizontal', 'right' if col == 5 else 'center' if col in (2, 6, 7, 8) else 'left')
        alignment.set('vertical', 'center')
        alignment.set('wrapText', '1')
        style.set('applyAlignment', '1')
        style.set('numFmtId', '0' if col == 5 else '49')
        body_styles.append(str(len(styles)))
        styles.append(style)
    styles.set('count', str(len(styles)))
    by_number = {int(row.get('r')): row for row in rows}
    for number, item in enumerate(data['rows'], 4):
        row = by_number[number]
        row[:] = [E.Element(tag('c'), r=get_column_letter(col)+str(number), s=body_styles[col-1])
                  if value == '' or value is None else package.cell(row, col, value, body_styles[col-1])
                  for col, value in enumerate(item['values'], 1)]
        lines = 1
        for value, width in zip(item['values'], widths):
            count = sum(max(1, math.ceil(sum(2 if unicodedata.east_asian_width(c) in 'WF' else 1
                                            for c in line) / (width - 2)))
                        for line in str(value).splitlines())
            lines = max(lines, count)
        row.set('ht', str(min(409, max(32, lines * 16 + 8))))
        row.set('customHeight', '1')
    view = sheet.find(tag('sheetViews'))[0]
    # The template was saved scrolled to A42; frozen panes must start at A1.
    view.set('topLeftCell', 'A1')
    for node in list(view):
        if node.tag in (tag('pane'), tag('selection')):
            view.remove(node)
    E.SubElement(view, tag('pane'), xSplit='4', ySplit='3', topLeftCell='E4', activePane='bottomRight', state='frozen')
    E.SubElement(view, tag('selection'), pane='bottomRight', activeCell='E4', sqref='E4')
    view.set('showGridLines', '0')
    props = sheet.find(tag('sheetPr'))
    if props is None:
        props = E.SubElement(sheet, tag('sheetPr'))
    setup_props = props.find(tag('pageSetUpPr'))
    if setup_props is None:
        setup_props = E.SubElement(props, tag('pageSetUpPr'))
    setup_props.set('fitToPage', '1')
    setup = sheet.find(tag('pageSetup'))
    if setup is None:
        setup = E.SubElement(sheet, tag('pageSetup'))
    setup.attrib.update({'orientation': 'landscape', 'paperSize': '8', 'fitToWidth': '1', 'fitToHeight': '0'})
    setup.attrib.pop('scale', None)
    for key in ('rowBreaks', 'colBreaks'):
        node = sheet.find(tag(key))
        if node is not None:
            sheet.remove(node)
    names = package.book.find(tag('definedNames'))
    if names is None:
        names = E.Element(tag('definedNames'))
        # OOXML requires definedNames before calcPr and the later workbook nodes.
        after = {'sheets', 'functionGroups', 'externalReferences'}
        position = max(i for i, node in enumerate(package.book)
                       if E.QName(node).localname in after) + 1
        package.book.insert(position, names)
    for node in list(names):
        if node.get('name') in ('_xlnm.Print_Area', '_xlnm.Print_Titles'):
            names.remove(node)
    quoted = "'" + name.replace("'", "''") + "'!"
    E.SubElement(names, tag('definedName'), name='_xlnm.Print_Area', localSheetId='0').text = quoted + '$A$1:$M$' + str(last)
    E.SubElement(names, tag('definedName'), name='_xlnm.Print_Titles', localSheetId='0').text = quoted + '$1:$3'
