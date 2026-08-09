from datetime import date, datetime
from pathlib import Path

import pytest
from openpyxl import Workbook, load_workbook
from openpyxl.drawing.image import Image as SpreadsheetImage
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from PIL import Image

from app.services.customer_order_huaxing import (
    HUAXING_CUSTOMER_MAPPINGS,
    HuaxingCustomerOrderError,
    _dedupe_multi_orders,
    _issues,
    _record_fields,
    _validate_skips,
)
from app.services.customer_order_manual import apply_overrides_to_records
from app.services.huaxing_order_legacy import (
    edu_schedule,
    multi_schedule,
    new_order_excel,
    shixin_schedule,
    three_sixty_schedule,
    yinhui_schedule,
)


def test_huaxing_customer_order_center_exposes_exactly_six_new_mappings():
    assert set(HUAXING_CUSTOMER_MAPPINGS) == {
        "edu",
        "360",
        "yinhui",
        "seasons",
        "maxx",
        "shushupapa",
    }
    assert all(spec.target_template.endswith("_SCHEDULE_APPEND_V2") for spec in HUAXING_CUSTOMER_MAPPINGS.values())


def test_edu_inspection_date_is_seven_days_before_ship_date_and_avoids_weekend():
    row = {
        "customer_type": "EDU",
        "customer_po": "EDU-100",
        "item_no": "A100",
        "product_name": "Test",
        "quantity": 120,
        "case_pack": 12,
        "ship_date": "2026-08-16",
    }

    edu_schedule.add_derived_fields(row, today=date(2026, 8, 1))

    assert row["inspection_date"] == "2026-08-07"
    assert row["cartons"] == 10


def test_360_date_code_uses_factory_year_and_day_of_year():
    assert three_sixty_schedule.build_360_date_code("2026-07-02", "60350") == "60350A26183"


def test_360_manual_inspection_result_clears_overdue_blocker_and_is_exportable(tmp_path):
    record = {
        "production_no": "RL-450484",
        "contract_no": "450484",
        "item_no": "1212016551.04",
        "quantity": 100,
        "inspection_date": "2026-08-01",
        "source_sheet": "接单表",
    }
    flags = three_sixty_schedule.build_flags(record, today=date(2026, 8, 7))
    issue = next(flag for flag in flags if flag["code"] == "missing_inspection_result")
    assert issue["field"] == "inspection_result"

    apply_overrides_to_records(
        [record],
        ["360-1"],
        [{
            "row_id": "360-1",
            "issue_key": "360-1:missing_inspection_result",
            "field": "inspection_result",
            "value": "合格",
        }],
    )
    assert record["inspection_result"] == "合格"
    assert not any(
        flag.get("code") == "missing_inspection_result"
        for flag in three_sixty_schedule.build_flags(record, today=date(2026, 8, 7))
    )

    output_path = tmp_path / "360人工补录.xlsx"
    three_sixty_schedule.create_import_workbook([record], output_path)
    workbook = load_workbook(output_path, data_only=True)
    worksheet = workbook["AI导入待确认"]
    headers = {cell.value: cell.column for cell in worksheet[1]}
    assert worksheet.cell(2, headers["验货结果"]).value == "合格"
    workbook.close()


def test_yinhui_uses_fixed_exchange_rate_and_ship_minus_five_days():
    row = {
        "so_no": "SO-1",
        "contract_no": "YH-1",
        "customer": "YINHUI",
        "item_no": "ITEM-1",
        "product_name": "Test",
        "quantity": 10,
        "case_pack": 5,
        "po_ship_date": "2026-08-20",
        "unit_price_usd": 2,
    }

    yinhui_schedule.add_derived_fields(row, today=date(2026, 8, 1))

    assert row["unit_price_hkd"] == 15.5
    assert row["total_hkd"] == 155
    assert row["inspection_date"] == "2026-08-15"


