"""Parse a standalone shipping-code mapping workbook."""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime

import openpyxl
import xlrd
from fastapi import HTTPException


def _text(value) -> str:
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if isinstance(value, (datetime, date)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value).strip()


def _number(value) -> float | None:
    try:
        return float(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _day(value) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = _text(value)
    if re.fullmatch(r'\d{5}(\.0)?', text):
        try:
            return xlrd.xldate.xldate_as_datetime(float(text), 0).date().isoformat()
        except (ValueError, OverflowError):
            pass
    match = re.search(r'(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})', text)
    if match:
        return f'{int(match.group(1)):04d}-{int(match.group(2)):02d}-{int(match.group(3)):02d}'
    return text[:10]


ALIASES = {
    'date': ('日期', '客出单日期', 'date'),
    'contract': ('合同号', '合同', 'contractno', 'contract'),
    'code': ('货号', '产品编号', '备案号', '备案货号', 'item', 'itemno', 'sku'),
    'name': ('货名', '产品中文名称', '产品名称', '品名', 'description'),
    'quantity': ('数量', '數量', 'qty', 'quantity'),
    'cartons': ('箱数', 'ctns', 'cartons'),
    'perCarton': ('每箱个数', '装箱', '装箱数', 'coefficient'),
    'category': ('玩具类别', '类别', 'category'),
    'note': ('备注', '备注（柜单）', 'remark'),
    'gross': ('每箱毛重', '毛重', 'gross'),
    'net': ('每箱净重', '净重', 'net'),
    'volume': ('体积', 'cbm'),
    'country': ('国家', '国家标准', 'country'),
    'customer': ('客户', 'customer'),
    'transport': ('运输公司', '运输', 'transport'),
    'mode': ('柜型/T车', '柜型/车', 'mode'),
    'trip': ('车次', 'trip'),
    'containerType': ('柜型', 'containerType'),
    'plate': ('车牌号', '车牌', 'plate'),
    'containerNo': ('柜号', 'containerNo'),
    'sealNo': ('封条号', 'sealNo'),
    'port': ('港口', '出港口', 'port'),
    'po': ('箱唛/P/O', '箱唛', 'PO', 'po'),
}


def _norm(value) -> str:
    return re.sub(r'[\s:：/\\_\-.#]', '', _text(value).lower())


def _header_map(row: list) -> dict[str, int]:
    normalized = [_norm(cell) for cell in row]
    result: dict[str, int] = {}
    for field, aliases in ALIASES.items():
        for index, header in enumerate(normalized):
            if any(header == _norm(alias) for alias in aliases):
                result[field] = index
                break
    return result


def _customer_and_mode(mode: str) -> tuple[str, str]:
    text = _text(mode)
    if not text:
        return '-', '-'
    match = re.match(r'(.+?)(?:出)?(?:盐田|蛇口|香港|大铲湾|惠州|南沙|前海|虎门|赤湾|上海)', text)
    customer = '-'
    if match:
        customer = match.group(1).replace('出', '').strip() or '-'
    remainder = text[len(customer):].lstrip('出').strip() if customer != '-' else text
    return customer, remainder or text


def _port(mode: str) -> str:
    for port in ('大铲湾', '前海', '虎门', '南沙', '惠州', '香港', '蛇口', '盐田', '赤湾', '上海'):
        if port in _text(mode):
            return port
    return '-'


def export_rows(rows: list[dict], label: str = '') -> dict:
    from app.services.shipping_exports import EXPORT_ROOT
    folder = EXPORT_ROOT / '货号映射'
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"货号映射_{label or datetime.now().strftime('%Y-%m-%d')}.csv"
    target = folder / filename
    headers = ['日期', '合同号', '货号', '货名', '每箱个数', '类别', '毛重', '净重', '体积', '客户', '港口', '来源', '状态']
    keys = ['date', 'contractNo', 'code', 'name', 'perCarton', 'category', 'gross', 'net', 'volume', 'customer', 'port', 'source', 'status']
    target.write_text('', encoding='utf-8-sig')
    with target.open('a', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(key, '') for key in keys])
    return {'path': str(target), 'filename': filename, 'count': len(rows)}


