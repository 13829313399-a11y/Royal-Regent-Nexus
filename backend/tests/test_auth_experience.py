"""Auth experience contracts against disposable databases, never the business DB."""
import importlib
from datetime import datetime, timedelta
from sqlalchemy import select

import pytest
from fastapi.testclient import TestClient

from test_password_reset_workflow import (
    make_client, create_user, login, submit_reset, approve_reset,
    ADMIN_TEST_PASSWORD, EMPLOYEE_PASSWORD, NEW_PASSWORD,
)


@pytest.mark.parametrize("old_status", ["pending", "approved", "expired"])
def test_real_password_change_invalidates_every_old_claim(monkeypatch, old_status):
    with make_client(monkeypatch) as original_browser:
        create_user("claim-invalidation")
        app = importlib.import_module("app.main").app
        with TestClient(app) as authenticated, TestClient(app) as admin:
            request_id = submit_reset(original_browser, "claim-invalidation").json()["request_id"]
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
            if old_status != "pending":
                assert approve_reset(admin, request_id).status_code == 200
            if old_status == "expired":
                models = importlib.import_module("app.models.auth")
                with importlib.import_module("app.db").SessionLocal() as db:
                    item = db.get(models.AuthPasswordResetRequest, request_id)
                    item.status = "expired"
                    item.expires_at = "2000-01-01 00:00:00"
                    db.commit()
            assert login(authenticated, "claim-invalidation", EMPLOYEE_PASSWORD).status_code == 200
            changed = authenticated.post("/api/auth/change-password", json={
                "current_password": EMPLOYEE_PASSWORD, "new_password": NEW_PASSWORD,
                "confirm_password": NEW_PASSWORD,
            })
            assert changed.status_code == 200, changed.text
            claim = original_browser.get("/api/auth/password-reset-claim").json()
            assert claim["status"] == "expired"
            assert claim["can_request_reopen"] is False
            completed = original_browser.post("/api/auth/password-reset-claim/complete", json={
                "new_password": "AnotherPass789!", "confirm_password": "AnotherPass789!",
            })
            assert completed.status_code == 409
            reopened = admin.post(f"/api/system/password-reset-requests/{request_id}/reissue", json={
                "review_comment": "verified again", "identity_verified": True,
            })
            assert reopened.status_code == 409, reopened.text
            assert authenticated.get("/api/auth/me").status_code == 200
            assert login(authenticated, "claim-invalidation", NEW_PASSWORD).status_code == 200


def test_registration_receipt_constraints_and_private_error_redaction(monkeypatch):
    with make_client(monkeypatch) as client:
        payload = dict(username="001-receipt", display_name="测试员工", password=" secret123 ",
                       confirm_password=" secret123 ", phone="", email="qa@example.test",
                       factory_id="huaxing", org_unit_id="huaxing", department="engineering", position="实际岗位")
        for field, limit in {"username":64,"display_name":128,"phone":64,"email":128,"factory_id":64,
                             "org_unit_id":64,"department":64,"position":128,"password":256,"confirm_password":256}.items():
            result = client.post("/api/auth/register", json={**payload, field:"x"*(limit+1)})
            assert result.status_code == 422, (field,result.text)
            assert result.json()["code"] == "AUTH_VALIDATION_ERROR"
            assert result.json()["field_errors"][0]["field"] == field
            assert "input" not in result.text and "secret123" not in result.text
            assert result.headers["cache-control"] == "private, no-store"
            assert result.json()["trace_id"] == result.headers["x-request-id"]
        response = client.post("/api/auth/register", json=payload)
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["status"] == "pending" and data["request_id"]
        assert datetime.fromisoformat(data["submitted_at"]).tzinfo is not None
        models = importlib.import_module("app.models.auth")
        with importlib.import_module("app.db").SessionLocal() as db:
            record = db.get(models.AuthRegistrationRequest, data["request_id"])
            assert record.username == "001-receipt"
            assert importlib.import_module("app.services.auth").verify_password(payload["password"], db.get(models.AuthUser, record.user_id))
        conflict = client.post("/api/auth/register", json=payload)
        assert conflict.status_code == 409 and conflict.json()["code"] == "AUTH_REGISTRATION_CONFLICT"
        assert "request_id" not in conflict.json()
        wrong = client.post("/api/auth/register", json={**payload,"username":"new-org","org_unit_id":"missing"})
        assert wrong.json()["code"] == "AUTH_ORGANIZATION_CHANGED"


