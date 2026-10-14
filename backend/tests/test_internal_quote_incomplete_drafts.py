"""Draft persistence must not require completed costing or manufacture empty work."""
from copy import deepcopy
import importlib
import json

import pytest

from test_internal_quote_api import create_payload, login, logout, make_client
from test_internal_quote_alternatives import create, fill


def detail(client, quote_id):
    response = client.get(f"/api/internal-quotes/{quote_id}")
    assert response.status_code == 200, response.text
    result = response.json()
    return result, {row["department"]: row for row in result["sections"]}


@pytest.mark.parametrize("mode", ["direct_output", "whole_quote_review", "section_review"])
@pytest.mark.parametrize("whole_product", [False, True])
def test_incomplete_carton_draft_saves_but_cannot_submit_or_issue(monkeypatch, mode, whole_product):
    with make_client(monkeypatch) as client:
        login(client, "incomplete-owner", "admin", "*", "*")
        quote = fill(client, create(client, suffix="INCOMPLETE", mode=mode))
        quote_id = quote["id"]
        _, sections = detail(client, quote_id)
        valid_sales = sections["sales"]
        assert valid_sales["calculation"]["totals"]
        incomplete = deepcopy(valid_sales["payload"])
        incomplete["cartons"][0]["length_in"] = 0
        engineering = deepcopy(sections["engineering"]["payload"])
        engineering["materials"][0]["quantity"] = 7
        draft = {"revision": valid_sales["revision"], "payload": incomplete}
        if whole_product:
            result = client.put(f"/api/internal-quotes/{quote_id}/sections/save-all", json={"sections": [
                {"section_code": "engineering", "revision": sections["engineering"]["revision"], "payload": engineering},
                {"section_code": "sales", **draft},
            ]})
        else:
            result = client.put(f"/api/internal-quotes/{quote_id}/sections/sales", json=draft)
        assert result.status_code == 200, result.text
        current, saved = detail(client, quote_id)
        sales = saved["sales"]
        assert sales["payload"] == incomplete
        assert sales["status"] == "draft"
        assert sales["revision"] == valid_sales["revision"] + 1
        assert sales["calculation_status"] == "blocked"
        calculation = sales["calculation"]
        assert calculation["totals"] == {}
        assert calculation["line_breakdown"] == calculation["pricing_breakdown"] == []
        assert all(float(value) == 0 for value in calculation["currency_totals"].values())
        assert "长度" in calculation["warnings"][0]["message"]
        calc = importlib.import_module("app.services.internal_quote_calculator")
        assert calculation["input_hash"] == calc.content_hash(incomplete)
        assert calculation["reference_snapshot_id"] == current["reference_snapshot_id"]
        if whole_product:
            assert saved["engineering"]["payload"] == engineering
        if mode == "section_review":
            denied = client.post(f"/api/internal-quotes/{quote_id}/sections/sales/submit", json={"revision": sales["revision"]})
            assert denied.status_code == 400, denied.text
            assert "长度" in denied.text
        else:
            endpoint = "direct-issue" if mode == "direct_output" else "final-submit"
            denied = client.post(f"/api/internal-quotes/{quote_id}/{endpoint}", json={"revision": current["header_revision"]})
            assert denied.status_code == 409, denied.text
        # Failed completion must not roll back the separately saved draft.
        assert detail(client, quote_id)[1]["sales"] == sales
        stale = client.put(f"/api/internal-quotes/{quote_id}/sections/sales", json=draft)
        assert stale.status_code == 409, stale.text
        assert "current_revision" in stale.text
        preview = client.post(f"/api/internal-quotes/{quote_id}/cost-preview", json={"drafts": [{
            "section_code": "sales", "revision": sales["revision"], "payload": valid_sales["payload"],
        }]})
        assert preview.status_code == 200, preview.text
        fixed = client.put(f"/api/internal-quotes/{quote_id}/sections/sales", json={
            "revision": sales["revision"], "payload": valid_sales["payload"]})
        assert fixed.status_code == 200, fixed.text
        assert fixed.json()["calculation_status"] == "valid"
        totals = fixed.json()["calculation"]["totals"]
        assert totals == preview.json()["calculations"]["sales"]["totals"]
        old_totals = valid_sales["calculation"]["totals"]
        for key in ("carton_hkd", "carton_cuft", "packaging_material_hkd", "total_hkd"):
            assert totals[key] == old_totals[key]
        if whole_product:
            # The same draft transaction increased Engineering's quantity 2 -> 7.
            assert float(totals["base_factory_price_hkd"]) > float(old_totals["base_factory_price_hkd"])
        else:
            assert totals == old_totals


