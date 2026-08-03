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
    response = client.post("/api/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return response


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


def approve_reset(client: TestClient, request_id: str):
    return client.post(
        f"/api/system/password-reset-requests/{request_id}/approve",
        json={"review_comment": "已电话核验员工身份"},
    )


def test_public_submission_is_non_enumerating_deduplicated_and_notification_is_redacted(monkeypatch):
    with make_client(monkeypatch) as client:
        create_user("reset-existing")
        existing = submit_reset(client, "reset-existing")
        missing = submit_reset(client, "reset-missing")
        duplicate = submit_reset(client, "reset-existing")

        assert existing.status_code == missing.status_code == duplicate.status_code == 200
        assert existing.json()["status"] == missing.json()["status"] == "submitted"
        assert existing.json()["message"] == missing.json()["message"]
        assert existing.json()["request_id"] == duplicate.json()["request_id"]
        assert existing.json()["request_id"] != missing.json()["request_id"]

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        system_service = importlib.import_module("app.services.system")
        with db_module.SessionLocal() as db:
            requests = db.scalars(select(auth_models.AuthPasswordResetRequest)).all()
            notifications = db.scalars(
                select(auth_models.SystemNotification).where(
                    auth_models.SystemNotification.type == "password_reset"
                )
            ).all()
            assert len(requests) == 2
            assert len(notifications) == 2
            for notification in notifications:
                payload = system_service.parse_payload(notification.payload_json)
                assert set(payload) == {"password_reset_request_id", "matched_user_id"}
                assert "13800000000" not in notification.message
                assert "contact" not in notification.payload_json


def test_admin_approval_generates_one_time_random_password_and_revokes_old_sessions(monkeypatch):
    with make_client(monkeypatch) as admin_client:
        user_id = create_user("reset-approval")
        app = importlib.import_module("app.main").app
        with TestClient(app) as employee_client:
            old_login = login(employee_client, "reset-approval", EMPLOYEE_PASSWORD)
            old_cookie = old_login.cookies.get("rr_session")
            reset_response = submit_reset(admin_client, "reset-approval")
            request_id = reset_response.json()["request_id"]
            login(admin_client, "admin", ADMIN_TEST_PASSWORD)

            approval = approve_reset(admin_client, request_id)
            assert approval.status_code == 200, approval.text
            temporary_password = approval.json()["temporary_password"]
            assert temporary_password != "123456"
            assert len(temporary_password) >= 12
            assert approval.json()["expires_at"]

            employee_client.cookies.set("rr_session", old_cookie)
            assert employee_client.get("/api/auth/me").status_code == 401

            db_module = importlib.import_module("app.db")
            auth_models = importlib.import_module("app.models.auth")
            auth_service = importlib.import_module("app.services.auth")
            with db_module.SessionLocal() as db:
                user = db.get(auth_models.AuthUser, user_id)
                reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                notification = db.get(auth_models.SystemNotification, reset_request.notification_id)
                assert user.force_password_change == 1
                assert auth_service.verify_password(temporary_password, user)
                assert temporary_password not in user.password_hash
                assert reset_request.status == "approved"
                assert reset_request.issue_count == 1
                assert notification.status == "handled"
                detail_text = "\n".join(
                    item.detail for item in db.scalars(select(auth_models.AuthAuditLog)).all()
                )
                assert temporary_password not in detail_text

            detail = admin_client.get(f"/api/system/password-reset-requests/{request_id}")
            assert detail.status_code == 200
            assert "temporary_password" not in detail.json()
            assert approve_reset(admin_client, request_id).status_code == 409


def test_concurrent_admin_approval_only_issues_one_temporary_password(monkeypatch):
    with make_client(monkeypatch) as setup_client:
        create_user("reset-concurrent")
        request_id = submit_reset(setup_client, "reset-concurrent").json()["request_id"]
        app = importlib.import_module("app.main").app
        with TestClient(app) as first_admin, TestClient(app) as second_admin:
            login(first_admin, "admin", ADMIN_TEST_PASSWORD)
            login(second_admin, "admin", ADMIN_TEST_PASSWORD)
            barrier = Barrier(2)

            def approve(client: TestClient):
                barrier.wait()
                return approve_reset(client, request_id)

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(approve, (first_admin, second_admin)))

        assert sorted(response.status_code for response in responses) == [200, 409]
        successful = next(response for response in responses if response.status_code == 200)
        assert successful.json()["temporary_password"]

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
            assert reset_request.status == "approved"
            assert reset_request.issue_count == 1


def test_permissions_scope_and_unmatched_requests_are_enforced_by_backend(monkeypatch):
    with make_client(monkeypatch) as client:
        create_user(
            "reset-manager",
            factory_id="huaxing",
            department="engineering",
            role_id="factory_permission_admin",
        )
        create_user("reset-in-scope", factory_id="huaxing", department="engineering")
        create_user("reset-out-scope", factory_id="huaxing", department="production")
        in_scope_id = submit_reset(client, "reset-in-scope").json()["request_id"]
        out_scope_id = submit_reset(client, "reset-out-scope").json()["request_id"]
        unmatched_id = submit_reset(client, "reset-unknown").json()["request_id"]

        login(client, "reset-manager", EMPLOYEE_PASSWORD)
        visible = client.get("/api/system/password-reset-requests?status=pending")
        assert visible.status_code == 200, visible.text
        assert {item["id"] for item in visible.json()} == {in_scope_id}
        assert approve_reset(client, out_scope_id).status_code == 403
        assert approve_reset(client, unmatched_id).status_code == 403

        client.post("/api/auth/logout")
        login(client, "admin", ADMIN_TEST_PASSWORD)
        unmatched_approval = approve_reset(client, unmatched_id)
        assert unmatched_approval.status_code == 409
        assert "未匹配系统账号" in unmatched_approval.json()["detail"]


