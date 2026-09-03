from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace

import pytest
from openpyxl import Workbook, load_workbook

from app.services.internal_quote import _rr2_cost_summary
from app.services.internal_quote_calculator import calculate_section
from app.services.internal_quote_excel import (
    _build_summary_sheet,
    _justplay_electronic_category,
    _justplay_electronic_source_parts,
)
from app.services.internal_quote_import import parse_internal_quote_workbook
from test_internal_quote_excel_formula_links import _find_row, _section
from test_internal_quote_import import workbook_bytes


def _electronic_export_fixture(component_mode=True, inline_battery=False):
    snapshot = {"fx": {"rmb_hkd": ".85", "hkd_usd": "7.8", "rmb_usd": "6.63"},
                "markup": "1.2", "settlement": ".97"}
    imported = parse_internal_quote_workbook(workbook_bytes([
        ["零件名称", "规格", "用量", "单价RMB", "备注"],
        ["IC", "A1", 2, .85],
        ["", "A2", 1, .425],
        ["LED", "红光", 3, .085],
        ["喇叭", "27mm", 1, .255],
        ["PCB", "主板", 1, .85],
        ["电阻", "10K", 1, .085],
        ["邦定成本", .17],
        ["人工成本", .255],
        ["10%利润"],
    ]), "electronic", rmb_hkd=Decimal(".85"))
    payload = imported.payload_fragment
    for row in payload["components"]:
        row["pricing_component_id"] = "a"
    payload["components"].extend([
        {"item": name, "specification": spec, "quantity": 1, "unit_price_rmb": unit,
         "pricing_component_id": "b"}
        for name, spec, unit in [("IC", "B1", .85), ("LED", "蓝光", .17),
                                 ("Speaker", "20mm", .425), ("PCB", "副板", 1.7)]
    ])
    if inline_battery:
        payload["components"].append({"item": "电池", "specification": "旧电子表电池", "quantity": 1,
                                      "unit_price_rmb": .34, "pricing_component_id": "a"})
    electronic = calculate_section("electronic", payload, snapshot, "ELECTRONIC-EXPORT")
    materials = [
        {"item": "AG13电池×3", "category": "auxiliary", "auxiliary_category": "电池",
         "quantity": 3, "unit_price_rmb": .17, "pricing_component_id": "a"},
        {"item": "LR44电池×2", "category": "auxiliary", "auxiliary_category": "电池",
         "quantity": 2, "unit_price_rmb": .255, "pricing_component_id": "b"},
        {"item": "电池片", "category": "hardware", "quantity": 1,
         "unit_price_rmb": .085, "pricing_component_id": "a"},
    ]
    engineering = calculate_section("engineering", {"materials": materials}, snapshot, "ELECTRONIC-EXPORT")
    components = [{"id": "a", "name": "电话", "markup_x": "1.16"},
                  {"id": "b", "name": "镜子", "markup_x": "1.25"}]
    sales = {"pricing_mode": "component", "pricing_components": components} if component_mode else {}
    sections = [_section("electronic", payload=payload, calculation=electronic),
                _section("engineering", payload={"materials": materials}, calculation=engineering),
                _section("sales", payload=sales)]
    for section in sections:
        section.is_required = True
    context = {"electronic_hkd": Decimal(electronic["totals"]["total_hkd"]),
               "auxiliary_hkd": Decimal(engineering["totals"]["auxiliary_hkd"]),
               "hardware_hkd": Decimal(engineering["totals"]["hardware_hkd"])}
    context["factory_price_hkd"] = sum(context.values())
    summary = _rr2_cost_summary(sections, context, snapshot, factory_id="huakang-b")
    workbook = Workbook()
    _build_summary_sheet(workbook, SimpleNamespace(product_name="电子拆分验证", quote_no="JP-ELECTRONIC-QA",
                         customer="JustPlay" if component_mode else "普通客", region_code="mainland", remark="演示文件，不对应正式订单"),
                         sections, snapshot, summary, context, [])
    return workbook, summary, sections, context


