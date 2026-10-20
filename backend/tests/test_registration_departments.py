"""Registration department options must survive registration and position approval."""
import importlib
import re
from pathlib import Path

import pytest
from test_system_user_management_api import login, logout, make_client, register_payload


@pytest.mark.parametrize(
    "role_id", ["position_3d_operator", "position_3d_supervisor", "position_3d_manager"]
)
def test_three_d_registration_approval_preserves_profile_and_scope(monkeypatch, role_id):
    # This legacy approval contract must not inherit the workstation's IAM V2 flags.
    monkeypatch.setenv("IAM_IDENTITY_WRITES_ENABLED", "false")
    monkeypatch.setenv("IAM_IDENTITY_SCHEDULING_ENABLED", "false")
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
        assert rejected.status_code == 400, rejected.text
        assert rejected.json()["detail"] == "请选择有效部门"


def test_every_advertised_factory_department_can_submit_registration(monkeypatch):
    with make_client(monkeypatch) as client:
        response = client.get("/api/auth/organization-catalog")
        assert response.status_code == 200, response.text
        organization = next(o for o in response.json()["organizations"] if o["id"] == "huakang-c")
        departments = {d["code"] for d in organization["departments"]}
        assert {"warehouse", "pmc-warehouse"} <= departments
        for department in departments:
            payload = {
                **register_payload(f"catalog-{department}"),
                "phone": "",
                "email": f"catalog-{department}@example.test",
                "factory_id": organization["factory_id"],
                "org_unit_id": organization["id"],
                "department": department,
                "position": "申请岗位",
            }
            registered = client.post("/api/auth/register", json=payload)
            assert registered.status_code == 200, (department, registered.text)
            assert registered.json()["status"] == "pending"


@pytest.mark.parametrize("identity_mode", ["legacy", "v2"])
@pytest.mark.parametrize("role_id", [
    "position_warehouse_keeper", "position_warehouse_supervisor", "position_warehouse_manager",
])
def test_warehouse_registration_requires_approval_and_preserves_department(monkeypatch, identity_mode, role_id):
    from test_iam_api import make_client as make_identity_client
    monkeypatch.setenv("IAM_IDENTITY_WRITES_ENABLED", "true" if identity_mode == "v2" else "false")
    monkeypatch.setenv("IAM_IDENTITY_SCHEDULING_ENABLED", "false")
    monkeypatch.setenv("IAM_POSITION_WORKBENCH_ENABLED", "false")
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "true")
    with make_identity_client(monkeypatch) as client:
        payload = {
            **register_payload(f"warehouse-{identity_mode}-{role_id}"),
            "factory_id": "huakang-c", "org_unit_id": "huakang-c",
            "department": "warehouse", "position": "仓管",
        }
        registered = client.post("/api/auth/register", json=payload)
        assert registered.status_code == 200, registered.text
        assert registered.json()["status"] == "pending"
        credentials = {"username": payload["username"], "password": payload["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 401

        login(client, "admin")
        applications = client.get("/api/system/registration-requests?status=pending").json()
        application = next(item for item in applications if item["username"] == payload["username"])
        assert application["department"] == "warehouse"
        approved = client.post(
            f"/api/system/registration-requests/{application['id']}/approve",
            json={"system_position_role_id": role_id, "profile": {key: payload[key] for key in (
                "display_name", "phone", "email", "factory_id", "org_unit_id", "department", "position",
            )}},
        )
        assert approved.status_code == 200, approved.text
        logout(client)
        signed_in = client.post("/api/auth/login", json=credentials)
        assert signed_in.status_code == 200, signed_in.text
        account = signed_in.json()
        assert account["profile"]["primary_department"] == "warehouse"
        assert account["profile"]["primary_factory_id"] == "huakang-c"
        assert account["profile"]["position"] == "仓管"
        assert "fabric_warehouse:receive" in account["permissions"]
        assert "system:user_manage" not in account["permissions"]
        assert {(g["role_id"], g["factory_id"], g["department"]) for g in account["grants"]} == {
            (role_id, "huakang-c", "pmc-warehouse"),
        }
        if identity_mode == "v2":
            assert account["identity"]["identity_mode"] == "v2"


@pytest.mark.parametrize("disabled", ["department", "organization"])
def test_disabled_warehouse_organization_or_department_cannot_register(monkeypatch, disabled):
    with make_client(monkeypatch) as client:
        db_module = importlib.import_module("app.db")
        models = importlib.import_module("app.models.identity")
        with db_module.SessionLocal() as db:
            target = db.get(models.IamOrgDepartment, ("huakang-c", "warehouse")) if disabled == "department" else db.get(models.IamOrgUnit, "huakang-c")
            target.status = "inactive"
            db.commit()
        result = client.post("/api/auth/register", json={
            **register_payload(), "factory_id": "huakang-c", "org_unit_id": "huakang-c",
            "department": "warehouse", "position": "仓管",
        })
        assert result.status_code == 422, result.text
        assert result.json()["code"] == "AUTH_ORGANIZATION_CHANGED"
