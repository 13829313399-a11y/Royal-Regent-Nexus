"""SEASONS reservation/formal lanes in the user's three-sheet workbook.

Only explicit QF + product links consume an existing reservation. Reimporting
the same PO is a no-op; manual history, prices and inactive areas are retained.
"""
from copy import copy, deepcopy
from datetime import datetime
import re

from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.formula.translate import Translator
from openpyxl.styles import PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.formula import ArrayFormula

SHEETS = ('ITEM表', '接单表', '正单评审表')
INACTIVE = {'取消单', '取消订单', '已走货订单', '已走货'}


def text(value):
    return str(value or '').strip()


def columns(sheet):
    return (5, 6, 8, 11) if sheet.title == 'ITEM表' else (4, 5, 7, 10)


def markers(sheet):
    result = {}
    ref, po, product, _ = columns(sheet)
    for r in range(4, sheet.max_row + 1):
        if any(sheet.cell(r, c).data_type != 'f' and text(sheet.cell(r, c).value) for c in (ref, product)):
            continue
        label = text(sheet.cell(r, 1).value)
        if label in INACTIVE | {'预备单'}:
            result.setdefault(label, r)
    return result


def boundary(sheet):
    positions = markers(sheet)
    return min((r for key, r in positions.items() if key in INACTIVE), default=sheet.max_row + 1)


def entries(sheet, *, active=True):
    ref, po, product, qty = columns(sheet)
    end = boundary(sheet) if active else sheet.max_row + 1
    result = []
    for r in range(4, end):
        sku = text(sheet.cell(r, product).value).upper()
        po_value = text(sheet.cell(r, po).value).upper()
        reference = text(sheet.cell(r, ref).value).upper()
        if not sku or sheet.cell(r, product).data_type == 'f' or sku == '产品编号':
            continue
        qf = po_value if re.fullmatch(r'QF\d+(?:-\d+)?', po_value) else ''
        if not qf and re.fullmatch(r'QF\d+(?:-\d+)?', reference) and not po_value:
            qf = reference
        result.append(dict(cell=sheet.cell(r, product), po=po_value, ref=reference,
                           product=sku, qf=qf, quantity=sheet.cell(r, qty)))
    return result


def note(row, message):
    from .customer_order_unified import _issue
    row.setdefault('issues', []).append(_issue('warning', 'seasons_reservation', 'row', message))


def annotate(workbook, rows):
    """Expose existing-row and explicit-link behavior before generation."""
    existing = entries(workbook['ITEM表'], active=False)
    for row in rows:
        sku, po = text(row.get('product_no')).upper(), text(row.get('po_no')).upper()
        matches = [e for e in existing if e['product'] == sku and e['po'] == po and po]
        if matches:
            note(row, '当前排期已有此单及货号；相同单据不重复新增、不重复扣预备数量。差异保留提醒。')
        if row.get('order_type') == '正式PO' and not row.get('_seasons_explicit_qf'):
            note(row, '未从本产品原单识别到唯一 QF 号；可生成正式单，不猜测或扣减其他预备单。')
        if any(e['qf'] and e['ref'] != e['qf'] for e in matches):
            note(row, '排期 SO 与客户 QF 不一致；按本次原单及排期 P/O 号校正对应 SO，保留人工价格和其他资料。')


def _reserve_section(workbook, sheet):
    found = markers(sheet).get('预备单')
    if found:
        return found
    from .huaxing_order_legacy.edu_grouped_export import _insert
    start = boundary(sheet)
    _insert(workbook, sheet, start, 2)
    for c in range(1, sheet.max_column + 1):
        cell = sheet.cell(start, c)
        cell._style = copy(sheet.cell(start + 2, c)._style)
        cell.fill = PatternFill('solid', fgColor='FDE9E9')
    sheet.cell(start, 1, '预备单')
    return start


