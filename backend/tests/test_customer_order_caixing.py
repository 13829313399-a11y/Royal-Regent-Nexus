from __future__ import annotations

from io import BytesIO

import openpyxl
import pytest
from fastapi import HTTPException

from app.api.customer_order import _ensure_customer_factory
from app.services import customer_order_caixing as service
from app.services.customer_order_buzzbee import _decrypt_schedule


PLAYMATES_PO_TEXT = """
Page: 1 of 8
OG-1931815 DATE: 2026/01/23
TO: ROYAL REGENT PRODUCTS (H.K.) LIMITED
CUSTOMER: IMPORTS DRAGON-CAN                                      OUR CONF NO: SG -1926247
PRODUCT NO DESCRIPTION REF C.O. U/M ORDER QTY. UNIT PRICE AMOUNT
HKD HKD
58120E8 WINX CLUB FAIRY WINGS ASST. / PRODUCT LINE: WINX CLUB
Customer Item no.: 58120P
MIX: 58120E8-05
DELIVERY DATE: 2026/04/08 CHN PC
58121E8             WINX CLUB BLOOM FAIRY WINGS ROLE PLAY 300 23.2700 6,981.00
58122E8             WINX CLUB STELLA FAIRY WINGS ROLE PLAY 300 23.2700 6,981.00
ASSORTMENT : 58121E8             2
58122E8             2
8 PCS/CTN
TOTAL : 13,962.00
USE US STANDARD PACKAGING AND US STANDARD INSTRUCTION SHEET WHENEVER APPLICABLE.
"""

SINGLE_PRODUCT_TEXT = """
Page: 1 of 8
OE-1931878 DATE: 2026/02/12
CUSTOMER: PLAYMATES-USA                                        OUR CONF NO: SE -1926304
PRODUCT NO DESCRIPTION REF C.O. U/M ORDER QTY. UNIT PRICE AMOUNT
68695 ULTIMATE THUNDER MEGAZORD / PRODUCT LINE: POWER RANGERS
DELIVERY DATE: 2026/05/13 CHN PC 3,000 0.0000 0.00
TOTAL : 0.00
"""


def build_caixing_schedule() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "采购订单"
    for column, header in enumerate(service.EXPORT_COLUMNS, start=1):
        sheet.cell(1, column).value = header
    sheet["A2"] = "旧数据"
    sheet["B2"] = "SC-OLD"
    sheet["C2"] = "OG-OLD"
    workbook.create_sheet("说明")
    workbook.active = 0
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_caixing_parser_reproduces_playmates_header_and_product_mapping(monkeypatch):
    monkeypatch.setattr(service, "_extract_pdf_text", lambda _content: PLAYMATES_PO_TEXT)

    rows = service.parse_caixing_pdf("1931815.pdf", b"%PDF synthetic")

    assert len(rows) == 2
    assert rows[0].source_date == "2026/01/23"
    assert rows[0].po_no == "OG-1931815"
    assert rows[0].contract_no == "SG-1926247"
    assert rows[0].customer_name == "IMPORTS DRAGON-CAN"
    assert rows[0].product_no == "58121 E8"
    assert rows[0].product_name_en == "WINX CLUB BLOOM FAIRY WINGS ROLE PLAY"
    assert rows[0].quantity == 300
    assert str(rows[0].unit_price_hkd) == "23.2700"
    assert str(rows[0].amount_hkd) == "6981.00"
    assert rows[0].packaging == "美国包装"
    assert rows[1].product_no == "58122 E8"


def test_caixing_parser_handles_quantity_on_delivery_date_line(monkeypatch):
    monkeypatch.setattr(service, "_extract_pdf_text", lambda _content: SINGLE_PRODUCT_TEXT)

    rows = service.parse_caixing_pdf("1931878.pdf", b"%PDF synthetic")

    assert len(rows) == 1
    assert rows[0].product_no == "68695"
    assert rows[0].quantity == 3000
    assert rows[0].unit_price_hkd == 0
    assert rows[0].amount_hkd == 0


def test_caixing_preview_and_export_append_fixed_24_columns_to_active_sheet(monkeypatch):
    monkeypatch.setattr(service, "_extract_pdf_text", lambda _content: PLAYMATES_PO_TEXT)
    schedule_content = build_caixing_schedule()
    po_files = [("1931815.pdf", b"%PDF synthetic")]

    preview = service.create_caixing_batch_preview(
        factory_id="huaxing",
        received_date="2026-07-29",
        po_files=po_files,
        schedule_file_name="2026年彩星排期.xlsx",
        schedule_content=schedule_content,
    )

    assert preview["customer_code"] == "caixing"
    assert preview["summary"] == {
        "total": 2,
        "valid": 2,
        "warning": 0,
        "blocked": 0,
    }
    assert preview["output_file_name"] == "2026年彩星排期.xlsx"
    assert preview["rows"][0]["item_sheet_name"] == "采购订单"
    assert preview["rows"][0]["requested_ship_date"] == ""
    assert preview["_schedule_encrypted"] is False

    output, file_name, _ = service.export_caixing_batch_schedule(
        factory_id="huaxing",
        received_date="2026-07-29",
        po_files=po_files,
        schedule_file_name="2026年彩星排期.xlsx",
        schedule_content=schedule_content,
    )

    assert file_name == "2026年彩星排期.xlsx"
    plain, encrypted = _decrypt_schedule(output)
    assert encrypted is False
    workbook = service.CaixingSchedule(plain)
    rows = workbook.read_rows("采购订单")
    assert rows[2]["A"] == "旧数据"
    assert rows[3]["A"] == "2026/01/23"
    assert rows[3]["B"] == "SG-1926247"
    assert rows[3]["C"] == "OG-1931815"
    assert rows[3]["D"] == "IMPORTS DRAGON-CAN"
    assert rows[3]["E"] == "58121 E8"
    assert rows[3]["F"] == "WINX CLUB BLOOM FAIRY WINGS ROLE PLAY"
    assert rows[3]["G"] == "300"
    assert rows[3]["R"] == "美国包装"
    assert rows[3]["W"] == "23.27"
    assert rows[3]["X"] == "6981"
    assert rows[4]["E"] == "58122 E8"


def test_caixing_customer_is_owned_by_huaxing():
    _ensure_customer_factory("caixing", "huaxing")
    with pytest.raises(HTTPException, match="彩星.*只属于华兴厂区"):
        _ensure_customer_factory("caixing", "huakang-a")
