from io import BytesIO
import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"
EDGE_TOKEN = "edge-test-token-that-is-not-a-production-secret"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    run_id = uuid4().hex
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{TEST_TMP_DIR / f'three_d_printing_{run_id}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    monkeypatch.setenv("THREE_D_EDGE_AGENT_TOKEN", EDGE_TOKEN)
    monkeypatch.setenv(
        "THREE_D_ASSET_DIR",
        str(TEST_TMP_DIR / f"three_d_assets_{run_id}"),
    )

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login(client: TestClient, username: str, password: str = "123456") -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text


def ensure_three_d_operator(username: str) -> None:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
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
        db.add(
            auth_models.AuthUserRole(
                id=f"{user_id}:position_3d_operator:huakang-a:three-d-printing",
                user_id=user_id,
                role_id="position_3d_operator",
                factory_id="huakang-a",
                department="three-d-printing",
            )
        )
        db.commit()


def jpeg_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (80, 60), color=(18, 136, 119)).save(
        output,
        format="JPEG",
        quality=90,
    )
    return output.getvalue()


def test_admin_business_flow_image_storage_and_factory_lock(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)

        initial_dashboard = client.get(
            "/api/three-d-printing/dashboard",
            params={"factory_id": "huakang-a"},
        )
        assert initial_dashboard.status_code == 200, initial_dashboard.text
        assert len(initial_dashboard.json()["printers"]) == 11
        current_settings = initial_dashboard.json()["settings"]
        settings_update = client.put(
            "/api/three-d-printing/settings",
            json={
                "factory_id": "huakang-a",
                "revision": current_settings["revision"],
                "machine_count": 11,
                "electricity_per_machine_day": 1.5,
                "labor_per_day": 220,
                "material_loss_rate": 1.2,
                "profit_rate_percent": 40,
            },
        )
        assert settings_update.status_code == 200, settings_update.text
        assert settings_update.json()["revision"] == current_settings["revision"] + 1

        material = client.post(
            "/api/three-d-printing/materials",
            json={
                "factory_id": "huakang-a",
                "name": "PLA",
                "material_type": "filament",
                "price_per_kg": 88,
            },
        )
        assert material.status_code == 201, material.text

        stock = client.post(
            "/api/three-d-printing/inventory/adjust",
            json={
                "revision": 0,
                "idempotency_key": "baseline-adjust",
                "factory_id": "huakang-a",
                "material_name": "PLA",
                "target_stock_g": 10000,
                "min_stock_g": 3000,
                "reason": "测试初始化库存",
            },
        )
        assert stock.status_code == 200, stock.text

        product = client.post(
            "/api/three-d-printing/products",
            json={
                "factory_id": "huakang-a",
                "name": "测试产品",
                "customer": "测试客户",
                "material_name": "PLA",
                "weight_g": 100,
                "duration_hours": 2,
                "default_quantity": 2,
                "quoted_price": 100,
            },
        )
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]

        image = client.post(
            f"/api/three-d-printing/products/{product_id}/image",
            params={"factory_id": "huakang-a"},
            files={"file": ("product.jpg", jpeg_bytes(), "image/jpeg")},
        )
        assert image.status_code == 200, image.text
        assert image.json()["image_size_bytes"] > 0
        assert "factory_id=huakang-a" in image.json()["image_url"]
        image_read = client.get(image.json()["image_url"])
        assert image_read.status_code == 200
        assert image_read.headers["content-type"].startswith("image/jpeg")

        record = client.post(
            "/api/three-d-printing/records",
            json={
                "idempotency_key": "baseline-create-record",
                "factory_id": "huakang-a",
                "business_date": "2026-07-29",
                "machine_no": 1,
                "status": "running",
                "product_id": product_id,
                "product_name": "测试产品",
                "material_name": "PLA",
                "weight_g": 100,
                "quantity": 2,
                "duration_hours": 2,
                "design_fee": 10,
                "quoted_price": 100,
                "customer": "测试客户",
                "remark": "",
            },
        )
        assert record.status_code == 201, record.text

        dashboard = client.get(
            "/api/three-d-printing/dashboard",
            params={"factory_id": "huakang-a"},
        )
        assert dashboard.status_code == 200, dashboard.text
        body = dashboard.json()
        assert len(body["materials"]) == 1
        assert len(body["products"]) == 1
        assert len(body["records"]) == 1
        assert body["inventory"][0]["stock_g"] == 9800
        # The operating view mirrors the old daily fixed-labor summary, while
        # immutable record allocations remain available for historical reports.
        legacy = body["summary"]["legacyDisplay"]
        assert legacy["laborCost"] == 220
        assert legacy["totalCost"] == 241.62
        assert body["summary"]["laborCost"] == 6.67
        rows = client.get("/api/three-d-printing/collections/records",
                          params={"factory_id": "huakang-a"}).json()["items"]
        assert rows[0]["product_image_url"].startswith(image.json()["image_url"] + "&v=")
        assert client.get(rows[0]["product_image_url"]).status_code == 200

        wrong_factory = client.get(
            "/api/three-d-printing/dashboard",
            params={"factory_id": "huaxing"},
        )
        assert wrong_factory.status_code == 400


