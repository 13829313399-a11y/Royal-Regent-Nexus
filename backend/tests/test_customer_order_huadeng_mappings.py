from __future__ import annotations

from datetime import datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest
import pytesseract
from openpyxl.utils import get_column_letter

from app.api.customer_order import CUSTOMER_FACTORY_IDS
from app.services import customer_order_huadeng as service
from app.services.huadeng_order_legacy import common_pdf_text, simba_po_parser


def _workbook_bytes(sheet_name: str, headers: dict[int, str], row: dict[int, object]) -> bytes:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = sheet_name
    for column, value in headers.items():
        worksheet.cell(1, column, value)
    for column, value in row.items():
        worksheet.cell(2, column, value)
    for column in range(1, max(headers, default=1) + 1):
        worksheet.column_dimensions[get_column_letter(column)].width = 16
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_huadeng_mapping_registry_is_factory_scoped() -> None:
    assert set(service.HUADENG_CUSTOMER_MAPPINGS) == {
        "casdon", "jakks", "simba", "spin", "spin-master",
    }
    assert {
        code: CUSTOMER_FACTORY_IDS[code]
        for code in service.HUADENG_CUSTOMER_MAPPINGS
    } == {
        "casdon": "huadeng",
        "jakks": "huadeng",
        "simba": "huadeng",
        "spin": "huadeng",
        "spin-master": "huadeng",
    }
    with pytest.raises(service.HuadengCustomerOrderError, match="只属于华登厂区"):
        service.create_huadeng_customer_preview(
            customer_code="casdon",
            factory_id="huaxing",
            received_date="2026-08-03",
            po_files=[("casdon.pdf", b"pdf")],
            schedule_file_name="Casdon排期.xlsx",
            schedule_content=b"schedule",
        )


def test_revision_dedupe_prefers_latest_and_more_complete_order() -> None:
    original = {
        "po_number": "PO-1",
        "filename": "PO-1.pdf",
        "po_date": "2026-07-01",
        "lines": [{"item_code": "A1", "qty": 10}],
    }
    revision = {
        "po_number": "PO-1",
        "filename": "PO-1 REV2.pdf",
        "po_date": "2026-07-02",
        "ship_date": "2026-08-10",
        "lines": [{"item_code": "A1", "qty": 20, "unit_price": 1, "total_usd": 20}],
    }
    kept, warnings = service._dedupe_revision_orders(
        [original, revision], quality_fields=("po_date", "ship_date"),
    )
    assert kept == [revision]
    assert "保留 PO-1 REV2.pdf" in warnings[0]


