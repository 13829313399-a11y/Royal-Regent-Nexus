from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

from app.services.internal_quote_artifacts import _merge_import_payload
from app.services.internal_quote_import import parse_internal_quote_workbook


def workbook_bytes(rows: list[list[object]], title: str = "报价明细") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = title
    for row in rows:
        sheet.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_mold_import_maps_rr2_fields_to_p2_engineering_contract():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "目标数", "备注"],
                ["M-100", "公仔头模", "ABS", 85, 1, 28000, "4A", 8000, "客户模"],
            ]
        ),
        "mold",
        fallback_qty=Decimal("5000"),
    )

    assert parsed.target_department == "engineering"
    assert parsed.header_row == 1
    assert parsed.row_count == 1
    assert parsed.payload_fragment["amortization_qty"] == "5000.0000"
    assert parsed.payload_fragment["molds"][0] == {
        "item": "公仔头模",
        "mold_no": "M-100",
        "quantity": "1.0000",
        "cost_rmb": "28000.0000",
        "material": "ABS",
        "net_weight_g": "85.0000",
        "cavity": "",
        "machine_code": "4A",
        "target_output": "8000.0000",
        "mold_base_type": "",
        "structure": "",
        "cycle_time_seconds": "0.0000",
        "mold_size": "",
        "color": "",
        "image_reference": "",
        "remark": "客户模",
        "source_row": 2,
    }
    assert any("图片附件" in warning for warning in parsed.warnings)


def test_electronic_import_converts_rmb_and_maps_extra_parameters():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["零件名称", "规格", "用量", "单价RMB", "备注"],
                ["IC", "A1", 2, 10, "主控"],
                ["邦定成本", 1.5],
                ["10%利润"],
            ]
        ),
        "electronic",
        rmb_hkd=Decimal("0.85"),
    )

    component = parsed.payload_fragment["components"][0]
    assert parsed.target_department == "electronic"
    assert component["quantity"] == "2.0000"
    assert component["unit_price_rmb"] == "10.0000"
    assert component["unit_price_hkd"] == "11.7647"
    assert component["tax_rate_percent"] == "13.0000"
    assert component["source_currency"] == "RMB"
    assert parsed.payload_fragment["bonding_rmb"] == "1.5000"
    assert parsed.payload_fragment["bonding_hkd"] == "1.7647"
    assert parsed.payload_fragment["profit_rate_percent"] == "10.0000"


def test_electronic_import_keeps_smt_specs_as_components_and_reads_exact_summary_labels():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["零件名称", "规格", "用量", "单价RMB", "合计RMB", "备注"],
                ["IC", "A1", 1, 0.1, 0.1, "主控"],
                [None, "A2", 2, 0.2, 0.4, ""],
                ["电阻", "SMT0603", 18, 0.002, 0.036, ""],
                [None, "SMT0402", 1, 0.003, 0.003, ""],
                ["报价按客户确认图纸为准"],
                [None, None, None, "零件成本:", 0.539],
                [None, None, None, "贴片成本:", 0.496],
                [None, None, None, "人工成本:", 0.6925],
                ["含*10%利润价(月结以此价为准)"],
            ]
        ),
        "electronic",
        rmb_hkd=Decimal("0.85"),
    )

    assert parsed.row_count == 4
    assert len(parsed.payload_fragment["components"]) == 2
    assert parsed.payload_fragment["components"][1]["specification"] == "SMT0603"
    assert parsed.payload_fragment["components"][1]["children"][0]["specification"] == "SMT0402"
    assert parsed.payload_fragment["smt_rmb"] == "0.4960"
    assert parsed.payload_fragment["smt_hkd"] == "0.5835"
    assert parsed.payload_fragment["labor_rmb"] == "0.6925"
    assert parsed.payload_fragment["profit_rate_percent"] == "10.0000"


def test_electronic_append_promotes_legacy_hkd_extras_before_adding_rmb_import():
    merged = _merge_import_payload(
        "electronic",
        {
            "components": [{"item": "旧件", "quantity": "1", "unit_price_hkd": "2"}],
            "bonding_hkd": "1",
            "smt_hkd": "2",
            "profit_rate_percent": "10",
            "tax_credit_difference_hkd": "9",
        },
        {
            "pricing_currency": "RMB",
            "components": [{"item": "新件", "quantity": "1", "unit_price_rmb": ".3"}],
            "bonding_rmb": ".5",
            "bonding_hkd": ".5882",
            "smt_rmb": ".2",
            "smt_hkd": ".2353",
            "profit_rate_percent": "10",
        },
        "append",
        ".85",
    )

    assert len(merged["components"]) == 2
    assert merged["pricing_currency"] == "RMB"
    assert merged["bonding_rmb"] == "1.35"
    assert merged["smt_rmb"] == "1.90"
    assert "bonding_hkd" not in merged
    assert "smt_hkd" not in merged
    assert "tax_credit_difference_hkd" not in merged


