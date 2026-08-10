"""Idempotently create factory-scoped injection machine masters from normalized JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.core.time import business_now
from app.db import SessionLocal
from app.models.injection_scheduling import InjectionSchedulingMachine
from app.schemas.injection_scheduling import InjectionSchedulingMachineCreate
from app.services.injection_scheduling import _apply_machine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--factory-id", default="huaxing")
    parser.add_argument("--actor", default="machine-master-import")
    parser.add_argument("--actor-name", default="机台主数据导入")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    document = json.loads(args.input.read_text(encoding="utf-8"))
    source_rows = document.get("rows")
    if not isinstance(source_rows, list):
        raise TypeError("输入文件缺少 rows 数组")

    payloads: list[InjectionSchedulingMachineCreate] = []
    for row in source_rows:
        if row.get("factory_id") != args.factory_id:
            raise ValueError(
                f"输入厂区 {row.get('factory_id')!r} 与 --factory-id {args.factory_id!r} 不一致"
            )
        payloads.append(
            InjectionSchedulingMachineCreate.model_validate(
                {**row, "factory_id": args.factory_id, "expected_revision": 0}
            )
        )

    machine_codes = [payload.machine_code for payload in payloads]
    if len(machine_codes) != len(set(machine_codes)):
        raise ValueError("输入中存在重复机台编号")

    created = 0
    skipped = 0
    now = business_now().isoformat(timespec="seconds")
    with SessionLocal() as db:
        existing_codes = set(
            db.scalars(
                select(InjectionSchedulingMachine.machine_code).where(
                    InjectionSchedulingMachine.factory_id == args.factory_id,
                    InjectionSchedulingMachine.machine_code.in_(machine_codes),
                )
            ).all()
        )
        for payload in payloads:
            if payload.machine_code in existing_codes:
                skipped += 1
                continue
            record = InjectionSchedulingMachine(
                id=f"ismachine-{uuid4().hex}",
                factory_id=args.factory_id,
                machine_code=payload.machine_code,
                created_by=args.actor,
                created_by_name=args.actor_name,
                updated_by=args.actor,
                updated_by_name=args.actor_name,
                created_at=now,
                updated_at=now,
            )
            _apply_machine(record, payload)
            db.add(record)
            created += 1
        db.commit()

    print(
        json.dumps(
            {
                "factory_id": args.factory_id,
                "source_rows": len(payloads),
                "created": created,
                "skipped_existing": skipped,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
