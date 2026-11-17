"""2026 盐田散货 W-series truck sheets (xlsx)."""
import io
import json
from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import MergedCell
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.models.shipping_mail import ShippingMailItem, ShippingTask
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize, task_fields

TO_NAMES = ('苏迪', '罗梓良')
FROM_NAME = '农建壮'
HEADERS = ['序号', '洋行', '合约', '工厂备案货号', '出货申报货号', '数量', '箱数', '板数', '毛重', '净重',
           'CBM', '出口国家', '每箱毛重', '每箱净重', '每箱体积', '品牌', 'SO', 'PO', '船期', '备注']


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line(item: dict, contract: str, so_number: str) -> dict:
    cartons = _number(item.get('cartons'))
    quantity = _number(item.get('quantity'))
    coefficient = quantity / cartons if quantity and cartons else None
    gross_per = _number(item.get('gross_weight')) / cartons if item.get('gross_weight') and cartons else None
    net_per = _number(item.get('net_weight')) / cartons if item.get('net_weight') and cartons else None
    cbm_per = _number(item.get('cbm')) * 35.4 / cartons if item.get('cbm') and cartons else None
    cbm = cbm_per * cartons / 35.4 if cbm_per and cartons else _number(item.get('cbm'))
    return {
        'id': uuid4().hex, 'tradingHouse': 'ZURU', 'contract': str(item.get('contract_no') or contract),
        'filingCode': str(item.get('product_code') or ''), 'declareCode': str(item.get('product_code') or ''),
        'coefficient': _round(coefficient),
        'quantity': _round(cartons * coefficient) if cartons and coefficient else _round(quantity),
        'cartons': _round(cartons), 'boards': '',
        'grossWeight': _round(gross_per * cartons) if gross_per and cartons else _round(item.get('gross_weight')),
        'netWeight': _round(net_per * cartons) if net_per and cartons else _round(item.get('net_weight')),
        'cbm': _round(cbm), 'country': '', 'grossPerCarton': _round(gross_per),
        'netPerCarton': _round(net_per), 'cbmPerCarton': _round(cbm_per), 'brand': str(item.get('brand') or ''),
        'so': so_number, 'po': str(item.get('customer_po') or ''), 'shippingNote': str(item.get('shipping_note') or ''), 'remark': str(item.get('remark') or ''),
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_number(line.get(key)) or 0 for line in lines), 3)
    return {key: total(key) for key in ('quantity', 'cartons', 'grossWeight', 'netWeight', 'cbm')}


def _blank_line(so_number: str) -> dict:
    return {
        'id': uuid4().hex, 'tradingHouse': 'ZURU', 'contract': '', 'filingCode': '', 'declareCode': '',
        'coefficient': None, 'quantity': None, 'cartons': None, 'boards': '', 'grossWeight': None,
        'netWeight': None, 'cbm': None, 'country': '', 'grossPerCarton': None, 'netPerCarton': None,
        'cbmPerCarton': None, 'brand': '', 'so': so_number, 'po': '', 'shippingNote': '', 'remark': '',
    }


