import importlib

from test_internal_quote_api import (
    ALL_SECTION_CODES,
    create_payload,
    ensure_user,
    login,
    logout,
    make_client,
)


ENGINEERING_PAYLOAD = {
    "materials": [
        {
            "item": "五金件",
            "category": "hardware",
            "quantity": "2",
            "unit_price_rmb": "8.5",
        }
    ],
    "molds": [{"item": "主模", "quantity": "1", "cost_rmb": "1000"}],
    "amortization_qty": "100",
    "customer_mold_subsidy_usd": "5",
}


MOLDING_PAYLOAD = {
    "injection_lines": [
        {
            "item": "主壳",
            "material": "ABS",
            "grade": "750SW",
            "net_weight_g": "454",
            "machine_code": "5A",
            "sets": "2",
            "target_output": "100",
            "quantity": "2",
        }
    ]
}


ASSEMBLY_PAYLOAD = {
    "labor_base_hkd": "260",
    "standard_work_hours": "11",
    "groups": [
        {
            "name": "成品组装",
            "category": "assembly",
            "production_qty": "100",
            "teams": "1",
            "processes": [{"name": "组装", "persons": "2", "remark": ""}],
        }
    ],
}


def test_business_and_engineering_roles_can_edit_all_sections_while_department_roles_stay_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_cross_sales", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="CROSS-EDIT", participating_sections=ALL_SECTION_CODES),
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        sales_edits_molding = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 1, "payload": MOLDING_PAYLOAD},
        )
        assert sales_edits_molding.status_code == 200, sales_edits_molding.text

        logout(client)
        login(client, "iq_cross_engineer", "engineer", "engineering")
        engineering_edits_painting = client.put(
            f"/api/internal-quotes/{quote_id}/sections/painting",
            json={"revision": 1, "payload": {"rows": []}},
        )
        assert engineering_edits_painting.status_code == 200, engineering_edits_painting.text

        logout(client)
        login(client, "iq_cross_molding", "molding_clerk", "molding")
        molding_edits_own_section = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 2, "payload": MOLDING_PAYLOAD},
        )
        assert molding_edits_own_section.status_code == 200, molding_edits_own_section.text
        molding_edits_painting = client.put(
            f"/api/internal-quotes/{quote_id}/sections/painting",
            json={"revision": 2, "payload": {"rows": [{"item": "越权"}]}},
        )
        assert molding_edits_painting.status_code == 403


def test_p2_reference_snapshot_contract_and_manual_sync_are_factory_scoped(monkeypatch):
    with make_client(monkeypatch) as client:
        profile = login(
            client,
            "iq_p2_sales_supervisor",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:reference_manage" in profile["permissions"]

        contract = client.get(
            "/api/internal-quotes/calculation-contracts?factory_id=huaxing"
        )
        assert contract.status_code == 200
        assert contract.json()["formula_version"] == "rr2-2026-v1"
        assert set(contract.json()["sections"]) == {
            "sales",
            "engineering",
            "electronic",
            "molding",
            "painting",
            "slush",
            "sewing",
            "assembly",
        }

        created_response = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P2-REF", participating_sections=ALL_SECTION_CODES),
        )
        assert created_response.status_code == 201, created_response.text
        created = created_response.json()
        quote_id = created["id"]
        old_reference_id = created["reference_snapshot_id"]
        assert old_reference_id.startswith("IQREF-")
        assert created["formula_version"] == "rr2-2026-v1"
        assert all(
            section["calculation_status"] == "pending"
            and section["calculation_reference_snapshot_id"] == old_reference_id
            for section in created["sections"]
        )

        reference = client.get(
            f"/api/internal-quotes/{quote_id}/reference-snapshot"
        )
        assert reference.status_code == 200
        old_snapshot = reference.json()
        assert old_snapshot["snapshot"]["fx"] == {
            "hkd_usd": "7.8",
            "rmb_hkd": "0.85",
            "rmb_usd": "7.75",
        }
        original_price = old_snapshot["snapshot"]["legacy_material_prices"]["ABS 750NSW"]

        db_module = importlib.import_module("app.db")
        molding_models = importlib.import_module("app.models.molding_sample")
        with db_module.SessionLocal() as db:
            price = db.query(molding_models.MoldingSampleMaterialPrice).filter_by(
                material="ABS 750NSW"
            ).one()
            price.unit_price = 99.5
            db.commit()

        frozen = client.get(
            f"/api/internal-quotes/{quote_id}/reference-snapshot"
        ).json()
        assert frozen["id"] == old_reference_id
        assert frozen["snapshot"]["legacy_material_prices"]["ABS 750NSW"] == original_price

        synced_response = client.post(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/sync",
            json={"revision": 1, "reason": "同步最新材料价"},
        )
        assert synced_response.status_code == 200, synced_response.text
        synced = synced_response.json()
        assert synced["header_revision"] == 2
        assert synced["reference_snapshot_id"] != old_reference_id

        latest = client.get(
            f"/api/internal-quotes/{quote_id}/reference-snapshot"
        ).json()
        assert latest["source_revision"] == 2
        assert latest["snapshot"]["legacy_material_prices"]["ABS 750NSW"] == "99.5000"
        with db_module.SessionLocal() as db:
            reference_models = importlib.import_module("app.models.internal_quote")
            old = db.get(reference_models.InternalQuoteReferenceSet, old_reference_id)
            assert old is not None
            assert old.is_current is False
            assert old.superseded_at