def test_yinhui_export_preserves_complete_workbook_and_inserts_before_total(tmp_path: Path):
    source_path = tmp_path / "银辉原排期.xlsx"
    output_path = tmp_path / "银辉原排期_银辉新单.xlsx"
    image_path = tmp_path / "marker.png"
    Image.new("RGB", (8, 8), "red").save(image_path)

    workbook = Workbook()
    linked = workbook.active
    linked.title = "接单表"
    linked["A1"] = "='Iteam表'!G6"
    target = workbook.create_sheet("Iteam表")
    image_sheet = workbook.create_sheet("历史图片")
    image_sheet["A1"] = "历史资料"
    image_sheet.add_image(SpreadsheetImage(image_path), "B2")
    headers = [
        "出单日期", "SO", "银辉合同号", "客名", "產品編號", "产品名称",
        "PO数量", "装箱数量", "外箱装箱数", "说明书", "彩盒", "客贴纸",
        "贴位图", "日期码", "备注", "箱唛资料", "验货日期", "完成情况",
        "备注", "订单单价USD", "单价HK$", "总金额HK$", "总金额USD",
        "总金额HK$", "出厂价HK$", "出厂价总金额HK$",
    ]
    for column, value in enumerate(headers, 1):
        target.cell(4, column, value)
        target.column_dimensions[target.cell(4, column).column_letter].width = 16
    history = [
        "2026-07-01", "SO-HISTORY", "PO-HISTORY", "历史客户", "ITEM-HISTORY", "历史产品",
        10, 5, "=G5/H5", "说明书", "彩盒", None, None, "180B6RR", None, None,
        "2026-07-20", None, None, 2, "=T5*7.75", "=U5*G5", "=V5/7.75",
        "=G5*U5", "=T5*7.75", "=Y5*G5",
    ]
    detail_fill = PatternFill("solid", fgColor="DDEBF7")
    for column, value in enumerate(history, 1):
        cell = target.cell(5, column, value)
        cell.fill = detail_fill
    target.row_dimensions[5].height = 28
    target.merge_cells("E6:F6")
    target["E6"] = "合计"
    target["G6"] = "=SUBTOTAL(9,G5:G5)"
    target.row_dimensions[6].height = 36
    target.auto_filter.ref = "A4:Z5"
    target.print_area = "A1:Z6"
    target.page_setup.orientation = "landscape"
    target.freeze_panes = "A5"
    target.conditional_formatting.add(
        "E6:F6",
        CellIsRule(operator="equal", formula=['"合计"'], fill=PatternFill("solid", fgColor="FFF2CC")),
    )
    validation = DataValidation(type="list", formula1='"A,B"')
    validation.add("E6")
    target.add_data_validation(validation)
    workbook.save(source_path)
    workbook.close()
    original_bytes = source_path.read_bytes()

    yinhui_schedule.create_export(
        [{
            "order_date": "2026-08-07",
            "so_no": "SO-NEW",
            "contract_no": "PO-NEW",
            "customer": "新客户",
            "item_no": "ITEM-NEW",
            "product_name": "新产品",
            "quantity": 20,
            "case_pack": 4,
            "unit_price_usd": 3,
            "factory_unit_price_hkd": 20,
        }],
        output_path,
        source_path,
        template_filename=source_path.name,
    )

    assert source_path.read_bytes() == original_bytes
    rendered = load_workbook(output_path, data_only=False)
    assert rendered.sheetnames == ["接单表", "Iteam表", "历史图片"]
    assert rendered["历史图片"]["A1"].value == "历史资料"
    assert len(rendered["历史图片"]._images) == 1
    assert rendered["接单表"]["A1"].value == "='Iteam表'!G7"
    target = rendered["Iteam表"]
    assert target["B5"].value == "SO-HISTORY"
    assert target["B6"].value == "SO-NEW"
    assert target["I6"].value == "=IFERROR(G6/H6,5.0)"
    assert target["U6"].value == "=T6*7.75"
    assert target["E7"].value == "合计"
    assert target["G7"].value == "=SUBTOTAL(9,G5:G6)"
    assert "E7:F7" in {str(value) for value in target.merged_cells.ranges}
    assert target.row_dimensions[6].height == 28
    assert target.row_dimensions[7].height == 36
    assert target["A6"].fill.fgColor.rgb == target["A5"].fill.fgColor.rgb
    assert target["A6"]._style.fontId == target["A5"]._style.fontId
    assert target.auto_filter.ref == "A4:Z6"
    assert str(target.print_area).endswith("$A$1:$Z$7")
    assert target.page_setup.orientation == "landscape"
    assert target.freeze_panes == "A5"
    assert "E7:F7" in {str(value.sqref) for value in target.conditional_formatting}
    assert {str(value.sqref) for value in target.data_validations.dataValidation} == {"E7"}
    rendered.close()


