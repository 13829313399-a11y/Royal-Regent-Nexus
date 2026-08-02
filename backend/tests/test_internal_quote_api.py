import importlib
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote as url_quote
from uuid import uuid4

import pytest
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
    "hair",
    "assembly",
]
DEFAULT_FREIGHT_ROUTES = [
    {"route_key": "hk40", "route_name": "HK 40 柜", "capacity_key": "cap_40", "freight_hkd": "8000", "lifting_hkd": "0"},
    {"route_key": "hk20", "route_name": "HK 20 柜", "capacity_key": "cap_20", "freight_hkd": "7100", "lifting_hkd": "0"},
    {"route_key": "yt40", "route_name": "YT 40 柜", "capacity_key": "cap_40", "freight_hkd": "7200", "lifting_hkd": "0"},
    {"route_key": "yt20", "route_name": "YT 20 柜", "capacity_key": "cap_20", "freight_hkd": "6000", "lifting_hkd": "0"},
    {"route_key": "hk10t", "route_name": "HK 10 吨车", "capacity_key": "cap_10t", "freight_hkd": "14900", "lifting_hkd": "0"},
    {"route_key": "yt10t", "route_name": "YT 10 吨车", "capacity_key": "cap_10t", "freight_hkd": "11500", "lifting_hkd": "0"},
    {"route_key": "hk5t", "route_name": "HK 5 吨车", "capacity_key": "cap_5t", "freight_hkd": "12500", "lifting_hkd": "0"},
    {"route_key": "yt5t", "route_name": "YT 5 吨车", "capacity_key": "cap_5t", "freight_hkd": "11000", "lifting_hkd": "0"},
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


def grant_user_permission(
    username: str,
    permission_code: str,
    department: str,
    factory_id: str = "huaxing",
) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    with db_module.SessionLocal() as db:
        permission = db.query(auth_models.AuthPermission).filter_by(code=permission_code).one()
        timestamp = auth_service.now_text()
        db.add(
            auth_models.AuthUserPermissionOverride(
                id=f"override-{username}-{permission_code.replace(':', '-')}",
                user_id=f"user-{username}",
                permission_id=permission.id,
                effect="allow",
                factory_id=factory_id,
                department=department,
                status="active",
                valid_from=timestamp,
                valid_until="",
                reason="测试个人授权",
                source_type="manual",
                created_by_user_id="user-admin",
                approved_by_user_id="user-admin",
                created_at=timestamp,
                updated_at=timestamp,
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


def test_mapped_import_template_download_requires_quote_access_and_returns_xlsx(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get("/api/internal-quotes/quote-missing/imports/mold/template")
        assert anonymous.status_code == 401

        login(client, "iq_template_download", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="TEMPLATE", participating_sections=ALL_SECTION_CODES),
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        response = client.get(f"/api/internal-quotes/{quote_id}/imports/molding/template")
        assert response.status_code == 200, response.text
        assert response.content.startswith(b"PK")
        assert response.headers["content-type"].startswith(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        assert response.headers["content-disposition"].startswith("attachment; filename*=UTF-8''")
        assert response.headers["content-disposition"].endswith("-2026.07.xlsx")

        fixed_templates = {
            "mold": "展兴模具--工模报价表.xlsx",
            "assembly": "装工.xlsx",
            "hardware": "五金1.xlsx",
            "painting": "喷油报价单.xlsx",
            "electronic": "电子报价单.xlsx",
            "sewing": "车缝报价单.xlsx",
        }
        for import_type, file_name in fixed_templates.items():
            fixed_response = client.get(
                f"/api/internal-quotes/{quote_id}/imports/{import_type}/template"
            )
            assert fixed_response.status_code == 200, fixed_response.text
            assert fixed_response.content == (
                BACKEND_DIR
                / "app"
                / "data"
                / "internal_quote_import_templates"
                / file_name
            ).read_bytes()
            assert fixed_response.headers["content-disposition"] == (
                f"attachment; filename*=UTF-8''{url_quote(file_name)}"
            )

        invalid = client.get(f"/api/internal-quotes/{quote_id}/imports/unknown/template")
        assert invalid.status_code == 400


def test_sales_create_keeps_all_section_slots_but_only_mandatory_departments_participate(monkeypatch):
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
        assert len(quote["sections"]) == 9
        assert [section["department"] for section in quote["sections"]] == [
            "sales",
            "engineering",
            "electronic",
            "molding",
            "painting",
            "slush",
            "sewing",
            "hair",
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


def test_quote_header_can_only_change_before_section_work_starts(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_header_editor", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="HEADER-EDIT"),
        )
        assert created.status_code == 201, created.text
        quote = created.json()

        updated = client.patch(
            f"/api/internal-quotes/{quote['id']}",
            json={"revision": quote["header_revision"], "product_name": "填写前修正产品名"},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["product_name"] == "填写前修正产品名"
        assert updated.json()["header_revision"] == quote["header_revision"] + 1

        saved = client.put(
            f"/api/internal-quotes/{quote['id']}/sections/sales",
            json={"revision": 1, "payload": {"currency": "HKD", "confirmed": True}},
        )
        assert saved.status_code == 200, saved.text
        blocked = client.patch(
            f"/api/internal-quotes/{quote['id']}",
            json={"revision": updated.json()["header_revision"], "qty": 2000},
        )
        assert blocked.status_code == 409
        assert "协作填写前" in blocked.json()["detail"]


def test_quote_delete_allows_creator_or_local_sales_supervisor_and_protects_released_records(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_delete_creator", "sales_customer_owner", "sales-business")
        creator_quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="DELETE-CREATOR"),
        )
        assert creator_quote.status_code == 201, creator_quote.text
        creator_quote_id = creator_quote.json()["id"]

        stale = client.delete(
            f"/api/internal-quotes/{creator_quote_id}",
            params={"revision": 2},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 1

        forbidden_quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="DELETE-SUPERVISOR"),
        )
        assert forbidden_quote.status_code == 201, forbidden_quote.text
        forbidden_quote_id = forbidden_quote.json()["id"]

        logout(client)
        login(client, "iq_delete_other_owner", "sales_customer_owner", "sales-business")
        forbidden = client.delete(
            f"/api/internal-quotes/{forbidden_quote_id}",
            params={"revision": 1},
        )
        assert forbidden.status_code == 403
        assert forbidden.json()["detail"] == "仅建单人或本厂区业务主管可删除内部报价"

        logout(client)
        login(client, "iq_delete_supervisor", "sales_customer_supervisor", "sales-business")
        supervisor_deleted = client.delete(
            f"/api/internal-quotes/{forbidden_quote_id}",
            params={"revision": 1},
        )
        assert supervisor_deleted.status_code == 204, supervisor_deleted.text
        assert client.get(f"/api/internal-quotes/{forbidden_quote_id}").status_code == 404

        logout(client)
        login(client, "iq_delete_creator", "sales_customer_owner", "sales-business")
        creator_deleted = client.delete(
            f"/api/internal-quotes/{creator_quote_id}",
            params={"revision": 1},
        )
        assert creator_deleted.status_code == 204, creator_deleted.text

        protected_quote = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="DELETE-PROTECTED"),
        )
        assert protected_quote.status_code == 201, protected_quote.text
        protected_quote_id = protected_quote.json()["id"]
        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            record = db.get(quote_models.InternalQuote, protected_quote_id)
            record.status = "released"
            record.final_release_status = "approved"
            db.commit()

        protected = client.delete(
            f"/api/internal-quotes/{protected_quote_id}",
            params={"revision": 1},
        )
        assert protected.status_code == 409
        assert "请使用归档保留审计记录" in protected.json()["detail"]

        with db_module.SessionLocal() as db:
            assert db.get(quote_models.InternalQuote, creator_quote_id) is None
            assert db.query(quote_models.InternalQuoteSection).filter_by(quote_id=creator_quote_id).count() == 0
            deletion_audits = db.query(auth_models.AuthAuditLog).filter_by(
                action="internal_quote_deleted"
            ).all()
            assert len(deletion_audits) == 2
            assert any("DELETE-CREATOR" in item.detail for item in deletion_audits)
            assert any("DELETE-SUPERVISOR" in item.detail for item in deletion_audits)


def test_section_live_preview_uses_authoritative_calculator_without_persisting(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_live_preview_engineer", "engineer", "engineering")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(initiator_department="engineering", suffix="LIVE-PREVIEW"),
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        saved_payload = {
            "materials": [
                {
                    "item": "五金件",
                    "category": "hardware",
                    "quantity": "2",
                    "unit_price_rmb": "8.5",
                }
            ],
            "molds": [],
            "production_mold_fees": [],
        }
        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/engineering",
            json={"revision": 1, "payload": saved_payload},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 2
        assert saved.json()["calculation"]["totals"]["hardware_hkd"] == "20.0000"

        before_summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert before_summary.status_code == 200, before_summary.text
        assert before_summary.json()["factory_price_hkd"] == "20.0000"

        preview_payload = {
            **saved_payload,
            "materials": [{**saved_payload["materials"][0], "loss_rate": "1.02"}],
        }
        preview = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/preview",
            json={"revision": 2, "payload": preview_payload},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["calculation_status"] == "valid"
        assert preview.json()["saved_factory_price_hkd"] == "20.0000"
        assert preview.json()["preview_factory_price_hkd"] == "20.4000"
        assert preview.json()["delta_hkd"] == "0.4000"
        assert preview.json()["components_hkd"]["hardware_hkd"] == "20.4000"
        assert preview.json()["calculation"]["line_breakdown"][0]["loss_rate"] == "1.0200"

        # A live preview must not create a revision, audit event, or saved amount.
        section = client.get(f"/api/internal-quotes/{quote_id}").json()["sections"]
        engineering = next(item for item in section if item["department"] == "engineering")
        assert engineering["revision"] == 2
        assert engineering["payload"] == saved_payload
        revisions = client.get(
            f"/api/internal-quotes/{quote_id}/sections/engineering/revisions"
        )
        assert [item["revision"] for item in revisions.json()] == [2, 1]
        after_summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert after_summary.json()["factory_price_hkd"] == "20.0000"

        stale = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/preview",
            json={"revision": 1, "payload": preview_payload},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 2


def test_sales_markup_selection_and_misc_ratio_survive_save_detail_and_summary_reload(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_sales_pricing_persistence", "sales_customer_owner", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="SALES-PRICING-PERSIST"),
        )
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]
        payload = {
            "paper_price_factor": 2.75,
            "testing_fee_total_usd": 1250,
            "testing_fee_moqs": [5000, 10000],
            "packaging_materials": [],
            "product_size_in": {"length": 0, "width": 0, "height": 0},
            "color_box_size_unit": "inch",
            "color_box_size_in": {"length": 0, "width": 0, "height": 0},
            "cartons": [],
            "freight_calc": {"enabled": False},
            "shipping": {
                "markup_x": 1.25,
                "markup_tiers": [
                    {"moq": 3000, "markup_x": 1.25},
                    {"moq": 5000, "markup_x": 1.20},
                    {"moq": 10000, "markup_x": 1.15},
                ],
                "selected_markup_moq": 3000,
                "misc_ratio": 0.035,
            },
        }

        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": payload, "reason": "保存人工选档和杂项"},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["payload"]["shipping"]["misc_ratio"] == 0.035
        assert saved.json()["payload"]["shipping"]["selected_markup_moq"] == 3000
        assert saved.json()["payload"]["testing_fee_total_usd"] == 1250
        assert saved.json()["payload"]["testing_fee_moqs"] == [5000, 10000]
        assert saved.json()["calculation"]["totals"]["testing_fee_moqs"] == ["5000.0000", "10000.0000"]
        assert saved.json()["calculation"]["totals"]["testing_fee_tiers"] == [
            {"moq": "5000.0000", "unit_price_usd": "0.2500"},
            {"moq": "10000.0000", "unit_price_usd": "0.1250"},
        ]
        assert saved.json()["calculation"]["totals"]["testing_fee_unit_usd"] == "0.2500"

        detail = client.get(f"/api/internal-quotes/{quote_id}")
        assert detail.status_code == 200, detail.text
        sales = next(item for item in detail.json()["sections"] if item["department"] == "sales")
        assert sales["payload"]["shipping"]["misc_ratio"] == 0.035
        assert sales["payload"]["shipping"]["selected_markup_moq"] == 3000
        assert sales["payload"]["testing_fee_total_usd"] == 1250
        assert sales["payload"]["testing_fee_moqs"] == [5000, 10000]
        assert sales["calculation"]["totals"]["testing_fee_moqs"] == ["5000.0000", "10000.0000"]
        assert sales["calculation"]["totals"]["testing_fee_unit_usd"] == "0.2500"

        summary = client.get(f"/api/internal-quotes/{quote_id}/summary")
        assert summary.status_code == 200, summary.text
        pricing = summary.json()["rr2_cost_summary"]["shipping_pricing"]
        assert pricing["misc_ratio"] == "0.0350"
        assert pricing["active_markup_moq"] == "3000.0000"
        assert pricing["markup"] == "1.2500"
        assert [item["is_active"] for item in pricing["markup_tiers"]] == [True, False, False]


def test_factory_customers_are_readable_but_only_managed_by_local_sales_supervisor(monkeypatch):
    with make_client(monkeypatch) as client:
        owner_profile = login(
            client,
            "iq_customer_owner",
            "sales_customer_owner",
            "sales-business",
        )
        assert "internal_quote:customer_manage" not in owner_profile["permissions"]
        initial = client.get(
            "/api/internal-quotes/customers",
            params={"factory_id": "huaxing"},
        )
        assert initial.status_code == 200, initial.text
        assert initial.json() == []
        forbidden = client.post(
            "/api/internal-quotes/customers",
            params={"factory_id": "huaxing"},
            json={"name": "Owner Cannot Add"},
        )
        assert forbidden.status_code == 403

        logout(client)
        supervisor_profile = login(
            client,
            "iq_customer_supervisor",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:customer_manage" in supervisor_profile["permissions"]
        created = client.post(
            "/api/internal-quotes/customers",
            params={"factory_id": "huaxing"},
            json={"name": "Alpha Client"},
        )
        assert created.status_code == 201, created.text
        customer = created.json()
        assert customer["factory_id"] == "huaxing"
        assert customer["revision"] == 1

        duplicate = client.post(
            "/api/internal-quotes/customers",
            params={"factory_id": "huaxing"},
            json={"name": " alpha   client "},
        )
        assert duplicate.status_code == 409

        cross_factory = client.post(
            "/api/internal-quotes/customers",
            params={"factory_id": "huadeng"},
            json={"name": "Wrong Factory"},
        )
        assert cross_factory.status_code == 403

        stale = client.put(
            f"/api/internal-quotes/customers/{customer['id']}",
            json={"name": "Alpha Renamed", "revision": 2},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["current_revision"] == 1

        updated = client.put(
            f"/api/internal-quotes/customers/{customer['id']}",
            json={"name": "Alpha Renamed", "revision": 1},
        )
        assert updated.status_code == 200, updated.text
        assert updated.json()["name"] == "Alpha Renamed"
        assert updated.json()["revision"] == 2

        quote_payload = create_payload(suffix="CUSTOMER-HISTORY")
        quote_payload["customer"] = "Alpha Renamed"
        quote = client.post("/api/internal-quotes", json=quote_payload)
        assert quote.status_code == 201, quote.text

        deleted = client.delete(
            f"/api/internal-quotes/customers/{customer['id']}",
            params={"revision": 2},
        )
        assert deleted.status_code == 204, deleted.text
        remaining = client.get(
            "/api/internal-quotes/customers",
            params={"factory_id": "huaxing"},
        )
        assert remaining.status_code == 200
        assert remaining.json() == []
        historical_quote = client.get(f"/api/internal-quotes/{quote.json()['id']}")
        assert historical_quote.status_code == 200
        assert historical_quote.json()["customer"] == "Alpha Renamed"


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
        assert initial.json()["freight_routes"] == DEFAULT_FREIGHT_ROUTES

        forbidden = client.put(
            "/api/internal-quotes/pricing-baseline",
            params={"factory_id": "huaxing", "workshop_code": "huaxing-workshop"},
            json={
                "revision": 1,
                "workshop_name": "华兴",
                "material_prices": [{"material": "ABS", "grade": "750SW", "price_hkd_lb": "9.25"}],
                "machine_prices": [{"machine_range": "4A-6A", "machine": "80T", "shift_price_hkd": "999"}],
                "freight_routes": DEFAULT_FREIGHT_ROUTES,
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
                "freight_routes": [
                    {**DEFAULT_FREIGHT_ROUTES[0], "route_name": "香港 40 柜", "freight_hkd": "8200", "lifting_hkd": "1300"},
                    *DEFAULT_FREIGHT_ROUTES[2:],
                    {"route_key": "hk8t", "route_name": "HK 8 吨车", "capacity_key": "8 吨车容量", "freight_hkd": "6500", "lifting_hkd": "1100"},
                ],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["source_type"] == "custom"
        assert saved.json()["revision"] == 2
        assert saved.json()["updated_by_name"] == "iq_baseline_supervisor"
        saved_routes = saved.json()["freight_routes"]
        assert len(saved_routes) == 8
        assert saved_routes[0] == {
            "route_key": "hk40",
            "route_name": "香港 40 柜",
            "capacity_key": "cap_40",
            "freight_hkd": "8200",
            "lifting_hkd": "1300",
        }
        assert all(row["route_key"] != "hk20" for row in saved_routes)
        assert saved_routes[-1] == {
            "route_key": "hk8t",
            "route_name": "HK 8 吨车",
            "capacity_key": "8 吨车容量",
            "freight_hkd": "6500",
            "lifting_hkd": "1100",
        }

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
        assert preserved.json()["freight_routes"] == saved_routes

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
        assert snapshot.json()["snapshot"]["freight"]["routes"] == saved_routes

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

        logout(client)
        engineering_profile = login(
            client,
            "iq_participation_engineering",
            "engineering_supervisor",
            "engineering",
        )
        assert "internal_quote:create" in engineering_profile["permissions"]
        removed = client.post(
            f"/api/internal-quotes/{quote['id']}/participation/remove",
            json={"revision": 2, "remove_sections": ["electronic"]},
        )
        assert removed.status_code == 200, removed.text
        removed_result = removed.json()
        assert removed_result["header_revision"] == 3
        electronic = next(
            section
            for section in removed_result["sections"]
            if section["department"] == "electronic"
        )
        assert electronic["is_required"] is False
        assert electronic["status"] == "draft"
        assert electronic["payload"] == {}
        assert electronic["calculation"] == {}
        assert electronic["revision"] == 3

        mandatory = client.post(
            f"/api/internal-quotes/{quote['id']}/participation/remove",
            json={"revision": 3, "remove_sections": ["sales"]},
        )
        assert mandatory.status_code == 422
        assert any(
            "不能移除" in item["msg"]
            for item in mandatory.json()["detail"]
        )

        removed_summary = client.get(f"/api/internal-quotes/{quote['id']}/summary")
        assert removed_summary.status_code == 200
        assert removed_summary.json()["required_sections"] == 3
        assert all(
            section["section_code"] != "electronic"
            for section in removed_summary.json()["sections"]
        )

        removed_timeline = client.get(f"/api/internal-quotes/{quote['id']}/timeline")
        assert any(
            event["action"] == "participation_removed"
            and "electronic" in event["detail"]
            for event in removed_timeline.json()["business_events"]
        )

        readded = client.post(
            f"/api/internal-quotes/{quote['id']}/participation",
            json={"revision": 3, "add_sections": ["electronic"]},
        )
        assert readded.status_code == 200, readded.text
        readded_electronic = next(
            section
            for section in readded.json()["sections"]
            if section["department"] == "electronic"
        )
        assert readded_electronic["is_required"] is True
        assert readded_electronic["revision"] == 4

        logout(client)
        login(client, "iq_participation_molding", "molding_clerk", "molding")
        forbidden = client.post(
            f"/api/internal-quotes/{quote['id']}/participation/remove",
            json={"revision": 4, "remove_sections": ["electronic"]},
        )
        assert forbidden.status_code == 403

        logout(client)
        sales_profile = login(
            client,
            "iq_participation_sales",
            "sales_customer_supervisor",
            "sales-business",
        )
        assert "internal_quote:create" in sales_profile["permissions"]
        removed_by_sales = client.post(
            f"/api/internal-quotes/{quote['id']}/participation/remove",
            json={"revision": 4, "remove_sections": ["electronic"]},
        )
        assert removed_by_sales.status_code == 200, removed_by_sales.text
        assert next(
            section
            for section in removed_by_sales.json()["sections"]
            if section["department"] == "electronic"
        )["is_required"] is False


def test_sales_section_state_machine_blocks_stale_revision_and_self_review(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user("iq_sales_reviewer", "sales_customer_supervisor", "sales-business")
        login(client, "iq_sales_self", "sales_customer_supervisor", "sales-business")
        payload = create_payload(suffix="FLOW")
        payload.update(
            {
                "business_owner_id": "user-iq_sales_reviewer",
                "business_owner_name": "iq_sales_reviewer",
            }
        )
        created = client.post("/api/internal-quotes", json=payload).json()
        quote_id = created["id"]
        created_notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "quote_created"
            and item["payload"].get("department") == "sales"
        )
        assert created_notification["payload"]["route"] == (
            f"/modules/sales-business/internal-quote-desk/{quote_id}/collaboration"
            "?factory=huaxing&section=sales"
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

        self_review = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={"revision": 3, "decision": "approve", "reason": ""},
        )
        assert self_review.status_code == 403

        logout(client)
        login(client, "iq_sales_other_reviewer", "sales_customer_supervisor", "sales-business")
        non_selected_review = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={"revision": 3, "decision": "approve", "reason": "非指定审核人"},
        )
        assert non_selected_review.status_code == 403
        assert "指定的业务审核负责人" in non_selected_review.json()["detail"]

        logout(client)
        login(client, "iq_sales_reviewer", "sales_customer_supervisor", "sales-business")
        review_notification = next(
            item
            for item in client.get("/api/system/notifications").json()
            if item["payload"].get("quote_id") == quote_id
            and item["payload"].get("event") == "section_submitted"
            and item["payload"].get("department") == "sales"
        )
        assert review_notification["payload"]["route"] == (
            f"/modules/sales-business/internal-quote-desk/{quote_id}/collaboration"
            "?factory=huaxing&section=sales"
        )
        assert review_notification["status"] == "unread"
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


def test_business_supervisor_can_self_review_an_owned_self_created_quote(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        profile = login(
            client,
            "iq_supervisor_self_review",
            "position_sales_supervisor",
            "sales-business",
        )
        assert "internal_quote:self_review" in profile["permissions"]
        payload = create_payload(suffix="SUPERVISOR-SELF")
        payload.update(
            {
                "business_owner_id": "user-iq_supervisor_self_review",
                "business_owner_name": "iq_supervisor_self_review",
            }
        )
        created = client.post("/api/internal-quotes", json=payload)
        assert created.status_code == 201, created.text
        quote_id = created.json()["id"]

        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"currency": "HKD", "confirmed": True}},
        )
        assert saved.status_code == 200, saved.text
        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/submit",
            json={"revision": saved.json()["revision"]},
        )
        assert submitted.status_code == 200, submitted.text

        approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/review",
            json={
                "revision": submitted.json()["revision"],
                "decision": "approve",
                "reason": "业务主管本人报价自审",
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["reviewed_by"] == "iq_supervisor_self_review"


def test_personal_self_review_permission_is_limited_to_own_created_quotes(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        username = "iq_independent_sales_self_review"
        ensure_user(username, "position_sales_business", "sales-business")
        grant_user_permission(
            username,
            "internal_quote:self_review",
            "sales-business",
        )
        profile = login(
            client,
            username,
            "position_sales_business",
            "sales-business",
        )
        assert "internal_quote:self_review" in profile["permissions"]

        owner_options = client.get(
            "/api/internal-quotes/business-owners?factory_id=huaxing"
        )
        assert owner_options.status_code == 200, owner_options.text
        assert f"user-{username}" in {item["id"] for item in owner_options.json()}

        def create_and_submit(suffix: str) -> tuple[str, int]:
            payload = create_payload(suffix=suffix)
            payload.update(
                {
                    "business_owner_id": f"user-{username}",
                    "business_owner_name": username,
                }
            )
            created = client.post("/api/internal-quotes", json=payload)
            assert created.status_code == 201, created.text
            quote_id = created.json()["id"]
            saved = client.put(
                f"/api/internal-quotes/{quote_id}/sections/sales",
                json={"revision": 1, "payload": {"currency": "HKD", "confirmed": True}},
            )
            assert saved.status_code == 200, saved.text
            submitted = client.post(
                f"/api/internal-quotes/{quote_id}/sections/sales/submit",
                json={"revision": saved.json()["revision"]},
            )
            assert submitted.status_code == 200, submitted.text
            return quote_id, submitted.json()["revision"]

        owned_quote_id, owned_revision = create_and_submit("PERSONAL-SELF")
        approved = client.post(
            f"/api/internal-quotes/{owned_quote_id}/sections/sales/review",
            json={
                "revision": owned_revision,
                "decision": "approve",
                "reason": "个人授权自审",
            },
        )
        assert approved.status_code == 200, approved.text

        foreign_quote_id, foreign_revision = create_and_submit("PERSONAL-FOREIGN")
        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        with db_module.SessionLocal() as db:
            foreign_quote = db.get(quote_models.InternalQuote, foreign_quote_id)
            foreign_quote.created_by = "user-another-creator"
            foreign_quote.created_by_name = "其他建单人"
            db.commit()

        forbidden = client.post(
            f"/api/internal-quotes/{foreign_quote_id}/sections/sales/review",
            json={
                "revision": foreign_revision,
                "decision": "approve",
                "reason": "不应允许审核别人创建的报价",
            },
        )
        assert forbidden.status_code == 403, forbidden.text
        assert "仅适用于本人创建" in forbidden.json()["detail"]


def test_submitter_can_withdraw_before_review_and_duplicate_save_keeps_revision(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_sales_withdraw_owner", "sales_customer_supervisor", "sales-business")
        created = client.post(
            "/api/internal-quotes",
            json=create_payload(suffix="WITHDRAW"),
        ).json()
        quote_id = created["id"]
        initial_payload = {"currency": "HKD", "confirmed": True}

        saved = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": initial_payload},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["revision"] == 2

        duplicate = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 2, "payload": {"confirmed": True, "currency": "HKD"}},
        )
        assert duplicate.status_code == 200, duplicate.text
        assert duplicate.json()["revision"] == 2
        revisions_after_duplicate = client.get(
            f"/api/internal-quotes/{quote_id}/sections/sales/revisions"
        )
        assert [item["revision"] for item in revisions_after_duplicate.json()] == [2, 1]

        changed_payload = {**initial_payload, "remark": "修改后的内容"}
        changed = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 2, "payload": changed_payload},
        )
        assert changed.status_code == 200, changed.text
        assert changed.json()["revision"] == 3

        submitted = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/submit",
            json={"revision": 3},
        )
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["status"] == "pending_review"
        assert submitted.json()["revision"] == 4
        assert submitted.json()["submitted_by_id"] == "user-iq_sales_withdraw_owner"

        logout(client)
        login(client, "iq_sales_withdraw_other", "sales_customer_supervisor", "sales-business")
        forbidden = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/withdraw",
            json={"revision": 4},
        )
        assert forbidden.status_code == 403
        assert "仅原提交人" in forbidden.json()["detail"]

        logout(client)
        login(client, "iq_sales_withdraw_owner", "sales_customer_supervisor", "sales-business")
        withdrawn = client.post(
            f"/api/internal-quotes/{quote_id}/sections/sales/withdraw",
            json={"revision": 4},
        )
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()["status"] == "draft"
        assert withdrawn.json()["revision"] == 5
        assert withdrawn.json()["submitted_by_id"] == ""

        duplicate_after_withdraw = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 5, "payload": changed_payload},
        )
        assert duplicate_after_withdraw.status_code == 200, duplicate_after_withdraw.text
        assert duplicate_after_withdraw.json()["revision"] == 5

        timeline = client.get(f"/api/internal-quotes/{quote_id}/timeline")
        assert timeline.status_code == 200
        assert any(event["action"] == "withdraw" for event in timeline.json()["business_events"])


