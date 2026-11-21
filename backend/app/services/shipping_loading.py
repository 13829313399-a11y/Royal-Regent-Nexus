"""Build DK container loading sheets from shipping tasks and the source email."""
import io
import json
import re
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from uuid import uuid4

import xlrd
import xlwt
from xlutils.copy import copy
from fastapi import HTTPException
from sqlalchemy import func, select

from app.models.shipping_mail import (
    ShippingGeneratedDoc,
    ShippingLoadingSheet,
    ShippingMailItem,
    ShippingTask,
)
from app.models.customer_order_ledger import OrderLedgerLine
from app.services.auth import AuthContext
from app.services import file_open, shipping_exports
from app.services.shipping_mail_service import authorize, task_fields

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
    sheet_count = db.scalar(
        select(func.count()).select_from(ShippingLoadingSheet).where(
            ShippingLoadingSheet.factory_id == factory_id,
            ShippingLoadingSheet.sheet_date == day,
        )
    ) or 0
    doc_count = db.scalar(
        select(func.count()).select_from(ShippingGeneratedDoc).where(
            ShippingGeneratedDoc.factory_id == factory_id,
            ShippingGeneratedDoc.module == 'so_dk',
            ShippingGeneratedDoc.created_at.like(f'{day}%'),
        )
    ) or 0
    return f'W{int(doc_count or sheet_count) + 1}'


