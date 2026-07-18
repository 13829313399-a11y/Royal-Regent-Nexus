import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'internal_quote_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def ensure_user(username: str, role_id: str, department: str, factory_id: str = "huaxing") -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    with db_module.SessionLocal() as db:
        if db.get(auth_models.AuthUser, user_id) is None:
            salt, password_hash = auth_service.make_password_hash("123456")
            db.add(
                auth_models.AuthUser(
                    id=user_id,
                    username=username,
                    display_name=username,
                    password_salt=salt,
                    password_hash=password_hash,
                    status="active",
                    force_password_change=0,
                    created_at=auth_service.now_text(),
                    updated_at=auth_service.now_text(),
                )
            )
        binding_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        if db.get(auth_models.AuthUserRole, binding_id) is None:
            db.add(
                auth_models.AuthUserRole(
                    id=binding_id,
                    user_id=user_id,
                    role_id=role_id,
                    factory_id=factory_id,
                    department=department,
                )
            )
        db.commit()


def login(
    client: TestClient,
    username: str,
    role_id: str,
    department: str,
    factory_id: str = "huaxing",
) -> dict:
    ensure_user(username, role_id, department, factory_id)
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200
    return response.json()


def logout(client: TestClient) -> None:
    response = client.post("/api/auth/logout")
    assert response.status_code == 204


def create_payload(*, initiator_department: str = "sales-business", suffix: str = "001") -> dict:
    return {
        "factory_id": "huaxing",
        "workshop_code": "huaxing-workshop",
        "workshop_name": "华兴",
        "quote_no": f"IQ-TEST-{suffix}",
        "product_name": "内部报价测试产品",
        "customer": "测试客户",
        "qty": 5000,
        "version_label": "V1",
        "initiator_department": initiator_department,
        "business_owner_id": "owner-001",
        "business_owner_name": "业务负责人",
        "target_date": "2026-08-01",
        "remark": "P1 回归",
    }


