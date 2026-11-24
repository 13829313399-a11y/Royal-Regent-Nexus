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


def test_monthly_workbook_preserves_cost_visibility_per_order():
    from io import BytesIO
    from openpyxl import load_workbook
    from app.schemas.molding_sample import MoldingSampleDetailResponse
    from app.services.molding_sample_monthly_excel import build_production_month_workbook

    def record(order_id, cost, visible):
        return MoldingSampleDetailResponse.model_validate({
            "order": vars(_sample_order(id=order_id)),
            "items": [{"id": f"{order_id}-1", "order_id": order_id, "actual_amount_hkd": cost,
                       "material": "ABS", "actual_weight_kg": 2, "required_material_kg": 3,
                       "actual_material_cost_components": [
                           dict(material="结算专用牌号", source_type="virgin", ratio_percent=100,
                                weight_kg=2, unit_price=cost, amount_hkd=cost),
                       ]}],
            "can_view_cost": visible,
        })

    restricted = record("BP-PRIVATE", 9876.54, False)
    workbook = load_workbook(BytesIO(build_production_month_workbook([restricted], "华康A", "2026-07")))
    assert "实际料费（HKD）" not in [cell.value for cell in workbook["模具明细"][3]]
    for sheet in workbook:
        assert all("HKD" not in str(cell.value) for cell in sheet[3])

    records = [restricted, record("BP-VISIBLE", 12.34, True)]
    workbook = load_workbook(BytesIO(build_production_month_workbook(records, "华康A", "2026-07")))
    details = workbook["模具明细"]
    amount_column = next(cell.column for cell in details[3] if cell.value == "实际料费（HKD）")
    assert details.cell(4, amount_column).value == "无成本权限"
    assert details.cell(5, amount_column).value == 12.34
    for sheet in workbook:
        for row in sheet.iter_rows(min_row=4, values_only=True):
            if row[0] == "BP-PRIVATE":
                assert 9876.54 not in row and "结算专用牌号" not in row
    assert all(row[9] is None and row[10] is None for row in workbook["配料明细"].values if row[0] == "BP-PRIVATE")


def test_monthly_mold_reconciliation_separates_blends_estimates_and_stored_fees():
    from io import BytesIO
    from openpyxl import load_workbook
    from app.schemas.molding_sample import MoldingSampleDetailResponse
    from app.services.molding_sample_monthly_excel import build_production_month_workbook

    order_id = "BP-RECON"
    settled = dict(id="i1", order_id=order_id, mold_id="001", sort_order=1, required_material_kg=10,
                   collected_weight_kg=9, actual_weight_kg=8, material_components=[
                       dict(material="ABS", ratio_percent=70, source_type="virgin"),
                       dict(material="PP", ratio_percent=30, source_type="runner"),
                   ], actual_material_cost_components=[
                       dict(material="ABS", ratio_percent=75, source_type="virgin", weight_kg=6, unit_price=5, amount_hkd=66.14),
                       dict(material="PP", ratio_percent=25, source_type="runner", weight_kg=2, unit_price=1, amount_hkd=4.41),
                   ], actual_amount_hkd=70.55, injection_cost=20, injection_cost_hkd=22, exchange_rate_at_save=1.1)
    legacy = dict(id="i2", order_id=order_id, mold_id="002", sort_order=2, required_material_kg=2,
                  actual_weight_kg=1, material="50% ABS + 50% PP 水口料", actual_amount_hkd=0, injection_cost=50)
    incomplete = dict(id="i3", order_id=order_id, mold_id="003", sort_order=3, required_material_kg=6,
                      collected_weight_kg=4, material="50% ABS + 50% 未定价料")
    record = MoldingSampleDetailResponse.model_validate({
        "order": vars(_sample_order(id=order_id)), "items": [legacy, incomplete, settled],
    })
    workbook = load_workbook(BytesIO(build_production_month_workbook([record], "华康A", "2026-07",
                                                                     prices={"abs": 10, "pp": 2})))

    def rows(name):
        sheet = workbook[name]
        keys = [cell.value for cell in sheet[3]]
        return [dict(zip(keys, row)) for row in sheet.iter_rows(min_row=4, values_only=True)]

    first, second, third = rows("逐模对账")
    assert (first["耗用减预计（kg）"], first["实领减耗用（kg）"]) == (-2, 1)
    assert (first["预计料费（HKD）"], first["已存实际料费（HKD）"], first["单模合计（HKD）"]) == (167.55, 70.55, 92.55)
    assert first["实耗估算（HKD）"] is None and first["保存汇率（HKD/RMB）"] == 1.1
    components = rows("配料明细")
    assert [(r["用料口径"], r["原料来源"], r["配比"], r["分项重量（kg）"], r["单价（HKD/lb）"], r["分项料费（HKD）"])
            for r in components[:4]] == [
        ("计划用料", "原料", .7, 7, 10, 154.32), ("计划用料", "水口料", .3, 3, 2, 13.23),
        ("已存结算", "原料", .75, 6, 5, 66.14), ("已存结算", "水口料", .25, 2, 1, 4.41),
    ]
    assert second["实耗估算（HKD）"] == 13.22 and second["已存实际料费（HKD）"] == 0
    assert second["单模合计（HKD）"] is None and second["啤办费（RMB）"] == 50
    assert third["预计料费（HKD）"] is None and third["实际耗用（kg）"] is None
    assert third["实耗估算（HKD）"] is None and "缺当前原料价" in components[-1]["数据来源"]
    assert [r["用料口径"] for r in components if r["模具编号"] == "003"] == ["计划用料", "计划用料"]
    summary = rows("单据汇总")[0]
    assert (summary["已填实耗项数"], summary["预计用料合计（kg）"], summary["费用齐全项数"]) == (2, 18, 1)
    assert summary["实际耗用合计（kg）"] is None and summary["全单费用（HKD）"] is None


