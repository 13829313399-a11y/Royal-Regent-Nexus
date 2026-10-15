"""Personnel contacts use current profile data and the existing detail read scope."""
import importlib

import pytest

from test_iam_api import create_user, login, make_client


@pytest.fixture(autouse=True)
def seed_test_accounts(monkeypatch):
    monkeypatch.setenv("SEED_DEFAULT_ACCOUNTS", "true")


@pytest.mark.parametrize("contacts", [
    ("13800000000", "current@example.com"),
    ("", ""),
    None,
])
def test_identity_returns_current_account_and_profile_contacts(monkeypatch, contacts):
    with make_client(monkeypatch) as client:
        target = create_user("contact-target", "engineer", "huakang-a", "engineering")
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            profile = db.get(models.EmployeeProfile, target)
            if contacts is None:
                db.delete(profile)
            else:
                profile.phone, profile.email = contacts
            db.commit()
        login(client, "admin")
        response = client.get(f"/api/system/users/{target}/identity")
        assert response.status_code == 200, response.text
        detail = response.json()
        assert detail["username"] == "contact-target"
        assert (detail["phone"], detail["email"]) == (contacts or (None, None))
        with db_module.SessionLocal() as db:
            profile = db.get(models.EmployeeProfile, target)
            assert ((profile.phone, profile.email) if profile else None) == contacts
        listed = client.get("/api/system/people", params={"q": "contact-target"})
        assert listed.status_code == 200, listed.text
        assert all("phone" not in item and "email" not in item for item in listed.json()["items"])


def test_contacts_remain_limited_to_manageable_person_details(monkeypatch):
    with make_client(monkeypatch) as client:
        local = create_user("contact-local", "engineer", "huakang-a", "engineering")
        foreign = create_user("contact-foreign", "engineer", "huakang-b", "engineering")
        create_user("contact-reader", "position_engineering_engineer", "huakang-a", "engineering")
        models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        with db_module.SessionLocal() as db:
            permission = db.query(models.AuthPermission).filter_by(code="system:user_manage").one()
            db.add(models.AuthRolePermission(id=f"contact-reader:{permission.id}",
                role_id="position_engineering_engineer", permission_id=permission.id))
            for target in (local, foreign):
                profile = db.get(models.EmployeeProfile, target)
                profile.phone, profile.email = "13800000000", "private@example.com"
            db.commit()
        login(client, "contact-reader")
        allowed = client.get(f"/api/system/users/{local}/identity")
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["phone"] == "13800000000"
        denied = client.get(f"/api/system/users/{foreign}/identity")
        assert denied.status_code == 403
        assert not {"username", "phone", "email"}.intersection(denied.json())
        login(client, "contact-local")
        denied = client.get(f"/api/system/users/{local}/identity")
        assert denied.status_code == 403
        assert not {"username", "phone", "email"}.intersection(denied.json())
