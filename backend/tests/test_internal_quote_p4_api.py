import hashlib
import importlib
import json
from io import BytesIO

from openpyxl import load_workbook

from test_internal_quote_api import ALL_SECTION_CODES, create_payload, login, logout, make_client


def mark_all_sections_not_applicable(quote_id: str) -> None:
    db_module = importlib.import_module("app.db")
    quote_models = importlib.import_module("app.models.internal_quote")
    with db_module.SessionLocal() as db:
        quote = db.get(quote_models.InternalQuote, quote_id)
        sections = db.query(quote_models.InternalQuoteSection).filter_by(quote_id=quote_id).all()
        for section in sections:
            section.status = "not_applicable"
            section.calculation_status = "not_applicable"
            section.dependency_status = "current"
        quote.status = "ready_for_final_review"
        db.commit()


def mark_required_sections_not_applicable(quote_id: str) -> None:
    db_module = importlib.import_module("app.db")
    quote_models = importlib.import_module("app.models.internal_quote")
    with db_module.SessionLocal() as db:
        quote = db.get(quote_models.InternalQuote, quote_id)
        sections = db.query(quote_models.InternalQuoteSection).filter_by(quote_id=quote_id).all()
        for section in sections:
            if not section.is_required:
                continue
            section.status = "not_applicable"
            section.calculation_status = "not_applicable"
            section.dependency_status = "current"
        quote.status = "ready_for_final_review"
        db.commit()


def test_p4_release_ignores_inactive_optional_sections_and_marks_them_in_structured_data(monkeypatch):
    with make_client(monkeypatch) as client:
        submitter = login(
            client,
            "iq_p4_optional_submitter",
            "sales_customer_supervisor",
            "sales-business",
        )
        payload = create_payload(suffix="P4-OPTIONAL")
        payload["business_owner_id"] = submitter["id"]
        payload["business_owner_name"] = submitter["display_name"]
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        mark_required_sections_not_applicable(quote_id)

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text
        logout(client)
        login(
            client,
            "iq_p4_optional_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "参与分段均已完成"},
        )
        assert approved.status_code == 200, approved.text
        export = approved.json()["export"]
        downloaded = client.get(
            f"/api/internal-quotes/{quote_id}/exports/{export['id']}/download"
        )
        workbook = load_workbook(BytesIO(downloaded.content), read_only=True, data_only=False)
        rows = list(workbook["结构化数据"].iter_rows(min_row=4, values_only=True))
        payload_rows = {row[1]: row for row in rows if row[0] == "payload"}
        assert payload_rows["sales"][3] == "not_applicable"
        assert payload_rows["sales"][11] == "是"
        assert payload_rows["electronic"][3] == "draft"
        assert payload_rows["electronic"][11] == "否"
        workbook.close()


