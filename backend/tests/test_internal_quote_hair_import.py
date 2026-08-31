import hashlib
from io import BytesIO

import pytest
from fastapi import HTTPException
from openpyxl import Workbook

from app.services.internal_quote_artifacts import _validate_import_file
from app.services.internal_quote_import import parse_internal_quote_workbook
from app.services.internal_quote_templates import build_internal_quote_import_template
from test_internal_quote_api import create_payload, login, logout, make_client
from test_internal_quote_calculator import calculate


HAIR_HEADER = ["图片", "货号", "货名", "单价(HK$)", "重量(g)", "单位", "备注", "名细", "重量（G)", "单价"]


def hair_workbook(rows, *, detail_title="明细", header=None):
    workbook = Workbook()
    formal = workbook.active
    formal.title = "正式"
    formal.append(HAIR_HEADER)
    formal.append([None, "OLD", "过期正式价", 99, 999, "PCS"])
    if detail_title:
        detail = workbook.create_sheet(detail_title)
        detail.append(header or HAIR_HEADER)
        for row in rows:
            detail.append(row)
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_original_hair_xls_reads_detail_product_price_and_weight_without_rounding():
    source, file_name = build_internal_quote_import_template("hair")
    assert file_name == "车发部报价单.xls"
    assert hashlib.sha256(source).hexdigest() == "42666f23c024ea6136aa3656a90ede68caa6b2882d55e1f41b394f1bd92c99dd"
    parsed = parse_internal_quote_workbook(source, "hair", fallback_product_name="当前产品")
    assert (parsed.sheet_name, parsed.header_row, parsed.row_count) == ("明细", 9, 1)
    assert parsed.payload_fragment["lines"] == [{
        "name": "当前产品", "craft": "车发", "weight_g": "15.0000",
        "unit_price_hkd": "2.3870229885057475", "unit": "PCS",
        "remark": "头发为:K发", "item_no": "", "source_sheet": "明细", "source_row": 10,
    }]
    assert any("未填货名" in warning for warning in parsed.warnings)
    result = calculate("hair", parsed.payload_fragment)
    assert result["status"] == "valid"
    assert result["totals"] == {"total_hkd": "2.3870"}


def test_hair_detail_ignores_material_breakdown_and_totals_and_preserves_each_product():
    source = hair_workbook([
        [None, "A-1", "直发", 2.39, 15, "PCS", "K发", "头发", 150, 0.04],
        [None, None, None, None, None, None, None, "梳发人工", 100, 0.3],
        [None, "A-2", "卷发", 1.123456, 8.765432, "套", "卷曲"],
        [None, None, "合计", 3.513456, 23.765432],
    ], detail_title="明細")
    parsed = parse_internal_quote_workbook(source, "hair")
    assert parsed.row_count == 2
    assert [row["source_row"] for row in parsed.payload_fragment["lines"]] == [2, 4]
    assert parsed.payload_fragment["lines"][1]["weight_g"] == "8.765432"
    assert parsed.payload_fragment["lines"][1]["unit_price_hkd"] == "1.123456"
    assert parsed.payload_fragment["lines"][1]["unit"] == "套"
    assert calculate("hair", parsed.payload_fragment)["totals"] == {"total_hkd": "3.5135"}


@pytest.mark.parametrize("price,weight", [(None, 15), (2.39, None), (0, 15), (2.39, -1), ("#VALUE!", 15), ("=1+1", 15)])
def test_hair_invalid_or_uncalculated_values_do_not_fall_back_to_formal_sheet(price, weight):
    source = hair_workbook([[None, "A-1", "直发", price, weight, "PCS"]])
    with pytest.raises(ValueError, match="单价和重量必须为正数"):
        parse_internal_quote_workbook(source, "hair")


def test_hair_requires_detail_sheet_and_product_hkd_price_header():
    with pytest.raises(ValueError, match="明细.*工作表"):
        parse_internal_quote_workbook(hair_workbook([], detail_title=None), "hair")
    for missing_column in (3, 4):
        header = list(HAIR_HEADER)
        header[missing_column] = "其他"
        with pytest.raises(ValueError, match="不能使用右侧材料明细单价代替"):
            parse_internal_quote_workbook(hair_workbook([], header=header), "hair")