def test_casdon_preview_and_export_use_received_date_and_seven_day_rule(monkeypatch) -> None:
    headers = {
        2: "来单日期", 4: "合同联系人", 5: "客户PO", 6: "合同号", 7: "客名",
        8: "版本", 9: "货号", 10: "产品名称", 11: "数量", 13: "外装箱",
        27: "验货期", 29: "PO走货期", 32: "单价/港币", 33: "单价/美金",
        34: "总货价/港币", 35: "总货价/美金", 37: "英文品名", 47: "走货国家",
    }
    schedule = _workbook_bytes(
        "Casdon 排货表-总",
        headers,
        {6: "OLD", 7: "CASDON UK", 8: "A", 9: "1234(A)", 10: "玩具厨房", 11: 12, 37: "Toy Kitchen"},
    )

    def parse(_self, _path: str):
        return {
            "po_number": "8395",
            "po_date": "2026-07-30",
            "ship_date": "2026-08-10",
            "customer": "CASDON UK",
            "customer_po_header": "UK-PO-1",
            "version": "A",
            "lines": [{
                "line_no": "1", "item_code": "1234", "description_en": "Toy Kitchen",
                "qty": 24, "unit": "PCS", "unit_price": 10, "total_usd": 240,
                "is_charge": False,
            }],
            "raw_text": "",
        }

    monkeypatch.setattr(service.casdon_po_parser.CasdonPOParser, "parse", parse)
    preview = service.create_huadeng_customer_preview(
        customer_code="casdon",
        factory_id="huadeng",
        received_date="2026-08-03",
        po_files=[("PO 8395.pdf", b"pdf")],
        schedule_file_name="2026年Casdon排期.xlsx",
        schedule_content=schedule,
    )
    row = preview["rows"][0]
    assert row["received_date"] == "2026-08-03"
    assert row["contract_no"] == "8395"
    assert row["product_name_zh"] == "玩具厨房"
    assert row["line_q"] == "2026-08-03"
    assert row["requested_ship_date"] == "2026-08-10"
    assert row["unit_price_hkd"] == "77.5"
    assert row["amount_hkd"] == "1860"

    output, file_name, exported_preview = service.export_huadeng_customer_schedule(
        customer_code="casdon",
        factory_id="huadeng",
        received_date="2026-08-03",
        po_files=[("PO 8395.pdf", b"pdf")],
        schedule_file_name="2026年Casdon排期.xlsx",
        schedule_content=schedule,
    )
    workbook = openpyxl.load_workbook(BytesIO(output), data_only=False)
    try:
        assert workbook.sheetnames == ["Casdon 排货表-总"]
        assert workbook["Casdon 排货表-总"].cell(2, 6).value == "OLD"
        assert workbook["Casdon 排货表-总"].cell(3, 6).value == "8395"
        assert workbook["Casdon 排货表-总"].cell(3, 2).value == datetime(2026, 8, 3)
    finally:
        workbook.close()
    assert file_name == preview["output_file_name"]
    assert exported_preview["summary"]["total"] == 1


def test_jakks_blocks_change_orders_and_dedupes_batch(monkeypatch) -> None:
    monkeypatch.setattr(
        service.jakks_schedule,
        "load_dataset",
        lambda _path: {"records": [{"sku": "J-1", "product": "标准公仔", "contact": "Amy", "contract_no": "C1"}]},
    )

    def parse_po(_path):
        return {
            "contract_no": "C1",
            "customer_po": "PO-1",
            "customer": "JAKKS",
            "order_date": "2026-08-01",
            "lines": [{
                "item_no": "J-1", "product_name": "PO品名", "po_description": "Toy Figure",
                "quantity": 100, "unit": "PCS", "unit_price_usd": 2, "total_usd": 200,
                "ship_date": "2026-09-01", "special_note": "",
            }],
            "warnings": [],
        }

    monkeypatch.setattr(service.jakks_po_parser, "parse_po", parse_po)
    prepared = service._prepare_jakks(
        [("C1-CXL.pdf", b"cancel"), ("C1.pdf", b"one"), ("C1-copy.pdf", b"two")],
        "2026年Jakks排期.xlsx",
        b"schedule",
    )
    assert len(prepared.records) == 1
    assert prepared.records[0]["product_name"] == "标准公仔"
    assert prepared.records[0]["contact"] == "Amy"
    assert any("CXL/SUP" in warning for warning in prepared.warnings)
    assert any("完全重复" in warning for warning in prepared.warnings)


