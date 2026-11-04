"""Synthetic contracts for BuzzBee's separate unified-review packaging code."""
from io import BytesIO
from copy import copy

import openpyxl
import pytest

from app.services import customer_order_buzzbee_color_box as boxes
from app.services import customer_order_huaxing_unified as mapping
from app.services import customer_order_unified as unified
from test_customer_order_huaxing_unified import data, template


CODE = "87654-04-28-TEST"
OTHER = "87654-05-28-TEST"


def review_order(book, number=4, so="SO-A", item="87654-1", customer="WMU", note=None):
    sheet = book["正单评审表"]
    for column, value in ((3, "CONTRACT-A"), (4, so), (6, customer), (7, item), (20, note)):
        sheet.cell(number, column).value = value


def item_order(book, number=4, so="SO-A", item="87654-1", customer="WMU", code=CODE, lane=0):
    sheet = book[mapping.BUZZBEE_SHEETS[lane]]
    for column, value in ((5, so), (7, customer), (8, item), (20, code)):
        sheet.cell(number, column).value = value


def snapshot(sheet):
    return {cell.coordinate: (cell.value, tuple(cell._style or [0] * 9))
            for row in sheet for cell in row if cell.value is not None or cell.has_style}


def roundtrip(book):
    buffer = BytesIO()
    book.save(buffer)
    return openpyxl.load_workbook(BytesIO(buffer.getvalue()))


def test_append_after_body_occupied_column_preserves_notes_and_all_original_cells():
    book = template()
    review = book["正单评审表"]
    review_order(book, so="", note=CODE)  # Actual historical layout has no SO.
    review["U15"] = '=IFERROR(VLOOKUP(A15,[1]Sheet1!A:B,2,FALSE),"")'
    # Compare saved representations: XLSX normalizes an empty literal to None.
    originals = {sheet.title: snapshot(sheet) for sheet in roundtrip(book)}
    column = boxes.prepare_review(book)
    assert column == 22 and review["V3"].value == "彩盒编号"
    assert review["V4"].value == CODE and review["T4"].value == CODE
    assert review["V15"].value is None
    reopened = roundtrip(book)
    for name, cells in originals.items():
        for coordinate, (value, style) in cells.items():
            assert reopened[name][coordinate].value == value
            assert tuple(reopened[name][coordinate]._style or [0] * 9) == style
    assert boxes.prepare_review(reopened) == column
    assert reopened["正单评审表"].max_column == column + 2
    assert [review.cell(3, column + i).value for i in range(3)] == ["彩盒编号", "系列", "备注"]


def test_unique_full_identity_can_supply_history_code_and_notes_need_no_cross_row_lookup():
    book = template()
    item_order(book)
    review_order(book, note="保留业务备注")
    review_order(book, number=5, so="", item="UNRELATED", note=OTHER)
    col = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, col).value == CODE
    assert book["正单评审表"].cell(5, col).value == OTHER
    assert book["正单评审表"]["T4"].value == "保留业务备注"


@pytest.mark.parametrize("changes", [
    {"so": "SOA"}, {"item": "87654"}, {"customer": "OTHER"},
])
def test_history_never_relaxes_reference_variant_or_customer(changes):
    book = template()
    item_order(book, **changes)
    review_order(book)
    col = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, col).value is None


@pytest.mark.parametrize("note", [
    "彩盒", f"请改为 {CODE}", f"{CODE}-{OTHER}", "=A1", f"{CODE}(r?)",
])
def test_unproven_or_formula_notes_do_not_become_codes(note):
    book = template()
    review_order(book, so="", note=note)
    col = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, col).value is None


@pytest.mark.parametrize("code", [f"{CODE}(r1)", f"{CODE}-HT", f"{CODE}-HT(r2)"])
def test_single_complete_code_keeps_all_suffixes_in_history_and_source_po(code):
    from app.services.customer_order_buzzbee import parse_po
    from test_customer_order_buzzbee import build_wmu_po

    book = template()
    review_order(book, so="", note=code)
    col = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, col).value == code
    po = openpyxl.load_workbook(BytesIO(build_wmu_po()))
    po["Packaging Box"]["B1"] = code
    buffer = BytesIO()
    po.save(buffer)
    parsed = parse_po("synthetic-po.xlsx", buffer.getvalue())
    assert len(parsed) == 7
    assert all(line.values["packaging"] == code for line in parsed)


@pytest.mark.parametrize("duplicate", [False, True])
def test_conflicting_note_or_multiple_item_matches_stay_empty(duplicate):
    book = template()
    item_order(book)
    review_order(book, note=OTHER if not duplicate else CODE)
    if duplicate:
        item_order(book, number=5, code=OTHER)
    col = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, col).value is None