def test_imported_parts_split_by_component_without_allocating_overhead_to_ic_led_speaker():
    workbook, summary, sections, context = _electronic_export_fixture()
    sheet = workbook["报价明细"]
    blocks = []
    for component_id, name, raw_costs, battery_label, markup in [
        ("a", "电话", [2.5, .3, .3], "AG13电池×3", 1.16),
        ("b", "镜子", [1, .2, .5], "LR44电池×2", 1.25),
    ]:
        start = _find_row(sheet, 3, f"{name} · 电子")
        labels = [sheet.cell(start + offset, 3).value for offset in range(1, 6)]
        assert [label.split("（")[0] for label in labels] == ["IC", "LED", "喇叭", "PCB", "电池"]
        assert battery_label in labels[-1]
        assert [sheet.cell(start + offset, 4).value for offset in range(1, 4)] == pytest.approx(raw_costs)
        if component_id == "a":
            assert "A1" in labels[0] and "A2" in labels[0] and "B1" not in labels[0]
        else:
            assert "B1" in labels[0] and "A1" not in labels[0]
        assert sheet.cell(start + 5, 4).value == pytest.approx(.6)
        electronic_total = sum(float(entry["amount_hkd"]) for entry in summary["shipping_pricing"]["pricing_entries"]
                               if entry["section"] == "electronic" and entry["pricing_component_id"] == component_id)
        assert float(sheet.cell(start, 8).value[1:]) == pytest.approx(electronic_total)
        assert electronic_total > sum(raw_costs)
        assert sheet.cell(start + 4, 4).value == f"=H{start}-SUM(D{start+1}:D{start+3})"
        assert sheet.cell(start + 6, 4).value == f"=SUM(D{start+1}:D{start+5})"
        assert sheet.cell(start + 7, 4).value == markup
        assert sheet.cell(start + 8, 4).value == "=1-$Q$6"
        assert sheet.cell(start + 9, 4).value == f"=D{start+6}*D{start+7}/D{start+8}"
        assert sheet.cell(start + 11, 4).value == f"=D{start+9}/D{start+10}"
        assert [sheet.cell(start + offset, 2).value for offset in range(1, 6)] == ["电子"] * 4 + ["电池"]
        # No battery is left in the primary detail block or counted as an adjustment.
        primary = _find_row(sheet, 3, f"{name}明细")
        assert not any("电池×" in str(sheet.cell(row, 3).value) for row in range(primary, start))
        assert not any(sheet.cell(row, 3).value == "分配调整" for row in range(primary, start))
        blocks.append((start, electronic_total))
    # Summary entries are persisted to four decimal places independently.
    assert sum(total + .6 for _, total in blocks) + .1 == pytest.approx(float(context["factory_price_hkd"]), abs=.0005)
    assert sheet.cell(_find_row(sheet, 3, "电池片"), 2).value == "五金"
    usd_refs = [f"$D${start+11}" for start, _ in blocks]
    combined = [cell.value for row in sheet for cell in row if cell.data_type == "f" and all(ref in cell.value for ref in usd_refs)]
    assert combined and all(combined[0].count(ref) == 1 for ref in usd_refs)
    # The tax summary must include every electronic/battery detail range once.
    for start, _ in blocks:
        for category in ("电子", "电池"):
            headers = [cell for row in sheet for cell in row if cell.value == category and cell.column >= 5]
            assert headers
            assert any(f'SUMIF($B${start+1}:$B${start+5},{header.coordinate},$D${start+1}:$D${start+5})'
                       in str(sheet.cell(header.row + 1, header.column).value) for header in headers)
    output = BytesIO()
    workbook.save(output)
    with_formula = load_workbook(BytesIO(output.getvalue()))
    assert with_formula["报价明细"].cell(blocks[0][0] + 4, 4).data_type == "f"
    assert with_formula["报价明细"].cell(blocks[0][0], 1).border.top.style == "medium"
    with_formula.close()
    workbook.close()