def test_jakks_native_contract_pdf_accepts_plain_item_and_trailing_usd(
    monkeypatch,
    tmp_path: Path,
) -> None:
    contract_text = """CONTRACT
JAKKS PACIFIC (H.K. ) LIMITED
Contract #: 811626
Printed Date: 11-Aug-2026 Order Date: 11-Aug-2026
Customer PO: 236856
Confirmation No: 67078 UNITED STATES
Ultimate Consignee Name: JAKKS PACIFIC, INC.
ITEM NUMBER DESCRIPTION QUANTITY PRICE EXTENDED PRICE
10022J CHARMING CUPID CUTIE PLUSH 5L 5L 100 3.0670 306.70 USD
Customer Item No.: 10022J 25 CA
UPC: 199460000214 Outer Pack: 4
Stock #: 10022J
Country of Origin: CHINA Line#: 1.000 Request Date: 13-Oct-2026
NOTES: OPEN WINDOW BOX
TOTAL USD 306.70
"""
    monkeypatch.setattr(
        service.jakks_po_parser,
        "extract_text",
        lambda _path: (contract_text, False),
    )

    parsed = service.jakks_po_parser.parse_po(tmp_path / "JDCUS-SI67078-OK811626-HE.pdf")

    assert parsed["contract_no"] == "811626"
    assert parsed["order_date"] == "2026-08-11"
    assert parsed["customer_po"] == "236856"
    assert parsed["confirmation_no"] == "67078"
    assert parsed["country"] == "UNITED STATES"
    assert parsed["customer"] == "JAKKS PACIFIC, INC. UNITED STATES"
    assert parsed["source_format"] == "pdf"
    assert parsed["used_ocr"] is False
    assert len(parsed["lines"]) == 1
    line = parsed["lines"][0]
    assert line == {
        "item_no": "10022J",
        "product_name": "CHARMING CUPID CUTIE PLUSH 5L 5L",
        "po_description": "CHARMING CUPID CUTIE PLUSH 5L 5L",
        "product_name_source": "PO英文品名",
        "quantity": 100,
        "unit": "PCS",
        "inner_pack": "",
        "outer_pack": 4,
        "cartons": 25,
        "unit_price_usd": 3.067,
        "total_usd": 306.7,
        "ship_date": "2026-10-13",
        "special_note": "OPEN WINDOW BOX",
    }
    assert any("标准 CONTRACT PDF" in warning for warning in parsed["warnings"])


def test_jakks_export_overwrites_copied_po_field_formula(tmp_path: Path) -> None:
    schedule = _workbook_bytes(
        "26-Jakks排货表",
        {1: "来单日期", 5: "客户PO", 6: "合同号", 7: "客名", 9: "货号", 10: "产品名称", 11: "数量"},
        {5: "OLD", 6: "OLD", 7: "JAKKS", 9: "J-OLD", 10: "旧品名", 11: "=5000-4999"},
    )
    line = {
        "order_date": "2026-08-18", "customer_po": "236856", "contract_no": "811626",
        "customer": "JAKKS PACIFIC, INC. UNITED STATES", "item_no": "10022J",
        "product_name": "CHARMING CUPID CUTIE PLUSH 5L 5L", "quantity": 100,
        "unit": "PCS", "unit_price_usd": 3.067, "total_usd": 306.7,
        "source_file": "JDCUS-SI67078-OK811626-HE.pdf",
    }
    output = tmp_path / "jakks-formula-override.xlsx"

    service._export_prepared(
        customer_code="jakks",
        prepared=service.PreparedBatch(
            [line], [], "26-Jakks排货表总 Ai",
            export_payload={"filename": "Jakks批量", "lines": [line]},
        ),
        schedule_file_name="2026年Jakks排货表.xlsx",
        schedule_content=schedule,
        output_path=output,
    )

    workbook = openpyxl.load_workbook(output, data_only=False)
    try:
        worksheet = workbook["26-Jakks排货表"]
        assert worksheet.cell(3, 6).value == "811626"
        assert worksheet.cell(3, 9).value == "10022J"
        assert worksheet.cell(3, 11).value == 100
    finally:
        workbook.close()


def test_simba_prefers_same_name_excel_and_inherits_schedule(monkeypatch) -> None:
    parsed_names: list[str] = []
    monkeypatch.setattr(
        service.simba_schedule,
        "read_schedule",
        lambda *_args, **_kwargs: {"sheet": "Simba排期", "records": [{"contract_no": "S1", "item_no": "A1"}]},
    )

    def parse_po_file(_content, *, filename: str):
        parsed_names.append(filename)
        return {
            "filename": filename,
            "rows": [{
                "contract_no": "S1", "customer_po": "PO-S1", "item_no": "A1",
                "quantity": 120, "outer_pack": 12, "po_ship_date": "2026-09-01",
                "customer": "SIMBA", "contact": "May", "source_sheet": "转换PO",
            }],
            "warnings": [],
        }

    monkeypatch.setattr(service.simba_po_parser, "parse_po_file", parse_po_file)
    monkeypatch.setattr(
        service.simba_schedule,
        "enrich_rows_from_schedule",
        lambda rows, _schedule: {
            "product_names_applied": 1,
            "exact_fields_applied": 2,
            "product_name_conflicts": [],
        },
    )
    prepared = service._prepare_simba(
        [("Release-S1.pdf", b"pdf"), ("Release-S1.xlsx", b"xlsx")],
        "2026年Simba排期.xlsx",
        b"schedule",
        "2026-08-03",
    )
    assert parsed_names == ["Release-S1.xlsx"]
    assert len(prepared.records) == 1
    assert prepared.records[0]["order_date"] == "2026-08-03"
    assert any("优先采用 Excel" in warning for warning in prepared.warnings)


