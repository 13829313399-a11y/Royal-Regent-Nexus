from decimal import Decimal

import pytest
from openpyxl import Workbook

from app.services.internal_quote import _rr2_cost_summary
from app.services.internal_quote_excel import _build_summary_sheet
from test_internal_quote_factory_tax_rules import make_quote, sales_payload
from test_internal_quote_summary import SNAPSHOT, rows_by_key, section
from test_internal_quote_purchase_export import arithmetic_value


@pytest.mark.parametrize("mode", ["ordinary", "detached", "component"])
@pytest.mark.parametrize("quantity", [6, 12])
@pytest.mark.parametrize("carton_owner", ["sales", "engineering"])
def test_carton_cost_is_kept_once_without_generic_tax_tag(mode, quantity, carton_owner):
    carton_price = str(Decimal(".31040625") * 6 / quantity)
    # A carton with its own multiplier exercises the detached output path.
    carton = {"kind": "carton", "item": "测试外箱", "per_piece_hkd": carton_price,
              **({"markup_override": "1.1"} if mode == "detached" else {})}
    payload = {**sales_payload(mode), "cartons": [{"item": "测试外箱", "length_in": 9,
               "width_in": 4.75, "height_in": 15.75, "qty_per_carton": quantity}],
               "color_box_size_in": {"length": 8.25, "width": 4, "height": 14.75}, "paper_price_factor": 2.75}
    materials = [{"kind": "material", "item": "测试螺丝", "category": "hardware",
                  "amount_hkd": "2", "pricing_component_id": "part"}]
    if carton_owner == "sales":
        sections = [section("sales", payload, {"carton_hkd": carton_price}, [carton]),
                    section("engineering", {}, {"hardware_hkd": "2", "total_hkd": "2"}, materials)]
    else:
        # Legacy engineering-owned cartons use the same non-refundable rule.
        payload.pop("cartons")
        sections = [section("sales", payload, {}, []), section("engineering", {},
                    {"hardware_hkd": "2", "carton_hkd": carton_price, "total_hkd": str(Decimal(carton_price) + 2)},
                    [*materials, {**carton, "pricing_component_id": "part"}])]
    context = {"factory_price_hkd": Decimal(carton_price) + 2, "carton_hkd": Decimal(carton_price)}
    summary = _rr2_cost_summary(sections, context, SNAPSHOT, factory_id="huakang-b")
    assert summary["totals"]["total_deduction_hkd"] == "0.2300"
    workbook = Workbook()
    try:
        _build_summary_sheet(workbook, make_quote("huakang-b"), sections, SNAPSHOT, summary, context)
        sheet = workbook["报价明细"]
        # Management headers live outside column B, so these are visible detail rows.
        carton_rows = [r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 2).value == "纸箱"]
        assert carton_rows
        assert all(sheet.cell(r, 1).value in (None, "") for r in carton_rows)
        carton_entries = [e for e in summary["shipping_pricing"]["pricing_entries"] if e["kind"] == "carton"]
        assert sum(Decimal(e["amount_hkd"]) for e in carton_entries) == pytest.approx(Decimal(carton_price), abs=Decimal(".0001"))
        taxable_rows = [r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 1).value == "¥13%"]
        assert sum(arithmetic_value(sheet, f"D{r}") for r in taxable_rows) == pytest.approx(2)
    finally:
        workbook.close()


@pytest.mark.parametrize("paint_cost", ["0.2", "0.3"])
def test_management_material_labor_split_matches_export_definition(paint_cost):
    paint = Decimal(paint_cost)
    sections = [
        section("sales", {"shipping": {"markup_x": 1, "misc_ratio": 0}, "freight_calc": {"enabled": False}}, {}),
        section("engineering", {}, {"hardware_hkd": "1", "total_hkd": "1"}),
        section("molding", {}, {"injection_material_hkd": "1", "injection_imported_material_hkd": "1",
                "injection_domestic_material_hkd": "0", "injection_labor_hkd": "0.5", "total_hkd": "1.5"}),
        section("painting", {}, {"painting_labor_hkd": "0.48", "paint_material_hkd": paint_cost,
                "total_hkd": str(paint + Decimal(".48"))}),
        section("assembly", {}, {"assembly_hkd": "1", "total_hkd": "1"}),
    ]
    cost = Decimal("3.98") + paint
    result = _rr2_cost_summary(sections, {"factory_price_hkd": cost}, SNAPSHOT)
    t3 = rows_by_key(result["t3"])
    assert Decimal(t3["no_labor_cost"]["value"]) == Decimal("2") + paint
    # Injection, spray and assembly are labor; paint remains material.
    labor = Decimal(".5") + Decimal(".48") + Decimal("1")
    assert Decimal(t3["labor_ratio"]["value"]) == (labor / cost * 100).quantize(Decimal(".0001"))
    assert Decimal(t3["gross"]["value"]) == labor
    assert Decimal(t3["total_cost"]["value"]) == cost
    assert Decimal(t3["profit"]["value"]) == 0
    assert Decimal(result["totals"]["total_deduction_hkd"]) == (1 + paint) * Decimal(".115")