def test_molding_import_maps_rr2_injection_and_blow_sections_and_ignores_derived_prices():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["二、注塑部分"],
                ["模具名称", "模号", "材质", "料型", "颜色", "啤净重(g)", "料损耗 3%", "料价 HK$/g", "原料单价 HK$", "机台", "啤价(HK$/啤)", "出模数", "套数", "机型", "目标数", "周期(秒)", "成品金额 HK$", "成品用量", "备注"],
                ["主体模", "M-01", "ABS", "750SW", "黑色", 100, 103, 0.0187, 1.926, "80T", 0.188, "2", 1, "5A", 5000, 24, 2.114, 2, "客签色"],
                [],
                ["二·B、吹气部分"],
                ["货名", "日产量/22H", "用料", "预估料重 g", "料价 HK$/lb", "产品料价", "吹工", "披锋", "小计", "利润 ×", "合计 HK$", "成品用量", "出数", "模价 (¥)", "备注"],
                ["吹气瓶", "12000", "ABS 750SW", 45, 8.5, 0.8425, 0.2, 0.1, 1.1425, 1.05, 1.1996, 1, "1出2", 5000, "透明"],
            ],
            title="啤机报价",
        ),
        "molding",
    )

    assert parsed.target_department == "molding"
    assert parsed.header_row == 2
    assert parsed.row_count == 2
    assert parsed.payload_fragment["injection_loss_rate_percent"] == "3.0000"
    assert parsed.payload_fragment["injection_lines"][0] == {
        "item": "主体模",
        "mold_no": "M-01",
        "material": "ABS",
        "grade": "750SW",
        "color": "黑色",
        "net_weight_g": "100.0000",
        "loss_rate_percent": "3.0000",
        "machine_name": "80T",
        "machine_code": "5A",
        "cavity": "2",
        "sets": "1.0000",
        "target_output": "5000.0000",
        "cycle_time_seconds": "24.0000",
        "quantity": "2.0000",
        "remark": "客签色",
        "source_row": 3,
    }
    assert parsed.payload_fragment["blow_lines"][0] == {
        "item": "吹气瓶",
        "daily_capacity": "12000",
        "material": "ABS",
        "grade": "750SW",
        "estimated_weight_g": "45.0000",
        "labor_hkd": "0.2000",
        "burr_hkd": "0.1000",
        "profit_multiplier": "1.0500",
        "quantity": "1.0000",
        "output_count": "1出2",
        "mold_price_rmb": "5000.0000",
        "remark": "透明",
        "source_row": 7,
    }
    assert any("不直接写入" in warning for warning in parsed.warnings)


def test_molding_import_replace_updates_both_sections_and_loss_rate():
    merged = _merge_import_payload(
        "molding",
        {
            "injection_loss_rate_percent": "5",
            "injection_lines": [{"item": "旧注塑"}],
            "blow_lines": [{"item": "旧吹气"}],
            "caixing_tool_plan_rows": [{"ref_no": "KEEP"}],
        },
        {
            "injection_loss_rate_percent": "3",
            "injection_lines": [{"item": "新注塑"}],
            "blow_lines": [{"item": "新吹气"}],
        },
        "replace",
    )

    assert merged["injection_loss_rate_percent"] == "3"
    assert [row["item"] for row in merged["injection_lines"]] == ["新注塑"]
    assert [row["item"] for row in merged["blow_lines"]] == ["新吹气"]
    assert merged["caixing_tool_plan_rows"] == [{"ref_no": "KEEP"}]


def test_painting_import_maps_eight_operation_contract_and_row_metadata():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["图片", "名称", "位置", "夹模", "夹模单价", "移印", "移印单价", "散枪", "散枪单价", "擦PP水", "擦PP水单价", "总报价", "备注"],
                ["头部.png", "公仔", "面部", 2, 0.5, 1, 0.3, 3, 0.2, 4, 0.1, 2.3, "对色板"],
            ]
        ),
        "painting",
    )

    row = parsed.payload_fragment["rows"][0]
    assert row["operations"]["clamp"] == {"quantity": "2.0000", "unit_price_hkd": "0.5000"}
    assert row["operations"]["pad_print"] == {"quantity": "1.0000", "unit_price_hkd": "0.3000"}
    assert row["operations"]["spray"] == {"quantity": "3.0000", "unit_price_hkd": "0.2000"}
    assert row["operations"]["wipe"] == {"quantity": "0.0000", "unit_price_hkd": "0.0000"}
    assert row["operations"]["pp_water"] == {"quantity": "4.0000", "unit_price_hkd": "0.1000"}
    assert row["image_reference"] == "头部.png"
    assert row["name"] == "公仔"
    assert row["position"] == "面部"
    assert row["remark"] == "对色板"
    assert "总报价和合计仅用于核对" in parsed.warnings[0]


def test_painting_import_merges_a_two_row_operation_header():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["位置", "夹模", None, "移印", None, "散枪", None, "备注"],
                [None, "数量", "单价", "数量", "单价", "数量", "单价", None],
                ["面部", 2, 0.5, 1, 0.3, 3, 0.2, "对色板"],
            ]
        ),
        "painting",
    )

    row = parsed.payload_fragment["rows"][0]
    assert parsed.header_row == 1
    assert parsed.row_count == 1
    assert row["source_row"] == 3
    assert row["operations"]["clamp"] == {"quantity": "2.0000", "unit_price_hkd": "0.5000"}
    assert row["operations"]["pad_print"] == {"quantity": "1.0000", "unit_price_hkd": "0.3000"}