def test_simba_scanned_pdf_uses_shared_tesseract_configuration(monkeypatch) -> None:
    class FakePage:
        def extract_text(self, **_kwargs):
            return ""

        def to_image(self, **_kwargs):
            return type("Rendered", (), {"original": object()})()

    class FakePdf:
        pages = [FakePage()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    configured: list[object] = []
    monkeypatch.setattr(common_pdf_text.pdfplumber, "open", lambda _source: FakePdf())
    monkeypatch.setattr(
        common_pdf_text,
        "configure_tesseract",
        lambda module: (configured.append(module) or (r"C:\Tesseract\tesseract.exe", "eng")),
    )
    monkeypatch.setattr(
        pytesseract,
        "image_to_string",
        lambda _image, *, lang, config: f"Release Order {lang} {config}",
    )

    text, pages, used_ocr = common_pdf_text.extract_pdf_text(b"scanned")

    assert configured == [pytesseract]
    assert text == "Release Order eng --psm 6"
    assert pages == 1
    assert used_ocr is True


def test_simba_release_parser_tolerates_ocr_reference_and_zero_packing() -> None:
    text = """
Release Order
Reference: $C700144914/ 800
Date of creation: 27.APR.2026
Mat. No.: 109491008
SPB Feature Plush, 30cm
Packing: OPC / 12PC Volume: 2.568 FT3 - 0.073 M3
Carton dimension: 59.500 x 26.000 x 47.000 CM
Quantity Master Contract No. PO Contract No. Unit Price Delivery Date
264 PC 500055145/ 10 300493420/ 10 40.45 HKD 09.JUN.2026
Total CTN: 22
Port of discharge: MELBOURNE
"""

    rows = simba_po_parser.parse_release_order_text(text, "RR_700144914.pdf")

    assert rows is not None
    assert len(rows) == 1
    assert rows[0]["contract_no"] == "700144914/800"
    assert rows[0]["item_no"] == "109491008"
    assert rows[0]["inner_pack"] == 0
    assert rows[0]["outer_pack"] == 12
    assert rows[0]["cartons"] == 22
    assert rows[0]["quantity"] == 264


def test_simba_empty_batch_reports_each_file_parser_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        service.simba_schedule,
        "read_schedule",
        lambda *_args, **_kwargs: {"sheet": "Simba排期", "records": []},
    )
    monkeypatch.setattr(
        service.simba_po_parser,
        "parse_po_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("OCR未配置")),
    )

    with pytest.raises(
        service.HuadengCustomerOrderError,
        match="RR700147106.pdf.*OCR未配置",
    ):
        service._prepare_simba(
            [("RR700147106.pdf", b"pdf")],
            "仙霸排货表.xlsx",
            b"schedule",
            "2026-08-12",
        )


