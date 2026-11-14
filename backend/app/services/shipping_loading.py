"""Build DK container loading sheets from shipping tasks and the source email."""
import io
import json
from datetime import date, datetime
from uuid import uuid4

import xlwt
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.shipping_mail import (
    ShippingLoadingSheet,
    ShippingMailItem,
    ShippingTask,
)
from app.services.auth import AuthContext
from app.services.shipping_mail_service import authorize

SHIPPER = '华兴玩具制品（河源）有限公司'
PREPARERS = ('农建壮', '小美')
DEPARTMENT = 'W'


def _now() -> str:
    return datetime.now().isoformat(timespec='seconds')


def _new_id() -> str:
    return f'load-{uuid4().hex}'


def _today() -> date:
    return date.today()


def next_number(db, factory_id: str, sheet_date: str | None = None) -> str:
    day = sheet_date or _today().isoformat()
    count = db.scalar(
        select(func.count()).select_from(ShippingLoadingSheet).where(
            ShippingLoadingSheet.factory_id == factory_id,
            ShippingLoadingSheet.sheet_date == day,
        )
    ) or 0
    return f'W{11 + int(count)}'


def _port_label(from_port: str) -> str:
    upper = (from_port or '').upper()
    if 'YANTIAN' in upper or '盐田' in from_port:
        return '盐田'
    if 'SHEKOU' in upper or '蛇口' in from_port:
        return '蛇口'
    if 'NANSHA' in upper or '南沙' in from_port:
        return '南沙'
    if 'CHIWAN' in upper or '赤湾' in from_port:
        return '赤湾'
    return (from_port or '').strip()[:20]


def _container_label(value: str) -> str:
    return (value or '').replace('1*', '').replace('*', '') or '40HQ'


def _number(value) -> float | None:
    if value in (None, ''):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line_from_item(item: dict, fields: dict) -> dict:
    cartons = _number(item.get('cartons'))
    quantity = _number(item.get('quantity'))
    gross = _number(item.get('gross_weight'))
    net = _number(item.get('net_weight'))
    coefficient = quantity / cartons if quantity and cartons else None
    gross_per_carton = gross / cartons if gross and cartons else None
    net_per_carton = net / cartons if net and cartons else None
    total_quantity = cartons * coefficient if cartons and coefficient is not None else quantity
    return {
        'id': uuid4().hex,
        'tradingCompany': 'DK',
        'contract': str(fields.get('contract_no') or ''),
        'filingCode': str(item.get('product_code') or ''),
        'declareCode': str(item.get('product_code') or ''),
        'coefficient': _round(coefficient),
        'quantity': _round(total_quantity),
        'cartons': _round(cartons),
        'grossWeight': _round(cartons * gross_per_carton) if cartons and gross_per_carton else _round(gross),
        'netWeight': _round(cartons * net_per_carton) if cartons and net_per_carton else _round(net),
        'cbm': _round(_number(item.get('cbm'))),
        'category': '',
        'grossPerCarton': _round(gross_per_carton),
        'netPerCarton': _round(net_per_carton),
        'description': str(item.get('product_name') or ''),
        'department': DEPARTMENT,
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_number(line.get(key)) or 0 for line in lines), 3)
    return {
        'quantity': total('quantity'),
        'cartons': total('cartons'),
        'grossWeight': total('grossWeight'),
        'netWeight': total('netWeight'),
        'cbm': total('cbm'),
    }


def _header(task: ShippingTask, fields: dict, number: str) -> dict:
    today = _today()
    return {
        'shipper': SHIPPER,
        'consignee': '',
        'tradingCompany': 'DK',
        'soNo': task.so_number or str(fields.get('so_number') or ''),
        'vessel': str(fields.get('vessel_name') or ''),
        'voyage': str(fields.get('voyage_no') or ''),
        'containerType': _container_label(task.container_type or str(fields.get('container_type') or '')),
        'cutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'sheetDate': today.isoformat(),
        'preparer': PREPARERS[0],
        'brandNote': '',
        'originPort': _port_label(str(fields.get('from_port') or task.port or '')),
        'transportCompany': '',
        'number': number,
        'plate': '',
        'containerNo': '',
        'sealNo': '',
        'tareWeight': '',
        'destinationCountry': task.destination_country or str(fields.get('destination_country') or ''),
        'bookingDate': str(fields.get('booking_date') or ''),
        'photoNote': '注，要照相',
        'department': DEPARTMENT,
        'remark': '',
    }