def test_na_reopen_clone_and_cross_department_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        ensure_user("iq_business_owner_option", "sales_customer_supervisor", "sales-business")
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
        payload = create_payload(initiator_department="engineering", suffix="ENG")
        payload.update(
            {
                "business_owner_id": "user-iq_business_owner_option",
                "business_owner_name": "iq_business_owner_option",
            }
        )
        created_response = client.post(
            "/api/internal-quotes",
            json=payload,
        )
        assert created_response.status_code == 201
        created = created_response.json()
        quote_id = created["id"]

        editable_sales = client.put(
            f"/api/internal-quotes/{quote_id}/sections/sales",
            json={"revision": 1, "payload": {"blocked": True}},
        )
        assert editable_sales.status_code == 200, editable_sales.text
        assert editable_sales.json()["revision"] == 2

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
        assert na_approved.status_code == 403

        logout(client)
        login(client, "iq_business_owner_option", "sales_customer_supervisor", "sales-business")
        na_approved = client.post(
            f"/api/internal-quotes/{quote_id}/sections/engineering/review",
            json={"revision": 2, "decision": "approve", "reason": "确认不适用"},
        )
        assert na_approved.status_code == 200
        assert na_approved.json()["status"] == "not_applicable"

        logout(client)
        login(client, "iq_engineer_creator", "engineer", "engineering")
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


