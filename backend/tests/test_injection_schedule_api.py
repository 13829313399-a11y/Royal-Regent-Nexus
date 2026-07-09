import importlib
import sys
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from test_injection_schedule_excel import build_daily_schedule_workbook


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'injection_schedule_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)

    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]

    main = importlib.import_module("app.main")
    return TestClient(main.app)


def login_as(client, username: str):
    response = client.post("/api/auth/login", json={"username": username, "password": "123456"})
    assert response.status_code == 200
    return response.json()


def upload_fixture(client, factory_id: str = "huaxing"):
    return client.post(
        "/api/injection-scheduling/imports/daily-schedule",
        data={"factory_id": factory_id},
        files={
            "file": (
                "fixture.xlsx",
                build_daily_schedule_workbook(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def test_daily_schedule_import_requires_login_and_module_permission(monkeypatch):
    with make_client(monkeypatch) as client:
        anonymous_response = upload_fixture(client)
        assert anonymous_response.status_code == 401

        login_as(client, "engineer")
        no_permission_response = upload_fixture(client)
        assert no_permission_response.status_code == 403


def test_daily_schedule_import_persists_preview_and_machine_status(monkeypatch):
    with make_client(monkeypatch) as client:
        login_profile = login_as(client, "molding_clerk")
        assert "injection_schedule:import" in login_profile["permissions"]

        import_response = upload_fixture(client)
        assert import_response.status_code == 201
        preview = import_response.json()
        batch_id = preview["batch_id"]
        assert preview["factory_id"] == "huaxing"
        assert preview["summary"]["machine_count"] == 2
        assert preview["summary"]["task_count"] == 3
        assert preview["summary"]["pending_task_count"] == 2
        assert len(preview["machines"]) == 2
        assert len(preview["tasks"]) == 3
        assert any(issue["issue_type"] == "missing_due_date" for issue in preview["issues"])

        preview_response = client.get(f"/api/injection-scheduling/imports/{batch_id}/preview")
        assert preview_response.status_code == 200
        assert preview_response.json()["summary"]["scheduled_task_count"] == 1

        machines_response = client.get(f"/api/injection-scheduling/machines/status?batch_id={batch_id}")
        assert machines_response.status_code == 200
        machines = machines_response.json()
        assert [machine["machine_code"] for machine in machines] == ["旧1", "新1"]


def test_injection_schedule_factory_scope_limits_import_but_not_read(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, "admin")
        import_response = upload_fixture(client, "huadeng")
        assert import_response.status_code == 201
        batch_id = import_response.json()["batch_id"]

        login_as(client, "molding_clerk")
        blocked_import_response = upload_fixture(client, "huadeng")
        assert blocked_import_response.status_code == 403

        preview_response = client.get(f"/api/injection-scheduling/imports/{batch_id}/preview")
        assert preview_response.status_code == 200
        assert preview_response.json()["factory_id"] == "huadeng"

        machines_response = client.get(f"/api/injection-scheduling/machines/status?batch_id={batch_id}")
        assert machines_response.status_code == 200
        assert [machine["machine_code"] for machine in machines_response.json()] == ["旧1", "新1"]
