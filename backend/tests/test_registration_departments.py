"""Registration department options must survive registration and position approval."""
import re
from pathlib import Path

import pytest
from test_system_user_management_api import login, logout, make_client, register_payload


@pytest.mark.parametrize(
    "role_id", ["position_3d_operator", "position_3d_supervisor", "position_3d_manager"]
)
def test_three_d_registration_approval_preserves_profile_and_scope(monkeypatch, role_id):
    with make_client(monkeypatch) as client:
        payload = {
            **register_payload(f"applicant-{role_id}"),
            "factory_id": "huakang-a",
            "department": "three-d-printing",
            "position": "技术员",
        }
        registered = client.post("/api/auth/register", json=payload)
        assert registered.status_code == 200, registered.text
        assert registered.json()["status"] == "pending"
        credentials = {"username": payload["username"], "password": payload["password"]}
        pending_login = client.post("/api/auth/login", json=credentials)
        assert pending_login.status_code == 401
        assert pending_login.json()["detail"] == "账号申请正在审批中，请等待管理员开通"

        login(client, "admin")
        requests = client.get("/api/system/registration-requests?status=pending").json()
        application = next(item for item in requests if item["username"] == payload["username"])
        assert application["department"] == "three-d-printing"
        approved = client.post(
            f"/api/system/registration-requests/{application['id']}/approve",
            json={
                "system_position_role_id": role_id,
                "profile": {key: payload[key] for key in (
                    "display_name", "phone", "email", "factory_id", "department", "position"
                )},
            },
        )
        assert approved.status_code == 200, approved.text
        logout(client)
        signed_in = client.post("/api/auth/login", json=credentials)
        assert signed_in.status_code == 200, signed_in.text
        account = signed_in.json()
        assert account["profile"]["primary_department"] == "three-d-printing"
        assert account["profile"]["primary_factory_id"] == "huakang-a"
        assert account["profile"]["position"] == "技术员"
        assert "three_d_printing:operate" in account["permissions"]
        assert "three_d_printing:printer_control" not in account["permissions"]
        assert "system:user_manage" not in account["permissions"]
        assert {(g["factory_id"], g["department"]) for g in account["grants"]} == {
            ("huakang-a", "three-d-printing")
        }


def test_registration_catalog_accepts_frontend_options_and_rejects_unknown(monkeypatch):
    with make_client(monkeypatch) as client:
        from app.services.auth import ALLOWED_DEPARTMENTS

        catalog = Path(__file__).resolve().parents[2] / "src/data/registrationDepartments.ts"
        options = set(re.findall(r"\{ id: '([^']+)'", catalog.read_text(encoding="utf-8")))
        assert options
        assert options <= ALLOWED_DEPARTMENTS, options - ALLOWED_DEPARTMENTS
        rejected = client.post(
            "/api/auth/register", json={**register_payload(), "department": "unknown-department"}
        )
        assert rejected.status_code == 400
        assert rejected.json()["detail"] == "请选择有效部门"