def test_old_electronic_source_battery_and_engineering_battery_are_added_only_once():
    workbook, summary, _, _ = _electronic_export_fixture(inline_battery=True)
    sheet = workbook["报价明细"]
    start = _find_row(sheet, 3, "电话 · 电子")
    assert sheet.cell(start + 5, 4).value == pytest.approx(1)
    total = sum(float(entry["amount_hkd"]) for entry in summary["shipping_pricing"]["pricing_entries"]
                if entry["section"] == "electronic" and entry["pricing_component_id"] == "a")
    assert sheet.cell(start, 8).value == f"={format(total, '.12g')}-D{start+5}+0.6"
    assert "旧电子表电池" in sheet.cell(start + 5, 3).value
    assert "AG13电池×3" in sheet.cell(start + 5, 3).value
    workbook.close()


def test_ordinary_customer_keeps_existing_electronic_and_battery_layout():
    workbook, _, _, _ = _electronic_export_fixture(component_mode=False)
    sheet = workbook["报价明细"]
    assert not any(" · 电子" in str(cell.value) or cell.value == "PCB" for row in sheet for cell in row)
    assert _find_row(sheet, 3, "电子") > 0
    assert _find_row(sheet, 3, "电池") > 0
    workbook.close()


@pytest.mark.parametrize("name,expected", [
    ("IC (240S)", "IC"), ("LED红光", "LED"), ("LEDS", "LED"), ("Speaker 27mm", "喇叭"),
    ("扬声器", "喇叭"), ("AG13电池*3", "电池"), ("BATTERIES", "电池"),
    ("电池片", "PCB"), ("电池盒", "PCB"), ("BATTERY HOLDER", "PCB"),
    ("LED PCB", "PCB"), ("MIC", "PCB"), ("电阻", "PCB"),
])
def test_electronic_export_classification_does_not_mistake_contacts_or_pcb_assemblies_for_batteries(name, expected):
    assert _justplay_electronic_category(name) == expected


@pytest.mark.parametrize("mode", ["detail", "quick", "legacy"])
def test_source_parts_support_quick_and_legacy_hkd_quotes(mode):
    row = {"item": "IC", "specification": "主控", "quantity": 2, "unit_price_hkd": 1,
           "pricing_component_id": "b"}
    payload = {"components": [row]}
    if mode == "detail":
        payload["pricing_currency"] = "RMB"
    if mode == "quick":
        payload = {"quote_mode": "quick", "quick_quotes": [row]}
    calc = calculate_section("electronic", payload, {"fx": {"rmb_hkd": ".85"}}, "SOURCE-PARTS")
    parts = _justplay_electronic_source_parts(_section("electronic", payload=payload, calculation=calc))
    assert len(parts) == 1 and parts[0]["category"] == "IC"
    assert parts[0]["amount_hkd"] == (1 if mode == "quick" else 2)
    assert parts[0]["pricing_component_id"] == "b"
    assert parts[0]["specification"] == "主控"


def test_mismatched_legacy_snapshot_does_not_borrow_payload_category_or_component():
    parts = _justplay_electronic_source_parts(_section("electronic", payload={"components": [{"item": "IC", "pricing_component_id": "a"}]},
        calculation={"line_breakdown": [{"kind": "electronic_component", "item": "LED", "line_hkd": 1, "pricing_component_id": "b"}]}))
    assert parts[0]["category"] == "LED" and parts[0]["pricing_component_id"] == "b"


def test_inconsistent_electronic_total_is_not_silently_exported_as_negative_pcb():
    workbook, summary, sections, context = _electronic_export_fixture()
    workbook.close()
    for entry in summary["shipping_pricing"]["pricing_entries"]:
        if entry["section"] == "electronic":
            entry["amount_hkd"] = 0
    with pytest.raises(ValueError, match="电子总价不足"):
        _build_summary_sheet(Workbook(), SimpleNamespace(product_name="错误报价", quote_no="BAD", customer="JustPlay", region_code="mainland", remark=""),
                             sections, {"fx": {"rmb_hkd": .85, "hkd_usd": 7.8}}, summary, context, [])
