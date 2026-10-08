"""Upgrade both published branches in disposable databases without rewriting history."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.schemas.module_feedback import FeedbackCreate
from app.services.module_feedback import create_ticket, validate_uploads
from test_module_feedback import create_payload, png, user


BACKEND = Path(__file__).resolve().parents[1]
MERGE = "20261005_0131"
ASSISTANT_MERGE = "20261008_0140"


@pytest.mark.parametrize("start", ["20260929_0130", "20261005_0120", "20260929_0131", "20261006_0139"])
def test_both_branches_upgrade_to_single_head_preserving_existing_rows(tmp_path, start):
    database = tmp_path / (start + ".db")
    env = dict(os.environ, DATABASE_URL="sqlite:///" + database.as_posix(), SEED_ADMIN_PASSWORD="",
               AUTHZ_MODE="enforce", AUTHZ_WRITES_ENABLED="false", IAM_IDENTITY_WRITES_ENABLED="false",
               IAM_IDENTITY_SCHEDULING_ENABLED="false", PYTHONIOENCODING="utf-8")

    def upgrade(revision):
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", revision], cwd=BACKEND,
            env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        assert result.returncode == 0, result.stderr

    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    heads = script.get_heads()
    assert len(heads) == 1
    head = heads[0]
    assert ASSISTANT_MERGE in {revision.revision for revision in script.walk_revisions()}
    assert set(script.get_revision(ASSISTANT_MERGE).down_revision) == {"20260929_0131", "20261006_0139"}
    assert set(script.get_revision(MERGE).down_revision) == {"20260929_0130", "20261005_0120"}
    assert script.get_revision("20261005_0120").down_revision == "20260924_0119"
    upgrade(start)
    with sqlite3.connect(database) as connection:
        values = {"id": "preserve-account", "username": "preserve-account", "status": "suspended"}
        for _, name, kind, required, default, _ in connection.execute('PRAGMA table_info("auth_users")'):
            if name not in values and required and default is None:
                values[name] = 0 if "INT" in kind else ""
        connection.execute('INSERT INTO auth_users (' + ','.join('"' + name + '"' for name in values) + ') VALUES (' +
            ','.join('?' for _ in values) + ')', tuple(values.values()))
        if start == "20260929_0131":
            connection.execute("""INSERT INTO nexus_assistant_sessions
                (id, owner_user_id, employment_epoch, create_request_id, title, revision,
                 deletion_state, created_at, updated_at, budget_tokens, budget_unknown)
                VALUES ('preserve-session', 'preserve-account', 1, 'preserve-request',
                        'Existing private conversation', 1, 'active', 1, 1, 0, 0)""")
    if start == "20261005_0120":
        engine = create_engine("sqlite:///" + database.as_posix())
        with Session(engine) as db:
            create_ticket(db, user(), FeedbackCreate(**create_payload()), validate_uploads([("evidence.png", png())]))
        engine.dispose()
    with sqlite3.connect(database) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
                  if row[0] not in {"alembic_version", "sqlite_sequence", "auth_permissions"}]
        before = {table: ([row[1] for row in connection.execute('PRAGMA table_info("' + table + '")')],
                          connection.execute('SELECT * FROM "' + table + '"').fetchall()) for table in tables}
        permissions = connection.execute("SELECT * FROM auth_permissions ORDER BY id").fetchall()
    upgrade("head")
    upgrade("head")
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchall() == [(head,)]
        for table, (columns, rows) in before.items():
            quoted = ','.join('"' + name + '"' for name in columns)
            after = connection.execute('SELECT ' + quoted + ' FROM "' + table + '"').fetchall()
            if table == "auth_permission_metadata" and start == "20261005_0120":
                # Main's existing UV replacement migration registers 18 new
                # metadata rows while traversing the older local branch.
                assert set(rows).issubset(after), table
                added = set(after) - set(rows)
                assert len(added) == 18 and all(row[columns.index("module_code")] == "uv_ops" for row in added)
                continue
            if table == "auth_iam_state" and start == "20261005_0120":
                # The already-published identity migration installs its shared
                # mutation lock; the feedback merge adds no IAM state itself.
                assert set(rows).issubset(after), table
                assert set(after) - set(rows) == {("identity_mutation_lock", "{}", "")}
                continue
            assert sorted(after, key=repr) == sorted(rows, key=repr), table
        # Forward migrations may register their own codes; they never remove old permissions.
        after_permissions = set(connection.execute("SELECT * FROM auth_permissions").fetchall())
        assert set(permissions).issubset(after_permissions)
        assert connection.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE 'module_feedback_%'").fetchone()[0] == 6
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        if start == "20261005_0120":
            assert connection.execute("SELECT COUNT(*) FROM module_feedback_tickets").fetchone()[0] == 1
