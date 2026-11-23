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


def _key(value):
    return re.sub(r'\s+', '', str(value or '')).casefold()


def cancellation_matches(row, history, ignored_rows=()):
    """Resolve a complete historical SO without inventing a numbered split batch."""
    if not row.get('confirmation_no') or not row.get('source_line_no'):
        return []
    fields = ('contract_no', 'po_no', 'product_no')
    family = [old for old in history if all(_key(row.get(f)) and
        _key(row.get(f)) == _key(getattr(old, f)) for f in fields)
        and (_key(old.reference_no) == _key(row.get('confirmation_no'))
             or _key(old.reference_no).startswith(_key(row['confirmation_no']) + '-'))]
    pool = [old for old in family if old.row not in ignored_rows]
    exact = [old for old in pool if same_history(row, old)]
    bare = [old for old in pool if _key(old.reference_no) == _key(row['confirmation_no'])]
    # A bare SO is usable only when the whole family is one historical batch.
    if bare:
        if len(pool) != 1:
            return []
        candidate = dict(row, reference_no=bare[0].reference_no)
        return bare if same_history(candidate, bare[0]) else []
    return exact


def existing_rows(row, history):
    # A later original-PO retry must not revive a cancelled legacy bare SO.
    return cancellation_matches(row, history)


def describe_history(row, history, workbook=None):
    if row.get('document_kind') == 'cancellation':
        ignored = _proven_notices(workbook, row, history) if workbook is not None else []
        matches = cancellation_matches(row, history, ignored)
        safe = len(matches) == 1 and not is_shipped(matches[0])
        message = ('已匹配原订单；在原行标为取消单，保留原单资料，不新增订单。' if safe
                   else '未唯一匹配未走货原订单；仅保留提醒，不新增取消订单，也不改写原记录。')
        row['issues'].append({'severity': 'warning', 'code': 'jakks_cancellation', 'field': 'order_type',
                              'message': message, 'can_skip': False})
    elif existing_rows(row, history):
        for issue in row['issues']:
            if issue.get('code') == 'duplicate_existing_order':
                issue.update(severity='warning', can_skip=False, skip_key='',
                    message='排期已有相同批次、合同、PO、完整货号、数量及货期；保留原记录，不重复追加。')


def _summary_matches(workbook, old):
    from .customer_order_unified import _text
    result = {}
    for name in ('接单表', '正单评审表'):
        sheet = workbook[name]
        found = [r for r in range(4, sheet.max_row + 1)
            if all(_key(sheet.cell(r, c).value) == _key(getattr(old, field))
                for c, field in ((3,'contract_no'),(4,'reference_no'),(5,'po_no'),(7,'product_no')))]
        if len(found) == 1:
            result[name] = found[0]
    return result


