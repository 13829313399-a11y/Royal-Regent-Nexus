from io import BytesIO

import pytest
from openpyxl import load_workbook

from test_internal_quote_api import make_client, login, logout, create_payload
from test_internal_quote_alternatives import create, fill, fork
from test_internal_quote_series_export import series


def current(client, quote):
    return client.get(f"/api/internal-quotes/{quote['id']}").json()


def freeze_body(client, quotes, frozen=True):
    return {"frozen": frozen, "reason": "整单核对 / 客户要求微调",
            "products": [{"quote_id": q["id"], "revision": current(client, q)["header_revision"],
                          "family_revision": client.get(f"/api/internal-quotes/{q['id']}/alternatives").json()["revision"]}
                         for q in quotes]}


def freeze(client, quotes, frozen=True):
    response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/freeze",
                           json=freeze_body(client, quotes, frozen))
    assert response.status_code == 200, response.text
    return response.json()


def issue(client, quote):
    response = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue",
                           json={"revision": current(client, quote)["header_revision"]})
    assert response.status_code == 200, response.text
    return response.json()


def edit_sales(client, quote, amount):
    sales = next(s for s in current(client, quote)["sections"] if s["department"] == "sales")
    sales["payload"]["packaging_materials"][0]["unit_price_rmb"] = amount
    return client.put(f"/api/internal-quotes/{quote['id']}/sections/sales", json={
        "revision": sales["revision"], "payload": sales["payload"], "reason": "微调同一版报价"})


@pytest.mark.parametrize("justplay", [False, True])
def test_output_remains_editable_and_reexports_preserve_exact_history(monkeypatch, justplay):
    with make_client(monkeypatch) as client:
        login(client, "editable-output", "admin", "*", "*")
        if justplay:
            payload = create_payload(suffix="JP-EDITABLE")
            payload.update(workflow_mode="direct_output", factory_id="huakang-b",
                           workshop_code="huakang-b-workshop", customer="JustPlay", pricing_components=["主体", "配件"])
            response = client.post("/api/internal-quotes", json=payload)
            assert response.status_code == 201, response.text
            quote = fill(client, response.json())
        else:
            quote = fill(client, create(client))
        first = issue(client, quote)
        after = current(client, quote)
        assert after["status"] == "drafting" and after["final_release_status"] == "output"
        listing = client.get("/api/internal-quotes", params={"factory_id": quote["factory_id"], "status": "exported"})
        assert listing.status_code == 200, listing.text
        assert any(row["id"] == quote["id"] for row in listing.json())
        assert all(s["status"] == "draft" for s in after["sections"] if s["is_required"])
        assert issue(client, quote)["id"] == first["id"]
        url = f"/api/internal-quotes/{quote['id']}/exports/{first['id']}/download"
        original = client.get(url).content
        book = load_workbook(BytesIO(original))
        assert all(not sheet.protection.sheet for sheet in book)
        assert not book.security or not book.security.lockStructure
        assert "仍可修改" in book["审批与版本"]["B5"].value
        book.close()
        assert edit_sales(client, quote, 2).status_code == 200
        assert current(client, quote)["final_release_status"] == "invalidated"
        second = issue(client, quote)
        assert second["id"] != first["id"] and second["sha256"] != first["sha256"]
        stale = client.post(f"/api/internal-quotes/{quote['id']}/direct-issue",
                            json={"revision": quote["header_revision"]})
        assert stale.status_code == 409
        assert client.get(url).content == original
        assert current(client, quote)["version_label"] == quote["version_label"]
        rows = client.get(f"/api/internal-quotes/{quote['id']}/exports").json()
        assert {row["status"] for row in rows} == {"current", "superseded"}
        # The current output also remains available to customer-price conversion.
        pool = client.get("/api/customer-price/internal-quote-artifacts",
                          params={"factory_id": quote["factory_id"], "status": "available"})
        assert pool.status_code == 200, pool.text
        assert any(row["export_id"] == second["id"] for row in pool.json())


def test_manual_freeze_and_unfreeze_same_version_preserve_files_and_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "freeze-owner", "admin", "*", "*")
        quote = fill(client, create(client))
        issue(client, quote)
        frozen = freeze(client, [quote])[0]
        assert frozen["final_release_status"] == "issued" and frozen["status"] == "exported"
        assert all(s["status"] == "sealed" for s in frozen["sections"] if s["is_required"])
        final = issue(client, quote)
        url = f"/api/internal-quotes/{quote['id']}/exports/{final['id']}/download"
        original = client.get(url).content
        assert edit_sales(client, quote, 3).status_code == 409
        body = freeze_body(client, [quote], False)
        logout(client)
        login(client, "freeze-engineer", "engineer", "engineering")
        assert client.post(f"/api/internal-quotes/{quote['id']}/freeze", json=body).status_code == 403
        assert client.get(f"/api/internal-quotes/{quote['id']}/freeze-options").status_code == 403
        logout(client)
        login(client, "freeze-owner", "admin", "*", "*")
        unfrozen = freeze(client, [quote], False)[0]
        assert unfrozen["id"] == quote["id"] and unfrozen["version_label"] == quote["version_label"]
        assert unfrozen["status"] == "drafting"
        assert edit_sales(client, quote, 3).status_code == 200
        assert issue(client, quote)["id"] != final["id"]
        assert client.get(url).content == original