def test_360_export_targets_iteam_sheet_and_keeps_row_formulas(tmp_path: Path):
    template_path = tmp_path / "360排期.xlsx"
    output_path = tmp_path / "360排期_360新单.xlsx"
    workbook = Workbook()
    workbook.active.title = "接单表"
    target = workbook.create_sheet("Iteam表")
    headers = [
        None, "出单日期", "PO号", "生产单号", "360生产单号", "WM PO号",
        "360合同号", "客名", "產品編號", "产品名称", "规格", "PO数量",
        "外箱装箱数", "箱数", "说明书", "彩盒", "车款", "日期码", "备注",
        "验货日期", "FCD期", "走货期", "跟单", "订单单价USD", "单价HK$",
        "总金额USD", "总金额HK$", "出厂价HK$", "出厂价总金额HK$",
    ]
    for column, value in enumerate(headers, 1):
        target.cell(3, column, value)
        target.column_dimensions[target.cell(3, column).column_letter].width = 16
    row = [
        "已上系统", "2026-07-01", "PO-OLD", "REL-OLD", "RL-OLD", None,
        "CONTRACT-OLD", "历史客户", "10001", "历史产品", "欧洲", 10, 2,
        "=L4/M4", "EN", "彩盒", "车款", "60350A26183", None, datetime(2026, 7, 20),
        None, "=T4+14", "跟单", 12, "=X4*7.75", "=X4*L4", "=Y4*L4",
        "=X4*7.75-3.8", "=AB4*L4",
    ]
    for column, value in enumerate(row, 1):
        target.cell(4, column, value)
    target.merge_cells("E5:J5")
    target["E5"] = "合计"
    target["L6"] = "=SUBTOTAL(9,L4:L5)"
    target.auto_filter.ref = "A3:AC5"
    workbook.save(template_path)
    workbook.close()

    three_sixty_schedule.create_schedule_review_workbook(
        template_path.read_bytes(),
        [{
            "order_date": "2026-08-07",
            "po_no": "PO-NEW",
            "customer_release_no": "REL-NEW",
            "production_no": "RL-NEW",
            "contract_no": "CONTRACT-NEW",
            "customer": "新客户",
            "item_no": "20002",
            "product_name": "新产品",
            "spec": "美国",
            "quantity": 20,
            "outer_pack": 4,
            "inspection_date": "2026-08-20",
            "unit_price_usd": 15,
        }],
        output_path,
        template_filename=template_path.name,
    )

    rendered = load_workbook(output_path, data_only=False)
    assert rendered.sheetnames == ["接单表", "Iteam表"]
    target = rendered["Iteam表"]
    assert target["C4"].value == "PO-OLD"
    assert target["C5"].value == "PO-NEW"
    assert target["N5"].value == "=L5/M5"
    assert target["Y5"].value == "=X5*7.75"
    assert target["Z5"].value == "=X5*L5"
    assert target["AA5"].value == "=Y5*L5"
    assert target["E6"].value == "合计"
    assert target["L7"].value == "=SUBTOTAL(9,L4:L6)"
    assert target.auto_filter.ref == "A3:AC6"
    rendered.close()


