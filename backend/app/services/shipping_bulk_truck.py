"""2026 盐田散货 W-series truck sheets (xlsx)."""
import io
import json
import re
import xlrd
import xlwt
from datetime import date, datetime
from xlutils.copy import copy
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
from app.services.shipping_loading import _style_from_template

TO_NAMES = ('苏迪', '罗梓良')
FROM_NAME = '农建壮'
HEADERS = ['序号', '洋行', '合约', '工厂备案货号', '出货申报货号', '数量', '箱数', '板数', '毛重', '净重',
           'CBM', '出口国家', '每箱毛重', '每箱净重', '每箱体积', '品牌', 'SO', 'PO', '船期', '备注']


def format_table_name(transport: str, origin_port: str) -> str:
    clean_transport = str(transport or '').strip().rstrip('，, ')
    carrier = (clean_transport if clean_transport.endswith('运输') else f'{clean_transport}运输') if clean_transport else ''
    clean_port = str(origin_port or '').strip()
    if carrier and clean_port:
        return f'{carrier}，出{clean_port}'
    if clean_port:
        return f'出{clean_port}'
    return carrier


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _po_text(value) -> str:
    return re.sub(r'^PO[-\s]*', '', str(value or '').strip(), flags=re.I)


def _round(value: float | None) -> float | None:
    return round(value, 3) if value is not None else None


def _line(item: dict, contract: str, so_number: str) -> dict:
    cartons = _number(item.get('cartons'))
    quantity = _number(item.get('quantity'))
    coefficient = quantity / cartons if quantity and cartons else None
    gross_per = _number(item.get('gross_weight')) / cartons if item.get('gross_weight') and cartons else None
    net_per = _number(item.get('net_weight')) / cartons if item.get('net_weight') and cartons else None
    cbm = _number(item.get('cbm'))
    cbm_per = cbm / cartons if cbm and cartons else None
    return {
        'id': uuid4().hex, 'tradingHouse': 'ZURU', 'contract': str(item.get('contract_no') or contract),
        'filingCode': str(item.get('product_code') or ''), 'declareCode': str(item.get('product_code') or ''),
        'name': str(item.get('product_name') or ''),
        'coefficient': _round(coefficient),
        'quantity': _round(cartons * coefficient) if cartons and coefficient else _round(quantity),
        'cartons': _round(cartons), 'boards': '',
        'grossWeight': _round(gross_per * cartons) if gross_per and cartons else _round(item.get('gross_weight')),
        'netWeight': _round(net_per * cartons) if net_per and cartons else _round(item.get('net_weight')),
        'cbm': _round(cbm), 'country': '', 'grossPerCarton': _round(gross_per),
        'netPerCarton': _round(net_per), 'cbmPerCarton': _round(cbm_per), 'brand': str(item.get('brand') or ''),
        'so': so_number, 'po': _po_text(item.get('customer_po')), 'shippingNote': str(item.get('shipping_note') or ''), 'remark': str(item.get('remark') or ''),
    }


def compute_totals(lines: list[dict]) -> dict:
    def total(key: str) -> float:
        return round(sum(_number(line.get(key)) or 0 for line in lines), 3)
    return {key: total(key) for key in ('quantity', 'cartons', 'grossWeight', 'netWeight', 'cbm')}