def test_simba_export_adds_one_total_row_after_each_item_group(tmp_path: Path) -> None:
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = "2026年排货表"
    headers = {
        2: "来单日期",
        5: "客户PO",
        6: "合同号",
        7: "客名",
        9: "货号",
        10: "产品名称",
        11: "数量",
        13: "外装箱",
        14: "总箱数",
    }
    for column, value in headers.items():
        worksheet.cell(1, column, value)
    for column, value in {
        2: datetime(2026, 7, 1),
        5: "PO-OLD",
        6: "OLD/100",
        7: "SIMBA",
        9: "ITEM-OLD",
        10: "旧产品",
        11: 10,
        13: 2,
        14: "=K2/M2",
    }.items():
        worksheet.cell(2, column, value)
    worksheet["J3"] = "合计："
    worksheet["K3"] = "=SUM(K2:K2)"
    worksheet["J3"].fill = openpyxl.styles.PatternFill("solid", fgColor="FFF2CC")
    worksheet["K3"].fill = openpyxl.styles.PatternFill("solid", fgColor="FFF2CC")
    source = BytesIO()
    workbook.save(source)
    workbook.close()
    output_path = tmp_path / "Simba逐款合计.xlsx"

    records = [
        {
            "order_date": "2026-08-14",
            "customer_po": "PO-A1",
            "contract_no": "A/100",
            "customer": "SIMBA",
            "item_no": "ITEM-A",
            "product_name": "产品A",
            "quantity": 12,
            "outer_pack": 3,
            "cartons": 4,
        },
        {
            "order_date": "2026-08-14",
            "customer_po": "PO-A2",
            "contract_no": "A/200",
            "customer": "SIMBA",
            "item_no": "ITEM-A",
            "product_name": "产品A",
            "quantity": 18,
            "outer_pack": 3,
            "cartons": 6,
        },
        {
            "order_date": "2026-08-14",
            "customer_po": "PO-B1",
            "contract_no": "B/100",
            "customer": "SIMBA",
            "item_no": "ITEM-B",
            "product_name": "产品B",
            "quantity": 20,
            "outer_pack": 4,
            "cartons": 5,
        },
    ]
    service._export_prepared(
        customer_code="simba",
        prepared=service.PreparedBatch(records, [], "2026年排货表"),
        schedule_file_name="Simba排期.xlsx",
        schedule_content=source.getvalue(),
        output_path=output_path,
    )

    rendered = openpyxl.load_workbook(output_path, data_only=False)
    worksheet = rendered["2026年排货表"]
    assert worksheet["K3"].value == "=SUM(K2:K2)"
    assert worksheet["I4"].value == worksheet["I5"].value == "ITEM-A"
    assert worksheet["J6"].value == "合计："
    assert worksheet["K6"].value == "=SUM(K4:K5)"
    assert worksheet["I7"].value == "ITEM-B"
    assert worksheet["J8"].value == "合计："
    assert worksheet["K8"].value == "=SUM(K7:K7)"
    assert worksheet["J6"].fill.fgColor.rgb == worksheet["J3"].fill.fgColor.rgb
    rendered.close()


def test_spin_master_uses_independent_schedule_and_composite_dedupe(monkeypatch) -> None:
    monkeypatch.setattr(
        service.spin_master_parser,
        "validate_schedule_file",
        lambda _path: {"sheet": "SPIN排期", "rows": [{"contract_no": "OLD"}]},
    )
    monkeypatch.setattr(
        service.spin_master_parser,
        "parse_po_file",
        lambda path: {"source": str(path), "items": [{"line_no": 10}]},
    )
    monkeypatch.setattr(
        service.spin_master_new_order_writer,
        "_records",
        lambda order: [{
            "customer_po": "PO-SM", "contract_no": "45001/10", "customer": "SPIN MASTER",
            "item_no": "GML/100/200", "product_name": "GML4pkSLD", "english_name": "GML4pkSLD",
            "quantity": 100, "outer_pack": 4, "cartons": 25, "ship_date": "2026-09-01",
            "unit_price_usd": 1, "total_usd": 100, "unit_price_hkd": 7.75, "total_hkd": 775,
            "source_file": order["source"],
        }],
    )
    prepared = service._prepare_spin_master(
        [("SM-1.pdf", b"one"), ("SM-1-copy.pdf", b"two")],
        "2026年SpinMaster排期.xlsx",
        b"schedule",
    )
    assert prepared.sheet_name == "SPIN排期"
    assert len(prepared.records) == 1
    assert any("完全重复" in warning for warning in prepared.warnings)


