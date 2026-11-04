"""Expose proven BuzzBee packaging references in the unified review sheet."""
from collections import defaultdict
from copy import copy
import re

from openpyxl.formula.tokenizer import Tokenizer
from openpyxl.utils import column_index_from_string, get_column_letter
from openpyxl.worksheet.cell_range import CellRange, MultiCellRange

from app.services.customer_order_buzzbee import packaging_references


HEADER = "彩盒编号"


def _literal(cell):
    return "" if cell.data_type == "f" or cell.value is None else str(cell.value).strip()


def _code(cell):
    return packaging_references(_literal(cell), codes_only=True)


def _insert_extension_column(workbook, sheet, start):
    """Insert a manual extension without leaving references at the old column.

    openpyxl's insert_cols does not maintain dependent formulas/ranges. Keep
    this narrow operation sparse and reject structures we cannot preserve.
    """
    from app.services.customer_order_unified import CustomerOrderUnifiedError

    def shift_range(reference):
        area = CellRange(str(reference))
        if area.max_col >= start:
            area.max_col += 1
            if area.min_col >= start:
                area.min_col += 1
        return str(area)

    def shift_reference(reference):
        pattern = r"(\$?)([A-Z]{1,3})(\$?\d+)?"
        if not re.fullmatch(pattern + r"(?::" + pattern + r")?", reference, re.I):
            return reference
        if ":" not in reference and not re.search(r"\d", reference):
            return reference  # An Excel name such as V is not a column range.
        def shifted(match):
            number = column_index_from_string(match.group(2).upper())
            return match.group(1) + get_column_letter(number + (number >= start)) + (match.group(3) or "")
        return re.sub(pattern, shifted, reference, flags=re.I)

    def shift_sort(state):
        if state is not None:
            if state.ref:
                state.ref = shift_range(state.ref)
            for condition in state.sortCondition:
                condition.ref = shift_range(condition.ref)

    def shift_filter(auto_filter):
        if auto_filter is None:
            return
        if auto_filter.ref:
            original = CellRange(auto_filter.ref)
            # colId is relative to the filter's first column. A filter moved
            # wholly right keeps its IDs; an inserted interior column shifts
            # only filters on the columns to its right.
            if original.min_col < start <= original.max_col:
                for column in auto_filter.filterColumn:
                    if original.min_col + column.colId >= start:
                        column.colId += 1
            auto_filter.ref = shift_range(auto_filter.ref)
        shift_sort(auto_filter.sortState)

    def formula(value, owner):
        leading = value.startswith("=")
        tokens = Tokenizer(value if leading else "=" + value)
        for token in tokens.items:
            if token.type == "FUNC" and token.subtype == "OPEN" and token.value.upper() == "INDIRECT(":
                raise CustomerOrderUnifiedError("BuzzBee 评审扩展列遇到 INDIRECT 动态引用，请先核对模板")
            if token.type != "OPERAND" or token.subtype != "RANGE":
                continue
            qualifier, separator, reference = token.value.rpartition("!")
            if separator:
                # External workbook and 3-D references cannot be safely retargeted.
                target = qualifier.strip("'").replace("''", "'")
                if "[" in target:
                    continue
                if ":" in target:
                    raise CustomerOrderUnifiedError("BuzzBee 评审扩展列遇到跨页范围公式，请先核对模板")
                if target != sheet.title:
                    continue
            elif owner != sheet.title:
                continue
            token.value = (qualifier + separator if separator else "") + shift_reference(reference)
        rendered = tokens.render()
        return rendered if leading else rendered[1:]

    updates = []
    for owner in workbook:
        if owner._charts or owner._images:
            raise CustomerOrderUnifiedError("BuzzBee 评审扩展列需移动现有列，但模板含图表或图片，请先核对模板")
        for cell in list(owner._cells.values()):
            if cell.data_type == "f":
                if not isinstance(cell.value, str):
                    raise CustomerOrderUnifiedError("BuzzBee 评审扩展列遇到数组公式，请先核对模板")
                updates.append((cell, "value", formula(cell.value, owner.title)))
        for rules in owner.conditional_formatting._cf_rules.values():
            for rule in rules:
                if rule.formula:
                    updates.append((rule, "formula", [formula(f, owner.title) for f in rule.formula]))
                for kind in ("colorScale", "dataBar", "iconSet"):
                    visual = getattr(rule, kind)
                    if visual is not None:
                        for threshold in visual.cfvo:
                            if threshold.type == "formula" and isinstance(threshold.val, str):
                                updates.append((threshold, "val", formula(threshold.val, owner.title)))
        for rule in owner.data_validations.dataValidation:
            for field in ("formula1", "formula2"):
                value = getattr(rule, field)
                if isinstance(value, str) and value:
                    updates.append((rule, field, formula(value, owner.title)))
        for name in owner.defined_names.values():
            if name.attr_text:
                updates.append((name, "attr_text", formula(name.attr_text, owner.title)))
        for table in owner.tables.values():
            for column in table.tableColumns:
                for field in ("calculatedColumnFormula", "totalsRowFormula"):
                    expression = getattr(column, field)
                    if expression is not None and expression.attr_text:
                        updates.append((expression, "attr_text", formula(expression.attr_text, owner.title)))
    for name in workbook.defined_names.values():
        if name.attr_text:
            updates.append((name, "attr_text", formula(name.attr_text, "")))
    for table in sheet.tables.values():
        area = CellRange(table.ref)
        if area.min_col < start <= area.max_col:
            raise CustomerOrderUnifiedError("BuzzBee 评审扩展列不能切开现有 Excel 表格，请先核对模板")

    # All unsupported structures and formula parse failures were checked above.
    for obj, field, value in updates:
        setattr(obj, field, value)
    for (number, column), cell in sorted(list(sheet._cells.items()), key=lambda entry: entry[0][1], reverse=True):
        if column >= start:
            del sheet._cells[number, column]
            cell.column = column + 1
            sheet._cells[number, column + 1] = cell
            if getattr(cell, "hyperlink", None):
                cell.hyperlink.ref = cell.coordinate
    for key, dimension in sorted(list(sheet.column_dimensions.items()), reverse=True,
                                 key=lambda entry: column_index_from_string(entry[0])):
        first = dimension.min or column_index_from_string(key)
        last = dimension.max or first
        if last >= start:
            del sheet.column_dimensions[key]
            dimension.min = first + (first >= start)
            dimension.max = last + 1
            dimension.index = get_column_letter(dimension.min)
            sheet.column_dimensions[dimension.index] = dimension
    merged = [shift_range(area) for area in sheet.merged_cells.ranges]
    sheet.merged_cells = MultiCellRange()
    for area in merged:
        sheet.merge_cells(area)
    for rule in sheet.data_validations.dataValidation:
        rule.sqref = MultiCellRange([shift_range(area) for area in rule.sqref.ranges])
    conditional = list(sheet.conditional_formatting._cf_rules.items())
    sheet.conditional_formatting._cf_rules.clear()
    for conditional_range, rules in conditional:
        conditional_range.sqref = MultiCellRange([shift_range(area) for area in conditional_range.sqref.ranges])
        sheet.conditional_formatting._cf_rules[conditional_range] = rules
    for table in sheet.tables.values():
        table.ref = shift_range(table.ref)
        shift_filter(table.autoFilter)
        shift_sort(table.sortState)
    shift_filter(sheet.auto_filter)
    if sheet.print_area:
        from openpyxl.worksheet.print_settings import PrintArea
        sheet.print_area = [shift_range(area) for area in PrintArea.from_string(sheet.print_area).ranges]
    if sheet.print_title_cols:
        sheet.print_title_cols = shift_reference(sheet.print_title_cols)
    if sheet.freeze_panes:
        sheet.freeze_panes = shift_reference(sheet.freeze_panes)
    for selection in sheet.sheet_view.selection:
        if selection.activeCell:
            selection.activeCell = shift_reference(selection.activeCell)
        if selection.sqref:
            selection.sqref = " ".join(shift_range(area) for area in selection.sqref.split())
    for page_break in sheet.col_breaks.brk:
        if page_break.id >= start:
            page_break.id += 1


