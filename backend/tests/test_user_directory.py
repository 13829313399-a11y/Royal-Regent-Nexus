import importlib
import sys
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from PIL import Image

TEST_TMP_DIR = Path(__file__).resolve().parents[1] / ".pytest-tmp"
BACKEND_DIR = Path(__file__).resolve().parents[1]
ADMIN_TEST_PASSWORD = "AdminSeed123!"
MEMBER_PASSWORD = "MemberSeed123!"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def make_client(monkeypatch):
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'directory_{uuid4().hex}.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("SEED_ADMIN_PASSWORD", ADMIN_TEST_PASSWORD)
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    main = importlib.import_module("app.main")
    return TestClient(main.app)


def avatar_png() -> bytes:
    image = Image.new("RGB", (32, 32), color=(13, 148, 136))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def add_member(
    *,
    user_id: str,
    username: str,
    display_name: str,
    status: str = "active",
    factory_id: str = "huakang-a",
    department: str = "engineering",
    position: str = "工程师",
    with_avatar: bool = False,
):
    db_module = importlib.import_module("app.db")
    auth_models = importlib.import_module("app.models.auth")
    auth_service = importlib.import_module("app.services.auth")
    salt = uuid4().hex
    with db_module.SessionLocal() as db:
        db.add(
            auth_models.AuthUser(
                id=user_id,
                username=username,
                display_name=display_name,
                password_salt=salt,
                password_hash=auth_service.hash_password(MEMBER_PASSWORD, salt),
                status=status,
                force_password_change=0,
                avatar_png=avatar_png() if with_avatar else None,
                avatar_version="avatar-v1" if with_avatar else "",
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.add(
            auth_models.EmployeeProfile(
                user_id=user_id,
                primary_factory_id=factory_id,
                primary_department=department,
                position=position,
                created_at=auth_service.now_text(),
                updated_at=auth_service.now_text(),
            )
        )
        db.commit()


def login(client: TestClient, username: str, password: str = MEMBER_PASSWORD):
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200


def test_directory_requires_login_and_ordinary_user_can_read_without_user_manage(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        assert client.get("/api/directory/summary").status_code == 401
        assert client.get("/api/directory/members").status_code == 401
        assert client.post("/api/directory/presence/heartbeat").status_code == 401

        add_member(user_id="member-1", username="member-one", display_name="普通成员")
        login(client, "member-one")

        response = client.get("/api/directory/members")
        assert response.status_code == 200
        assert {item["display_name"] for item in response.json()["items"]} >= {
            "普通成员",
            "系统管理员",
        }
        assert client.get("/api/system/users").status_code == 403


def test_directory_whitelists_fields_excludes_inactive_and_applies_fallbacks(
    monkeypatch,
):
    with make_client(monkeypatch) as client:
        add_member(
            user_id="member-active",
            username="active-secret-login",
            display_name="",
            factory_id="",
            department="",
            position="",
        )
        add_member(
            user_id="member-suspended",
            username="hidden-suspended",
            display_name="停用成员",
            status="suspended",
        )
        login(client, "admin", ADMIN_TEST_PASSWORD)

        response = client.get("/api/directory/members?page_size=50")
        assert response.status_code == 200
        members = response.json()["items"]
        active = next(item for item in members if item["id"] == "member-active")
        assert set(active) == {
            "id",
            "display_name",
            "position",
            "primary_factory_id",
            "primary_department",
            "avatar_url",
            "avatar_version",
            "presence_state",
        }
        assert active == {
            "id": "member-active",
            "display_name": "未命名成员",
            "position": "职位待完善",
            "primary_factory_id": "未确认厂区",
            "primary_department": "未确认部门",
            "avatar_url": "",
            "avatar_version": "",
            "presence_state": "offline",
        }
        serialized = response.text
        assert "active-secret-login" not in serialized
        assert "hidden-suspended" not in serialized
        assert "停用成员" not in serialized


def test_presence_thresholds_stable_order_filters_and_pagination(monkeypatch):
    with make_client(monkeypatch) as client:
        add_member(
            user_id="online-a",
            username="online-a",
            display_name="阿晨",
            factory_id="huakang-a",
            department="engineering",
        )
        add_member(
            user_id="away-b",
            username="away-b",
            display_name="白露",
            factory_id="huakang-a",
            department="production",
        )
        add_member(
            user_id="offline-c",
            username="offline-c",
            display_name="陈墨",
            factory_id="huakang-b",
            department="engineering",
        )
        directory_service = importlib.import_module("app.services.directory")
        auth_models = importlib.import_module("app.models.auth")
        db_module = importlib.import_module("app.db")
        now = directory_service.business_now().replace(microsecond=0)
        # Assert the boundary itself, independent of password hashing / CI load.
        monkeypatch.setattr(directory_service, "business_now", lambda: now)
        with db_module.SessionLocal() as db:
            for user_id, seen_at in (
                ("online-a", now - directory_service.timedelta(seconds=119)),
                ("away-b", now - directory_service.timedelta(seconds=121)),
                ("offline-c", now - directory_service.timedelta(minutes=16)),
            ):
                timestamp = directory_service._timestamp(seen_at)
                db.add(
                    auth_models.AuthUserPresence(
                        user_id=user_id,
                        last_seen_at=timestamp,
                        created_at=timestamp,
                        updated_at=timestamp,
                    )
                )
            db.commit()

        login(client, "admin", ADMIN_TEST_PASSWORD)
        response = client.get("/api/directory/members?page_size=50")
        assert response.status_code == 200
        visible = {
            item["id"]: item["presence_state"] for item in response.json()["items"]
        }
        assert visible["online-a"] == "online"
        assert visible["away-b"] == "away"
        assert visible["offline-c"] == "offline"
        ids = [item["id"] for item in response.json()["items"]]
        assert ids.index("online-a") < ids.index("away-b") < ids.index("offline-c")

        filtered = client.get(
            "/api/directory/members",
            params={
                "q": "工程师",
                "presence": "online",
                "factory_id": "huakang-a",
                "department": "engineering",
                "page": 1,
                "page_size": 1,
            },
        ).json()
        assert [item["id"] for item in filtered["items"]] == ["online-a"]
        assert filtered["total"] == 1
        assert filtered["total_pages"] == 1

        factory_search = client.get(
            "/api/directory/members",
            params={"q": "华康A", "page_size": 50},
        ).json()
        assert {item["id"] for item in factory_search["items"]} >= {
            "online-a",
            "away-b",
        }
        assert "offline-c" not in {item["id"] for item in factory_search["items"]}

        department_search = client.get(
            "/api/directory/members",
            params={"q": "工程部", "page_size": 50},
        ).json()
        assert {item["id"] for item in department_search["items"]} >= {
            "online-a",
            "offline-c",
        }
        assert "away-b" not in {item["id"] for item in department_search["items"]}
        assert client.get("/api/directory/members?page_size=51").status_code == 422
        assert client.get(f"/api/directory/members?q={'x' * 65}").status_code == 422


def test_heartbeat_coalesces_writes_and_inactive_user_disappears(monkeypatch):
    with make_client(monkeypatch) as client:
        add_member(
            user_id="heartbeat-user", username="heartbeat-user", display_name="心跳成员"
        )
        login(client, "heartbeat-user")

        first = client.post("/api/directory/presence/heartbeat")
        second = client.post("/api/directory/presence/heartbeat")
        assert first.status_code == 200
        assert first.json() == {
            "status": "ok",
            "written": True,
            "presence_state": "online",
        }
        assert second.status_code == 200
        assert second.json()["written"] is False

        db_module = importlib.import_module("app.db")
        auth_models = importlib.import_module("app.models.auth")
        with db_module.SessionLocal() as db:
            presence = db.get(auth_models.AuthUserPresence, "heartbeat-user")
            assert presence is not None
            original_timestamp = presence.last_seen_at
            user = db.get(auth_models.AuthUser, "heartbeat-user")
            user.status = "suspended"
            db.commit()

        assert client.get("/api/directory/summary").status_code == 401
        login(client, "admin", ADMIN_TEST_PASSWORD)
        response = client.get("/api/directory/members?page_size=50")
        assert "heartbeat-user" not in {item["id"] for item in response.json()["items"]}
        with db_module.SessionLocal() as db:
            assert (
                db.get(auth_models.AuthUserPresence, "heartbeat-user").last_seen_at
                == original_timestamp
            )


def test_avatar_has_generic_404_private_cache_and_conditional_304(monkeypatch):
    with make_client(monkeypatch) as client:
        add_member(
            user_id="avatar-user",
            username="avatar-user",
            display_name="头像成员",
            with_avatar=True,
        )
        add_member(
            user_id="no-avatar-user",
            username="no-avatar-user",
            display_name="无头像成员",
        )
        add_member(
            user_id="inactive-avatar-user",
            username="inactive-avatar-user",
            display_name="停用头像成员",
            status="retired",
            with_avatar=True,
        )
        login(client, "admin", ADMIN_TEST_PASSWORD)

        avatar = client.get("/api/directory/members/avatar-user/avatar")
        assert avatar.status_code == 200
        assert avatar.headers["content-type"] == "image/png"
        assert avatar.headers["cache-control"] == "private, max-age=86400, immutable"
        assert avatar.headers["etag"] == '"avatar-v1"'
        cached = client.get(
            "/api/directory/members/avatar-user/avatar",
            headers={"If-None-Match": avatar.headers["etag"]},
        )
        assert cached.status_code == 304
        assert cached.content == b""
        assert cached.headers["etag"] == '"avatar-v1"'

        missing_details = []
        for user_id in ("missing-user", "no-avatar-user", "inactive-avatar-user"):
            response = client.get(f"/api/directory/members/{user_id}/avatar")
            assert response.status_code == 404
            missing_details.append(response.json()["detail"])
        assert missing_details == ["头像不可用"] * 3


def test_summary_is_fixed_query_count_without_per_member_lookup(monkeypatch):
    with make_client(monkeypatch):
        add_member(user_id="query-a", username="query-a", display_name="查询甲")
        add_member(user_id="query-b", username="query-b", display_name="查询乙")
        db_module = importlib.import_module("app.db")
        directory_service = importlib.import_module("app.services.directory")
        from sqlalchemy import event

        statements: list[str] = []

        def count_statement(
            _connection, _cursor, statement, _parameters, _context, _executemany
        ):
            statements.append(statement)

        event.listen(db_module.engine, "before_cursor_execute", count_statement)
        try:
            with db_module.SessionLocal() as db:
                summary = directory_service.get_directory_summary(db)
        finally:
            event.remove(db_module.engine, "before_cursor_execute", count_statement)

        assert summary.total_members >= 3
        assert len(summary.preview_members) <= 6
        assert len(statements) == 2
