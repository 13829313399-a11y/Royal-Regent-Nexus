"""Review persisted queue heads, then start only the explicitly reviewed batches."""

import hashlib
import json
from collections import Counter

from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import (
    CalendarEvent,
    Demand,
    FactorySettings,
    Machine,
    MoldAsset,
    Run,
    RunDemand,
)

from .calculations import now
from .common import record, scoped
from .planning import recalculate
from .production import action, validate_execution


def preview(db, factory, items, instant=None):
    instant = instant or now()
    settings = db.get(FactorySettings, factory)
    events = [
        record(event)
        for event in db.scalars(
            select(CalendarEvent)
            .where(CalendarEvent.factory_id == factory)
            .order_by(CalendarEvent.id)
        )
    ]
    rows, facts = [], []
    for item in items:
        row = {
            "machine_id": item.machine_id,
            "run_id": item.run_id,
            "can_start": False,
            "reason": "",
            "machine_code": "",
            "mold_code": "",
            "order_no": "",
            "remaining_shots": None,
        }
        fact = {}
        try:
            machine = scoped(db, Machine, item.machine_id, factory)
            row["machine_code"] = machine.code
            run = scoped(db, Run, item.run_id, factory)
            head = db.scalar(
                select(Run)
                .where(
                    Run.factory_id == factory,
                    Run.machine_id == machine.id,
                    Run.status == "PLANNED",
                )
                .order_by(Run.sequence, Run.id)
                .limit(1)
            )
            if run.machine_id != machine.id or not head or head.id != run.id:
                raise HTTPException(409, "下一批已变化，请关闭窗口后重新勾选机台")
            asset = scoped(db, MoldAsset, run.mold_asset_id, factory)
            links = list(
                db.scalars(
                    select(RunDemand)
                    .where(RunDemand.run_id == run.id)
                    .order_by(RunDemand.id)
                )
            )
            demands = [
                record(scoped(db, Demand, link.demand_id, factory)) for link in links
            ]
            row.update(
                mold_code=run.snapshot.get("mold_code", ""),
                order_no=" / ".join(
                    dict.fromkeys(d.get("order_no") or "未填订单" for d in demands)
                ),
                remaining_shots=max(0, run.planned_physical_shots - run.physical_shots),
                mold_asset_id=asset.id,
            )
            fact = {
                "machine": record(machine),
                "run": record(run),
                "asset": record(asset),
                "links": [record(link) for link in links],
                "demands": demands,
            }
            validate_execution(db, factory, run, machine, instant)
            row["can_start"] = True
        except HTTPException as exc:
            row["reason"] = str(exc.detail)
        rows.append(row)
        facts.append(fact)
    # Do not choose an arbitrary winner when two selected heads need one asset.
    assets = Counter(row.get("mold_asset_id") for row in rows if row["can_start"])
    for row, fact in zip(rows, facts, strict=True):
        if row["can_start"] and assets[row["mold_asset_id"]] > 1:
            row.update(
                can_start=False,
                reason="所选机台共用同一套实物模具，请保留其中一台后重新核对",
            )
        row["review_token"] = hashlib.sha256(
            json.dumps(
                {
                    "factory": factory,
                    "row": row,
                    "facts": fact,
                    "parameters": settings.parameters,
                    "events": events,
                },
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            ).encode()
        ).hexdigest()
    return {
        "revision": settings.revision,
        "items": rows,
        "eligible_count": sum(row["can_start"] for row in rows),
        "as_of": instant.isoformat(),
    }


def start(db, payload, actor):
    if not payload.confirm_actual_start:
        raise HTTPException(422, "请先确认所选批次现在实际开工")
    if payload.base_revision != payload.expected_revision:
        raise HTTPException(409, "核对版本不一致，请重新核对")
    instant = now()
    reviewed = preview(db, payload.factory_id, payload.items, instant)
    results, before = [], {}
    # All eligibility is reviewed before any mutation, while begin_write holds
    # the shared resource lock. Each actual start still revalidates execution.
    for item, row in zip(payload.items, reviewed["items"], strict=True):
        result = {**row, "success": False}
        if not row["can_start"]:
            results.append(result)
            continue
        if row["review_token"] != item.review_token:
            result["reason"] = "设备、模具或需求资料已变化，请重新核对后再开工"
            results.append(result)
            continue
        try:
            with db.begin_nested():
                started = action(
                    db,
                    payload.factory_id,
                    item.run_id,
                    "start",
                    actor,
                    "看板批量开工",
                    instant=instant,
                    recalculate_after=False,
                )
            before[item.run_id] = started["before"]
            result.update(success=True, reason="已开工")
        except HTTPException as exc:
            result["reason"] = str(exc.detail)
        results.append(result)
    count = sum(row["success"] for row in results)
    calculation = recalculate(db, payload.factory_id, actor, instant) if count else {}
    return {
        **calculation,
        "bulk_start": True,
        "started_count": count,
        "failed_count": len(results) - count,
        "results": results,
        "started_at": instant.isoformat(),
        "before": before,
    }