def test_login_retry_after_uses_threshold_exit_and_preserves_cookie_contract(monkeypatch):
    with make_client(monkeypatch) as client:
        create_user("throttle-qa")
        models = importlib.import_module("app.models.auth")
        auth = importlib.import_module("app.services.auth")
        with importlib.import_module("app.db").SessionLocal() as db:
            # 12 failures: the THIRD oldest (12-10) must leave, not the first.
            for age in [899,898,500,450,400,350,300,250,200,150,100,50]:
                db.add(models.AuthAuditLog(username="throttle-qa", user_id="", action="login_denied",
                    detail=auth.BAD_CREDENTIALS_MESSAGE, ip_address="testclient", user_agent="",
                    created_at=(datetime.now()-timedelta(seconds=age)).strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
        result = login(client,"throttle-qa",EMPLOYEE_PASSWORD)
        assert result.status_code == 429
        assert result.json()["code"] == "AUTH_LOGIN_THROTTLED"
        retry = result.json()["retry_after_seconds"]
        assert 390 <= retry <= 401 and int(result.headers["retry-after"]) == retry
        bad = login(client,"unknown-qa","incorrect")
        assert bad.json()["code"] == "AUTH_INVALID_CREDENTIALS"
        good = login(client,"admin",ADMIN_TEST_PASSWORD)
        assert good.status_code == 200
        cookie = good.headers["set-cookie"]
        for value in ["HttpOnly","Max-Age=43200","Path=/","SameSite=lax"]: assert value in cookie
        assert client.get("/api/auth/me").headers["cache-control"] == "private, no-store"
        logout = client.post("/api/auth/logout")
        for value in ["Max-Age=0","Path=/","SameSite=lax","HttpOnly"]: assert value in logout.headers["set-cookie"]


def test_recovery_exact_username_match_never_selects_an_ambiguous_case_variant(monkeypatch):
    with make_client(monkeypatch) as browser:
        upper_id = create_user("CaseUser")
        lower_id = create_user("caseuser")
        models = importlib.import_module("app.models.auth")
        for name, expected in [("CaseUser",upper_id),("caseuser",lower_id),("CASEUSER",None),("Straße",None)]:
            result = submit_reset(browser,name)
            assert result.status_code == 200
            with importlib.import_module("app.db").SessionLocal() as db:
                assert db.get(models.AuthPasswordResetRequest,result.json()["request_id"]).user_id == expected


def test_claim_completion_supersedes_previously_expired_claim_and_old_session(monkeypatch):
    with make_client(monkeypatch) as old_browser:
        create_user("claim-old-expired")
        app = importlib.import_module("app.main").app
        with TestClient(app) as new_browser, TestClient(app) as session, TestClient(app) as admin:
            assert login(admin,"admin",ADMIN_TEST_PASSWORD).status_code == 200
            assert login(session,"claim-old-expired",EMPLOYEE_PASSWORD).status_code == 200
            old_id=submit_reset(old_browser,"claim-old-expired").json()["request_id"]
            assert approve_reset(admin,old_id).status_code == 200
            models=importlib.import_module("app.models.auth")
            with importlib.import_module("app.db").SessionLocal() as db:
                old=db.get(models.AuthPasswordResetRequest,old_id); old.status="expired"; old.expires_at="2000-01-01 00:00:00"; db.commit()
            new_id=submit_reset(new_browser,"claim-old-expired").json()["request_id"]
            assert approve_reset(admin,new_id).status_code == 200
            assert new_browser.post("/api/auth/password-reset-claim/complete",json={"new_password":NEW_PASSWORD,"confirm_password":NEW_PASSWORD}).status_code == 200
            result=admin.post(f"/api/system/password-reset-requests/{old_id}/reissue",json={"review_comment":"verified","identity_verified":True})
            assert result.status_code == 409
            stale=session.post("/api/auth/change-password",json={"current_password":EMPLOYEE_PASSWORD,"new_password":"NoPass123!","confirm_password":"NoPass123!"})
            assert stale.status_code == 401
