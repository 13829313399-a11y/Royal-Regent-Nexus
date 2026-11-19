"""Jakks source line identity and the supplied two-level ITEM header layout."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re


def header_row(sheet):
    if sheet.title != 'ITEM表':
        return 3
    from .customer_order_unified import ITEM_HEADERS, _normalized_header
    expected = tuple(_normalized_header(v) for v in ITEM_HEADERS[:28])
    for row, values in enumerate(sheet.iter_rows(min_row=3, max_row=4, max_col=28, values_only=True), start=3):
        if tuple(_normalized_header(value) for value in values) == expected:
            return row
    return 3


def same_history(row, old):
    """Only complete source identities and equal quantities/dates prove a repeat."""
    def key(v): return re.sub(r'\s+', '', str(v or '')).casefold()
    def number(v):
        try: return Decimal(str(v).replace(',', ''))
        except (InvalidOperation, ValueError): return None
    def day(v):
        if isinstance(v, (date, datetime)): return v.isoformat()[:10]
        return str(v or '').strip()[:10]
    return (all(key(row.get(field)) and key(row.get(field)) == key(getattr(old, field))
                for field in ('contract_no', 'po_no', 'product_no', 'reference_no'))
            and number(row.get('quantity')) is not None
            and number(row.get('quantity')) == number(old.quantity)
            and bool(day(row.get('requested_ship_date')))
            and day(row.get('requested_ship_date')) == day(old.requested_ship_date))


def existing_rows(row, history):
    if not row.get('confirmation_no') or not row.get('source_line_no'):
        return []
    return [old for old in history if same_history(row, old)]


def cancellation_matches(row, history):
    # Never infer a PDF Line# from an unnumbered legacy SO, even when one row
    # happens to have equal quantity/date: another batch can share those facts.
    return existing_rows(row, history)


def describe_history(row, history):
    if row.get('document_kind') == 'cancellation':
        matches = cancellation_matches(row, history)
        safe = len(matches) == 1 and not is_shipped(matches[0])
        message = ('已匹配原订单；生成排期时将订单类型标为取消单，数量作为原单证据保留。' if safe
                   else '未唯一匹配未走货订单；取消通知单独写入取消区，原订单及走货记录保持不变。')
        row['issues'].append({'severity': 'warning', 'code': 'jakks_cancellation', 'field': 'order_type',
                              'message': message, 'can_skip': False})
    elif existing_rows(row, history):
        for issue in row['issues']:
            if issue.get('code') == 'duplicate_existing_order':
                issue.update(severity='warning', can_skip=False, skip_key='',
                    message='排期已有相同批次、合同、PO、完整货号、数量及货期；生成时保留原记录，不重复追加。')


def export_cancellations(workbook, rows, history, warnings):
    from copy import copy
    from openpyxl.styles import PatternFill
    from .customer_order_unified import (_marker_row, _copy_template_row, _write_item_row,
        _write_summary_row, _text, _number, _excel_value)
    from .huakang_a_order_legacy.unified_schedule import _insert_rows
    green = PatternFill('solid', fgColor='B7E1A1')
    def mark(sheet, rowno):
        sheet.cell(rowno, 2).value = '取消单'
        # Retain formulas, monetary values, fonts, widths and user-owned columns.
        end = 28 if sheet.title == 'ITEM表' else 19
        for col in range(1, end + 1):
            sheet.cell(rowno, col).fill = copy(green)
    for row in rows:
        matches = cancellation_matches(row, history)
        # A repeated notice without Line# may only match an already archived
        # cancellation. It can never select an ordinary unnumbered order.
        if any('取消' in old.order_type and same_history(row, old) for old in history):
            continue
        summaries = {}
        if len(matches) == 1 and not is_shipped(matches[0]):
            old = matches[0]
            for name in ('接单表', '正单评审表'):
                sheet = workbook[name]
                found = [r for r in range(4, sheet.max_row + 1)
                    if all(_text(sheet.cell(r, c).value) == _text(getattr(old, field))
                           for c, field in ((3,'contract_no'),(4,'reference_no'),(5,'po_no'),(7,'product_no')))]
                if len(found) == 1:
                    summaries[name] = found[0]
            if len(summaries) == 2:
                mark(workbook['ITEM表'], old.row)
                for name, r in summaries.items(): mark(workbook[name], r)
                old.order_type = '取消单'
                continue
            warnings.append(f'{row["reference_no"]}：三表关联不唯一，原记录保持不变，通知另存取消区。')
        slots = {}
        for name in ('ITEM表', '接单表', '正单评审表'):
            sheet = workbook[name]
            start = _marker_row(sheet) + 1
            boundary = min((c.row for c in sheet._cells.values() if c.column == 1 and c.row >= start
                and _text(c.value) in {'已走货订单', '已走货', '取消单'}), default=sheet.max_row + 1)
            occupied = {c.row for c in sheet._cells.values() if start <= c.row < boundary
                        and c.value not in (None, '') and c.data_type != 'f'}
            target = max(occupied, default=start - 1) + 1
            if target >= boundary:
                _insert_rows(workbook, sheet, boundary, 1)
                if name == 'ITEM表':
                    for old in history:
                        if old.row >= boundary:
                            old.row += 1
            _copy_template_row(sheet, header_row(sheet) + 1, target)
            slots[name] = target
        _write_item_row(workbook['ITEM表'], slots['ITEM表'], row)
        for name in ('接单表', '正单评审表'):
            sheet = workbook[name]
            r = slots[name]
            _write_summary_row(sheet, r, row, item_row=slots['ITEM表'], item_sheet=workbook['ITEM表'])
            for col, field in ((14,'unit_price_hkd'),(15,'amount_hkd'),(16,'unit_price_usd'),(17,'amount_usd')):
                sheet.cell(r, col).value = _excel_value(_number(row.get(field)))
        for name, r in slots.items():
            mark(workbook[name], r)
        from .customer_order_unified import UnifiedHistoryRow
        history.append(UnifiedHistoryRow(row=slots['ITEM表'], order_type='取消单', **{
            k: _text(row.get(k)) for k in ('contract_no','reference_no','po_no','product_no','quantity','requested_ship_date')}))
        warnings.append(f'{row["reference_no"]}：取消通知已存入三表取消区；未改写未匹配或已走货的原订单。')


def is_shipped(old):
    return '已走货' in old.order_type or bool(old.extras.get('shipped_evidence'))


def shipped_evidence(sheet, row, header):
    from .customer_order_unified import _text
    markers = sorted(c.row for c in sheet._cells.values() if c.column == 1 and c.row <= row
                     and _text(c.value) in {'已走货订单', '已走货', '取消单'})
    if markers and '已走货' in _text(sheet.cell(markers[-1], 1).value):
        return '已走货分区'
    columns = [c.column for c in sheet._cells.values() if c.row == header
               and re.search(r'(?:实际.*(?:出货|走货|发货)|(?:出货|走货|发货)日期)', _text(c.value))]
    for col in columns:
        cell = sheet.cell(row, col)
        if cell.data_type != 'f' and cell.value not in (None, '', 0, '0'):
            return f'已填{sheet.cell(header, col).value}'
    return ''


def upgrade_supplements(workbook, rows, history, warnings):
    """A formal PO can fill a proven SUP row without adding its quantity again."""
    from .customer_order_unified import _text, _number, _excel_value
    for row in rows:
        if row.get('_jakks_supplementary') or row.get('document_kind') == 'cancellation':
            continue
        matches = existing_rows(row, history)
        if len(matches) != 1 or matches[0].order_type != '补充合同' or is_shipped(matches[0]):
            continue
        old = matches[0]
        summaries = {}
        for name in ('接单表', '正单评审表'):
            sheet = workbook[name]
            found = [r for r in range(4, sheet.max_row + 1)
                if all(_text(sheet.cell(r, c).value) == _text(getattr(old, field))
                       for c, field in ((3,'contract_no'),(4,'reference_no'),(5,'po_no'),(7,'product_no')))]
            if len(found) == 1:
                summaries[name] = found[0]
        if len(summaries) != 2:
            warnings.append(f'{row["reference_no"]}：正式合同已识别，原补充合同的三表关联不唯一，保留原表，请核对关联。')
            continue
        workbook['ITEM表'].cell(old.row, 2).value = '正式PO'
        for name, r in summaries.items():
            sheet = workbook[name]
            # Existing live links are retained; only literal order types change.
            if sheet.cell(r, 2).data_type != 'f':
                sheet.cell(r, 2).value = '正式PO'
            for col, field in ((14,'unit_price_hkd'),(15,'amount_hkd'),(16,'unit_price_usd'),(17,'amount_usd')):
                value = _number(row.get(field))
                if value is not None and sheet.cell(r, col).data_type != 'f':
                    sheet.cell(r, col).value = _excel_value(value)
        from .customer_order_huadeng_usd import write_prices
        write_prices(workbook,row,summaries['接单表'],summaries['正单评审表'],preserve_amount_formulas=True)
        warnings.append(f'{row["reference_no"]}：已在原位将补充合同转为正式PO并补齐原单价格，未重复增加数量。')
