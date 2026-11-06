"""Header-based Silverlit unified workbook adapter (including the 1031 layout)."""
from collections import defaultdict
from copy import copy

from openpyxl.formula.translate import Translator
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula


ITEM_FIELDS = (
    'received_date', 'order_type', 'production_no', 'contract_no', 'reference_no',
    'po_no', 'customer_name', 'product_no', 'product_name_zh', 'product_name_en',
    'quantity', 'units_per_carton', 'carton_count', 'standard', 'manual', 'label',
    'customer_label', 'carton_mark', 'fabric_label', 'packaging', 'date_code',
    'system_status', 'release_date', 'sample_date', 'inspection_date',
    'requested_ship_date', 'third_party_inspection', 'inspection_result',
)
ORDER_FIELDS = (
    'received_date', 'order_type', 'contract_no', 'reference_no', 'po_no',
    'customer_name', 'product_no', 'product_name_zh', 'product_name_en', 'quantity',
    'units_per_carton', 'carton_count', 'standard', 'unit_price_hkd', 'amount_hkd',
    'unit_price_usd', 'amount_usd', 'inspection_date', 'requested_ship_date',
)
DATE_FIELDS = {'received_date', 'release_date', 'sample_date', 'inspection_date', 'requested_ship_date'}


def columns(sheet):
    from . import customer_order_unified as u
    item = sheet.title == u.ITEM_SHEET
    fields = ITEM_FIELDS if item else ORDER_FIELDS
    headers = u.ITEM_HEADERS[:28] if item else u.ORDER_HEADERS[:19]
    found = defaultdict(list)
    for (number, column), cell in sheet._cells.items():
        if number == 3 and cell.data_type != 'f' and cell.value is not None:
            found[u._normalized_header(cell.value)].append(column)
    result = {}
    for field, header in zip(fields, headers, strict=True):
        matches = sorted(found[u._normalized_header(header)])
        if field == 'order_type' and sheet.title == u.ORDER_SHEET and not matches:
            # The supplied Silverlit 接单表 deliberately omits this column.
            continue
        if field == 'date_code' and len(matches) == 2:
            # The unified template also has a second, manual 日期码 after inspection.
            packaging = found[u._normalized_header('包装')]
            status = found[u._normalized_header('是否上系统')]
            if len(packaging) == len(status) == 1:
                matches = [c for c in matches if packaging[0] < c < status[0]]
        if len(matches) != 1:
            raise u.CustomerOrderUnifiedError(f'{sheet.title} 第3行“{header}”缺失或重复，请核对表头')
        result[field] = matches[0]
    for field, header in (('remarks', '备注'),):
        matches = found[u._normalized_header(header)]
        if len(matches) > 1:
            raise u.CustomerOrderUnifiedError(f'{sheet.title} 第3行“{header}”重复，请核对表头')
        if matches:
            result[field] = matches[0]
    return result


def validate(workbook):
    from . import customer_order_unified as u
    for name in u.SHEETS:
        if name not in workbook:
            raise u.CustomerOrderUnifiedError(f'银辉统一排期缺少工作表：{name}')
        columns(workbook[name])


def read_history(workbook):
    from . import customer_order_unified as u
    from .customer_order_regional import history_number
    from .customer_order_huaxing_unified import outer_pack
    sheet = workbook[u.ITEM_SHEET]
    cols = columns(sheet)
    fields = ('received_date', 'order_type', 'production_no', 'contract_no',
              'reference_no', 'po_no', 'customer_name', 'product_no',
              'product_name_zh', 'product_name_en', 'standard', 'packaging',
              'date_code', 'requested_ship_date')
    result = []
    for number in range(4, sheet.max_row + 1):
        def text(field):
            cell = sheet._cells.get((number, cols.get(field)))
            return u._text(cell.value) if cell is not None and cell.data_type != 'f' else ''
        values = {field: text(field) for field in fields}
        if not values['product_no'] or values['product_no'] == '产品编号' or '模拟数据' in text('remarks'):
            continue
        values['reference_no'] = values['reference_no'] or values['contract_no'] or values['po_no']
        values['quantity'] = history_number(sheet.cell(number, cols['quantity']), workbook, 'yinhui')
        values['units_per_carton'] = outer_pack(history_number(
            sheet.cell(number, cols['units_per_carton']), workbook, 'yinhui', pack=True))
        result.append(u.UnifiedHistoryRow(row=number, source_sheet=sheet.title,
                                         **values, extras={'remarks': text('remarks')}))
    return result


