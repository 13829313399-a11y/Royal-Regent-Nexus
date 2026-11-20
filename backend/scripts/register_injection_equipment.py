"""Inspect a fixed source profile, or explicitly register its equipment in local SQLite."""

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.models.injection_scheduling import FactorySettings
from app.services.injection_scheduling.machine_register import (
    PROFILES,
    apply_register,
    inspect_register,
)
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--database", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--confirm-sha256")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    report = inspect_register(args.source.read_bytes(), args.profile)
    if args.apply:
        if args.confirm_sha256 != report["sha256"]:
            parser.error("请先核对报告，再通过 --confirm-sha256 指定来源哈希")
        if not args.database or not args.database.is_file() or not args.backup:
            parser.error("应用前必须指定现有本地数据库及新的备份文件路径")
        database, backup = args.database.resolve(), args.backup.resolve()
        if backup == database or backup.exists():
            parser.error("备份必须是尚不存在的新文件，不能覆盖数据库或旧备份")
        backup.parent.mkdir(parents=True, exist_ok=True)
        with (
            closing(
                sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)
            ) as source,
            closing(sqlite3.connect(backup)) as target,
        ):
            source.backup(target)
            if target.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("备份完整性检查失败")
        engine = create_engine("sqlite:///" + database.as_posix())

        @event.listens_for(engine, "connect")
        def enforce_foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        with Session(engine) as db:
            setting = db.get(FactorySettings, report["factory_id"])
            if setting is None:
                raise RuntimeError("目标数据库尚未初始化注塑排产模块")
            payload = {
                "factory_id": report["factory_id"],
                "base_revision": setting.revision,
                "client_operation_id": uuid4().hex,
                "source_sha256": report["sha256"],
            }
            report["applied"] = apply_register(
                db, report, payload, "local-maintenance:user-authorized"
            )
        engine.dispose()
        report["backup"] = str(backup)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "factory": report["factory_id"],
                "machines": len(report["machines"]),
                "sha256": report["sha256"],
                "conflicts": report["assignment_conflicts"],
                "unassigned_rows": report["unassigned_source_rows"],
                "created": report.get("applied", {}).get("created_count"),
                "report": str(args.report),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
