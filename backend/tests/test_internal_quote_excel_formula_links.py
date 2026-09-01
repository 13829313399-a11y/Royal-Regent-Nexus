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
                    "net_weight_g": "3.2",
                    "loss_rate_percent": "3",
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
        assert sheet["E9"].value == "=3.2*(1+3/100)"
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
        "t1": [
            {"key": "hardware", "value": "2.13"},
            {"key": "sewing_cloth", "value": "12.66"},
        ],
        "t2": [{"key": "other_buy", "value": "4.2"}],
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
                {"id": "detail-02", "name": "镜片", "cost_hkd": "4.2", "pricing_base_hkd": "4.2", "markup": "1.08"},
            ],
            "pricing_entries": [
                {
                    "section": "sewing",
                    "kind": "sewing",
                    "label": "车衣",
                    "amount_hkd": "12.66",
                    "markup_override": "1.03",
                },
                {
                    "section": "engineering",
                    "kind": "purchase",
                    "auxiliary_category": "镜片",
                    "label": "镜片",
                    "amount_hkd": "4.2",
                    "markup_override": "1.08",
                },
            ],
            "rows": [
                {"name": "出厂价", "freight_hkd": "0", "lift_hkd": "0"},
                {"name": "港柜", "freight_hkd": "1.90", "lift_hkd": "1.10"},
            ],
        },
    }
    _build_summary_sheet(
        workbook,
        quote,
        [sales],
        {"fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"}},
        summary,
        {"sewing_hkd": "12.66"},
    )
    sheet = workbook.active
    try:
        def group_cost_row(name: str) -> int:
            return next(
                row
                for row in range(1, sheet.max_row + 1)
                if sheet.cell(row, 2).value == name
                and sheet.cell(row, 3).value == "成本"
            )

        main_cost_row = group_cost_row("主倍率汇总")
        detail_cost_row = group_cost_row("车衣")
        mirror_cost_row = group_cost_row("镜片")
        total_quote_row = _find_row(sheet, 2, "报价合计")
        main_cost_formula = str(sheet.cell(main_cost_row, 4).value)
        assert main_cost_formula.startswith("=SUM(D")
        assert main_cost_formula != f"=D{main_cost_row}"
        assert str(sheet.cell(main_cost_row, 5).value).startswith(
            f"=$D${main_cost_row}+"
        )
        assert sheet.cell(main_cost_row + 1, 4).value == 1.16
        assert sheet.cell(main_cost_row + 2, 4).value == "=1-$Q$6"
        assert sheet.cell(main_cost_row + 3, 4).value == f"=D{main_cost_row}*D{main_cost_row + 1}/D{main_cost_row + 2}"
        assert sheet.cell(detail_cost_row - 1, 2).value == "车衣"
        assert sheet.cell(detail_cost_row - 1, 3).value == "车衣"
        assert str(sheet.cell(detail_cost_row - 1, 4).value).startswith("=")
        assert sheet.cell(detail_cost_row + 1, 4).value == 1.03
        assert sheet.cell(mirror_cost_row - 1, 2).value == "其他外购"
        assert sheet.cell(mirror_cost_row - 1, 3).value == "镜片"
        assert sheet.cell(mirror_cost_row + 1, 4).value == 1.08
        assert detail_cost_row == main_cost_row + 6
        assert mirror_cost_row == detail_cost_row + 6
        assert total_quote_row == mirror_cost_row + 4
        assert sheet.cell(main_cost_row + 4, 2).value is None
        assert sheet.cell(detail_cost_row + 4, 2).value is None
        assert sheet.cell(total_quote_row, 4).value == (
            f"=D{main_cost_row + 3}+D{detail_cost_row + 3}+D{mirror_cost_row + 3}"
        )
        def border_style(row: int, column: int, side: str) -> str | None:
            return getattr(getattr(sheet.cell(row, column).border, side), "style", None)

        assert border_style(main_cost_row, 2, "top") is None
        assert border_style(main_cost_row, 4, "top") == "thin"
        assert border_style(main_cost_row, 4, "left") is None
        assert border_style(main_cost_row + 3, 2, "bottom") is None
        assert border_style(main_cost_row + 3, 4, "bottom") == "thin"
        assert border_style(detail_cost_row - 1, 2, "top") is None
        assert border_style(detail_cost_row - 1, 4, "top") == "thin"
        assert border_style(detail_cost_row + 3, 4, "bottom") == "thin"
        assert border_style(total_quote_row, 2, "bottom") is None
        assert border_style(total_quote_row, 4, "bottom") == "thin"
        assert not any(
            sheet.cell(row, 3).value in {
                "分段汇总（HKD）",
                "分段报价合计（HKD）",
                "综合报价（USD，最后换算）",
            }
            for row in range(1, sheet.max_row + 1)
        )
        legacy_header_row = _find_row(sheet, 3, "旺季价")
        assert sheet.cell(legacy_header_row + 1, 4).value == f"=D{total_quote_row}"
        assert str(sheet.cell(legacy_header_row + 1, 9).value).count("SUMIF") >= 3
        second_header_row = legacy_header_row + 3
        assert str(sheet.cell(second_header_row + 1, 9).value).count("SUMIF") >= 3
        third_header_row = legacy_header_row + 6
        assert sheet.cell(third_header_row, 15).value in (None, "")
        assert sheet.cell(third_header_row + 1, 15).value in (None, "")
        tax_amount_row = legacy_header_row + 10
        assert str(sheet.cell(tax_amount_row, 4).value).count("SUMIF") >= 3
        assert not any(
            "#REF!" in str(cell.value)
            for row in sheet.iter_rows()
            for cell in row
        )
    finally:
        workbook.close()


