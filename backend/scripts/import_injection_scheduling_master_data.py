from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db import SessionLocal
from app.services.injection_scheduling_master_consolidation import (
    consolidate_master_data_workbook,
    stage_consolidated_master_data,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="只读整理单价/机安工作表，并可幂等写入受控主数据提案。"
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--factory", default="huaxing")
    parser.add_argument(
        "--stage",
        action="store_true",
        help="写入三类 PROPOSED 提案；不绕过独立批准，也不激活价格。",
    )
    parser.add_argument("--proposed-by", default="system:controlled-excel-import")
    parser.add_argument("--proposed-by-name", default="受控 Excel 整理任务")
    parser.add_argument(
        "--reason",
        default="按机安优先、单价安数回退规则整理华兴旧表，保留字段证据并提交独立复核",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    content = args.source.read_bytes()
    consolidated = consolidate_master_data_workbook(
        content,
        args.source.name,
        factory_id=args.factory,
    )
    result: dict[str, object] = {
        "source_file_name": consolidated["source_file_name"],
        "source_file_hash": consolidated["source_file_hash"],
        "consolidation_digest": consolidated["consolidation_digest"],
        "summary": consolidated["summary"],
        "review_samples": [
            {
                "mold_key": item["mold_key"],
                "display_mold_no": item["display_mold_no"],
                "code": item["code"],
                "source_priority": item["source_priority"],
                "conflicts": item["conflicts"],
                "source_rows": [
                    {
                        "sheet_name": source["sheet_name"],
                        "source_row": source["source_row"],
                    }
                    for source in item["source_rows"]
                ],
            }
            for item in consolidated["review_entries"][:20]
        ],
        "staged": False,
    }
    if args.stage:
        with SessionLocal() as db:
            result["database"] = stage_consolidated_master_data(
                db,
                consolidated=consolidated,
                proposed_by=args.proposed_by,
                proposed_by_name=args.proposed_by_name,
                reason=args.reason,
            )
        result["staged"] = True
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