def _append(workbook, sheet, reservation=False, after=None, clone=True):
    from .customer_order_unified import _copy_template_row
    from .huaxing_order_legacy.edu_grouped_export import _insert
    reserve = _reserve_section(workbook, sheet)
    lo, hi = (reserve + 1, boundary(sheet)) if reservation else (4, reserve)
    candidates = [e['cell'] for e in entries(sheet) if lo <= e['cell'].row < hi]
    # Do not put a new row below the subtotal or consume a user's note-only row.
    totals = [r for r in range(lo, hi) if any(
        c.data_type != 'f' and re.fullmatch(r'(?:订单\+预备单总计|订单总计|合计|总计)[:：]?', text(c.value))
        for c in sheet[r])]
    end = min(totals, default=hi)
    occupied = [r for r in range(lo, end) if any(c.value not in (None, '') and c.data_type != 'f' for c in sheet[r])]
    start = after + 1 if after is not None else max(occupied, default=lo - 1) + 1
    source = candidates[-1] if candidates else next((e['cell'] for e in entries(sheet)), sheet.cell(4, 1))
    _insert(workbook, sheet, start, 1)
    if clone:
        _copy_template_row(sheet, source.row, start)
    return start


def _replace_single_reference(formula, formula_sheet, target, old, new):
    """Move explicit references; section SUM ranges intentionally stay in lane."""
    tokens = Tokenizer(formula).items
    for token in tokens:
        if token.type != 'OPERAND' or token.subtype != 'RANGE':
            continue
        match = re.fullmatch(r"(?:(?P<sheet>'(?:[^']|'')+'|[^!]+)!)?(?P<col>\$?[A-Z]{1,3})(?P<abs>\$?)(?P<row>\d+)(?::(?P<col2>\$?[A-Z]{1,3})(?P<abs2>\$?)(?P<row2>\d+))?", token.value)
        if not match:
            continue
        name = (match['sheet'] or formula_sheet).strip("'").replace("''", "'")
        if name == target and int(match['row']) == old and (not match['row2'] or int(match['row2']) == old):
            prefix = match['sheet'] + '!' if match['sheet'] else ''
            token.value = f"{prefix}{match['col']}{match['abs']}{new}"
            if match['row2']:
                token.value += f":{match['col2']}{match['abs2']}{new}"
    return '=' + ''.join(t.value for t in tokens)


def _move_to_formal(workbook, sheet, entry):
    old_cell = entry['cell']
    if old_cell.row < markers(sheet)['预备单']:
        return old_cell.row
    new = _append(workbook, sheet, clone=False)
    old = old_cell.row
    for source in list(sheet[old]):
        dest = sheet.cell(new, source.column)
        dest._style = copy(source._style)
        dest.comment = copy(source.comment)
        dest._hyperlink = copy(source.hyperlink)
        if dest._hyperlink is not None:
            dest._hyperlink.ref = dest.coordinate
        value = copy(source.value)
        if isinstance(value, ArrayFormula):
            value.ref = Translator('=' + value.ref, origin=source.coordinate).translate_formula(dest.coordinate)[1:]
        dest.value = value
        dest.data_type = source.data_type
        source.value = None
        source.comment = None
        source._hyperlink = None
    sheet.row_dimensions[new].height = sheet.row_dimensions[old].height
    for validation in sheet.data_validations.dataValidation:
        for area in list(validation.ranges.ranges):
            if area.min_row <= old <= area.max_row:
                validation.add(f'{get_column_letter(area.min_col)}{new}:{get_column_letter(area.max_col)}{new}')
    for conditional, rules in list(sheet.conditional_formatting._cf_rules.items()):
        for area in list(conditional.sqref.ranges):
            if area.min_row <= old <= area.max_row and not area.min_row <= new <= area.max_row:
                address = f'{get_column_letter(area.min_col)}{new}:{get_column_letter(area.max_col)}{new}'
                for rule in rules:
                    cloned = deepcopy(rule)
                    cloned.formula = [Translator('=' + value.lstrip('='), origin=f'{get_column_letter(area.min_col)}{area.min_row}').translate_formula(f'{get_column_letter(area.min_col)}{new}')[1:]
                                      if isinstance(value, str) and not value.isdigit() else value for value in (rule.formula or [])]
                    sheet.conditional_formatting.add(address, cloned)
    for ws in workbook:
        for cell in list(ws._cells.values()):
            if cell.data_type == 'f':
                if isinstance(cell.value, ArrayFormula):
                    cell.value.text = _replace_single_reference(cell.value.text, ws.title, sheet.title, old, new)
                else:
                    cell.value = _replace_single_reference(cell.value, ws.title, sheet.title, old, new)
        for validation in ws.data_validations.dataValidation:
            for attr in ('formula1', 'formula2'):
                formula = getattr(validation, attr)
                if isinstance(formula, str) and formula.startswith('='):
                    setattr(validation, attr, _replace_single_reference(formula, ws.title, sheet.title, old, new))
        for rules in ws.conditional_formatting._cf_rules.values():
            for rule in rules:
                rule.formula = [_replace_single_reference('=' + value.lstrip('='), ws.title, sheet.title, old, new)[1:]
                                if isinstance(value, str) else value for value in (rule.formula or [])]
        definitions = list(ws.defined_names.values()) + (list(workbook.defined_names.values()) if ws == sheet else [])
        for definition in definitions:
            formula = definition.attr_text
            if isinstance(formula, str):
                definition.attr_text = _replace_single_reference('=' + formula.lstrip('='), ws.title, sheet.title, old, new)[1:]
    entry['cell'] = sheet.cell(new, columns(sheet)[2])
    entry['quantity'] = sheet.cell(new, columns(sheet)[3])
    return new