def test_sales_customer_owner_can_adjust_quote_fx_with_revision_and_recalculation(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_fx_owner", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="FX-UPDATE"),
        )
        assert created.status_code == 201, created.text
        quote = created.json()
        quote_id = quote["id"]
        old_reference_id = quote["reference_snapshot_id"]

        logout(client)
        login(client, "iq_fx_engineering", "engineer", "engineering")
        engineering = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": ENGINEERING_PAYLOAD},
        )
        assert engineering.status_code == 200, engineering.text
        assert engineering.json()["calculation"]["totals"]["hardware_hkd"] == "20.0000"

        forbidden = client.put(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/fx",
            json={"revision": 1, "rmb_hkd": "0.9", "hkd_usd": "7.9"},
        )
        assert forbidden.status_code == 403

        logout(client)
        login(client, "iq_fx_owner", "sales_customer_owner", "sales-business")
        updated = client.put(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/fx",
            json={"revision": 1, "rmb_hkd": "0.9", "hkd_usd": "7.9"},
        )
        assert updated.status_code == 200, updated.text
        result = updated.json()
        assert result["header_revision"] == 2
        assert result["reference_snapshot_id"] != old_reference_id
        recalculated = next(
            section for section in result["sections"] if section["department"] == "engineering"
        )
        assert recalculated["revision"] == 3
        assert recalculated["calculation"]["totals"]["hardware_hkd"] == "18.8889"

        reference = client.get(
            f"/api/internal-quotes/{quote_id}/reference-snapshot"
        )
        assert reference.status_code == 200
        assert reference.json()["source_type"] == "manual_fx"
        assert reference.json()["source_revision"] == 2
        assert reference.json()["snapshot"]["fx"] == {
            "hkd_usd": "7.9",
            "rmb_hkd": "0.9",
            "rmb_usd": "7.75",
        }

        timeline = client.get(f"/api/internal-quotes/{quote_id}/timeline")
        assert timeline.status_code == 200
        assert any(
            event["action"] == "reference_fx_update"
            and "RMB→HKD 0.85→0.9" in event["reason"]
            for event in timeline.json()["business_events"]
        )

        stale = client.put(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/fx",
            json={"revision": 1, "rmb_hkd": "0.91", "hkd_usd": "7.9"},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2

        invalid = client.put(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/fx",
            json={"revision": 2, "rmb_hkd": "0", "hkd_usd": "7.9"},
        )
        assert invalid.status_code == 422

        excessive_precision = client.put(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/fx",
            json={"revision": 2, "rmb_hkd": "0.851", "hkd_usd": "7.9"},
        )
        assert excessive_precision.status_code == 422


def test_p2_section_calculation_dependency_invalidation_and_blocked_submit(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_p2_creator", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="P2-CALC", participating_sections=ALL_SECTION_CODES),
        ).json()
        quote_id = created["id"]

        logout(client)
        login(client, "iq_p2_engineer", "engineer", "engineering")
        engineering = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": ENGINEERING_PAYLOAD},
        )
        assert engineering.status_code == 200, engineering.text
        engineering_section = engineering.json()
        assert engineering_section["calculation_status"] == "valid"
        assert engineering_section["calculation"]["formula_version"] == "rr2-2026-v1"
        assert engineering_section["calculation"]["totals"]["hardware_hkd"] == "20.0000"
        assert engineering_section["calculation"]["totals"]["mold_amortization_usd"] == "1.2403"

        logout(client)
        login(client, "iq_p2_molding", "molding_clerk", "molding")
        molding = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 1, "payload": MOLDING_PAYLOAD},
        )
        assert molding.status_code == 200, molding.text
        molding_section = molding.json()
        assert molding_section["calculation_status"] == "valid"
        assert molding_section["dependency_status"] == "current"
        assert molding_section["calculation"]["dependencies"]["engineering_molds_hash"]
        assert molding_section["calculation"]["totals"]["total_hkd"] == "26.9100"

        logout(client)
        login(client, "iq_p2_engineer_update", "engineer", "engineering")
        engineering_update = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={
                "revision": 2,
                "payload": {
                    **ENGINEERING_PAYLOAD,
                    "molds": [
                        {**ENGINEERING_PAYLOAD["molds"][0], "item": "主模调整"}
                    ],
                },
                "reason": "工程模具资料调整",
            },
        )
        assert engineering_update.status_code == 200

        detail = client.get(f"/api/internal-quotes/{quote_id}").json()
        stale_molding = next(
            section for section in detail["sections"] if section["department"] == "molding"
        )
        assert stale_molding["revision"] == 3
        assert stale_molding["calculation_status"] == "stale"
        assert stale_molding["dependency_status"] == "stale"

        logout(client)
        login(client, "iq_p2_molding_fix", "molding_clerk", "molding")
        blocked = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={
                "revision": 3,
                "payload": {
                    "injection_lines": [
                        {
                            "material": "UNKNOWN",
                            "grade": "NONE",
                            "net_weight_g": "10",
                            "machine_code": "999A",
                            "sets": "1",
                            "target_output": "1",
                        }
                    ]
                },
            },
        )
        assert blocked.status_code == 200
        assert blocked.json()["calculation_status"] == "blocked"
        assert {item["code"] for item in blocked.json()["calculation"]["warnings"]} == {
            "material_price_missing",
            "machine_price_missing",
        }

        blocked_submit = client.post(
            f"/api/internal-quotes/{quote_id}/sections/molding/submit",
            json={"revision": 4},
        )
        assert blocked_submit.status_code == 409
        assert "阻断警告" in blocked_submit.json()["detail"]["message"]

        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200
        body = summary.json()
        assert body["formula_version"] == "rr2-2026-v1"
        assert body["components_hkd"]["hardware_hkd"] == "20.0000"
        assert body["calculation_phase"] == "blocked"
        assert any(
            warning["section_code"] == "molding" and warning["severity"] == "blocking"
            for warning in body["warnings"]
        )


