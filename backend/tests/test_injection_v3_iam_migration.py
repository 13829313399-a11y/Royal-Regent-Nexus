"""Verify the historical V3 migration at its original revision."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]
PREVIOUS = "20260904_0099"
REVISION = "20260905_0100"


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
        "injection_v3_calendar_event",
        "injection_v3_demand",
        "injection_v3_factory_settings",
        "injection_v3_historical_output",
        "injection_v3_import_batch",
        "injection_v3_import_row",
        "injection_v3_machine",
        "injection_v3_mold_asset",
        "injection_v3_mold_master",
        "injection_v3_operation",
        "injection_v3_report_allocation",
        "injection_v3_run",
        "injection_v3_run_demand",
        "injection_v3_saved_view",
        "injection_v3_shared_revision",
        "injection_v3_shift_report",
    }
    assert {name for name in names if name.startswith("injection_v3_")} == expected
    assert not any(name.startswith(("injection_schedule_", "injection_scheduling_")) for name in names)
    registered = {
        row[0]
        for row in db.execute(
            "SELECT code FROM auth_permissions WHERE code LIKE 'injection%'"
        )
    }
    assert registered == {f"injection_scheduling:{action}" for action in ("read", "plan", "report", "master_write")}
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
