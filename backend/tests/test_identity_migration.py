"""Rehearse the real Alembic chain on synthetic legacy rows, never a live DB."""
import importlib.util
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from uuid import uuid4
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
HEAD = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini"))).get_current_head()


def test_additive_upgrade_preserves_legacy_rows_and_is_idempotent(tmp_path):
    database = tmp_path / "legacy.db"
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{database.as_posix()}", SEED_ADMIN_PASSWORD="", AUTHZ_MODE="enforce")
    def upgrade(target):
        run = subprocess.run([sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", target],
                             cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
        assert run.returncode == 0, run.stderr
    upgrade("20260924_0124")
    with sqlite3.connect(database) as db:
        def insert(table, values):
            # Supply every required pre-V2 column, with synthetic non-sensitive data.
            for _, name, kind, required, default, pk in db.execute(f'PRAGMA table_info("{table}")'):
                if name not in values and required and default is None:
                    values[name] = 0 if "INT" in kind else ""
            columns = ','.join('"' + c + '"' for c in values)
            db.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({",".join("?" for _ in values)})', tuple(values.values()))
        insert("auth_users", {"id": "legacy-test", "username": "legacy-test", "display_name": "隔离迁移", "status": "suspended",
                              "password_salt": "synthetic-not-a-password", "password_hash": "synthetic-not-a-hash"})
        insert("employee_profiles", {"user_id": "legacy-test", "primary_factory_id": "huakang-a", "primary_department": "management", "position": "本厂总务"})
        insert("auth_roles", {"id": "migration-role", "code": "migration-role", "name": "迁移测试"})
        insert("auth_user_roles", {"id": "legacy-binding", "user_id": "legacy-test", "role_id": "migration-role", "factory_id": "huakang-a", "department": "management"})
        insert("auth_role_binding_metadata", {"user_role_id": "legacy-binding", "state": "revoked", "valid_from": "2099-01-01 00:00:00", "source_type": "legacy_import"})
        watched = ["auth_users", "employee_profiles", "auth_user_roles", "auth_role_binding_metadata", "auth_user_permission_overrides"]
        before = {table: ([c[1] for c in db.execute(f'PRAGMA table_info("{table}")')], db.execute(f'SELECT * FROM "{table}"').fetchall()) for table in watched}
        db.commit()
    # Rehearse maintenance-window recovery before admitting any V2 writes.
    # SQLite DDL can survive a failed migration; do not blindly rerun it.
    backup = tmp_path / "before-interruption.db"
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.backup(target)
    interrupted_script = '''
from alembic import command
from alembic.config import Config
from alembic.operations import Operations
original = Operations.create_table
def interrupted(self, name, *args, **kwargs):
    result = original(self, name, *args, **kwargs)
    if name == "iam_org_units":
        raise RuntimeError("IAM_TEST_INTERRUPTED_AFTER_FIRST_V2_TABLE")
    return result
Operations.create_table = interrupted
command.upgrade(Config("alembic.ini"), "head")
'''
    interrupted = subprocess.run([sys.executable, "-c", interrupted_script], cwd=BACKEND, env=env,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    assert interrupted.returncode != 0
    assert "IAM_TEST_INTERRUPTED_AFTER_FIRST_V2_TABLE" in interrupted.stderr
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20260924_0124"
    # Only disposable test files are restored. Real recovery requires the
    # verified pre-migration backup while the maintenance window is still held.
    with sqlite3.connect(backup) as source, sqlite3.connect(database) as target:
        source.backup(target)
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT count(*) FROM sqlite_master WHERE name='iam_org_units'").fetchone()[0] == 0
    upgrade("head")
    upgrade("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(HEAD,)]
        for table, (columns, rows) in before.items():
            names = ','.join('"' + c + '"' for c in columns)
            assert db.execute(f'SELECT {names} FROM "{table}"').fetchall() == rows
        assert db.execute("SELECT identity_mode,employment_epoch,primary_factory_id FROM employee_profiles WHERE user_id='legacy-test'").fetchone() == ("legacy", 1, "huakang-a")
        assert db.execute("SELECT count(*) FROM employee_assignments").fetchone()[0] == 0
        assert db.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
    spec = importlib.util.spec_from_file_location("iam_preflight", BACKEND / "tools/iam_v2_preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    stat = database.stat()
    report = module.inspect_copy(database)
    assert report["integrity"] == "ok"
    assert database.stat().st_mtime_ns == stat.st_mtime_ns


def test_postgres_real_alembic_chain_in_disposable_schema():
    url = os.getenv('IAM_TEST_POSTGRES_URL', '')
    if not url:
        pytest.skip('IAM_TEST_POSTGRES_URL not provided')
    parsed = make_url(url)
    assert parsed.host in {'127.0.0.1', 'localhost'} and parsed.database == 'iam_v2_test'
    schema = 'iam_qa_' + uuid4().hex
    control = create_engine(url)
    with control.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_url = parsed.update_query_dict({'options': f'-csearch_path={schema}'}).render_as_string(hide_password=False)
    env = dict(os.environ, DATABASE_URL=scoped_url, SEED_ADMIN_PASSWORD='')
    engine = create_engine(scoped_url)
    try:
        for target in ('20260924_0124', 'head', 'head'):
            run = subprocess.run([sys.executable, '-m', 'alembic', '-c', str(BACKEND / 'alembic.ini'), 'upgrade', target],
                                 cwd=BACKEND, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=240)
            assert run.returncode == 0, run.stderr[-15000:]
        with engine.connect() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version')) == HEAD
            assert connection.scalar(text("SELECT count(*) FROM auth_iam_state WHERE key='identity_mutation_lock'")) == 1
            assert connection.scalar(text('SELECT count(*) FROM employee_assignments')) == 0
    finally:
        engine.dispose()
        assert schema.startswith('iam_qa_') and len(schema) == 39
        with control.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        control.dispose()
