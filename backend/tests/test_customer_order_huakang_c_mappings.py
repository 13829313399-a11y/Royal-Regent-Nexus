from __future__ import annotations

from copy import deepcopy
from io import BytesIO

import openpyxl
import pytest

from app.api import customer_order as customer_order_api
from app.services import customer_order_huakang_c as service


def _schedule_bytes(customer_code: str) -> bytes:
    spec = service.get_huakang_c_customer_mapping(customer_code)
    profile = service.huakang_schedule.PROFILES[spec.legacy_code]
    workbook = openpyxl.Workbook()
    worksheet = workbook.active
    worksheet.title = profile.sheets[0]
    for row in range(1, profile.header_rows + 1):
        worksheet.cell(row, 1, f"{spec.name}表头{row}")
    item_columns, product_column = service.huakang_schedule._product_columns(profile)
    worksheet.cell(profile.style_row, profile.key_cols[0], "OLD-CONTRACT")
    worksheet.cell(profile.style_row, profile.key_cols[1], "OLD-ITEM")
    worksheet.cell(profile.style_row, item_columns[0], "ITEM-1")
    worksheet.cell(profile.style_row, product_column, "排期标准品名")
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def _order(customer_code: str) -> dict[str, object]:
    spec = service.get_huakang_c_customer_mapping(customer_code)
    return {
        "customer_code": spec.legacy_code,
        "customer_name": spec.name,
        "po_number": "PO-100",
        "contract_no": "SC-100",
        "po_date": "2026-07-01",
        "ship_date": "2026-09-01",
        "ship_dates": ["2026-09-01"],
        "ship_to": "Hong Kong",
        "version": "2" if customer_code == "jazwares" else "",
        "contact": "Amy",
        "lines": [{
            "item_code": "ITEM-1",
            "description": "PO Product",
            "qty": 120,
            "unit": "PCS",
            "unit_price_usd": 2.0,
            "amount_usd": 240.0,
            "pcs_per_carton": 12,
            "carton_qty": 10,
            "source_unit_price_usd": 0,
            "unit_price_hkd": 0,
            "version": "2" if customer_code == "jazwares" else "",
        }],
        "warnings": [],
    }


def test_huakang_c_registry_is_factory_scoped_and_keeps_maxx_separate() -> None:
    assert set(service.HUAKANG_C_CUSTOMER_MAPPINGS) == {
        "index", "jazwares", "maxx", "strottman", "jp",
    }
    assert customer_order_api.CUSTOMER_FACTORY_IDS["index"] == "huakang-c"
    assert customer_order_api.CUSTOMER_FACTORY_IDS["maxx"] == "huaxing"
    assert customer_order_api.CUSTOMER_FACTORY_OPTIONS["maxx"] == (
        "huaxing",
        "huakang-c",
    )
    assert customer_order_api._get_mapped_customer_spec(
        "maxx", "huaxing"
    ).target_template == "HUAXING_MAXX_NEW_ORDER_V1"
    assert customer_order_api._get_mapped_customer_spec(
        "maxx", "huakang-c"
    ).target_template == "HUAKANG_C_MAXX_NEW_ORDER_V1"

    with pytest.raises(service.HuakangCCustomerOrderError, match="只属于华康C厂区"):
        service.create_huakang_c_customer_preview(
            customer_code="index",
            factory_id="huakang-a",
            received_date="2026-08-03",
            po_files=[("INDEX.pdf", b"pdf")],
            schedule_file_name="INDEX排期.xlsx",
            schedule_content=_schedule_bytes("index"),
        )


def test_revision_deduplication_keeps_latest_po() -> None:
    original = dict(_order("jazwares"), filename="PO-100.pdf", version="")
    revision = dict(_order("jazwares"), filename="PO-100 REV2.pdf", version="2")
    selected, report = service._deduplicate([original, revision])
    assert [order["filename"] for order in selected] == ["PO-100 REV2.pdf"]
    assert "忽略 PO-100.pdf" in report[0]


