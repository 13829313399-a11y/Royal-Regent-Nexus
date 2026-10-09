import pytest
import sys
from pathlib import Path
from types import SimpleNamespace


BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.services import molding_sample_excel as excel_service


def _sample_item(order_id: str = "BP-DISPATCH-XLSX-001") -> SimpleNamespace:
    return SimpleNamespace(
        id=f"{order_id}-001",
        sort_order=1,
        mold_id="M-001",
        mold_name="测试模具",
        material="ABS 750NSW",
        material_components=[],
    )


def _sample_order(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "id": "BP-DISPATCH-XLSX-001",
        "factory_id": "huakang-c",
        "production_factory_id": "huakang-a",
        "production_assigned_at": "2026-07-20 18:30:00",
        "order_number": "P-001",
        "doc_number": "DOC-001",
        "product_name": "跨厂啤办测试",
        "client_name": "测试客户",
        "date": "2026-07-20",
        "stage": "T0",
        "order_type": "啤办",
        "workshop": "工程部",
        "send_to": "内部",
        "supervisor": "工程主管",
        "eng_name": "工程师",
        "reason": "跨厂测试",
        "status": "待生产",
        "reject_reason": "",
        "completed_date": "",
        "updated_at": "2026-07-20 18:30:00",
        "items": [_sample_item()],
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_engineering_template_marks_origin_and_keeps_huakang_cd_executor_unassigned():
    workbook = excel_service.build_engineering_import_template("huakang-c")
    rows = excel_service._read_first_sheet_rows(workbook)

    assert rows[6][:6] == [
        "来源厂区",
        "华康C（huakang-c）",
        "承接生产厂",
        "",
        "派厂状态 / 时间",
        "待派厂；华康 C / D 必须选择 A / B",
    ]


def test_engineering_template_defaults_self_capable_factory_to_itself():
    workbook = excel_service.build_engineering_import_template("huaxing")
    rows = excel_service._read_first_sheet_rows(workbook)

    assert rows[6][1] == "华兴（huaxing）"
    assert rows[6][3] == "华兴（huaxing）"
    assert rows[6][5] == "本厂承接；正式创建后记录时间"


def test_parser_preserves_explicit_production_factory_and_leaves_missing_cd_assignment_empty():
    rows = [
        ["工程部啤办通知单 · 基础资料与模具明细导入模板"],
        ["客户", "测试客户", "产品编号", "P-001", "产品名称", "跨厂啤办测试"],
        ["开单日期", "2026-07-20", "阶段", "T0", "填写部", "工程部"],
        ["发至", "内部", "审核主管", "工程主管", "落单人", "工程师"],
        ["注意事项", "跨厂测试"],
        [],
        ["来源厂区", "华康C（huakang-c）", "承接生产厂", "华康A（huakang-a）"],
        ["模具编号", "模具名称", "所需用料", "啤数"],
        ["M-001", "测试模具", "ABS 750NSW", 1],
    ]
    workbook = excel_service._build_workbook(excel_service._sheet_xml(rows, header_row_index=8))

    parsed = excel_service.parse_order_excel(workbook)

    assert parsed.order.factory_id == "huakang-c"
    assert parsed.order.production_factory_id == "huakang-a"

    rows[6][3] = ""
    workbook_without_assignment = excel_service._build_workbook(
        excel_service._sheet_xml(rows, header_row_index=8)
    )
    parsed_without_assignment = excel_service.parse_order_excel(workbook_without_assignment)

    assert parsed_without_assignment.order.factory_id == "huakang-c"
    assert parsed_without_assignment.order.production_factory_id is None


def test_single_and_batch_exports_show_dispatch_contract_and_round_trip_executor():
    order = _sample_order()

    single_workbook = excel_service.export_order_to_excel(order)
    single_rows = excel_service._read_first_sheet_rows(single_workbook)

    assert single_rows[3][:8] == [
        "来源厂区",
        "华康C（huakang-c）",
        "承接生产厂",
        "华康A（huakang-a）",
        "派厂状态",
        "已派厂",
        "派厂时间",
        "2026-07-20 18:30:00",
    ]

    round_trip = excel_service.parse_order_excel(single_workbook, order_id_override="BP-DISPATCH-XLSX-002")
    assert round_trip.order.factory_id == "huakang-c"
    assert round_trip.order.production_factory_id == "huakang-a"

    batch_workbook = excel_service.export_orders_to_excel([order])
    batch_rows = excel_service._read_first_sheet_rows(batch_workbook)
    headers = batch_rows[1]
    values = batch_rows[2]

    assert values[headers.index("来源厂区")] == "华康C（huakang-c）"
    assert values[headers.index("承接生产厂")] == "华康A（huakang-a）"
    assert values[headers.index("派厂状态")] == "已派厂"
    assert values[headers.index("派厂时间")] == "2026-07-20 18:30:00"


def test_external_export_may_keep_production_factory_empty():
    order = _sample_order(
        production_factory_id=None,
        production_assigned_at="",
        workshop="模厂",
        send_to="发至模厂",
    )

    workbook = excel_service.export_order_to_excel(order)
    rows = excel_service._read_first_sheet_rows(workbook)

    assert rows[3][3] == "—"
    assert rows[3][5] == "外发单（无需派厂）"
    assert rows[3][7] == "—"


@pytest.mark.parametrize("header", ["报价目标", "报价目标（啤/日）", "报价目标(啤/日)", "报价目标（每日啤数）"])
def test_quote_target_maps_by_header_even_when_columns_move(header):
    rows = [["产品名称", "映射样品"], [header, "备注", "啤数", "模具编号", "模具名称", "所需用料"], ["3000.0", "保留备注", 50, "M1", "模具", "ABS"]]
    parsed = excel_service.parse_order_excel(excel_service._build_workbook(excel_service._sheet_xml(rows, header_row_index=2)))
    assert parsed.items[0].quote_target_daily_qty == 3000
    assert parsed.items[0].shoot_qty == 50
    assert parsed.items[0].notes == "保留备注"


@pytest.mark.parametrize("value", ["-1", "0", "12.5", "3000啤", "NaN", "Infinity", "2147483648"])
def test_quote_target_excel_rejects_invalid_input_with_row_number(value):
    rows = [["产品名称", "映射样品"], ["模具编号", "模具名称", "报价目标", "所需用料"], ["M1", "模具", value, "ABS"]]
    with pytest.raises(ValueError, match="第 3 行报价目标"):
        excel_service.parse_order_excel(excel_service._build_workbook(excel_service._sheet_xml(rows, header_row_index=2)))


def test_old_template_keeps_quote_target_empty_and_quote_cycle_in_notes():
    rows = [["产品名称", "旧模板"], ["模具编号", "模具名称", "啤数", "报价周期", "所需用料"], ["M1", "模具", 50, "3天", "ABS"]]
    parsed = excel_service.parse_order_excel(excel_service._build_workbook(excel_service._sheet_xml(rows, header_row_index=2)))
    assert parsed.items[0].quote_target_daily_qty is None
    assert parsed.items[0].notes == "报价周期：3天"
