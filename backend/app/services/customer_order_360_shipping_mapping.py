"""Workbook-owned 360 shipping identifiers, separate from ledger/order identities."""
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

SHEET = '360出货货号映射'
HEADERS = ('SO#/Reference', '完整产品编号', '出货货号', '来源文件', '来源工作表', '来源行', '匹配说明')
MAX_ROWS = 10000
ERROR_VALUES = {'#REF!', '#N/A', '#DIV/0!', '#VALUE!', '#NAME?', '#NUM!', '#NULL!', '#SPILL!', '#CALC!'}


class ShippingMappingError(ValueError):
    pass


def text(value):
    if value is None or isinstance(value, bool):
        return ''
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value).strip()


def key(value):
    return re.sub(r'\s+', '', text(value)).upper()


def numeric_display_key(value):
    """For reference-file comparison only; never change stored full product IDs."""
    value = key(value)
    if re.fullmatch(r'[1-9][0-9]{6,10}(?:\.[0-9]+)?', value):
        return format(Decimal(value).normalize(), 'f')
    return value


def read_mapping(workbook):
    if SHEET not in workbook.sheetnames:
        return []
    sheet = workbook[SHEET]
    positions = {}
    for cell in list(sheet._cells.values()):
        if cell.row == 1 and cell.data_type != 'f' and key(cell.value) in {key(h) for h in HEADERS}:
            positions.setdefault(key(cell.value), []).append(cell.column)
    if any(len(positions.get(key(h), [])) != 1 for h in HEADERS[:3]):
        raise ShippingMappingError('360出货货号映射：前三个必要表头缺失或重复，请核对映射表。')
    cols = [positions[key(h)][0] for h in HEADERS[:3]]
    rows = sorted({c.row for c in sheet._cells.values()
                   if c.row > 1 and c.column in cols and c.value not in (None, '')})
    if len(rows) > MAX_ROWS:
        raise ShippingMappingError('360出货货号映射超过10000条，请先整理映射表。')
    result = []
    for row in rows:
        cells = [sheet.cell(row, col) for col in cols]
        if any(c.data_type in ('f', 'e') or key(c.value) in ERROR_VALUES for c in cells):
            raise ShippingMappingError(f'360出货货号映射第{row}行含公式或Excel错误，请使用已核对的文本值。')
        reference, product, shipping = [text(c.value) for c in cells]
        if not product or not shipping:
            raise ShippingMappingError(f'360出货货号映射第{row}行缺少完整产品编号或出货货号，请先核对。')
        if max(map(len, (reference, product, shipping))) > 500:
            raise ShippingMappingError(f'360出货货号映射第{row}行内容过长。')
        result.append(dict(row=row, source_sheet=SHEET, reference_no=reference, product_no=product,
                           extras={'shipping_item': shipping}))
    return result


def read_mapping_from_content(content):
    from . import customer_order_unified as unified
    workbook = unified._load_workbook(content)
    try:
        return read_mapping(workbook)
    except ShippingMappingError as exc:
        raise unified.CustomerOrderUnifiedError(str(exc)) from exc
    finally:
        workbook.close()


def records_as_history(records):
    return [dict(row=r['row'],source_sheet=f"{r['file']} · {r['sheet']}",
                 reference_no=r['reference'],product_no=r['product'],extras={'shipping_item':r['shipping']})
            for r in records]


