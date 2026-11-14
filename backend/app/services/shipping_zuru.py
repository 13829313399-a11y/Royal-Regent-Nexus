"""ZURU container cargo sheets: draft from a shipping task and .xlsx export."""
import io
import json
from datetime import date
from uuid import uuid4

from fastapi import HTTPException
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from sqlalchemy import select

from app.models.shipping_mail import ShippingMailItem, ShippingTask
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize

TO_NAMES = ('苏迪', '罗梓良')
FROM_NAME = '农建壮'
COUNTRY_EN = {
    '英国': 'UNITED KINGDOM', '美国': 'USA', '德国': 'GERMANY', '法国': 'FRANCE',
    '意大利': 'ITALY', '澳大利亚': 'AUSTRALIA', '加拿大': 'CANADA', '日本': 'JAPAN',
    '韩国': 'SOUTH KOREA', '菲律宾': 'PHILIPPINES', '荷兰': 'NETHERLANDS', '西班牙': 'SPAIN',
    '越南': 'VIETNAM', '马来西亚': 'MALAYSIA', '新加坡': 'SINGAPORE', '泰国': 'THAILAND',
}


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line(item: dict, contract: str, country: str) -> dict:
    cartons = _number(item.get('cartons'))
    quantity = _number(item.get('quantity'))
    gross = _number(item.get('gross_weight'))
    net = _number(item.get('net_weight'))
    coefficient = quantity / cartons if quantity and cartons else None
    gross_per_carton = gross / cartons if gross and cartons else None
    net_per_carton = net / cartons if net and cartons else None
    return {
        'id': uuid4().hex,
        'tradingHouse': '',
        'contract': contract,
        'filingCode': str(item.get('product_code') or ''),
        'declareCode': str(item.get('product_code') or ''),
        'brand': '',
        'coefficient': _round(coefficient),
        'quantity': _round(cartons * coefficient) if cartons and coefficient else _round(quantity),
        'cartons': _round(cartons),
        'grossWeight': _round(cartons * gross_per_carton) if cartons and gross_per_carton else _round(gross),
        'netWeight': _round(cartons * net_per_carton) if cartons and net_per_carton else _round(net),
        'cbm': None,
        'cbmPerCarton': _round(_number(item.get('cbm')) / cartons) if cartons and _number(item.get('cbm')) else None,
        'country': country,
        'grossPerCarton': _round(gross_per_carton),
        'netPerCarton': _round(net_per_carton),
        'remark': '',
        'po': str(item.get('customer_po') or ''),
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_number(line.get(key)) or 0 for line in lines), 3)
    return {key: total(key) for key in ('quantity', 'cartons', 'grossWeight', 'netWeight', 'cbm')}


def _display_cutoff(value: str) -> str:
    text = (value or '')
    if not text:
        return ''
    day, _, clock = text.partition('T')
    try:
        parsed = date.fromisoformat(day)
        formatted = f'{parsed.year}/{parsed.month}/{parsed.day}'
    except ValueError:
        formatted = day
    return f'{formatted} {clock[:5]}' if clock else formatted


def _blank_line(country: str) -> dict:
    return {
        'id': uuid4().hex, 'tradingHouse': '', 'contract': '', 'filingCode': '', 'declareCode': '',
        'brand': '', 'coefficient': None, 'quantity': None, 'cartons': None, 'grossWeight': None,
        'netWeight': None, 'cbm': None, 'cbmPerCarton': None, 'country': country,
        'grossPerCarton': None, 'netPerCarton': None, 'remark': '', 'po': '',
    }