def test_spin_and_spin_master_specs_remain_separate() -> None:
    spin = service.get_huadeng_customer_mapping("spin")
    spin_master = service.get_huadeng_customer_mapping("spin-master")
    assert spin.target_template == "HUADENG_SPIN_SCHEDULE_APPEND_V2"
    assert spin_master.target_template == "HUADENG_SPIN_MASTER_SCHEDULE_APPEND_V2"
    assert spin.schedule_extensions == (".xlsx",)
    assert spin_master.schedule_extensions == (".xls", ".xlsx")


def test_spin_preview_uses_spin_schedule_family_and_keeps_manual_dates_blank(monkeypatch) -> None:
    schedule = _workbook_bytes(
        service.spin_schedule.MASTER_SHEET,
        {2: "来单期", 4: "联系人", 5: "客PO", 6: "合同号", 7: "客名", 8: "版本", 9: "货号", 10: "产品名称", 11: "数量", 13: "外箱", 27: "验货期", 28: "PO走货期", 36: "英文品名"},
        {5: "OLD", 6: "OLD/10", 7: "SPIN MASTER", 9: "1111/123456/7890/9999-10", 10: "Spin标准品名", 11: 100, 13: 4, 36: "Spin Product"},
    )

    def parse(_self, _path: str):
        return {
            "po_number": "45000001",
            "po_date": "2026-08-01",
            "contact": "Karen Sun",
            "customer": "SPIN MASTER",
            "lines": [{
                "line_no": "10", "qty": 100, "unit": "PC", "material_number": "123456",
                "description_en": "GML4pkSLD Spin Product", "sales_material": "7890",
                "material_group": "1111", "unit_price": 1.5, "total_usd": 150,
                "ship_date": "2026-09-01", "sales_order": "9999", "line_item": "10",
                "customer": "SPIN MASTER", "customer_po": "PO-SPIN",
                "item_key": "1111/123456/7890",
            }],
            "raw_text": "",
        }

    monkeypatch.setattr(service.spin_po_parser.SpinPOParser, "parse", parse)
    preview = service.create_huadeng_customer_preview(
        customer_code="spin",
        factory_id="huadeng",
        received_date="2026-08-03",
        po_files=[("Spin PO.pdf", b"pdf")],
        schedule_file_name="2026年Spin排期.xlsx",
        schedule_content=schedule,
    )
    row = preview["rows"][0]
    assert row["target_template"] == "HUADENG_SPIN_SCHEDULE_APPEND_V2"
    assert row["contract_no"] == "45000001/10"
    assert row["product_name_zh"] == "Spin标准品名"
    assert row["units_per_carton"] == "4"
    assert row["line_q"] == ""
    assert row["requested_ship_date"] == "2026-09-01"