@pytest.mark.parametrize("empty", [{}, {"injection_lines": []}, {
    "injection_lines": [], "blow_lines": [], "caixing_tool_plan_rows": [], "injection_loss_rate_percent": 3,
}])
@pytest.mark.parametrize("operation", ["formula", "materials"])
def test_empty_molding_remains_pending_after_reference_recalculation(monkeypatch, empty, operation):
    with make_client(monkeypatch) as client:
        login(client, "empty-owner", "admin", "*", "*")
        payload = create_payload(suffix="EMPTY-MOLDING", participating_sections=["sales", "engineering", "molding", "assembly"])
        payload["workflow_mode"] = "direct_output"
        response = client.post("/api/internal-quotes", json=payload)
        assert response.status_code == 201, response.text
        quote_id = response.json()["id"]
        before, sections = detail(client, quote_id)
        assert sections["molding"]["payload"] == {}
        assert sections["molding"]["calculation_status"] == "pending"
        if empty:
            saved = client.put(f"/api/internal-quotes/{quote_id}/sections/molding", json={"revision": 1, "payload": empty})
            assert saved.status_code == 200, saved.text
            assert saved.json()["calculation_status"] == "pending"
        current, sections = detail(client, quote_id)
        revision = sections["molding"]["revision"]
        if operation == "formula":
            result = client.post(f"/api/internal-quotes/{quote_id}/formula/recalculate", json={
                "revision": current["header_revision"], "reason": "空白部门重算测试"})
        else:
            result = client.put(f"/api/internal-quotes/{quote_id}/reference-snapshot/materials", json={
                "revision": current["header_revision"], "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "20"}]})
        assert result.status_code == 200, result.text
        current, sections = detail(client, quote_id)
        molding = sections["molding"]
        assert molding["payload"] == empty
        assert molding["revision"] == revision
        assert molding["calculation_status"] == "pending"
        assert molding["dependency_status"] == "current"
        assert molding["calculation"]["totals"] == {}
        assert molding["calculation"]["warnings"] == []
        assert molding["calculation"]["reference_snapshot_id"] == current["reference_snapshot_id"]
        assert current["reference_snapshot_id"] != before["reference_snapshot_id"]
        # Default switches are persisted at creation, but do not mean that an
        # Engineering/Sales form has been filled or is ready for calculation.
        for code in ("engineering", "sales"):
            assert sections[code]["revision"] == 1
            assert not sections[code]["filled_at"]
            assert sections[code]["calculation_status"] == "pending"
        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200, summary.text
        assert not any(w["code"] in {"engineering_parts_unsaved", "calculation_blocked"} for w in summary.json()["warnings"])


def test_incomplete_draft_cannot_bypass_department_permissions(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        login(client, "draft-admin", "admin", "*", "*")
        quote = create(client, suffix="DRAFT-PERMISSION")
        logout(client)
        login(client, "draft-molding", "molding_clerk", "molding")
        response = client.put(f"/api/internal-quotes/{quote['id']}/sections/sales", json={
            "revision": 1, "payload": {"cartons": [{"length_in": 0}]}})
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("empty", [{}, {"injection_lines": []}])
@pytest.mark.parametrize("operation", ["save", "recalculate"])
def test_empty_molding_recalculation_clears_legacy_blocked_cost_snapshot(monkeypatch, empty, operation):
    with make_client(monkeypatch) as client:
        login(client, "legacy-empty-owner", "admin", "*", "*")
        payload = create_payload(suffix="EMPTY-LEGACY", participating_sections=["sales", "engineering", "molding", "assembly"])
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one()
            row.payload_json = json.dumps(empty)
            row.calculation_status = "blocked"
            row.calculation_json = json.dumps({"status": "blocked", "totals": {"total_hkd": "99"}, "warnings": [{"code": "no_calculation_lines"}]})
            db.commit()
        if operation == "save":
            response = client.put(f"/api/internal-quotes/{quote_id}/sections/molding", json={"revision": 1, "payload": empty})
        else:
            response = client.post(f"/api/internal-quotes/{quote_id}/formula/recalculate", json={"revision": 1, "reason": "修复空白状态"})
        assert response.status_code == 200, response.text
        molding = detail(client, quote_id)[1]["molding"]
        assert molding["calculation_status"] == "pending"
        assert molding["calculation"]["totals"] == {}
        assert molding["calculation"]["warnings"] == []