def test_rejection_requires_reason_and_is_terminal(monkeypatch):
    with make_client(monkeypatch) as client:
        create_user("reset-reject")
        request_id = submit_reset(client, "reset-reject").json()["request_id"]
        login(client, "admin", ADMIN_TEST_PASSWORD)
        blank = client.post(
            f"/api/system/password-reset-requests/{request_id}/reject",
            json={"review_comment": ""},
        )
        assert blank.status_code == 422
        rejected = client.post(
            f"/api/system/password-reset-requests/{request_id}/reject",
            json={"review_comment": "资料无法核验"},
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "rejected"
        assert approve_reset(client, request_id).status_code == 409


def test_temporary_login_is_backend_restricted_and_change_rotates_session(monkeypatch):
    with make_client(monkeypatch) as admin_client:
        user_id = create_user("reset-change")
        request_id = submit_reset(admin_client, "reset-change").json()["request_id"]
        login(admin_client, "admin", ADMIN_TEST_PASSWORD)
        approval = approve_reset(admin_client, request_id)
        temporary_password = approval.json()["temporary_password"]

        app = importlib.import_module("app.main").app
        with TestClient(app) as employee_client:
            temporary_login = login(employee_client, "reset-change", temporary_password)
            old_session_cookie = temporary_login.cookies.get("rr_session")
            assert temporary_login.json()["force_password_change"] is True
            assert employee_client.get("/api/auth/me").status_code == 200
            blocked = employee_client.get("/api/system/users")
            assert blocked.status_code == 403
            assert blocked.json()["detail"] == "请先修改临时密码"

            wrong_current = employee_client.post(
                "/api/auth/change-password",
                json={
                    "current_password": "WrongPassword!",
                    "new_password": "FormalPass456!",
                    "confirm_password": "FormalPass456!",
                },
            )
            assert wrong_current.status_code == 400
            mismatch = employee_client.post(
                "/api/auth/change-password",
                json={
                    "current_password": temporary_password,
                    "new_password": "FormalPass456!",
                    "confirm_password": "FormalPass789!",
                },
            )
            assert mismatch.status_code == 400
            same_password = employee_client.post(
                "/api/auth/change-password",
                json={
                    "current_password": temporary_password,
                    "new_password": temporary_password,
                    "confirm_password": temporary_password,
                },
            )
            assert same_password.status_code == 400

            changed = employee_client.post(
                "/api/auth/change-password",
                json={
                    "current_password": temporary_password,
                    "new_password": "FormalPass456!",
                    "confirm_password": "FormalPass456!",
                },
            )
            assert changed.status_code == 200, changed.text
            assert changed.json()["force_password_change"] is False
            assert changed.cookies.get("rr_session") != old_session_cookie

            db_module = importlib.import_module("app.db")
            auth_models = importlib.import_module("app.models.auth")
            with db_module.SessionLocal() as db:
                user = db.get(auth_models.AuthUser, user_id)
                reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
                assert user.force_password_change == 0
                assert reset_request.status == "completed"
                assert reset_request.completed_at
                assert reset_request.expires_at == ""


def test_reissue_invalidates_old_temporary_password_and_only_returns_new_once(monkeypatch):
    with make_client(monkeypatch) as admin_client:
        create_user("reset-reissue")
        request_id = submit_reset(admin_client, "reset-reissue").json()["request_id"]
        login(admin_client, "admin", ADMIN_TEST_PASSWORD)
        first_password = approve_reset(admin_client, request_id).json()["temporary_password"]
        reissue = admin_client.post(
            f"/api/system/password-reset-requests/{request_id}/reissue",
            json={"review_comment": "员工遗失第一次临时密码，已再次核验"},
        )
        assert reissue.status_code == 200
        second_password = reissue.json()["temporary_password"]
        assert second_password != first_password

        app = importlib.import_module("app.main").app
        with TestClient(app) as employee_client:
            assert employee_client.post(
                "/api/auth/login",
                json={"username": "reset-reissue", "password": first_password},
            ).status_code == 401
            employee_client.cookies.clear()
            assert employee_client.post(
                "/api/auth/login",
                json={"username": "reset-reissue", "password": second_password},
            ).status_code == 200

        detail = admin_client.get(f"/api/system/password-reset-requests/{request_id}").json()
        assert detail["issue_count"] == 2
        assert "temporary_password" not in detail


def test_expired_temporary_password_is_rejected_and_request_becomes_expired(monkeypatch):
    with make_client(monkeypatch) as admin_client:
        create_user("reset-expired")
        request_id = submit_reset(admin_client, "reset-expired").json()["request_id"]
        login(admin_client, "admin", ADMIN_TEST_PASSWORD)
        temporary_password = approve_reset(admin_client, request_id).json()["temporary_password"]

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            reset_request = db.get(auth_models.AuthPasswordResetRequest, request_id)
            reset_request.expires_at = "2000-01-01 00:00:00"
            db.commit()

        app = importlib.import_module("app.main").app
        with TestClient(app) as employee_client:
            expired_login = employee_client.post(
                "/api/auth/login",
                json={"username": "reset-expired", "password": temporary_password},
            )
            assert expired_login.status_code == 401
            assert "临时密码已过期" in expired_login.json()["detail"]

        with db_module.SessionLocal() as db:
            assert db.get(auth_models.AuthPasswordResetRequest, request_id).status == "expired"
