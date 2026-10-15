"""Legacy stored parent rows must never masquerade as newly costed child rows."""
import importlib
import json
from copy import deepcopy

import pytest

from test_internal_quote_api import make_client, login, create_payload
from test_internal_quote_p2_api import MOLDING_PAYLOAD, ENGINEERING_PAYLOAD


def legacy_quote(client, *, mode="direct_output"):
    payload = create_payload(suffix="LEGACY-PROJECTION", participating_sections=[
        "sales", "engineering", "molding", "assembly"])
    payload["workflow_mode"] = mode
    created = client.post("/api/internal-quotes", json=payload)
    assert created.status_code == 201, created.text
    quote = created.json()
    engineering = {**deepcopy(ENGINEERING_PAYLOAD), "molds": [{
        "mold_no": "M1", "item": "上/下", "quantity": 1, "cost_rmb": 1000}]}
    parent = {**MOLDING_PAYLOAD["injection_lines"][0], "item": "上/下", "mold_no": "M1",
              "engineering_source_key": "mold-no:M1#1", "remark": "保留机台"}
    saved = client.put(f"/api/internal-quotes/{quote['id']}/sections/save-all", json={"sections": [
        {"section_code": "engineering", "revision": 1, "payload": engineering},
        {"section_code": "molding", "revision": 1, "payload": {"injection_lines": [parent]}}]})
    assert saved.status_code == 200, saved.text
    engineering["molds"][0]["parts"] = [
        {"id": "top", "name": "上壳", "unit_net_weight_g": 10, "output_count": 2, "quantity": 3},
        {"id": "bottom", "name": "下壳", "unit_net_weight_g": 20, "output_count": 4, "quantity": 1}]
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.internal_quote")
    with db_module.SessionLocal() as db:
        row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote["id"], department="engineering").one()
        # Simulate imported historical split metadata with an apparently current old calculation.
        row.payload_json = json.dumps(engineering, ensure_ascii=False)
        db.commit()
    return quote["id"], engineering


def stored_molding(quote_id):
    db_module = importlib.import_module("app.db")
    models = importlib.import_module("app.models.internal_quote")
    with db_module.SessionLocal() as db:
        row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one()
        return {"payload": json.loads(row.payload_json), "calculation": json.loads(row.calculation_json),
                "revision": row.revision, "calculation_status": row.calculation_status,
                "dependency_status": row.dependency_status}


def molding_detail(client, quote_id):
    response = client.get(f"/api/internal-quotes/{quote_id}")
    assert response.status_code == 200, response.text
    return next(row for row in response.json()["sections"] if row["department"] == "molding")


def header_revision(client, quote_id):
    return client.get(f"/api/internal-quotes/{quote_id}").json()["header_revision"]


def test_mutable_projection_exposes_staleness_without_changing_saved_costs(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client)
        before = stored_molding(quote_id)
        assert before["calculation_status"] == "valid"
        displayed = molding_detail(client, quote_id)
        assert [row["item"] for row in displayed["payload"]["injection_lines"]] == ["上壳", "下壳"]
        assert displayed["calculation_status"] == displayed["dependency_status"] == "stale"
        assert displayed["calculation"]["line_breakdown"] == []
        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200, summary.text
        assert any(row["code"] == "engineering_parts_unsaved" for row in summary.json()["warnings"])
        assert float(summary.json()["components_hkd"]["molding_hkd"]) == 0
        assert stored_molding(quote_id) == before
        issued = client.post(f"/api/internal-quotes/{quote_id}/direct-issue", json={"revision": header_revision(client, quote_id)})
        assert issued.status_code == 409, issued.text
        assert "工程配件" in issued.text


@pytest.mark.parametrize("state", ["pending", "approved", "issued", "section_pending", "version_archived", "document_archived", "engineering_na"])
def test_readonly_history_keeps_saved_rows_and_costs(monkeypatch, state):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client)
        before = stored_molding(quote_id)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            quote = db.get(models.InternalQuote, quote_id)
            if state == "section_pending":
                db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one().status = "pending_review"
            elif state == "engineering_na":
                db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="engineering").one().status = "not_applicable"
            elif state == "version_archived":
                importlib.import_module("app.services.internal_quote_alternatives")._family(db, quote, create=True)
                db.get(models.InternalQuoteAlternative, quote_id).archived = True
            elif state == "document_archived":
                quote.status = "archived"
            else:
                quote.final_release_status = state
            db.commit()
        displayed = molding_detail(client, quote_id)
        assert displayed["payload"] == before["payload"]
        assert displayed["calculation"] == before["calculation"]
        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200, summary.text
        assert not any(row["code"] == "engineering_parts_unsaved" for row in summary.json()["warnings"])
        assert stored_molding(quote_id) == before


@pytest.mark.parametrize("operation", ["save", "recalculate"])
def test_explicit_write_persists_and_prices_the_displayed_children(monkeypatch, operation):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client)
        before = stored_molding(quote_id)
        if operation == "save":
            result = client.put(f"/api/internal-quotes/{quote_id}/sections/molding", json={
                "revision": before["revision"], "payload": before["payload"]})
        else:
            result = client.post(f"/api/internal-quotes/{quote_id}/formula/recalculate", json={
                "revision": header_revision(client, quote_id), "reason": "同步历史配件"})
        assert result.status_code == 200, result.text
        saved = stored_molding(quote_id)
        assert saved["revision"] == before["revision"] + 1
        assert saved["payload"] == molding_detail(client, quote_id)["payload"]
        assert saved["calculation_status"] == "valid"
        assert [row["net_weight_g"] for row in saved["calculation"]["line_breakdown"]] == ["10.0000", "20.0000"]
        assert [row["quantity"] for row in saved["calculation"]["line_breakdown"]] == ["2.0000", "2.0000"]
        assert [row["remark"] for row in saved["payload"]["injection_lines"]] == ["保留机台", "保留机台"]


