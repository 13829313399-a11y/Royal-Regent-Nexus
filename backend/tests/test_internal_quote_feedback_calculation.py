"""Regression for Huakang B feedback 40e404cc, without changing source inputs."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest
from openpyxl import Workbook

from app.services.internal_quote_calculator import calculate_section
from app.services.internal_quote_excel import _build_summary_sheet
from app.services.internal_quote_workbook_view import WorkbookValues
from test_internal_quote_excel_formula_links import _section
from test_internal_quote_api import make_client, login
from test_internal_quote_alternatives import create, fill


SNAPSHOT = {"fx": {"rmb_hkd": ".85", "hkd_usd": "7.78"},
            "material_prices": {"C-PP|5090T": "7.80"}, "injection_loss_rate_percent": "3",
            "machine_prices": [{"range": "10A-12A", "machine": "120T", "shift_price_hkd": "1160"}]}
MOLD = {"item": "包装盘", "mold_id": "tray", "mold_no": "1", "material_type": "C-PP",
        "net_weight_g": 8, "cavity": 2, "quantity": 2, "target_output": 15230.7692,
        "machine_code": "12", "cycle_time_seconds": 26, "cost_rmb": 40000,
        "pricing_component_id": "tray"}


@pytest.mark.parametrize("component", [False, True])
@pytest.mark.parametrize("costed", [False, True])
def test_export_uses_only_costed_injection_rows_and_retains_usage(component, costed):
    # Deliberately different from mold sets: neither value may be rewritten.
    injection = {**MOLD, "material": "C-PP", "grade": "5090T", "sets": 2, "quantity": 3}
    original = deepcopy(injection)
    calculation = calculate_section("molding", {"injection_lines": [injection]}, SNAPSHOT, "frozen")
    assert calculation["status"] == "valid"
    engineering = _section("engineering", payload={"molds": [deepcopy(MOLD)]})
    molding = _section("molding", calculation=calculation if costed else {})
    molding.is_required = costed
    shipping = {"markup": "1.15", "misc_ratio": ".02", "rows": []}
    sales_payload = {}
    if component:
        sales_payload = {"pricing_mode": "component", "pricing_components": [{"id": "tray", "name": "包装盘配件"}]}
        shipping.update(pricing_mode="component", pricing_groups=[{"id": "tray", "name": "包装盘配件", "markup": "1.15", "cost_hkd": "0"}],
                        pricing_entries=[], global_pricing={"entries": [], "markup": "1.15", "cost_hkd": "0"})
    book = Workbook()
    try:
        _build_summary_sheet(book, SimpleNamespace(product_name="75596", quote_no="75595", remark="", customer="JustPlay" if component else "普通客", region_code="mainland"),
                             [engineering, molding, _section("sales", payload=sales_payload)], SNAPSHOT,
                             {"t1": [], "t2": [], "t3": [], "t4": [], "shipping_pricing": shipping}, {})
        sheet = book["报价明细"]
        rows = [r for r in range(1, sheet.max_row + 1) if sheet.cell(r, 3).value == "包装盘"]
        if costed:
            assert len(rows) == 1
            row = rows[0]
            values = WorkbookValues(book)
            assert values.cell(sheet.title, f"I{row}") == MOLD["target_output"]
            assert values.cell(sheet.title, f"E{row}") == pytest.approx(8.24)
            assert values.cell(sheet.title, f"J{row}") == pytest.approx(1160 / 15230.7692 / 2 * 3)
            assert values.cell(sheet.title, f"K{row}") == pytest.approx(8 * 1.03 * 7.8 / 454 * 3)
        else:
            assert rows == [], "Raw engineering molds must not manufacture injection costs"
        assert injection == original
        assert json.loads(engineering.payload_json)["molds"][0] == MOLD
    finally:
        book.close()


def test_missing_molding_blocks_new_output_and_summary_without_mutating_inputs(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "feedback-calculation", "admin", "*", "*")
        quote = fill(client, create(client, "MOLDING-MISSING"))
        section = next(s for s in quote["sections"] if s["department"] == "engineering")
        payload = {**section["payload"], "molds": [deepcopy(MOLD)], "mold_allocation_enabled": False}
        saved = client.put(f"/api/internal-quotes/{quote['id']}/sections/engineering", json={"revision": section["revision"], "payload": payload})
        assert saved.status_code == 200, saved.text
        quote = client.get(f"/api/internal-quotes/{quote['id']}").json()
        assert any(b["section_code"] == "molding" and "未参与" in b["reason"] for b in quote["readiness"]["blockers"])
        summary = client.get(f"/api/internal-quotes/{quote['id']}/summary")
        assert summary.status_code == 200, summary.text
        assert summary.json()["pricing_complete"] is False
        before = deepcopy(quote["sections"])
        issued = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue", json={"revision": quote["header_revision"]})
        assert issued.status_code == 409, issued.text
        assert "啤机核价" in issued.text
        after = client.get(f"/api/internal-quotes/{quote['id']}").json()
        assert after["sections"] == before
        assert after["header_revision"] == quote["header_revision"]


def test_tooling_only_is_not_implicitly_injection_costing():
    from app.services.internal_quote_molding_costs import missing_molding_cost_reason
    engineering = _section("engineering", payload={"molds": [{"item": "工模", "cost_rmb": 40000}]})
    engineering.is_required, engineering.status = True, "draft"
    assert missing_molding_cost_reason([engineering]) == ""