def _existing_doc_number(db, factory_id: str, task_id: str) -> str:
    row = db.scalar(select(ShippingGeneratedDoc).where(
        ShippingGeneratedDoc.factory_id == factory_id,
        ShippingGeneratedDoc.task_id == task_id,
        ShippingGeneratedDoc.module == 'so_dk',
    ).order_by(ShippingGeneratedDoc.created_at.desc()))
    if row is None:
        return ''
    try:
        return str((json.loads(row.header_json or '{}') or {}).get('number') or '')
    except (TypeError, ValueError):
        return ''


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
    match = re.search(r'(\d{2})\s*[xX*]?\s*(HQ|GP|HC|OT|FR|RF)', value or '', re.I)
    if match:
        return f'{match.group(1)}{match.group(2).upper()}'
    return '40HQ'


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
    provided = _number(item.get('coefficient') or item.get('pack_qty') or item.get('pieces_per_carton'))
    if provided and not cartons and quantity:
        cartons = quantity / provided
    coefficient = provided or (quantity / cartons if quantity and cartons else None)
    if coefficient and cartons and not quantity:
        quantity = coefficient * cartons
    gross_per_carton = gross / cartons if gross and cartons else None
    net_per_carton = net / cartons if net and cartons else None
    total_quantity = quantity if quantity is not None else (cartons * coefficient if cartons and coefficient is not None else None)
    return {
        'id': uuid4().hex,
        'tradingCompany': 'DK',
        'contract': str(fields.get('contract_no') or item.get('contract_no') or ''),
        'filingCode': str(item.get('product_code') or ''),
        'declareCode': str(item.get('product_code') or ''),
        'coefficient': _round(coefficient),
        'quantity': _round(total_quantity),
        'cartons': _round(cartons),
        'grossWeight': _round(cartons * gross_per_carton) if cartons and gross_per_carton else _round(gross),
        'netWeight': _round(cartons * net_per_carton) if cartons and net_per_carton else _round(net),
        'cbm': _round(_number(item.get('cbm'))),
        'category': '塑胶',
        'grossPerCarton': _round(gross_per_carton),
        'netPerCarton': _round(net_per_carton),
        'description': str(item.get('product_name') or ''),
        'department': DEPARTMENT,
        'cartonMark': str(item.get('customer_po') or item.get('po') or ''),
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


def _transport_company_name(value: str) -> str:
    return str(value or '').strip()


def task_transport(task: ShippingTask, fields: dict, default: str = '成隆达') -> str:
    value = _transport_company_name(fields.get('transport_company') or fields.get('transportCompany') or '')
    if value:
        return value
    try:
        items = json.loads(task.items_json or '[]')
    except (TypeError, ValueError):
        items = []
    for item in items if isinstance(items, list) else []:
        value = _transport_company_name((item or {}).get('transport_company') or '')
        if value:
            return value
    return default


def sheet_title(header: dict) -> str:
    transport = str(header.get('transportCompany') or '成隆达').strip()
    if not transport.endswith('运输'):
        transport = f'{transport}运输'
    port = str(header.get('originPort') or '盐田').strip()
    return f'{transport}出{port}'


def sheet_stem(header: dict) -> str:
    so_number = str(header.get('soNo') or header.get('so_number') or '').strip()
    po_number = str(header.get('poNo') or header.get('po_no') or '').strip()
    reference = so_number or po_number
    return f'{sheet_title(header)}_{reference}' if reference else sheet_title(header)


def sheet_filename(header: dict) -> str:
    return f'{sheet_stem(header)}.xls'


def sheet_xlsx_filename(header: dict) -> str:
    return f'{sheet_stem(header)}.xlsx'


def _consignee(task: ShippingTask, fields: dict) -> str:
    value = str(fields.get('consignee') or fields.get('receiver') or '').strip()
    if value:
        return value
    try:
        items = json.loads(task.items_json or '[]')
    except (TypeError, ValueError):
        items = []
    for item in items if isinstance(items, list) else []:
        value = str((item or {}).get('consignee') or '').strip()
        if value:
            return value
    return str(task.customer or '').strip()


def _email_date(value: object) -> str:
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except (TypeError, ValueError):
        return text[:10] if re.match(r'^\d{4}-\d{2}-\d{2}', text) else ''


def _header(task: ShippingTask, fields: dict, number: str) -> dict:
    today = _today()
    try:
        items = json.loads(task.items_json or '[]')
    except (TypeError, ValueError):
        items = []
    po_no = ''
    contract_no = ''
    filing_code = ''
    brand_note = str(fields.get('brand') or fields.get('brand_name') or '')
    for item in items if isinstance(items, list) else []:
        po_no = po_no or str((item or {}).get('customer_po') or '').strip()
        contract_no = contract_no or str((item or {}).get('contract_no') or '').strip()
        filing_code = filing_code or str((item or {}).get('product_code') or '').strip()
        brand_note = brand_note or str((item or {}).get('brand') or '').strip()
    return {
        'shipper': SHIPPER,
        'consignee': _consignee(task, fields),
        'tradingCompany': 'DK',
        'soNo': task.so_number or str(fields.get('so_number') or ''),
        'poNo': po_no,
        'contractNo': contract_no or str(fields.get('contract_no') or ''),
        'filingCode': filing_code,
        'vessel': str(fields.get('vessel_name') or ''),
        'voyage': str(fields.get('voyage_no') or ''),
        'containerType': _container_label(task.container_type or str(fields.get('container_type') or '')),
        'cutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'sheetDate': (_email_date(fields.get('received_at')) or today.isoformat()),
        'preparer': PREPARERS[0],
        'brandNote': brand_note,
        'originPort': _port_label(str(task.port or fields.get('from_port') or '')),
        'transportCompany': task_transport(task, fields),
        'number': number,
        'plate': '',
        'containerNo': '',
        'sealNo': '',
        'tareWeight': '',
        'destinationCountry': task.destination_country or str(fields.get('destination_country') or ''),
        'destination': str(fields.get('destination') or fields.get('to_port') or ''),
        'bookingDate': str(fields.get('booking_date') or ''),
        'bookingNo': str(fields.get('booking_no') or fields.get('so_number') or ''),
        'tradeTerm': str(fields.get('trade_term') or 'FOB'),
        'shippingClerk': str(fields.get('shipping_clerk') or PREPARERS[0]),
        'truckHead': str(fields.get('truck_head') or ''),
        'cartonMark': str(fields.get('carton_mark') or ''),
        'blNo': str(fields.get('bl_no') or ''),
        'photoNote': '注，要照相',
        'department': DEPARTMENT,
        'remark': '',
    }


def draft(db, user: AuthContext, factory_id: str, task_id: str) -> dict:
    authorize(user, factory_id, 'read')
    task = db.scalar(select(ShippingTask).where(ShippingTask.id == task_id, ShippingTask.factory_id == factory_id))
    if task is None:
        raise HTTPException(404, '船务排期不存在')
    fields = task_fields(db, task)

    lines = [_line_from_item(item, fields) for item in json.loads(task.items_json or '[]')]
    number = _existing_doc_number(db, factory_id, task.id) or next_number(db, factory_id)
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


def _style_from_template(book, xf_index: int) -> xlwt.XFStyle:
    xf = book.xf_list[xf_index]
    style = xlwt.XFStyle()
    font = book.font_list[xf.font_index]
    style.font = xlwt.Font()
    style.font.name = font.name
    style.font.height = font.height
    style.font.bold = bool(font.bold)
    style.font.italic = bool(font.italic)
    style.font.underline = font.underline_type
    style.font.colour_index = font.colour_index
    style.font.struck_out = bool(font.struck_out)
    border = xf.border
    style.borders = xlwt.Borders()
    style.borders.left = border.left_line_style
    style.borders.right = border.right_line_style
    style.borders.top = border.top_line_style
    style.borders.bottom = border.bottom_line_style
    style.borders.left_colour = border.left_colour_index
    style.borders.right_colour = border.right_colour_index
    style.borders.top_colour = border.top_colour_index
    style.borders.bottom_colour = border.bottom_colour_index
    background = xf.background
    if background.fill_pattern:
        style.pattern = xlwt.Pattern()
        style.pattern.pattern = background.fill_pattern
        style.pattern.pattern_fore_colour = background.pattern_colour_index
        style.pattern.pattern_back_colour = background.background_colour_index
    alignment = xf.alignment
    style.alignment = xlwt.Alignment()
    style.alignment.horz = alignment.hor_align
    style.alignment.vert = alignment.vert_align
    style.alignment.wrap = alignment.text_wrapped
    style.alignment.rota = alignment.rotation
    style.alignment.inde = alignment.indent_level
    style.alignment.shri = alignment.shrink_to_fit
    try:
        format_string = book.format_map[xf.format_key].format_str
    except KeyError:
        format_string = 'General'
    style.num_format_str = format_string or 'General'
    return style
DK_TEMPLATE = Path(__file__).resolve().parent.parent / 'templates' / 'dk_w11_coefficient.xls'


def _render_template(payload: dict) -> bytes:
    """Fill the original DK W11 workbook so borders, fills and print settings stay identical."""
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    book_in = xlrd.open_workbook(str(DK_TEMPLATE), formatting_info=True)
    for fmt in book_in.format_map.values():
        if fmt.format_str is None:
            fmt.format_str = 'General'
    book = copy(book_in)
    sheet = book.get_sheet(0)
    sheet.name = sheet_title(header)[:31]
    book._Workbook__worksheets = [sheet]
    book._Workbook__worksheet_idx_from_name = {sheet.name: 0}
    book._Workbook__active_sheet = 0
    sheet.portrait = False
    sheet.paper_size_code = 9
    sheet.print_scaling = 100
    sheet.fit_num_pages = 1
    sheet.fit_width_to_pages = 1
    sheet.fit_height_to_pages = 1
    sheet.print_centered_horz = 1
    sheet.print_centered_vert = 1
    sheet.print_grid = False
    sheet.left_margin = 0.16
    sheet.right_margin = 0.16
    sheet.top_margin = 0.3
    sheet.bottom_margin = 0.3
    sheet.row(6).height = 800
    for row_index in range(0, 4):
        sheet.row(row_index).height = 760
    sheet.row(4).height = 600
    sheet.row(5).height = 620
    source = book_in.sheet_by_index(0)
    cache: dict[int, xlwt.XFStyle] = {}

    def style_at(row: int, col: int) -> xlwt.XFStyle:
        index = source.cell_xf_index(row, col)
        if index not in cache:
            cache[index] = _style_from_template(book_in, index)
        return cache[index]

    def write(row: int, col: int, value, style_row: int | None = None, style_col: int | None = None, style=None):
        row_obj = sheet.row(row)
        cells = getattr(row_obj, '_Row__cells', {})
        if col in cells:
            del cells[col]
        sheet.write(row, col, value if value is not None else '', style or style_at(style_row if style_row is not None else row, style_col if style_col is not None else col))

    write(0, 0, f'发货商：{header.get("shipper") or SHIPPER}')
    write(0, 11, f'柜S/O:{header.get("soNo") or ""}')
    write(1, 0, f'收货商：{header.get("consignee") or ""}')
    write(1, 11, f'船名:{header.get("vessel") or ""}')
    write(2, 0, 'TO: ')
    write(2, 1, '谢国祥')
    write(2, 11, f'航次:{header.get("voyage") or ""}')
    write(3, 0, 'CC:')
    write(3, 1, 'Carmen')
    write(3, 11, f'提单号：{header.get("blNo") or ""}')
    transport = header.get('transportCompany') or '成隆达'
    if not str(transport).endswith('运输'):
        transport = f'{transport}运输'
    write(3, 4, f'{transport.rstrip("，, ")}，出{header.get("originPort") or "盐田"}')
    try:
        day = date.fromisoformat(str(header.get('sheetDate') or '')[:10])
        date_style = _style_from_template(book_in, source.cell_xf_index(4, 1))
        date_style.num_format_str = 'm/d'
        write(4, 1, datetime(day.year, day.month, day.day), style=date_style)
    except ValueError:
        write(4, 1, header.get('sheetDate') or '')
    write(4, 11, header.get('number') or '')
    write(4, 12, '柜')
    write(5, 1, header.get('destinationCountry') or '')
    write(5, 3, f'柜型:{header.get("containerType") or "40HQ"}')
    write(5, 5, f'成交方式：{header.get("tradeTerm") or "FOB"}')
    write(5, 11, '         载柜号:')

    def header_align_style(row: int, col: int) -> xlwt.XFStyle:
        style = _style_from_template(book_in, source.cell_xf_index(row, col))
        style.alignment.horz = xlwt.Alignment.HORZ_LEFT
        style.alignment.vert = xlwt.Alignment.VERT_CENTER
        style.alignment.wrap = 1
        return style

    for row, text in (
        (0, f'柜S/O:{header.get("soNo") or ""}'),
        (1, f'船名:{header.get("vessel") or ""}'),
        (2, f'航次:{header.get("voyage") or ""}'),
        (3, f'提单号：{header.get("blNo") or ""}'),
        (4, header.get('number') or ''),
        (5, '         载柜号:'),
    ):
        write(row, 11, text, style=header_align_style(row, 11))
    write(4, 12, '柜', style=header_align_style(4, 12))

    for index in range(5):
        row = 7 + index
        if index >= len(lines):
            for col in range(16):
                write(row, col, '')
            continue
        line = lines[index]
        quantity = line.get('quantity')
        cartons = line.get('cartons')
        coefficient = line.get('coefficient')
        if coefficient in (None, 0) and quantity and cartons:
            coefficient = _number(quantity) / _number(cartons) if _number(cartons) else None
        values = [index + 1, line.get('tradingCompany') or 'DK', line.get('contract') or '',
                  line.get('filingCode') or '', line.get('declareCode') or '', quantity, cartons,
                  None, None, line.get('cbm'), line.get('category') or '塑胶',
                  line.get('grossPerCarton'), line.get('netPerCarton'),
                  line.get('description') or '', line.get('cartonMark') or header.get('cartonMark') or '',
                  line.get('department') or DEPARTMENT]
        for col, value in enumerate(values):
            write(row, col, value)
        if coefficient and cartons:
            write(row, 5, round(float(coefficient) * float(cartons), 3))
        if line.get('grossPerCarton') not in (None, '') and cartons:
            write(row, 7, round(float(line.get('grossPerCarton')) * float(cartons), 3))
        else:
            write(row, 7, line.get('grossWeight'))
        if line.get('netPerCarton') not in (None, '') and cartons:
            write(row, 8, round(float(line.get('netPerCarton')) * float(cartons), 3))
        else:
            write(row, 8, line.get('netWeight'))

    write(15, 6, f'车牌:{header.get("plate") or ""}')
    write(16, 4, header.get('photoNote') or '注:要照相')
    write(16, 6, f'柜号：{header.get("containerNo") or ""}')
    write(17, 6, f'封条号：{header.get("sealNo") or ""}')
    write(17, 11, f'品牌:{header.get("brandNote") or ""}')
    tare = str(header.get('tareWeight') or '')
    write(18, 6, f'空柜重量:{tare}{"KGS" if tare and not tare.upper().endswith("KGS") else ""}')
    write(19, 4, '     合计')
    totals = compute_totals(lines)
    for col, key in ((5, 'quantity'), (6, 'cartons'), (7, 'grossWeight'), (8, 'netWeight'), (9, 'cbm')):
        write(19, col, totals.get(key) or 0, style_row=19, style_col=col)
    write(20, 0, f' 截数期: {_display_cutoff(header.get("cutoff") or "")}')
    write(20, 8, f'      日期  : {_format_date(header.get("sheetDate") or "")}')
    write(20, 12, f'制表人: {header.get("preparer") or PREPARERS[0]}')

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def render_xls(payload: dict) -> bytes:
    if DK_TEMPLATE.exists():
        return _render_template(payload)
    return _render_built(payload)


def _render_built(payload: dict) -> bytes:
    """Render the DK sheet with the exact W11 template geometry (33 rows / 17 columns)."""
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book = xlwt.Workbook(encoding='utf-8')
    sheet = book.add_sheet(sheet_title(header)[:31])

    widths = [1900, 3264, 3264, 4454, 1632, 1568, 1952, 1920, 1792, 1344, 1632, 1600, 3402, 1300]
    for index, width in enumerate(widths):
        sheet.col(index).width = width
    for row in range(33):
        sheet.row(row).height = 620
    sheet.portrait = True
    sheet.paper_size_code = 9
    sheet.print_scaling = 70
    sheet.fit_num_pages = 1
    sheet.fit_width_to_pages = 1
    sheet.fit_height_to_pages = 1
    sheet.left_margin = 0.24
    sheet.right_margin = 0.16
    sheet.top_margin = 0.53
    sheet.bottom_margin = 0.51

    font = xlwt.Font(); font.name = '宋体'; font.height = 220
    bold_font = xlwt.Font(); bold_font.name = '宋体'; bold_font.height = 220; bold_font.bold = True
    title_font = xlwt.Font(); title_font.name = '宋体'; title_font.height = 240
    borders = xlwt.Borders()
    for side in ('left', 'right', 'top', 'bottom'):
        setattr(borders, side, xlwt.Borders.THIN)
    base = xlwt.XFStyle(); base.font = font; base.borders = borders
    bold = xlwt.XFStyle(); bold.font = bold_font; bold.borders = borders
    plain_bold = xlwt.XFStyle(); plain_bold.font = bold_font
    title = xlwt.XFStyle(); title.font = title_font
    date_style = xlwt.XFStyle(); date_style.num_format_str = 'm"月"d"日"'; date_style.font = font; date_style.borders = borders
    center = xlwt.Alignment(); center.horz = xlwt.Alignment.HORZ_CENTER; center.vert = xlwt.Alignment.VERT_CENTER; center.wrap = 1
    left = xlwt.Alignment(); left.horz = xlwt.Alignment.HORZ_LEFT; left.vert = xlwt.Alignment.VERT_CENTER; left.wrap = 1
    base.alignment = left; bold.alignment = center

    def put(row, col, value, style=base):
        sheet.write(row, col, value if value is not None else '', style)

    merged = {
        (0, 10): (f'柜S/O:{header.get("soNo") or ""}', bold),
        (1, 10): (f'船名:{header.get("vessel") or ""}', bold),
        (2, 10): (f'航次:{header.get("voyage") or ""}', bold),
        (3, 10): (f'提单号：{header.get("blNo") or ""}', bold),
        (15, 5): (f'车牌:{header.get("plate") or ""}', title),
        (16, 5): (f'柜号：{header.get("containerNo") or ""}', title),
        (16, 10): (f'注:{header.get("brandNote") or ""}', title),
        (17, 5): (f'封条号：{header.get("sealNo") or ""}', title),
        (18, 5): (f'空柜重量:{header.get("tareWeight") or ""}', title),
    }
    for r1, c1, r2, c2 in (
        (0, 10, 0, 13), (1, 10, 1, 13), (2, 10, 2, 13), (3, 10, 3, 13),
        (15, 5, 15, 7), (16, 5, 16, 7), (16, 10, 16, 12), (17, 5, 17, 7),
        (17, 10, 17, 12), (18, 5, 18, 7), (18, 10, 18, 12), (19, 10, 19, 12),
    ):
        value, style = merged.get((r1, c1), ('', base))
        sheet.write_merge(r1, r2, c1, c2, value, style)

    put(0, 0, f'发货商：{header.get("shipper") or SHIPPER}', plain_bold)
    put(1, 0, f'收货商：{header.get("consignee") or ""}', plain_bold)
    put(2, 0, 'TO: ', plain_bold)
    put(2, 1, '谢国祥', plain_bold)
    put(3, 0, 'CC:', plain_bold)
    put(3, 1, 'Carmen', plain_bold)

    try:
        day = date.fromisoformat(str(header.get('sheetDate') or '')[:10])
        put(4, 1, datetime(day.year, day.month, day.day), date_style)
    except ValueError:
        put(4, 1, header.get('sheetDate') or '')
    transport = header.get('transportCompany') or ''
    port = header.get('originPort') or ''
    put(4, 4, f'{transport}运输，出{port}' if transport else f'出{port}', plain_bold)
    put(4, 10, header.get('number') or '', bold)
    put(4, 11, '柜', plain_bold)
    put(5, 0, '国名：', plain_bold)
    put(5, 1, header.get('destinationCountry') or '', plain_bold)
    put(5, 4, f'     柜型:{header.get("containerType") or "40HQ"}', plain_bold)
    put(5, 10, '         载柜号:', plain_bold)

    headers = ['洋行', '合同', '备案货号', '走货申报货号', '数量', '件数', '毛重', '净重', '体积CBM',
               '玩具类别', 'KG/箱\n（毛重）', 'KG/箱\n（净重）', '每单/\n总件数', '部门']
    for col, text in enumerate(headers):
        put(6, col, text, bold)

    for index in range(5):
        row = 7 + index
        if index >= len(lines):
            for col in range(14):
                put(row, col, '')
            continue
        line = lines[index]
        quantity = line.get('quantity')
        cartons = line.get('cartons')
        coefficient = line.get('coefficient')
        if coefficient in (None, 0) and quantity and cartons:
            coefficient = _number(quantity) / _number(cartons) if _number(cartons) else None
        gross_per = line.get('grossPerCarton')
        net_per = line.get('netPerCarton')
        values = [line.get('tradingCompany') or 'DK', line.get('contract') or '', line.get('filingCode') or '',
                  line.get('declareCode') or '', quantity, None, None, None, line.get('cbm'),
                  line.get('category') or '塑胶', gross_per, net_per, line.get('description') or '',
                  line.get('department') or DEPARTMENT]
        for col, value in enumerate(values):
            if value is not None:
                put(row, col, value)
        excel_row = row + 1
        if coefficient:
            coefficient_text = f'{float(coefficient):g}'
            put(row, 5, xlwt.Formula(f'E{excel_row}/{coefficient_text}'))
        else:
            put(row, 5, cartons)
        if gross_per not in (None, ''):
            put(row, 6, xlwt.Formula(f'K{excel_row}*F{excel_row}'))
        else:
            put(row, 6, line.get('grossWeight'))
        if net_per not in (None, ''):
            put(row, 7, xlwt.Formula(f'L{excel_row}*F{excel_row}'))
        else:
            put(row, 7, line.get('netWeight'))

    put(20, 3, '     合计', bold)
    for col, letter in ((4, 'E'), (5, 'F'), (6, 'G'), (7, 'H'), (8, 'I')):
        put(20, col, xlwt.Formula(f'SUM({letter}8:{letter}12)'), bold)

    put(16, 3, header.get('photoNote') or '注，要照相', title)

    put(22, 0, f' 截数期 {_display_cutoff(header.get("cutoff") or "")}', title)
    put(22, 7, f'      日期   {_format_date(header.get("sheetDate") or "")}', title)
    put(23, 0, ' 制表人:', title)
    put(23, 1, header.get('preparer') or PREPARERS[0], title)

    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def schedule_lines(db, user: AuthContext, factory_id: str, query: str) -> dict:
    authorize(user, factory_id, 'read')
    keyword = (query or '').strip().lower()
    if not keyword:
        raise HTTPException(422, '请输入合同号、SO 或备案货号')
    tasks = db.scalars(select(ShippingTask).where(ShippingTask.factory_id == factory_id)).all()
    rows = []
    seen = set()
    for task in tasks:
        so_number = str(task.so_number or '')
        try:
            items = json.loads(task.items_json or '[]')
        except (TypeError, ValueError):
            continue
        for item in items if isinstance(items, list) else []:
            contract = str((item or {}).get('contract_no') or '')
            product = str((item or {}).get('product_code') or '')
            haystack = f'{contract} {so_number} {product}'.lower()
            if keyword not in haystack:
                continue
            key = (contract, product, so_number)
            if key in seen:
                continue
            seen.add(key)
            rows.append({**(item or {}), 'so_number': so_number, 'customer': task.customer})
    return {'lines': rows[:200]}


def search_products(db, user: AuthContext, factory_id: str, query: str) -> dict:
    authorize(user, factory_id, 'read')
    needle = (query or '').strip().lower()
    if not needle:
        return {'items': []}
    tokens = [token for token in re.split(r'[\s/,，]+', needle) if token]
    rows: list[dict] = []
    seen: set[tuple[str, str, str]] = set()

    def add(item: dict, so_number: str = '', customer: str = '', source: str = 'schedule') -> None:
        code = str(item.get('product_code') or '').strip()
        contract = str(item.get('contract_no') or '').strip()
        if not code:
            return
        haystack = f'{code} {contract} {item.get("customer_po") or ""} {so_number} {item.get("booking_no") or ""}'.lower()
        if not all(token in haystack for token in tokens):
            return
        key = (contract, code, so_number)
        if key in seen:
            return
        seen.add(key)
        rows.append({**item, 'so_number': so_number, 'customer': customer, 'source': source})

    tasks = db.scalars(select(ShippingTask).where(ShippingTask.factory_id == factory_id)).all()
    for task in tasks:
        try:
            items = json.loads(task.items_json or '[]')
        except (TypeError, ValueError):
            items = []
        for item in items if isinstance(items, list) else []:
            add(item or {}, str(task.so_number or ''), str(task.customer or ''), 'schedule')

    ledger = db.scalars(select(OrderLedgerLine).where(
        OrderLedgerLine.factory_id == factory_id,
        OrderLedgerLine.status == 'active',
    )).all()
    for line in ledger:
        data = line.data if isinstance(line.data, dict) else {}
        contract = str(data.get('contract_no') or '')
        key = (contract, line.product_no or '', line.reference_no or '')
        if key in seen:
            continue
        add({
            'product_code': line.product_no,
            'product_name': data.get('product_name_zh') or data.get('product_name') or '',
            'quantity': float(line.quantity or 0),
            'cartons': data.get('carton_count'),
            'coefficient': data.get('coefficient'),
            'gross_weight': data.get('gross_weight'),
            'net_weight': data.get('net_weight'),
            'cbm': data.get('cbm'),
            'contract_no': contract,
            'customer_po': data.get('po_no'),
            'country': data.get('country'),
            'consignee': data.get('consignee'),
            'brand': data.get('brand') or data.get('brand_name') or data.get('brandName') or '',
        }, str(line.reference_no or ''), str(line.customer_name or ''), 'order')
    return {'items': rows[:200]}


def _sheet_codes(header: dict, lines: list) -> list[str]:
    codes: list[str] = []
    for line in lines if isinstance(lines, list) else []:
        code = str((line or {}).get('filingCode') or (line or {}).get('declareCode') or '').strip()
        if code and code not in codes:
            codes.append(code)
    header_code = str(header.get('filingCode') or '').strip()
    if not codes and header_code:
        codes.append(header_code)
    return codes


def sheet_code_filename(header: dict, lines: list) -> str:
    codes = _sheet_codes(header, lines)
    base = '_'.join(codes) if codes else 'SO出货表'
    number = str(header.get('number') or '').strip()
    return f'{base}_{number}.xls' if number else f'{base}.xls'


def _number_or_none(value):
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _hq_payload(header: dict, lines: list) -> dict:
    hq_lines = []
    for line in lines if isinstance(lines, list) else []:
        cartons = _number_or_none((line or {}).get('cartons'))
        cbm = _number_or_none((line or {}).get('cbm'))
        hq_lines.append({
            'id': str((line or {}).get('id') or uuid4().hex),
            'tradingHouse': str(header.get('tradingCompany') or (line or {}).get('tradingCompany') or ''),
            'contract': str((line or {}).get('contract') or ''),
            'filingCode': str((line or {}).get('filingCode') or ''),
            'declareCode': str((line or {}).get('declareCode') or ''),
            'brand': str((line or {}).get('brand') or header.get('brandNote') or ''),
            'coefficient': _number_or_none((line or {}).get('coefficient')),
            'quantity': _number_or_none((line or {}).get('quantity')),
            'cartons': cartons,
            'grossWeight': _number_or_none((line or {}).get('grossWeight')),
            'netWeight': _number_or_none((line or {}).get('netWeight')),
            'cbm': cbm,
            'cbmPerCarton': round(cbm / cartons, 6) if cbm and cartons else None,
            'country': str(header.get('destinationCountry') or ''),
            'grossPerCarton': _number_or_none((line or {}).get('grossPerCarton')),
            'netPerCarton': _number_or_none((line or {}).get('netPerCarton')),
            'remark': str((line or {}).get('description') or ''),
            'po': str((line or {}).get('po') or ''),
        })
    vessel_voyage = ' '.join(part for part in (str(header.get('vessel') or '').strip(), str(header.get('voyage') or '').strip()) if part)
    to_names = header.get('toNames')
    if not isinstance(to_names, list) or not to_names:
        to_names = ['苏迪', '罗梓良']
    return {
        'header': {
            'toNames': [str(name) for name in to_names if str(name).strip()],
            'fromName': str(header.get('shippingClerk') or '农建壮'),
            'sheetDate': str(header.get('sheetDate') or _today().isoformat()),
            'cutoff': str(header.get('cutoff') or ''),
            'number': str(header.get('truckHead') or header.get('number') or ''),
            'soNo': str(header.get('soNo') or ''),
            'poNo': '',
            'vesselVoyage': vessel_voyage,
            'blNo': '',
            'transportCompany': str(header.get('transportCompany') or ''),
            'containerType': str(header.get('containerType') or ''),
            'tradeTerm': str(header.get('tradeTerm') or 'FOB'),
            'plate': str(header.get('plate') or ''),
            'containerNo': str(header.get('containerNo') or ''),
            'sealNo': str(header.get('sealNo') or ''),
            'tareWeight': str(header.get('tareWeight') or ''),
            'originPort': str(header.get('originPort') or '盐田'),
            'destinationCountry': str(header.get('destinationCountry') or ''),
        },
        'lines': hq_lines,
    }


def _sheet_variant(header: dict) -> str:
    return 'hq' if str(header.get('_variant') or '').lower() == 'hq' else 'dk'


def _sheet_filename(header: dict, lines: list) -> str:
    if _sheet_variant(header) == 'hq':
        codes = _sheet_codes(header, lines)
        base = '_'.join(codes) if codes else f"HQ柜出货_{header.get('soNo') or header.get('number') or '未命名'}"
        return f'{base}.xlsx'
    return sheet_code_filename(header, lines)


def export_sheet(db, user: AuthContext, factory_id: str, payload: dict) -> tuple[str, bytes]:
    authorize(user, factory_id, 'import')
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    task_id = str(payload.get('taskId') or '')
    if task_id:
        task = db.scalar(select(ShippingTask).where(
            ShippingTask.id == task_id, ShippingTask.factory_id == factory_id,
        ))
        if task is not None:
            email_day = _email_date(task_fields(db, task).get('received_at'))
            if email_day:
                header['sheetDate'] = email_day
    variant = 'hq' if str(payload.get('variant') or 'dk').lower() == 'hq' else 'dk'
    header['_variant'] = variant
    number = str(header.get('number') or '').strip() or next_number(db, factory_id)
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
    filename = _sheet_filename(header, lines)
    if variant == 'hq':
        from app.services import shipping_zuru
        content = shipping_zuru.render_hq_xlsx(_hq_payload(header, lines))
        module = 'so_zuru'
    else:
        content = render_xls({'header': header, 'lines': lines})
        module = 'so_dk'
    try:
        shipping_exports.save_import_file(module, filename, content)
    except Exception:  # noqa: BLE001 - drop-folder copy is best effort
        pass
    return filename, content


def list_sheets(db, user: AuthContext, factory_id: str, limit: int = 50, variant: str | None = None) -> list[dict]:
    authorize(user, factory_id, 'read')
    rows = db.scalars(
        select(ShippingLoadingSheet)
        .where(ShippingLoadingSheet.factory_id == factory_id)
        .order_by(ShippingLoadingSheet.created_at.desc())
        .limit(limit)
    ).all()
    result = []
    for row in rows:
        header = json.loads(row.header_json or '{}')
        current = _sheet_variant(header)
        if variant and current != variant:
            continue
        lines = json.loads(row.lines_json or '[]')
        result.append({
            'id': row.id, 'number': row.number, 'sheetDate': row.sheet_date,
            'filename': _sheet_filename(header, lines),
            'filingCodes': _sheet_codes(header, lines),
            'variant': current,
            'task_id': row.task_id,
            'soNo': header.get('soNo') or '',
            'contractNo': header.get('contractNo') or '',
            'transportCompany': _transport_company_name(header.get('transportCompany') or ''),
            'originPort': header.get('originPort') or '',
            'createdAt': row.created_at, 'totals': json.loads(row.totals_json or '{}'),
        })
    return result


def _load_sheet(db, user: AuthContext, factory_id: str, sheet_id: str):
    authorize(user, factory_id, 'read')
    row = db.get(ShippingLoadingSheet, sheet_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '柜货单不存在')
    header = json.loads(row.header_json or '{}')
    lines = json.loads(row.lines_json or '[]')
    return row, header, lines


def get_sheet(db, user: AuthContext, factory_id: str, sheet_id: str) -> dict:
    row, header, lines = _load_sheet(db, user, factory_id, sheet_id)
    header['transportCompany'] = _transport_company_name(header.get('transportCompany') or '')
    return {
        'id': row.id, 'number': row.number, 'sheetDate': row.sheet_date,
        'filename': _sheet_filename(header, lines), 'createdAt': row.created_at,
        'filingCodes': _sheet_codes(header, lines), 'variant': _sheet_variant(header),
        'task_id': row.task_id,
        'header': header, 'lines': lines, 'totals': json.loads(row.totals_json or '{}'),
    }


def open_sheet(db, user: AuthContext, factory_id: str, sheet_id: str) -> dict:
    row, header, lines = _load_sheet(db, user, factory_id, sheet_id)
    header['transportCompany'] = _transport_company_name(header.get('transportCompany') or '')
    filename = _sheet_filename(header, lines)
    if _sheet_variant(header) == 'hq':
        from app.services import shipping_zuru
        content = shipping_zuru.render_hq_xlsx(_hq_payload(header, lines))
    else:
        content = render_xls({'header': header, 'lines': lines})
    path = file_open.open_bytes(filename, content)
    return {'path': path, 'filename': filename}


def delete_sheet(db, user: AuthContext, factory_id: str, sheet_id: str) -> dict:
    authorize(user, factory_id, 'write')
    row = db.get(ShippingLoadingSheet, sheet_id)
    if row is None or row.factory_id != factory_id:
        raise HTTPException(404, '柜货单不存在')
    header = json.loads(row.header_json or '{}')
    lines = json.loads(row.lines_json or '[]')
    filenames = {_sheet_filename(header, lines), sheet_filename(header)}
    db.delete(row)
    db.commit()
    for name in filenames:
        if not name:
            continue
        try:
            (shipping_exports.EXPORT_ROOT / 'SO 出货表' / shipping_exports._safe_name(name)).unlink(missing_ok=True)
        except OSError:
            pass
    return {'deleted': True}
