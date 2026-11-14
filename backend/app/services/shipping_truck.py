"""Buzzbee 客上车 (truck loading) sheets for 盐田仓 CFS deliveries."""
import io
import json
from datetime import date
from uuid import uuid4

import xlwt
from fastapi import HTTPException
from sqlalchemy import select

from app.models.shipping_mail import ShippingMailItem, ShippingTask
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize

SHIPPER = '华兴玩具制品（河源）有限公司'
CONSIGNEE = '华登玩具制品有限公司'
TO_NAME = '罗梓良'
PREPARER = '农建壮'
HEADERS = ['部门', '序号', '洋行', '合同', '备案货号', '走货申报货号', '货名', '国家', '玩具类别',
           '数量', '件数', '毛重', '净重', '体积CBM', '箱唛', '每单总件数', '每箱毛重', '每箱净重', '备注']


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line(item: dict, country: str) -> dict:
    quantity = _number(item.get('quantity'))
    cartons = _number(item.get('cartons'))
    coefficient = quantity / cartons if quantity and cartons else None
    gross_per = _number(item.get('gross_weight')) / cartons if item.get('gross_weight') and cartons else None
    net_per = _number(item.get('net_weight')) / cartons if item.get('net_weight') and cartons else None
    pieces = quantity / coefficient if quantity and coefficient else cartons
    return {
        'id': uuid4().hex, 'department': '', 'tradingHouse': 'Buzzbee',
        'contract': '', 'filingCode': str(item.get('product_code') or ''),
        'declareCode': str(item.get('product_code') or ''),
        'name': str(item.get('product_name') or ''), 'country': country, 'category': '',
        'quantity': _round(quantity), 'coefficient': _round(coefficient), 'pieces': _round(pieces),
        'grossWeight': _round(gross_per * pieces) if gross_per and pieces else None,
        'netWeight': _round(net_per * pieces) if net_per and pieces else None,
        'cbm': None, 'cartonMark': str(item.get('customer_po') or ''), 'totalCartons': '',
        'grossPerCarton': _round(gross_per), 'netPerCarton': _round(net_per), 'remark': '',
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_number(line.get(key)) or 0 for line in lines), 3)
    return {key: total(key) for key in ('quantity', 'pieces', 'grossWeight', 'netWeight', 'cbm')}


def draft_truck(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
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
    lines = [_line(item, country) for item in json.loads(task.items_json or '[]')]
    if not lines:
        lines = [{
            'id': uuid4().hex, 'department': '', 'tradingHouse': 'Buzzbee', 'contract': '',
            'filingCode': '', 'declareCode': '', 'name': '', 'country': country, 'category': '',
            'quantity': None, 'coefficient': None, 'pieces': None, 'grossWeight': None,
            'netWeight': None, 'cbm': None, 'cartonMark': '', 'totalCartons': '',
            'grossPerCarton': None, 'netPerCarton': None, 'remark': '',
        }]
    origin = str(fields.get('from_port') or task.port or '')
    if '盐田' in origin or 'YANTIAN' in origin.upper():
        cfs = '盐田仓CFS'
    elif '蛇口' in origin or 'SHEKOU' in origin.upper():
        cfs = '蛇口仓CFS'
    else:
        cfs = origin or '盐田仓CFS'
    header = {
        'shipper': SHIPPER, 'consignee': CONSIGNEE, 'reference': '', 'toName': TO_NAME,
        'vehicle': 'W15', 'cfs': cfs, 'tradeTerm': 'EXW', 'cc': 'PAT',
        'tableName': f'{cfs}客上车W15车', 'consolidator': '华兴与新际拼车',
        'scheduleText': '', 'brandNote': '', 'plate': '', 'cutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'sheetDate': date.today().isoformat(), 'preparer': PREPARER,
        'bookingDate': str(fields.get('booking_date') or ''),
    }
    return {'taskId': task.id, 'header': header, 'lines': lines, 'totals': compute_totals(lines)}


def _format_date(value: str) -> str:
    text = (value or '')[:10]
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return value or ''
    return f'{day.year}年{day.month:02d}月{day.day:02d}日'


def render_truck_xls(payload: dict) -> bytes:
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = xlwt.Workbook(encoding='utf-8')
    sheet = book.add_sheet((header.get('tableName') or '客上车')[:31])
    widths = [7, 7, 12, 12, 16, 14, 26, 10, 10, 10, 8, 10, 10, 10, 16, 12, 10, 10, 22]
    for index, width in enumerate(widths):
        sheet.col(index).width = 256 * width
    bold = xlwt.easyxf('font: bold on')

    sheet.write_merge(0, 0, 0, 18, f'发货商：{header.get("shipper") or SHIPPER}', bold)
    sheet.write(1, 0, f'收货商：{header.get("consignee") or CONSIGNEE}')
    sheet.write(1, 6, header.get('reference') or '')
    sheet.write(2, 0, 'TO:')
    sheet.write_merge(2, 2, 3, 4, header.get('toName') or TO_NAME)
    sheet.write_merge(2, 2, 8, 11, f'盐客上车 {header.get("vehicle") or "W15"}车')
    sheet.write_merge(2, 2, 12, 14, f'成交方式:{header.get("tradeTerm") or "EXW"}')
    sheet.write(3, 14, header.get('tableName') or '')
    sheet.write(4, 0, 'CC:')
    sheet.write(4, 3, header.get('cc') or 'PAT')
    sheet.write_merge(4, 4, 4, 18, header.get('cfs') or '')

    for col, text in enumerate(HEADERS):
        sheet.write(6, col, text, bold)

    row = 7
    for seq, line in enumerate(lines, start=1):
        values = [line.get('department'), seq, line.get('tradingHouse'), line.get('contract'),
                  line.get('filingCode'), line.get('declareCode'), line.get('name'), line.get('country'),
                  line.get('category'), line.get('quantity'), line.get('pieces'), line.get('grossWeight'),
                  line.get('netWeight'), line.get('cbm'), line.get('cartonMark'), line.get('totalCartons'),
                  line.get('grossPerCarton'), line.get('netPerCarton'), line.get('remark')]
        for col, value in enumerate(values):
            sheet.write(row, col, value if value is not None else '')
        row += 1

    if header.get('consolidator'):
        sheet.write(row, 6, header['consolidator'])
        row += 1
    if header.get('scheduleText'):
        sheet.write(row, 6, header['scheduleText'])
        row += 1

    sheet.write(row + 1, 14, header.get('brandNote') or '')
    sheet.write(row + 2, 8, f'车牌：{header.get("plate") or ""}')
    totals_row = row + 3
    sheet.write(totals_row, 8, '合计')
    for col, key in ((9, 'quantity'), (10, 'pieces'), (11, 'grossWeight'), (12, 'netWeight'), (13, 'cbm')):
        sheet.write(totals_row, col, totals[key])

    sheet.write(totals_row + 1, 0, f'截数期{_format_date(header.get("cutoff") or "")}')
    sheet.write(totals_row + 2, 0, f'制表人:{header.get("preparer") or PREPARER}')
    sheet.write(totals_row + 2, 4, _format_date(header.get('sheetDate') or ''))

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()
