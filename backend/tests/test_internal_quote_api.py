import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"
ALL_SECTION_CODES = [
    "sales",
    "engineering",
    "electronic",
    "molding",
    "painting",
    "slush",
    "sewing",
    "assembly",
]

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


def create_payload(
    *,
    initiator_department: str = "sales-business",
    suffix: str = "001",
    participating_sections: list[str] | None = None,
) -> dict:
    payload = {
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
        "target_customer_price": "USD 3.50",
        "target_date": "2026-08-01",
        "remark": "P1 回归",
    }
    if participating_sections is not None:
        payload["participating_sections"] = participating_sections
    return payload


def test_sales_create_keeps_eight_section_slots_but_only_mandatory_departments_participate(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get("/api/internal-quotes?factory_id=huaxing")
        assert anonymous.status_code == 401

        profile = login(client, "iq_sales_create", "sales_customer_owner", "sales-business")
        assert "internal_quote:create" in profile["permissions"]
        missing_target = create_payload(suffix="NO-TARGET")
        missing_target["target_customer_price"] = "   "
        rejected = client.post("/api/internal-quotes", json=missing_target)
        assert rejected.status_code == 422

        response = client.post("/api/internal-quotes", json=create_payload())
        assert response.status_code == 201, response.text
        quote = response.json()
        assert quote["status"] == "drafting"
        assert quote["initiator_department"] == "sales-business"
        assert quote["business_owner_name"] == "业务负责人"
        assert quote["target_customer_price"] == "USD 3.50"
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
        assert {
            section["department"] for section in quote["sections"] if section["is_required"]
        } == {"sales", "engineering", "assembly"}

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


def test_pricing_baseline_is_readable_by_sales_owner_and_only_managed_by_sales_supervisor(monkeypatch):
    with make_client(monkeypatch) as client:
        owner_profile = login(client, "iq_baseline_owner", "sales_customer_owner", "sales-business")
        assert "internal_quote:baseline_read" in owner_profile["permissions"]
        assert "internal_quote:baseline_manage" not in owner_profile["permissions"]

        initial = client.get(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
        )
        assert initial.status_code == 200, initial.text
        assert initial.json()["source_type"] == "custom"
        assert initial.json()["revision"] == 1
        assert initial.json()["updated_by_name"] == "系统导入"
        assert len(initial.json()["material_prices"]) == 18
        assert len(initial.json()["machine_prices"]) == 14
        assert initial.json()["material_prices"][0] == {
            "material": "ABS",
            "grade": "750SW",
            "price_hkd_lb": "8.50",
        }
        assert initial.json()["material_prices"][-1] == {
            "material": "PC料",
            "grade": "2605",
            "price_hkd_lb": "12.50",
        }
        assert initial.json()["machine_prices"][0] == {
            "machine_range": "4A-6A",
            "machine": "80T",
            "shift_price_hkd": "940",
        }
        assert initial.json()["machine_prices"][-1] == {
            "machine_range": "105A",
            "machine": "800T",
            "shift_price_hkd": "4500",
        }

        forbidden = client.put(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
            json={
                "revision": 1,
                "workshop_name": "华兴",
                "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "9.25"}],
                "machine_prices": [{"machine_range": "4A-6A", "machine": "80T", "shift_price_hkd": "999"}],
            },
        )
        assert forbidden.status_code == 403

        logout(client)
        supervisor_profile = login(
            client,
            "iq_baseline_supervisor",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:baseline_read" in supervisor_profile["permissions"]
        assert "internal_quote:baseline_manage" in supervisor_profile["permissions"]

        saved = client.put(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
            json={
                "revision": 1,
                "workshop_name": "华兴",
                "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "9.25"}],
                "machine_prices": [{"machine_range": "4A-6A", "machine": "80T", "shift_price_hkd": "999"}],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["source_type"] == "custom"
        assert saved.json()["revision"] == 2
        assert saved.json()["updated_by_name"] == "iq_baseline_supervisor"

        db_module = importlib.import_module("app.db")
        baseline_service = importlib.import_module("app.services.internal_quote_baseline")
        with db_module.SessionLocal() as db:
            baseline_service.seed_internal_quote_pricing_baseline_defaults(db)
        preserved = client.get(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
        )
        assert preserved.status_code == 200, preserved.text
        assert preserved.json()["revision"] == 2
        assert preserved.json()["updated_by_name"] == "iq_baseline_supervisor"
        assert preserved.json()["material_prices"][0]["price_hkd_lb"] == "9.25"

        stale = client.put(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
            json={
                "revision": 1,
                "workshop_name": "华兴",
                "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "10"}],
                "machine_prices": [{"machine_range": "4A-6A", "machine": "80T", "shift_price_hkd": "1000"}],
            },
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2

        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="BASELINE-SNAPSHOT"),
        )
        assert created.status_code == 201, created.text
        snapshot = client.get(
            f"/api/internal-quotes/{created.json()['id']}/reference-snapshot"
        )
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["snapshot"]["pricing_baseline_revision"] == 2
        assert snapshot.json()["snapshot"]["material_prices"]["ABS|750SW"] == "9.25"
        assert snapshot.json()["snapshot"]["machine_prices"][0]["shift_price_hkd"] == "999"

        logout(client)
        engineering_profile = login(
            client,
            "iq_baseline_engineering",
            "engineering_supervisor",
            "engineering",
        )
        assert "internal_quote:reference_manage" in engineering_profile["permissions"]
        denied_engineering = client.get(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
        )
        assert denied_engineering.status_code == 403


def test_create_validates_mandatory_sections_and_can_select_optional_departments(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_optional_create", "sales_customer_owner", "sales-business")
        missing_assembly = client.post(
            "/api/internal-quotes",
            json=create_payload(
                suffix="MISSING-ASSEMBLY",
                participating_sections=["sales", "engineering", "electronic"],
            ),
        )
        assert missing_assembly.status_code == 422

        created = client.post(
            "/api/internal-quotes",
            json=create_payload(
                suffix="OPTIONAL",
                participating_sections=["sales", "engineering", "electronic", "assembly"],
            ),
        )
        assert created.status_code == 201, created.text
        required = {
            section["department"] for section in created.json()["sections"] if section["is_required"]
        }
        assert required == {"sales", "engineering", "electronic", "assembly"}


def test_business_or_engineering_can_add_optional_participation_later(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_participation_admin", "admin", "*", "*")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="ADD-PARTICIPATION"),
        )
        assert created.status_code == 201, created.text
        quote = created.json()

        inactive_save = client.put(
            f"/api/internal-quotes/{quote['id']}/sections/electronic",
            json={"revision": 1, "payload": {"items": []}},
        )
        assert inactive_save.status_code == 409
        assert "未参与" in inactive_save.json()["detail"]

        added = client.post(
            f"/api/internal-quotes/{quote['id']}/participation",
            json={"revision": 1, "add_sections": ["electronic"]},
        )
        assert added.status_code == 200, added.text
        result = added.json()
        assert result["header_revision"] == 2
        electronic = next(
            section for section in result["sections"] if section["department"] == "electronic"
        )
        assert electronic["is_required"] is True
        assert electronic["status"] == "draft"
        assert electronic["revision"] == 2

        stale = client.post(
            f"/api/internal-quotes/{quote['id']}/participation",
            json={"revision": 1, "add_sections": ["painting"]},
        )
        assert stale.status_code == 409

        summary = client.get(f"/api/internal-quotes/{quote['id']}/summary")
        assert summary.status_code == 200
        assert summary.json()["required_sections"] == 4
        assert len(summary.json()["sections"]) == 4

        timeline = client.get(f"/api/internal-quotes/{quote['id']}/timeline")
        assert any(
            event["action"] == "participation_added"
            for event in timeline.json()["business_events"]
        )


def test_sales_section_state_machine_blocks_stale_revision_and_self_review(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_sales_self", "sales_customer_supervisor", "sales-business")
        created = client.post("/api/internal-quotes", json=create_payload(suffix="FLOW")).json()
        quote_id = created["id"]

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
        assert cloned["target_customer_price"] == "USD 3.50"
        assert all(section["status"] == "draft" and section["revision"] == 1 for section in cloned["sections"])
        assert {
            section["department"] for section in cloned["sections"] if section["is_required"]
        } == {"sales", "engineering", "assembly"}

        wrong_factory = client.get("/api/internal-quotes?factory_id=huadeng")
        assert wrong_factory.status_code == 403


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

        locked = client.put(
            f"/api/internal-quotes/{quote['id']}/sections/sales",
            json={"revision": 1, "payload": {"confirmed": True}},
        )
        assert locked.status_code == 409
