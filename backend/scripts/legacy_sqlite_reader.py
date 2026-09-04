"""Read-only legacy SQLite/WAL capture; independent of Nexus settings and DB.

Offline sources are copied to a disposable directory before SQLite opens them.
Live sources use the SQLite online backup API with a read-only connection.
Only app_state and product_images are accepted; never extract config or .git.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import struct
import tempfile
import time
from typing import Any
import warnings
from zipfile import ZipFile

from PIL import Image
from scan_three_d_secrets import scan_text

VERSION = "three-d-snapshot-v1"
FACTORY_ID = "huakang-a"
SITE_CODE = "heyuan"
MAX_SOURCE_BYTES = 2 * 1024**3
MAX_STATE_BYTES = 128 * 1024**2
MAX_IMAGE_BYTES = 20 * 1024**2
MAX_IMAGE_PIXELS = 25_000_000
MEMBERS = ("data.sqlite", "data.sqlite-wal", "data.sqlite-shm", "data.json")


class SnapshotError(ValueError):
    """Static codes only: source exceptions/values may contain credentials."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def file_fingerprint(path: Path) -> dict[str, Any]:
    digest = sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
            size += len(block)
    return {"size_bytes": size, "sha256": digest.hexdigest()}


def read_json(path: Path) -> dict[str, Any]:
    if path.stat().st_size > MAX_STATE_BYTES:
        raise SnapshotError("source_json_too_large")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError):
        raise SnapshotError("invalid_source_json") from None
    validate_state(value)
    assert_no_secrets(value)
    return value


def assert_no_secrets(value: Any) -> None:
    """Fail closed before a source payload or report leaves private scratch."""
    if any(scan_text(json.dumps(value, ensure_ascii=False)).values()):
        raise SnapshotError("sensitive_source_or_report_blocked")