def reference_records(content, file_name):
    """Read bounded columns only: native files have distant formatting-only XFD cells."""
    with ZipFile(BytesIO(content)) as archive:
        if sum(e.file_size for e in archive.infolist()) > 200 * 1024**2:
            raise ShippingMappingError('原排期解压后超过200MB，未创建映射。')
    book = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=False)
    records, seen = [], set()
    try:
        if '360客排期表' not in book.sheetnames:
            raise ShippingMappingError('原排期缺少360客排期表，未按其他客户文件猜测映射。')
        # The supplied 取消单 sheet has no shipping-item field and a different
        # layout; never read its F/G version/quantity cells as shipping evidence.
        for name in ('360客排期表', '已完成'):
            if name not in book.sheetnames:
                continue
            sheet = book[name]
            if sheet.max_row is None or sheet.max_row > MAX_ROWS + 3:
                raise ShippingMappingError(f'原排期{name}的行范围未确认或超过10000行，未截断处理。')
            header = next(sheet.iter_rows(min_row=3, max_row=3, max_col=7, values_only=True))
            if key(header[4]) != '正单合同号' or key(header[5]) != '产品货号' or key(header[6]) != '出货货号':
                raise ShippingMappingError(f'原排期{name}的产品货号/出货货号表头不一致，未猜测列。')
            for row, cells in enumerate(sheet.iter_rows(min_row=4, max_row=sheet.max_row, max_col=7), 4):
                if any(c.data_type == 'e' or key(c.value) in ERROR_VALUES for c in cells[4:7]):
                    raise ShippingMappingError(f'原排期{name}第{row}行身份或出货货号存在Excel错误，未创建映射。')
                if any(c.data_type == 'f' for c in cells[4:7]):
                    continue
                reference, product, shipping = [text(c.value) for c in cells[4:7]]
                if (not re.fullmatch(r'RL-\d{6}-\d+(?:-\d+)?', key(reference))
                        or not re.fullmatch(r'\d{7}|\d{10,11}(?:\.\d+)?', key(product))
                        or not shipping or key(shipping) in {'TBA', 'TBD', 'N/A', '待定', '待提供'}):
                    continue
                identity = (key(reference), key(product), shipping)
                if identity not in seen:
                    seen.add(identity)
                    records.append(dict(reference=reference, product=product, shipping=shipping,
                        file=Path(file_name).name, sheet=name, row=row, note='原排期出货货号'))
        if len(records) > MAX_ROWS:
            raise ShippingMappingError('原排期有效映射超过10000条，请拆分后处理。')
    finally:
        book.close()
    return records


def embed_reference_mapping(workbook, records):
    """Create an explicit, visible map once; never replace an existing/manual map."""
    if SHEET in workbook.sheetnames:
        raise ShippingMappingError('统一排期已有360出货货号映射，不能未经核对覆盖。')
    if not records or len(records) > MAX_ROWS:
        raise ShippingMappingError('原排期没有有效映射或超出数量限制。')
    if any(not text(r.get('product')) or not text(r.get('shipping'))
           or any(key(r.get(k)) in ERROR_VALUES for k in ('reference', 'product', 'shipping')) for r in records):
        raise ShippingMappingError('映射含缺失身份/出货货号或Excel错误，未创建映射表。')
    # Numeric Excel storage can drop decimal display zeroes (.30 becomes .3).
    # Add aliases only for observed current full IDs with unique numeric-equivalent
    # reference evidence; original ITEM H and ledger matching remain untouched.
    indexed = {}
    for record in records:
        indexed.setdefault((key(record['reference']), numeric_display_key(record['product'])), []).append(record)
    aliases, seen = [], {(key(r['reference']), key(r['product']), r['shipping']) for r in records}
    sheet = workbook['ITEM表']
    from .customer_order_360_shipping_item import _order_identity
    row_numbers = sorted({c.row for c in sheet._cells.values() if c.row >= 4 and c.column == 8 and c.value not in (None, '')})
    for row in row_numbers:
        if any('模拟数据' in str(c.value or '') for (r, _), c in sheet._cells.items() if r == row):
            continue
        ref, product = _order_identity(sheet, row)
        candidates = indexed.get((key(ref), numeric_display_key(product)), [])
        if len({r['shipping'] for r in candidates}) != 1:
            continue
        original = candidates[0]
        identity = (key(ref), key(product), original['shipping'])
        if identity not in seen:
            seen.add(identity)
            aliases.append(dict(original, reference=ref, product=product,
                                note=f"仅兼容小数末尾零显示；原产品货号 {original['product']}"))
    records = [*records, *aliases]
    if len(records) > MAX_ROWS:
        raise ShippingMappingError('含显示别名的映射超过10000条。')
    result = workbook.create_sheet(SHEET)
    result.append(HEADERS)
    for record in records:
        result.append([record[k] for k in ('reference', 'product', 'shipping', 'file', 'sheet', 'row', 'note')])
    for cells in result:
        for cell in cells:
            if isinstance(cell.value, str):
                cell.data_type = 's'
                cell.number_format = '@'
            cell.alignment = Alignment(vertical='center', wrap_text=True)
    for cell in result[1]:
        cell.font = Font(name='Arial', bold=True, color='FFFFFF', size=10)
        cell.fill = PatternFill('solid', fgColor='234970')
    for column, width in zip('ABCDEFG', (24, 24, 28, 42, 22, 12, 64)):
        result.column_dimensions[column].width = width
    result.row_dimensions[1].height = 28
    result.freeze_panes = 'C2'
    result.auto_filter.ref = result.dimensions
    return dict(rows=len(records), aliases=len(aliases), sheet=SHEET)