def test_complete_append_skips_group_summary_rows_when_selecting_style_and_boundary(
    tmp_path: Path,
):
    source_path = tmp_path / "分组排期.xlsx"
    output_path = tmp_path / "分组排期_新单.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "接单表"
    worksheet.append(["PO号", "货号", "数量", "箱数"])
    worksheet.append(["PO-OLD", "ITEM-OLD", 12, "=C2/4"])
    worksheet["A2"].fill = PatternFill("solid", fgColor="DDEBF7")
    worksheet.merge_cells("A3:D3")
    worksheet["A3"] = "分组汇总"
    worksheet["A3"].fill = PatternFill("solid", fgColor="FFF2CC")
    worksheet["A4"] = "合计"
    worksheet["C4"] = "=SUBTOTAL(9,C2:C2)"
    workbook.save(source_path)
    workbook.close()

    new_order_excel.append_records_to_workbook(
        source_path,
        output_path,
        [{"po_no": "PO-NEW", "item_no": "ITEM-NEW", "quantity": 20}],
        {
            "po_no": ("PO号",),
            "item_no": ("货号",),
            "quantity": ("数量",),
            "cartons": ("箱数",),
        },
        filename=source_path.name,
        sheet_names=("接单表",),
    )

    rendered = load_workbook(output_path, data_only=False)
    worksheet = rendered["接单表"]
    assert worksheet["A2"].value == "PO-OLD"
    assert worksheet["A3"].value == "PO-NEW"
    assert worksheet["D3"].value == "=C3/4"
    assert worksheet["A3"].fill.fgColor.rgb == worksheet["A2"].fill.fgColor.rgb
    assert worksheet["A4"].value == "分组汇总"
    assert worksheet["A5"].value == "合计"
    assert worksheet["C5"].value == "=SUBTOTAL(9,C2:C3)"
    rendered.close()


def test_complete_append_keeps_formula_with_record_fallback(tmp_path: Path):
    source_path = tmp_path / "公式兜底排期.xlsx"
    output_path = tmp_path / "公式兜底排期_新单.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "接单表"
    worksheet.append(["数量", "装箱", "箱数"])
    worksheet.append([12, 4, "=A2/B2"])
    workbook.save(source_path)
    workbook.close()

    new_order_excel.append_records_to_workbook(
        source_path,
        output_path,
        [{"quantity": 60, "pack_qty": "3P/12", "cartons": 5}],
        {
            "quantity": ("数量",),
            "pack_qty": ("装箱",),
            "cartons": ("箱数",),
        },
        filename=source_path.name,
        sheet_names=("接单表",),
        formula_fallback_fields=("cartons",),
    )

    rendered = load_workbook(output_path, data_only=False)
    assert rendered["接单表"]["C3"].value == "=IFERROR(A3/B3,5)"
    rendered.close()


def test_seasons_composite_pack_uses_outer_carton_quantity():
    assert shixin_schedule.outer_pack_number("4P/16") == 16
    assert shixin_schedule.outer_pack_number("3P/12") == 12
    assert shixin_schedule.outer_pack_number("24/144") == 144


def test_yinhui_identifiers_are_written_as_text(tmp_path: Path):
    source_path = tmp_path / "银辉排期.xlsx"
    output_path = tmp_path / "银辉排期_新单.xlsx"
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Iteam表"
    worksheet.append(["SO", "银辉合同号", "产品编号", "PO数量", "装箱数量", "总箱数"])
    worksheet.append(["2300000001", "4500000001", "5122208863801", 10, 5, "=D2/E2"])
    workbook.save(source_path)
    workbook.close()

    yinhui_schedule.create_export(
        [{
            "so_no": "2300000463-780",
            "contract_no": "4500002406",
            "item_no": "5122208863801",
            "quantity": 20,
        }],
        output_path,
        source_path,
        template_filename=source_path.name,
    )

    rendered = load_workbook(output_path, data_only=False)
    worksheet = rendered["Iteam表"]
    for coordinate in ("A3", "B3", "C3"):
        assert worksheet[coordinate].data_type == "s"
        assert worksheet[coordinate].number_format == "@"
    assert worksheet["F3"].value == '=IFERROR(D3/E3,"")'
    rendered.close()


