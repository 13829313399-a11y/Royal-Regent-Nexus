"""Offline backup/restore rehearsal. Never overwrites an existing destination.

SQLite source and assets must be quiesced. PostgreSQL uses a supplied pg_dump
archive from the same stopped-writer window, verified by pg_restore --list.
The manifest binds database, migration revision and every asset to one batch.
"""

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def digest(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inventory(root):
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise ValueError("Assets must be a real directory")
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or path.is_junction():
            raise ValueError("Asset links are not supported")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "sha256": digest(path),
                "size": path.stat().st_size,
            }
    return result


def sqlite_check(path):
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity failed")
        if db.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError("Database foreign key check failed")
        revision = db.execute("SELECT version_num FROM alembic_version").fetchone()
        if not revision:
            raise ValueError("Migration revision missing")
        return revision[0]


def verify(bundle):
    bundle = Path(bundle).resolve(strict=True)
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != "rr-three-d-backup-v1":
        raise ValueError("Unknown backup format")
    if not manifest.get("writers_stopped"):
        raise ValueError("Backup lacks stopped-writer assertion")
    if manifest["database_type"] not in {"sqlite", "postgresql"}:
        raise ValueError("Unknown database type")
    database = bundle / (
        "database.sqlite" if manifest["database_type"] == "sqlite" else "database.dump"
    )
    if database.is_symlink() or digest(database) != manifest["database_sha256"]:
        raise ValueError("Database hash mismatch")
    if inventory(bundle / "assets") != manifest["assets"]:
        raise ValueError("Asset manifest mismatch")
    if (
        manifest["database_type"] == "sqlite"
        and sqlite_check(database) != manifest["revision"]
    ):
        raise ValueError("Revision mismatch")
    return manifest


def backup(
    database,
    assets,
    output,
    *,
    writers_stopped=False,
    postgres=False,
    revision=None,
    pg_restore=None,
):
    if not writers_stopped:
        raise ValueError("Stop ALL writers and asset uploads before backup")
    database, assets, output = (
        Path(database).resolve(strict=True),
        Path(assets).resolve(strict=True),
        Path(output).resolve(),
    )
    if not assets.is_dir() or output == assets or assets in output.parents:
        raise ValueError("Backup destination must be outside assets")
    output.mkdir(parents=True, exist_ok=False)
    before = inventory(assets)
    target = output / ("database.dump" if postgres else "database.sqlite")
    if postgres:
        if not revision or not pg_restore:
            raise ValueError(
                "PostgreSQL archive requires revision and pg_restore executable"
            )
        subprocess.run(
            [str(pg_restore), "--list", str(database)], check=True, capture_output=True
        )
        shutil.copyfile(database, target)
    else:
        # Hold the writer lock until both data and assets are copied. A separate
        # read connection is needed for SQLite backup while BEGIN IMMEDIATE is held.
        with sqlite3.connect(
            database.as_uri() + "?mode=rw", uri=True, timeout=5
        ) as lock:
            lock.execute("BEGIN IMMEDIATE")
            with (
                sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source,
                sqlite3.connect(target) as destination,
            ):
                source.backup(destination)
            shutil.copytree(assets, output / "assets")
            if before != inventory(assets):
                raise ValueError("Assets changed during backup; bundle incomplete")
        revision = sqlite_check(target)
    if postgres:
        shutil.copytree(assets, output / "assets")
    if before != inventory(assets) or before != inventory(output / "assets"):
        raise ValueError("Assets changed during backup")
    manifest = {
        "format": "rr-three-d-backup-v1",
        "batch_id": uuid4().hex,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "writers_stopped": True,
        "database_type": "postgresql" if postgres else "sqlite",
        "revision": revision,
        "database_sha256": digest(target),
        "assets": before,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    verify(output)
    return manifest


def restore(bundle, output):
    manifest = verify(bundle)
    output = Path(output).resolve()
    source = Path(bundle).resolve()
    if output == source or source in output.parents:
        raise ValueError("Restore must be outside backup")
    # Existing destination (even empty) is always rejected. Rehearsal only.
    output.mkdir(parents=True, exist_ok=False)
    name = (
        "database.sqlite" if manifest["database_type"] == "sqlite" else "database.dump"
    )
    shutil.copyfile(source / name, output / name)
    shutil.copytree(source / "assets", output / "assets")
    if (
        digest(output / name) != manifest["database_sha256"]
        or inventory(output / "assets") != manifest["assets"]
    ):
        raise ValueError("Restore verification failed")
    if manifest["database_type"] == "sqlite":
        sqlite_check(output / name)
    (output / "restore-evidence.json").write_text(
        json.dumps(
            {
                "batch_id": manifest["batch_id"],
                "database_sha256": manifest["database_sha256"],
                "assets_verified": len(manifest["assets"]),
                "status": "restored_sqlite_verified"
                if manifest["database_type"] == "sqlite"
                else "archive_verified_requires_isolated_pg_restore",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    b = sub.add_parser("backup")
    b.add_argument("--database", required=True)
    b.add_argument("--assets", required=True)
    b.add_argument("--output", required=True)
    b.add_argument("--writers-stopped", action="store_true")
    b.add_argument("--postgres", action="store_true")
    b.add_argument("--revision")
    b.add_argument("--pg-restore")
    v = sub.add_parser("verify")
    v.add_argument("--bundle", required=True)
    r = sub.add_parser("restore")
    r.add_argument("--bundle", required=True)
    r.add_argument("--output", required=True)
    args = vars(parser.parse_args())
    command = args.pop("command")
    result = {"backup": backup, "verify": verify, "restore": restore}[command](**args)
    print(
        json.dumps(
            {
                "status": "verified",
                "batch_id": result["batch_id"],
                "revision": result["revision"],
                "asset_count": len(result["assets"]),
            }
        )
    )


if __name__ == "__main__":
    main()
