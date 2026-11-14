"""补料单 / Shipping Advice sheets."""
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

HEADERS = ['No.', 'Mix#', 'Container#', 'Seal#', 'Size', 'Item#', 'Description', 'Sales Conf.#',
           'P.O. No.#', 'Ctns', 'pallet', 'Qty (Pcs)', 'Booking#', 'Delivery Date', 'cbm',
           'G.W (kgs)', 'pack (pcs)', 'Container Tare Weight (kgs)', 'VGM (kgs)']


def _num(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line(item: dict, fields: dict, task: ShippingTask) -> dict:
    ctns = _num(item.get('cartons'))
    qty = _num(item.get('quantity'))
    cbm_per = item.get('cbm') / ctns if item.get('cbm') and ctns else None
    gw_per = item.get('gross_weight') / ctns if item.get('gross_weight') and ctns else None
    return {
        'id': uuid4().hex, 'mixNo': '', 'containerNo': '', 'sealNo': '',
        'size': (task.container_type or fields.get('container_type') or '').replace('1*', ''),
        'itemNo': str(item.get('product_code') or ''), 'description': str(item.get('product_name') or ''),
        'salesConf': str(fields.get('contract_no') or ''), 'po': str(item.get('customer_po') or ''),
        'ctns': _round(ctns), 'pallet': '', 'qty': _round(qty),
        'booking': task.so_number or '',
        'deliveryDate': task.planned_ship_date or '',
        'cbmPerCarton': _round(cbm_per), 'cbm': _round(ctns * cbm_per) if ctns and cbm_per else None,
        'gwPerCarton': _round(gw_per), 'gw': _round(ctns * gw_per) if ctns and gw_per else None,
        'pack': '', 'tare': None, 'vgm': None,
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_num(line.get(key)) or 0 for line in lines), 3)
    totals = {key: total(key) for key in ('ctns', 'pallet', 'qty', 'cbm', 'gw', 'tare')}
    totals['vgm'] = round(totals['gw'] + totals['tare'], 3)
    return totals


