from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from app.api import customer_order as customer_order_api
from app.services import customer_order_huakang_a as service


def _schedule_bytes() -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "360客排期表"
    worksheet.cell(1, 1, "华康A 360客排期")
    headers = {
        4: "入单日期",
        5: "正单合同号",
        6: "产品货号",
        8: "产品名称",
        10: "PO数量",
        12: "验货日期",
        13: "走货期 FCD",
        20: "第三方客户 PO NO#",
        21: "跟单",
        22: "Customer Release No.",
        23: "外箱装箱数",
        24: "总箱数",
        35: "MS Container Type (FCL/LCL)",
        37: "Port of Discharge",
        40: "走货方式",
    }
    for column, value in headers.items():
        worksheet.cell(3, column, value)
    worksheet.cell(5, 5, "OLD-HISTORY")
    worksheet.cell(5, 6, "OLD-ITEM")
    worksheet.cell(5, 8, "旧产品")
    worksheet.cell(5, 10, 1)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _parsed_record(file_name: str = "RL-100-1.pdf") -> dict[str, object]:
    return {
        "file_name": file_name,
        "contract_no": "RL-100-1",
        "release_type": "FIRM",
        "revision": 2,
        "revision_date": "03-Jul-2026",
        "customer_po": "PO-360-1",
        "customer_release": "CR-1",
        "contact": "Amy",
        "container_type": "FCL",
        "item_no": "60350",
        "description": "ThreeSixty Toy",
        "quantity": 240,
        "master_carton_qty": 12,
        "planned_inspection_date": "2026-07-10",
        "factory_commit_date": "2026-07-17",
        "transportation_mode": "SEA",
        "port": "FELIXSTOWE",
        "parse_ok": True,
        "parse_warnings": [],
    }


def test_huakang_a_360_registry_coexists_with_huaxing_360() -> None:
    assert set(service.HUAKANG_A_CUSTOMER_MAPPINGS) == {"360"}
    assert customer_order_api.CUSTOMER_FACTORY_IDS["360"] == "huaxing"
    assert customer_order_api.CUSTOMER_FACTORY_OPTIONS["360"] == (
        "huaxing",
        "huakang-a",
    )
    assert customer_order_api._get_mapped_customer_spec(
        "360", "huaxing"
    ).target_template == "HUAXING_360_SCHEDULE_APPEND_V2"
    assert customer_order_api._get_mapped_customer_spec(
        "360", "huakang-a"
    ).target_template == "HUAKANG_A_360_SCHEDULE_APPEND_V2"

    with pytest.raises(service.HuakangACustomerOrderError, match="只属于华康A厂区"):
        service.create_huakang_a_customer_preview(
            customer_code="360",
            factory_id="huakang-c",
            received_date="2026-08-03",
            po_files=[("RL-100-1.pdf", b"pdf")],
            schedule_file_name="360排期.xlsx",
            schedule_content=_schedule_bytes(),
        )


def test_legacy_parser_extracts_threesixty_release_fields(tmp_path: Path) -> None:
    source = tmp_path / "RL-100-1.txt"
    source.write_text("placeholder", encoding="utf-8")
    text = """
PURCHASE ORDER RELEASE (FIRM) RL-100-1
REVISION 2
Revision Date : 03-Jul-2026
Customer PO Number : PO-360-1
Customer Release No. : CR-1
Our Contact : Amy
MS Container Type (FCL/LCL) : FCL
1 60350 Each 240
ThreeSixty Toy
Master Carton Qty : 12
Planned Inspection Date : 10-Jul-2026 Factory Commit Date : 17-Jul-2026
Transportation Mode : SEA
Port of Discharge : FELIXSTOWE
"""

    parsed = service.schedule_parser._parse_po_text(source, text, 1, tmp_path)

    assert parsed["parse_ok"] is True
    assert parsed["contract_no"] == "RL-100-1"
    assert parsed["revision"] == 2
    assert parsed["item_no"] == "60350"
    assert parsed["quantity"] == 240
    assert parsed["master_carton_qty"] == 12
    assert parsed["planned_inspection_date"] == "2026-07-10"
    assert parsed["factory_commit_date"] == "2026-07-17"


