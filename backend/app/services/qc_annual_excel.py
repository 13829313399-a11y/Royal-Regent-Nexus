"""Annual inspection summary with the monthly table, editable column chart and detail list."""
from copy import copy
from datetime import date
from io import BytesIO
from math import ceil
from unicodedata import east_asian_width
from openpyxl import load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.chart.data_source import AxDataSource, NumData, NumVal, StrData, StrRef, StrVal
from openpyxl.chart.axis import ChartLines
from openpyxl.chart.shapes import GraphicalProperties
from openpyxl.drawing.spreadsheet_drawing import AnchorMarker, TwoCellAnchor
from openpyxl.utils import get_column_letter

from app.services.qc_daily_report import _quantity
from app.services.qc_monthly_excel import TEMPLATE_DIR


def workbook(report):
    book = load_workbook(TEMPLATE_DIR / 'approved-layouts.xlsx')
    model = book['问题照片与整改进度']
    styles = {role: model[address]._style for role, address in {
        'title': 'A2', 'period': 'A3', 'section': 'A5', 'header': 'A6',
        'body': 'B7', 'alternate': 'B8',
    }.items()}
    for template in list(book):
        book.remove(template)
    sheet = book.create_sheet('客验货统计表')
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 80
    sheet.sheet_view.zoomScaleNormal = 80
    sheet.sheet_view.selection[0].activeCell = 'A4'
    sheet.sheet_view.selection[0].sqref = 'A4'
    year, customer, result = (report['filters'][k] for k in ('year', 'customer', 'result'))
    label = next((c['label'] for c in report['options']['customers'] if c['key'] == customer), '全部客户')
    detail_title = {'FAIL':'不合格','PENDING':'待定','LG':'LG','OTHER':'其他结果','ALL':'全部','PASS':'合格'}[result]
    widths = (11, 19, 27, 12, 24, 12, 12, 14, 12, 12, 12, 12)
    for i, width in enumerate(widths, 1):
        sheet.column_dimensions[get_column_letter(i)].width = width

    def put(row, col, value, cell_style):
        cell = sheet.cell(row, col, value)
        if isinstance(value, str):
            cell.data_type = 's'
        cell._style = copy(styles[cell_style])
        return cell

    def strip(row, start, end, value, cell_style):
        sheet.merge_cells(start_row=row, start_column=start, end_row=row, end_column=end)
        put(row, start, value, cell_style)

    strip(1, 1, 12, f'华兴 {year} 年度验货统计表', 'title')
    strip(2, 1, 12, f'年视图  {year}-01-01 至 {year}-12-31　　{label}', 'period')
    strip(3, 8, 12, '月度合格率　　PASS ÷（PASS + FAIL）', 'header')
    sheet.row_dimensions[1].height = 26
    sheet.row_dimensions[2].height = 18
    sheet.row_dimensions[3].height = 21
    keys = ('total', 'PASS', 'FAIL', 'PENDING', 'LG', 'passRate')
    for col, name in enumerate(('月份', '验货总批数', '合格批数', '不合格批数', 'PENDING', 'LG', '合格率'), 1):
        put(3, col, name, 'header')
    months = {int(r['month'][-2:]):r for r in report['months']}
    rates = []
    for month in range(1, 14):
        total = month == 13
        row = month + 3
        data = report['totals'] if total else months.get(month, {})
        month_style = 'header' if total else 'body'
        put(row, 1, '年度合计' if total else f'{month}月', month_style)
        for col, key in enumerate(keys, 2):
            value = data.get(key)
            if key == 'passRate' and value is not None:
                value /= 100
                if not total:
                    rates.append(NumVal(idx=month-1, v=value))
            cell = put(row, col, value, month_style)
            if key == 'passRate':
                cell.number_format = '0.0%'
        sheet.row_dimensions[row].height = 24 if total else (19 if data.get('total') else 15)

    chart = BarChart()
    chart.type = 'col'
    chart.legend = None
    chart.y_axis.scaling.min, chart.y_axis.scaling.max = 0, 1
    chart.y_axis.numFmt = '0%'
    chart.y_axis.majorUnit = 0.25
    chart.y_axis.majorGridlines = ChartLines(spPr=GraphicalProperties())
    chart.y_axis.majorGridlines.spPr.line.solidFill = 'E0E0E0'
    chart.y_axis.majorGridlines.spPr.line.width = 6350
    chart.gapWidth = 85
    chart.graphical_properties = GraphicalProperties(solidFill='FFFFFF')
    chart.graphical_properties.line.noFill = True
    chart.add_data(Reference(sheet, min_col=7, min_row=4, max_row=15))
    series = chart.series[0]
    series.cat = AxDataSource(strRef=StrRef(f="'客验货统计表'!$A$4:$A$15", strCache=StrData(
        ptCount=12, pt=[StrVal(idx=i, v=f'{i+1}月') for i in range(12)])))
    series.val.numRef.numCache = NumData(formatCode='0.0%', ptCount=12, pt=rates)
    series.graphicalProperties = GraphicalProperties(solidFill='686868')
    series.graphicalProperties.line.noFill = True
    chart.anchor = TwoCellAnchor(_from=AnchorMarker(col=7, row=3), to=AnchorMarker(col=12, row=16))
    sheet.add_chart(chart)

    sheet.row_dimensions[17].height = 7
    strip(18, 1, 12, f'{detail_title}验货明细　（{report["details"]["total"]} 条）', 'section')
    sheet.row_dimensions[18].height = 20
    sheet.row_dimensions[19].height = 21
    for col, name in enumerate(('客户','产品 PO','产品名称','数量','验货时间','验货机构','验货结果','不良原因 / 备注'), 1):
        put(19, col, name, 'header')
    sheet.merge_cells('H19:L19')
    for row, item in enumerate(report['details']['items'], 20):
        notes = '\n'.join(dict.fromkeys(v for v in (item['inspectionProblem'], item['remark']) if v))
        values = (item['customer'], item['poNo'], item['productName'], _quantity(item['quantity']),
                  date.fromisoformat(item['date']), item['agency'], item['result'], notes)
        for col, value in enumerate(values, 1):
            cell = put(row, col, value, 'alternate' if row % 2 else 'body')
            if col == 5:
                cell.number_format = 'yyyy-mm-dd"（排期）"' if item['usesScheduleDate'] else 'yyyy-mm-dd'
        sheet.merge_cells(start_row=row, start_column=8, end_row=row, end_column=12)
        lines = max(sum(max(1, ceil(sum(2 if east_asian_width(c) in ('W', 'F') else 1 for c in part) / chars))
                        for part in str(text).split('\n'))
                    for text,chars in ((notes, 57), (item['productName'], 24), (item['poNo'], 16), (item['customer'], 10), (item['agency'], 10)))
        sheet.row_dimensions[row].height = min(409, max(22, lines*15 + 3))
    if not report['details']['items']:
        strip(20, 1, 12, '当前筛选范围内暂无此类记录', 'body')
        sheet.row_dimensions[20].height = 23
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    sheet.page_setup.fitToWidth, sheet.page_setup.fitToHeight = 1, 0
    sheet.print_area = f'A1:L{max(20, sheet.max_row)}'
    output = BytesIO()
    book.save(output)
    return output.getvalue()