def test_p2_workflow_revision_changes_do_not_invalidate_calculated_downstream_sections(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user(
            "iq_p2_lifecycle_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        login(client, "iq_p2_lifecycle_creator", "sales_customer_owner", "sales-business")
        payload = create_payload(
            suffix="P2-LIFECYCLE",
            participating_sections=ALL_SECTION_CODES,
        )
        payload["business_owner_id"] = "user-iq_p2_lifecycle_reviewer"
        payload["business_owner_name"] = "iq_p2_lifecycle_reviewer"
        created = client.post(
            "/api/internal-quotes",
            json=payload,
        ).json()
        quote_id = created["id"]

        logout(client)
        login(client, "iq_p2_lifecycle_engineer", "engineer", "engineering")
        engineering = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": ENGINEERING_PAYLOAD},
        )
        assert engineering.status_code == 200, engineering.text

        logout(client)
        login(client, "iq_p2_lifecycle_molding", "molding_clerk", "molding")
        molding = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 1, "payload": MOLDING_PAYLOAD},
        )
        assert molding.status_code == 200, molding.text

        logout(client)
        login(client, "iq_p2_lifecycle_assembly", "admin", "assembly")
        assembly = client.put(
            f"/api/internal-quotes/{quote_id}/sections/assembly",
            json={"revision": 1, "payload": ASSEMBLY_PAYLOAD},
        )
        assert assembly.status_code == 200, assembly.text
        assembly_submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/assembly/submit",
            json={"revision": 2},
        )
        assert assembly_submitted.status_code == 200, assembly_submitted.text

        logout(client)
        login(
            client,
            "iq_p2_lifecycle_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        assembly_approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/assembly/review",
            json={"revision": 3, "decision": "approve", "reason": "装配核价确认"},
        )
        assert assembly_approved.status_code == 200, assembly_approved.text

        logout(client)
        login(client, "iq_p2_lifecycle_sales", "sales_customer_owner", "sales-business")
        sales = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"additional_tax_hkd": "1"}},
        )
        assert sales.status_code == 200, sales.text
        assert sales.json()["calculation_status"] == "valid"

        logout(client)
        login(client, "iq_p2_lifecycle_submitter", "engineer", "engineering")
        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/submit",
            json={"revision": 2},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["revision"] == 3

        detail = client.get(f"/api/internal-quotes/{quote_id}")
        assert detail.status_code == 200
        sections = {item["department"]: item for item in detail.json()["sections"]}
        assert sections["molding"]["revision"] == 2
        assert sections["molding"]["calculation_status"] == "valid"
        assert sections["molding"]["dependency_status"] == "current"
        assert sections["assembly"]["revision"] == 4
        assert sections["assembly"]["status"] == "approved"
        assert sections["assembly"]["calculation_status"] == "valid"
        assert sections["assembly"]["dependency_status"] == "current"
        assert sections["sales"]["revision"] == 2
        assert sections["sales"]["calculation_status"] == "valid"
        assert sections["sales"]["dependency_status"] == "current"

        logout(client)
        login(
            client,
            "iq_p2_lifecycle_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/review",
            json={"revision": 3, "decision": "approve", "reason": "工程核价确认"},
        )
        assert approved.status_code == 200, approved.text

        approved_detail = client.get(f"/api/internal-quotes/{quote_id}").json()
        approved_sections = {
            item["department"]: item for item in approved_detail["sections"]
        }
        assert approved_sections["molding"]["revision"] == 2
        assert approved_sections["assembly"]["revision"] == 4
        assert approved_sections["assembly"]["status"] == "approved"
        assert approved_sections["sales"]["revision"] == 2
        for section_code in ("molding", "assembly", "sales"):
            assert approved_sections[section_code]["calculation_status"] == "valid"
            assert approved_sections[section_code]["dependency_status"] == "current"


