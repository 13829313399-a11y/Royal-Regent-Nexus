from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import Workbook

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
        "structure": "",
        "mold_size": "",
        "color": "",
        "note": "客户模",
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
    assert component["unit_price_hkd"] == "11.7647"
    assert component["source_currency"] == "RMB"
    assert parsed.payload_fragment["bonding_hkd"] == "1.7647"
    assert parsed.payload_fragment["profit_rate_percent"] == "10.0000"


def test_painting_import_maps_seven_operation_contract():
    parsed = parse_internal_quote_workbook(
        workbook_bytes(
            [
                ["位置", "夹模", "单价", "移印", "单价", "散枪", "单价", "备注"],
                ["面部", 2, 0.5, 1, 0.3, 3, 0.2, "对色板"],
            ]
        ),
        "painting",
    )

    row = parsed.payload_fragment["rows"][0]
    assert row["operations"]["clamp"] == {"quantity": "2.0000", "unit_price_hkd": "0.5000"}
    assert row["operations"]["pad_print"] == {"quantity": "1.0000", "unit_price_hkd": "0.3000"}
    assert row["operations"]["spray"] == {"quantity": "3.0000", "unit_price_hkd": "0.2000"}
    assert row["operations"]["wipe"] == {"quantity": "0.0000", "unit_price_hkd": "0.0000"}


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
