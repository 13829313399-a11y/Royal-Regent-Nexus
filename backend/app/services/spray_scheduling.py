"""Small deterministic finite-capacity suggestion pass; leaves execution intact."""
from datetime import timedelta
from sqlalchemy import select
from fastapi import HTTPException
from app.models import spray_production as m
from app.services import spray_production as s


def suggest(db, factory, actor, p):
    earliest = s.instant(p.get("start_at"))
    candidates = list(db.execute(select(m.SprayBatch, m.SprayOrderLine, m.SprayOrder).join(m.SprayOrderLine, m.SprayBatch.line_id == m.SprayOrderLine.id).join(m.SprayOrder, m.SprayOrderLine.order_id == m.SprayOrder.id).where(m.SprayBatch.factory_id == factory, m.SprayOrder.status == "active").order_by(m.SprayOrder.priority.desc(), m.SprayOrder.due_date, m.SprayBatch.created_at).limit(200)))
    resources = list(db.scalars(select(m.SprayResource).where(m.SprayResource.factory_id == factory).order_by(m.SprayResource.name)))
    changes, skipped = [], []
    for batch, line, _ in candidates:
        for state, qty in s.stock(db, factory, batch.id).items():
            if qty <= 0 or not state.startswith(("ready:", "rework:")):
                continue
            step = s.find(db, m.SprayStep, factory, state.split(":")[1])
            if not line.prep_ready_at:
                skipped.append({"batch_id": batch.id, "reason": "备产未完成"}); continue
            accepted = False
            for resource in resources:
                if resource.capability != step.capability or not resource.machine_rate or not resource.person_minutes:
                    continue
                duration = timedelta(hours=float(s.D(s.throughput(qty, resource.machine_rate, resource.person_minutes, resource.workers, resource.setup_hours)["hours"])))
                occupied = [(s.instant(t.start_at), s.instant(t.end_at)) for t in db.scalars(select(m.SprayTask).where(m.SprayTask.resource_id == resource.id, m.SprayTask.status.in_(["planned", "running", "paused"])))]
                occupied += [(s.instant(t["start_at"]), s.instant(t["end_at"])) for t in changes if t["resource_id"] == resource.id]
                for window in resource.calendar:
                    start = max(earliest, s.instant(line.prep_ready_at), s.instant(window["start"]))
                    for a, b in sorted(occupied):
                        if start < b and start + duration > a:
                            start = b
                    if start + duration > s.instant(window["end"]):
                        continue
                    candidate = {"batch_id": batch.id, "step_id": step.id, "resource_id": resource.id, "quantity": str(qty), "workers": resource.workers, "start_at": start.isoformat(), "rework": state.startswith("rework:")}
                    try:
                        changes = s.plan_changes(db, factory, changes + [candidate])
                    except HTTPException:
                        continue
                    accepted = True
                    break
                if accepted: break
            if not accepted:
                skipped.append({"batch_id": batch.id, "reason": "缺节拍、等待未结束或完整班次不足；可拆批手工安排"})
    if not changes:
        s.fail("没有满足实际库存、备产、能力、节拍和班次条件的可排批次")
    result = s.preview_plan(db, factory, actor, {"changes": changes})
    result["skipped"] = skipped
    result["strategy"] = "优先级 → 交期 → 来料；保留现有任务，逐一寻找可用资源"
    return result