def _review_tail(workbook, sheet, column):
    """Keep 彩盒编号/系列/备注 adjacent, retaining existing notes on insertion."""
    from app.services.customer_order_unified import CustomerOrderUnifiedError, _normalized_header
    series = [cell.column for cell in sheet[3] if _normalized_header(cell.value) == "系列"]
    if len(series) > 1 or (series and series[0] != column + 1):
        raise CustomerOrderUnifiedError("BuzzBee 的“系列”应位于“彩盒编号”后一列，请先核对表头")
    for offset, header in ((1, "系列"), (2, "备注")):
        destination = column + offset
        if _normalized_header(sheet.cell(3, destination).value) == header:
            if any(sheet.cell(3, destination).coordinate in area for area in sheet.merged_cells.ranges):
                raise CustomerOrderUnifiedError(f"BuzzBee 的“{header}”使用合并表头，请先核对模板")
            continue
        occupied = any(c >= destination and cell.value is not None
                       for (_, c), cell in sheet._cells.items())
        merged = any(area.max_col >= destination for area in sheet.merged_cells.ranges)
        if occupied or merged:
            _insert_extension_column(workbook, sheet, destination)
        cell = sheet.cell(3, destination, header)
        cell._style = copy(sheet.cell(3, column)._style)
        sheet.column_dimensions[get_column_letter(destination)].width = 22
    if sheet.print_area:
        from openpyxl.worksheet.print_settings import PrintArea
        areas = PrintArea.from_string(sheet.print_area)
        for area in areas.ranges:
            if area.min_col <= 20 <= area.max_col:
                area.max_col = max(area.max_col, column + 2)
        sheet.print_area = [str(area) for area in areas.ranges]


