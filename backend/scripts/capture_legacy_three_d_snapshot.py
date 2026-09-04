"""Capture a SQLite backup plus non-secret manifest, without loading Nexus DB."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from legacy_sqlite_reader import SnapshotError, capture_snapshot
from scan_three_d_secrets import SafeParser


def main() -> int:
    parser = SafeParser(description="只读封存旧3D SQLite/WAL一致性快照")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-dir", type=Path)
    source.add_argument("--source-zip", type=Path)
    source.add_argument("--source", type=Path, help="单独的 SQLite 路径")
    parser.add_argument("--output-dir", type=Path, required=True, help="必须是源目录之外的新目录")
    parser.add_argument("--live", action="store_true", help="通过在线backup捕获正在运行的SQLite，不复制活跃DB/WAL")
    parser.add_argument("--wal-checkpoint-confirmed", action="store_true", help="仅在已确认停写且成功checkpoint时允许缺失WAL")
    try:
        args = parser.parse_args()
        if args.live and args.source_zip:
            raise SnapshotError("live_mode_requires_sqlite")
        result = capture_snapshot(args.source_dir or args.source_zip or args.source, args.output_dir,
                                  live=args.live, wal_checkpoint_confirmed=args.wal_checkpoint_confirmed)
        print(json.dumps(result.manifest, ensure_ascii=False, indent=2))
        return 0
    except Exception:
        # Never echo source paths, sqlite errors, JSON snippets, or credentials.
        exc = sys.exc_info()[1]
        print(json.dumps({"status": "failed", "error_code": exc.code if isinstance(exc, SnapshotError) else "capture_failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