def test_p2_sales_can_be_approved_before_other_departments_save_without_resubmitting(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user(
            "iq_p2_scope_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        login(client, "iq_p2_scope_creator", "sales_customer_owner", "sales-business")
        payload = create_payload(
            suffix="P2-DEPENDENCY-SCOPE",
            participating_sections=ALL_SECTION_CODES,
        )
        payload["business_owner_id"] = "user-iq_p2_scope_reviewer"
        payload["business_owner_name"] = "iq_p2_scope_reviewer"
        created = client.post(
            "/api/internal-quotes",
            json=payload,
        ).json()
        quote_id = created["id"]

        logout(client)
        login(client, "iq_p2_scope_sales", "sales_customer_owner", "sales-business")
        sales = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"additional_tax_hkd": "1"}},
        )
        assert sales.status_code == 200, sales.text
        sales_submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/submit",
            json={"revision": 2},
        )
        assert sales_submitted.status_code == 200, sales_submitted.text

        logout(client)
        login(
            client,
            "iq_p2_scope_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        sales_approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={"revision": 3, "decision": "approve", "reason": "业务资料确认"},
        )
        assert sales_approved.status_code == 200, sales_approved.text

        logout(client)
        login(client, "iq_p2_scope_engineer", "engineer", "engineering")
        engineering = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": ENGINEERING_PAYLOAD},
        )
        assert engineering.status_code == 200, engineering.text

        logout(client)
        login(client, "iq_p2_scope_molding", "molding_clerk", "molding")
        molding = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 1, "payload": MOLDING_PAYLOAD},
        )
        assert molding.status_code == 200, molding.text

        logout(client)
        login(client, "iq_p2_scope_assembly", "admin", "assembly")
        assembly = client.put(
            f"/api/internal-quotes/{quote_id}/sections/assembly",
            json={"revision": 1, "payload": ASSEMBLY_PAYLOAD},
        )
        assert assembly.status_code == 200, assembly.text

        logout(client)
        login(client, "iq_p2_scope_engineer_update", "engineer", "engineering")
        engineering_update = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={
                "revision": 2,
                "payload": {
                    **ENGINEERING_PAYLOAD,
                    "materials": [
                        {**ENGINEERING_PAYLOAD["materials"][0], "quantity": "3"}
                    ],
                },
                "reason": "只调整五金用量",
            },
        )
        assert engineering_update.status_code == 200, engineering_update.text

        detail = client.get(f"/api/internal-quotes/{quote_id}").json()
        sections = {item["department"]: item for item in detail["sections"]}
        for section_code in ("molding", "assembly"):
            assert sections[section_code]["revision"] == 2
            assert sections[section_code]["calculation_status"] == "valid"
            assert sections[section_code]["dependency_status"] == "current"
        assert sections["sales"]["revision"] == 4
        assert sections["sales"]["status"] == "approved"
        assert sections["sales"]["calculation_status"] == "valid"
        assert sections["sales"]["dependency_status"] == "current"