def _fix_reference(workbook, row, match):
    qf = text(row.get('_seasons_qf')).upper()
    if not qf or match['qf'] != qf:
        return
    for name in SHEETS:
        sheet = workbook[name]
        matches = [e for e in entries(sheet) if e['qf'] == qf and e['product'] == match['product']]
        if len(matches) == 1:
            ref = columns(sheet)[0]
            sheet.cell(matches[0]['cell'].row, ref).value = qf
    match['ref'] = qf
    orders = [e for e in entries(workbook['接单表']) if e['qf'] == qf and e['product'] == match['product']]
    reviews = [e for e in entries(workbook['正单评审表']) if e['qf'] == qf and e['product'] == match['product']]
    if len(orders) == len(reviews) == 1:
        _link_template_price(workbook, orders[0]['cell'].row, reviews[0]['cell'].row)


def _link_template_price(workbook, order_row, review_row):
    cell = workbook['正单评审表'].cell(review_row, 14)
    formula = cell.value.text if isinstance(cell.value, ArrayFormula) else cell.value
    if cell.data_type == 'f' and isinstance(formula, str) and '接单表' in formula and re.search(r'!?\$?N\$?\d', formula):
        ref = f"'接单表'!N{order_row}"
        cell.value = f'=IF(LEN({ref})=0,"",{ref})'


def _prices(workbook, row, numbers):
    from .customer_order_unified import _number
    order = workbook['接单表']
    r = numbers['接单表']
    order.cell(r, 14).value = _number(row.get('unit_price_hkd'))
    for name in ('接单表', '正单评审表'):
        sheet, n = workbook[name], numbers[name]
        if name != '接单表':
            ref = f"'接单表'!N{r}"
            sheet.cell(n, 14).value = f'=IF(LEN({ref})=0,"",{ref})'
        sheet.cell(n, 15).value = f'=IF(OR(LEN(J{n})=0,LEN(N{n})=0),"",ROUND(J{n}*N{n},2))'
        sheet.cell(n, 16).value = f'=IF(OR(LEN(N{n})=0,NOT(ISNUMBER($P$1)),$P$1<=0),"",N{n}/$P$1)'
        sheet.cell(n, 17).value = f'=IF(OR(LEN(J{n})=0,LEN(P{n})=0),"",ROUND(J{n}*P{n},2))'