def test_preview_uses_same_request_engineering_draft_without_persisting(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, engineering = legacy_quote(client)
        before = stored_molding(quote_id)
        engineering["molds"][0]["parts"][0]["unit_net_weight_g"] = 35
        detail = client.get(f"/api/internal-quotes/{quote_id}").json()
        sections = {row["department"]: row for row in detail["sections"]}
        response = client.post(f"/api/internal-quotes/{quote_id}/cost-preview", json={"drafts": [
            {"section_code": "engineering", "revision": sections["engineering"]["revision"], "payload": engineering},
            {"section_code": "molding", "revision": before["revision"], "payload": before["payload"]}]})
        assert response.status_code == 200, response.text
        assert [row["net_weight_g"] for row in response.json()["calculations"]["molding"]["line_breakdown"]] == ["35.0000", "20.0000"]
        assert stored_molding(quote_id) == before
        saved = client.put(f"/api/internal-quotes/{quote_id}/sections/save-all", json={"sections": [
            {"section_code": "engineering", "revision": sections["engineering"]["revision"], "payload": engineering},
            {"section_code": "molding", "revision": before["revision"], "payload": before["payload"]}]})
        assert saved.status_code == 200, saved.text
        actual = stored_molding(quote_id)["calculation"]
        preview = response.json()["calculations"]["molding"]
        assert actual["totals"] == preview["totals"]
        assert actual["input_hash"] == preview["input_hash"]
        assert actual["dependency_hash"] == preview["dependency_hash"]


def test_legacy_section_submission_cannot_silently_approve_old_parent_cost(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client, mode="section_review")
        before = stored_molding(quote_id)
        response = client.post(f"/api/internal-quotes/{quote_id}/sections/molding/submit", json={"revision": before["revision"]})
        assert response.status_code == 409, response.text
        assert "工程配件" in response.text
        assert stored_molding(quote_id) == before


def test_matching_child_payload_with_old_parent_calculation_is_still_blocked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client)
        projected = molding_detail(client, quote_id)["payload"]
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one()
            row.payload_json = json.dumps(projected, ensure_ascii=False)
            db.commit()
        before = stored_molding(quote_id)
        assert molding_detail(client, quote_id)["calculation_status"] == "stale"
        result = client.post(f"/api/internal-quotes/{quote_id}/direct-issue", json={"revision": header_revision(client, quote_id)})
        assert result.status_code == 409, result.text
        assert "工程配件" in result.text
        saved = client.put(f"/api/internal-quotes/{quote_id}/sections/molding", json={
            "revision": before["revision"], "payload": before["payload"]})
        assert saved.status_code == 200, saved.text
        assert len(stored_molding(quote_id)["calculation"]["line_breakdown"]) == 2
        assert molding_detail(client, quote_id)["calculation_status"] == "valid"


def test_recalculate_initializes_empty_legacy_molding_from_parts(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        quote_id, _ = legacy_quote(client)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.query(models.InternalQuoteSection).filter_by(quote_id=quote_id, department="molding").one()
            row.payload_json = "{}"
            db.commit()
        result = client.post(f"/api/internal-quotes/{quote_id}/formula/recalculate", json={
            "revision": header_revision(client, quote_id), "reason": "同步历史配件"})
        assert result.status_code == 200, result.text
        saved = stored_molding(quote_id)
        assert [row["item"] for row in saved["payload"]["injection_lines"]] == ["上壳", "下壳"]
        # Required department-owned fields are still absent, so this is not a valid zero quote.
        assert saved["calculation_status"] == "blocked"
        assert saved["payload"] == molding_detail(client, quote_id)["payload"]


def test_unmatched_unsplit_mold_requires_department_inputs_and_keeps_manual_row(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "projection-admin", "admin", "*", "*")
        response = client.post("/api/internal-quotes", json=create_payload(
            suffix="UNMATCHED-PARENT", participating_sections=["sales", "engineering", "molding", "assembly"]))
        assert response.status_code == 201, response.text
        quote_id = response.json()["id"]
        manual_payload = {"injection_lines": [
            {**MOLDING_PAYLOAD["injection_lines"][0], "mold_no": "MANUAL"}
        ]}
        response = client.put(f"/api/internal-quotes/{quote_id}/sections/save-all", json={"sections": [
            {"section_code": "engineering", "revision": 1, "payload": ENGINEERING_PAYLOAD},
            {"section_code": "molding", "revision": 1, "payload": manual_payload}]})
        assert response.status_code == 200, response.text
        saved = stored_molding(quote_id)
        assert saved["calculation_status"] == "blocked"
        rows = saved["payload"]["injection_lines"]
        assert [row["item"] for row in rows] == ["主模", "主壳"]
        assert rows[1] == manual_payload["injection_lines"][0]
        assert saved["payload"] == molding_detail(client, quote_id)["payload"]