def test_p2_dependency_and_reference_sync_close_stale_review_notifications(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user(
            "iq_p2_notice_reviewer",
            "sales_customer_supervisor",
            "sales-business",
        )
        login(client, "iq_p2_notice_creator", "sales_customer_owner", "sales-business")
        payload = create_payload(
            suffix="P2-NOTICE-LIFECYCLE",
            participating_sections=["sales", "engineering", "molding", "assembly"],
        )
        payload["business_owner_id"] = "user-iq_p2_notice_reviewer"
        payload["business_owner_name"] = "iq_p2_notice_reviewer"
        quote = client.post(
            "/api/internal-quotes",
            json=payload,
        ).json()
        quote_id = quote["id"]

        logout(client)
        login(client, "iq_p2_notice_engineer", "engineer", "engineering")
        engineering = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": ENGINEERING_PAYLOAD},
        )
        assert engineering.status_code == 200, engineering.text

        logout(client)
        login(client, "iq_p2_notice_molding", "molding_clerk", "molding")
        molding = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 1, "payload": MOLDING_PAYLOAD},
        )
        assert molding.status_code == 200, molding.text
        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/molding/submit",
            json={"revision": 2},
        )
        assert submitted.status_code == 200, submitted.text

        logout(client)
        login(client, "iq_p2_notice_reviewer", "sales_customer_supervisor", "sales-business")
        first_review_notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "section_submitted"
            and item["payload"].get("department") == "molding"
        )
        assert first_review_notification["status"] == "unread"

        logout(client)
        login(client, "iq_p2_notice_engineer_update", "engineer", "engineering")
        engineering_update = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={
                "revision": 2,
                "payload": {
                    **ENGINEERING_PAYLOAD,
                    "molds": [
                        {**ENGINEERING_PAYLOAD["molds"][0], "item": "主模调整"}
                    ],
                },
                "reason": "工程模具资料调整",
            },
        )
        assert engineering_update.status_code == 200, engineering_update.text

        logout(client)
        login(client, "iq_p2_notice_reviewer", "sales_customer_supervisor", "sales-business")
        notifications_after_dependency_change = client.get("/api/system/notifications").json()
        assert next(
            item
            for item in notifications_after_dependency_change
            if item["id"] == first_review_notification["id"]
        )["status"] == "handled"

        logout(client)
        login(client, "iq_p2_notice_molding_retry", "molding_clerk", "molding")
        recalculated = client.put(
            f"/api/internal-quotes/{quote_id}/sections/molding",
            json={"revision": 4, "payload": MOLDING_PAYLOAD},
        )
        assert recalculated.status_code == 200, recalculated.text
        resubmitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/molding/submit",
            json={"revision": recalculated.json()["revision"]},
        )
        assert resubmitted.status_code == 200, resubmitted.text

        logout(client)
        login(client, "iq_p2_notice_reviewer", "sales_customer_supervisor", "sales-business")
        second_review_notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "section_submitted"
            and item["payload"].get("department") == "molding"
            and item["status"] == "unread"
        )

        logout(client)
        login(client, "iq_p2_notice_reference_manager", "sales_customer_supervisor", "sales-business")
        synced = client.post(
            f"/api/internal-quotes/{quote_id}/reference-snapshot/sync",
            json={"revision": 1, "reason": "参考快照更新"},
        )
        assert synced.status_code == 200, synced.text

        logout(client)
        login(client, "iq_p2_notice_reviewer", "sales_customer_supervisor", "sales-business")
        notifications_after_sync = client.get("/api/system/notifications").json()
        assert next(
            item for item in notifications_after_sync if item["id"] == second_review_notification["id"]
        )["status"] == "handled"