def _formal_same(workbook, row, match):
    from .customer_order_unified import _number, _date_value
    sheet, r = workbook['ITEM表'], match['cell'].row
    if _number(row.get('quantity')) is None or _number(match['quantity'].value) != _number(row.get('quantity')):
        return False
    for value, column in ((row.get('reference_no'), 5), (row.get('contract_no'), 4),
                          (row.get('_seasons_qf') if row.get('_seasons_explicit_qf') else '', 3)):
        existing = text(sheet.cell(r, column).value).upper()
        if existing and text(value) and existing != text(value).upper():
            return False
    def normalized_date(value):
        return value.date() if isinstance(value, datetime) else _date_value(value)
    old_date, new_date = normalized_date(sheet.cell(r, 26).value), normalized_date(row.get('requested_ship_date'))
    if old_date and new_date and old_date != new_date:
        return False
    prices = [e for e in entries(workbook['接单表']) if e['po'] == match['po'] and e['product'] == match['product']]
    if len(prices) == 1:
        old = _number(workbook['接单表'].cell(prices[0]['cell'].row, 14).value)
        new = _number(row.get('unit_price_hkd'))
        if old is not None and new is not None and old != new:
            return False
    return True


def _totals(workbook):
    for name in SHEETS[1:]:
        sheet = workbook[name]
        reserve, end = markers(sheet)['预备单'], boundary(sheet)
        for r in range(4, end):
            label = text(sheet.cell(r, 14).value)
            if re.fullmatch(r'(?:合计|总计)[:：]?', label):
                refs = [f'O{e["cell"].row}' for e in entries(sheet) if bool(e['qf']) == (r > reserve)]
                sheet.cell(r, 15).value = '=SUM(' + (','.join(refs) or '0') + ')'
            elif re.fullmatch(r'订单总计[:：]?', label):
                refs = [f'O{e["cell"].row}' for e in entries(sheet) if not e['qf']]
                sheet.cell(r, 15).value = '=SUM(' + (','.join(refs) or '0') + ')'
            elif re.fullmatch(r'订单\+预备单总计[:：]?', label):
                refs = [f'O{e["cell"].row}' for e in entries(sheet)]
                sheet.cell(r, 15).value = '=SUM(' + (','.join(refs) or '0') + ')'