def test_seasons_schedule_families_are_kept_in_separate_lanes():
    assert shixin_schedule.schedule_family_from_sheets(["正单评审表"]) == "seasons"
    assert shixin_schedule.schedule_family_from_sheets(["手掌", "面具"]) == "internal"


def test_maxx_and_shushupapa_apply_their_seven_day_dates():
    maxx = multi_schedule._line_values(
        {"client": "maxx", "po_number": "MAXX-1", "ship_date": "2026-08-20"},
        {"item_code": "100", "description": "Maxx item", "quantity": 10},
    )
    shushupapa = multi_schedule._line_values(
        {"client": "shushupapa", "po_number": "SSP-1", "ship_date": "2026-08-20"},
        {"item_code": "200", "description": "Shushu item", "quantity": 10},
    )

    assert maxx["complete_date"] == "2026-08-13"
    assert maxx["inspection_date"] == "2026-08-13"
    assert shushupapa["complete_date"] is None
    assert shushupapa["inspection_date"] == "2026-08-13"


def test_multi_customer_revision_dedup_keeps_highest_revision():
    selected, report = _dedupe_multi_orders([
        {"po_number": "PO-1", "filename": "PO-1.pdf"},
        {"po_number": "PO-1", "filename": "PO-1_REV2.pdf"},
    ])

    assert [item["filename"] for item in selected] == ["PO-1_REV2.pdf"]
    assert "PO-1.pdf" in report[0]


def test_common_preview_contract_maps_each_customer_and_blocks_high_risk_flags():
    assert _record_fields("edu", {"customer_po": "E-1", "item_no": "A"})["po_no"] == "E-1"
    assert _record_fields("360", {"production_no": "RL-1", "item_full": "B"})["contract_no"] == "RL-1"
    assert _record_fields("yinhui", {"contract_no": "Y-1"})["po_no"] == "Y-1"
    assert _record_fields("seasons", {"oqf_no": "QF-1"})["po_no"] == "QF-1"
    assert _record_fields("maxx", {"po_number": "M-1"})["po_no"] == "M-1"
    assert _record_fields("shushupapa", {"po_number": "S-1"})["po_no"] == "S-1"

    issues = _issues(
        {"flags": [{"level": "high", "code": "missing_item", "text": "缺货号"}]},
        "maxx-1",
    )
    assert issues[0]["severity"] == "blocked"
    assert issues[0]["can_skip"] is False


def test_existing_orders_and_data_risks_support_controlled_manual_resolution():
    issues = _issues(
        {
            "po_number": "PO-EXISTING",
            "_duplicate_existing": True,
            "flags": [{"level": "high", "code": "missing_item", "text": "缺货号"}],
        },
        "maxx-1",
    )
    duplicate = next(issue for issue in issues if issue["code"] == "duplicate_existing_order")
    hard_blocker = next(issue for issue in issues if issue["code"] == "missing_item")

    assert duplicate["severity"] == "blocked"
    assert duplicate["can_skip"] is True
    assert duplicate["skip_label"] == "测试阶段确认重复导入当前或历史排期已有订单"
    assert hard_blocker["can_skip"] is False

    preview = {"rows": [{"issues": issues}]}
    with pytest.raises(HuaxingCustomerOrderError, match="缺货号"):
        _validate_skips(preview, {duplicate["skip_key"]})
    _validate_skips({"rows": [{"issues": [duplicate]}]}, {duplicate["skip_key"]})
    _validate_skips(
        preview,
        {duplicate["skip_key"], hard_blocker["skip_key"]},
    )
