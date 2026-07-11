import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'pricing_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def ensure_test_user(username: str, role_id: str, factory_id: str = "huaxing") -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    department = "sales-business" if role_id.startswith("sales_") else "engineering"

    with db_module.SessionLocal() as db:
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
        db.flush()
        db.add(
            auth_models.AuthUserRole(
                id=f"{user_id}:{role_id}:{factory_id}:{department}",
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.commit()


def login(client: TestClient, username: str, role_id: str | None = None, factory_id: str = "huaxing"):
    if username == "admin":
        password = ADMIN_TEST_PASSWORD
    else:
        assert role_id
        ensure_test_user(username, role_id, factory_id)
        password = "123456"
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()


def run_local_pricing(lines, context):
    order = {"markup": 0, "percent": 1, "fixed": 2}
    calculated_lines = []
    for line in lines:
        gross = line["qty"] * line["unit_price"]
        amount = gross
        applied = []
        rules = sorted(context["rules"], key=lambda rule: order[rule["kind"]])
        for rule in rules:
            if rule.get("product_line") and rule["product_line"] != line.get("product_line"):
                continue
            if rule.get("min_qty") is not None and line["qty"] < rule["min_qty"]:
                continue
            if rule["kind"] == "markup":
                amount += rule["value"]
            elif rule["kind"] == "percent":
                amount -= amount * rule["value"] / 100
            else:
                amount -= rule["value"]
            applied.append(rule["id"])
        calculated_lines.append({
            **line,
            "gross": round(gross, 2),
            "after_discount": round(max(0, amount), 2),
            "applied_rules": applied,
        })

    subtotal = round(sum(line["after_discount"] for line in calculated_lines), 2)
    tier = next((tier for tier in reversed(sorted(context["rebate_tiers"], key=lambda item: item["threshold"])) if tier["threshold"] <= subtotal), None)
    rebate = round(subtotal * tier["rate"] / 100, 2) if tier else 0
    tax = round((subtotal - rebate) * context["tax_rate"] / 100, 2)
    return {
        "lines": calculated_lines,
        "subtotal": subtotal,
        "rebate": {"amount": rebate, "tier": tier},
        "tax": {"amount": tax, "rate": context["tax_rate"]},
        "total": round(subtotal - rebate + tax, 2),
        "currency": context["currency"],
    }


def test_pricing_context_and_quote_submission_are_permission_scoped_and_persisted(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous = client.get("/api/pricing/context?customer_id=buzzbee&factory_id=huaxing")
        assert anonymous.status_code == 401

        profile = login(client, "sales_a", "sales_customer_owner")
        assert "internal_pricing:create" in profile["permissions"]

        context_response = client.get("/api/pricing/context?customer_id=buzzbee&factory_id=huaxing")
        assert context_response.status_code == 200
        context = context_response.json()
        assert context["customer_id"] == "buzzbee"
        assert context["currency"] == "HKD"
        assert context["rules"]

        lines = [
            {"sku": "BB-001", "description": "塑胶主体", "qty": 6000, "unit_price": 8.5, "product_line": "塑胶"},
            {"sku": "BB-002", "description": "彩盒", "qty": 6000, "unit_price": 1.2, "product_line": "包装"},
        ]
        local_result = run_local_pricing(lines, context)
        create_response = client.post("/api/pricing/quotes", json={
            "factory_id": "huaxing",
            "customer_id": "buzzbee",
            "project_name": "露营火堆套装",
            "lines": lines,
            "local_result": local_result,
        })
        assert create_response.status_code == 201
        created = create_response.json()
        assert created["id"].startswith("IQ-")
        assert created["project_name"] == "露营火堆套装"
        assert created["result"] == local_result
        assert created["created_by"] == "user-sales_a"

        list_response = client.get("/api/pricing/quotes?factory_id=huaxing&customer_id=buzzbee")
        assert list_response.status_code == 200
        assert [quote["id"] for quote in list_response.json()] == [created["id"]]


def test_quote_submission_rejects_tampered_totals_and_wrong_factory_scope(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "sales_a", "sales_customer_owner")
        context = client.get("/api/pricing/context?customer_id=disney&factory_id=huaxing").json()
        lines = [{"sku": "DS-001", "description": "玩具", "qty": 1000, "unit_price": 10, "product_line": "玩具"}]
        tampered = run_local_pricing(lines, context)
        tampered["total"] += 1

        mismatch = client.post("/api/pricing/quotes", json={
            "factory_id": "huaxing",
            "customer_id": "disney",
            "project_name": "篡改测试",
            "lines": lines,
            "local_result": tampered,
        })
        assert mismatch.status_code == 409
        assert mismatch.json()["detail"] == "前端测算结果与服务器复算结果不一致"

        out_of_scope = client.get("/api/pricing/context?customer_id=disney&factory_id=huadeng")
        assert out_of_scope.status_code == 403


def test_engineering_user_cannot_use_internal_pricing(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "engineer_pricing", "engineer")
        response = client.get("/api/pricing/context?customer_id=buzzbee&factory_id=huaxing")
        assert response.status_code == 403
