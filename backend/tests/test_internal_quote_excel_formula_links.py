import json
from types import SimpleNamespace

from openpyxl import Workbook

from app.services.internal_quote_excel import _build_summary_sheet


def _section(
    department: str,
    *,
    payload: dict[str, object] | None = None,
    calculation: dict[str, object] | None = None,
):
    return SimpleNamespace(
        department=department,
        calculation_status="valid",
        payload_json=json.dumps(payload or {}, ensure_ascii=False),
        calculation_json=json.dumps(calculation or {}, ensure_ascii=False),
    )


def _find_row(sheet, column: int, value: object) -> int:
    return next(
        row
        for row in range(1, sheet.max_row + 1)
        if sheet.cell(row, column).value == value
    )


def test_export_links_molding_assembly_cartons_and_flat_cards_to_source_cells():
    workbook = Workbook()
    quote = SimpleNamespace(
        product_name="公式联动测试",
        quote_no="IQ-FORMULA-LINKS",
        region_code="mainland",
        remark="",
    )
    sales = _section(
        "sales",
        payload={
            "paper_price_factor": 2.75,
            "inner_paper_price_factor": 3.25,
            "flat_card_price_factor": 2.75,
            "color_box_size_unit": "cm",
            "color_box_size_in": {"length": 7.5, "width": 3.35, "height": 4.92},
            "product_size_in": {"length": 6, "width": 6, "height": 6},
            "cartons": [
                {
                    "item": "主纸箱",
                    "size_unit": "cm",
                    "length_in": 80 / 2.54,
                    "width_in": 29 / 2.54,
                    "height_in": 30 / 2.54,
                    "qty_per_carton": 4,
                    "flat_cards": [
                        {
                            "name": "主平卡",
                            "length_in": 19 / 2.54,
                            "width_in": 8.5 / 2.54,
                            "quantity": 2,
                        }
                    ],
                },
                {
                    "item": "内纸箱",
                    "size_unit": "cm",
                    "length_in": 80 / 2.54,
                    "width_in": 29 / 2.54,
                    "height_in": 30 / 2.54,
                    "qty_per_carton": 1,
                    "flat_cards": [],
                },
            ],
        },
        calculation={"line_breakdown": [], "totals": {}},
    )
    molding = _section(
        "molding",
        calculation={
            "line_breakdown": [
                {
                    "kind": "injection",
                    "item": "车轮芯",
                    "material": "1#PP",
                    "grade": "7032 E3",
                    "loss_weight_g": "3.296",
                    "material_price_hkd_lb": "6.8",
                    "material_price_hkd_g": "0.014978",
                    "machine_code": "4A-6A",
                    "machine_shift_price_hkd": "940",
                    "sets": "3",
                    "target_output": "4800",
                    "molding_cost_hkd": "0.065278",
                    "material_cost_hkd": "0.04937",
                }
            ],
            "totals": {},
        },
    )
    assembly_amount = 35 * 260 / 3500
    packaging_amount = 17 * 260 / 3500
    assembly = _section(
        "assembly",
        payload={"labor_base_hkd": 260},
        calculation={
            "group_summaries": [
                {
                    "category": "assembly",
                    "group": "组装半成品",
                    "standard_work_hours": "11",
                    "labor_base_hkd": "260",
                    "production_qty": "3500",
                    "teams": "1",
                    "total_persons": "35",
                    "amount_hkd_pcs": str(assembly_amount),
                },
                {
                    "category": "packaging",
                    "group": "包装",
                    "standard_work_hours": "11",
                    "labor_base_hkd": "260",
                    "production_qty": "3500",
                    "teams": "1",
                    "total_persons": "17",
                    "amount_hkd_pcs": str(packaging_amount),
                },
            ]
        },
    )
    summary = {
        "t1": [{"key": "material", "value": "0.04937"}],
        "t2": [],
        "t3": [{"key": "injection_labor", "value": "0.065278"}],
        "t4": [],
        "molding_material_breakdown": {
            "total_hkd": "0.04937",
            "imported_hkd": "0.04937",
            "domestic_hkd": "0",
        },
        "shipping_pricing": {
            "markup": "1.2",
            "active_markup_moq": "10000",
            "markup_tiers": [],
            "misc_ratio": "0.02",
            "rows": [],
        },
    }
    reference_snapshot = {
        "fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"},
        "material_prices": {
            "1#PP|7032 E3": {
                "label": "7032 E3 1#PP料",
                "price_hkd_lb": "6.8",
            }
        },
        "machine_prices": [
            {"machine_range": "4A-6A", "shift_price_hkd": "940"}
        ],
        "assembly_labor_base_hkd": "260",
    }
    _build_summary_sheet(
        workbook,
        quote,
        [sales, molding, assembly],
        reference_snapshot,
        summary,
        {
            "molding_hkd": 0.04937 + 0.065278,
            "assembly_hkd": assembly_amount,
            "packing_labor_hkd": packaging_amount,
        },
    )
    sheet = workbook.active
    try:
        assert sheet["F9"].value == "=D$2/454"
        assert sheet["J9"].value == "=D$6/I9/H9"
        assert sheet["K9"].value == "=E9*F9"

        molding_total_row = _find_row(sheet, 3, "模具合计")
        material_detail_row = _find_row(sheet, 2, "料价")
        molding_detail_row = _find_row(sheet, 2, "啤工")
        assert sheet.cell(material_detail_row, 4).value == f"=K{molding_total_row}"
        assert sheet.cell(molding_detail_row, 4).value == f"=J{molding_total_row}"

        assembly_row = next(
            row
            for row in range(1, sheet.max_row + 1)
            if str(sheet.cell(row, 3).value).startswith("组装半成品")
        )
        packaging_labor_row = next(
            row
            for row in range(1, sheet.max_row + 1)
            if str(sheet.cell(row, 3).value).startswith("包装（")
        )
        assert sheet.cell(assembly_row, 4).value == "=35*$M$4/3500"
        assert sheet.cell(packaging_labor_row, 4).value == "=17*$M$4/3500"

        assert [sheet.cell(5, column).value for column in range(14, 18)] == [
            "主纸箱系数",
            "内纸箱系数",
            "平卡系数",
            "杂项",
        ]
        assert [sheet.cell(6, column).value for column in range(14, 17)] == [
            2.75,
            3.25,
            2.75,
        ]

        outer_row = _find_row(sheet, 14, "外箱 (cm):")
        inner_row = _find_row(sheet, 14, "内箱 (cm):")
        flat_card_row = _find_row(sheet, 14, "主平卡 (cm):")
        paperboard_row = _find_row(sheet, 14, "纸板价")
        carton_price_row = _find_row(sheet, 14, "箱价：")
        packing_qty_row = _find_row(sheet, 14, "装箱：")
        total_row = _find_row(sheet, 14, "合计")
        assert inner_row == outer_row + 1
        assert sheet.cell(flat_card_row, 17).value == 2.0
        assert sheet.cell(paperboard_row, 15).value == (
            f"=O{flat_card_row}/2.54*P{flat_card_row}/2.54*Q{flat_card_row}*$P$6/1000"
        )
        assert sheet.cell(carton_price_row, 15).value == (
            f"=(O{outer_row}/2.54+P{outer_row}/2.54+2)"
            f"*(P{outer_row}/2.54+Q{outer_row}/2.54+1)*$N$6*2/1000"
            f"+((O{inner_row}/2.54+P{inner_row}/2.54+2)"
            f"*(P{inner_row}/2.54+Q{inner_row}/2.54+1)*$O$6*2/1000)*O{packing_qty_row}"
        )
        assert sheet.cell(total_row, 15).value == (
            f"=IFERROR(O{carton_price_row}/O{packing_qty_row},0)"
        )
    finally:
        workbook.close()