def test_monthly_receipt_links_a_single_mold_without_requiring_inventory_movement_access():
    from io import BytesIO
    from openpyxl import load_workbook
    from app.models.molding_sample import MoldingSampleInventoryMovement, MoldingSampleRequisition
    from app.schemas.molding_sample import MoldingSampleDetailResponse
    from app.services.molding_sample_monthly_excel import build_production_month_workbook

    order_id = "BP-RECEIPT-ONLY"
    record = MoldingSampleDetailResponse.model_validate({
        "order": vars(_sample_order(id=order_id)), "can_view_cost": False,
        "items": [{"id": "item-01", "order_id": order_id, "mold_id": "00042", "receipt_no": "LL-042"}],
    })
    receipt = MoldingSampleRequisition(id="r1", order_id=order_id, factory_id="huakang-a", req_number="LL-042",
        date="2026-08-01", material="ABS", requested_weight_kg=3, applicant="申请人", status="已出库",
        inventory_batch_no="B-01", issued_at="2026-08-02", notes="")
    book = load_workbook(BytesIO(build_production_month_workbook([record], "华康A", "2026-07", requisitions=[receipt])))
    assert "出库流水" not in book.sheetnames
    warehouse = book["领料记录"]
    assert "流水净出库（kg）" not in [c.value for c in warehouse[3]]
    assert (warehouse["C4"].value, warehouse["E4"].value, warehouse["H4"].value) == ("已关联模具", "00042", 3)
    assert book["逐模对账"]["H4"].hyperlink.location == "'领料记录'!A4"
    assert book["逐模对账"]["F4"].value is None
    mold_columns = {c.value: c.column for c in book["逐模对账"][3]}
    assert book["逐模对账"].cell(4, mold_columns["本模申请（kg）"]).value == 3
    assert "本模净出库（kg）" not in mold_columns
    issue = MoldingSampleInventoryMovement(requisition_id=receipt.id, movement_type="出库扣减", quantity_kg=-3,
                                          material="ABS", batch_no="B-01", created_at="2026-08-02")
    issued = load_workbook(BytesIO(build_production_month_workbook([record], "华康A", "2026-07",
                                                                   requisitions=[receipt], movements=[issue])))
    mold = issued["逐模对账"]
    by_label = dict(zip([cell.value for cell in mold[3]], [cell.value for cell in mold[4]]))
    assert by_label["本模净出库（kg）"] == 3 and by_label["回填实领（kg）"] is None


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