def _identity(sheet, number, columns):
    # Keep separators and product variants: SO-A and SOA are different orders.
    values = tuple(_literal(sheet.cell(number, column)).casefold() for column in columns)
    return values if all(values) else None


def _active_end(sheet):
    from app.services.customer_order_unified import _marker_row
    cancelled = _marker_row(sheet)
    shipped = [number for (number, _), cell in sheet._cells.items()
               if number >= 4 and "已走货" in _literal(cell)]
    return min([cancelled, *shipped])


def _write(sheet, number, column, value):
    cell = sheet.cell(number, column)
    if not cell.has_style:
        cell._style = copy(sheet.cell(number, 20)._style)
    cell.number_format = "@"
    cell.value = value


def _remember_styles(workbook):
    from app.services import customer_order_huaxing_unified as mapping
    from app.services.customer_order_top_area import boundary

    snapshots = {}
    names = (*mapping.item_sheets(workbook, "buzzbee"), "接单表", "正单评审表")
    for name in names:
        sheet = workbook[name]
        end, _ = boundary(sheet)
        item = name not in ("接单表", "正单评审表")
        product, contract, reference = (8, 4, 5) if item else (7, 3, 4)
        actual = [number for number in range(4, end)
                  if _literal(sheet.cell(number, product))
                  and (_literal(sheet.cell(number, reference)) or _literal(sheet.cell(number, contract)))]
        # A no-history template can still have deliberately styled blank rows.
        styled = sorted({number for (number, _), cell in sheet._cells.items()
                         if 4 <= number < end and cell.has_style})
        source = actual[-1] if actual else (styled[0] if styled else None)
        if source is not None:
            snapshots[name] = (
                {column: copy(cell._style) for (number, column), cell in sheet._cells.items() if number == source},
                sheet.row_dimensions[source].height,
            )
    # Snapshot once before a batch: later generated rows cannot become templates.
    workbook._buzzbee_style_templates = snapshots


def _restore_row_style(workbook, sheet, number):
    source = getattr(workbook, "_buzzbee_style_templates", {}).get(sheet.title)
    if source:
        styles, height = source
        for column, style in styles.items():
            if style is not None:
                sheet.cell(number, column)._style = copy(style)
        if height is not None:
            sheet.row_dimensions[number].height = height