def _boundary(sheet, cols):
    from .customer_order_top_area import _label, _TOTALS, _SECTIONS
    from .customer_order_unified import CustomerOrderUnifiedError
    candidates = {}
    for cell in sheet._cells.values():
        if cell.row < 4:
            continue
        label = _label(cell)
        if cell.column <= 10 and label in _TOTALS:
            candidates[cell.row] = True
        elif cell.column <= 2 and label in _SECTIONS:
            candidates.setdefault(cell.row, False)
    for number, total in sorted(candidates.items()):
        keys = [sheet._cells.get((number, cols[field]))
                for field in ('contract_no', 'reference_no', 'po_no', 'product_no')]
        if any(c is not None and c.value not in (None, '') and c.data_type != 'f'
               and _label(c) not in _TOTALS | _SECTIONS for c in keys):
            continue
        return number, total
    raise CustomerOrderUnifiedError(f'{sheet.title} 未找到正单区的合计、取消或已走货边界，请核对模板')


def _copy_row(sheet, source_row, target_row):
    """Copy only meaningful table width, without expanding style-only XFD cells."""
    from .huakang_a_order_legacy.unified_schedule import copy_array_formula
    width = max(c.column for c in sheet._cells.values() if c.row == 3 and c.value is not None)
    manual = {c.column for c in sheet._cells.values() if c.row == 3 and
              str(c.value or '').strip() in {'放版日期', '抽版日期', '纸箱', '紙箱', '拆单来源', '拆單來源'}}
    row_style = copy(sheet.row_dimensions[source_row])
    row_style.index = target_row
    sheet.row_dimensions[target_row] = row_style
    for column in range(1, width + 1):
        source, target = sheet.cell(source_row, column), sheet.cell(target_row, column)
        reserved = target.value if target.data_type == 'f' else None
        target._style = copy(source._style)
        if reserved is not None:
            continue  # Existing reserved formula is user-owned, including manual columns.
        if column in manual:
            target.value = None
        elif isinstance(source.value, ArrayFormula):
            target.value = copy_array_formula(source.value, source.coordinate, target.coordinate)
        elif source.data_type == 'f':
            target.value = Translator(source.value, origin=source.coordinate).translate_formula(target.coordinate)
        else:
            target.value = None
        for validation in sheet.data_validations.dataValidation:
            if source.coordinate in validation.cells:
                validation.add(target.coordinate)


def _slots(workbook, sheet, cols, count):
    from .customer_order_top_area import insert_rows, _SUM
    footer, is_total = _boundary(sheet, cols)
    occupied = {c.row for c in sheet._cells.values() if 4 <= c.row < footer
                and ((c.value not in (None, '') and c.data_type != 'f')
                     or c.comment is not None or c.hyperlink is not None)}
    first = max(occupied, default=3) + 1
    available = list(range(first, footer))
    shortfall = max(0, count - len(available))
    if shortfall:
        insert_rows(workbook, sheet, footer, shortfall)
        available.extend(range(footer, footer + shortfall))
        footer += shortfall
    slots = available[:count]
    source = max((r for r in occupied if sheet.cell(r, cols['product_no']).value), default=4)
    for target in slots:
        if target != source:
            _copy_row(sheet, source, target)
    if is_total and slots:
        for cell in list(sheet._cells.values()):
            if cell.row != footer or cell.data_type != 'f' or not isinstance(cell.value, str):
                continue
            match = _SUM.fullmatch(cell.value)
            if match and all(match.group(k).replace('$', '').upper() == get_column_letter(cell.column)
                             for k in ('start', 'end')):
                if int(match['first']) < first and int(match['last']) < slots[-1] < footer:
                    cell.value = cell.value[:match.start('last')] + str(slots[-1]) + cell.value[match.end('last'):]
    return slots