def draft_supplement(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
    authorize(user, factory_id, 'read')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务排期不存在')
    fields = {}
    if task.mail_item_id:
        item = db.get(ShippingMailItem, task.mail_item_id)
        if item is not None:
            fields = json.loads(item.fields_json or '{}')
    lines = [_line(item, fields, task) for item in json.loads(task.items_json or '[]')]
    if not lines:
        lines = [{
            'id': uuid4().hex, 'mixNo': '', 'containerNo': '', 'sealNo': '', 'size': (task.container_type or '').replace('1*', ''),
            'itemNo': '', 'description': '', 'salesConf': '', 'po': '', 'ctns': None, 'pallet': '',
            'qty': None, 'booking': task.so_number or '', 'deliveryDate': task.planned_ship_date or '',
            'cbmPerCarton': None, 'cbm': None, 'gwPerCarton': None, 'gw': None, 'pack': '',
            'tare': None, 'vgm': None,
        }]
    header = {
        'to': 'PLAYMATE', 'from': 'ROYAL REGENT', 'subject': 'SHIPMENT ADVICE', 'ref': '',
        'date': date.today().isoformat(), 'customerMarket': str(task.customer or fields.get('customer') or ''),
        'vessel': ' '.join(part for part in (str(fields.get('vessel_name') or ''), str(fields.get('voyage_no') or '')) if part),
        'portOfLoading': str(fields.get('from_port') or task.port or ''),
        'portOfDischarge': str(task.destination_country or fields.get('destination_country') or ''),
        'etd': task.planned_ship_date or '',
        'invoice': '', 'origin': 'CHINA', 'receipt': '',
    }
    return {'taskId': task.id, 'header': header, 'lines': lines, 'totals': compute_totals(lines)}


def render_supplement_xlsx(payload: dict) -> bytes:
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = Workbook()
    sheet = book.active
    sheet.title = '补料单'
    widths = [5, 7, 14, 14, 7, 10, 42, 14, 12, 8, 7, 9, 15, 11, 7, 10, 7, 12, 10]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = width
    thin = Side(style='thin', color='999999')
    border = Border(left=thin, right=thin, top=thin, bottom=thin)

    def put(cell, value, bold=False, bordered=False):
        target = sheet[cell]
        target.value = value
        target.font = Font(bold=bold)
        if bordered:
            target.border = border
        target.alignment = Alignment(vertical='center', wrap_text=True)

    put('C2', '更正补料', bold=True)
    put('A3', 'To', bold=True)
    put('C3', header.get('to') or 'PLAYMATE')
    put('A4', 'From', bold=True)
    put('C4', header.get('from') or 'ROYAL REGENT')
    put('A5', 'Subject', bold=True)
    put('C5', header.get('subject') or 'SHIPMENT ADVICE')
    put('A6', 'REF#', bold=True)
    put('C6', header.get('ref') or '')
    put('A7', 'Date', bold=True)
    put('C7', header.get('date') or '')
    put('A10', 'Please be advised of following shipment details :')

    rows = [
        ('Customer/ Market', 'customerMarket'), ('Name of Vessel', 'vessel'),
        ('Port of Loading', 'portOfLoading'), ('Port of Discharge', 'portOfDischarge'),
        ('E.T.D.', 'etd'), ('Invoice Number/Date', 'invoice'),
        ('Country of Origin', 'origin'), ('Place of receipt', 'receipt'),
    ]
    row = 12
    for label, key in rows:
        put(f'A{row}', label, bold=True)
        put(f'D{row}', ':')
        put(f'E{row}', header.get(key) or '')
        row += 1

    header_row = 21
    for index, text in enumerate(HEADERS, start=1):
        put(f'{get_column_letter(index)}{header_row}', text, bold=True, bordered=True)

    start = header_row + 1
    row = start
    for seq, line in enumerate(lines, start=1):
        values = [seq, line.get('mixNo'), line.get('containerNo'), line.get('sealNo'), line.get('size'),
                  line.get('itemNo'), line.get('description'), line.get('salesConf'), line.get('po'),
                  line.get('ctns'), line.get('pallet'), line.get('qty'), line.get('booking'),
                  line.get('deliveryDate'), line.get('cbm'), line.get('gw'), line.get('pack'),
                  line.get('tare'), line.get('vgm')]
        for index, value in enumerate(values, start=1):
            put(f'{get_column_letter(index)}{row}', value if value is not None else '', bordered=True)
        row += 1

    for column, key in (('J', 'ctns'), ('K', 'pallet'), ('L', 'qty'), ('O', 'cbm'), ('P', 'gw'),
                        ('R', 'tare'), ('S', 'vgm')):
        put(f'{column}{row}', totals[key], bold=True, bordered=True)

    summary_row = row + 4
    for index, text in enumerate(['Item#', 'Mix NO', 'Pcs', 'Ctns', 'Sales Conf#'], start=1):
        put(f'{get_column_letter(index)}{summary_row}', text, bold=True, bordered=True)
    summary: dict[str, dict] = {}
    for line in lines:
        key = line.get('itemNo') or ''
        entry = summary.setdefault(key, {'pcs': 0, 'ctns': 0, 'salesConf': line.get('salesConf') or ''})
        entry['pcs'] += _num(line.get('qty')) or 0
        entry['ctns'] += _num(line.get('ctns')) or 0
    summary_row += 1
    for item_no, entry in summary.items():
        put(f'A{summary_row}', item_no, bordered=True)
        put(f'C{summary_row}', entry['pcs'], bordered=True)
        put(f'D{summary_row}', round(entry['ctns'], 3), bordered=True)
        put(f'E{summary_row}', entry['salesConf'], bordered=True)
        summary_row += 1

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