def test_entire_document_freeze_is_atomic_and_rejects_partial_stale_foreign_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "freeze-series", "admin", "*", "*")
        quotes = series(client)
        quotes[0] = fill(client, quotes[0])
        endpoint = f"/api/internal-quotes/{quotes[0]['id']}/freeze"
        assert client.post(endpoint, json=freeze_body(client, quotes)).status_code == 409
        assert all(current(client, q)["final_release_status"] != "issued" for q in quotes)
        assert all(client.get(f"/api/internal-quotes/{q['id']}/exports").json() == [] for q in quotes)
        quotes[1:] = [fill(client, q) for q in quotes[1:]]
        other = fill(client, create(client, "OTHER"))
        for wrong in (quotes[:2], [quotes[0], quotes[0], quotes[2]], [quotes[0], other, quotes[2]]):
            assert client.post(endpoint, json=freeze_body(client, wrong)).status_code == 409
        stale = freeze_body(client, quotes)
        assert edit_sales(client, quotes[2], 2).status_code == 200
        assert client.post(endpoint, json=stale).status_code == 409
        assert all(current(client, q)["final_release_status"] != "issued" for q in quotes)
        # One alternative per product is a current-version choice, not an extra product.
        variant = fork(client, current(client, quotes[1]), "version")
        selected = [quotes[0], variant, quotes[2]]
        freeze(client, selected)
        assert all(current(client, q)["final_release_status"] == "issued" for q in selected)
        assert current(client, quotes[1])["final_release_status"] != "issued"
        freeze(client, selected, False)
        assert all(current(client, q)["status"] == "drafting" for q in selected)


def test_unfrozen_old_formula_guidance_preserves_inputs_references_and_historical_files(monkeypatch):
    import importlib
    with make_client(monkeypatch) as client:
        login(client, "old-formula-unfreeze", "admin", "*", "*")
        quote = fill(client, create(client))
        frozen = freeze(client, [quote])[0]
        artifact = issue(client, quote)
        root = f"/api/internal-quotes/{quote['id']}"
        url = root + f"/exports/{artifact['id']}/download"
        original = client.get(url).content
        references = client.get(root + "/reference-snapshot").json()["snapshot"]
        # Only this isolated test database is made to resemble a historical freeze.
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            db.get(models.InternalQuote, quote["id"]).formula_version = "rr2-2026-v12"
            for section in frozen["sections"]:
                if section["is_required"]:
                    db.get(models.InternalQuoteSection, section["id"]).calculation_formula_version = "rr2-2026-v12"
            db.commit()
        locked_layout = client.get(root + "/output-layout").json()
        assert not any(w.get("code") == "formula_outdated" for w in locked_layout["warnings"])
        unfrozen = freeze(client, [quote], False)[0]
        response = client.get(root + "/output-layout")
        assert response.status_code == 200, response.text
        layout = response.json()
        pending = [w for w in layout["warnings"] if w.get("code") == "formula_outdated"]
        assert {w["section_code"] for w in pending} == {
            s["department"] for s in unfrozen["sections"] if s["is_required"]}
        assert all(w["section_name"] for w in pending)
        assert layout["quote_price_hkd"] is None
        assert current(client, quote)["header_revision"] == unfrozen["header_revision"]
        assert current(client, quote)["formula_version"] == "rr2-2026-v12"
        response = client.post(root + "/formula/recalculate", json={
            "revision": unfrozen["header_revision"], "reason": "解冻后沿用原参考价格更新公式"})
        assert response.status_code == 200, response.text
        updated = response.json()
        assert {s["department"]: s["payload"] for s in updated["sections"]} == {
            s["department"]: s["payload"] for s in unfrozen["sections"]}
        assert client.get(root + "/reference-snapshot").json()["snapshot"] == references
        ready = client.get(root + "/output-layout").json()
        assert not any(w.get("code") == "formula_outdated" for w in ready["warnings"])
        assert ready["quote_price_hkd"] is not None
        assert client.get(url).content == original
        assert issue(client, quote)["id"] != artifact["id"]


def test_adopted_frozen_version_and_legacy_workflow_are_not_silently_unlocked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "freeze-adoption", "admin", "*", "*")
        quote = fill(client, create(client))
        issue(client, quote)
        family = client.get(f"/api/internal-quotes/{quote['id']}/alternatives").json()
        body = {"family_revision": family["revision"], "selected_quote_id": quote["id"], "reason": "客户采用"}
        assert client.patch(f"/api/internal-quotes/{quote['id']}/alternative-selection", json=body).status_code == 409
        freeze(client, [quote])
        body["family_revision"] = client.get(f"/api/internal-quotes/{quote['id']}/alternatives").json()["revision"]
        assert client.patch(f"/api/internal-quotes/{quote['id']}/alternative-selection", json=body).status_code == 200
        assert client.post(f"/api/internal-quotes/{quote['id']}/freeze", json=freeze_body(client, [quote], False)).status_code == 409
        assert current(client, quote)["final_release_status"] == "issued"
        legacy = fill(client, create(client, "LEGACY", "whole_quote_review"))
        assert client.post(f"/api/internal-quotes/{legacy['id']}/freeze", json=freeze_body(client, [legacy])).status_code == 409


def test_home_document_anchor_can_be_an_archived_original_but_not_an_archived_document(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "freeze-archived-source", "admin", "*", "*")
        original = fill(client, create(client))
        target = fork(client, original)
        family = client.get(f"/api/internal-quotes/{original['id']}/alternatives").json()
        archived = client.post(f"/api/internal-quotes/{original['id']}/alternative-archive", json={
            "family_revision": family["revision"], "archived": True, "reason": "原方案不用"})
        assert archived.status_code == 200, archived.text
        options = client.get(f"/api/internal-quotes/{original['id']}/freeze-options")
        assert options.status_code == 200, options.text
        assert [item["quote_id"] for item in options.json()["products"][0]["options"]] == [target["id"]]
        response = client.post(f"/api/internal-quotes/{original['id']}/freeze", json=freeze_body(client, [target]))
        assert response.status_code == 200, response.text
        assert current(client, target)["final_release_status"] == "issued"
