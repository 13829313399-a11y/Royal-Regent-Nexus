"""Dickie grouped ITEM details and appended summaries; never consumes MO stock."""
from collections import defaultdict
import re

from openpyxl.styles import PatternFill

# Explicit business-confirmed members only; never infer a family by truncation.
SERIES = {'203747029': '203747020', '203747020': '203747020'}
HISTORICAL_SECTIONS = {'取消单', '取消订单', '已走货', '已走货订单', '已完成', '已完成订单'}


def series_key(value):
    from app.services.customer_order_unified import _key
    product = _key(value)
    return SERIES.get(product, product)


def _columns(sheet):
    return (4, 7, 10) if sheet.title in ('接单表', '正单评审表') else (5, 8, 11)


def _stock(sheet, number):
    from app.services.customer_order_unified import _text
    from app.services.huaxing_order_legacy.edu_grouped_export import _green
    ref, product, quantity = _columns(sheet)
    kind = sheet.cell(number, 2)
    kind_text = _text(kind.value).upper() if kind.data_type != 'f' else ''
    reference = sheet.cell(number, ref)
    reference_text = _text(reference.value).upper() if reference.data_type != 'f' else ''
    return ('MO' in kind_text or '备料' in kind_text
            or reference_text in {'已入系统', '欠MO', '备料', '备料单'}
            or all(_green(sheet.cell(number, c)) for c in (ref, product, quantity)))


def active_boundary(sheet):
    """Normal new orders end before structural totals or historical sections."""
    from app.services.customer_order_unified import _text, CustomerOrderUnifiedError
    ref, product, _ = _columns(sheet)
    historical, totals = [], []
    summary = sheet.title in ('接单表', '正单评审表')
    for (row, column), cell in list(sheet._cells.items()):
        if row < 4 or cell.data_type == 'f' or not isinstance(cell.value, str):
            continue
        # A real order's fields/notes never become a section boundary merely
        # because they mention cancellation or shipment.
        if any(sheet.cell(row, c).data_type not in ('f', 'e')
               and sheet.cell(row, c).value not in (None, '') for c in (ref, product)):
            continue
        label = re.sub(r'\s+', '', _text(cell.value))
        if column <= 3 and label in HISTORICAL_SECTIONS:
            historical.append(row)
        elif summary and column == 10 and re.fullmatch(
                r'20\d{2}(?:[-–—/]20\d{2})?年接单(?:合计)?', label):
            totals.append(row)
    if not historical:
        raise CustomerOrderUnifiedError(f'{sheet.title} 未找到正常新单区与取消/已走货区的分界，请核对分区标题')
    return min(historical + totals)


def _placement(sheet, product_key=None):
    """A product key groups ITEM rows; summaries append after active content."""
    from app.services.customer_order_unified import _text
    _, product, _ = _columns(sheet)
    boundary = active_boundary(sheet)
    matches = [] if product_key is None else [r for r in range(4, boundary)
               if sheet.cell(r, product).data_type != 'f'
               and series_key(sheet.cell(r, product).value) == product_key]
    stock = [r for r in matches if _stock(sheet, r)]
    if matches:
        start = min(stock) if stock else max(matches) + 1
    else:
        # Summaries and genuinely new ITEM groups append at the active-area end.
        occupied = [r for r in range(4, boundary) if any(
            c.value not in (None, '') and c.data_type != 'f' for c in sheet[r])]
        start = max(occupied, default=3) + 1
    ordinary = [r for r in range(4, boundary)
                if _text(sheet.cell(r, product).value) and not _stock(sheet, r)
                and sheet.cell(r, product).data_type != 'f']
    same_item = [r for r in ordinary if series_key(sheet.cell(r, product).value) == product_key]
    choices = same_item or ordinary or matches or [max(4, start - 1)]
    source = min(choices, key=lambda r: abs(r - start))
    return start, sheet.cell(source, product)