def prepare_review(workbook):
    """Add/reuse the column and fill only proven, empty active-history cells."""
    from app.services import customer_order_huaxing_unified as mapping
    from app.services.customer_order_unified import CustomerOrderUnifiedError, _normalized_header

    review = workbook["正单评审表"]
    matches = [cell.column for cell in review[3] if _normalized_header(cell.value) == HEADER]
    if len(matches) > 1:
        raise CustomerOrderUnifiedError("正单评审表的“彩盒编号”列重复，请先核对表头")
    if matches:
        column = matches[0]
        if column <= 19 or any(review.cell(3, column).coordinate in area
                               for area in review.merged_cells.ranges):
            raise CustomerOrderUnifiedError("正单评审表的“彩盒编号”占用公共字段或合并表头，请先核对表头")
    else:
        # max_column includes body cells and merged ranges even with a blank
        # header; in real templates the blank U header has cancelled-row formulas.
        column = mapping._extension_column(review, HEADER, after=20)
        if review.print_area:
            from openpyxl.worksheet.print_settings import PrintArea
            areas = PrintArea.from_string(review.print_area)
            expanded = []
            for area in areas.ranges:
                if area.min_col <= 20 <= area.max_col:
                    area.max_col = max(area.max_col, column)
                expanded.append(str(area))
            review.print_area = expanded

    _review_tail(workbook, review, column)
    sources = defaultdict(list)
    for name in mapping.item_sheets(workbook, "buzzbee"):
        sheet = workbook[name]
        for number in range(4, _active_end(sheet)):
            key = _identity(sheet, number, (5, 8, 7))  # SO, full item, end customer
            if key:
                sources[key].append(_code(sheet.cell(number, 20)))
    # Original remarks (usually T) remain a source; the new trailing manual
    # remarks field must not make that previously unique source ambiguous.
    remarks = [cell.column for cell in review[3]
               if 19 < cell.column < column and _normalized_header(cell.value) == "备注"]
    for number in range(4, _active_end(review)):
        target = review.cell(number, column)
        # Formula cells (even formulas displaying "") and manual values are owned
        # by the user. Whitespace is also an existing value.
        if target.value not in (None, ""):
            continue
        if not (_literal(review.cell(number, 7)) and
                (_literal(review.cell(number, 4)) or _literal(review.cell(number, 3)))):
            continue
        key = _identity(review, number, (4, 7, 6))
        candidates = sources.get(key, [])
        note = _code(review.cell(number, remarks[0])) if len(remarks) == 1 else ""
        if len(candidates) > 1:
            continue
        item_code = candidates[0] if candidates else ""
        if item_code and note and item_code != note:
            continue
        value = item_code or note
        if value:
            _write(review, number, column, value)
    _remember_styles(workbook)
    return column


def write_new_row(workbook, column, review_row, item_sheet, item_row, *, order_row=None, row=None):
    """A newly generated order links to its exact ITEM row, never another PO."""
    from app.services.customer_order_unified import _fit_generated_text

    review = workbook["正单评审表"]
    targets = [(item_sheet, item_row), (review, review_row)]
    if order_row is not None:
        targets.append((workbook["接单表"], order_row))
    for sheet, number in targets:
        _restore_row_style(workbook, sheet, number)
    if row and row.get("order_type") == "正单":
        # Source/ledger vocabulary remains canonical; the user's schedule uses
        # 正式PO. Both summaries already link to this exact ITEM B cell.
        item_sheet.cell(item_row, 2).value = "正式PO"
    value = None
    if _code(item_sheet.cell(item_row, 20)):
        name = item_sheet.title.replace("'", "''")
        ref = f"'{name}'!T{item_row}"
        value = f'=IF(LEN({ref})=0,"",{ref})'
    _write(review, review_row, column, value)
    for extra in (column + 1, column + 2):
        _write(review, review_row, extra, None)
    # Restore the source's complete style, then grow only generated rows for
    # wrapped long text, including values behind exact-row summary formulas.
    for sheet, number in targets:
        linked = None
        if sheet is not item_sheet:
            linked = {2: item_sheet.cell(item_row, 2).value,
                      8: item_sheet.cell(item_row, 9).value,
                      9: item_sheet.cell(item_row, 10).value,
                      13: item_sheet.cell(item_row, 14).value,
                      column: item_sheet.cell(item_row, 20).value} if sheet is review else {
                      2: item_sheet.cell(item_row, 2).value,
                      8: item_sheet.cell(item_row, 9).value,
                      9: item_sheet.cell(item_row, 10).value,
                      13: item_sheet.cell(item_row, 14).value}
        _fit_generated_text(sheet, number, linked)