@pytest.mark.parametrize("existing", [OTHER, '=""', " ", 0])
def test_existing_manual_or_formula_value_is_never_overwritten(existing):
    book = template()
    review_order(book, note=CODE)
    review = book["正单评审表"]
    review["W3"], review["W4"] = "彩盒编号", existing
    assert boxes.prepare_review(book) == 23
    assert review["W4"].value == existing and review.max_column == 25


def test_cancelled_and_shipped_sections_are_not_backfilled():
    book = template()
    review = book["正单评审表"]
    review_order(book, note=CODE)
    review["A5"] = "已走货订单"
    review_order(book, number=6, note=CODE)
    review_order(book, number=15, note=CODE)
    col = boxes.prepare_review(book)
    assert review.cell(4, col).value == CODE
    assert review.cell(6, col).value is None and review.cell(15, col).value is None


@pytest.mark.parametrize("layout", ["duplicate", "merged", "common"])
def test_invalid_existing_header_is_rejected_without_changing_workbook(layout):
    book = template()
    review = book["正单评审表"]
    review["U3"] = "彩盒编号"
    if layout == "duplicate":
        review["V3"] = " 彩盒编号 "
    elif layout == "merged":
        review.merge_cells("U3:V3")
    else:
        review["U3"], review["G3"] = None, "彩盒编号"
    original = snapshot(review)
    with pytest.raises(unified.CustomerOrderUnifiedError, match="彩盒编号"):
        boxes.prepare_review(book)
    assert snapshot(review) == original


def test_new_column_extends_existing_print_area_without_moving_titles():
    book = template()
    review = book["正单评审表"]
    review.print_area = "A1:T12"
    review.print_title_rows = "1:3"
    review.merge_cells("A1:T1")
    boxes.prepare_review(book)
    assert "$W$12" in review.print_area
    assert review.print_title_rows == "$1:$3"
    assert str(review.merged_cells) == "A1:T1"


@pytest.mark.parametrize("packaging", [CODE, f"{CODE}-HT(r2)", "", "普通彩盒"])
def test_new_rows_link_exact_item_lane_and_clear_any_inherited_formula(packaging):
    book = template()
    review = book["正单评审表"]
    review_order(book, note="原备注")
    review["U3"], review["U4"] = "彩盒编号", '="OLD-CODE"'
    lane = mapping.BUZZBEE_SHEETS[1]
    row = dict(id="new", reference_no="NEW-SO", contract_no="NEW-CONTRACT",
               product_no="87654-2", customer_name="WMU", quantity="12",
               units_per_carton="6", packaging=packaging, item_sheet_name=lane,
               issues=[], _huaxing_customer="buzzbee")
    mapping.export_rows(book, [row])
    ir = next(n for n in range(4, book[lane].max_row + 1) if book[lane].cell(n, 5).value == "NEW-SO")
    rr = next(n for n in range(4, review.max_row + 1) if review.cell(n, 4).value == "NEW-SO")
    assert review["U4"].value == '="OLD-CODE"'
    assert review.cell(rr, 21).value == (
        f'=IF(LEN(\'{lane}\'!T{ir})=0,"",\'{lane}\'!T{ir})'
        if packaging.startswith(CODE) else None
    )
    assert book["接单表"].max_column == 20
    assert book[lane].max_column == 30


def test_other_customers_do_not_add_buzzbee_header():
    book = template("dickie")
    mapping.export_rows(book, [dict(
        id="other", reference_no="OTHER", product_no="OTHER-ITEM", quantity="6",
        units_per_carton="6", item_sheet_name="ITEM表", issues=[], _huaxing_customer="dickie",
    )])
    assert not any(c.value == boxes.HEADER for c in book["正单评审表"][3])


@pytest.mark.parametrize("raw,expected", [
    (f"{CODE}（r1）", f"{CODE}(r1)"),
    (f"{CODE} ( r1 )", f"{CODE}(r1)"),
    (f"{CODE}-HT（R2）", f"{CODE}-HT(R2)"),
    (f"{CODE} (r1)、{OTHER}-PDQ", f"{CODE}(r1)、{OTHER}-PDQ"),
    (f"{CODE}-PDQ / {OTHER}-HT", f"{CODE}-PDQ、{OTHER}-HT"),
])
def test_revision_and_multiple_complete_codes_are_preserved(raw, expected):
    from app.services.customer_order_buzzbee import parse_po
    from test_customer_order_buzzbee import build_wmu_po

    book = template()
    review_order(book, so="", note=raw)
    column = boxes.prepare_review(book)
    assert book["正单评审表"].cell(4, column).value == expected
    po = openpyxl.load_workbook(BytesIO(build_wmu_po()))
    po["Packaging Box"]["B1"] = "USE ENGLISH PACKAGING REF#" + raw
    parsed = parse_po("ordinary-name.xlsx", data(po))
    assert all(line.values["packaging"] == expected for line in parsed)


