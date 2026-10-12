"""Archive boundaries across documents, alternatives and legacy workflows."""
import importlib
import json
import pytest

from test_internal_quote_api import make_client, login, logout, create_payload, ensure_user, grant_user_permission
from test_internal_quote_alternatives import create, fork, fill
from test_internal_quote_whole_review import mark_whole_quote_ready, whole_review_payload


def checked(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def current(client, identity):
    return checked(client.get(f"/api/internal-quotes/{identity}"))


def family(client, identity):
    return checked(client.get(f"/api/internal-quotes/{identity}/alternatives"))


def create_batch(client, suffix, mode="direct_output"):
    payload = create_payload(suffix=suffix)
    payload.update(workflow_mode=mode, quote_type="series", products=[
        {"product_name": "A", "qty": 5000}, {"product_name": "B", "qty": 5000}])
    root = checked(client.post("/api/internal-quotes", json=payload), 201)
    products = checked(client.get(f"/api/internal-quotes/{root['id']}/batch-products"))
    return root, current(client, products[1]["quote_id"])


def archive_version(client, identity):
    return checked(client.post(f"/api/internal-quotes/{identity}/alternative-archive", json={
        "family_revision": family(client, identity)["revision"], "archived": True, "reason": "暂不采用此版"}))


def test_document_archive_restore_all_products_versions_and_keep_version_archive(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "archive-document", "admin", "*", "*")
        payload = create_payload(suffix="ARCHIVE-DOCUMENT")
        payload.update(workflow_mode="direct_output", quote_type="series", products=[
            {"product_name": "A款", "qty": 5000}, {"product_name": "B款", "qty": 5000}])
        root = checked(client.post("/api/internal-quotes", json=payload), 201)
        products = checked(client.get(f"/api/internal-quotes/{root['id']}/batch-products"))
        child_id = products[1]["quote_id"]
        variant = fork(client, current(client, child_id))
        archive_version(client, child_id)
        # The batch source must not overwrite an individually archived target.
        checked(client.post(f"/api/internal-quotes/{root['id']}/batch-products/{child_id}/copy-baseline",
                            json={"revision": current(client, child_id)["header_revision"]}), 409)
        before = {q: current(client, q) for q in [root["id"], child_id, variant["id"]]}
        archived = checked(client.post(f"/api/internal-quotes/{root['id']}/archive", json={
            "revision": root["header_revision"], "reason": "项目暂停"}))
        for identity in before:
            assert current(client, identity)["status"] == "archived"
            assert all(row["archived"] for row in family(client, identity)["items"])
        info = family(client, variant["id"])
        assert info["document_archive"]["quote_id"] == root["id"]
        checked(client.post(f"/api/internal-quotes/{variant['id']}/alternative-archive", json={
            "family_revision": info["revision"], "archived": False, "reason": "不能绕过整单"}), 409)
        checked(client.post(f"/api/internal-quotes/{root['id']}/restore", json={
            "revision": root["header_revision"], "reason": "旧revision"}), 409)
        checked(client.post(f"/api/internal-quotes/{root['id']}/restore", json={
            "revision": archived["header_revision"], "reason": "   "}), 400)
        checked(client.post(f"/api/internal-quotes/{root['id']}/restore", json={
            "revision": archived["header_revision"], "reason": "项目继续"}))
        for identity, original in before.items():
            restored = current(client, identity)
            assert restored["status"] == original["status"]
            assert restored["sections"] == original["sections"]
            assert restored["document_archive"] is None
        rows = family(client, child_id)["items"]
        assert next(row for row in rows if row["quote_id"] == child_id)["archived"]
        assert not next(row for row in rows if row["quote_id"] == variant["id"])["archived"]


def test_old_batch_archive_protects_variants_and_restore_requires_archive_permission(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        login(client, "old-archive-admin", "admin", "*", "*")
        quote = create(client, "OLD-ARCHIVE")
        variant = fork(client, quote)
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.get(models.InternalQuote, quote["id"])
            row.status = "archived"; row.archived_at = "2026-10-12 09:00:00"
            row.archived_by = "legacy"; row.header_revision += 1
            db.commit()
        info = family(client, variant["id"])
        assert info["document_archive"] and all(row["archived"] for row in info["items"])
        checked(client.put(f"/api/internal-quotes/{variant['id']}/sections/sales", json={
            "revision": variant["sections"][-1]["revision"], "payload": {"confirmed": True}}), 409)
        logout(client); login(client, "old-archive-sales", "sales_customer_owner", "sales-business")
        checked(client.post(f"/api/internal-quotes/{quote['id']}/restore", json={"revision": 2, "reason": "恢复"}), 403)
        checked(client.post(f"/api/internal-quotes/{quote['id']}/alternative-archive", json={
            "family_revision": info["revision"], "archived": False, "reason": "恢复"}), 409)
        logout(client); login(client, "old-archive-admin", "admin", "*", "*")
        restored = checked(client.post(f"/api/internal-quotes/{quote['id']}/restore", json={"revision": 2, "reason": "主管恢复"}))
        assert restored["status"] == "drafting"
        assert not any(row["archived"] for row in family(client, variant["id"])["items"])


def test_issued_alternative_blocks_document_archive_and_archived_series_but_history_survives(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "archive-output", "admin", "*", "*")
        quote, sibling = create_batch(client, "ARCHIVE-OUTPUT")
        quote = fill(client, quote)
        variant = fork(client, quote)
        record = checked(client.post(f"/api/internal-quotes/{variant['id']}/direct-issue", json={"revision": variant["header_revision"]}))
        checked(client.post(f"/api/internal-quotes/{quote['id']}/archive", json={"revision": quote["header_revision"], "reason": "整单"}), 409)
        assert current(client, quote["id"])["status"] != "archived"
        archive_version(client, variant["id"])
        checked(client.post(f"/api/internal-quotes/{quote['id']}/series-export", json={"products": [
            {"quote_id": variant["id"], "revision": current(client, variant["id"])["header_revision"]},
            {"quote_id": sibling["id"], "revision": sibling["header_revision"]}]}), 409)
        historical = checked(client.post(f"/api/internal-quotes/{variant['id']}/exports"), 201)
        assert historical["id"] == record["id"]


@pytest.mark.parametrize("workflow", ["v2", "v3"])
def test_pending_review_survives_archive_restore_without_changing_submission(monkeypatch, workflow):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "true")
    with make_client(monkeypatch) as client:
        ensure_user("archive-reviewer", "sales_customer_owner", "sales-business")
        grant_user_permission("archive-reviewer", "internal_quote:sales_review", "sales-business")
        grant_user_permission("archive-reviewer", "internal_quote:archive", "sales-business")
        login(client, "archive-reviewer", "sales_customer_owner", "sales-business")
        payload = whole_review_payload("ARCHIVE-REVIEW", "user-archive-reviewer", "archive-reviewer")
        quote = checked(client.post("/api/internal-quotes", json=payload), 201)
        mark_whole_quote_ready(quote["id"])
        if workflow == "v2":
            db_module = importlib.import_module("app.db")
            models = importlib.import_module("app.models.internal_quote")
            with db_module.SessionLocal() as db:
                db.get(models.InternalQuote, quote["id"]).module_version = "v2"
                for section in db.query(models.InternalQuoteSection).filter_by(quote_id=quote["id"], is_required=True):
                    section.status = "approved"
                db.commit()
                row = db.get(models.InternalQuote, quote["id"])
                release = importlib.import_module("app.services.internal_quote_release")
                row.header_revision = 2
                row.final_submission_manifest_json = json.dumps(release._release_manifest(row,
                    db.query(models.InternalQuoteSection).filter_by(quote_id=row.id).all()))
                row.status = "final_reviewing"; row.final_release_status = "pending"
                row.final_submission_revision = 1
                row.final_submitted_by = row.created_by
                row.final_submitted_by_name = row.created_by_name
                db.commit()
        else:
            checked(client.post(f"/api/internal-quotes/{quote['id']}/final-submit", json={"revision": 1}))
        submitted = current(client, quote["id"])
        archived = checked(client.post(f"/api/internal-quotes/{quote['id']}/archive", json={"revision": 2, "reason": "暂停"}))
        restored = checked(client.post(f"/api/internal-quotes/{quote['id']}/restore", json={"revision": archived["header_revision"], "reason": "继续"}))
        assert restored["status"] == "final_reviewing"
        assert restored["final_submission_manifest"] == submitted["final_submission_manifest"]
        # Retained approval must still reject changed cost snapshots after restore.
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            section = db.query(models.InternalQuoteSection).filter_by(quote_id=quote["id"], department="sales").one()
            original_hash = section.calculation_hash
            section.calculation_hash = "changed-after-submission"
            db.commit()
        checked(client.post(f"/api/internal-quotes/{quote['id']}/final-review", json={
            "revision": restored["header_revision"], "decision": "approve", "reason": "不能跳过变化"}), 409)
        with db_module.SessionLocal() as db:
            db.query(models.InternalQuoteSection).filter_by(quote_id=quote["id"], department="sales").one().calculation_hash = original_hash
            db.commit()
        result = checked(client.post(f"/api/internal-quotes/{quote['id']}/final-review", json={
            "revision": restored["header_revision"], "decision": "approve", "reason": "核对通过"}))
        assert result["quote"]["status"] == ("exported" if workflow == "v2" else "fully_approved")


def test_legacy_archived_output_with_superseded_export_stays_exported(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "archive-legacy-export", "admin", "*", "*")
        quote, sibling = create_batch(client, "ARCHIVE-LEGACY", mode="whole_quote_review")
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            row = db.get(models.InternalQuote, quote["id"])
            row.status = "archived"; row.final_release_status = "approved"
            row.final_release_revision = 1; row.header_revision = 2
            db.add(models.InternalQuoteExportFile(id="archived-export", quote_id=row.id, factory_id=row.factory_id, sha256="historical", content=b"historical",
                release_stage="p4_final_approved", status="superseded",
                export_manifest_json=json.dumps({"final_release_revision": 1})))
            db.commit()
        restored = checked(client.post(f"/api/internal-quotes/{quote['id']}/restore", json={"revision": 2, "reason": "继续"}))
        assert restored["status"] == "exported" and restored["final_release_status"] == "approved"
        archive_version(client, quote["id"])
        checked(client.post(f"/api/internal-quotes/{quote['id']}/series-export", json={"products": [
            {"quote_id": quote["id"], "revision": restored["header_revision"]},
            {"quote_id": sibling["id"], "revision": sibling["header_revision"]}]}), 409)
