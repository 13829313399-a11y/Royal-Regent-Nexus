"""Huakang D may explicitly save an engineering section with no cost lines."""
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.services.internal_quote_calculator import CalculationInputError, calculate_section
from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_alternatives import fill, fork
from test_internal_quote_calculator import SNAPSHOT


EMPTY_ENGINEERING = {"materials": [], "molds": [], "cartons": [], "mold_allocation_enabled": False}


@pytest.mark.parametrize("factory", ["huakang-d", "huakang-a", "huakang-b", "huakang-c", "huaxing", "huadeng", ""])
def test_empty_engineering_exception_uses_trusted_factory_only(factory):
    result = calculate_section("engineering", {**EMPTY_ENGINEERING, "factory_id": "huakang-d"},
                               SNAPSHOT, "REF", context={"factory_id": factory})
    assert result["status"] == ("valid" if factory == "huakang-d" else "blocked")
    assert float(result["totals"]["total_hkd"]) == 0
    assert float(result["totals"]["mold_amortization_usd"]) == 0
    assert any(row["code"] == "no_calculation_lines" for row in result["warnings"]) == (factory != "huakang-d")


def test_huakang_d_still_checks_entered_engineering_lines_and_other_departments():
    with pytest.raises(CalculationInputError):
        calculate_section("engineering", {**EMPTY_ENGINEERING, "materials": [
            {"item": "螺丝", "category": "hardware", "quantity": 1, "unit_price_rmb": -1},
        ]}, SNAPSHOT, "REF", context={"factory_id": "huakang-d"})
    assembly = calculate_section("assembly", {"groups": []}, SNAPSHOT, "REF", context={"factory_id": "huakang-d"})
    assert assembly["status"] == "blocked"


@pytest.mark.parametrize("factory,empty", [
    ("huakang-d", EMPTY_ENGINEERING), ("huakang-d", {}), ("huaxing", EMPTY_ENGINEERING),
])
def test_preview_save_copy_and_output_without_engineering_lines(monkeypatch, factory, empty):
    with make_client(monkeypatch) as client:
        login(client, "empty-engineering-owner", "admin", "*", "*")
        payload = create_payload(suffix=f"EMPTY-ENG-{factory}")
        payload.update(factory_id=factory, workflow_mode="direct_output")
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        quote = fill(client, response.json())
        root = f"/api/internal-quotes/{quote['id']}"
        sections = {row["department"]: row for row in quote["sections"]}
        drafts = [{"section_code": code, "revision": sections[code]["revision"],
                   "payload": empty if code == "engineering" else sections[code]["payload"]}
                  for code in ("engineering", "sales")]
        preview = client.post(root + "/cost-preview", json={"drafts": drafts})
        assert preview.status_code == 200, preview.text
        expected = "valid" if factory == "huakang-d" else "blocked"
        assert preview.json()["calculations"]["engineering"]["status"] == expected
        saved = client.put(root + "/sections/save-all", json={"sections": drafts})
        assert saved.status_code == 200, saved.text
        quote = client.get(root).json()
        engineering = next(row for row in quote["sections"] if row["department"] == "engineering")
        assert engineering["filled_at"]
        assert engineering["calculation_status"] == expected
        assert float(engineering["calculation"]["totals"]["total_hkd"]) == 0
        assert engineering["calculation"]["totals"] == preview.json()["calculations"]["engineering"]["totals"]
        if factory != "huakang-d":
            denied = client.post(root + "/direct-issue", json={"revision": quote["header_revision"]})
            assert denied.status_code == 409 and "工程部" in denied.text
            return
        # An empty save remains idempotent, and a copied version can issue too.
        again = client.put(root + "/sections/engineering", json={"revision": engineering["revision"], "payload": empty})
        assert again.status_code == 200, again.text
        assert again.json()["revision"] == engineering["revision"]
        copied = fork(client, quote, "version")
        for current in (quote, copied):
            current_root = f"/api/internal-quotes/{current['id']}"
            issued = client.post(current_root + "/direct-issue", json={"revision": current["header_revision"]})
            assert issued.status_code == 200, issued.text
            record = issued.json()
            raw = client.get(current_root + f"/exports/{record['id']}/download")
            assert raw.status_code == 200, raw.text[:200] if raw.status_code != 200 else ""
            workbook = load_workbook(BytesIO(raw.content), read_only=True)
            assert workbook["审批与版本"]["B4"].value == "P4 直接输出"
            workbook.close()