def parse_code_mapping_workbook(raw: bytes, filename: str) -> list[dict]:
    suffix = filename.lower().rsplit('.', 1)[-1]
    try:
        if suffix == 'xls':
            book = xlrd.open_workbook(file_contents=raw)
            current_year = str(datetime.now().year)
            sheet = next((item for item in book.sheets() if current_year in item.name and '出货' in item.name), None)
            if sheet is None:
                sheet = next((item for item in book.sheets() if '货号' in item.name or '出货' in item.name), book.sheet_by_index(0))
            rows = [[sheet.cell_value(r, c) for c in range(sheet.ncols)] for r in range(sheet.nrows)]
        elif suffix in ('xlsx', 'xlsm'):
            book = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            try:
                current_year = str(datetime.now().year)
                sheet = next((item for item in book.worksheets if current_year in item.title and '出货' in item.title), None)
                if sheet is None:
                    sheet = next((item for item in book.worksheets if '货号' in item.title or '出货' in item.title), book.worksheets[0])
                rows = [list(row) for row in sheet.iter_rows(values_only=True)]
            finally:
                book.close()
        else:
            raise HTTPException(422, '请上传 Excel 文件（.xlsx / .xls）')
    except HTTPException:
        raise
    except Exception as error:  # noqa: BLE001
        raise HTTPException(422, f'Excel 读取失败：{type(error).__name__}') from error

    columns: dict[str, int] = {}
    start = -1
    for index, row in enumerate(rows[:15]):
        found = _header_map(row)
        if 'code' in found and ('contract' in found or 'date' in found):
            columns = found
            start = index
            break
    if start < 0:
        raise HTTPException(422, '未找到货号/合同号表头')

    def value(row: list, field: str) -> str:
        index = columns.get(field)
        return _text(row[index]) if index is not None and index < len(row) else ''

    def num(row: list, field: str) -> float | None:
        index = columns.get(field)
        return _number(row[index]) if index is not None and index < len(row) else None

    result: list[dict] = []
    for row in rows[start + 1:]:
        code = value(row, 'code')
        if not code:
            continue
        mode = value(row, 'mode')
        customer = value(row, 'customer') or _customer_and_mode(mode)[0]
        if customer == '-':
            customer = _customer_and_mode(mode)[0]
        quantity = num(row, 'quantity')
        cartons = num(row, 'cartons')
        gross = num(row, 'gross')
        net = num(row, 'net')
        per_carton = num(row, 'perCarton')
        if per_carton is None and quantity and cartons:
            per_carton = quantity / cartons
        result.append({
            'date': _day(value(row, 'date')),
            'contractNo': value(row, 'contract'),
            'code': code,
            'name': value(row, 'name') or '-',
            'quantity': str(int(quantity)) if quantity is not None and quantity.is_integer() else (str(quantity) if quantity is not None else '-'),
            'cartons': str(int(cartons)) if cartons is not None and cartons.is_integer() else (str(cartons) if cartons is not None else '-'),
            'perCarton': f'{round(per_carton, 2)} 个' if per_carton else '-',
            'category': value(row, 'category') or '塑胶',
            'note': value(row, 'note') or '-',
            'gross': f'{gross / cartons:.3f}' if gross is not None and cartons else '-',
            'net': f'{net / cartons:.3f}' if net is not None and cartons else '-',
            'volume': f'{num(row, "volume"):.3f}' if num(row, 'volume') is not None else '-',
            'source': '导入',
            'country': value(row, 'country') or '-',
            'customer': customer,
            'transport': value(row, 'transport') or '-',
            'containerMode': '柜' if '柜' in mode else ('T车' if '车' in mode else '-'),
            'trip': value(row, 'trip') or '-',
            'containerType': value(row, 'containerType') or '-',
            'plate': value(row, 'plate') or '-',
            'containerNo': value(row, 'containerNo') or '-',
            'sealNo': value(row, 'sealNo') or '-',
            'port': value(row, 'port') or _port(mode),
            'mode': _customer_and_mode(mode)[1] or mode or '-',
            'po': value(row, 'po') or '-',
            'status': '已同步',
            'tone': 'blue',
        })
    return result