def test_sales_create_generates_eight_sections_and_keeps_deduplicated_views(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get("/api/internal-quotes?factory_id=huaxing")
        assert anonymous.status_code == 401

        profile = login(client, "iq_sales_create", "sales_customer_owner", "sales-business")
        assert "internal_quote:create" in profile["permissions"]
        response = client.post("/api/internal-quotes", json=create_payload())
        assert response.status_code == 201, response.text
        quote = response.json()
        assert quote["status"] == "drafting"
        assert quote["initiator_department"] == "sales-business"
        assert quote["business_owner_name"] == "业务负责人"
        assert len(quote["sections"]) == 8
        assert [section["department"] for section in quote["sections"]] == [
            "sales",
            "engineering",
            "electronic",
            "molding",
            "painting",
            "slush",
            "sewing",
            "assembly",
        ]
        assert all(section["status"] == "draft" and section["revision"] == 1 for section in quote["sections"])

        quote_id = quote["id"]
        assert client.get(f"/api/internal-quotes/{quote_id}").status_code == 200
        assert client.get(f"/api/internal-quotes/{quote_id}").status_code == 200
        timeline = client.get(f"/api/internal-quotes/{quote_id}/timeline")
        assert timeline.status_code == 200
        assert len(timeline.json()["view_records"]) == 1
        assert timeline.json()["business_events"][0]["action"] == "create"

        listed = client.get("/api/internal-quotes?factory_id=huaxing&keyword=TEST-001")
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [quote_id]
        assert listed.json()[0]["sections"] == []


def test_sales_section_state_machine_blocks_stale_revision_and_self_review(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_sales_self", "sales_customer_supervisor", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="FLOW")).json()
        quote_id = created["id"]
        created_notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "quote_created"
            and item["payload"].get("department") == "sales"
        )
        direct_handle = client.patch(
            f"/api/system/notifications/{created_notification['id']}",
            json={"status": "handled"},
        )
        assert direct_handle.status_code == 409
        assert "业务流程" in direct_handle.json()["detail"]

        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"currency": "HKD", "confirmed": True}},
        )
        assert saved.status_code == 200
        assert saved.json()["revision"] == 2

        stale = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"confirmed": False}},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/submit",
            json={"revision": 2},
        )
        assert submitted.status_code == 200
        assert submitted.json()["status"] == "pending_review"
        assert submitted.json()["revision"] == 3
        notifications_after_submit = client.get("/api/system/notifications").json()
        assert next(
            item for item in notifications_after_submit if item["id"] == created_notification["id"]
        )["status"] == "handled"
        review_notification = next(
            item
            for item in notifications_after_submit
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "section_submitted"
            and item["payload"].get("department") == "sales"
        )
        assert review_notification["status"] == "unread"

        self_review = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={"revision": 3, "decision": "approve", "reason": ""},
        )
        assert self_review.status_code == 403

        logout(client)
        login(client, "iq_sales_reviewer", "sales_customer_supervisor", "sales-business")
        approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={"revision": 3, "decision": "approve", "reason": "复核通过"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"
        assert approved.json()["revision"] == 4
        notifications_after_review = client.get("/api/system/notifications").json()
        assert next(
            item for item in notifications_after_review if item["id"] == review_notification["id"]
        )["status"] == "handled"

        revisions = client.get(f"/api/internal-quotes/{quote_id}/sections/sales/revisions")
        assert revisions.status_code == 200
        assert [item["revision"] for item in revisions.json()] == [4, 3, 2, 1]

        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200
        assert summary.json()["completed_sections"] == 1
        assert summary.json()["calculation_phase"] == "calculated"


def test_na_reopen_clone_and_cross_department_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user("iq_business_owner_option", "sales_customer_owner", "sales-business")
        login(client, "iq_engineer_creator", "engineer", "engineering")
        owner_options = client.get(
            "/api/internal-quotes/business-owners?factory_id=huaxing"
        )
        assert owner_options.status_code == 200, owner_options.text
        assert any(
            item["id"] == "user-iq_business_owner_option"
            and item["display_name"] == "iq_business_owner_option"
            for item in owner_options.json()
        )
        created_response = client.post(
            "/api/internal-quotes",
            json=create_payload(initiator_department="engineering", suffix="ENG"),
        )
        assert created_response.status_code == 201
        created = created_response.json()
        quote_id = created["id"]

        forbidden_sales = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"blocked": True}},
        )
        assert forbidden_sales.status_code == 403

        na_missing_reason = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/request-na",
            json={"revision": 1, "reason": ""},
        )
        assert na_missing_reason.status_code == 422

        na_request = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/request-na",
            json={"revision": 1, "reason": "本项目无工程段成本"},
        )
        assert na_request.status_code == 200
        assert na_request.json()["status"] == "na_pending"

        logout(client)
        login(client, "iq_engineering_reviewer", "engineering_supervisor", "engineering")
        na_approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/review",
            json={"revision": 2, "decision": "approve", "reason": "确认不适用"},
        )
        assert na_approved.status_code == 200
        assert na_approved.json()["status"] == "not_applicable"

        reopened = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/reopen",
            json={"revision": 3, "reason": "客户范围变化，恢复核价"},
        )
        assert reopened.status_code == 200
        assert reopened.json()["status"] == "draft"

        clone = client.post(
            f"/api/internal-quotes/{quote_id}/clone",
            json={
                "quote_no": "IQ-TEST-ENG-COPY",
                "version_label": "V2",
                "business_owner_id": "owner-002",
                "business_owner_name": "复制单负责人",
                "target_date": "2026-08-15",
            },
        )
        assert clone.status_code == 201, clone.text
        cloned = clone.json()
        assert cloned["cloned_from_quote_id"] == quote_id
        assert cloned["initiator_department"] == "engineering"
        assert all(section["status"] == "draft" and section["revision"] == 1 for section in cloned["sections"])

        wrong_factory = client.get("/api/internal-quotes?factory_id=huadeng")
        assert wrong_factory.status_code == 403


