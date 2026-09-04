"""No business DB: synthetic SQLite/WAL, image, CLI and source safety tests."""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_STORED, ZipFile

import pytest
from PIL import Image

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from legacy_sqlite_reader import (
    SnapshotError,
    _check_wal,
    capture_snapshot,
    file_fingerprint,
    inspect_image,
    inspect_snapshot,
)


def state() -> dict:
    return {"settings": {"machines": 1}, "materials": [{"id": "m1", "name": "PLA"}],
            "products": [], "records": {}, "inventory": {}, "stockInLogs": []}


def make_db(directory: Path) -> Path:
    directory.mkdir()
    path = directory / "data.sqlite"
    with closing(sqlite3.connect(path)) as db:
        db.executescript("""
            CREATE TABLE app_state (id INTEGER PRIMARY KEY, state_json TEXT, updated_at INTEGER);
            CREATE TABLE product_images (product_id TEXT PRIMARY KEY, storage_type TEXT, mime_type TEXT,
                                         image_data BLOB, sha256 TEXT, updated_at INTEGER);
        """)
        db.execute("INSERT INTO app_state VALUES (1, ?, 1788497206084)", (json.dumps(state()),))
        db.commit()
    return path


def cli(*args: str, script: str = "migrate_legacy_three_d_printing.py") -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": "nonexistent_driver://analyze-must-not-load-app-db", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", env=env, timeout=45, check=False)


def test_backup_includes_wal_and_does_not_change_any_source_file(tmp_path):
    path = make_db(tmp_path / "source")
    with closing(sqlite3.connect(path)) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("PRAGMA wal_autocheckpoint=0")
        updated = state()
        updated["products"] = [{"id": "new-in-wal", "name": "New"}]
        writer.execute("UPDATE app_state SET state_json=?", (json.dumps(updated),))
        writer.commit()
        before = {p.name: file_fingerprint(p) for p in path.parent.iterdir()}
        bundle = capture_snapshot(path.parent, tmp_path / "bundle")
        after = {p.name: file_fingerprint(p) for p in path.parent.iterdir()}
        assert before == after
        assert bundle.manifest["counts"]["products"] == 1
        assert bundle.manifest["source"]["wal_validation"]["committed_frames"] > 0
        assert bundle.state == updated
        assert sorted(p.name for p in bundle.path.parent.iterdir()) == ["manifest.json", "snapshot.sqlite"]
        assert bundle.path.read_bytes()[18:20] == bytes([1, 1])
        assert inspect_snapshot(bundle.path)[0] == updated


