import hashlib
import importlib
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select


TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"
EMPLOYEE_PASSWORD = "OldStrong123!"
NEW_PASSWORD = "FormalPass456!"
CLAIM_COOKIE_NAME = "rr_password_reset_claim"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'password_reset_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    monkeypatch.setenv("AUTHZ_MODE", "enforce")
    monkeypatch.setenv("AUTHZ_WRITES_ENABLED", "false")
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    main = importlib.import_module("app.main")
    return TestClient(main.app)


def create_user(
    username: str,
    *,
    factory_id: str = "huaxing",
    department: str = "engineering",
    role_id: str = "engineer",
) -> str:
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    user_id = f"user-{username}"
    now = auth_service.now_text()
    with db_module.SessionLocal() as db:
        salt, password_hash = auth_service.make_password_hash(EMPLOYEE_PASSWORD)
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=f"{username} 员工",
                password_salt=salt,
                password_hash=password_hash,
                status="active",
                force_password_change=0,
                created_at=now,
                updated_at=now,
            )
        )
        db.flush()
        binding_id = f"{user_id}:{role_id}:{factory_id}:{department}"
        db.add(
            auth_models.AuthUserRole(
                id=binding_id,
                user_id=user_id,
                role_id=role_id,
                factory_id=factory_id,
                department=department,
            )
        )
        db.flush()
        db.add(
            auth_models.AuthRoleBindingMetadata(
                user_role_id=binding_id,
                state="active",
                source_type="test",
                source_id="",
                valid_from=now,
                valid_until="",
                reason="password reset workflow test",
                created_by_user_id="",
                approved_by_user_id="",
                revoked_by_user_id="",
                revoked_at="",
                revoke_reason="",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position="工程师",
                phone="13800000000",
                email=f"{username}@example.com",
                confirmation_status="confirmed",
                source_registration_request_id="",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            auth_models.AuthUserAuthorizationRevision(
                user_id=user_id,
                revision=1,
                updated_at=now,
            )
        )
        db.commit()
    return user_id


def login(client: TestClient, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def submit_reset(client: TestClient, username: str, *, contact: str = "13800000000"):
    return client.post(
        "/api/auth/password-reset-requests",
        json={
            "username": username,
            "display_name": f"{username} 员工",
            "contact": contact,
            "note": "华兴，工程部，忘记密码",
        },
    )


def approve_reset(
    client: TestClient,
    request_id: str,
    *,
    identity_verified: bool = True,
):
    return client.post(
        f"/api/system/password-reset-requests/{request_id}/approve",
        json={
            "review_comment": "已通过内部资料核验员工身份",
            "identity_verified": identity_verified,
        },
    )


def test_submission_sets_httponly_claim_cookie_and_persists_only_hash(monkeypatch):
    with make_client(monkeypatch) as browser:
        user_id = create_user("reset-claim")
        response = submit_reset(browser, "reset-claim")

        assert response.status_code == 200, response.text
        assert "请保留当前浏览器" in response.json()["message"]
        raw_claim = response.cookies.get(CLAIM_COOKIE_NAME)
        assert raw_claim
        set_cookie = response.headers["set-cookie"]
        assert "HttpOnly" in set_cookie
        assert "Max-Age=172800" in set_cookie
        assert "SameSite=lax" in set_cookie

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        request_id = response.json()["request_id"]
        with db_module.SessionLocal() as db:
            reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
            assert reset_request.user_id == user_id
            assert reset_request.claim_token_hash == hashlib.sha256(raw_claim.encode()).hexdigest()
            assert len(reset_request.claim_token_hash) == 64
            assert raw_claim not in reset_request.claim_token_hash
            notification = db.get(auth_models.SystemNotification, reset_request.notification_id)
            assert notification.status == "unread"
            assert set(importlib.import_module("app.services.system").parse_payload(notification.payload_json)) == {
                "password_reset_request_id",
                "matched_user_id",
            }
            serialized_audit = "\n".join(
                f"{item.action}\n{item.detail}\n{item.user_agent}"
                for item in db.scalars(select(auth_models.AuthAuditLog)).all()
            )
            assert raw_claim not in serialized_audit


def test_public_status_is_non_enumerating_for_absent_invalid_and_unknown_accounts(monkeypatch):
    with make_client(monkeypatch) as browser:
        no_cookie = browser.get("/api/auth/password-reset-claim")
        assert no_cookie.status_code == 200
        assert no_cookie.json() == {
            "status": "none",
            "request_id": "",
            "can_complete": False,
            "expires_at": "",
            "message": "当前浏览器没有找到原申请凭证，请重新提交密码重置申请。",
        }

        browser.cookies.set(CLAIM_COOKIE_NAME, "invalid-claim-value")
        invalid = browser.get("/api/auth/password-reset-claim")
        assert invalid.status_code == 200
        assert invalid.json() == no_cookie.json()

        real_browser = TestClient(importlib.import_module("app.main").app)
        unknown_browser = TestClient(importlib.import_module("app.main").app)
        try:
            create_user("reset-known")
            known = submit_reset(real_browser, "reset-known")
            unknown = submit_reset(unknown_browser, "reset-unknown")
            assert known.status_code == unknown.status_code == 200
            assert known.json()["status"] == unknown.json()["status"] == "submitted"
            assert known.json()["message"] == unknown.json()["message"]
            assert real_browser.get("/api/auth/password-reset-claim").json()["status"] == "pending"
            assert unknown_browser.get("/api/auth/password-reset-claim").json()["status"] == "pending"
        finally:
            real_browser.close()
            unknown_browser.close()


def test_approval_requires_identity_and_does_not_change_password_or_sessions(monkeypatch):
    with make_client(monkeypatch) as setup_browser:
        user_id = create_user("reset-approval")
        app = importlib.import_module("app.main").app
        with TestClient(app) as first_session, TestClient(app) as second_session, TestClient(app) as admin:
            assert login(first_session, "reset-approval", EMPLOYEE_PASSWORD).status_code == 200
            assert login(second_session, "reset-approval", EMPLOYEE_PASSWORD).status_code == 200
            reset_response = submit_reset(setup_browser, "reset-approval")
            request_id = reset_response.json()["request_id"]
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200

            db_module = importlib.import_module("app.db")
            auth_models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                user = db.get(auth_models.AuthUser, user_id)
                original_credentials = (user.password_salt, user.password_hash)

            missing_confirmation = approve_reset(admin, request_id, identity_verified=False)
            assert missing_confirmation.status_code == 400
            approval = approve_reset(admin, request_id)
            assert approval.status_code == 200, approval.text
            assert "temporary_password" not in approval.json()
            assert "原浏览器" in approval.json()["message"]
            assert approval.json()["request"]["status"] == "approved"

            with db_module.SessionLocal() as db:
                user = db.get(auth_models.AuthUser, user_id)
                reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                assert (user.password_salt, user.password_hash) == original_credentials
                assert user.force_password_change == 0
                assert reset_request.issue_count == 1
                assert reset_request.expires_at
                sessions = db.scalars(
                    select(auth_models.AuthSession).where(auth_models.AuthSession.user_id == user_id)
                ).all()
                assert len(sessions) == 2
                assert {session.status for session in sessions} == {"active"}

            assert first_session.get("/api/auth/me").status_code == 200
            with TestClient(app) as fresh_login:
                assert login(fresh_login, "reset-approval", EMPLOYEE_PASSWORD).status_code == 200


def test_pending_rejected_and_expired_claims_cannot_complete(monkeypatch):
    with make_client(monkeypatch) as browser:
        create_user("reset-blocked")
        request_id = submit_reset(browser, "reset-blocked").json()["request_id"]
        pending = browser.post(
            "/api/auth/password-reset-claim/complete",
            json={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        )
        assert pending.status_code == 409

        app = importlib.import_module("app.main").app
        with TestClient(app) as admin:
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
            rejected = admin.post(
                f"/api/system/password-reset-requests/{request_id}/reject",
                json={"review_comment": "资料无法核验"},
            )
            assert rejected.status_code == 200
        assert browser.get("/api/auth/password-reset-claim").json()["status"] == "rejected"
        assert browser.post(
            "/api/auth/password-reset-claim/complete",
            json={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
        ).status_code == 409

        second_browser = TestClient(app)
        try:
            second_request_id = submit_reset(second_browser, "reset-blocked").json()["request_id"]
            with TestClient(app) as admin:
                assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
                assert approve_reset(admin, second_request_id).status_code == 200
            db_module = importlib.import_module("app.db")
            auth_models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                reset_request = db.get(auth_models.AuthPasswordResetRequest, second_request_id)
                reset_request.expires_at = "2000-01-01 00:00:00"
                db.commit()
            expired = second_browser.get("/api/auth/password-reset-claim")
            assert expired.json()["status"] == "expired"
            assert expired.json()["can_complete"] is False
            assert second_browser.post(
                "/api/auth/password-reset-claim/complete",
                json={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
            ).status_code == 409
        finally:
            second_browser.close()


def test_approved_claim_completes_once_revokes_sessions_and_deletes_cookie(monkeypatch):
    with make_client(monkeypatch) as original_browser:
        user_id = create_user("reset-complete")
        app = importlib.import_module("app.main").app
        with TestClient(app) as first_session, TestClient(app) as second_session, TestClient(app) as admin:
            assert login(first_session, "reset-complete", EMPLOYEE_PASSWORD).status_code == 200
            assert login(second_session, "reset-complete", EMPLOYEE_PASSWORD).status_code == 200
            first_request = submit_reset(original_browser, "reset-complete")
            request_id = first_request.json()["request_id"]
            raw_claim = first_request.cookies.get(CLAIM_COOKIE_NAME)

            other_browser = TestClient(app)
            try:
                other_request_id = submit_reset(other_browser, "reset-complete").json()["request_id"]
                assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
                assert approve_reset(admin, request_id).status_code == 200
                approved_status = original_browser.get("/api/auth/password-reset-claim").json()
                assert approved_status["status"] == "approved"
                assert approved_status["can_complete"] is True

                mismatch = original_browser.post(
                    "/api/auth/password-reset-claim/complete",
                    json={"new_password": NEW_PASSWORD, "confirm_password": "DifferentPass789!"},
                )
                assert mismatch.status_code == 400
                completed = original_browser.post(
                    "/api/auth/password-reset-claim/complete",
                    json={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
                )
                assert completed.status_code == 200, completed.text
                assert completed.json()["status"] == "completed"
                assert completed.cookies.get("rr_session") is None
                assert CLAIM_COOKIE_NAME in completed.headers["set-cookie"]
                assert "Max-Age=0" in completed.headers["set-cookie"]
                assert original_browser.cookies.get(CLAIM_COOKIE_NAME) is None

                db_module = importlib.import_module("app.db")
                auth_models = importlib.import_module("app.models.auth")
                auth_service = importlib.import_module("app.services.auth")
                with db_module.SessionLocal() as db:
                    user = db.get(auth_models.AuthUser, user_id)
                    reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                    other_request = db.get(auth_models.AuthPasswordResetRequest, other_request_id)
                    assert auth_service.verify_password(NEW_PASSWORD, user)
                    assert not auth_service.verify_password(EMPLOYEE_PASSWORD, user)
                    assert user.force_password_change == 0
                    assert reset_request.status == "completed"
                    assert reset_request.completed_at
                    assert other_request.status == "expired"
                    sessions = db.scalars(
                        select(auth_models.AuthSession).where(auth_models.AuthSession.user_id == user_id)
                    ).all()
                    assert sessions
                    assert {session.status for session in sessions} == {"revoked"}
                    audit_text = "\n".join(
                        f"{item.action}\n{item.detail}\n{item.ip_address}\n{item.user_agent}"
                        for item in db.scalars(select(auth_models.AuthAuditLog)).all()
                    )
                    for secret in (
                        raw_claim,
                        NEW_PASSWORD,
                        EMPLOYEE_PASSWORD,
                        user.password_hash,
                        user.password_salt,
                    ):
                        assert secret not in audit_text

                assert first_session.get("/api/auth/me").status_code == 401
                assert second_session.get("/api/auth/me").status_code == 401
                with TestClient(app) as login_browser:
                    assert login(login_browser, "reset-complete", EMPLOYEE_PASSWORD).status_code == 401
                    assert login(login_browser, "reset-complete", NEW_PASSWORD).status_code == 200
            finally:
                other_browser.close()


def test_reopen_extends_only_expired_claim_without_rotating_secret(monkeypatch):
    with make_client(monkeypatch) as browser:
        user_id = create_user("reset-reopen")
        response = submit_reset(browser, "reset-reopen")
        request_id = response.json()["request_id"]
        raw_claim = response.cookies.get(CLAIM_COOKIE_NAME)
        app = importlib.import_module("app.main").app
        with TestClient(app) as admin:
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
            assert approve_reset(admin, request_id).status_code == 200
            too_early = admin.post(
                f"/api/system/password-reset-requests/{request_id}/reissue",
                json={"review_comment": "提前重开", "identity_verified": True},
            )
            assert too_early.status_code == 409

            db_module = importlib.import_module("app.db")
            auth_models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                original_hash = reset_request.claim_token_hash
                reset_request.status = "expired"
                reset_request.expires_at = "2000-01-01 00:00:00"
                db.commit()

            reopened = admin.post(
                f"/api/system/password-reset-requests/{request_id}/reissue",
                json={"review_comment": "员工仍在原浏览器，重新开放", "identity_verified": True},
            )
            assert reopened.status_code == 200, reopened.text
            assert "temporary_password" not in reopened.json()
            assert "重新开放 4 小时" in reopened.json()["message"]

            with db_module.SessionLocal() as db:
                user = db.get(auth_models.AuthUser, user_id)
                reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                assert reset_request.claim_token_hash == original_hash == hashlib.sha256(raw_claim.encode()).hexdigest()
                assert reset_request.status == "approved"
                assert reset_request.issue_count == 2
                assert importlib.import_module("app.services.auth").verify_password(EMPLOYEE_PASSWORD, user)


def test_legacy_requests_cannot_fall_back_to_temporary_password(monkeypatch):
    with make_client(monkeypatch) as browser:
        create_user("reset-legacy")
        response = submit_reset(browser, "reset-legacy")
        request_id = response.json()["request_id"]
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
            reset_request.claim_token_hash = None
            db.commit()

        app = importlib.import_module("app.main").app
        with TestClient(app) as admin:
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
            legacy = admin.get("/api/system/password-reset-requests?status=legacy_invalid")
            assert legacy.status_code == 200
            assert [item["id"] for item in legacy.json()] == [request_id]
            assert legacy.json()[0]["status"] == "legacy_invalid"
            blocked = approve_reset(admin, request_id)
            assert blocked.status_code == 409
            assert "旧版流程" in blocked.json()["detail"]
            assert "temporary_password" not in blocked.text

        assert browser.get("/api/auth/password-reset-claim").json()["status"] == "none"


def test_permissions_scope_remains_enforced(monkeypatch):
    with make_client(monkeypatch) as setup_browser:
        create_user(
            "reset-manager",
            factory_id="huaxing",
            department="engineering",
            role_id="factory_permission_admin",
        )
        create_user("reset-in-scope", factory_id="huaxing", department="engineering")
        create_user("reset-out-scope", factory_id="huaxing", department="production")
        in_scope_id = submit_reset(setup_browser, "reset-in-scope").json()["request_id"]
        out_scope_browser = TestClient(importlib.import_module("app.main").app)
        unmatched_browser = TestClient(importlib.import_module("app.main").app)
        try:
            out_scope_id = submit_reset(out_scope_browser, "reset-out-scope").json()["request_id"]
            unmatched_id = submit_reset(unmatched_browser, "reset-unknown").json()["request_id"]
            app = importlib.import_module("app.main").app
            with TestClient(app) as manager:
                assert login(manager, "reset-manager", EMPLOYEE_PASSWORD).status_code == 200
                visible = manager.get("/api/system/password-reset-requests?status=pending")
                assert visible.status_code == 200
                assert {item["id"] for item in visible.json()} == {in_scope_id}
                assert approve_reset(manager, out_scope_id).status_code == 403
                assert approve_reset(manager, unmatched_id).status_code == 403

            with TestClient(app) as admin:
                assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
                unmatched_approval = approve_reset(admin, unmatched_id)
                assert unmatched_approval.status_code == 409
                assert "未匹配系统账号" in unmatched_approval.json()["detail"]
        finally:
            out_scope_browser.close()
            unmatched_browser.close()


def test_simultaneous_completion_only_changes_password_once(monkeypatch):
    with make_client(monkeypatch) as original_browser:
        user_id = create_user("reset-concurrent")
        response = submit_reset(original_browser, "reset-concurrent")
        request_id = response.json()["request_id"]
        raw_claim = response.cookies.get(CLAIM_COOKIE_NAME)
        app = importlib.import_module("app.main").app
        with TestClient(app) as admin:
            assert login(admin, "admin", ADMIN_TEST_PASSWORD).status_code == 200
            assert approve_reset(admin, request_id).status_code == 200

        barrier = Barrier(2)

        def complete():
            with TestClient(app) as browser:
                browser.cookies.set(CLAIM_COOKIE_NAME, raw_claim)
                barrier.wait()
                return browser.post(
                    "/api/auth/password-reset-claim/complete",
                    json={"new_password": NEW_PASSWORD, "confirm_password": NEW_PASSWORD},
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: complete(), range(2)))

        assert sorted(response.status_code for response in responses) == [200, 409]
        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            user = db.get(auth_models.AuthUser, user_id)
            reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
            assert reset_request.status == "completed"
            assert importlib.import_module("app.services.auth").verify_password(NEW_PASSWORD, user)
            completed_audits = db.scalars(
                select(auth_models.AuthAuditLog).where(
                    auth_models.AuthAuditLog.action == "password_reset_completed"
                )
            ).all()
            assert len(completed_audits) == 1
