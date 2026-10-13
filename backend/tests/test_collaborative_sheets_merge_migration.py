"""Rehearse both applied histories in disposable databases, never a live store."""
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest

BACKEND = Path(__file__).resolve().parents[1]
MAIN_HEAD = "20261008_0147"
COLLABORATION_HEAD = "20261009_0121"
MERGE = "20261009_0148"


def graph():
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    return ScriptDirectory.from_config(config)


def test_merge_keeps_both_applied_parents_and_no_schema_operations():
    script = graph()
    heads = script.get_heads()
    assert len(heads) == 1
    assert MERGE in {revision.revision for revision in script.iterate_revisions(heads[0], "base")}
    assert set(script.get_revision(MERGE).down_revision) == {MAIN_HEAD, COLLABORATION_HEAD}
    assert script.get_revision(COLLABORATION_HEAD).down_revision == "20261005_0120"
    assert set(script.get_revision(MAIN_HEAD).down_revision) == {"20261008_0140", "20261008_0146"}
    assert script.get_revision(MERGE).module.upgrade() is None
    assert script.get_revision(MERGE).module.downgrade() is None


@pytest.mark.parametrize("start", [MAIN_HEAD, COLLABORATION_HEAD])
def test_both_existing_heads_upgrade_without_losing_accounts_or_saved_fills(tmp_path, start):
    path = tmp_path / "merge-rehearsal.sqlite"
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{path.as_posix()}", SEED_ADMIN_PASSWORD="",
               AUTHZ_MODE="enforce", AUTHZ_WRITES_ENABLED="false", IAM_IDENTITY_WRITES_ENABLED="false",
               IAM_IDENTITY_SCHEDULING_ENABLED="false", PYTHONIOENCODING="utf-8")
    def upgrade(revision):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision],
            cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=240)
        assert result.returncode == 0, result.stderr
    def insert(connection, table, values):
        for _, name, kind, required, default, _ in connection.execute(f'PRAGMA table_info("{table}")'):
            if name not in values and required and default is None:
                values[name] = 0 if "INT" in kind else ""
        names = ",".join('"' + n + '"' for n in values)
        connection.execute(f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))
    upgrade(start)
    with sqlite3.connect(path) as connection:
        insert(connection, "auth_users", {"id": "preserve-user", "username": "preserve-user", "display_name": "Synthetic owner", "status": "suspended"})
        if start == COLLABORATION_HEAD:
            insert(connection, "collaborative_sheets", {"id": "preserve-fill", "factory_id": "huaxing", "owner_user_id": "preserve-user",
                "status": "open", "revision": 7, "format": "xlsx", "manifest": json.dumps({"sheets": []}),
                "overrides": json.dumps({"0:A1": "00017"}), "grants": "[]"})
            insert(connection, "collaborative_sheet_events", {"id": "preserve-event", "task_id": "preserve-fill", "actor_id": "preserve-user",
                "action": "cells_saved", "revision": 7, "detail": json.dumps({"changes": [{"address": "A1", "after": "00017"}]})})
            insert(connection, "collaborative_sheet_submissions", {"task_id": "preserve-fill", "user_id": "preserve-user", "revision": 7})
        watched = ["auth_users", "auth_roles", "auth_user_roles", "auth_role_permissions", "auth_user_permission_overrides", "employee_profiles"]
        if start == COLLABORATION_HEAD:
            watched += ["collaborative_sheets", "collaborative_sheet_events", "collaborative_sheet_submissions"]
        before = {table: ([c[1] for c in connection.execute(f'PRAGMA table_info("{table}")')],
                          connection.execute(f'SELECT * FROM "{table}"').fetchall()) for table in watched}
        permissions = connection.execute("SELECT * FROM auth_permissions ORDER BY id").fetchall()
        tables = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
    upgrade(MERGE)
    upgrade(MERGE)
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [(MERGE,)]
        for table, (columns, rows) in before.items():
            names = ",".join('"' + n + '"' for n in columns)
            assert connection.execute(f'SELECT {names} FROM "{table}"').fetchall() == rows, table
        assert set(permissions) <= set(connection.execute("SELECT * FROM auth_permissions").fetchall())
        if start == MAIN_HEAD:
            after = dict(connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"))
            assert all(after[name] == definition for name, definition in tables.items())
            assert set(after) - set(tables) == {"collaborative_sheets", "collaborative_sheet_events", "collaborative_sheet_submissions"}
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'collaborative_sheet_events_%'").fetchone()[0] == 2
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
