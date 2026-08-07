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


def _client(monkeypatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv(
        "DATABASE_URL",
        f"sqlite:///{TEST_TMP_DIR / f'profile_api_{uuid4().hex}.db'}",
    )
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    return TestClient(importlib.import_module("app.main").app)


def _login(client: TestClient, username: str, password: str = "123456") -> None:
    response = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text


def _ensure_user(
    username: str,
    role_id: str,
    *,
    factory_id: str,
    department: str,
) -> None:
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
                id=f"{user_id}:{role_id}:{factory_id}:{department}",
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.commit()


def test_profile_registry_api_is_factory_scoped_and_not_inferred_for_general_manager(
    monkeypatch,
):
    with _client(monkeypatch) as client:
        _login(client, "admin", ADMIN_TEST_PASSWORD)
        response = client.get(
            "/api/injection-scheduling/import-profiles",
            params={"factory_id": "huakang-b"},
        )
        assert response.status_code == 200, response.text
        assert [item["profile_code"] for item in response.json()["items"]] == [
            "huakang_b_daily_plan_v1"
        ]
        assert response.json()["items"][0]["status"] == "ACTIVE"

        _ensure_user(
            "profile-general-manager",
            "position_general_manager",
            factory_id="*",
            department="*",
        )
        client.post("/api/auth/logout")
        _login(client, "profile-general-manager")
        denied = client.get(
            "/api/injection-scheduling/import-profiles",
            params={"factory_id": "huakang-b"},
        )
        assert denied.status_code == 403, denied.text