def test_legacy_xls_support_is_limited_to_hair_and_checks_file_signature():
    source, file_name = build_internal_quote_import_template("hair")
    _validate_import_file(file_name, source, import_type="hair")
    for department in ("mold", "sewing"):
        with pytest.raises(HTTPException) as error:
            _validate_import_file(file_name, source, import_type=department)
        assert error.value.status_code == 400
    with pytest.raises(HTTPException) as error:
        _validate_import_file(file_name, b"PKfake", import_type="hair")
    assert error.value.status_code == 400
    with pytest.raises(ValueError, match="无法读取车发部 XLS"):
        parse_internal_quote_workbook(source[:8] + b"broken", "hair")


def test_hair_import_preview_confirm_replace_source_download_and_delete(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_hair_creator", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="HAIR", participating_sections=["engineering", "assembly", "hair", "sales"]))
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        source, file_name = build_internal_quote_import_template("hair")
        upload = {"file": (file_name, source, "application/vnd.ms-excel")}
        preview_response = client.post(f"/api/internal-quotes/{quote_id}/imports/hair/preview", files=upload)
        assert preview_response.status_code == 201, preview_response.text
        preview = preview_response.json()
        assert preview["target_department"] == "hair"
        assert preview["payload_fragment"]["lines"][0]["name"] == created.json()["product_name"]
        assert preview["row_count"] == 1

        def current_section():
            detail = client.get(f"/api/internal-quotes/{quote_id}").json()
            return next(section for section in detail["sections"] if section["department"] == "hair")

        assert current_section()["payload"] == {}
        assert current_section()["revision"] == 1
        for revision in (1, 2):
            if revision == 2:
                preview = client.post(f"/api/internal-quotes/{quote_id}/imports/hair/preview", files=upload).json()
                assert preview["diff_summary"]["existing_rows"] == 1
            confirmed = client.post(f"/api/internal-quotes/{quote_id}/imports/{preview['batch_id']}/confirm", json={"revision": revision, "mode": "append"})
            assert confirmed.status_code == 200, confirmed.text
            section = confirmed.json()["section"]
            assert confirmed.json()["batch"]["confirm_mode"] == "replace"
            assert section["revision"] == revision + 1
            assert section["calculation_status"] == "valid"
            assert section["calculation"]["totals"] == {"total_hkd": "2.3870"}
            assert len(section["payload"]["lines"]) == 1
            assert section["payload"]["lines"][0]["import_batch_id"] == preview["batch_id"]

        attachments = client.get(f"/api/internal-quotes/{quote_id}/attachments?department=hair").json()
        assert len(attachments) == 1
        attachment = attachments[0]
        assert attachment["is_import_source"] and attachment["import_type"] == "hair"
        downloaded = client.get(f"/api/internal-quotes/{quote_id}/attachments/{attachment['id']}/download")
        assert downloaded.headers["content-type"] == "application/vnd.ms-excel"
        assert downloaded.content == source

        stale = client.delete(f"/api/internal-quotes/{quote_id}/attachments/{attachment['id']}", params={"revision": 2})
        assert stale.status_code == 409
        assert len(current_section()["payload"]["lines"]) == 1
        deleted = client.delete(f"/api/internal-quotes/{quote_id}/attachments/{attachment['id']}", params={"revision": 3})
        assert deleted.status_code == 204, deleted.text
        assert current_section()["payload"]["lines"] == []
        assert current_section()["revision"] == 4


def test_hair_import_enforces_department_access_and_participation(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_hair_access", "sales_customer_owner", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="HAIR-ACCESS", participating_sections=["engineering", "assembly", "molding", "sales"]))
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        source, file_name = build_internal_quote_import_template("hair")
        upload = {"file": (file_name, source, "application/vnd.ms-excel")}
        inactive = client.post(f"/api/internal-quotes/{quote_id}/imports/hair/preview", files=upload)
        assert inactive.status_code == 409, inactive.text
        logout(client)
        login(client, "iq_hair_other_department", "molding_clerk", "molding")
        denied = client.post(f"/api/internal-quotes/{quote_id}/imports/hair/preview", files=upload)
        assert denied.status_code == 403, denied.text