def test_export_renders_justplay_components_before_one_global_packaging_block():
    workbook = Workbook()
    quote = SimpleNamespace(
        product_name="JustPlay 分配输出测试",
        quote_no="IQ-JUSTPLAY-LAYOUT",
        customer="JustPlay",
        region_code="mainland",
        remark="",
    )
    sales = _section(
        "sales",
        payload={
            "pricing_mode": "component",
            "pricing_components": [
                {"id": "component-01", "name": "主体", "markup_x": "1.15"},
                {"id": "component-02", "name": "镜子", "markup_x": "1.05"},
            ],
            "testing_fee_enabled": False,
            "cartons": [
                {
                    "length_in": "12",
                    "width_in": "10",
                    "height_in": "8",
                    "size_unit": "in",
                    "qty_per_carton": "6",
                }
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
                    "item": "主体胶壳",
                    "material": "PP",
                    "net_weight_g": "97",
                    "loss_rate_percent": "3",
                    "loss_weight_g": "99.91",
                    "material_price_hkd_lb": "6.8",
                    "machine_shift_price_hkd": "940",
                    "sets": "1",
                    "target_output": "1175",
                    "material_cost_hkd": "1.2",
                    "molding_cost_hkd": "0.8",
                    "amount_hkd": "2",
                    "pricing_component_id": "component-01",
                },
                {
                    "kind": "injection",
                    "item": "镜框",
                    "material": "ABS",
                    "net_weight_g": "31",
                    "loss_rate_percent": "3",
                    "loss_weight_g": "31.93",
                    "material_price_hkd_lb": "8.5",
                    "machine_shift_price_hkd": "1490",
                    "sets": "1",
                    "target_output": "3725",
                    "material_cost_hkd": "0.6",
                    "molding_cost_hkd": "0.4",
                    "amount_hkd": "1",
                    "pricing_component_id": "component-02",
                },
            ],
            "totals": {},
        },
    )
    summary = {
        "t1": [],
        "t2": [],
        "t3": [],
        "t4": [],
        "shipping_pricing": {
            "markup": "1.15",
            "active_markup_moq": "10000",
            "markup_tiers": [],
            "misc_ratio": "0.03",
            "pricing_mode": "component",
            "pricing_groups": [
                {"id": "component-01", "name": "主体", "cost_hkd": "2.52", "pricing_base_hkd": "4.02", "markup": "1.15"},
                {"id": "component-02", "name": "镜子", "cost_hkd": "1", "pricing_base_hkd": "1", "markup": "1.05"},
            ],
            "pricing_entries": [
                {"section": "molding", "kind": "injection", "label": "主体胶壳", "amount_hkd": "2", "pricing_component_id": "component-01", "is_global": False},
                {"section": "molding", "kind": "injection", "label": "镜框", "amount_hkd": "1", "pricing_component_id": "component-02", "is_global": False},
                {
                    "section": "assembly",
                    "kind": "assembly_process",
                    "label": "主体组装",
                    "amount_hkd": "0.52",
                    "pricing_component_id": "component-01",
                    "is_global": False,
                    "persons": "7",
                    "teams": "1",
                    "production_qty": "3500",
                    "formula_allocation_factor": "1",
                },
                {"section": "sales", "kind": "packaging_material", "category": "color_box_inner_card", "label": "彩盒/内卡", "amount_hkd": "0.8", "is_global": True},
                {"section": "sales", "kind": "justplay_fixed_packaging", "category": "other_purchase", "label": "胶纸/胶水/胶针", "formula_code": "adhesive", "amount_hkd": "0.0811627907", "is_global": True},
                {"section": "sales", "kind": "justplay_fixed_packaging", "category": "other_purchase", "label": "纸托板成本", "formula_code": "paper_pallet", "amount_hkd": "0.1819444444", "is_global": True},
                {"section": "sales", "kind": "carton", "label": "外箱", "amount_hkd": "0.7", "is_global": True},
            ],
            "global_pricing": {
                "cost_hkd": "1.7631072351",
                "pricing_base_hkd": "1.7631072351",
                "markup": "1.25",
                "settlement": "0.97",
                "entries": [
                    {"section": "sales", "kind": "packaging_material", "category": "color_box_inner_card", "label": "彩盒/内卡", "amount_hkd": "0.8", "is_global": True},
                    {"section": "sales", "kind": "justplay_fixed_packaging", "category": "other_purchase", "label": "胶纸/胶水/胶针", "formula_code": "adhesive", "amount_hkd": "0.0811627907", "is_global": True},
                    {"section": "sales", "kind": "justplay_fixed_packaging", "category": "other_purchase", "label": "纸托板成本", "formula_code": "paper_pallet", "amount_hkd": "0.1819444444", "is_global": True},
                    {"section": "sales", "kind": "carton", "label": "外箱", "amount_hkd": "0.7", "is_global": True},
                ],
            },
            "rows": [
                {"name": "出厂价", "freight_hkd": "0", "lift_hkd": "0"},
                {"name": "港柜", "freight_hkd": "2.645", "lift_hkd": "3.657"},
                {"name": "港散", "freight_hkd": "5.447", "lift_hkd": "10.169"},
            ],
        },
    }
    _build_summary_sheet(
        workbook,
        quote,
        [sales, molding],
        {"fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8"}},
        summary,
        {},
    )
    sheet = workbook["报价明细"]
    try:
        assert workbook.sheetnames[:2] == ["报价明细", "_报价明细计算"]
        main_title_row = _find_row(sheet, 1, "主体-明细")
        mirror_title_row = _find_row(sheet, 1, "镜子-明细")
        packaging_title_row = _find_row(sheet, 3, "包装明细")

        def find_between(column: int, value: str, start: int, end: int) -> int:
            return next(
                row
                for row in range(start, end + 1)
                if sheet.cell(row, column).value == value
            )

        assert main_title_row < mirror_title_row < packaging_title_row
        assert _find_row(sheet, 3, "主体胶壳") < mirror_title_row
        assert _find_row(sheet, 3, "镜框") > mirror_title_row
        main_mold_row = _find_row(sheet, 3, "主体胶壳")
        mirror_mold_row = _find_row(sheet, 3, "镜框")
        assert sheet.cell(main_mold_row, 5).value == "=97*(1+3/100)"
        assert sheet.cell(main_mold_row, 6).value.startswith("=")
        assert sheet.cell(main_mold_row, 10).value.startswith("=")
        assert sheet.cell(main_mold_row, 11).value == (
            f"=E{main_mold_row}*F{main_mold_row}"
        )
        assert sheet.cell(mirror_mold_row, 5).value == "=31*(1+3/100)"
        assembly_row = _find_row(sheet, 3, "主体组装")
        assert sheet.cell(assembly_row, 4).value == "=7*$M$4/3500"
        main_hkd_row = find_between(3, "配件报价（HKD）：", main_title_row, mirror_title_row - 1)
        main_fx_row = find_between(3, "美金兑港币汇率：", main_title_row, mirror_title_row - 1)
        main_usd_row = find_between(3, "配件单价（USD）：", main_title_row, mirror_title_row - 1)
        assert main_fx_row == main_hkd_row + 1
        assert main_usd_row == main_hkd_row + 2
        assert sheet.cell(main_fx_row, 4).value == "=$R$4"
        assert sheet.cell(main_usd_row, 4).value == f"=D{main_hkd_row}/D{main_fx_row}"
        mirror_hkd_row = find_between(3, "配件报价（HKD）：", mirror_title_row, packaging_title_row - 1)
        mirror_fx_row = find_between(3, "美金兑港币汇率：", mirror_title_row, packaging_title_row - 1)
        mirror_usd_row = find_between(3, "配件单价（USD）：", mirror_title_row, packaging_title_row - 1)
        assert mirror_fx_row == mirror_hkd_row + 1
        assert mirror_usd_row == mirror_hkd_row + 2
        assert sheet.cell(mirror_usd_row, 4).value == f"=D{mirror_hkd_row}/D{mirror_fx_row}"
        assert sum(
            1
            for row in range(1, sheet.max_row + 1)
            if sheet.cell(row, 3).value == "包装明细"
        ) == 1
        packaging_cost_row = _find_row(sheet, 3, "彩盒/内卡")
        assert packaging_cost_row > packaging_title_row
        assert sheet.cell(packaging_cost_row, 4).value == 0.8
        outer_carton_row = _find_row(sheet, 14, "外箱 (inch):")
        packing_qty_row = _find_row(sheet, 14, "装箱：")
        adhesive_row = _find_row(sheet, 3, "胶纸/胶水/胶针")
        paper_pallet_row = _find_row(sheet, 3, "纸托板成本")
        assert sheet.cell(adhesive_row, 4).value == (
            f"=3.9/2150*(O{outer_carton_row}*2+P{outer_carton_row}*4+6)/O{packing_qty_row}+0.06"
        )
        assert sheet.cell(paper_pallet_row, 4).value == f"=19/24/O{packing_qty_row}+0.05"
        assert sheet.cell(adhesive_row, 1).value == ""
        assert sheet.cell(paper_pallet_row, 1).value == ""
        carton_cost_row = _find_row(sheet, 3, "纸箱")
        assert str(sheet.cell(carton_cost_row, 4).value).startswith("=O")
        lift_cost_row = _find_row(sheet, 3, "吊柜费")
        packaging_freight_row = find_between(
            3,
            "运费",
            packaging_title_row,
            lift_cost_row - 1,
        )
        packaging_subtotal_row = find_between(
            3,
            "成本金额：",
            packaging_freight_row + 1,
            lift_cost_row - 1,
        )
        packaging_hkd_row = find_between(
            3,
            "单价（HK$）：",
            packaging_subtotal_row,
            lift_cost_row - 1,
        )
        packaging_fx_row = find_between(
            3,
            "美金兑港币汇率：",
            packaging_subtotal_row,
            lift_cost_row - 1,
        )
        packaging_usd_row = find_between(
            3,
            "包装成本（USD）：",
            packaging_subtotal_row,
            lift_cost_row - 1,
        )
        assert sheet.cell(packaging_title_row, 5).value == "港柜"
        assert sheet.cell(packaging_title_row, 6).value == "港散"
        assert sheet.cell(packaging_freight_row, 5).value == 2.645
        assert sheet.cell(packaging_freight_row, 6).value == 5.447
        assert sheet.cell(packaging_subtotal_row, 5).value == (
            f"=$D${packaging_subtotal_row}+E{packaging_freight_row}"
        )
        assert sheet.cell(packaging_subtotal_row + 1, 4).value == 1.25
        assert sheet.cell(packaging_hkd_row, 5).value == (
            f"=E{packaging_subtotal_row}*E{packaging_subtotal_row + 1}/E{packaging_subtotal_row + 2}"
        )
        assert sheet.cell(packaging_fx_row, 5).value == "=$R$4"
        assert sheet.cell(packaging_usd_row, 5).value == (
            f"=E{packaging_hkd_row}/E{packaging_fx_row}"
        )
        assert sheet.cell(lift_cost_row, 5).value == 3.657
        assert sheet.cell(lift_cost_row, 6).value == 10.169
        lift_hkd_row = lift_cost_row + 3
        lift_fx_row = lift_cost_row + 4
        lift_usd_row = lift_cost_row + 5
        assert sheet.cell(lift_hkd_row, 5).value == (
            f"=E{lift_cost_row}*E{lift_cost_row + 1}/E{lift_cost_row + 2}"
        )
        assert sheet.cell(lift_fx_row, 5).value == "=$R$4"
        assert sheet.cell(lift_usd_row, 5).value == f"=E{lift_hkd_row}/E{lift_fx_row}"
        assert not any(
            sheet.cell(row, 3).value in {
                "分段汇总及运输方案（HKD）",
                "包装、纸箱及运输（一次汇总）",
                "分段报价合计（HKD）",
                "综合报价（USD，最后换算）",
            }
            for row in range(1, sheet.max_row + 1)
        )
        freight_total_row = _find_row(sheet, 3, "产品价（含运费）（USD）：")
        combined_total_row = _find_row(sheet, 3, "产品价（含吊柜费）（USD）：")
        final_header_row = freight_total_row - 1
        assert lift_usd_row < final_header_row < freight_total_row < combined_total_row
        assert sheet.cell(final_header_row, 4).value == "出厂价"
        assert sheet.cell(final_header_row, 5).value == "港柜"
        assert sheet.cell(freight_total_row, 5).value == (
            f"=$D${main_usd_row}+$D${mirror_usd_row}+E{packaging_usd_row}"
        )
        assert sheet.cell(combined_total_row, 4).value == f"=D{freight_total_row}"
        assert sheet.cell(combined_total_row, 5).value == (
            f"=E{freight_total_row}+E{lift_usd_row}"
        )
        legacy_header_row = _find_row(sheet, 3, "旺季价")
        assert sheet.cell(legacy_header_row + 1, 4).value == (
            f"=F{combined_total_row}*$R$4"
        )
        assert str(sheet.cell(legacy_header_row + 1, 5).value).count("SUMIF") >= 3
        third_header_row = legacy_header_row + 6
        assert str(sheet.cell(third_header_row + 1, 8).value).count("SUMIF") >= 3
        tax_amount_row = legacy_header_row + 10
        assert str(sheet.cell(tax_amount_row, 4).value).count("SUMIF") >= 3
        assert "_报价明细计算" not in str(sheet.cell(tax_amount_row, 4).value)
    finally:
        workbook.close()