def test_slush_import_maps_visible_quote_fields_and_ignores_source_total():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["产品编号", "胶件名称", "材料", "料重(g)", "日产量24H", "用量(PC)", "单价 HKD", "总价 HKD", "备注"],
                ["RC-01", "公仔手臂", "PVC", 35.5, 8000, 2, 3.6, 99, "透明"],
                ["合计", None, None, None, None, None, None, 99, None],
            ],
            title="搪胶报价",
        ),
        "slush",
    )

    assert parsed.target_department == "slush"
    assert parsed.header_row == 1
    assert parsed.row_count == 1
    assert parsed.payload_fragment["lines"][0] == {
        "product_code": "RC-01",
        "item": "公仔手臂",
        "material": "PVC",
        "weight_g": "35.5000",
        "daily_output_24h": "8000.0000",
        "quantity": "2.0000",
        "unit_price_hkd": "3.6000",
        "remark": "透明",
        "source_row": 2,
    }
    assert any("总价和合计仅用于核对" in warning for warning in parsed.warnings)


def test_slush_import_replace_only_replaces_slush_lines():
    merged = _merge_import_payload(
        "slush",
        {"lines": [{"product_code": "OLD"}], "legacy_note": "keep"},
        {"lines": [{"product_code": "RC-01"}]},
        "replace",
    )

    assert merged["lines"] == [{"product_code": "RC-01"}]
    assert merged["legacy_note"] == "keep"


def test_sewing_import_keeps_usage_rmb_price_markup_and_labor_line():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["物料名称", "裁片部位", "供应商", "用量", "单价", "码点", "价钱", "备注"],
                ["绒布", "身体", "供应商A", 0.25, 12, 1.1, 3.3, "红色"],
                ["车缝人工", "", "", 1, 2, 1, 2, ""],
            ]
        ),
        "sewing",
    )

    group = parsed.payload_fragment["groups"][0]
    assert parsed.target_department == "sewing"
    assert group["category"] == "clothes"
    assert group["materials"][0]["usage"] == "0.2500"
    assert group["materials"][0]["unit_price_rmb"] == "12.0000"
    assert group["materials"][0]["markup"] == "1.1000"
    assert group["materials"][1]["item"] == "车缝人工"
    assert group["labor_rmb"] == "0.0000"


def test_sewing_import_maps_screenshot_fields_multiple_groups_and_ignores_derived_totals():
    header = ["布料名称", "部位", "工艺", "裁片数", "用量/码", "物料价(RMB)", "价钱(RMB)", "码点", "总价钱(RMB)", "备注"]
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["产品：6寸小蜥蜴 / 盾牌"],
                header,
                ["绒布", "身体", "电绣", 4, 0.25, 12, 3, 1.1, 99, "红色"],
                ["车缝人工", "", "", 0, 1, 2, 2, 1, 99, ""],
                ["合计", None, None, None, None, None, None, None, 198, None],
                ["产品：发套"],
                header,
                ["毛料", "头部", "", 2, 0.5, 8, 4, 0, 88, "黑色"],
            ],
            title="车缝报价",
        ),
        "sewing",
    )

    assert parsed.target_department == "sewing"
    assert parsed.header_row == 2
    assert parsed.row_count == 3
    assert [group["name"] for group in parsed.payload_fragment["groups"]] == ["6寸小蜥蜴 / 盾牌", "发套"]
    first = parsed.payload_fragment["groups"][0]["materials"][0]
    assert first == {
        "item": "绒布",
        "part": "身体",
        "craft": "电绣",
        "pieces": "4.0000",
        "supplier": "",
        "usage": "0.2500",
        "unit_price_rmb": "12.0000",
        "markup": "1.1000",
        "remark": "红色",
        "source_row": 3,
    }
    assert parsed.payload_fragment["groups"][1]["category"] == "hair"
    assert parsed.payload_fragment["groups"][1]["materials"][0]["markup"] == "1.0000"
    assert any("总价钱和合计仅用于核对" in warning for warning in parsed.warnings)


def test_assembly_import_builds_process_groups_and_uses_quote_qty_fallback():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["组装工序名称", "人数", "工具", "备注"],
                ["装电池", 4, "电批", "检查极性"],
            ]
        ),
        "assembly",
        fallback_qty=Decimal("1000"),
    )

    group = parsed.payload_fragment["groups"][0]
    process = group["processes"][0]
    assert group["category"] == "assembly"
    assert process["name"] == "装电池"
    assert process["persons"] == "4.0000"
    assert process["production_qty"] == "1000.0000"
    assert any("报价数量" in warning for warning in parsed.warnings)


def test_binary_xls_is_rejected_by_p3_parser():
    with pytest.raises(ValueError, match="xlsx/xlsm"):
        parse_internal_quote_workbook(b"\xD0\xCF\x11\xE0fake", "mold")