@pytest.mark.parametrize("builder,cell", [("build_wmc_po", "A48"), ("build_tottus_po", "B40")])
def test_each_single_order_parser_preserves_fullwidth_revision(builder, cell):
    from app.services.customer_order_buzzbee import parse_po
    import test_customer_order_buzzbee as fixtures

    po = openpyxl.load_workbook(BytesIO(getattr(fixtures, builder)()))
    po.active[cell] = "USE ENGLISH PACKAGING REF#57520-05-25-EN（r1）"
    parsed = parse_po("no-customer-in-filename.xlsx", data(po))
    assert parsed[0].values["packaging"] == "57520-05-25-EN(r1)"
    assert parsed[0].lineage["packaging"].endswith("!" + cell)


def test_series_insertion_preserves_existing_notes_and_updates_all_references():
    from openpyxl.formatting.rule import FormulaRule
    from openpyxl.styles import Font, PatternFill
    from openpyxl.workbook.defined_name import DefinedName
    from openpyxl.worksheet.datavalidation import DataValidation

    book = template()
    review = book["正单评审表"]
    review_order(book, note="原来的业务备注")
    review["U3"], review["V3"] = "彩盒编号", "备注"
    review["V4"], review["V5"] = "已填写的尾部备注", '=""'
    review["V4"].font = Font(name="Arial", bold=True, color="123456")
    original_style = copy(review["V4"]._style)
    review["W15"] = "=V4"  # Blank W header, cancelled-section body formula.
    review["X15"] = '=IF(V4="V4",V5,\'接单表\'!V4)'
    review.merge_cells("V1:W1")
    review["V1"] = "用户合并标题"
    review.column_dimensions["V"].width = 38
    review.print_area = "A1:X16"
    review.auto_filter.ref = "A3:X12"
    review.auto_filter.add_filter_column(21, ["已填写的尾部备注"])
    review.auto_filter.add_sort_condition("V4:V12")
    validation = DataValidation(type="custom", formula1='LEN($V4)<50')
    validation.add("V4:V12")
    review.add_data_validation(validation)
    review.conditional_formatting.add("V4:V12", FormulaRule(formula=['$V4="确认"'], fill=PatternFill("solid", fgColor="FFFF00")))
    book["接单表"]["V4"] = "其他表本地值"
    book["接单表"]["V5"] = "='正单评审表'!$V$4"
    book["接单表"]["W5"] = "=V4"
    book.defined_names.add(DefinedName("ReviewNotes", attr_text="'正单评审表'!$V$4:$V$12"))
    boxes.prepare_review(book)
    result = roundtrip(book)
    review = result["正单评审表"]
    assert [review.cell(3, c).value for c in (21, 22, 23)] == ["彩盒编号", "系列", "备注"]
    assert review["T4"].value == "原来的业务备注"
    assert review["V4"].value is None
    assert review["W4"].value == "已填写的尾部备注"
    assert review["W4"]._style == original_style
    assert review["W5"].value == '=""'
    assert review["X15"].value == "=W4"
    assert review["Y15"].value == '=IF(W4="V4",W5,\'接单表\'!V4)'
    assert "W1:X1" in str(review.merged_cells)
    assert review["W1"].value == "用户合并标题"
    assert review.column_dimensions["W"].width == 38
    assert "$Y$16" in review.print_area
    assert review.auto_filter.ref == "A3:Y12"
    assert review.auto_filter.filterColumn[0].colId == 22
    assert review.auto_filter.sortState.ref == "A3:Y12"
    assert review.auto_filter.sortState.sortCondition[0].ref == "W4:W12"
    assert str(review.data_validations.dataValidation[0].sqref) == "W4:W12"
    assert review.data_validations.dataValidation[0].formula1 == "LEN($W4)<50"
    cf = next(iter(review.conditional_formatting))
    assert str(cf.sqref) == "W4:W12"
    assert review.conditional_formatting[cf][0].formula == ['$W4="确认"']
    assert result["接单表"]["V5"].value == "='正单评审表'!$W$4"
    assert result["接单表"]["W5"].value == "=V4"
    assert result.defined_names["ReviewNotes"].attr_text == "'正单评审表'!$W$4:$W$12"
    original = snapshot(review)
    boxes.prepare_review(result)
    assert snapshot(review) == original


def test_unsupported_dynamic_reference_is_rejected_before_column_movement():
    book = template()
    review = book["正单评审表"]
    review["U3"], review["V3"] = "彩盒编号", "备注"
    review["V4"] = '用户备注'
    book["接单表"]["V4"] = '=INDIRECT("正单评审表!V4")'
    before = snapshot(review)
    with pytest.raises(unified.CustomerOrderUnifiedError, match="INDIRECT"):
        boxes.prepare_review(book)
    assert snapshot(review) == before