def draft_zuru(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
    authorize(user, factory_id, 'read')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务排期不存在')
    fields = {}
    if task.mail_item_id:
        item = db.get(ShippingMailItem, task.mail_item_id)
        if item is not None:
            fields = json.loads(item.fields_json or '{}')
    country = str(task.destination_country or fields.get('destination_country') or '')
    lines = [_line(item, str(fields.get('contract_no') or ''), COUNTRY_EN.get(country, country))
             for item in json.loads(task.items_json or '[]')]
    if not lines:
        lines = [_blank_line(COUNTRY_EN.get(country, country))]
    vessel_voyage = ' '.join(part for part in (str(fields.get('vessel_name') or ''), str(fields.get('voyage_no') or '')) if part)
    header = {
        'toNames': list(TO_NAMES),
        'fromName': FROM_NAME,
        'sheetDate': date.today().isoformat(),
        'cutoff': _display_cutoff(task.cutoff_date or str(fields.get('cutoff_date') or '')),
        'number': 'W187',
        'soNo': task.so_number or str(fields.get('so_number') or ''),
        'vesselVoyage': vessel_voyage,
        'blNo': '',
        'transportCompany': '',
        'containerType': (task.container_type or str(fields.get('container_type') or '40HQ')).replace('1*', ''),
        'tradeTerm': 'FOB',
        'plate': '',
        'containerNo': '',
        'sealNo': '',
        'tareWeight': '',
        'originPort': task.port or '',
        'destinationCountry': COUNTRY_EN.get(country, country),
    }
    return {'taskId': task.id, 'header': header, 'lines': lines, 'totals': compute_totals(lines)}


def _border():
    thin = Side(style='thin', color='999999')
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def render_zuru_xlsx(payload: dict) -> bytes:
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = Workbook()
    sheet = book.active
    sheet.title = (header.get('originPort') or header.get('number') or 'SO出货表')[:31]
    widths = {'A': 5, 'B': 9, 'C': 16, 'D': 18, 'E': 12, 'F': 9, 'G': 8, 'H': 9, 'I': 9,
              'J': 9, 'K': 8, 'L': 12, 'M': 18, 'N': 8, 'O': 8, 'P': 9, 'Q': 16, 'R': 16}
    for column, width in widths.items():
        sheet.column_dimensions[column].width = width

    def put(cell, value, bold=False, border=True):
        target = sheet[cell]
        target.value = value
        target.font = Font(bold=bold)
        if border:
            target.border = _border()
        target.alignment = Alignment(vertical='center', wrap_text=True)
        return target

    put('B1', 'TO:', bold=True, border=False)
    put('C1', (header.get('toNames') or TO_NAMES)[0], border=False)
    if len(header.get('toNames') or []) > 1:
        put('C3', (header.get('toNames') or [])[1], border=False)
    put('L3', f"车头注明   {header.get('number') or 'W187'}柜", border=False)
    put('J4', '柜S/O:', border=False)
    put('L4', header.get('soNo') or '', border=False)
    put('J5', '船名航次：', border=False)
    put('L5', header.get('vesselVoyage') or '', border=False)
    put('J6', '提单号：', border=False)
    put('L6', header.get('blNo') or '', border=False)

    sheet['A7'] = header.get('sheetDate') or ''
    sheet['A7'].number_format = 'yyyy/m/d'
    put('E7', f"{header.get('transportCompany') or ''}派{header.get('containerType') or '40HQ'}柜出货如下", border=False)
    put('P7', f"成交方式：{header.get('tradeTerm') or 'FOB'}", border=False)

    headers = ['序号', '洋行', '合约', '工厂备案货号', '出货申报货号', '数量', '箱数', '毛重', '毛重', '净重', 'CBM',
               '出口国家', '品牌', '每箱毛重', '每箱净重', '每箱体积', '备注', 'PO']
    for index, text in enumerate(headers, start=1):
        put(f'{get_column_letter(index)}8', text, bold=True)

    row = 9
    for seq, line in enumerate(lines, start=1):
        values = [seq, line.get('tradingHouse'), line.get('contract'), line.get('filingCode'),
                  line.get('declareCode'), line.get('quantity'), line.get('cartons'), '',
                  line.get('grossWeight'), line.get('netWeight'), line.get('cbm'), line.get('country'),
                  line.get('brand'), line.get('grossPerCarton'), line.get('netPerCarton'), line.get('cbmPerCarton'),
                  line.get('remark'), line.get('po')]
        for index, value in enumerate(values, start=1):
            put(f'{get_column_letter(index)}{row}', value if value is not None else '')
        row += 1

    total_row = row
    put(f'A{total_row}', '合计', bold=True)
    for column, key in (('F', 'quantity'), ('G', 'cartons'), ('I', 'grossWeight'),
                        ('J', 'netWeight'), ('K', 'cbm')):
        put(f'{column}{total_row}', totals[key], bold=True)

    manual = total_row + 2
    put(f'D{manual}', f"车牌：{header.get('plate') or ''}", border=False)
    put(f'D{manual + 1}', f"柜号：{header.get('containerNo') or ''}", border=False)
    put(f'D{manual + 2}', f"封条号：{header.get('sealNo') or ''}", border=False)
    put(f'D{manual + 3}', f"柜重：{header.get('tareWeight') or ''}", border=False)
    put(f'L{manual + 6}', 'FROM:', border=False)
    put(f'O{manual + 6}', header.get('fromName') or FROM_NAME, border=False)
    sheet[f'K{manual + 7}'] = header.get('sheetDate') or ''
    sheet[f'K{manual + 7}'].number_format = 'yyyy/m/d'

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
