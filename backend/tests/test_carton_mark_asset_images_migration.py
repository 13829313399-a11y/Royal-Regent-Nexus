"""The new kind constraint preserves stored bytes and association boundaries."""
import importlib
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text, MetaData, Table

from test_carton_mark_assets_migration import _run_alembic


def index_contracts(db):
    return sorted((bool(row[2]), tuple(col[2] for col in db.execute(f'PRAGMA index_info("{row[1]}")')))
                  for row in db.execute('PRAGMA index_list("carton_mark_assets")'))


def foreign_key_contracts(db):
    return sorted(tuple(row[2:]) for row in db.execute('PRAGMA foreign_key_list("carton_mark_assets")'))


def test_image_upgrade_preserves_originals_keys_and_safe_downgrade(tmp_path):
    path = tmp_path / "photos.db"
    url = f"sqlite:///{path.as_posix()}"
    result = _run_alembic(url, "upgrade", "20261006_0137")
    assert result.returncode == 0, result.stderr
    engine = create_engine(url)
    # Seed the historical schema, before later order-weight fields existed.
    orders = Table("carton_orders", MetaData(), autoload_with=engine)
    with engine.begin() as db:
        db.execute(orders.insert().values(id="image-migration-order", factory_id="huaxing",
            order_no="image-migration-order", customer_code="ZURU", customer_name="ZURU",
            supplier_id="test-supplier", supplier_name_snapshot="测试供应商",
            contract_no="4500222793", item_no="100369", quantity_basis="EXPLICIT",
            product_order_quantity=None, order_date="2026-10-05", due_date="2026-10-10",
            status="DRAFT", created_by="seed", created_by_name="seed",
            updated_by="seed", updated_by_name="seed", created_at="2026-10-05", updated_at="2026-10-05"))
    engine.dispose()
    with sqlite3.connect(path) as db:
        db.execute("""INSERT INTO carton_mark_assets
          VALUES ('preserved','huaxing','4500222793.pdf','pdf','application/pdf',3,'digest',X'000102',
          '4500222793','image-migration-order','manual_order','[]','warning',7,0,'user','员工','before','before')""")
        before = db.execute("SELECT * FROM carton_mark_assets").fetchall()
        indexes, foreign_keys = index_contracts(db), foreign_key_contracts(db)
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE carton_mark_assets SET kind='image'")
    result = _run_alembic(url, "upgrade", "20261006_0138")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM carton_mark_assets").fetchall() == before
        assert index_contracts(db) == indexes
        assert foreign_key_contracts(db) == foreign_keys
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        db.execute("UPDATE carton_mark_assets SET kind='image', is_archived=1")
    result = _run_alembic(url, "downgrade", "20261006_0137")
    assert result.returncode != 0 and "禁止降级" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "20261006_0138"
        assert db.execute("SELECT content,kind FROM carton_mark_assets").fetchone() == (b"\0\1\2", "image")
        db.execute("UPDATE carton_mark_assets SET kind='pdf', is_archived=0")
    result = _run_alembic(url, "downgrade", "20261006_0137")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT * FROM carton_mark_assets").fetchall() == before
        assert foreign_key_contracts(db) == foreign_keys
        assert index_contracts(db) == indexes


def test_postgres_image_migration_emits_only_constraint_change():
    backend = Path(__file__).resolve().parents[1]
    result = subprocess.run([sys.executable, "-m", "alembic", "-c", str(backend / "alembic.ini"),
        "upgrade", "20261006_0137:20261006_0138", "--sql"], cwd=backend, capture_output=True, text=True,
        env={**os.environ, "DATABASE_URL": "postgresql://fixture:fixture@localhost/fixture",
             "ALEMBIC_OFFLINE_METADATA_ONLY": "1"}, encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert "DROP CONSTRAINT ck_carton_mark_asset_kind" in result.stdout
    assert "ADD CONSTRAINT ck_carton_mark_asset_kind CHECK (kind IN ('excel', 'pdf', 'image'))" in result.stdout
    assert "DROP TABLE" not in result.stdout and "DELETE FROM" not in result.stdout


def test_startup_refuses_legacy_photo_constraint(monkeypatch, tmp_path):
    db_module = importlib.import_module("app.db")
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as db:
        db.execute(text("CREATE TABLE alembic_version(version_num TEXT)"))
        db.execute(text("INSERT INTO alembic_version VALUES ('legacy')"))
        for table in ["carton_mark_customers", "carton_mark_templates", "carton_mark_documents"]:
            db.execute(text(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)"))
        db.execute(text("CREATE TABLE carton_mark_assets(id TEXT PRIMARY KEY, kind TEXT, CONSTRAINT ck_carton_mark_asset_kind CHECK(kind IN ('excel','pdf')))"))
    monkeypatch.setattr(db_module, "engine", engine)
    with pytest.raises(RuntimeError, match="图片格式约束"):
        db_module.ensure_carton_mark_library_schema_ready()
    engine.dispose()