def _local_sum_ranges(cell):
    """Only explicit same-column SUM ranges; never guess a named/dynamic total."""
    if cell.data_type != 'f' or not isinstance(cell.value, str):
        return []
    match = re.fullmatch(r'=SUM\(([^()]*)\)', re.sub(r'\s+', '', cell.value), re.I)
    if not match:
        return []
    from openpyxl.utils import column_index_from_string
    ranges = []
    for argument in match[1].split(','):
        part = re.fullmatch(r'\$?([A-Z]+)\$?(\d+):\$?([A-Z]+)\$?(\d+)', argument, re.I)
        if not part or any(column_index_from_string(part[i].upper()) != cell.column for i in (1, 3)):
            return []
        start, end = int(part[2]), int(part[4])
        if start < 4 or end < start:
            return []
        ranges.append((start, end))
    return ranges


def _summary_totals(sheet):
    """Capture the first active annual SUM block, excluding past-year blocks."""
    boundary = active_boundary(sheet)
    label = re.sub(r'\s+', '', str(sheet.cell(boundary, 10).value or ''))
    if not re.fullmatch(r'20\d{2}(?:[-–—/]20\d{2})?年接单(?:合计)?', label):
        return []
    ref, product, _ = _columns(sheet)
    orders = [r for r in range(4, boundary) if not _stock(sheet, r)
              and all(sheet.cell(r, c).value not in (None, '') and sheet.cell(r, c).data_type != 'f'
                      for c in (ref, product))]
    last_order = max(orders, default=0)
    totals = []
    for cell in sheet[boundary]:
        ranges = _local_sum_ranges(cell)
        if ranges and all(end < boundary for _, end in ranges) and any(start <= last_order <= end for start, end in ranges):
            totals.append(cell)
    return totals


def _include_appended_totals(totals, start, count):
    from openpyxl.utils import get_column_letter
    end = start + count - 1
    for cell in totals:
        # The insertion engine already expands adjacent ranges. A separated
        # range needs a new SUM argument, without including excluded MO/notes.
        ranges = _local_sum_ranges(cell)
        if ranges and not any(first <= start and end <= last for first, last in ranges):
            column = get_column_letter(cell.column)
            cell.value = f'{cell.value.rstrip()[:-1]},{column}{start}:{column}{end})'


def allocate_rows(workbook, rows):
    """Allocate each sheet independently; keep Cell handles across later inserts."""
    from app.services.customer_order_unified import _copy_template_row, CustomerOrderUnifiedError
    # Reuse the existing fully reference-aware insertion engine only. No EDU
    # numbering, matching, reservation selection or deduction code is called.
    from app.services.huaxing_order_legacy.edu_grouped_export import _insert, _green
    groups = defaultdict(list)
    for index, row in enumerate(rows):
        product = series_key(row.get('product_no'))
        if not product:
            raise CustomerOrderUnifiedError('Dickie 新单缺少完整货号，不能确定分组')
        groups[(row['item_sheet_name'], product)].append((index, row))
    handles = [dict() for _ in rows]
    allocations = [(lane, product, group) for (lane, product), group in groups.items()]
    if rows:
        # Both summaries retain input order even when ITEM grouping changes it
        # or the same batch spans different ITEM category sheets.
        allocations.extend((name, None, list(enumerate(rows))) for name in ('接单表', '正单评审表'))
    for name, product, group in allocations:
        sheet = workbook[name]
        start, source = _placement(sheet, product)
        totals = _summary_totals(sheet) if product is None else []
        _insert(workbook, sheet, start, len(group))
        _include_appended_totals(totals, start, len(group))
        ref_col, product_col, quantity_col = _columns(sheet)
        clear_stock_fill = all(_green(sheet.cell(source.row, c)) for c in (ref_col, product_col, quantity_col))
        for offset, (index, row) in enumerate(group):
            number = start + offset
            _copy_template_row(sheet, source.row, number)
            if clear_stock_fill:
                for cell in sheet[number]:
                    if _green(cell):
                        cell.fill = PatternFill()
            # Seed keys now; a later group can safely inspect allocated rows.
            sheet.cell(number, ref_col).value = row.get('reference_no')
            sheet.cell(number, product_col).value = row.get('product_no')
            handles[index][name] = sheet.cell(number, product_col)
    return handles
