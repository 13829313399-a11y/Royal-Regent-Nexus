"""V3 migration and real account/session authorization boundaries."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.api import auth as auth_api
from app.api import injection_scheduling as injection_api
from app.core.config import settings
from app.db import Base, get_db
from app.models import auth as models
from app.services import auth
from app.services.injection_scheduling.common import seed_settings
from app.services.permission_codes import INJECTION_SCHEDULING_PERMISSION_CODES
from app.services.permission_scope_policy import permission_scope_policy
from app.services.system_position_reconcile import reconcile_system_position_catalog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event, select
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]
BASE = "/api/injection-scheduling"
PREVIOUS = "20260904_0099"
REVISION = "20260905_0100"
PASSWORD = "InjectionReview123!"


def alembic(database, revision):
    env = os.environ.copy()
    env.update(
        DATABASE_URL=f"sqlite:///{database.as_posix()}", SEED_DEFAULT_ACCOUNTS="false"
    )
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(BACKEND / "alembic.ini"),
            "upgrade",
            revision,
        ],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def assert_v3_schema(db):
    names = {
        row[0]
        for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (
        REVISION,
    )
    expected = {
        table.name
        for table in Base.metadata.tables.values()
        if table.name.startswith("injection_v3_")
    }
    assert names & expected == expected
    assert len(expected) == 16
    assert not any(
        name.startswith(("injection_schedule_", "injection_scheduling_"))
        for name in names
    )
    for table in Base.metadata.tables.values():
        if table.name in expected:
            columns = {
                row[1] for row in db.execute(f'PRAGMA table_info("{table.name}")')
            }
            assert columns == set(table.columns.keys()), table.name
    registered = {
        row[0]
        for row in db.execute(
            "SELECT code FROM auth_permissions WHERE code LIKE 'injection%'"
        )
    }
    assert registered == set(INJECTION_SCHEDULING_PERMISSION_CODES)
    kinds = dict(
        db.execute(
            "SELECT p.code,m.access_kind FROM auth_permissions p JOIN auth_permission_metadata m ON m.permission_id=p.id WHERE p.code LIKE 'injection%'"
        ).fetchall()
    )
    assert kinds == {
        code: "read" if code.endswith(":read") else "operate" for code in registered
    }
    assert db.execute(
        "SELECT factory_id,revision FROM injection_v3_factory_settings ORDER BY factory_id"
    ).fetchall() == [("huadeng", 0), ("huakang-a", 0), ("huakang-b", 0), ("huaxing", 0)]
    assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert db.execute("PRAGMA foreign_key_check").fetchall() == []


def test_empty_sqlite_upgrades_full_historical_chain_to_v3(tmp_path):
    database = tmp_path / "empty-to-v3.db"
    alembic(database, REVISION)
    with sqlite3.connect(database) as db:
        assert_v3_schema(db)


def test_existing_0099_upgrade_preserves_unrelated_records_and_grants(tmp_path):
    database = tmp_path / "existing-0099.db"
    alembic(database, PREVIOUS)
    with sqlite3.connect(database) as db:
        db.executescript("""
            CREATE TABLE unrelated_v3_upgrade_evidence(id TEXT PRIMARY KEY, payload TEXT);
            INSERT INTO unrelated_v3_upgrade_evidence VALUES ('keep', '订单 001 不变');
            INSERT INTO auth_roles (id,code,name,description) VALUES ('v3-keep','v3-keep','保留角色','原授权');
            INSERT INTO auth_permissions (id,code,name,description) VALUES ('v3-keep-perm','test:keep','保留权限','原权限');
            INSERT INTO auth_role_permissions (id,role_id,permission_id) VALUES ('v3-keep-grant','v3-keep','v3-keep-perm');
        """)
        before = {
            name: db.execute(f'SELECT * FROM "{name}"').fetchall()
            for (name,) in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
            if name
            not in {"alembic_version", "auth_permissions", "auth_permission_metadata"}
        }
        permissions = db.execute("SELECT * FROM auth_permissions").fetchall()
        assert not any(row[1].startswith("injection") for row in permissions)
    alembic(database, REVISION)
    with sqlite3.connect(database) as db:
        assert_v3_schema(db)
        for name, rows in before.items():
            assert db.execute(f'SELECT * FROM "{name}"').fetchall() == rows, name
        assert set(permissions) <= set(
            db.execute("SELECT * FROM auth_permissions").fetchall()
        )
        assert not db.execute(
            "SELECT 1 FROM auth_role_permissions rp JOIN auth_permissions p ON p.id=rp.permission_id WHERE p.code LIKE 'injection%'"
        ).fetchall()
    # Re-running the head is an Alembic no-op, never duplicate tables or grants.
    alembic(database, REVISION)
    with sqlite3.connect(database) as db:
        assert_v3_schema(db)


@pytest.fixture
def iam_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "authz_mode", "enforce")
    monkeypatch.setattr(settings, "authz_writes_enabled", True)
    monkeypatch.setattr(settings, "seed_default_accounts", False)
    monkeypatch.setattr(settings, "session_cookie_secure", False)
    engine = create_engine(
        f"sqlite:///{tmp_path / 'real-iam.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enforce_foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    metadata = MetaData()
    auth_tables = {
        value.__table__.name
        for value in vars(models).values()
        if isinstance(value, type) and hasattr(value, "__table__")
    }
    for table in Base.metadata.sorted_tables:
        if table.name in auth_tables or table.name.startswith("injection_v3_"):
            table.to_metadata(metadata)
    metadata.create_all(engine)
    with Session(engine) as db:
        seed_settings(db)
        auth.seed_auth_defaults(db)

    def session():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    app = FastAPI()
    app.include_router(auth_api.router)
    app.include_router(injection_api.router)
    app.dependency_overrides[get_db] = session
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


def account(
    env,
    role="position_production_clerk",
    factory="huaxing",
    department="production",
    *,
    permissions=None,
):
    _, engine = env
    identity = uuid4().hex
    instant = auth.now_text()
    with Session(engine) as db:
        if permissions is not None:
            role = f"custom-{identity}"
            db.add(models.AuthRole(id=role, code=role, name="限定能力", description=""))
            db.add(
                models.AuthRoleMetadata(
                    role_id=role, scope_mode="own_factory", version=1
                )
            )
            db.flush()
            for permission in db.scalars(
                select(models.AuthPermission).where(
                    models.AuthPermission.code.in_(permissions)
                )
            ):
                db.add(
                    models.AuthRolePermission(
                        id=uuid4().hex, role_id=role, permission_id=permission.id
                    )
                )
        salt, hashed = auth.make_password_hash(PASSWORD)
        db.add(
            models.AuthUser(
                id=identity,
                username=identity,
                display_name="隔离 IAM 测试",
                password_salt=salt,
                password_hash=hashed,
                status="active",
                force_password_change=0,
                created_at=instant,
                updated_at=instant,
            )
        )
        db.flush()
        binding = uuid4().hex
        db.add(
            models.AuthUserRole(
                id=binding,
                user_id=identity,
                role_id=role,
                factory_id=factory,
                department=department,
            )
        )
        db.flush()
        db.add(
            models.AuthRoleBindingMetadata(
                user_role_id=binding, state="active", source_type="test", version=1
            )
        )
        db.add(
            models.EmployeeProfile(
                user_id=identity,
                primary_factory_id=factory,
                primary_department=department,
                confirmation_status="confirmed",
            )
        )
        db.add(
            models.AuthUserAuthorizationRevision(
                user_id=identity, revision=1, updated_at=instant
            )
        )
        db.commit()
    return identity


def login(env, identity):
    response = env[0].post(
        "/api/auth/login", json={"username": identity, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    assert "rr_session" in response.cookies


def write(env, endpoint="/demands", factory="huaxing", **fields):
    with Session(env[1]) as db:
        from app.models.injection_scheduling import FactorySettings

        revision = db.get(FactorySettings, factory).revision
    return env[0].post(
        BASE + endpoint,
        json={
            "factory_id": factory,
            "client_operation_id": uuid4().hex,
            "base_revision": revision,
            "data": {"mold_code": "IAM-01", "planned_shots": 100},
            **fields,
        },
    )


def test_real_session_fixed_clerk_scope_and_distinct_capabilities(iam_env):
    client, _ = iam_env
    assert (
        client.get(BASE + "/summary", params={"factory_id": "huaxing"}).status_code
        == 401
    )
    identity = account(iam_env)
    login(iam_env, identity)
    assert (
        client.get(BASE + "/summary", params={"factory_id": "huaxing"}).status_code
        == 200
    )
    assert (
        client.get(BASE + "/summary", params={"factory_id": "huadeng"}).status_code
        == 403
    )
    assert write(iam_env).status_code == 200
    assert write(iam_env, factory="huadeng").status_code == 403
    assert write(iam_env, "/molds", data={"mold_code": "MASTER"}).status_code == 403
    for factory in ("group", "huakang-c", "huakang-d"):
        assert (
            client.get(BASE + "/summary", params={"factory_id": factory}).status_code
            == 422
        )


def test_cross_factory_read_position_cannot_operate_remote_factory(iam_env):
    identity = account(iam_env, "position_molding_clerk")
    login(iam_env, identity)
    assert (
        iam_env[0].get(BASE + "/summary", params={"factory_id": "huadeng"}).status_code
        == 200
    )
    assert write(iam_env, factory="huadeng").status_code == 403
    assert write(iam_env).status_code == 200


def test_explicit_deny_wins_and_revoked_account_loses_session(iam_env):
    identity = account(iam_env, "position_molding_supervisor")
    login(iam_env, identity)
    assert write(iam_env, factory="huadeng").status_code == 200
    with Session(iam_env[1]) as db:
        permission = db.scalar(
            select(models.AuthPermission).where(
                models.AuthPermission.code == "injection_scheduling:plan"
            )
        )
        db.add(
            models.AuthUserPermissionOverride(
                id=uuid4().hex,
                user_id=identity,
                permission_id=permission.id,
                effect="deny",
                factory_id="huadeng",
                department="*",
                status="active",
            )
        )
        db.get(models.AuthUserAuthorizationRevision, identity).revision += 1
        db.commit()
    assert write(iam_env, factory="huadeng").status_code == 403
    assert write(iam_env).status_code == 200
    with Session(iam_env[1]) as db:
        db.get(models.AuthUser, identity).status = "disabled"
        db.commit()
    assert (
        iam_env[0].get(BASE + "/summary", params={"factory_id": "huaxing"}).status_code
        == 401
    )


def test_shared_master_permission_does_not_expand_order_or_factory_scope(iam_env):
    identity = account(
        iam_env,
        permissions={"injection_scheduling:read", "injection_scheduling:master_write"},
    )
    login(iam_env, identity)
    assert write(iam_env, "/molds", data={"mold_code": "SHARED-IAM"}).status_code == 200
    assert write(iam_env).status_code == 403
    assert (
        write(
            iam_env, "/machines", factory="huadeng", data={"code": "远厂1"}
        ).status_code
        == 403
    )
    response = iam_env[0].get(BASE + "/molds", params={"factory_id": "huaxing"})
    assert response.status_code == 200
    assert "SHARED-IAM" in response.text


def test_scope_policy_and_reconcile_only_current_codes_without_legacy_revival(iam_env):
    identity = account(iam_env)
    with Session(iam_env[1]) as db:
        code = "injection_scheduling:plan"
        permission = db.scalar(
            select(models.AuthPermission).where(models.AuthPermission.code == code)
        )
        link = db.scalar(
            select(models.AuthRolePermission).where(
                models.AuthRolePermission.role_id == "position_production_clerk",
                models.AuthRolePermission.permission_id == permission.id,
            )
        )
        db.delete(link)
        db.flush()
        before = db.get(models.AuthUserAuthorizationRevision, identity).revision
        result = reconcile_system_position_catalog(db)
        db.commit()
        assert "position_production_clerk" in result.changed_role_ids
        assert db.get(models.AuthUserAuthorizationRevision, identity).revision > before
        codes = set(
            db.scalars(
                select(models.AuthPermission.code).where(
                    models.AuthPermission.code.startswith("injection")
                )
            )
        )
        assert codes == set(INJECTION_SCHEDULING_PERMISSION_CODES)
        assert not reconcile_system_position_catalog(db).changed_role_ids
    for code in INJECTION_SCHEDULING_PERMISSION_CODES:
        assert permission_scope_policy(code).departments == (
            "production",
            "molding",
            "management",
        )


def test_department_scope_is_authoritative_in_enforce_mode(iam_env):
    identity = account(
        iam_env,
        department="engineering",
        permissions=set(INJECTION_SCHEDULING_PERMISSION_CODES),
    )
    login(iam_env, identity)
    assert (
        iam_env[0].get(BASE + "/summary", params={"factory_id": "huaxing"}).status_code
        == 403
    )
    assert write(iam_env).status_code == 403


def test_report_capability_is_separate_from_plan_capability(iam_env):
    for permissions, expected in (
        ({"injection_scheduling:read", "injection_scheduling:plan"}, 403),
        ({"injection_scheduling:read", "injection_scheduling:report"}, 404),
    ):
        identity = account(iam_env, permissions=permissions)
        login(iam_env, identity)
        # An absent run reaches the domain's 404 only after actual authorization.
        # A plan-only account must stop at 403 before any business lookup/write.
        response = iam_env[0].post(
            BASE + "/runs/missing-run/start",
            json={
                "factory_id": "huaxing",
                "base_revision": 0,
                "client_operation_id": uuid4().hex,
            },
        )
        assert response.status_code == expected, response.text
        if "injection_scheduling:report" in permissions:
            assert write(iam_env).status_code == 403