def test_p4_final_release_is_two_person_locked_and_hands_off_only_final_artifact(monkeypatch):
    with make_client(monkeypatch) as client:
        submitter = login(
            client,
            "iq_p4_submitter",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:final_submit" in submitter["permissions"]
        assert "internal_quote:final_approve" in submitter["permissions"]
        payload = create_payload(suffix="P4-RELEASE", participating_sections=ALL_SECTION_CODES)
        payload["business_owner_id"] = submitter["id"]
        payload["business_owner_name"] = submitter["display_name"]
        quote = client.post("/api/internal-quotes", json=payload).json()
        quote_id = quote["id"]

        blocked = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert blocked.status_code == 409

        mark_all_sections_not_applicable(quote_id)
        p3_export = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert p3_export.status_code == 201
        assert p3_export.json()["release_stage"] == "p3_section_approved"
        assert client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing"
        ).json() == []

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        )
        assert submitted.status_code == 200, submitted.text
        submitted_quote = submitted.json()["quote"]
        assert submitted_quote["status"] == "final_reviewing"
        assert submitted_quote["header_revision"] == 2
        assert submitted_quote["final_release_status"] == "pending"
        assert submitted_quote["final_submission_revision"] == 1
        assert submitted_quote["final_submission_manifest"]["manifest_sha256"]

        self_review = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": ""},
        )
        assert self_review.status_code == 403
        assert "不能审核自己的报价" in self_review.json()["detail"]

        logout(client)
        login(client, "iq_p4_owner_no_review", "sales_customer_owner", "sales-business")
        unauthorized_review = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": ""},
        )
        assert unauthorized_review.status_code == 403

        logout(client)
        reviewer = login(
            client,
            "iq_p4_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        notifications = client.get("/api/system/notifications")
        assert notifications.status_code == 200
        assert any(
            item["payload"].get("event") == "final_release_submitted"
            and item["payload"].get("quote_id") == quote_id
            for item in notifications.json()
        )

        approved = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "approve", "reason": "双人复核通过"},
        )
        assert approved.status_code == 200, approved.text
        result = approved.json()
        assert result["quote"]["status"] == "exported"
        assert result["quote"]["header_revision"] == 3
        assert result["quote"]["final_release_status"] == "approved"
        assert result["quote"]["final_release_revision"] == 1
        assert result["review"]["decision"] == "approve"
        final_export = result["export"]
        assert final_export["template_version"] == "internal-quote-p4-v2"
        assert final_export["release_stage"] == "p4_final_approved"
        assert final_export["export_manifest"]["p4_final_release_required"] is False
        assert final_export["export_manifest"]["final_reviewed_by"] == reviewer["id"]

        export_download = client.get(
            f"/api/internal-quotes/{quote_id}/exports/{final_export['id']}/download"
        )
        assert export_download.status_code == 200
        workbook = load_workbook(BytesIO(export_download.content), read_only=True, data_only=False)
        assert workbook["审批与版本"]["B4"].value == "P4 最终业务放行"
        assert workbook["审批与版本"]["B5"].value == "最终业务放行完成，可交接客价转换台"
        structured = workbook["结构化数据"]
        assert structured["B2"].value == "internal-quote-structured-data-v1"
        structured_rows = list(structured.iter_rows(min_row=4, values_only=True))
        assert {
            (record_type, department)
            for record_type, department in {(row[0], row[1]) for row in structured_rows}
            if department != "quote"
        } == {
            (record_type, department)
            for record_type in ("payload", "calculation")
            for department in (
                "sales",
                "engineering",
                "electronic",
                "molding",
                "painting",
                "slush",
                "sewing",
                "assembly",
            )
        }
        snapshot_parts = sorted(
            (row for row in structured_rows if row[0] == "reference_snapshot" and row[1] == "quote"),
            key=lambda row: row[8],
        )
        snapshot = json.loads("".join(str(row[10]) for row in snapshot_parts))
        assert snapshot["machine_prices"]
        assert snapshot["fx"]["hkd_usd"] == "7.8"
        for record_type in ("payload", "calculation"):
            sales_parts = sorted(
                (row for row in structured_rows if row[0] == record_type and row[1] == "sales"),
                key=lambda row: row[8],
            )
            assert len(sales_parts) == sales_parts[0][9]
            assert json.loads("".join(str(row[10]) for row in sales_parts)) == {}
        workbook.close()

        artifacts = client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing"
        )
        assert artifacts.status_code == 200, artifacts.text
        assert len(artifacts.json()) == 1
        handoff = artifacts.json()[0]
        assert handoff["export_id"] == final_export["id"]
        assert handoff["status"] == "available"
        assert handoff["artifact_manifest"]["release_revision"] == 1
        assert handoff["artifact_manifest"]["template_version"] == "internal-quote-p4-v2"
        assert handoff["sha256"] == final_export["sha256"]

        artifact_download = client.get(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/download"
        )
        assert artifact_download.status_code == 200
        assert artifact_download.headers["x-internal-quote-release-stage"] == "p4_final_approved"
        assert hashlib.sha256(artifact_download.content).hexdigest() == handoff["sha256"]

        consumed = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "customer-conversion-001"},
        )
        assert consumed.status_code == 200
        assert consumed.json()["status"] == "consumed"
        assert consumed.json()["consumer_reference"] == "customer-conversion-001"
        duplicate = client.post(
            f"/api/customer-price/internal-quote-artifacts/{handoff['id']}/consume",
            json={"consumer_reference": "customer-conversion-002"},
        )
        assert duplicate.status_code == 409

        repeated_export = client.post(f"/api/internal-quotes/{quote_id}/exports")
        assert repeated_export.status_code == 201
        assert repeated_export.json()["id"] == final_export["id"]
        assert client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing"
        ).json() == []
        consumed_artifacts = client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing&status=consumed"
        )
        assert [item["id"] for item in consumed_artifacts.json()] == [handoff["id"]]

        reopened = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/reopen",
            json={"revision": 1, "reason": "客户数量变更，重新核价"},
        )
        assert reopened.status_code == 200, reopened.text
        detail = client.get(f"/api/internal-quotes/{quote_id}").json()
        assert detail["status"] == "drafting"
        assert detail["final_release_status"] == "invalidated"
        revoked = client.get(
            "/api/customer-price/internal-quote-artifacts?factory_id=huaxing&status=revoked"
        )
        assert revoked.status_code == 200
        assert revoked.json()[0]["id"] == handoff["id"]
        assert revoked.json()[0]["revoke_reason"]