def test_business_owner_options_include_fixed_sales_positions_but_not_general_manager(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        ensure_user(
            "iq_fixed_sales_owner",
            "position_sales_business",
            "sales-business",
        )
        ensure_user(
            "iq_revoked_fixed_sales_owner",
            "position_sales_business",
            "sales-business",
        )
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        revoked_binding_id = (
            "user-iq_revoked_fixed_sales_owner:position_sales_business:"
            "huaxing:sales-business"
        )
        with db_module.SessionLocal() as db:
            db.add(
                auth_models.AuthRoleBindingMetadata(
                    user_role_id=revoked_binding_id,
                    state="revoked",
                )
            )
            db.commit()
        login(
            client,
            "iq_general_manager_owner_check",
            "position_general_manager",
            "management",
        )

        owner_options = client.get(
            "/api/internal-quotes/business-owners?factory_id=huaxing"
        )
        assert owner_options.status_code == 200, owner_options.text
        owner_ids = {item["id"] for item in owner_options.json()}
        assert "user-iq_fixed_sales_owner" in owner_ids
        assert "user-iq_revoked_fixed_sales_owner" not in owner_ids
        assert "user-iq_general_manager_owner_check" not in owner_ids


@pytest.mark.parametrize("authz_mode", ["legacy", "shadow", "enforce"])
@pytest.mark.parametrize(
    "role_id",
    [
        "position_sales_business",
        "position_sales_supervisor",
        "position_sales_manager",
    ],
)
def test_sales_position_can_read_cross_factory_but_only_operate_home_factory(
    monkeypatch,
    authz_mode,
    role_id,
):
    monkeypatch.setenv("AUTHZ_MODE", authz_mode)
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    with make_client(monkeypatch) as client:
        login(
            client,
            "iq_general_manager_cross_factory",
            "position_general_manager",
            "management",
        )
        foreign_payload = create_payload(suffix="GM-CROSS")
        foreign_payload.update(
            {
                "factory_id": "huadeng",
                "workshop_code": "huadeng-workshop",
                "workshop_name": "华登",
            }
        )

        created = client.post("/api/internal-quotes", json=foreign_payload)
        assert created.status_code == 201, created.text
        quote = created.json()

        updated = client.patch(
            f"/api/internal-quotes/{quote['id']}",
            json={"revision": 1, "remark": "总经理跨厂维护"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["remark"] == "总经理跨厂维护"

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        export_id = f"export-{role_id}-{authz_mode}"
        with db_module.SessionLocal() as db:
            db.add(
                quote_models.InternalQuoteExportFile(
                    id=export_id,
                    quote_id=quote["id"],
                    factory_id="huadeng",
                    file_name="foreign-history.xlsx",
                    content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    size_bytes=4,
                    sha256="0" * 64,
                    section_revisions_json="{}",
                    status="current",
                    content=b"test",
                    template_version="internal-quote-p4-v2",
                    formula_version="v2",
                    reference_snapshot_id=quote["reference_snapshot_id"],
                    header_revision=2,
                    release_stage="p4_final_release",
                    export_manifest_json="{}",
                    exported_by="user-iq_general_manager_cross_factory",
                    exported_by_name="总经理",
                    exported_at="2026-07-18 00:00:00",
                    superseded_at="",
                )
            )
            db.commit()

        listed = client.get("/api/internal-quotes?factory_id=huadeng")
        assert listed.status_code == 200, listed.text
        assert quote["id"] in {item["id"] for item in listed.json()}

        logout(client)
        login(
            client,
            f"iq_cross_read_{role_id}_{authz_mode}",
            role_id,
            "sales-business",
        )

        foreign_list = client.get("/api/internal-quotes?factory_id=huadeng")
        assert foreign_list.status_code == 200, foreign_list.text
        assert quote["id"] in {item["id"] for item in foreign_list.json()}

        foreign_detail = client.get(f"/api/internal-quotes/{quote['id']}")
        assert foreign_detail.status_code == 200, foreign_detail.text

        foreign_timeline = client.get(f"/api/internal-quotes/{quote['id']}/timeline")
        foreign_reference = client.get(
            f"/api/internal-quotes/{quote['id']}/reference-snapshot"
        )
        foreign_summary = client.get(f"/api/internal-quotes/{quote['id']}/summary")
        assert foreign_timeline.status_code == 200, foreign_timeline.text
        assert foreign_reference.status_code == 200, foreign_reference.text
        assert foreign_summary.status_code == 200, foreign_summary.text

        forbidden_payload = dict(foreign_payload)
        forbidden_payload["quote_no"] = (
            f"IQ-TEST-CROSS-FACTORY-DENIED-{role_id}-{authz_mode}"
        )
        forbidden_create = client.post("/api/internal-quotes", json=forbidden_payload)
        assert forbidden_create.status_code == 403

        forbidden_update = client.patch(
            f"/api/internal-quotes/{quote['id']}",
            json={"revision": 2, "remark": "业务部不应跨厂维护"},
        )
        assert forbidden_update.status_code == 403

        forbidden_section_edit = client.put(
            f"/api/internal-quotes/{quote['id']}/sections/sales",
            json={"revision": 1, "payload": {"blocked": True}},
        )
        assert forbidden_section_edit.status_code == 403

        forbidden_clone = client.post(
            f"/api/internal-quotes/{quote['id']}/clone",
            json={
                "quote_no": f"IQ-TEST-FOREIGN-CLONE-{role_id}-{authz_mode}",
                "version_label": "V2",
                "business_owner_id": "owner-foreign-clone",
                "business_owner_name": "外厂复制负责人",
                "target_date": "2026-09-01",
            },
        )
        assert forbidden_clone.status_code == 403

        foreign_export_history = client.get(
            f"/api/internal-quotes/{quote['id']}/exports"
        )
        assert foreign_export_history.status_code == 200, foreign_export_history.text
        assert [item["id"] for item in foreign_export_history.json()] == [export_id]
        assert foreign_export_history.json()[0]["status"] == "current"
        with db_module.SessionLocal() as db:
            assert db.get(quote_models.InternalQuoteExportFile, export_id).status == "current"

        forbidden_export_download = client.get(
            f"/api/internal-quotes/{quote['id']}/exports/{export_id}/download"
        )
        assert forbidden_export_download.status_code == 403

        local_payload = create_payload(suffix=f"SALES-LOCAL-{role_id}-{authz_mode}")
        local_create = client.post("/api/internal-quotes", json=local_payload)
        assert local_create.status_code == 201, local_create.text

        wrong_department_payload = create_payload(
            initiator_department="engineering",
            suffix=f"SALES-AS-ENGINEERING-{role_id}-{authz_mode}",
        )
        wrong_department_create = client.post(
            "/api/internal-quotes",
            json=wrong_department_payload,
        )
        assert wrong_department_create.status_code == 403


def test_fixed_engineering_position_cannot_initiate_as_sales(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login(
            client,
            "iq_fixed_engineering_initiator",
            "position_engineering_engineer",
            "engineering",
        )

        wrong_department = client.post(
            "/api/internal-quotes",
            json=create_payload(
                initiator_department="sales-business",
                suffix="ENGINEERING-AS-SALES",
            ),
        )
        assert wrong_department.status_code == 403

        own_department = client.post(
            "/api/internal-quotes",
            json=create_payload(
                initiator_department="engineering",
                suffix="ENGINEERING-LOCAL",
            ),
        )
        assert own_department.status_code == 201, own_department.text


def test_cross_factory_read_does_not_lazy_initialize_foreign_reference_data(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        login(
            client,
            "iq_general_manager_legacy_reference",
            "position_general_manager",
            "management",
        )
        foreign_payload = create_payload(suffix="LEGACY-REFERENCE")
        foreign_payload.update(
            {
                "factory_id": "huadeng",
                "workshop_code": "huadeng-workshop",
                "workshop_name": "华登",
            }
        )
        created = client.post("/api/internal-quotes", json=foreign_payload)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            quote = db.get(quote_models.InternalQuote, quote_id)
            assert quote is not None
            references = db.query(quote_models.InternalQuoteReferenceSet).filter_by(
                quote_id=quote_id,
            ).all()
            assert references
            for reference in references:
                db.delete(reference)
            quote.reference_snapshot_id = ""
            quote.formula_version = ""
            db.commit()

        logout(client)
        login(
            client,
            "iq_sales_foreign_legacy_reference",
            "position_sales_business",
            "sales-business",
        )

        assert client.get(f"/api/internal-quotes/{quote_id}").status_code == 200
        reference = client.get(f"/api/internal-quotes/{quote_id}/reference-snapshot")
        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert reference.status_code == 403
        assert summary.status_code == 403

        with db_module.SessionLocal() as db:
            quote = db.get(quote_models.InternalQuote, quote_id)
            assert quote is not None
            assert quote.reference_snapshot_id == ""
            assert quote.formula_version == ""
            assert db.query(quote_models.InternalQuoteReferenceSet).filter_by(
                quote_id=quote_id,
            ).count() == 0


def test_internal_quote_list_can_opt_in_to_section_progress(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_list_progress", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="LIST-PROGRESS"),
        ).json()

        compact = client.get("/api/internal-quotes?factory_id=huaxing")
        assert compact.status_code == 200
        assert compact.json()[0]["sections"] == []

        expanded = client.get(
            "/api/internal-quotes?factory_id=huaxing&include_sections=true"
        )
        assert expanded.status_code == 200
        row = next(item for item in expanded.json() if item["id"] == created["id"])
        assert len(row["sections"]) == 8
        assert all(section["revision"] == 1 for section in row["sections"])


def test_sales_supervisor_can_archive_and_archived_quote_is_locked(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_archive_supervisor", "sales_customer_supervisor", "sales-business")
        quote = client.post("/api/internal-quotes", json=create_payload(suffix="ARCHIVE")).json()
        quote_notifications = [
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote["id"]
        ]
        assert quote_notifications

        missing_reason = client.post(
            f"/api/internal-quotes/{quote['id']}/archive",
            json={"revision": 1, "reason": ""},
        )
        assert missing_reason.status_code == 422

        archived = client.post(
            f"/api/internal-quotes/{quote['id']}/archive",
            json={"revision": 1, "reason": "客户项目取消"},
        )
        assert archived.status_code == 200
        assert archived.json()["status"] == "archived"
        assert archived.json()["header_revision"] == 2
        archived_notifications = client.get("/api/system/notifications").json()
        assert all(
            next(item for item in archived_notifications if item["id"] == notification["id"])["status"]
            == "handled"
            for notification in quote_notifications
        )

        locked = client.put(
            f"/api/internal-quotes/{quote['id']}/sections/sales",
            json={"revision": 1, "payload": {"confirmed": True}},
        )
        assert locked.status_code == 409