def test_business_owner_options_only_include_users_with_sales_review_permission(monkeypatch):
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    with make_client(monkeypatch) as client:
        ensure_user(
            "iq_fixed_sales_owner",
            "position_sales_supervisor",
            "sales-business",
        )
        ensure_user(
            "iq_revoked_fixed_sales_owner",
            "position_sales_supervisor",
            "sales-business",
        )
        ensure_user(
            "iq_sales_owner_without_review",
            "position_sales_business",
            "sales-business",
        )
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        revoked_binding_id = (
            "user-iq_revoked_fixed_sales_owner:position_sales_supervisor:"
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
        assert "user-iq_sales_owner_without_review" not in owner_ids
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
        assert len(row["sections"]) == 9
        assert all(section["revision"] == 1 for section in row["sections"])


def test_internal_quote_list_page_loads_only_ten_rows_and_reports_remaining_pages(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_list_page", "sales_customer_owner", "sales-business")
        created_ids: list[str] = []
        for index in range(12):
            payload = create_payload(suffix=f"PAGE-{index:02d}")
            payload["customer"] = "分页客户A" if index % 2 == 0 else "分页客户B"
            created = client.post("/api/internal-quotes", json=payload)
            assert created.status_code == 201, created.text
            created_ids.append(created.json()["id"])

        first = client.get(
            "/api/internal-quotes",
            params={"factory_id": "huaxing", "page": 1, "page_size": 10, "include_sections": True},
        )
        assert first.status_code == 200, first.text
        first_page = first.json()
        assert first_page["total"] == 12
        assert first_page["page"] == 1
        assert first_page["page_size"] == 10
        assert first_page["total_pages"] == 2
        assert len(first_page["items"]) == 10
        assert all(len(item["sections"]) == 9 for item in first_page["items"])
        assert first_page["customers"] == ["分页客户A", "分页客户B"]

        second = client.get(
            "/api/internal-quotes",
            params={"factory_id": "huaxing", "page": 2, "page_size": 10},
        )
        assert second.status_code == 200, second.text
        second_page = second.json()
        assert len(second_page["items"]) == 2
        assert not ({item["id"] for item in first_page["items"]} & {item["id"] for item in second_page["items"]})
        assert {item["id"] for item in first_page["items"] + second_page["items"]} == set(created_ids)

        filtered = client.get(
            "/api/internal-quotes",
            params={"factory_id": "huaxing", "page": 1, "page_size": 10, "customer": "分页客户A"},
        )
        assert filtered.status_code == 200, filtered.text
        assert filtered.json()["total"] == 6
        assert all(item["customer"] == "分页客户A" for item in filtered.json()["items"])


def test_internal_quote_dashboard_reports_period_status_customer_progress_and_speed(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "iq_dashboard", "sales_customer_owner", "sales-business")
        definitions = [
            ("DASH-A-DONE", "客户A"),
            ("DASH-A-WIP", "客户A"),
            ("DASH-B-DONE", "客户B"),
            ("DASH-C-CANCEL", "客户C"),
            ("DASH-OLD", "历史客户"),
        ]
        quote_ids: dict[str, str] = {}
        for suffix, customer in definitions:
            payload = create_payload(suffix=suffix)
            payload["customer"] = customer
            created = client.post("/api/internal-quotes", json=payload)
            assert created.status_code == 201, created.text
            quote_ids[suffix] = created.json()["id"]

        db_module = importlib.import_module("app.db")
        quote_models = importlib.import_module("app.models.internal_quote")
        quote_service = importlib.import_module("app.services.internal_quote")
        week_start, week_end, _ = quote_service._dashboard_period_bounds("week")
        year_start, _, _ = quote_service._dashboard_period_bounds("year")
        available_seconds = max(4.0, (week_end - week_start).total_seconds())
        speed_unit = min(3600.0, available_seconds / 4)

        with db_module.SessionLocal() as db:
            done_a = db.get(quote_models.InternalQuote, quote_ids["DASH-A-DONE"])
            active_a = db.get(quote_models.InternalQuote, quote_ids["DASH-A-WIP"])
            done_b = db.get(quote_models.InternalQuote, quote_ids["DASH-B-DONE"])
            canceled_c = db.get(quote_models.InternalQuote, quote_ids["DASH-C-CANCEL"])
            old_quote = db.get(quote_models.InternalQuote, quote_ids["DASH-OLD"])
            assert done_a and active_a and done_b and canceled_c and old_quote

            current_stamp = week_start.strftime("%Y-%m-%d %H:%M:%S")
            for quote in (done_a, active_a, done_b, canceled_c):
                quote.created_at = current_stamp
                quote.updated_at = current_stamp

            done_a.status = "fully_approved"
            done_a.final_release_status = "approved"
            done_a.final_reviewed_at = (week_start + timedelta(seconds=speed_unit)).strftime("%Y-%m-%d %H:%M:%S")
            done_a.updated_at = done_a.final_reviewed_at
            done_b.status = "exported"
            done_b.final_release_status = "approved"
            done_b.final_reviewed_at = (week_start + timedelta(seconds=speed_unit * 2)).strftime("%Y-%m-%d %H:%M:%S")
            done_b.updated_at = done_b.final_reviewed_at
            canceled_c.status = "archived"
            canceled_c.archived_at = current_stamp
            old_quote.status = "fully_approved"
            old_quote.created_at = (year_start - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
            old_quote.updated_at = old_quote.created_at
            old_quote.final_reviewed_at = old_quote.created_at

            required_sections = (
                db.query(quote_models.InternalQuoteSection)
                .filter(
                    quote_models.InternalQuoteSection.quote_id == active_a.id,
                    quote_models.InternalQuoteSection.is_required.is_(True),
                )
                .order_by(quote_models.InternalQuoteSection.department)
                .all()
            )
            assert len(required_sections) == 3
            required_sections[0].status = "approved"
            db.commit()

        for period in ("week", "month", "year"):
            response = client.get(
                "/api/internal-quotes/dashboard",
                params={"factory_id": "huaxing", "period": period},
            )
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["period"] == period
            assert data["totals"] == {"total": 4, "in_progress": 1, "completed": 2, "canceled": 1}
            assert {item["key"]: item["count"] for item in data["status_distribution"]} == {
                "in_progress": 1,
                "completed": 2,
                "canceled": 1,
            }
            assert data["customer_quote_counts"][0]["customer"] == "客户A"
            assert data["customer_quote_counts"][0]["count"] == 2
            assert data["progress_items"] == [
                {
                    "quote_id": quote_ids["DASH-A-WIP"],
                    "quote_no": "IQ-TEST-DASH-A-WIP",
                    "product_name": "内部报价测试产品",
                    "customer": "客户A",
                    "status": "drafting",
                    "approved_sections": 1,
                    "required_sections": 3,
                    "percentage": 33.3,
                    "updated_at": current_stamp,
                }
            ]
            assert [item["customer"] for item in data["customer_speed"]] == ["客户A", "客户B"]
            assert data["customer_speed"][0]["average_hours"] < data["customer_speed"][1]["average_hours"]


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