def test_p4_final_rejection_is_immutable_and_can_be_resubmitted(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p4_reject_submitter", "sales_customer_supervisor", "sales-business")
        quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P4-REJECT", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = quote["id"]
        mark_all_sections_not_applicable(quote_id)
        assert client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 1},
        ).status_code == 200

        logout(client)
        login(client, "iq_p4_reject_reviewer", "sales_customer_supervisor", "sales-business")
        missing_reason = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "reject", "reason": ""},
        )
        assert missing_reason.status_code == 422
        rejected = client.post(
            f"/api/internal-quotes/{quote_id}/final-review",
            json={"revision": 2, "decision": "reject", "reason": "运费场景需业务确认"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["quote"]["status"] == "ready_for_final_review"
        assert rejected.json()["quote"]["header_revision"] == 3
        assert rejected.json()["quote"]["final_release_status"] == "rejected"
        assert rejected.json()["export"] is None

        logout(client)
        login(client, "iq_p4_reject_submitter", "sales_customer_supervisor", "sales-business")
        resubmitted = client.post(
            f"/api/internal-quotes/{quote_id}/final-submit",
            json={"revision": 3},
        )
        assert resubmitted.status_code == 200
        assert resubmitted.json()["quote"]["final_submission_revision"] == 2

        reviews = client.get(f"/api/internal-quotes/{quote_id}/final-reviews")
        assert reviews.status_code == 200
        assert [(item["submission_revision"], item["decision"]) for item in reviews.json()] == [
            (1, "reject")
        ]


def test_p4_quote_version_comparison_uses_clone_lineage_and_section_snapshots(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p4_compare", "sales_customer_supervisor", "sales-business")
        base = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P4-COMPARE-BASE", participating_sections=ALL_SECTION_CODES),
        ).json()
        target = client.post(
            f"/api/internal-quotes/{base['id']}/clone",
            json={
                "quote_no": "IQ-TEST-P4-COMPARE-TARGET",
                "version_label": "V2",
                "business_owner_id": "owner-compare",
                "business_owner_name": "版本负责人",
                "target_date": "2026-09-01",
            },
        ).json()
        unrelated = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P4-COMPARE-OTHER", participating_sections=ALL_SECTION_CODES),
        ).json()

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            base_molding = db.query(quote_models.InternalQuoteSection).filter_by(
                quote_id=base["id"], department="molding"
            ).one()
            target_molding = db.query(quote_models.InternalQuoteSection).filter_by(
                quote_id=target["id"], department="molding"
            ).one()
            base_molding.payload_json = json.dumps({"machine_cost_hkd": "10.0000"})
            base_molding.calculation_json = json.dumps({"totals": {"total_hkd": "10.0000"}})
            base_molding.calculation_status = "valid"
            target_molding.payload_json = json.dumps({"machine_cost_hkd": "12.5000"})
            target_molding.calculation_json = json.dumps({"totals": {"total_hkd": "12.5000"}})
            target_molding.calculation_status = "valid"
            target_molding.revision = 2
            db.commit()

        candidates = client.get(f"/api/internal-quotes/{target['id']}/version-candidates")
        assert candidates.status_code == 200
        assert [item["id"] for item in candidates.json()] == [base["id"]]

        comparison = client.get(
            f"/api/internal-quotes/{target['id']}/compare/{base['id']}"
        )
        assert comparison.status_code == 200, comparison.text
        result = comparison.json()
        assert result["base"]["id"] == base["id"]
        assert result["target"]["id"] == target["id"]
        assert result["total_before_hkd"] == "10.0000"
        assert result["total_after_hkd"] == "12.5000"
        assert result["total_delta_hkd"] == "2.5000"
        molding = next(item for item in result["sections"] if item["section_code"] == "molding")
        assert molding["before_revision"] == 1
        assert molding["after_revision"] == 2
        assert molding["payload_changes"] == [
            {"path": "machine_cost_hkd", "before": "10.0000", "after": "12.5000"}
        ]

        invalid = client.get(
            f"/api/internal-quotes/{target['id']}/compare/{unrelated['id']}"
        )
        assert invalid.status_code == 400
