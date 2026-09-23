from math import ceil
from app.models import uv_operations as m
from . import common as c


def preview(db, body, *, lock=False):
    machines = {key: c.get(db, m.UvOpsMachine, key, lock=lock) for key in sorted({x.machine_id for x in body.blocks})}
    tasks = {key: c.get(db, m.UvOpsTask, key, lock=lock) for key in sorted({x.task_id for x in body.blocks})}
    fixtures = {key: c.get(db, m.UvOpsFixture, key, lock=lock) for key in sorted({x.process_snapshot["fixture_id"] for x in tasks.values()})}
    c.require(len(tasks) == len(body.blocks), "duplicate_task", "一次排程不能重复分配同一任务", 422)
    existing = list(db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.status != "cancelled")))
    task_lookup = {x.id: x for x in db.scalars(c.query(m.UvOpsTask))}
    conflicts, blocks = [], []
    for item in body.blocks:
        task, machine = tasks[item.task_id], machines[item.machine_id]
        fixture = fixtures[task.process_snapshot["fixture_id"]]
        old = next((x for x in existing if x.task_id == task.id), None)
        reasons = []
        if task.version != item.task_version or machine.version != item.machine_version or (old.version if old else 0) != item.block_version:
            reasons.append("数据版本已变化")
        if task.status in {"in_progress", "completed", "cancelled"} or (old and old.fixed):
            reasons.append("固定或执行中的任务不能重排")
        if machine.maintenance:
            reasons.append("机台维护中")
        if not machine.capability_evidence or machine.width_mm is None or machine.height_mm is None or machine.ink_family == "unknown":
            reasons.append("机台能力尚未确认")
        elif fixture.width_mm > machine.width_mm or fixture.height_mm > machine.height_mm or machine.ink_family != task.process_snapshot["ink_family"]:
            reasons.append("尺寸或墨材不兼容")
        file = c.get(db, m.UvOpsFileVersion, task.file_version_id)
        if not file.confirmed_at or not file.first_article_evidence:
            reasons.append("文件与首件未准备完成")
        start, end = c.ts(item.start_at), c.ts(item.end_at)
        cycle = task.process_snapshot.get("cycle_seconds")
        duration = None if cycle is None else float(cycle) * ceil(task.quantity / task.process_snapshot["pieces_per_board"]) * task.process_snapshot["passes"]
        if end <= start:
            reasons.append("结束时间必须晚于开始时间")
        elif duration is None:
            reasons.append("工艺节拍未知，需先确认工艺版本")
        elif (item.end_at-item.start_at).total_seconds() < duration:
            reasons.append("时间窗口短于已确认工艺所需时间")
        for occupied in existing:
            if occupied.task_id in tasks or occupied.start_at >= end or occupied.end_at <= start:
                continue
            other = task_lookup[occupied.task_id]
            if occupied.machine_id == machine.id or other.process_snapshot["fixture_id"] == fixture.id:
                reasons.append("机台或共享治具与现有任务冲突")
        for other in blocks:
            if other["start_at"] < end and other["end_at"] > start and (other["machine_id"] == machine.id or tasks[other["task_id"]].process_snapshot["fixture_id"] == fixture.id):
                reasons.append("本次排程内机台或治具重复占用")
        if reasons:
            conflicts.append(dict(task_id=task.id, reasons=list(dict.fromkeys(reasons))))
        blocks.append(dict(task_id=task.id, machine_id=machine.id, start_at=start, end_at=end, fixed=item.fixed, estimated_seconds=duration, block_id=old.id if old else None))
    return dict(blocks=blocks, conflicts=conflicts, can_commit=not conflicts, rationale="按确认节拍、机台尺寸、墨材与治具排他约束核验；仅改变计划，不发送设备命令")


def commit(db, user, body):
    result = preview(db, body, lock=True)
    c.require(result["can_commit"], "schedule_conflict", "；".join(reason for x in result["conflicts"] for reason in x["reasons"]))
    saved = []
    for block in result["blocks"]:
        values = {key: block[key] for key in ("task_id", "machine_id", "start_at", "end_at", "fixed")}
        if block["block_id"]:
            row = c.get(db, m.UvOpsScheduleBlock, block["block_id"], lock=True)
            for key, value in values.items():
                setattr(row, key, value)
            c.touch(row)
        else:
            row = c.add(db, m.UvOpsScheduleBlock, user, **values)
        task = c.get(db, m.UvOpsTask, block["task_id"])
        task.status = "planned"
        c.touch(task)
        saved.append(c.record(row))
    return dict(blocks=saved)


def recommendations(db, task):
    results = []
    process = task.process_snapshot
    fixture = c.get(db, m.UvOpsFixture, process["fixture_id"])
    for machine in db.scalars(c.query(m.UvOpsMachine)):
        compatible = bool(machine.capability_evidence and not machine.maintenance and machine.width_mm and machine.height_mm and machine.width_mm >= fixture.width_mm and machine.height_mm >= fixture.height_mm and machine.ink_family == process["ink_family"])
        load = list(db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.machine_id == machine.id, m.UvOpsScheduleBlock.status == "planned")))
        results.append(dict(machine_id=machine.id, compatible=compatible, planned_tasks=len(load), earliest_after=max((x.end_at for x in load), default=None), reason="能力匹配，按已有排程负荷排序" if compatible else "能力未知、维护或尺寸/墨材不兼容"))
    return sorted(results, key=lambda x: (not x["compatible"], x["planned_tasks"], x["machine_id"]))