def test_edge_status_auto_record_and_admin_only_remote_control(monkeypatch):
    with make_client(monkeypatch) as client:
        edge_headers = {"X-Edge-Token": EDGE_TOKEN}
        heartbeat = client.post(
            "/api/three-d-printing/edge/heartbeat",
            headers=edge_headers,
            json={
                "factory_id": "huakang-a",
                "agent_key": "huakang-a-main",
                "name": "测试边缘代理",
                "version": "test",
                "host_fingerprint": "test-host",
                "capabilities": ["status", "pause", "resume"],
            },
        )
        assert heartbeat.status_code == 200, heartbeat.text

        running = client.post(
            "/api/three-d-printing/edge/status",
            headers=edge_headers,
            json={
                "factory_id": "huakang-a",
                "agent_key": "huakang-a-main",
                "statuses": [
                    {
                        "machine_no": 1,
                        "name": "1号机",
                        "printer_type": "bambu",
                        "model": "P1S",
                        "connected": True,
                        "state": "RUNNING",
                        "current_file": "test-product.gcode",
                        "progress_percent": 25,
                        "remaining_minutes": 40,
                        "observed_at": "",
                    }
                ],
            },
        )
        assert running.status_code == 200, running.text

        ensure_three_d_operator("three-d-user")
        login(client, "three-d-user")
        dashboard = client.get(
            "/api/three-d-printing/dashboard",
            params={"factory_id": "huakang-a"},
        )
        assert dashboard.status_code == 200, dashboard.text
        printer = dashboard.json()["printers"][0]
        assert printer["state"] == "RUNNING"
        assert dashboard.json()["records"][0]["auto_record"] is True

        denied = client.post(
            f"/api/three-d-printing/printers/{printer['id']}/commands",
            json={
                "factory_id": "huakang-a",
                "action": "pause",
                "reason": "权限测试",
                "idempotency_key": "operator-control-denied",
            },
        )
        assert denied.status_code == 403

        login(client, "admin", ADMIN_TEST_PASSWORD)
        command = client.post(
            f"/api/three-d-printing/printers/{printer['id']}/commands",
            json={
                "factory_id": "huakang-a",
                "action": "pause",
                "reason": "测试远程暂停",
                "idempotency_key": "admin-control-command",
            },
        )
        assert command.status_code == 202, command.text
        command_id = command.json()["id"]

        claim = client.post(
            "/api/three-d-printing/edge/commands/claim",
            headers=edge_headers,
            json={
                "factory_id": "huakang-a",
                "agent_key": "huakang-a-main",
                "limit": 10,
            },
        )
        assert claim.status_code == 200, claim.text
        assert claim.json()["commands"][0]["id"] == command_id
        assert claim.json()["commands"][0]["machine_no"] == 1

        ack = client.post(
            f"/api/three-d-printing/edge/commands/{command_id}/ack",
            headers=edge_headers,
            json={
                "factory_id": "huakang-a",
                "agent_key": "huakang-a-main",
                "status": "succeeded",
                "message": "printer accepted pause",
            },
        )
        assert ack.status_code == 200, ack.text
        assert ack.json()["status"] == "succeeded"

        idle = client.post(
            "/api/three-d-printing/edge/status",
            headers=edge_headers,
            json={
                "factory_id": "huakang-a",
                "agent_key": "huakang-a-main",
                "statuses": [
                    {
                        "machine_no": 1,
                        "name": "1号机",
                        "printer_type": "bambu",
                        "connected": True,
                        "state": "IDLE",
                        "current_file": "",
                        "progress_percent": 100,
                        "remaining_minutes": 0,
                        "observed_at": "",
                    }
                ],
            },
        )
        assert idle.status_code == 200, idle.text
        completed_dashboard = client.get(
            "/api/three-d-printing/dashboard",
            params={"factory_id": "huakang-a"},
        ).json()
        assert completed_dashboard["records"][0]["print_end_at"]