def draft(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
    authorize(user, factory_id, 'read')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务排期不存在')
    fields = {}
    if task.mail_item_id:
        item = db.get(ShippingMailItem, task.mail_item_id)
        if item is not None:
            fields = json.loads(item.fields_json or '{}')
    lines = [_line_from_item(item, fields) for item in json.loads(task.items_json or '[]')]
    number = next_number(db, factory_id)
    return {
        'number': number,
        'header': _header(task, fields, number),
        'lines': lines,
        'totals': compute_totals(lines),
        'taskId': task.id,
    }


def _format_date(value: str) -> str:
    text = (value or '')[:10]
    try:
        day = date.fromisoformat(text)
    except ValueError:
        return value or ''
    return f'{day.year}年{day.month}月{day.day}日'


def _display_cutoff(value: str) -> str:
    if not value:
        return ''
    if 'T' in value:
        day, clock = value.split('T', 1)
        return f'{_format_date(day)} {clock[:5]}'
    return _format_date(value)


def render_xls(payload: dict) -> bytes:
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = xlwt.Workbook(encoding='utf-8')
    sheet = book.add_sheet((header.get('originPort') or 'SO出货表')[:31])
    thin = xlwt.easyxf('borders: left thin, right thin, top thin, bottom thin; align: vert centre;')
    bold = xlwt.easyxf('font: bold on; borders: left thin, right thin, top thin, bottom thin; align: vert centre;')
    title = xlwt.easyxf('font: bold on; align: vert centre;')
    right = xlwt.easyxf('align: horiz right;')
    widths = [8, 24, 18, 18, 10, 10, 12, 12, 10, 10, 12, 12, 24, 8]
    for index, width in enumerate(widths):
        sheet.col(index).width = 256 * width

    def write(row: int, col: int, value, style=thin):
        sheet.write(row, col, value, style)

    def merge(row1, row2, col1, col2, value, style=title):
        sheet.write_merge(row1, row2, col1, col2, value, style)

    merge(0, 0, 0, 9, f'发货商：{header.get("shipper") or SHIPPER}')
    merge(0, 0, 10, 13, f'柜S/O:{header.get("soNo") or ""}')

    merge(1, 1, 0, 9, f'收货商：{header.get("consignee") or ""}')
    merge(1, 1, 10, 13, f'船名:{header.get("vessel") or ""}')

    merge(2, 2, 0, 9, 'TO: 谢国祥')
    merge(2, 2, 10, 13, f'航次:{header.get("voyage") or ""}')

    merge(3, 3, 0, 9, 'CC: Carmen')
    merge(3, 3, 10, 13, f'提单号：{header.get("bookingDate") or ""}')

    write(4, 1, _format_date(header.get('sheetDate') or ''), thin)
    transport = header.get('transportCompany') or ''
    port = header.get('originPort') or ''
    merge(4, 4, 4, 9, f'{transport}运输，出{port}' if transport else f'出{port}')
    write(4, 10, header.get('number') or '', thin)
    write(4, 11, '柜', thin)

    write(5, 0, '国名：', thin)
    write(5, 1, header.get('destinationCountry') or '', thin)
    write(5, 4, f'柜型:{header.get("containerType") or "40HQ"}', thin)
    merge(5, 5, 10, 11, '载柜号:')

    headers = ['洋行', '合同', '备案货号', '走货申报货号', '数量', '件数', '毛重', '净重', '体积CBM', '玩具类别',
               'KG/箱（毛重）', 'KG/箱（净重）', '每单/总件数', '部门']
    for col, text in enumerate(headers):
        write(6, col, text, bold)

    row = 7
    for line in lines:
        values = [
            line.get('tradingCompany') or 'DK', line.get('contract') or '', line.get('filingCode') or '',
            line.get('declareCode') or '', line.get('quantity'), line.get('cartons'), line.get('grossWeight'),
            line.get('netWeight'), line.get('cbm'), line.get('category') or '',
            line.get('grossPerCarton'), line.get('netPerCarton'), line.get('description') or '',
            line.get('department') or DEPARTMENT,
        ]
        for col, value in enumerate(values):
            write(row, col, value if value is not None else '')
        row += 1

    write(row, 3, '合计', bold)
    for col, key in ((4, 'quantity'), (5, 'cartons'), (6, 'grossWeight'), (7, 'netWeight'), (8, 'cbm')):
        write(row, col, totals[key], bold)
    row += 2

    write(row, 0, f'截数期 {_display_cutoff(header.get("cutoff") or "")}', title)
    write(row, 7, f'日期 {_format_date(header.get("sheetDate") or "")}', title)
    row += 1
    write(row, 0, '制表人:', thin)
    write(row, 1, header.get('preparer') or PREPARERS[0], thin)
    row += 2

    write(row, 3, header.get('photoNote') or '注，要照相', title)
    write(row, 5, f'车牌:{header.get("plate") or ""}', title)
    row += 1
    write(row, 5, f'柜号：{header.get("containerNo") or ""}', title)
    row += 1
    write(row, 5, f'封条号：{header.get("sealNo") or ""}', title)
    row += 1
    write(row, 5, f'空柜重量:{header.get("tareWeight") or ""}', title)
    write(row, 10, f'注:{header.get("brandNote") or ""}', title)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def export_sheet(db, user: AuthContext, factory_id: str, payload: dict) -> tuple[str, bytes]:
    authorize(user, factory_id, 'import')
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    number = next_number(db, factory_id)
    header['number'] = number
    totals = compute_totals(lines)
    sheet = ShippingLoadingSheet(
        id=_new_id(), factory_id=factory_id, number=number,
        sheet_date=_today().isoformat(), task_id=str(payload.get('taskId') or ''),
        header_json=json.dumps(header, ensure_ascii=False),
        lines_json=json.dumps(lines, ensure_ascii=False),
        totals_json=json.dumps(totals, ensure_ascii=False),
        created_by=user.id, created_at=_now(),
    )
    db.add(sheet)
    db.commit()
    filename = f'{header.get("originPort") or "待定港口"}SO出货表.xls'
    return filename, render_xls({'header': header, 'lines': lines})


def list_sheets(db, user: AuthContext, factory_id: str, limit: int = 50) -> list[dict]:
    authorize(user, factory_id, 'read')
    rows = db.scalars(
        select(ShippingLoadingSheet)
        .where(ShippingLoadingSheet.factory_id == factory_id)
        .order_by(ShippingLoadingSheet.created_at.desc())
        .limit(limit)
    ).all()
    return [{
        'id': row.id, 'number': row.number, 'sheetDate': row.sheet_date,
        'createdAt': row.created_at, 'totals': json.loads(row.totals_json or '{}'),
    } for row in rows]
