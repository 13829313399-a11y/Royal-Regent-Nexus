"""An additive grouping field preserves all original and scope constraints."""
import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from test_carton_mark_assets_migration import _run_alembic
from test_carton_mark_asset_images_migration import foreign_key_contracts, index_contracts


def test_photo_group_migration_preserves_original_and_blocks_group_loss(tmp_path):
    path = tmp_path / "groups.db"
    url = f"sqlite:///{path.as_posix()}"
    result = _run_alembic(url, "upgrade", "20261006_0138")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO carton_mark_assets VALUES
          ('photo','huaxing','未命名.png','image','image/png',3,'digest',X'000102',
           '4500222793',NULL,'manual','[]','',7,0,'user','员工','before','before')""")
        columns = ','.join('"' + row[1] + '"' for row in db.execute('PRAGMA table_info("carton_mark_assets")'))
        before = db.execute("SELECT " + columns + " FROM carton_mark_assets").fetchall()
        indexes, keys = index_contracts(db), foreign_key_contracts(db)
    result = _run_alembic(url, "upgrade", "20261006_0139")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT " + columns + " FROM carton_mark_assets").fetchall() == before
        assert db.execute("SELECT photo_group_id FROM carton_mark_assets").fetchone() == (None,)
        assert foreign_key_contracts(db) == keys
        assert all(index in index_contracts(db) for index in indexes)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        db.execute("UPDATE carton_mark_assets SET photo_group_id='group',is_archived=1")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE carton_mark_assets SET kind='pdf'")
    result = _run_alembic(url, "downgrade", "20261006_0138")
    assert result.returncode != 0 and "禁止降级" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261006_0139"
        db.execute("UPDATE carton_mark_assets SET photo_group_id=NULL,is_archived=0")
    result = _run_alembic(url, "downgrade", "20261006_0138")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM carton_mark_assets").fetchall() == before
        assert index_contracts(db) == indexes
        assert foreign_key_contracts(db) == keys


def test_postgres_grouping_ddl_is_additive():
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"),
        "upgrade", "20261006_0138:20261006_0139", "--sql"], cwd=backend, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": "postgresql://fixture:fixture@localhost/fixture", "ALEMBIC_OFFLINE_METADATA_ONLY": "1"}, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "ADD COLUMN photo_group_id VARCHAR(96)" in result.stdout
    assert "photo_group_id IS NULL OR kind = 'image'" in result.stdout
    assert "CREATE INDEX ix_carton_mark_asset_factory_photo_group" in result.stdout
    assert "DROP TABLE" not in result.stdout and "DELETE FROM" not in result.stdout


def test_startup_requires_photo_group_field(monkeypatch, tmp_path):
    db_module = importlib.import_module("app.db")
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy-group.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE alembic_version(version_num TEXT)"))
        db.execute(text("INSERT INTO alembic_version VALUES ('20261006_0138')"))
        for table in ["carton_mark_customers", "carton_mark_templates", "carton_mark_documents"]:
            db.execute(text(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)"))
        db.execute(text("CREATE TABLE carton_mark_assets(id TEXT PRIMARY KEY, kind TEXT, CONSTRAINT ck_carton_mark_asset_kind CHECK(kind IN ('excel','pdf','image')))"))
    monkeypatch.setattr(db_module, "engine", engine)
    with pytest.raises(RuntimeError, match="照片分组字段"):
        db_module.ensure_carton_mark_library_schema_ready()
    engine.dispose()
