from io import BytesIO

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


def test_mold_import_maps_rr2_fields_to_engineering_section():
    parsed = parse_internal_quote_workbook(workbook_bytes([
        ["模号", "产品名称", "材质", "克重", "套数", "模价", "机型", "备注"],
        ["M-100", "公仔头模", "ABS", 85, 10000, 28000, "4A", "客户模"],
    ]), "mold")

    assert parsed.target_department == "engineering"
    assert parsed.header_row == 1
    assert len(parsed.rows) == 1
    assert parsed.rows[0].specification == "M-100"
    assert parsed.rows[0].fields["mold_price_rmb"] == 28000
    assert parsed.rows[0].fields["amortization_qty"] == 10000


def test_electronic_import_maps_parts_and_extra_parameters():
    parsed = parse_internal_quote_workbook(workbook_bytes([
        ["零件名称", "规格", "用量", "单价", "备注"],
        ["IC", "A1", 2, 10, "主控"],
        ["邦定成本", 1.5],
        ["10%利润"],
    ]), "electronic")

    assert parsed.target_department == "electronic"
    assert len(parsed.rows) == 1
    assert parsed.rows[0].fields["unit_price_rmb"] == 10
    assert parsed.parameters["bonding_cost_rmb"] == 1.5
    assert parsed.parameters["profit_pct"] == 10


def test_sewing_import_keeps_usage_price_and_markup():
    parsed = parse_internal_quote_workbook(workbook_bytes([
        ["物料名称", "裁片部位", "供应商", "用量", "单价", "码点", "价钱", "备注"],
        ["绒布", "身体", "供应商A", 0.25, 12, 1.1, 3.3, "红色"],
    ]), "sewing")

    assert parsed.target_department == "sewing"
    assert len(parsed.rows) == 1
    assert parsed.rows[0].specification == "身体 / 供应商A"
    assert parsed.rows[0].fields == {
        "usage": 0.25,
        "material_price_hkd": 12.0,
        "markup": 1.1,
        "source_row": 2,
    }


def test_assembly_import_builds_process_cost_line():
    parsed = parse_internal_quote_workbook(workbook_bytes([
        ["工序名称", "人数"],
        ["装电池", 4],
    ]), "assembly")

    assert parsed.target_department == "assembly"
    assert len(parsed.rows) == 1
    assert parsed.rows[0].item_name == "装电池"
    assert parsed.rows[0].fields["people_count"] == 4
    assert parsed.rows[0].fields["base_rate_hkd"] == 310
    assert parsed.warnings


def test_painting_import_expands_each_operation_to_a_cost_line():
    parsed = parse_internal_quote_workbook(workbook_bytes([
        ["位置", "夹模", "单价", "移印", "单价", "备注"],
        ["面部", 2, 0.5, 1, 0.3, "对色板"],
    ]), "painting")

    assert parsed.target_department == "painting"
    assert [(row.item_name, row.quantity, row.unit_price_hkd) for row in parsed.rows] == [
        ("面部-夹模", 2, 0.5),
        ("面部-移印", 1, 0.3),
    ]
