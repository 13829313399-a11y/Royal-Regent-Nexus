"""Rehearse the real migration graph in an explicit disposable SQLite file."""
import hashlib
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_upgrade_from_previous_head_preserves_legacy_and_is_repeatable(tmp_path):
    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / "spray-migration-rehearsal.db"
    env = dict(os.environ, DATABASE_URL="sqlite:///" + database.as_posix(), SPRAY_OPS_ENABLED="false", SEED_DEFAULT_ACCOUNTS="false", PYTHONUTF8="1")
    def upgrade(revision):
        result = subprocess.run([sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"), "upgrade", revision], cwd=backend, env=env, capture_output=True, text=True, encoding="utf-8", timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
    upgrade("20260922_0118")
    with sqlite3.connect(database) as db:
        db.execute("INSERT INTO customer_price_settings (factory_id,customer_id,revision,settings_json,updated_at,updated_by,updated_by_name) VALUES ('huaxing','buzzbee',1,'{}','2026-09-22','merge-probe','Synthetic probe')")
        legacy = db.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()
        assert legacy, "Historical migration tables must exist in the rehearsal"
        old_counts = {name: db.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0] for name, _ in legacy}
        db.execute("CREATE TABLE spray_history_probe (id TEXT PRIMARY KEY, frozen_cost TEXT)")
        db.execute("INSERT INTO spray_history_probe VALUES ('immutable-test','0736.00')")
    upgrade("head")
    upgrade("head")
    with sqlite3.connect(database) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20260922_0119"
        assert db.execute("SELECT revision,settings_json,updated_by FROM customer_price_settings WHERE factory_id='huaxing' AND customer_id='buzzbee'").fetchone() == (1, '{}', 'merge-probe')
        assert db.execute("SELECT * FROM spray_history_probe").fetchall() == [("immutable-test", "0736.00")]
        assert len(db.execute("SELECT id FROM spray_ops_factories").fetchall()) == 4
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        for name, ddl in legacy:
            assert db.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()[0] == ddl
            assert db.execute('SELECT COUNT(*) FROM "' + name + '"').fetchone()[0] == old_counts[name]
