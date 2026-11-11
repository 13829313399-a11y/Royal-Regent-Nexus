import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.services.internal_quote import _rr2_cost_summary
from app.services.internal_quote_calculator import calculate_section
from app.services.internal_quote_excel import _build_summary_sheet
from app.services.internal_quote_history import _normalized_rows
from test_internal_quote_summary import SNAPSHOT, rows_by_key, section
from test_internal_quote_purchase_export import arithmetic_value

FACTORIES = ["huaxing", "huadeng", "huakang-a", "huakang-b", "huakang-c", "huakang-d"]


def make_quote(factory):
    return SimpleNamespace(product_name="税点验证", quote_no="TAX-CHECK", factory_id=factory,
                           customer="JustPlay" if factory == "huakang-b" else "普通客",
                           region_code="mainland", remark="")


def sales_payload(mode):
    return {"pricing_mode": "component" if mode == "component" else "standard",
            **({"pricing_components": [{"id": "part", "name": "配件1"}]} if mode == "component" else {}),
            "shipping": {"markup_x": 1.08, "misc_ratio": .03},
            "freight_calc": {"enabled": False, "freight_enabled": False, "lifting_enabled": False}}


@pytest.mark.parametrize("mode", ["ordinary", "detached", "component"])
def test_quick_paint_has_no_added_tax_in_summary_or_excel(mode):
    payload = {"quote_mode": "quick", "quick_quote": {
        "spray_labor_hkd": .48, "paint_hkd": .2, "paint_tax_rate_percent": 13,
        "pricing_component_id": "part", **({"markup_override": 1.1} if mode == "detached" else {})}}
    calc = calculate_section("painting", payload, SNAPSHOT, "REF")
    assert calc["status"] == "valid"
    assert calc["totals"]["total_hkd"] == "0.6800"
    assert calc["totals"]["paint_tax_hkd"] == "0.0000"
    assert not any(line["kind"] == "painting_quick_paint_tax" for line in calc["line_breakdown"])
    painting = section("painting", payload, calc["totals"], calc["line_breakdown"])
    sections = [painting, section("sales", sales_payload(mode), {})]
    context = {"factory_price_hkd": Decimal('.68'), "painting_hkd": Decimal('.68')}
    summary = _rr2_cost_summary(sections, context, SNAPSHOT, factory_id="huakang-b")
    assert summary["totals"]["total_deduction_hkd"] == "0.0230"  # .20 * 11.5%, once
    assert sum(Decimal(row["amount_hkd"]) for row in summary["shipping_pricing"]["pricing_entries"]) == Decimal('.68')
    workbook = Workbook()
    try:
        _build_summary_sheet(workbook, make_quote("huakang-b"), sections, SNAPSHOT, summary, context)
        for sheet in workbook:
            assert not any("油漆税金" in str(cell.value) for row in sheet for cell in row)
        sheet = workbook["报价明细"]
        for category, expected in (("油漆", .2), ("喷油工", .48)):
            details = [r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 2).value == category and sheet.cell(r, 3).value != "成本"]
            assert details
            assert sum(arithmetic_value(sheet, f"D{r}") for r in details) == pytest.approx(expected)
    finally:
        workbook.close()


@pytest.mark.parametrize("factory,mode", [(factory, mode) for factory in FACTORIES
    for mode in ("ordinary", "detached", "component") if mode != "component" or factory == "huakang-b"])
def test_sewing_material_and_hair_deductions_match_excel_without_slush_tax(factory, mode):
    meta = {"pricing_component_id": "part", **({"markup_override": 1.1} if mode == "detached" else {})}
    sections = [
        section("sales", sales_payload(mode), {}),
        section("sewing", {}, {"clothes_material_hkd": "15", "clothes_labor_hkd": "3", "clothes_hkd": "18", "hair_hkd": "0", "total_hkd": "18"}, [
            {**meta, "kind": "sewing_material", "category": "clothes", "group": "公仔", "item": "布料", "amount_hkd": "15"},
            {**meta, "kind": "sewing_labor", "category": "clothes", "group": "公仔", "item": "车衣人工", "amount_hkd": "3"}]),
        section("hair", {}, {"total_hkd": "6"}, [{**meta, "kind": "hair", "item": "头发", "amount_hkd": "6"}]),
        section("slush", {}, {"total_hkd": "8"}, [{**meta, "kind": "slush", "item": "软胶", "amount_hkd": "8"}]),
    ]
    context = {"factory_price_hkd": Decimal(32), "sewing_hkd": Decimal(18), "hair_hkd": Decimal(6), "slush_hkd": Decimal(8)}
    summary = _rr2_cost_summary(sections, context, SNAPSHOT, factory_id=factory)
    taxes = rows_by_key(summary["t4"])
    taxed = factory in {"huakang-c", "huakang-d"}
    assert summary["totals"]["total_deduction_hkd"] == ("2.4150" if taxed else "0.0000")
    assert taxes["slush3"]["deduction_hkd"] is None
    assert taxes["tax13b"]["amount_hkd"] == "0.0000"  # no second deduction via the generic 13% bucket
    workbook = Workbook()
    try:
        _build_summary_sheet(workbook, make_quote(factory), sections, SNAPSHOT, summary, context)
        sheet = workbook["报价明细"]
        header = next(cell.row for row in sheet for cell in row if cell.value == "人民币外购件成本")
        for col in (7, 8, 9):
            if taxed and col in (8, 9):
                assert sheet.cell(header + 1, col).value == pytest.approx(.115)
                expected = .69 if col == 8 else 1.725
                assert arithmetic_value(sheet, sheet.cell(header + 3, col).coordinate) == pytest.approx(expected)
            else:
                assert sheet.cell(header, col).value in (None, "")
                assert sheet.cell(header + 1, col).value in (None, "")
                assert sheet.cell(header + 3, col).value in (None, "")
        assert not any(cell.value == "搪胶类3%" for row in sheet for cell in row)
        slush_rows = [r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 2).value == "搪胶"]
        assert slush_rows
        assert all(sheet.cell(r, 1).value in (None, "") for r in slush_rows)
        assert sum(arithmetic_value(sheet, f"D{r}") for r in slush_rows) == pytest.approx(8)
    finally:
        workbook.close()


def test_reusing_quick_painting_in_mixed_history_does_not_add_tax():
    source = {"quote_mode": "quick", "quick_quote": {"spray_labor_hkd": 2, "paint_hkd": 3}}
    original = json.dumps(source)
    copied = _normalized_rows("painting", source, Decimal('.84'))
    calc = calculate_section("painting", copied, SNAPSHOT, "REF")
    assert calc["totals"]["total_hkd"] == "5.0000"
    assert calc["totals"]["paint_material_hkd"] == "3.0000"
    assert json.dumps(source) == original


@pytest.mark.parametrize("factory", FACTORIES)
def test_legacy_sales_tax_inputs_cannot_revive_excluded_tax(factory):
    payload = {**sales_payload("ordinary"), "tax_categories": [
        {"code": "slush", "amount_hkd": 100, "rate": .03},
        {"code": "sewing_clothes", "amount_hkd": 15, "rate": .115},
        {"code": "sewing_hair", "amount_hkd": 6, "rate": .115}]}
    calc = calculate_section("sales", payload, SNAPSHOT, "REF", context={"factory_id": factory})
    assert calc["totals"]["tax_deduction_hkd"] == ("2.4150" if factory in {"huakang-c", "huakang-d"} else "0.0000")