def export_rows(workbook, rows):
    from .customer_order_unified import _number, _number_text, _write_item_row, _write_summary_row
    from .customer_order_huaxing_unified import write_extras, _mark_generated_row
    for name in SHEETS:
        _reserve_section(workbook, workbook[name])
    pending = []
    # Inspect the whole batch before mutating any reservation. File order must
    # not choose which of two differing versions gets to consume its quantity.
    groups = {}
    for row in rows:
        key = (text(row.get('po_no')).upper(), text(row.get('product_no')).upper())
        signature = tuple(text(row.get(k)) for k in (
            'quantity', 'reference_no', '_seasons_qf', 'requested_ship_date', 'unit_price_hkd'))
        groups.setdefault(key, set()).add(signature)
    ambiguous = {key for key, values in groups.items() if len(values) > 1}
    # QFs uploaded together with formal POs must exist before consuming them.
    ordered = sorted(rows, key=lambda row: row.get('order_type') != 'QF预备单')
    for row in ordered:
        sku, po = text(row.get('product_no')).upper(), text(row.get('po_no')).upper()
        if (po, sku) in ambiguous or row.get('_seasons_source_difference'):
            pending.append(row)
            note(row, '本批同单同货号存在不同版本；差异另列待补资料，不按文件顺序选择数量或扣减预备单。')
            continue
        is_qf = row.get('order_type') == 'QF预备单'
        all_existing = entries(workbook['ITEM表'], active=False)
        matches = [e for e in all_existing if e['product'] == sku and e['po'] == po and po]
        if matches:
            if len(matches) == 1 and matches[0]['cell'].row < boundary(workbook['ITEM表']):
                match = matches[0]
                if is_qf:
                    old, new = _number(match['quantity'].value), _number(row.get('quantity'))
                    if old is not None and new is not None and old != new:
                        pending.append(row)
                        note(row, '本次 QF 数量与排期中的现有数量不同；保留原余量，修订另列待补资料。')
                        continue
                    _fix_reference(workbook, row, match)
                    # Existing reservation quantities may already be consumed;
                    # never reset them from the original QF or replace prices.
                    for field, col in (('packaging', 20), ('product_name_en', 10), ('standard', 14)):
                        cell = workbook['ITEM表'].cell(match['cell'].row, col)
                        if not cell.value or (field == 'packaging' and text(cell.value).lower().startswith('packing')):
                            cell.value = row.get(field) or None
                    continue
                if _formal_same(workbook, row, match):
                    continue
            pending.append(row)
            note(row, '排期已有此单但数量/身份不同；原行和预备余量保留，差异另列待补资料。')
            continue
        qf = text(row.get('_seasons_qf')).upper()
        linked = [e for e in entries(workbook['ITEM表']) if e['qf'] == qf and e['product'] == sku]
        can_link = bool(po) and not is_qf and row.get('_seasons_explicit_qf') and len(linked) == 1 and (_number(row.get('quantity')) or 0) > 0
        paired = {}
        if can_link:
            for name in SHEETS:
                candidates = [e for e in entries(workbook[name]) if e['qf'] == qf and e['product'] == sku]
                if len(candidates) != 1:
                    can_link = False
                    break
                paired[name] = candidates[0]
            value = linked[0]['quantity'].value
            if not (isinstance(value, str) and value.startswith('=')) and _number(value) is None:
                can_link = False
            if isinstance(value, ArrayFormula):
                can_link = False
        if can_link:
            for name in SHEETS:
                _move_to_formal(workbook, workbook[name], paired[name])
        elif not is_qf:
            note(row, 'QF 关系或余量未能唯一确认，本次只新增正式单，不扣其他预备单。')
        numbers = {}
        for name in SHEETS:
            sheet = workbook[name]
            after = paired[name]['cell'].row if can_link else None
            n = _append(workbook, sheet, reservation=is_qf, after=after)
            numbers[name] = n
            if name == 'ITEM表':
                _write_item_row(sheet, n, row)
                write_extras(sheet, n, row)
            else:
                _write_summary_row(sheet, n, row, item_row=numbers['ITEM表'], item_sheet=workbook['ITEM表'])
            _mark_generated_row(sheet, n)
        _prices(workbook, row, numbers)
        if can_link:
            cell = paired['ITEM表']['quantity']
            expression = cell.value[1:] if isinstance(cell.value, str) else _number_text(_number(cell.value))
            cell.value = f'=({expression})-K{numbers["ITEM表"]}'
            # Exact links avoid key-based lookups going blank on a source typo.
            for name in SHEETS[1:]:
                r = paired[name]['cell'].row
                for c, ic in ((10, 11), (12, 13)):
                    ref = f"'ITEM表'!{get_column_letter(ic)}{cell.row}"
                    workbook[name].cell(r, c).value = f'=IF(LEN({ref})=0,"",{ref})'
            # Replace only the template's price lookup with the now-unique
            # paired order row. This also avoids WPS _xlfn.SINGLE price blanks.
            _link_template_price(workbook, paired['接单表']['cell'].row, paired['正单评审表']['cell'].row)
    _totals(workbook)
    if pending:
        # Differences are visible without counting competing versions as two
        # business orders or changing formal/reservation subtotals.
        from .customer_order_unified import ITEM_HEADERS
        name = 'ITEM待补资料'
        sheet = workbook[name] if name in workbook.sheetnames else workbook.create_sheet(name)
        for c, header in enumerate(ITEM_HEADERS, 1):
            sheet.cell(3, c, header)
        sheet.cell(3, 29, '资料提醒')
        for c, header in ((30, '本次原单单价HKD'), (31, '本次原单金额HKD'), (32, '来源文件'), (33, '本次关联QF')):
            sheet.cell(3, c, header)
        for row in pending:
            n = max(4, sheet.max_row + 1)
            _write_item_row(sheet, n, row)
            sheet.cell(n, 29, '同单存在不同记录；未覆盖原订单、未重复扣预备数量，也未计入三表合计。')
            sheet.cell(n, 30, _number(row.get('unit_price_hkd')))
            sheet.cell(n, 31, _number(row.get('amount_hkd')))
            sheet.cell(n, 32, text(row.get('source_file_name') or row.get('source_po_file_name'))).data_type = 's'
            sheet.cell(n, 33, text(row.get('_seasons_qf'))).data_type = 's'