def test_remaining_huadeng_exporters_append_to_complete_schedule_workbooks(tmp_path: Path) -> None:
    jakks_template = _workbook_bytes(
        "26-Jakks排货表总 Ai",
        {1: "来单日期", 5: "客户PO", 6: "合同号", 7: "客名", 9: "货号", 10: "产品名称", 11: "数量"},
        {5: "OLD", 6: "OLD", 7: "JAKKS", 9: "J-OLD", 10: "旧品名", 11: 1},
    )
    jakks_line = {
        "order_date": "2026-08-03", "customer_po": "PO-J1", "contract_no": "J1",
        "customer": "JAKKS", "item_no": "J-1", "product_name": "Jakks产品", "quantity": 20,
        "unit": "PCS", "unit_price_usd": 1, "total_usd": 20, "source_file": "J1.pdf",
    }
    jakks_output = tmp_path / "jakks-new.xlsx"
    service._export_prepared(
        customer_code="jakks",
        prepared=service.PreparedBatch(
            [jakks_line], [], "26-Jakks排货表总 Ai",
            export_payload={"filename": "Jakks批量", "lines": [jakks_line]},
        ),
        schedule_file_name="Jakks排期.xlsx",
        schedule_content=jakks_template,
        output_path=jakks_output,
    )

    simba_template = _workbook_bytes(
        "Simba排期",
        {2: "来单日期", 5: "客户PO", 6: "合同号", 7: "客名", 9: "货号", 10: "产品名称", 11: "数量"},
        {5: "OLD", 6: "OLD", 7: "SIMBA", 9: "S-OLD", 10: "旧品名", 11: 1},
    )
    simba_output = tmp_path / "simba-new.xlsx"
    service._export_prepared(
        customer_code="simba",
        prepared=service.PreparedBatch([{
            "order_date": "2026-08-03", "customer_po": "PO-S1", "contract_no": "S1",
            "customer": "SIMBA", "item_no": "S-1", "product_name": "Simba产品", "quantity": 24,
            "outer_pack": 12, "cartons": 2, "po_ship_date": "2026-09-01", "source_file": "S1.xlsx",
        }], [], "Simba排期"),
        schedule_file_name="Simba排期.xlsx",
        schedule_content=simba_template,
        output_path=simba_output,
    )

    spin_master_template = _workbook_bytes(
        "SPIN排期",
        {1: "来单期", 4: "客PO", 5: "合同号", 6: "客名", 8: "货号/SI", 9: "产品名称", 10: "数量"},
        {4: "OLD", 5: "OLD", 6: "SPIN MASTER", 8: "SM-OLD", 9: "旧品名", 10: 1},
    )
    spin_master_output = tmp_path / "spin-master-new.xlsx"
    service._export_prepared(
        customer_code="spin-master",
        prepared=service.PreparedBatch([{
            "order_date": "2026-08-03", "customer_po": "PO-SM", "contract_no": "45001/10",
            "customer": "SPIN MASTER", "item_no": "GML/100/200", "product_name": "Spin产品",
            "english_name": "Spin Product", "quantity": 100, "outer_pack": 4, "cartons": 25,
            "ship_date": "2026-09-01", "source_file": "SM.pdf",
        }], [], "SPIN排期"),
        schedule_file_name="SpinMaster排期.xlsx",
        schedule_content=spin_master_template,
        output_path=spin_master_output,
    )

    spin_template = _workbook_bytes(
        service.spin_schedule.MASTER_SHEET,
        {5: "客PO", 6: "合同号", 7: "客名", 9: "货号", 10: "产品名称", 11: "数量"},
        {5: "OLD", 6: "OLD", 7: "SPIN MASTER", 9: "SPIN-OLD", 10: "旧品名", 11: 1},
    )
    spin_output = tmp_path / "spin-new.xlsx"
    spin_values = {
        service.spin_schedule.COL["customer_po"]: "PO-SPIN",
        service.spin_schedule.COL["contract"]: "45001/10",
        service.spin_schedule.COL["customer"]: "SPIN MASTER",
        service.spin_schedule.COL["item"]: "100/200/300",
        service.spin_schedule.COL["cn_name"]: "Spin产品",
        service.spin_schedule.COL["qty"]: 100,
    }
    service._export_prepared(
        customer_code="spin",
        prepared=service.PreparedBatch(
            [], [], service.spin_schedule.MASTER_SHEET,
            legacy_rows=[spin_values], inheritance={},
        ),
        schedule_file_name="Spin排期.xlsx",
        schedule_content=spin_template,
        output_path=spin_output,
    )

    expected = (
        (jakks_output, "26-Jakks排货表总 Ai", 6, "J1"),
        (simba_output, "Simba排期", 6, "S1"),
        (spin_master_output, "SPIN排期", 5, "45001/10"),
        (spin_output, service.spin_schedule.MASTER_SHEET, 6, "45001/10"),
    )
    for output, sheet_name, contract_column, new_contract in expected:
        assert output.exists()
        workbook = openpyxl.load_workbook(output, data_only=False)
        try:
            assert workbook.sheetnames == [sheet_name]
            worksheet = workbook[sheet_name]
            assert worksheet.cell(2, contract_column).value == "OLD"
            assert worksheet.cell(3, contract_column).value == new_contract
        finally:
            workbook.close()