def validate_state(state: Any) -> None:
    expected = {"settings": dict, "materials": list, "products": list,
                "records": dict, "inventory": dict}
    if not isinstance(state, dict) or any(
        not isinstance(state.get(key), kind) for key, kind in expected.items()
    ):
        raise SnapshotError("invalid_app_state_shape")
    for key in ("materials", "products", "stockInLogs", "schedules", "maintenance"):
        rows = state.get(key, [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SnapshotError("invalid_app_state_rows")
    for day in state["records"].values():
        if not isinstance(day, dict) or not isinstance(day.get("items"), list):
            raise SnapshotError("invalid_record_day")
        if any(not isinstance(row, dict) for row in day["items"]):
            raise SnapshotError("invalid_record_row")
    if any(not isinstance(row, dict) for row in state["inventory"].values()):
        raise SnapshotError("invalid_inventory_row")


def connect_readonly(path: Path) -> sqlite3.Connection:
    # Do not use immutable=1 here: that flag silently ignores committed WAL.
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    db.execute("PRAGMA query_only=ON")
    db.execute("PRAGMA trusted_schema=OFF")
    return db


def _check_database(db: sqlite3.Connection) -> dict[str, str]:
    tables = db.execute(
        "SELECT name, type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' "
        "AND type IN ('table', 'view')"
    ).fetchall()
    if set(tables) != {("app_state", "table"), ("product_images", "table")}:
        raise SnapshotError("unexpected_source_schema")
    expected = {
        "app_state": {"id", "state_json", "updated_at"},
        "product_images": {"product_id", "storage_type", "mime_type", "image_data", "sha256", "updated_at"},
    }
    for table, columns in expected.items():
        actual = {row[1] for row in db.execute(f'PRAGMA table_info("{table}")')}
        if not columns.issubset(actual):
            raise SnapshotError("missing_source_columns")
    for check in ("quick_check", "integrity_check"):
        if db.execute(f"PRAGMA {check}").fetchall() != [("ok",)]:
            raise SnapshotError("sqlite_integrity_failed")
    if db.execute("SELECT id FROM app_state").fetchall() != [(1,)]:
        raise SnapshotError("app_state_must_be_singleton")
    return {"quick_check": "ok", "integrity_check": "ok"}


def inspect_image(row: tuple[Any, ...]) -> dict[str, Any]:
    product_id, storage, mime, content, legacy_hash, updated_at = row
    result = {
        "product_id": str(product_id), "storage_type": str(storage),
        "mime_type": str(mime), "legacy_sha256": str(legacy_hash),
        "updated_at": updated_at, "content_sha256": "", "size_bytes": 0,
        "width": 0, "height": 0, "valid": False, "error_code": None,
    }
    if not isinstance(content, bytes) or not content or len(content) > MAX_IMAGE_BYTES:
        result["error_code"] = "invalid_image_blob_or_size"
        return result
    result.update(size_bytes=len(content), content_sha256=sha256(content).hexdigest())
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as picture:
                detected = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(picture.format)
                if detected is None or detected != str(mime).lower():
                    raise SnapshotError("image_mime_mismatch")
                if picture.width * picture.height > MAX_IMAGE_PIXELS:
                    raise SnapshotError("image_pixel_limit")
                result.update(width=picture.width, height=picture.height)
                picture.verify()
            with Image.open(BytesIO(content)) as picture:
                picture.load()
    except SnapshotError as exc:
        result["error_code"] = exc.code
        return result
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombWarning, Image.DecompressionBombError):
        result["error_code"] = "image_decode_failed"
        return result
    result["valid"] = True
    return result


def inspect_snapshot(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    """Return business state, image metadata, validation. Never return BLOBs."""
    try:
        with closing(connect_readonly(path)) as db:
            checks = _check_database(db)
            length = db.execute("SELECT length(CAST(state_json AS BLOB)) FROM app_state WHERE id=1").fetchone()[0]
            if length is None or length > MAX_STATE_BYTES:
                raise SnapshotError("state_json_too_large")
            raw, updated_at = db.execute("SELECT state_json, updated_at FROM app_state WHERE id=1").fetchone()
            state = json.loads(raw)
            validate_state(state)
            assert_no_secrets(state)
            images = [inspect_image(row) for row in db.execute(
                "SELECT product_id, storage_type, mime_type, image_data, sha256, updated_at "
                "FROM product_images ORDER BY product_id"
            )]
            assert_no_secrets(images)
            return state, images, {
                **checks, "state_updated_at_ms": updated_at,
                "state_updated_at_utc": datetime.fromtimestamp(int(updated_at) / 1000, UTC).isoformat(),
                "state_json_chars": len(raw),
            }
    except SnapshotError:
        raise
    except (sqlite3.Error, ValueError, TypeError, OverflowError, OSError):
        raise SnapshotError("invalid_legacy_sqlite") from None


def _wal_required(path: Path) -> bool:
    with path.open("rb") as stream:
        header = stream.read(100)
    if len(header) < 100 or header[:16] != b"SQLite format 3\x00":
        raise SnapshotError("invalid_sqlite_header")
    return header[18] == 2 or header[19] == 2


def _check_wal(path: Path) -> dict[str, int]:
    result = {"valid_frames": 0, "committed_frames": 0, "obsolete_tail_frames": 0}
    if not path.exists() or path.stat().st_size == 0:
        return result
    with path.open("rb") as stream:
        header = stream.read(32)
    if len(header) != 32:
        raise SnapshotError("invalid_wal_header")
    magic, version, page_size = struct.unpack(">III", header[:12])
    if magic not in (0x377F0682, 0x377F0683) or version != 3007000 or page_size < 512 or page_size > 65536 or page_size & (page_size - 1):
        raise SnapshotError("invalid_wal_header")
    if (path.stat().st_size - 32) % (24 + page_size):
        raise SnapshotError("truncated_wal_frame")
    word_order = "<" if magic == 0x377F0682 else ">"

    def checksum(data: bytes, sums: tuple[int, int]) -> tuple[int, int]:
        first, second = sums
        for left, right in struct.iter_unpack(word_order + "II", data):
            first = (first + left + second) & 0xFFFFFFFF
            second = (second + right + first) & 0xFFFFFFFF
        return first, second

    sums = checksum(header[:24], (0, 0))
    if sums != struct.unpack(">II", header[24:32]):
        raise SnapshotError("wal_header_checksum_mismatch")
    with path.open("rb") as stream:
        stream.seek(32)
        while frame := stream.read(24 + page_size):
            if frame[8:16] != header[16:24]:
                # SQLite reuses a WAL without truncating it. Older-checkpoint
                # frames after the current prefix are normal, not corruption.
                # https://www.sqlite.org/fileformat.html#wal_reset
                age = (struct.unpack(">I", header[16:20])[0] - struct.unpack(">I", frame[8:12])[0]) & 0xFFFFFFFF
                if not 0 < age < 0x80000000 or checksum(frame[:8] + frame[24:], sums) == struct.unpack(">II", frame[16:24]):
                    raise SnapshotError("wal_frame_salt_mismatch")
                result["obsolete_tail_frames"] += 1
                continue
            if result["obsolete_tail_frames"]:
                raise SnapshotError("wal_current_frame_after_obsolete_tail")
            if struct.unpack(">I", frame[:4])[0] == 0:
                raise SnapshotError("invalid_wal_page_number")
            sums = checksum(frame[:8] + frame[24:], sums)
            if sums != struct.unpack(">II", frame[16:24]):
                raise SnapshotError("wal_frame_checksum_mismatch")
            result["valid_frames"] += 1
            if struct.unpack(">I", frame[4:8])[0]:
                result["committed_frames"] = result["valid_frames"]
    return result


def _backup(source: Path, destination: Path) -> None:
    started = time.monotonic()

    def progress(status: int, remaining: int, total: int) -> None:
        if time.monotonic() - started > 120:
            raise SnapshotError("snapshot_backup_timeout")

    try:
        with closing(connect_readonly(source)) as src, closing(sqlite3.connect(destination)) as dst:
            src.backup(dst, pages=256, progress=progress, sleep=0.05)
            # The completed transport artifact has no external WAL dependency.
            dst.execute("PRAGMA journal_mode=DELETE")
    except sqlite3.Error:
        raise SnapshotError("snapshot_backup_failed") from None


def _stage_zip(source: Path, stage: Path) -> dict[str, Any]:
    before = file_fingerprint(source)
    with ZipFile(source) as archive:
        candidates = [item for item in archive.infolist() if PurePosixPath(item.filename).name == "data.sqlite"]
        if len(candidates) != 1:
            raise SnapshotError("archive_requires_one_sqlite")
        db_name = candidates[0].filename
        db_member = PurePosixPath(db_name)
        if db_member.is_absolute() or ".." in db_member.parts or "\\" in db_name or ":" in db_name:
            raise SnapshotError("unsafe_archive_member")
        prefix = str(PurePosixPath(db_name).parent)
        prefix = "" if prefix == "." else prefix + "/"
        components: dict[str, Any] = {}
        for name in MEMBERS:
            matches = [item for item in archive.infolist() if item.filename == prefix + name]
            if not matches:
                continue
            item = matches[0]
            member = PurePosixPath(item.filename)
            if len(matches) != 1 or member.is_absolute() or ".." in member.parts or "\\" in item.filename or ":" in item.filename:
                raise SnapshotError("unsafe_archive_member")
            if item.file_size > MAX_SOURCE_BYTES or item.is_dir() or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise SnapshotError("invalid_archive_member")
            target = stage / name  # Fixed allowlist basename, never user member paths.
            with archive.open(item) as src, target.open("xb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)
            components[name] = file_fingerprint(target)
    if file_fingerprint(source) != before:
        raise SnapshotError("source_changed_during_capture")
    return {"kind": "zip", **before, "components": components}


def _stage_directory(source: Path, stage: Path) -> dict[str, Any]:
    paths = {name: source / name for name in MEMBERS if (source / name).exists()}
    if "data.sqlite" not in paths:
        raise SnapshotError("sqlite_source_missing")
    for path in paths.values():
        if path.is_symlink() or not path.is_file() or path.resolve().parent != source.resolve():
            raise SnapshotError("unsafe_source_member")
        if path.stat().st_size > MAX_SOURCE_BYTES:
            raise SnapshotError("source_member_too_large")
    before = {name: file_fingerprint(path) for name, path in paths.items()}
    for name, path in paths.items():
        shutil.copyfile(path, stage / name)
    after = {name: file_fingerprint(path) for name, path in paths.items()}
    copied = {name: file_fingerprint(stage / name) for name in paths}
    after_names = {name for name in MEMBERS if (source / name).exists()}
    if before != after or before != copied or set(paths) != after_names:
        raise SnapshotError("source_changed_during_capture")
    return {"kind": "frozen_directory", "components": before}


@dataclass
class CapturedSnapshot:
    path: Path
    manifest: dict[str, Any]
    state: dict[str, Any]
    images: list[dict[str, Any]]
    fallback_state: dict[str, Any] | None


def capture_snapshot(source: Path, output_dir: Path, *, live: bool = False,
                     wal_checkpoint_confirmed: bool = False) -> CapturedSnapshot:
    source = source.expanduser().resolve()
    output_dir = output_dir.expanduser().resolve()
    if output_dir == source or output_dir in source.parents or (source.is_dir() and source in output_dir.parents):
        raise SnapshotError("snapshot_output_overlaps_source")
    if output_dir.exists():
        raise SnapshotError("snapshot_output_already_exists")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="three-d-capture-", dir=output_dir.parent) as scratch_name:
        scratch = Path(scratch_name)
        stage = scratch / "source"
        stage.mkdir()
        bundle = scratch / "bundle"
        bundle.mkdir()
        fallback = None
        if live:
            db_path = source / "data.sqlite" if source.is_dir() else source
            if not db_path.is_file() or db_path.is_symlink():
                raise SnapshotError("sqlite_source_missing")
            provenance = {"kind": "live_sqlite", "components": {}}
            # A live connection sees a consistent committed DB+WAL transaction.
            _backup(db_path, bundle / "snapshot.sqlite")
        else:
            if source.is_dir():
                provenance = _stage_directory(source, stage)
                db_path = stage / "data.sqlite"
            elif source.suffix.lower() == ".zip":
                provenance = _stage_zip(source, stage)
                db_path = stage / "data.sqlite"
            else:
                # Support a captured standalone DB and its correctly named sidecars.
                if not source.is_file() or source.is_symlink():
                    raise SnapshotError("sqlite_source_missing")
                before = file_fingerprint(source)
                provenance = {"kind": "sqlite_file", "components": {"data.sqlite": before}}
                shutil.copyfile(source, stage / "data.sqlite")
                for suffix in ("-wal", "-shm"):
                    companion = Path(str(source) + suffix)
                    if companion.exists():
                        if companion.is_symlink() or not companion.is_file():
                            raise SnapshotError("unsafe_source_member")
                        provenance["components"]["data.sqlite" + suffix] = file_fingerprint(companion)
                        shutil.copyfile(companion, stage / ("data.sqlite" + suffix))
                if before != file_fingerprint(source):
                    raise SnapshotError("source_changed_during_capture")
                for name, fingerprint in provenance["components"].items():
                    if fingerprint != file_fingerprint(stage / name):
                        raise SnapshotError("source_changed_during_capture")
                    original = source if name == "data.sqlite" else Path(str(source) + name.removeprefix("data.sqlite"))
                    if fingerprint != file_fingerprint(original):
                        raise SnapshotError("source_changed_during_capture")
                db_path = stage / "data.sqlite"
            wal = stage / "data.sqlite-wal"
            if _wal_required(db_path) and (not wal.exists() or wal.stat().st_size == 0) and not wal_checkpoint_confirmed:
                raise SnapshotError("wal_missing_requires_checkpoint_confirmation")
            provenance["wal_validation"] = _check_wal(wal)
            _backup(db_path, bundle / "snapshot.sqlite")
            if (stage / "data.json").is_file():
                # This is comparison evidence only, never a substitute for SQLite.
                try:
                    fallback = read_json(stage / "data.json")
                except SnapshotError:
                    provenance["json_comparison_error"] = "invalid_compatibility_json"
        state, images, checks = inspect_snapshot(bundle / "snapshot.sqlite")
        manifest = {
            "schema_version": 1, "tool_version": VERSION,
            "factory_id": FACTORY_ID, "site_code": SITE_CODE,
            "captured_at_utc": datetime.now(UTC).isoformat(),
            "source": provenance,
            "snapshot": {"file": "snapshot.sqlite", **file_fingerprint(bundle / "snapshot.sqlite")},
            "checks": checks,
            "wal_checkpoint_confirmed": wal_checkpoint_confirmed,
            "counts": {
                "materials": len(state["materials"]), "products": len(state["products"]),
                "business_date_keys": len(state["records"]),
                "production_records": sum(len(day["items"]) for day in state["records"].values()),
                "product_images": len(images),
                "image_total_bytes": sum(image["size_bytes"] for image in images),
                "invalid_images": sum(not image["valid"] for image in images),
            },
            "metadata_policy": "allowlist_no_config_no_raw_payload",
        }
        # Manifest has only allowlisted metadata; no raw app_state/config/payload.
        (bundle / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        bundle.rename(output_dir)
        return CapturedSnapshot(output_dir / "snapshot.sqlite", manifest, state, images, fallback)