def test_whole_table_to_right_moves_without_changing_relative_filter_ids():
    from openpyxl.worksheet.filters import AutoFilter
    from openpyxl.worksheet.table import Table

    book = template()
    review = book["正单评审表"]
    review["U3"], review["V3"] = "彩盒编号", "备注"
    review["X3"], review["Y3"] = "用户字段1", "用户字段2"
    review["X4"], review["Y4"] = "keep", "sort"
    table = Table(displayName="ManualTail", ref="X3:Y5", autoFilter=AutoFilter(ref="X3:Y5"))
    table.autoFilter.add_filter_column(0, ["keep"])
    table.autoFilter.add_sort_condition("Y4:Y5")
    review.add_table(table)
    boxes.prepare_review(book)
    review = roundtrip(book)["正单评审表"]
    table = review.tables["ManualTail"]
    assert table.ref == "Y3:Z5" and table.autoFilter.ref == "Y3:Z5"
    assert table.autoFilter.filterColumn[0].colId == 0
    assert table.autoFilter.sortState.sortCondition[0].ref == "Z4:Z5"
    assert review["Y4"].value == "keep" and review["Z4"].value == "sort"


def test_insert_updates_table_formula_metadata_and_visual_rule_thresholds():
    from openpyxl.formatting.rule import ColorScale, FormatObject, Rule
    from openpyxl.styles import Color
    from openpyxl.worksheet.table import Table, TableColumn, TableFormula

    book = template()
    review = book["正单评审表"]
    review["U3"], review["V3"] = "彩盒编号", "备注"
    review["V4"] = 7
    other = book.create_sheet("用户资料")
    other["A1"], other["A2"] = "引用备注", "='正单评审表'!$V$4"
    expression = "'正单评审表'!$V$4"
    table = Table(displayName="NotesLookup", ref="A1:A3", tableColumns=[TableColumn(
        id=1, name="引用备注", calculatedColumnFormula=TableFormula(attr_text=expression),
        totalsRowFormula=TableFormula(attr_text=expression),
    )])
    other.add_table(table)
    review.conditional_formatting.add("V4:V12", Rule(type="colorScale", colorScale=ColorScale(
        cfvo=[FormatObject(type="formula", val="$V$4"), FormatObject(type="max")],
        color=[Color("FF0000"), Color("00FF00")],
    )))
    boxes.prepare_review(book)
    result = roundtrip(book)
    column = result["用户资料"].tables["NotesLookup"].tableColumns[0]
    assert column.calculatedColumnFormula.attr_text == "'正单评审表'!$W$4"
    assert column.totalsRowFormula.attr_text == "'正单评审表'!$W$4"
    assert result["用户资料"]["A2"].value == "='正单评审表'!$W$4"
    review = result["正单评审表"]
    cf = next(iter(review.conditional_formatting))
    assert str(cf.sqref) == "W4:W12"
    assert review.conditional_formatting[cf][0].colorScale.cfvo[0].val == "$W$4"


@pytest.mark.parametrize("kind,expected", [("正单", "正式PO"), ("样板单", "样板单"), ("改单", "改单")])
def test_formal_po_is_only_an_export_display_name_and_series_notes_stay_manual(kind, expected):
    book = template()
    lane = mapping.BUZZBEE_SHEETS[1]
    review_order(book, note="旧备注")
    review = book["正单评审表"]
    review["U3"], review["V3"], review["W3"] = "彩盒编号", "系列", "备注"
    review["V4"], review["W4"] = '="旧系列"', '="旧备注"'
    row = dict(id="new", reference_no="NEW-SO", contract_no="NEW-CONTRACT",
               product_no="87654-2", customer_name="WMU", quantity="12", order_type=kind,
               units_per_carton="6", packaging=CODE, item_sheet_name=lane,
               issues=[], _huaxing_customer="buzzbee")
    mapping.export_rows(book, [row])
    ir = next(c.row for c in book[lane]._cells.values() if c.column == 5 and c.value == "NEW-SO")
    rr = next(c.row for c in review._cells.values() if c.column == 4 and c.value == "NEW-SO")
    assert row["order_type"] == kind
    assert book[lane].cell(ir, 2).value == expected
    assert review.cell(rr, 2).value == f'=IF(LEN(\'{lane}\'!B{ir})=0,"",\'{lane}\'!B{ir})'
    assert review.cell(rr, 22).value is None and review.cell(rr, 23).value is None
    assert review["V4"].value == '="旧系列"' and review["W4"].value == '="旧备注"'
