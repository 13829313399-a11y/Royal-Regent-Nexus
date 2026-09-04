"""Exercise the public CLI against a disposable target, including exit codes."""
from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

BACKEND = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND / "scripts" / "migrate_legacy_three_d_printing.py"


def environment(tmp_path):
    return {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'target.db'}",
            "THREE_D_ASSET_DIR": str(tmp_path / "assets"), "PYTHONIOENCODING": "utf-8"}


def run_cli(env, *args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], env=env,
                          cwd=BACKEND, capture_output=True, text=True, encoding="utf-8", timeout=90, check=False)


def source(tmp_path):
    directory = tmp_path / "source"
    directory.mkdir()
    path = directory / "snapshot.sqlite"
    state = {"settings": {"machines": 1, "elecPerMachine": 1.5, "laborPerDay": 220,
                           "lossRate": 1.2, "profitRate": 40},
             "materials": [{"id": "m1", "name": "PLA", "priceKg": 19}],
             "products": [{"id": "p1", "name": "Current name", "material": "PLA",
                           "weight": 10, "time": 2, "qty": 2, "price": 20, "customer": ""}],
             "records": {"2026-09-01": {"items": [{"_id": "r1", "productName": "Historic name",
                 "material": "PLA", "weight": 10, "qty": 2, "time": 2, "price": 20,
                 "machine": 1, "status": "running", "autoRecord": True,
                 "printStartTime": "2026-09-01T08:00:00+08:00",
                 "printEndTime": "2026-09-01T10:00:00+08:00"}]}},
             "inventory": {"PLA": {"stockG": 500, "minStockG": 100}},
             "stockInLogs": [{"id": "s1", "date": "2026-08-01", "material": "PLA", "amountG": 1000,
                              "cost": 19}], "schedules": [], "maintenance": []}
    stream = BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, "JPEG")
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE app_state (id INTEGER PRIMARY KEY, state_json TEXT, updated_at INTEGER);
            CREATE TABLE product_images (product_id TEXT PRIMARY KEY, storage_type TEXT, mime_type TEXT,
                                         image_data BLOB, sha256 TEXT, updated_at INTEGER);
        """)
        db.execute("INSERT INTO app_state VALUES (1, ?, 1788497206084)", (json.dumps(state),))
        db.execute("INSERT INTO product_images VALUES (?, ?, ?, ?, ?, ?)",
                   ("p1", "base64", "image/jpeg", stream.getvalue(), "legacy-uri-hash", 1788497206084))
        db.commit()
    return path


def test_cli_import_repeat_reconcile_and_detect_asset_tamper(tmp_path):
    env = environment(tmp_path)
    # Alembic upgrade itself is separately covered by the v2 schema suite.
    setup = subprocess.run([sys.executable, "-c",
        ("from app.db import Base,engine,SessionLocal; from app.models import three_d_printing as m; "
        "Base.metadata.create_all(engine); db=SessionLocal(); "
        "db.add(m.ThreeDPrintingSite(id='3dsite-huakang-a-heyuan',factory_id='huakang-a',site_code='heyuan',"
        "name='Heyuan',timezone='Asia/Shanghai',enabled=True,created_at='',updated_at='')); db.commit(); db.close()")],
        env=env, cwd=BACKEND, capture_output=True, text=True, timeout=90, check=False)
    assert setup.returncode == 0, setup.stderr
    path = source(tmp_path)
    original_hash = sha256(path.read_bytes()).hexdigest()
    first_path = tmp_path / "import.json"
    first = run_cli(env, "--source", path, "--mode", "import", "--report", first_path)
    assert first.returncode == 0, first.stdout + first.stderr
    report = json.loads(first_path.read_text(encoding="utf-8"))
    assert report["reconciliation"]["passed"] is True
    batch_id = report["batch_id"]
    with closing(sqlite3.connect(tmp_path / "target.db")) as db:
        counts_before = {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                         for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'three_d_printing_audit_events'")}
        assert db.execute("SELECT product_name FROM three_d_printing_production_records").fetchone()[0] == "Historic name"
        assert db.execute("SELECT SUM(stock_g) FROM three_d_printing_inventory").fetchone()[0] == 500
        assert db.execute("SELECT delta_g, affects_balance FROM three_d_printing_inventory_movements WHERE movement_type='legacy_history_only'").fetchone() == (1000, 0)
    repeated_path = tmp_path / "repeat.json"
    repeated = run_cli(env, "--source", path, "--mode", "import", "--report", repeated_path)
    assert repeated.returncode == 0, repeated.stdout + repeated.stderr
    assert json.loads(repeated_path.read_text(encoding="utf-8"))["status"] == "already_reconciled"
    with closing(sqlite3.connect(tmp_path / "target.db")) as db:
        assert counts_before == {name: db.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
                                 for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name != 'three_d_printing_audit_events'")}
    checked = run_cli(env, "--source", path, "--mode", "reconcile", "--migration-batch", batch_id)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert json.loads(checked.stdout)["reconciliation"]["passed"] is True
    files = [p for p in (tmp_path / "assets").rglob("*") if p.is_file()]
    assert files
    files[0].write_bytes(b"damaged asset")
    damaged = run_cli(env, "--source", path, "--mode", "reconcile", "--migration-batch", batch_id)
    assert damaged.returncode == 2, damaged.stdout + damaged.stderr
    assert json.loads(damaged.stdout)["reconciliation"]["passed"] is False
    assert sha256(path.read_bytes()).hexdigest() == original_hash


def test_missing_target_schema_is_not_created_by_import(tmp_path):
    env = environment(tmp_path)
    path = source(tmp_path)
    failed = run_cli(env, "--source", path, "--mode", "import")
    assert failed.returncode == 2
    assert "Traceback" not in failed.stderr
    target = tmp_path / "target.db"
    if target.exists():
        with closing(sqlite3.connect(target)) as db:
            assert db.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0


@pytest.mark.parametrize("kind", ["target", "assets", "captured_assets"])
def test_writing_paths_cannot_overlap_source_or_captured_bundle(tmp_path, kind):
    env = environment(tmp_path)
    path = source(tmp_path)
    before = sha256(path.read_bytes()).hexdigest()
    options = []
    if kind == "target":
        env["DATABASE_URL"] = f"sqlite:///{path.parent / 'nexus.db'}"
        expected = "target_database_overlaps_source"
    elif kind == "assets":
        env["THREE_D_ASSET_DIR"] = str(path.parent / "assets")
        expected = "asset_directory_overlaps_source"
    else:
        capture = tmp_path / "capture"
        env["THREE_D_ASSET_DIR"] = str(capture / "assets")
        options = ["--snapshot-dir", capture]
        expected = "asset_directory_overlaps_source"
    result = run_cli(env, "--source", path, "--mode", "import", *options)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == expected
    assert sha256(path.read_bytes()).hexdigest() == before
    assert not (path.parent / "nexus.db").exists()
    assert not (path.parent / "assets").exists()
    assert not (tmp_path / "capture" / "assets").exists()


@pytest.mark.parametrize("kind", ["snapshot", "target", "asset"])
def test_report_cannot_be_created_over_migration_outputs(tmp_path, kind):
    env = environment(tmp_path)
    path = source(tmp_path)
    options = []
    if kind == "snapshot":
        options = ["--snapshot-dir", tmp_path / "capture"]
        report = tmp_path / "capture" / "snapshot.sqlite"
        code = "report_output_overlaps_snapshot_directory"
    elif kind == "target":
        report = tmp_path / "target.db"
        code = "report_output_overlaps_target_database"
    else:
        report = tmp_path / "assets" / "report.json"
        code = "report_output_overlaps_asset_directory"
    result = run_cli(env, "--source", path, "--mode", "import", "--report", report, *options)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == code
    assert not (tmp_path / "target.db").exists()
    assert not report.exists()