def _put(sheet, number, column, value):
    from .customer_order_unified import _excel_value
    cell = sheet.cell(number, column)
    cell.value = _excel_value(value) if value not in ('', None) else None
    if isinstance(value, str):
        cell.data_type = 's'


def _write_item(sheet, number, row, cols):
    from . import customer_order_unified as u
    for field, col in cols.items():
        value = row.get(field)
        if field == 'inspection_date':
            value = row.get('customer_q') or row.get('line_q')
        if field == 'customer_name':
            value = value or row.get('customer_country')
        value = u._date_value(value) if field in DATE_FIELDS else (
            u._number(value) if field in {'quantity', 'units_per_carton', 'carton_count'} else u._text(value))
        _put(sheet, number, col, value)
    qty, pack = (get_column_letter(cols[f]) for f in ('quantity', 'units_per_carton'))
    sheet.cell(number, cols['carton_count']).value = (
        f'={qty}{number}/{pack}{number}' if u._number(row.get('units_per_carton')) not in (None, 0)
        and u._number(row.get('quantity')) is not None else None)
    for field in ('quantity', 'units_per_carton', 'carton_count'):
        sheet.cell(number, cols[field]).number_format = 'General'


def _write_summary(sheet, number, row, cols, item, item_row, item_cols):
    from . import customer_order_unified as u
    for field, col in cols.items():
        if field in {'contract_no', 'reference_no', 'po_no', 'customer_name', 'product_no'}:
            _put(sheet, number, col, u._text(row.get(field) or (row.get('customer_country') if field == 'customer_name' else '')))
        elif field in item_cols:
            ref = f"'{item.title}'!{get_column_letter(item_cols[field])}{item_row}"
            sheet.cell(number, col).value = f'=IF(LEN({ref})=0,"",{ref})'
    for field in ('unit_price_hkd', 'unit_price_usd'):
        _put(sheet, number, cols[field], u._number(row.get(field)))
    for price, amount in (('unit_price_hkd', 'amount_hkd'), ('unit_price_usd', 'amount_usd')):
        qty_col, price_col = get_column_letter(cols['quantity']), get_column_letter(cols[price])
        sheet.cell(number, cols[amount]).value = (
            f'=IF(OR(LEN({qty_col}{number})=0,LEN({price_col}{number})=0),"",'
            f'ROUND({qty_col}{number}*{price_col}{number},2))')


def export_rows(workbook, rows):
    from . import customer_order_unified as u
    from .customer_order_huaxing_unified import _mark_generated_row, DUPLICATE_CODES
    validate(workbook)
    if any(row.get('item_sheet_name') != u.ITEM_SHEET for row in rows):
        raise u.CustomerOrderUnifiedError('银辉订单未确定 ITEM 分类页，请重新预览')
    layouts = {name: columns(workbook[name]) for name in u.SHEETS}
    slots = {name: _slots(workbook, workbook[name], layouts[name], len(rows)) for name in u.SHEETS}
    item = workbook[u.ITEM_SHEET]
    for index, row in enumerate(rows):
        item_row = slots[item.title][index]
        _write_item(item, item_row, row, layouts[item.title])
        for name in (u.ORDER_SHEET, u.REVIEW_SHEET):
            _write_summary(workbook[name], slots[name][index], row, layouts[name],
                           item, item_row, layouts[item.title])
        duplicate = any(issue.get('code') in DUPLICATE_CODES | {'duplicate_order_warning'}
                        for issue in row.get('issues', []))
        for name in u.SHEETS:
            number = slots[name][index]
            _mark_generated_row(workbook[name], number, duplicate=duplicate,
                                last_column=max(layouts[name].values()))
            u._fit_generated_text(workbook[name], number)