def _clear_generated_notice(workbook, notice, warnings, original, expected, *, dry_run=False):
    """Retire only the old writer's proven three-sheet duplicate, without shifting rows."""
    from .customer_order_unified import _marker_row
    from openpyxl.formula.translate import Translator
    sheet = workbook['ITEM表']
    if notice.row <= _marker_row(sheet) or is_shipped(notice):
        return False
    summaries = _summary_matches(workbook, notice)
    if len(summaries) != 2:
        return False
    for name, r in summaries.items():
        s = workbook[name]
        if s.cell(r, 2).value != '取消单' or _key(s.cell(r, 6).value) != _key(expected.get('customer_name')):
            return False
        for col, source in ((1,'A'),(8,'I'),(9,'J'),(10,'K'),(11,'L'),(12,'M'),(13,'N'),(18,'Y'),(19,'Z'),(20,'AD')):
            ref = f"'ITEM表'!{source}{notice.row}"
            if s.cell(r, col).value != f'=IF(LEN({ref})=0,"",{ref})':
                return False
        if any(c.value is not None and c.column > 20 for c in s[r]):
            return False
    if sheet.cell(notice.row, 13).value != f'=K{notice.row}/L{notice.row}':
        return False
    if sheet.cell(notice.row, 29).value not in (None, '', f'=U{notice.row}'):
        return False
    allowed = {1,2,4,5,6,7,8,9,10,11,12,13,14,20,26,29}
    # New price links are the only populated extensions owned by the old writer.
    for c in sheet[notice.row]:
        if c.value is None or c.column in allowed:
            continue
        sources = [sheet.cell(original.row, c.column), sheet.cell(header_row(sheet) + 1, c.column)]
        copied_formula = False
        for source in sources:
            if c.data_type == source.data_type == 'f':
                try:
                    copied_formula |= Translator(source.value, origin=source.coordinate).translate_formula(c.coordinate) == c.value
                except (ValueError, TypeError):
                    pass
        if copied_formula:
            continue
        target = summaries['接单表']
        if not any(c.value == f'=IF(LEN(\'接单表\'!{column}{target})=0,"",\'接单表\'!{column}{target})'
                   for column in ('N','O','P','Q')):
            return False
    from .customer_order_unified import _text, _number
    # All populated business inputs must still equal the resolved original PO.
    for col, field in ((4,'contract_no'),(5,'reference_no'),(6,'po_no'),(7,'customer_name'),
            (8,'product_no'),(9,'product_name_zh'),(10,'product_name_en'),(11,'quantity'),
            (12,'units_per_carton'),(14,'standard'),(20,'packaging'),(26,'requested_ship_date')):
        actual, wanted = sheet.cell(notice.row,col).value, expected.get(field)
        if col in (11,12):
            equal = _number(actual) == _number(wanted)
        elif col == 26:
            equal = _text(actual)[:10] == _text(wanted)[:10]
        else:
            equal = _key(actual) == _key(wanted)
        if not equal:
            return False
    for name, r in summaries.items():
        for col, field in ((14,'unit_price_hkd'),(15,'amount_hkd'),(16,'unit_price_usd'),(17,'amount_usd')):
            if _number(workbook[name].cell(r,col).value) != _number(expected.get(field)):
                return False
    positions = [('ITEM表', notice.row), *summaries.items()]
    if any(c.comment or c.hyperlink for name, r in positions for c in workbook[name][r]):
        return False
    if dry_run:
        return True
    for name, r in positions:
        for c in workbook[name][r]:
            c.value = None
    warnings.append(f'{notice.reference_no}：已清理旧版重复生成的取消记录；原订单在原位取消，其他行位置不变。')
    return True



def _proven_notices(workbook, row, history):
    bare = [old for old in history if same_history(dict(row, reference_no=row.get('confirmation_no')), old)]
    if len(bare) != 1:
        return []
    return [old.row for old in history if '取消' in old.order_type and same_history(row, old)
        and _clear_generated_notice(workbook, old, [], bare[0], row, dry_run=True)]


def export_cancellations(workbook, rows, history, warnings, *, price_columns=None):
    from copy import copy
    from openpyxl.styles import PatternFill
    green = PatternFill('solid', fgColor='B7E1A1')
    def mark(sheet, rowno):
        # Summary formulas retain their live link to ITEM order type.
        if sheet.cell(rowno, 2).data_type != 'f':
            sheet.cell(rowno, 2).value = '取消单'
        for col in range(1, (28 if sheet.title == 'ITEM表' else 19) + 1):
            sheet.cell(rowno, col).fill = copy(green)
    plans = [(row, cancellation_matches(row, history, _proven_notices(workbook, row, history))) for row in rows]
    for row, matches in plans:
        if len(matches) != 1 or is_shipped(matches[0]):
            warnings.append(f'{row["reference_no"]}：未唯一匹配未走货原订单，取消未应用；未新增记录。')
            continue
        old = matches[0]
        claimed = {r.get('source_line_no') for r, m in plans if len(m) == 1 and m[0].row == old.row}
        summaries = _summary_matches(workbook, old)
        if len(claimed) > 1 or len(summaries) != 2:
            warnings.append(f'{row["reference_no"]}：批次或三表关联不唯一，取消未应用；未新增记录。')
            continue
        mark(workbook['ITEM表'], old.row)
        for name, r in summaries.items():
            mark(workbook[name], r)
        old.order_type = '取消单'
        warnings.append(f'{old.reference_no}：原订单已在原位标为取消单，未增加订单行或数量。')
        if _key(old.reference_no) == _key(row.get('confirmation_no')):
            for notice in list(history):
                if notice is not old and '取消' in notice.order_type and same_history(row, notice):
                    if _clear_generated_notice(workbook, notice, warnings, old, row):
                        history.remove(notice)
                    else:
                        warnings.append(f'{notice.reference_no}：旧取消记录含独立资料，已保留，请核对重复记录。')


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