def test_missing_wal_requires_explicit_checkpoint_attestation(tmp_path):
    path = make_db(tmp_path / "source")
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
    assert not Path(str(path) + "-wal").exists()
    with pytest.raises(SnapshotError, match="wal_missing_requires_checkpoint_confirmation"):
        capture_snapshot(path, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()
    assert capture_snapshot(path, tmp_path / "confirmed", wal_checkpoint_confirmed=True).manifest["checks"]["quick_check"] == "ok"


@pytest.mark.parametrize("corruption", ["header", "payload", "salt", "truncated"])
def test_damaged_wal_fails_instead_of_silent_base_database_fallback(tmp_path, corruption):
    path = make_db(tmp_path / "source")
    frozen = tmp_path / "frozen"
    frozen.mkdir()
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("UPDATE app_state SET updated_at=1788497207000")
        db.commit()
        shutil.copyfile(path, frozen / "data.sqlite")
        wal = bytearray(Path(str(path) + "-wal").read_bytes())
    if corruption == "header":
        wal = bytearray(b"x" * 32)
    elif corruption == "payload":
        wal[60] ^= 1
    elif corruption == "salt":
        wal[40] ^= 1
    else:
        wal = wal[:-1]
    (frozen / "data.sqlite-wal").write_bytes(wal)
    with pytest.raises(SnapshotError, match="wal"):
        capture_snapshot(frozen, tmp_path / "blocked")
    assert not (tmp_path / "blocked").exists()


def test_reused_wal_old_checkpoint_tail_is_accounted_for(tmp_path):
    path = make_db(tmp_path / "source")
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        big = state()
        big["products"] = [{"id": str(i), "name": "product " + "x" * 80} for i in range(100)]
        db.execute("UPDATE app_state SET state_json=?", (json.dumps(big),))
        db.commit()
        db.execute("PRAGMA wal_checkpoint(RESTART)")
        db.execute("UPDATE app_state SET updated_at=1788497207999")
        db.commit()
        result = _check_wal(Path(str(path) + "-wal"))
        assert result["obsolete_tail_frames"] > 0
        captured = capture_snapshot(path.parent, tmp_path / "captured")
        assert captured.manifest["checks"]["state_updated_at_ms"] == 1788497207999
        assert captured.manifest["counts"]["products"] == 100


def test_live_backup_does_not_initialize_nexus_and_sees_commit(tmp_path):
    path = make_db(tmp_path / "source")
    with closing(sqlite3.connect(path)) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("UPDATE app_state SET updated_at=1788497208000")
        db.commit()
        result = cli("--source", path, "--live", "--output-dir", tmp_path / "capture", script="capture_legacy_three_d_snapshot.py")
        assert result.returncode == 0, result.stdout + result.stderr
        assert json.loads(result.stdout)["checks"]["state_updated_at_ms"] == 1788497208000


def test_zip_allowlist_and_source_fingerprint(tmp_path):
    db = make_db(tmp_path / "source")
    archive = tmp_path / "legacy.zip"
    marker = "ghp_" + "Q" * 40
    with ZipFile(archive, "w") as zipped:
        zipped.write(db, "legacy/data.sqlite")
        zipped.writestr("legacy/config.json", marker)
        zipped.writestr("legacy/.git/config", marker)
    before = file_fingerprint(archive)
    captured = capture_snapshot(archive, tmp_path / "captured")
    assert captured.manifest["source"]["sha256"] == before["sha256"]
    assert file_fingerprint(archive) == before
    assert marker not in json.dumps(captured.manifest)
    assert not list(captured.path.parent.rglob("config*"))


@pytest.mark.parametrize("member", ["../data.sqlite", "/data.sqlite", "C:/data.sqlite"])
def test_archive_path_traversal_is_rejected(tmp_path, member):
    db = make_db(tmp_path / "source")
    archive = tmp_path / "legacy.zip"
    with ZipFile(archive, "w") as zipped:
        zipped.writestr(member, db.read_bytes())
    with pytest.raises(SnapshotError):
        capture_snapshot(archive, tmp_path / "captured")


def test_crc_exception_and_bad_arguments_never_echo_sensitive_values(tmp_path):
    db = make_db(tmp_path / "source")
    marker = "ghp_" + "Z" * 40
    archive = tmp_path / "legacy.zip"
    with ZipFile(archive, "w", compression=ZIP_STORED) as zipped:
        zipped.write(db, marker + "/data.sqlite")
    data = bytearray(archive.read_bytes())
    offset = data.find(b"SQLite format 3")
    assert offset >= 0
    data[offset] ^= 1
    archive.write_bytes(data)
    result = cli("--source-zip", archive, "--output-dir", tmp_path / "capture", script="capture_legacy_three_d_snapshot.py")
    assert result.returncode == 2
    assert marker not in result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    bad = cli("--source", marker, "--bad-argument", marker)
    assert bad.returncode == 2
    assert marker not in bad.stdout + bad.stderr


def test_image_blob_signature_decode_and_distinct_legacy_hash():
    stream = BytesIO()
    Image.new("RGB", (8, 8), "red").save(stream, "JPEG")
    content = stream.getvalue()
    result = inspect_image(("p1", "base64", "image/jpeg", content, "old-uri-hash", 1788497206084))
    assert result["valid"]
    assert result["content_sha256"] == sha256(content).hexdigest()
    assert result["legacy_sha256"] == "old-uri-hash"
    assert result["width"] == 8
    assert not inspect_image(("p1", "base64", "image/png", content, "", 0))["valid"]
    assert not inspect_image(("p1", "base64", "image/jpeg", b"broken", "", 0))["valid"]


def test_singleton_schema_and_overlapping_output_are_rejected(tmp_path):
    path = make_db(tmp_path / "source")
    with pytest.raises(SnapshotError, match="overlaps_source"):
        capture_snapshot(path.parent, path.parent / "capture")
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO app_state VALUES(2, '{}', 0)")
    with pytest.raises(SnapshotError, match="singleton"):
        capture_snapshot(path, tmp_path / "capture")


def test_analyze_prefers_sqlite_and_never_initializes_database(tmp_path):
    path = make_db(tmp_path / "source")
    (path.parent / "data.json").write_text("{}")
    report = tmp_path / "analysis.json"
    result = cli("--source", path.parent / "data.json", "--mode", "analyze", "--report", report)
    assert result.returncode == 0, result.stdout + result.stderr
    actual = json.loads(report.read_text(encoding="utf-8"))
    assert actual["source_kind"] == "sqlite"
    assert actual["manifest"]["source"]["json_comparison_error"] == "invalid_compatibility_json"
    assert actual["status"] == "analyzed"


def test_json_fallback_is_explicit_readonly_and_cannot_bypass_audit(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(state()), encoding="utf-8")
    denied = cli("--source", path)
    assert denied.returncode == 2
    allowed = cli("--source", path, "--allow-json-fallback", "--dry-run")
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert json.loads(allowed.stdout)["status"] == "dry_run"
    assert "JSON" in allowed.stderr
    audited = cli("--source", path, "--allow-json-fallback", "--expected-audit", tmp_path / "missing.json")
    assert audited.returncode == 2
    assert "authoritative_audit_requires_sqlite" in audited.stdout
    assert cli("--source", path, "--allow-json-fallback", "--report", path).returncode == 2


def test_sensitive_business_field_is_blocked_before_report_or_capture(tmp_path):
    path = make_db(tmp_path / "source")
    marker = "ghp_" + "A" * 40
    payload = state()
    payload["materials"][0]["name"] = marker
    with sqlite3.connect(path) as db:
        db.execute("UPDATE app_state SET state_json=?", (json.dumps(payload),))
    result = cli("--source-dir", path.parent, "--snapshot-dir", tmp_path / "capture", "--report", tmp_path / "report.json")
    assert result.returncode == 2
    assert marker not in result.stdout + result.stderr
    assert not (tmp_path / "report.json").exists()
    assert not (tmp_path / "capture").exists()


def test_reconciliation_and_resume_require_a_batch_before_loading_target(tmp_path):
    path = make_db(tmp_path / "source")
    result = cli("--source", path, "--mode", "reconcile")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == "reconcile_requires_migration_batch"
    result = cli("--source", path, "--mode", "import", "--resume")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == "resume_requires_import_and_migration_batch"


@pytest.mark.parametrize("mode", ["analyze", "dry-run", "import"])
def test_dry_run_never_loads_target_even_when_import_was_selected(tmp_path, mode):
    path = make_db(tmp_path / "source")
    result = cli("--source", path, "--mode", mode, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["status"] == "dry_run"


def test_import_failed_audit_never_loads_target_or_writes_rows(tmp_path):
    path = make_db(tmp_path / "source")
    audit = tmp_path / "audit.json"
    audit.write_text("{}", encoding="utf-8")
    result = cli("--source", path, "--mode", "import", "--expected-audit", audit)
    assert result.returncode == 2
    assert json.loads(result.stdout)["baseline_validation"]["status"] == "failed"
    assert json.loads(result.stdout)["status"] == "analyzed_with_errors"


def test_source_directory_alias_keeps_report_outside_source(tmp_path):
    path = make_db(tmp_path / "source")
    output = path.parent / "analysis.json"
    result = cli("--source", path.parent, "--report", output)
    assert result.returncode == 2
    assert json.loads(result.stdout)["error_code"] == "report_output_overlaps_source"
    assert not output.exists()


@pytest.mark.parametrize("size", ["99", "501", "not-a-number"])
def test_invalid_checkpoint_size_is_rejected(tmp_path, size):
    path = make_db(tmp_path / "source")
    assert cli("--source", path, "--chunk-size", size).returncode == 2


def test_capture_repeat_has_same_content_and_never_overwrites_bundle(tmp_path):
    path = make_db(tmp_path / "source")
    first = capture_snapshot(path, tmp_path / "first")
    second = capture_snapshot(path, tmp_path / "second")
    assert first.manifest["snapshot"] == second.manifest["snapshot"]
    assert first.manifest["counts"] == second.manifest["counts"]
    with pytest.raises(SnapshotError, match="already_exists"):
        capture_snapshot(path, tmp_path / "first")


def test_manifest_matches_schema_required_fields(tmp_path):
    path = make_db(tmp_path / "source")
    captured = capture_snapshot(path, tmp_path / "capture")
    schema = json.loads((SCRIPTS / "legacy_snapshot_manifest.schema.json").read_text())
    assert set(captured.manifest) == set(schema["required"])
    assert set(captured.manifest) <= set(schema["properties"])
    for key in ("schema_version", "tool_version", "factory_id", "site_code", "metadata_policy"):
        assert captured.manifest[key] == schema["properties"][key]["const"]