def test_huakang_a_360_preview_and_export_follow_legacy_mapping(monkeypatch) -> None:
    monkeypatch.setattr(
        service.schedule_parser,
        "parse_po_file",
        lambda path, _root: _parsed_record(Path(path).name),
    )
    schedule = _schedule_bytes()
    preview = service.create_huakang_a_customer_preview(
        customer_code="360",
        factory_id="huakang-a",
        received_date="2026-08-03",
        po_files=[("RL-100-1.pdf", b"pdf")],
        schedule_file_name="2026年华康A 360排期.xlsx",
        schedule_content=schedule,
    )

    row = preview["rows"][0]
    assert preview["factory_id"] == "huakang-a"
    assert preview["preview_schema_version"] == service.PREVIEW_SCHEMA_VERSION
    assert row["contract_no"] == "RL-100-1"
    assert row["po_no"] == "PO-360-1"
    assert row["product_no"] == "60350"
    assert row["product_name_en"] == "ThreeSixty Toy"
    assert row["carton_count"] == "20"
    assert row["line_q"] == "2026-07-10"
    assert row["requested_ship_date"] == "2026-07-17"
    assert row["status"] == "valid"

    output, file_name, exported_preview = service.export_huakang_a_customer_schedule(
        customer_code="360",
        factory_id="huakang-a",
        received_date="2026-08-03",
        po_files=[("RL-100-1.pdf", b"pdf")],
        schedule_file_name="2026年华康A 360排期.xlsx",
        schedule_content=schedule,
    )
    workbook = openpyxl.load_workbook(BytesIO(output), data_only=False)
    try:
        assert workbook.sheetnames == ["360客排期表"]
        worksheet = workbook["360客排期表"]
        assert worksheet.cell(5, 5).value == "OLD-HISTORY"
        assert worksheet.cell(6, 4).value == datetime(2026, 7, 3)
        assert worksheet.cell(6, 5).value == "RL-100-1"
        assert worksheet.cell(6, 6).value == "60350"
        assert worksheet.cell(6, 10).value == 240
        assert worksheet.cell(6, 24).value == 20
    finally:
        workbook.close()
    assert file_name == preview["output_file_name"]
    assert exported_preview["summary"] == {
        "total": 1,
        "valid": 1,
        "warning": 0,
        "blocked": 0,
    }


def test_missing_fcd_warns_but_missing_key_fields_block(monkeypatch) -> None:
    missing_fcd = _parsed_record()
    missing_fcd["factory_commit_date"] = ""
    missing_fcd["parse_warnings"] = ["未识别 FCD"]
    monkeypatch.setattr(
        service.schedule_parser,
        "parse_po_file",
        lambda _path, _root: missing_fcd,
    )
    preview = service.create_huakang_a_customer_preview(
        customer_code="360",
        factory_id="huakang-a",
        received_date="2026-08-03",
        po_files=[("RL-100-1.pdf", b"pdf")],
        schedule_file_name="360排期.xlsx",
        schedule_content=_schedule_bytes(),
    )
    assert preview["rows"][0]["status"] == "warning"

    missing_contract = dict(missing_fcd, contract_no="", parse_ok=False)
    missing_contract["parse_warnings"] = ["未识别合同号"]
    monkeypatch.setattr(
        service.schedule_parser,
        "parse_po_file",
        lambda _path, _root: missing_contract,
    )
    blocked = service.create_huakang_a_customer_preview(
        customer_code="360",
        factory_id="huakang-a",
        received_date="2026-08-03",
        po_files=[("bad.pdf", b"pdf")],
        schedule_file_name="360排期.xlsx",
        schedule_content=_schedule_bytes(),
    )
    assert blocked["rows"][0]["status"] == "blocked"