def _blank_line(so_number: str) -> dict:
    return {
        'id': uuid4().hex, 'tradingHouse': 'ZURU', 'contract': '', 'filingCode': '', 'declareCode': '', 'name': '',
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
    raw_items = json.loads(task.items_json or '[]')
    first_item = raw_items[0] if raw_items and isinstance(raw_items[0], dict) else {}
    lines = [_line(item, contract, task.so_number or '') for item in raw_items]
    for line in lines:
        line['tradingHouse'] = task.customer or line.get('tradingHouse') or 'ZURU'
        if not line.get('country'):
            line['country'] = country
    if not lines:
        lines = [_blank_line(task.so_number or '')]
    vehicle = str(first_item.get('vehicle') or fields.get('vehicle') or 'W218').strip()
    truck_type = str(first_item.get('truck_type') or fields.get('truck_type') or '3T').strip()
    transport = str(first_item.get('transport_company') or fields.get('transport_company') or '建联派').strip()
    brand = str(first_item.get('brand') or fields.get('brand') or task.customer or '').strip()
    raw_port = str(task.port or fields.get('from_port') or '').strip()
    upper_port = raw_port.upper()
    origin_port = '蛇口' if ('蛇' in raw_port or 'SHEKOU' in upper_port) else ('盐田' if ('盐' in raw_port or 'YANTIAN' in upper_port or 'SHATOU' in upper_port) else raw_port)
    port_short = '蛇' if origin_port == '蛇口' else ('盐' if origin_port == '盐田' else '')
    warehouse_no = str(first_item.get('warehouse_no') or fields.get('warehouse_no') or '').strip()
    truck_count = str(first_item.get('truck_count') or fields.get('truck_count') or '1').strip() or '1'
    table_name = format_table_name(transport, origin_port)
    header = {
        'toNames': list(TO_NAMES), 'fromName': FROM_NAME,
        'sheetDate': task.planned_ship_date or date.today().isoformat(),
        'vehicle': vehicle, 'transport': transport, 'truckType': truck_type,
        'tradeTerm': str(fields.get('trade_term') or fields.get('tradeTerm') or 'EXW'),
        'tableName': table_name, 'cutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'originPort': origin_port,
        'warehouseNo': warehouse_no,
        'truckCount': truck_count,
        'brandName': brand, 'brandNote': brand,
        'tradingHouse': str(first_item.get('trading_house') or fields.get('trading_house') or fields.get('tradingHouse') or task.customer or ''),
        'shipper': str(fields.get('shipper') or '华兴玩具制品（河源）有限公司'),
        'plate': str(first_item.get('plate') or fields.get('plate') or ''),
        'consignee': str(fields.get('consignee') or ''),
        'country': country,
        'arrivalCutoff': task.cutoff_date or str(fields.get('cutoff_date') or ''),
        'consolidator': '',
        'scheduleText': str(fields.get('schedule_text') or ''),
    }
    for line in lines:
        if header['tradingHouse']:
            line['tradingHouse'] = header['tradingHouse']
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
    template = Path(__file__).resolve().parent.parent / 'templates' / 'truck_w15.xls'
    header = payload.get('header') or {}
    lines = payload.get('lines') or []
    totals = compute_totals(lines)
    book_in = xlrd.open_workbook(str(template), formatting_info=True)
    for fmt in book_in.format_map.values():
        if fmt.format_str is None:
            fmt.format_str = 'General'
    book = copy(book_in)
    sheet = book.get_sheet(0)
    sheet.name = (header.get('tableName') or format_table_name(header.get('transport') or '', header.get('originPort') or '') or '盐田散货')[:31]
    book._Workbook__worksheets = [sheet]
    book._Workbook__worksheet_idx_from_name = {sheet.name: 0}
    book._Workbook__active_sheet = 0
    sheet.portrait = False
    sheet.paper_size_code = 9
    sheet.fit_num_pages = 1
    sheet.fit_width_to_pages = 1
    sheet.fit_height_to_pages = 1
    sheet.print_grid = False
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

    to_names = header.get('toNames') or list(TO_NAMES)
    write(0, 0, '发货商：华兴玩具制品（河源）有限公司')
    write(1, 0, '收货商：华登玩具制品有限公司')
    write(2, 0, 'TO:')
    write(2, 1, to_names[0] if to_names else '')
    render_port = str(header.get('originPort') or '盐田')
    render_short = '蛇' if '蛇' in render_port else '盐'
    render_vehicle = str(header.get('vehicle') or '').strip()
    display_name = f'{render_short}客上车{render_vehicle}车' if render_vehicle else str(header.get('tableName') or '')
    write(2, 13, display_name)
    write(3, 0, 'CC:')
    write(3, 1, str(header.get('cc') or 'PAT'))
    warehouse_no = str(header.get('warehouseNo') or '').strip()
    table_name = str(header.get('tableName') or '').strip()
    port_short = '蛇' if '蛇' in str(header.get('originPort') or '') else ('盐' if '盐' in str(header.get('originPort') or '') else '')
    tonnage = ''.join(ch for ch in str(header.get('truckType') or '3T') if ch.isdigit() or ch == '.') or '3'
    count = str(header.get('truckCount') or '1').strip() or '1'
    if warehouse_no:
        write(3, 4, f'入{port_short}港{warehouse_no}号仓 {count}只{tonnage}吨车如下：各')
    elif table_name.startswith('入') and '号仓' in table_name:
        write(3, 4, table_name)
    else:
        write(3, 4, f"{header.get('transport') or ''}{header.get('truckType') or '3T'}车如下:各")
    write(3, 13, f"成交方式:{header.get('tradeTerm') or 'FOB'}")
    write(4, 0, '收件日期：')
    try:
        day = date.fromisoformat(str(header.get('sheetDate') or '')[:10])
        write(4, 2, datetime(day.year, day.month, day.day), style=style_at(4, 2))
    except ValueError:
        write(4, 2, header.get('sheetDate') or '')

    for index in range(13):
        row = 6 + index
        if index >= len(lines):
            for col in range(18):
                write(row, col, '')
            continue
        line = lines[index]
        values = [index + 1, line.get('tradingHouse') or 'Buzzbee', line.get('contract') or '',
                  line.get('filingCode') or '', line.get('declareCode') or '', line.get('productName') or line.get('name') or '',
                  line.get('category') or '塑胶', line.get('quantity'), line.get('cartons'), None, None,
                  line.get('cbm'), line.get('so') or '', line.get('po') or '', line.get('totalCartons') or '',
                  line.get('grossPerCarton'), line.get('netPerCarton'), line.get('remark') or '']
        for col, value in enumerate(values):
            write(row, col, value)
        if line.get('grossPerCarton') not in (None, ''):
            write(row, 9, round(float(line.get('grossPerCarton')) * float(line.get('cartons') or 0), 3))
        else:
            write(row, 9, line.get('grossWeight'))
        if line.get('netPerCarton') not in (None, ''):
            write(row, 10, round(float(line.get('netPerCarton')) * float(line.get('cartons') or 0), 3))
        else:
            write(row, 10, line.get('netWeight'))

    write(11, 13, f"国家：{next((str(line.get('country') or '') for line in lines if line.get('country')), '')}")
    write(12, 13, str(header.get('consolidator') or ''))
    write(13, 13, str(header.get('scheduleText') or ''))
    write(14, 13, f"车牌：{header.get('plate') or ''}")
    write(15, 13, str(header.get('exceptionNote') or ''))
    write(17, 13, f"品牌：{header.get('brandNote') or ''}")
    for col in range(12, 19):
        write(19, col, '')
    write(19, 7, '合计')
    for col, key in ((8, 'cartons'), (9, 'grossWeight'), (10, 'netWeight'), (11, 'cbm')):
        write(19, col, totals.get(key) or 0, style_row=19, style_col=col)
    write(20, 0, f"截数期{_format_date(header.get('cutoff') or '')}")
    write(21, 0, f"制表人:{header.get('fromName') or FROM_NAME}")
    try:
        day = date.fromisoformat(str(header.get('sheetDate') or '')[:10])
        write(21, 13, f"日期：{day.year}/{day.month}/{day.day}")
    except ValueError:
        write(21, 13, f"日期：{header.get('sheetDate') or ''}")

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def render_bulk_xlsx(payload: dict) -> bytes:
    template = Path(__file__).resolve().parent.parent / 'templates' / 'truck_w15.xls'
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