def test_export_renders_formula_driven_split_pricing_groups():
    workbook = Workbook()
    quote = SimpleNamespace(product_name="分项倍率测试", quote_no="IQ-SPLIT-PRICING", region_code="mainland", remark="")
    sales = _section("sales", payload={"testing_fee_enabled": False}, calculation={"line_breakdown": [], "totals": {}})
    summary = {
        "t1": [],
        "t2": [],
        "t3": [],
        "t4": [],
        "shipping_pricing": {
            "markup": "1.16",
            "active_markup_moq": "10000",
            "markup_tiers": [],
            "misc_ratio": "0.02",
            "pricing_mode": "standard",
            "pricing_groups": [
                {"id": "main", "name": "主倍率汇总", "cost_hkd": "2.13", "pricing_base_hkd": "2.13", "markup": "1.16"},
                {"id": "detail-01", "name": "车衣", "cost_hkd": "12.66", "pricing_base_hkd": "12.66", "markup": "1.03"},
            ],
            "rows": [],
        },
    }
    _build_summary_sheet(
        workbook,
        quote,
        [sales],
        {"fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"}},
        summary,
        {},
    )
    sheet = workbook.active
    try:
        main_cost_row = _find_row(sheet, 2, "主倍率汇总")
        detail_cost_row = _find_row(sheet, 2, "车衣")
        total_quote_row = _find_row(sheet, 2, "报价合计")
        assert sheet.cell(main_cost_row, 4).value == 2.13
        assert sheet.cell(main_cost_row + 1, 4).value == 1.16
        assert sheet.cell(main_cost_row + 2, 4).value == "=1-$Q$6"
        assert sheet.cell(main_cost_row + 3, 4).value == f"=D{main_cost_row}*D{main_cost_row + 1}/D{main_cost_row + 2}"
        assert sheet.cell(detail_cost_row + 1, 4).value == 1.03
        assert sheet.cell(total_quote_row, 4).value == f"=D{main_cost_row + 3}+D{detail_cost_row + 3}"
    finally:
        workbook.close()