def draft_bulk(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
    authorize(user, factory_id, 'read')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务排期不存在')
    fields = task_fields(db, task)

    contract = str(fields.get('contract_no') or '')
    country = str(task.destination_country or fields.get('destination_country') or '')
    lines = [_line(item, contract, task.so_number or '') for item in json.loads(task.items_json or '[]')]
    if not lines:
        lines = [_blank_line(task.so_number or '')]
    for line in lines:
        if not line['country']:
            line['country'] = country
    header = {
        'toNames': list(TO_NAMES), 'fromName': FROM_NAME,
        'sheetDate': task.planned_ship_date or date.today().isoformat(),
        'vehicle': 'W218', 'transport': '建联派', 'truckType': '3T', 'tradeTerm': 'FOB',
        'tableName': '2026年盐田散货W218车', 'cutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'originPort': task.port or str(fields.get('from_port') or ''),
    }
    return {'taskId': task.id, 'header': header, 'lines': lines, 'totals': compute_totals(lines)}


def _format_date(value: str) -> str:
    text = (value or '')[:10]
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return value or ''
    return f'{day.year}年{day.month:02d}月{day.day:02d}日'


def _as_date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return value or ''


def _render_template(payload: dict) -> bytes:
    template = Path(__file__).resolve().parent.parent / 'templates' / 'yan_tian_bulk_truck.xlsx'
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = load_workbook(template)
    sheet = book.worksheets[0]

    to_names = header.get('toNames') or list(TO_NAMES)
    sheet['C1'] = to_names[0]
    sheet['C2'] = to_names[1] if len(to_names) > 1 else ''
    sheet['L3'] = f"车头注明   W {str(header.get('vehicle') or '218').lstrip('Ww').strip()} 车"
    sheet['A4'] = _as_date(header.get('sheetDate'))
    sheet['E4'] = f"{header.get('transport') or ''}{header.get('truckType') or '3T'}车出货如下"
    sheet['P4'] = f"成交方式：{header.get('tradeTerm') or 'FOB'}"
    sheet['L14'] = 'FROM:'
    sheet['N14'] = header.get('fromName') or FROM_NAME
    sheet['K15'] = _as_date(header.get('sheetDate'))

    for row in range(6, 12):
        for column in range(1, 21):
            cell = sheet.cell(row=row, column=column)
            if not isinstance(cell, MergedCell):
                cell.value = None
    for index, line in enumerate(lines[:6], start=1):
        row = 5 + index
        values = [index, line.get('tradingHouse'), line.get('contract'), line.get('filingCode'),
                  line.get('declareCode'), line.get('quantity'), line.get('cartons'), line.get('boards'),
                  line.get('grossWeight'), line.get('netWeight'), line.get('cbm'), line.get('country'),
                  line.get('grossPerCarton'), line.get('netPerCarton'), line.get('cbmPerCarton'),
                  line.get('brand'), line.get('so'), line.get('po'), line.get('shippingNote'), line.get('remark')]
        for column, value in enumerate(values, start=1):
            if value is not None:
                cell = sheet.cell(row=row, column=column)
                if not isinstance(cell, MergedCell):
                    cell.value = value
    for column, key in (('F', 'quantity'), ('G', 'cartons'), ('I', 'grossWeight'),
                        ('J', 'netWeight'), ('K', 'cbm')):
        sheet[f'{column}12'] = totals[key]

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def render_bulk_xlsx(payload: dict) -> bytes:
    template = Path(__file__).resolve().parent.parent / 'templates' / 'yan_tian_bulk_truck.xlsx'
    if template.is_file():
        return _render_template(payload)
    return _render_generated(payload)
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = Workbook()
    sheet = book.active
    sheet.title = (header.get('tableName') or '盐田散货')[:31]
    widths = [5, 8, 14, 16, 14, 9, 8, 7, 9, 9, 8, 10, 9, 9, 9, 14, 16, 10, 18, 20]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    thin = Side(style='thin', color='999999')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def put(cell, value, bold=False, bordered=True):
        target = sheet[cell]
        target.value = value
        target.font = Font(bold=bold)
        if bordered:
            target.border = border
        target.alignment = Alignment(vertical='center', wrap_text=True)

    put('B1', 'TO:', bold=True, bordered=False)
    put('C1', (header.get('toNames') or TO_NAMES)[0], bordered=False)
    put('C2', (header.get('toNames') or TO_NAMES)[1], bordered=False)
    put('L3', f"车头注明   W {header.get('vehicle') or '218'} 车", bordered=False)
    sheet['A4'] = header.get('sheetDate') or ''
    sheet['A4'].number_format = 'yyyy/m/d'
    put('E4', f"{header.get('transport') or ''}{header.get('truckType') or '3T'}车出货如下", bordered=False)
    put('P4', f"成交方式：{header.get('tradeTerm') or 'FOB'}", bordered=False)
    for index, text in enumerate(HEADERS, start=1):
        put(f'{get_column_letter(index)}5', text, bold=True)

    row = 6
    for seq, line in enumerate(lines, start=1):
        values = [seq, line.get('tradingHouse'), line.get('contract'), line.get('filingCode'),
                  line.get('declareCode'), line.get('quantity'), line.get('cartons'), line.get('boards'),
                  line.get('grossWeight'), line.get('netWeight'), line.get('cbm'), line.get('country'),
                  line.get('grossPerCarton'), line.get('netPerCarton'), line.get('cbmPerCarton'),
                  line.get('brand'), line.get('so'), line.get('po'), line.get('shippingNote'), line.get('remark')]
        for index, value in enumerate(values, start=1):
            put(f'{get_column_letter(index)}{row}', value if value is not None else '')
        row += 1

    put(f'A{row}', '合计', bold=True)
    for column, key in (('F', 'quantity'), ('G', 'cartons'), ('I', 'grossWeight'), ('J', 'netWeight'), ('K', 'cbm')):
        put(f'{column}{row}', totals[key], bold=True)
    row += 2
    put(f'L{row}', 'FROM:', bordered=False)
    put(f'N{row}', header.get('fromName') or FROM_NAME, bordered=False)
    sheet[f'K{row + 1}'] = header.get('sheetDate') or ''
    sheet[f'K{row + 1}'].number_format = 'yyyy/m/d'

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