@pytest.mark.parametrize(
    ("customer_code", "text", "expected"),
    [
        (
            "index",
            """INDEX PROMOTIONS
Purchase Order No. PO-INDEX-1
Date 7/1/2026
Ex-Factory 8/1/2026
Qty Units Description Unit Price TOTAL
1234 Product Header
480 pcs. - INDEX Toy $2.00 $960.00
48 pcs/carton
SubTotal""",
            ("PO-INDEX-1", "1234", 480),
        ),
        (
            "jazwares",
            """JAZWARES
07/01/2026 JAZ12345
PO Rev. 2
60 DAYS ROD 08/01/2026 SC-JAZ-1 SEA
ABC123 123-456 JAZWARES Toy 480 48 2.00 960.00
****""",
            ("JAZ12345", "ABC123", 480),
        ),
        (
            "maxx",
            """MAXX MARKETING
P.O. NO. MAXX-PO-1
P.O. DATE 01/07/2026
S.C. NO. SC-MAXX-1
DELIVERY 01/09/2026
MX-100 MAXX Toy 100 PCS 1.50 150.00""",
            ("MAXX-PO-1", "MX-100", 100),
        ),
        (
            "strottman",
            """STROTTMAN
Date Purchase Order # Terms
07/01/2026 PO123 NET
1234-1-F1 6,000 Case $125.00 $750,000.00
STROTTMAN Toy
Special Instructions 750K
01-Aug-2026 15-Aug-2026""",
            ("PO123", "1234-1", 750000),
        ),
        (
            "jp",
            """华康车衣
采购单编号：JP-100
日 期：2026年7月1日
2026年8月1日前交货
4L 布标
12345 车衣 1000 PCS""",
            ("JP-100", "12345", 1000),
        ),
    ],
)
def test_legacy_parser_recognizes_each_huakang_c_customer(
    customer_code: str,
    text: str,
    expected: tuple[str, str, int],
) -> None:
    parsed = service.huakang_po_parser.HuakangPOParser().parse_text(text)
    assert parsed["customer_code"] == service.get_huakang_c_customer_mapping(customer_code).legacy_code
    assert parsed["po_number"] == expected[0]
    assert parsed["lines"][0]["item_code"] == expected[1]
    assert parsed["lines"][0]["qty"] == expected[2]
    if customer_code == "strottman":
        assert parsed["lines"][0]["carton_qty"] == 6000
        assert parsed["lines"][0]["pcs_per_carton"] == 125
        assert parsed["ship_dates"] == ["2026-08-01", "2026-08-15"]


@pytest.mark.parametrize(
    ("customer_code", "contract_column", "item_column", "quantity_column", "data_row"),
    [
        ("index", 5, 6, 10, 4),
        ("jazwares", 5, 9, 11, 2),
        ("maxx", 5, 8, 11, 2),
        ("strottman", 5, 8, 11, 3),
        ("jp", 4, 5, 7, 3),
    ],
)
def test_preview_and_export_follow_each_customer_schedule_profile(
    monkeypatch,
    customer_code: str,
    contract_column: int,
    item_column: int,
    quantity_column: int,
    data_row: int,
) -> None:
    order = _order(customer_code)
    monkeypatch.setattr(
        service.huakang_po_parser.HuakangPOParser,
        "parse",
        lambda _self, _path: deepcopy(order),
    )
    schedule = _schedule_bytes(customer_code)
    preview = service.create_huakang_c_customer_preview(
        customer_code=customer_code,
        factory_id="huakang-c",
        received_date="2026-08-03",
        po_files=[(f"{customer_code}.pdf", b"pdf")],
        schedule_file_name=f"{customer_code}排期.xlsx",
        schedule_content=schedule,
    )
    row = preview["rows"][0]
    assert preview["factory_id"] == "huakang-c"
    assert row["received_date"] == "2026-08-03"
    assert row["contract_no"] == "SC-100"
    assert row["product_no"] == "ITEM-1"
    assert row["quantity"] == "120"
    assert row["unit_price_hkd"] == "15.5"
    assert row["amount_hkd"] == "1860"
    assert row["product_name_zh" if customer_code == "jp" else "product_name_en"] == "排期标准品名"
    if customer_code == "jp":
        assert row["status"] == "warning"
        assert any("尚无真实PO" in issue["message"] for issue in row["issues"])

    output, file_name, exported_preview = service.export_huakang_c_customer_schedule(
        customer_code=customer_code,
        factory_id="huakang-c",
        received_date="2026-08-03",
        po_files=[(f"{customer_code}.pdf", b"pdf")],
        schedule_file_name=f"{customer_code}排期.xlsx",
        schedule_content=schedule,
    )
    workbook = openpyxl.load_workbook(BytesIO(output), data_only=False)
    try:
        assert workbook.sheetnames[:2] == ["新增排期", "解析明细"]
        worksheet = workbook["新增排期"]
        assert worksheet.cell(data_row, contract_column).value == "SC-100"
        assert worksheet.cell(data_row, item_column).value == "ITEM-1"
        assert worksheet.cell(data_row, quantity_column).value == 120
        assert all(
            "OLD-CONTRACT" not in str(cell.value)
            for sheet in workbook
            for cells in sheet.iter_rows()
            for cell in cells
        )
    finally:
        workbook.close()
    assert file_name == preview["output_file_name"]
    assert exported_preview["summary"]["total"] == 1


def test_cross_customer_po_is_rejected(monkeypatch) -> None:
    wrong_order = _order("maxx")
    monkeypatch.setattr(
        service.huakang_po_parser.HuakangPOParser,
        "parse",
        lambda _self, _path: deepcopy(wrong_order),
    )
    with pytest.raises(service.HuakangCCustomerOrderError, match="当前入口只处理INDEX"):
        service.create_huakang_c_customer_preview(
            customer_code="index",
            factory_id="huakang-c",
            received_date="2026-08-03",
            po_files=[("MAXX.pdf", b"pdf")],
            schedule_file_name="INDEX排期.xlsx",
            schedule_content=_schedule_bytes("index"),
        )
