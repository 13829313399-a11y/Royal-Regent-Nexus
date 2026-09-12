"""Atomic workshop operations, using a per-factory write gate on both databases.

The gate is a database UPDATE (not a Python mutex or SELECT FOR UPDATE emulation).
It serializes inventory and resource decisions, including concurrent empty ranges.
Helpers never commit. The API commits the event and its idempotency receipt together.
"""
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from hashlib import sha256
import json
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select, update, func
from sqlalchemy.orm import Session
from app.models import spray_production as m

FACTORIES = ("huaxing", "huakang-a", "huakang-b", "huadeng")
CAPABILITIES = ("manual", "automatic", "pad", "uv")
D = Decimal


def fail(message, code=422):
    raise HTTPException(code, message)


def number(value, *, positive=False, signed=False):
    try:
        result = D(str(value))
    except (InvalidOperation, TypeError, ValueError):
        fail("数量或金额必须是有效十进制数")
    if not result.is_finite() or abs(result) > D("999999999999") or (not signed and result < 0) or (positive and result <= 0):
        fail("数量或金额超出允许范围")
    if result.as_tuple().exponent < -6:
        fail("输入最多保留六位小数")
    return result


def text(value, name="字段", maximum=255):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        fail(f"{name}不能为空且不能超过 {maximum} 字符")
    return value.strip()


def day(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        fail("业务日期格式应为 YYYY-MM-DD")


def instant(value):
    try:
        result = datetime.fromisoformat(str(value))
        if result.tzinfo is None:
            fail("排程时间必须包含时区")
        return result.astimezone(UTC)
    except ValueError:
        fail("时间格式无效")


def rows(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 200 or not all(isinstance(v, dict) for v in value):
        fail("请提供 1–200 行有效明细")
    return value


def headcount(value):
    result = number(value, positive=True)
    if result != result.to_integral_value() or result > 500:
        fail("投入人数必须是 1–500 的整数")
    return int(result)


def serial(obj, *, exclude=()):
    return {c.name: str(v) if isinstance(v, D) else v for c in obj.__table__.columns
            if c.name not in exclude for v in [getattr(obj, c.name)]}


def find(db, cls, factory, ident):
    item = db.scalar(select(cls).where(cls.id == ident, cls.factory_id == factory))
    if item is None:
        fail("当前厂区未找到该记录", 404)
    return item


def add(db, cls, factory, actor, **values):
    item = cls(id=uuid4().hex, factory_id=factory, created_by=actor, **values)
    db.add(item)
    db.flush()
    return item


def revision(db, factory):
    value = db.get(m.SprayFactory, factory)
    if value is None:
        fail("喷油数据库尚未迁移或初始化", 503)
    return value.revision


def execute(db, factory, actor, action, payload):
    if factory not in FACTORIES:
        fail("请选择华兴、华康 A、华康 B 或华登执行厂区")
    operation_id = text(payload.get("operation_id"), "操作标识", 128)
    digest = sha256(json.dumps({"action": action, "payload": payload}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    previous = db.scalar(select(m.SprayOperation).where(m.SprayOperation.factory_id == factory, m.SprayOperation.operation_id == operation_id))
    if previous:
        if previous.payload_hash != digest:
            fail("同一操作标识对应不同内容，请检查重复提交", 409)
        return previous.result
    if action == "preference-save":
        result = ACTIONS[action](db, factory, actor, payload)
        result["revision"] = revision(db, factory)
        add(db,m.SprayOperation,factory,actor,operation_id=operation_id,kind=action,payload_hash=digest,result=result)
        return result
    expected = payload.get("base_revision")
    statement = update(m.SprayFactory).where(m.SprayFactory.factory_id == factory)
    if expected is not None:
        statement = statement.where(m.SprayFactory.revision == expected)
    changed = db.execute(statement.values(revision=m.SprayFactory.revision + 1))
    if changed.rowcount != 1:
        fail("资料已变化，请刷新后重新预览；草稿可以保留", 409)
    # A same-ID writer may have committed while this writer waited for the gate.
    previous = db.scalar(select(m.SprayOperation).where(m.SprayOperation.factory_id == factory, m.SprayOperation.operation_id == operation_id))
    if previous:
        if previous.payload_hash != digest:
            fail("操作标识内容冲突", 409)
        db.rollback()
        return previous.result
    result = ACTIONS[action](db, factory, actor, payload)
    result["revision"] = revision(db, factory)
    add(db, m.SprayOperation, factory, actor, operation_id=operation_id, kind=action, payload_hash=digest, result=result)
    return result


def stock(db, factory, batch_id):
    result = {}
    for v in db.scalars(select(m.SprayMovement).where(m.SprayMovement.factory_id == factory, m.SprayMovement.batch_id == batch_id)):
        if v.from_state:
            result[v.from_state] = result.get(v.from_state, D(0)) - v.quantity
        result[v.to_state] = result.get(v.to_state, D(0)) + v.quantity
    return result


def move(db, factory, actor, batch, event, kind, source, target, quantity, reason="", available_at=""):
    if quantity == 0:
        return
    if source and stock(db, factory, batch).get(source, D(0)) < quantity:
        fail(f"批次数量已变化：{source} 可用量不足，请重新核对", 409)
    add(db, m.SprayMovement, factory, actor, batch_id=batch, event_id=event, kind=kind,
        from_state=source, to_state=target, quantity=quantity, reason=reason, available_at=available_at)


def steps(db, factory, line):
    return list(db.scalars(select(m.SprayStep).where(m.SprayStep.factory_id == factory, m.SprayStep.line_id == line).order_by(m.SprayStep.sequence)))


def ready(step):
    return f"ready:{step.id}"


def next_state(db, factory, step):
    next_step = db.scalar(select(m.SprayStep).where(m.SprayStep.factory_id == factory, m.SprayStep.line_id == step.line_id, m.SprayStep.sequence > step.sequence).order_by(m.SprayStep.sequence))
    return ready(next_step) if next_step else "finished"


def create_order(db, factory, actor, p):
    order = add(db, m.SprayOrder, factory, actor, document_no=text(p.get("document_no"), "工单号", 128),
                customer=text(p.get("customer"), "客户", 128), customer_factory_id=p.get("customer_factory_id", ""),
                source_ref=p.get("source_ref", ""), due_date=day(p.get("due_date")),
                expected_material_date=day(p["expected_material_date"]) if p.get("expected_material_date") else "", priority=int(p.get("priority", 0)))
    if order.customer_factory_id and order.customer_factory_id not in FACTORIES:
        fail("委托厂区无效")
    for v in rows(p.get("lines")):
        line = add(db, m.SprayOrderLine, factory, actor, order_id=order.id,
                   product_no=text(v.get("product_no"), "货号", 128), part_name=text(v.get("part_name"), "实体部件", 128),
                   quantity=number(v.get("quantity"), positive=True), unit=v.get("unit", "件"),
                   per_set=number(v["per_set"], positive=True) if v.get("per_set") else None,
                   price=number(v["price"]) if v.get("price") is not None else None,
                   currency=v.get("currency", "HKD"), price_reference=v.get("price_reference", ""))
        if line.unit not in ("件", "套") or line.currency not in ("HKD", "CNY", "USD"):
            fail("请选择明确的数量单位和币种")
        if line.price is not None and not line.price_reference.strip():
            fail("结算价须填写采用依据；未知价格请留空")
        created_steps = []
        for index, s in enumerate(rows(v.get("steps"))):
            if s.get("capability") not in CAPABILITIES:
                fail("工序能力必须为手喷、自动、移印或 UV")
            created_steps.append(add(db, m.SprayStep, factory, actor, line_id=line.id, sequence=index + 1,
                name=text(s.get("name"), "工序名称", 128), capability=s["capability"], color=s.get("color", ""), wait_hours=number(s.get("wait_hours", 0))))
        from app.services.spray_advanced import build_graph
        build_graph(db, factory, line, v["steps"], created_steps)
    return {"id": order.id}


def update_order(db, factory, actor, p):
    order = find(db, m.SprayOrder, factory, p.get("id"))
    if order.revision != p.get("expected_revision"):
        fail("工单版本已变化", 409)
    if "due_date" in p:
        order.due_date = day(p["due_date"])
    if "priority" in p:
        order.priority = int(p["priority"])
    if p.get("close"):
        order.close_reason = text(p.get("reason"), "结案差额说明", 2000)
        active = db.scalar(select(m.SprayTask.id).join(m.SprayBatch, m.SprayTask.batch_id == m.SprayBatch.id).join(m.SprayOrderLine, m.SprayBatch.line_id == m.SprayOrderLine.id).where(m.SprayOrderLine.order_id == order.id, m.SprayTask.status.in_(["planned", "running", "paused"])))
        if active:
            fail("尚有执行或待排任务，请先完成或取消安排")
        order.status = "closed"
    order.revision += 1
    return {"id": order.id}


def prepare(db, factory, actor, p):
    line = find(db, m.SprayOrderLine, factory, p.get("line_id"))
    line.prep_ready_at = instant(p.get("ready_at")).isoformat()
    line.prep_reason = text(p.get("reason"), "领料、调油、调机及首件完成依据", 2000)
    line.revision += 1
    return {"id": line.id}


def set_price(db, factory, actor, p):
    line = find(db, m.SprayOrderLine, factory, p.get("line_id"))
    if line.revision != p.get("expected_revision"):
        fail("部件版本已变化，请重新读取价格", 409)
    previous = {"price": str(line.price) if line.price is not None else None, "currency": line.currency, "reference": line.price_reference}
    if p.get("currency") not in ("HKD", "CNY", "USD"):
        fail("币种无效")
    line.price = number(p.get("price"))
    line.currency = p["currency"]
    line.price_reference = text(p.get("reason"), "采用价格依据", 255)
    line.revision += 1
    # The immutable command receipt preserves both price versions and the actor.
    return {"id": line.id, "previous": previous, "adopted": {"price": str(line.price), "currency": line.currency, "reference": line.price_reference}}


def resource(db, factory, actor, p):
    from app.services.spray_advanced import requirements
    if p.get("capability") not in CAPABILITIES:
        fail("资源能力无效")
    windows = p.get("calendar", [])
    if not isinstance(windows, list) or len(windows) > 366:
        fail("班次日历范围无效")
    intervals = sorted([(instant(w["start"]), instant(w["end"])) for w in windows])
    for index, (start, end) in enumerate(intervals):
        if start >= end or (index and start < intervals[index - 1][1]):
            fail("日历必须是无重叠的有效工作时段")
    workers = headcount(p.get("workers"))
    if workers > 500:
        fail("请核对资源人数")
    item = add(db, m.SprayResource, factory, actor, name=text(p.get("name"), "资源名称", 128), capability=p["capability"], workers=workers,
               machine_rate=number(p["machine_rate"], positive=True) if p.get("machine_rate") else None,
               person_minutes=number(p["person_minutes"], positive=True) if p.get("person_minutes") else None,
               setup_hours=number(p.get("setup_hours", 0)), calendar=[{"start": a.isoformat(), "end": b.isoformat()} for a, b in intervals],
               shared_requirements=requirements(db,factory,p.get("shared_requirements",[])))
    return {"id": item.id}


def receive(db, factory, actor, p):
    from app.services.spray_advanced import initial_state
    for v in rows(p.get("lines")):
        line = find(db, m.SprayOrderLine, factory, v.get("line_id"))
        order = find(db, m.SprayOrder, factory, line.order_id)
        if order.status != "active":
            fail("已结案订单不能新增来料")
        accepted, held, rejected = [number(v.get(k, 0)) for k in ("accepted", "held", "rejected")]
        total = accepted + held + rejected
        if total <= 0:
            fail("来料合计必须大于零")
        batch = add(db, m.SprayBatch, factory, actor, line_id=line.id, document_no=text(p.get("document_no"), "来料单号", 128),
                    source_line=text(v.get("source_line"), "原单行号", 128), business_date=day(p.get("business_date")), received=total)
        for target, qty in [(initial_state(db,factory,line.id), accepted), ("receipt-held", held), ("rejected", rejected)]:
            move(db, factory, actor, batch.id, batch.id, "receipt", "", target, qty)
    return {"id": batch.id}


def throughput(quantity, machine_rate, person_minutes, workers, setup_hours):
    staff = D(workers) * 60 / person_minutes
    rate = min(machine_rate, staff)
    return {"staff_rate": str(staff), "effective_rate": str(rate), "hours": str(quantity / rate + setup_hours)}


def plan_changes(db, factory, changes):
    from app.services.spray_advanced import eligible, requirements, check_shared
    normalized = []
    booked = {}
    edits = {v.get("task_id") for v in changes if v.get("task_id")}
    if len(edits)!=sum(bool(v.get('task_id')) for v in changes):fail('同一任务不能在草案中重复改排')
    released={}
    for ident in edits:
        previous=find(db,m.SprayTask,factory,ident)
        key=(previous.batch_id,previous.input_state)
        released[key]=released.get(key,D(0))+previous.quantity
    for v in rows(changes):
        batch = find(db, m.SprayBatch, factory, v.get("batch_id"))
        line = find(db, m.SprayOrderLine, factory, batch.line_id)
        order = find(db, m.SprayOrder, factory, line.order_id)
        if order.status != "active":
            fail("已结案工单不能排产")
        step = find(db, m.SprayStep, factory, v.get("step_id"))
        res = find(db, m.SprayResource, factory, v.get("resource_id"))
        if step.line_id != line.id or step.capability != res.capability:
            fail("工序、部件或资源能力不兼容", 409)
        quantity = number(v.get("quantity"), positive=True)
        workers = headcount(v.get("workers"))
        if workers > res.workers:
            fail(f"{res.name} 配置人数不足", 409)
        start = instant(v.get("start_at"))
        if not line.prep_ready_at or start < instant(line.prep_ready_at):
            fail("备产尚未完成，不能预留正式生产；请登记完成依据", 409)
        source = v.get("input_state") or (f"rework:{step.id}" if v.get("rework") else ready(step))
        if step.id not in {x.id for x in eligible(db,factory,line.id,source)}:
            fail("此实体状态尚未满足所选工序的全部前置关系",409)
        available = stock(db, factory, batch.id).get(source, D(0))+released.get((batch.id,source),D(0))
        if v.get("task_id"):
            old = find(db, m.SprayTask, factory, v["task_id"])
            if old.status != "planned" or old.revision != v.get("expected_revision"):
                fail("该任务已开始或版本变化，不能移动", 409)
            if (old.batch_id, old.step_id, old.input_state) != (batch.id, step.id, source):
                fail("改排不能更换实体批次或工序")
        key = (batch.id, source)
        booked[key] = booked.get(key, D(0)) + quantity
        if booked[key] > available:
            fail("实收/前工序已放行数量不足，预计到料不能占用", 409)
        waits = list(db.scalars(select(m.SprayMovement).where(m.SprayMovement.factory_id == factory, m.SprayMovement.batch_id == batch.id, m.SprayMovement.to_state == source, m.SprayMovement.available_at != "")))
        if any(start < instant(w.available_at) for w in waits):
            fail("前工序等待/固化尚未完成", 409)
        if v.get("manual_hours"):
            hours = number(v["manual_hours"], positive=True)
            basis = text(v.get("duration_reason"), "手填时长依据", 128)
        elif res.machine_rate and res.person_minutes:
            hours = D(throughput(quantity, res.machine_rate, res.person_minutes, workers, res.setup_hours)["hours"])
            basis = "已配置设备与人员节拍"
        else:
            fail("缺节拍，请填写确认工时和估算依据")
        end = start + timedelta(seconds=float(hours * 3600))
        if not any(start >= instant(w["start"]) and end <= instant(w["end"]) for w in res.calendar):
            fail(f"{res.name} 此安排超出已配置班次；请拆分数量到工作时段", 409)
        existing = db.scalars(select(m.SprayTask).where(m.SprayTask.factory_id == factory, m.SprayTask.resource_id == res.id, m.SprayTask.status.in_(["planned", "running", "paused"])))
        for task in existing:
            if task.id not in edits and start < instant(task.end_at) and end > instant(task.start_at):
                fail(f"{res.name} 与已有安排重叠", 409)
        if any(n["resource_id"] == res.id and start < instant(n["end_at"]) and end > instant(n["start_at"]) for n in normalized):
            fail(f"草案中 {res.name} 时段重叠", 409)
        shared = requirements(db,factory,v.get("shared_allocations",res.shared_requirements))
        if any(not any(x["id"] == required["id"] and x["quantity"] >= required["quantity"] for x in shared) for required in res.shared_requirements):
            fail("安排不能省略资源必需的人员或工装",409)
        all_occupied = [serial(t) for t in db.scalars(select(m.SprayTask).where(m.SprayTask.factory_id==factory,m.SprayTask.status.in_(["planned","running","paused"]))) if t.id not in edits]
        check_shared(db,factory,shared,start,end,all_occupied+normalized)
        normalized.append({"task_id": v.get("task_id"), "expected_revision": v.get("expected_revision"), "batch_id": batch.id,
                           "step_id": step.id, "resource_id": res.id, "quantity": str(quantity), "workers": workers,
                           "start_at": start.isoformat(), "end_at": end.isoformat(), "input_state": source,
                           "duration_source": basis, "manual_hours": str(hours) if v.get("manual_hours") else None, "duration_reason": basis,
                           "shared_allocations": shared, "rework": source.startswith("rework:"), "late": end.date().isoformat() > order.due_date})
    return normalized


def preview_plan(db, factory, actor, p):
    changes = plan_changes(db, factory, p.get("changes"))
    current = revision(db, factory)
    item = add(db, m.SprayScenario, factory, actor, base_revision=current, changes=changes)
    return {"id": item.id, "changes": changes, "base_revision": current, "warnings": ["存在超交期安排"] if any(v["late"] for v in changes) else []}


def apply_plan(db, factory, actor, p):
    item = find(db, m.SprayScenario, factory, p.get("scenario_id"))
    if item.status != "draft" or item.base_revision + 1 != revision(db, factory):
        fail("草案基准已变化，请保留改动并重新预览", 409)
    changes = plan_changes(db, factory, item.changes)
    ids = []
    for v in changes:
        if v["task_id"]:
            old = find(db, m.SprayTask, factory, v["task_id"])
            move(db, factory, actor, old.batch_id, item.id, "unreserve", f"reserved:{old.id}", old.input_state, old.quantity)
            old.status = "cancelled"
            old.revision += 1
        task = add(db, m.SprayTask, factory, actor, **{k: v[k] for k in ("batch_id", "step_id", "resource_id", "workers", "start_at", "end_at", "input_state", "duration_source", "shared_allocations")}, quantity=D(v["quantity"]))
        for allocation in v["shared_allocations"]:
            add(db,m.SprayTaskAllocation,factory,actor,task_id=task.id,shared_resource_id=allocation["id"],quantity=allocation["quantity"])
        move(db, factory, actor, task.batch_id, item.id, "reserve", task.input_state, f"reserved:{task.id}", task.quantity)
        ids.append(task.id)
    item.status = "applied"
    return {"ids": ids}


def task_action(db, factory, actor, p):
    task = find(db, m.SprayTask, factory, p.get("task_id"))
    action = p.get("action")
    if action in ("start","resume") and task.shared_allocations:
        from app.services.spray_advanced import check_shared
        current=datetime.now(UTC);end=current+timedelta(seconds=1)
        occupied=[{**serial(t),"start_at":current.isoformat(),"end_at":end.isoformat()} for t in db.scalars(select(m.SprayTask).where(m.SprayTask.factory_id==factory,m.SprayTask.id!=task.id,m.SprayTask.status=="running"))]
        check_shared(db,factory,task.shared_allocations,current,end,occupied)
    if action == "start" and task.status == "planned":
        # Schedule is a forecast; actual readiness is checked again at execution time.
        line = find(db, m.SprayOrderLine, factory, find(db, m.SprayBatch, factory, task.batch_id).line_id)
        current = datetime.now(UTC)
        if not line.prep_ready_at or instant(line.prep_ready_at) > current:
            fail("备产实际完成时间尚未到达")
        if any(v.available_at and instant(v.available_at) > current for v in db.scalars(select(m.SprayMovement).where(m.SprayMovement.batch_id == task.batch_id, m.SprayMovement.to_state == task.input_state))):
            fail("前工序等待时间尚未结束")
        running = db.scalar(select(m.SprayTask.id).where(m.SprayTask.factory_id == factory, m.SprayTask.resource_id == task.resource_id, m.SprayTask.status == "running"))
        if running:
            fail("此资源已有正在执行的任务", 409)
        move(db, factory, actor, task.batch_id, task.id, "start", f"reserved:{task.id}", f"running:{task.id}", task.quantity)
        task.status = "running"
    elif action == "pause" and task.status == "running":
        text(p.get("reason"), "暂停原因", 2000)
        task.status = "paused"
    elif action == "resume" and task.status == "paused":
        if db.scalar(select(m.SprayTask.id).where(m.SprayTask.factory_id == factory, m.SprayTask.resource_id == task.resource_id, m.SprayTask.status == "running")):
            fail("资源已有其他正在执行任务", 409)
        task.status = "running"
    elif action == "cancel" and task.status == "planned":
        move(db, factory, actor, task.batch_id, task.id, "cancel", f"reserved:{task.id}", task.input_state, task.quantity, text(p.get("reason"), "取消原因"))
        task.status = "cancelled"
    else:
        fail("当前任务状态不支持此操作", 409)
    task.revision += 1
    return {"id": task.id}


def calculate_wage(rule, parameters, quantity, hours, workers):
    rate = number(parameters.get("rate", 0))
    adjustment = number(parameters.get("adjustment", 0), signed=True)
    if rule == "legacy_piece_normalized":
        wage = quantity * rate / workers / number(parameters.get("base_hours"), positive=True) * number(parameters.get("paid_hours"), positive=True) + adjustment
        total = wage * workers / number(parameters.get("rmb_per_hkd"), positive=True)
    elif rule == "piece_direct":
        total = quantity * rate + adjustment
    elif rule == "time_based":
        total = hours * workers * rate + adjustment
    else:
        fail("不支持的工资策略；旧手填金额须保留为待核档案")
    return total


def allocation(total, weights):
    """Largest remainder, deterministic index tie-break; exact cent conservation."""
    if not weights or sum(weights) <= 0:
        fail("人员分摊权重必须大于零")
    cents = int((total * 100).quantize(D(1), rounding=ROUND_HALF_UP))
    sign = -1 if cents < 0 else 1
    shares = [D(abs(cents)) * w / sum(weights) for w in weights]
    values = [int(v) for v in shares]
    for i in sorted(range(len(weights)), key=lambda i: (-(shares[i] - values[i]), i))[:abs(cents) - sum(values)]:
        values[i] += 1
    return [str(D(v * sign) / 100) for v in values]


def report(db, factory, actor, p):
    from app.services.spray_advanced import progress, defect, check_payroll_open
    check_payroll_open(db,factory,day(p.get("business_date")),p.get("shift"))
    head = add(db, m.SprayReport, factory, actor, business_date=day(p.get("business_date")), shift=text(p.get("shift"), "班次", 32), team=text(p.get("team"), "班组", 128))
    for v in rows(p.get("lines")):
        values = {k: number(v.get(k, 0)) for k in ("regular_qty", "overtime_qty", "regular_hours", "overtime_hours", "good", "held", "rework", "scrap")}
        qty = values["regular_qty"] + values["overtime_qty"]
        if qty != sum(values[k] for k in ("good", "held", "rework", "scrap")):
            fail("正班 + 加班数量必须等于合格 + 待判 + 返工 + 报废")
        if values["regular_hours"] + values["overtime_hours"] > 24:
            fail("单行工时不能超过 24 小时")
        task = find(db, m.SprayTask, factory, v["task_id"]) if v.get("task_id") else None
        if task:
            if task.status not in ("running", "paused") or qty <= 0:
                fail("请选择已经开工的任务并填写本次增量")
            if task.reported + qty > task.quantity:
                fail("本次报工超出任务剩余量", 409)
        elif qty != 0 or not v.get("activity"):
            fail("无生产任务时只允许有说明的零产量非生产工时")
        people = v.get("people", [])
        if not isinstance(people, list) or not 1 <= len(people) <= 500 or not all(isinstance(person, dict) for person in people):
            fail("请填写本班人员或历史班组别名")
        for person in people:
            text(person.get("name"), "人员/班组名称", 128)
        if len({str(person.get("employee_id") or person["name"]).strip() for person in people}) != len(people):
            fail("同一报工行不能重复填写同一员工")
        calc, wage_status = {}, "unpriced"
        if v.get("rate_id"):
            rate = find(db, m.SprayRate, factory, v["rate_id"])
            if rate.rule_code == "employee_shift_guarantee":
                fail("班次保底策略只能在员工班次汇总采用，不能逐任务重复计算")
            if rate.effective_date > head.business_date:
                fail("工价版本尚未生效")
            basis = values["good"] if rate.quantity_basis == "good" else qty
            total = calculate_wage(rate.rule_code, rate.parameters, basis, values["regular_hours"] + values["overtime_hours"], D(len(people)))
            wage_status = "verified" if rate.status == "active" else "provisional"
            calc = {"rate_id": rate.id, "rule_code": rate.rule_code, "parameters": rate.parameters, "quantity": str(basis), "unrounded_amount": str(total), "amount": str(total.quantize(D('.01'), rounding=ROUND_HALF_UP)), "currency": rate.currency,
                    "allocations": allocation(total, [number(person.get("weight", 1), positive=True) for person in people])}
        result = add(db, m.SprayReportLine, factory, actor, report_id=head.id, task_id=task.id if task else None, activity=v.get("activity", ""), people=people, calculation=calc, wage_status=wage_status, **values)
        if task:
            step = find(db, m.SprayStep, factory, task.step_id)
            available_at = (datetime.now(UTC) + timedelta(hours=float(step.wait_hours))).isoformat() if step.wait_hours else ""
            for target, value in [(progress(db,factory,step,task.input_state), values["good"]), (defect(step,task.input_state,"held"), values["held"]), (defect(step,task.input_state,"rework"), values["rework"]), ("scrap", values["scrap"])]:
                move(db, factory, actor, task.batch_id, result.id, "report", f"running:{task.id}", target, value, available_at=available_at if target.startswith(("ready:","route:")) or target == "finished" else "")
            task.reported += qty
            task.revision += 1
            if task.reported == task.quantity:
                task.status = "completed"
    return {"id": head.id}


def correct_report(db, factory, actor, p):
    from app.services.spray_advanced import check_payroll_open
    original = find(db, m.SprayReport, factory, p.get("report_id"))
    check_payroll_open(db,factory,original.business_date,original.shift)
    if original.status != "confirmed":
        fail("报工已经更正", 409)
    reason = text(p.get("reason"), "更正原因", 2000)
    originals = list(db.scalars(select(m.SprayReportLine).where(m.SprayReportLine.report_id == original.id)))
    original_ids = [line.id for line in originals]
    for line in originals:
        movements = list(db.scalars(select(m.SprayMovement).where(m.SprayMovement.event_id == line.id)))
        for movement in movements:
            consumed = db.scalar(select(m.SprayMovement.id).where(
                m.SprayMovement.factory_id == factory, m.SprayMovement.batch_id == movement.batch_id,
                m.SprayMovement.from_state == movement.to_state,
                m.SprayMovement.created_at >= movement.created_at,
                m.SprayMovement.event_id.not_in(original_ids + [original.id])))
            if consumed:
                fail("报工产出已有后续流转，请使用独立差额记录，不能回改原报工", 409)
            # Reject correction after downstream consumption; never manufacture a balance.
            move(db, factory, actor, movement.batch_id, original.id, "report_reversal", movement.to_state, movement.from_state, movement.quantity, reason)
        if line.task_id:
            task = find(db, m.SprayTask, factory, line.task_id)
            task.reported -= line.regular_qty + line.overtime_qty
            task.status = "running"
            task.revision += 1
    original.status = "corrected"
    result = report(db, factory, actor, p)
    replacement = find(db, m.SprayReport, factory, result["id"])
    replacement.corrected_report_id = original.id
    replacement.reason = reason
    return result


def quality(db, factory, actor, p):
    from app.services.spray_advanced import initial_state, progress
    batch = find(db, m.SprayBatch, factory, p.get("batch_id"))
    source = p.get("source_state")
    disposition = p.get("disposition")
    allowed = ("release", "reject") if source == "receipt-held" else ("release", "rework", "scrap")
    if disposition not in allowed:
        fail("来料待检只允许放行或拒收；生产及退货待判只允许放行、返工或报废")
    available_at = ""
    if source == "receipt-held":
        target = initial_state(db,factory,batch.line_id) if p.get("disposition") == "release" else "rejected"
    elif source == "return-held":
        if p.get("disposition") == "release":
            target = "finished"
        elif p.get("disposition") == "rework":
            step = find(db, m.SprayStep, factory, p.get("step_id"))
            if step.line_id != batch.line_id:
                fail("返工工序不属于此部件")
            line = find(db,m.SprayOrderLine,factory,batch.line_id)
            suffix = ":route:" + ",".join(sorted(x.id for x in steps(db,factory,line.id) if x.id != step.id)) if line.graph_route else ""
            target = f"rework:{step.id}" + suffix
        else:
            target = "scrap"
    elif source and source.startswith("held:"):
        step = find(db, m.SprayStep, factory, source.split(":")[1])
        if step.line_id != batch.line_id:
            fail("待判工序不属于此部件")
        target = progress(db,factory,step,source) if p.get("disposition") == "release" else source.replace("held:","rework:",1) if p.get("disposition") == "rework" else "scrap"
        if disposition == "release" and step.wait_hours:
            available_at = (datetime.now(UTC) + timedelta(hours=float(step.wait_hours))).isoformat()
    else:
        fail("请选择真实的待判批次")
    if p.get("disposition") not in ("release", "rework", "scrap", "reject"):
        fail("处置类型无效")
    event = uuid4().hex
    move(db, factory, actor, batch.id, event, "quality", source, target, number(p.get("quantity"), positive=True), text(p.get("reason"), "质量处置说明", 2000), available_at=available_at)
    return {"id": event}


def make_rate(db, factory, actor, p):
    if not isinstance(p.get("parameters"), dict):
        fail("工资策略参数必须是明确的键值字段")
    if p.get("rule_code") not in ("legacy_piece_normalized", "piece_direct", "time_based", "employee_shift_guarantee") or p.get("quantity_basis") not in ("good", "attempt"):
        fail("请选择明确的工资策略及计量口径")
    if p.get("currency") not in ("HKD", "CNY", "USD"):
        fail("币种无效")
    if p["rule_code"] == "employee_shift_guarantee":
        number(p["parameters"].get("regular_hour_rate",0))
        number(p["parameters"].get("overtime_hour_rate",0))
    else:
        calculate_wage(p["rule_code"], p.get("parameters", {}), D(1), D(1), D(1))
    item = add(db, m.SprayRate, factory, actor, name=text(p.get("name"), "工价名称", 128), rule_code=p["rule_code"], currency=p["currency"],
               quantity_basis=p["quantity_basis"], parameters=p["parameters"], effective_date=day(p.get("effective_date")), evidence=text(p.get("evidence"), "工价来源", 2000))
    return {"id": item.id}


def activate_rate(db, factory, actor, p):
    item = find(db, m.SprayRate, factory, p.get("rate_id"))
    if item.rule_code == "legacy_piece_normalized":
        fail("历史兼容策略仅用于复算，不可直接升级为正式工资制度")
    item.evidence += "\n正式采用依据：" + text(p.get("reason"), "正式采用依据", 2000)
    item.status = "active"
    item.revision += 1
    return {"id": item.id}


def frozen(db, factory, customer, business_date, currency):
    if db.scalar(select(m.SpraySettlement.id).where(m.SpraySettlement.factory_id == factory, m.SpraySettlement.customer == customer, m.SpraySettlement.period == business_date[:7], m.SpraySettlement.currency == currency)):
        fail("该客户币种期间已冻结，请在开放期间登记退货/差额凭据", 409)


def shipment(db, factory, actor, p):
    head = add(db, m.SprayShipment, factory, actor, document_no=text(p.get("document_no"), "送货单号", 128), customer=text(p.get("customer"), "客户", 128), business_date=day(p.get("business_date")))
    for v in rows(p.get("lines")):
        batch = find(db, m.SprayBatch, factory, v.get("batch_id"))
        line = find(db, m.SprayOrderLine, factory, batch.line_id)
        order = find(db, m.SprayOrder, factory, line.order_id)
        if order.customer != head.customer or line.price is None:
            fail("客户不匹配或结算价尚未确认")
        frozen(db, factory, head.customer, head.business_date, line.currency)
        quantity = number(v.get("quantity"), positive=True)
        result = add(db, m.SprayShipmentLine, factory, actor, shipment_id=head.id, batch_id=batch.id, quantity=quantity, price=line.price,
                     currency=line.currency, amount=(quantity * line.price).quantize(D(".01"), rounding=ROUND_HALF_UP), price_reference=line.price_reference)
        waiting = db.scalars(select(m.SprayMovement).where(m.SprayMovement.batch_id == batch.id, m.SprayMovement.to_state == "finished"))
        if any(v.available_at and instant(v.available_at) > datetime.now(UTC) for v in waiting):
            fail("成品仍在工艺等待期")
        move(db, factory, actor, batch.id, result.id, "shipment", "finished", "shipped", quantity)
    for v in p.get("containers", []):
        returnable(db, factory, actor, {**v, "customer": head.customer, "document_no": head.document_no})
    return {"id": head.id}


def return_goods(db, factory, actor, p):
    original = find(db, m.SprayShipmentLine, factory, p.get("shipment_line_id"))
    source = find(db, m.SprayShipment, factory, original.shipment_id)
    if source.kind != "delivery":
        fail("退货必须引用原送货明细")
    business_date = day(p.get("business_date"))
    frozen(db, factory, source.customer, business_date, original.currency)
    if business_date < source.business_date:
        fail("退货日期不能早于送出日期")
    quantity = number(p.get("quantity"), positive=True)
    returned = db.scalar(select(func.sum(m.SprayShipmentLine.quantity)).where(m.SprayShipmentLine.original_line_id == original.id)) or D(0)
    if quantity - returned > original.quantity:
        fail("累计退货超过原送货量", 409)
    returned_amount = db.scalar(select(func.sum(m.SprayShipmentLine.amount)).where(m.SprayShipmentLine.original_line_id == original.id)) or D(0)
    cumulative_credit = ((quantity - returned) * original.amount / original.quantity).quantize(D(".01"), rounding=ROUND_HALF_UP)
    credit = -cumulative_credit - returned_amount
    head = add(db, m.SprayShipment, factory, actor, document_no=text(p.get("document_no"), "退货单号", 128), customer=source.customer,
               business_date=business_date, kind="return", reason=text(p.get("reason"), "退货原因", 2000))
    item = add(db, m.SprayShipmentLine, factory, actor, shipment_id=head.id, batch_id=original.batch_id, original_line_id=original.id,
               quantity=-quantity, price=original.price, currency=original.currency, amount=credit, price_reference=original.price_reference)
    move(db, factory, actor, original.batch_id, item.id, "return", "shipped", "return-held", quantity, head.reason)
    return {"id": head.id}


def returnable(db, factory, actor, p):
    item = add(db, m.SprayReturnable, factory, actor, customer=text(p.get("customer"), "往来客户", 128), name=text(p.get("name"), "容器名称", 128),
               quantity=number(p.get("quantity"), signed=True), unit=text(p.get("unit"), "容器单位", 16), document_no=text(p.get("document_no"), "凭据号", 128), reason=p.get("reason", ""))
    return {"id": item.id}


def settlement_preview(db, factory, p):
    period = text(p.get("period"), "结算月份", 7)
    day(period + "-01")
    customer = text(p.get("customer"), "客户", 128)
    currency = p.get("currency", "HKD")
    candidates = list(db.scalars(select(m.SprayShipmentLine).join(m.SprayShipment, m.SprayShipmentLine.shipment_id == m.SprayShipment.id).where(
        m.SprayShipment.factory_id == factory, m.SprayShipment.customer == customer, m.SprayShipment.business_date.startswith(period), m.SprayShipmentLine.currency == currency,
        ~m.SprayShipmentLine.id.in_(select(m.SpraySettlementLine.shipment_line_id)))))
    used={ident for record in db.scalars(select(m.SpraySettlement).where(m.SpraySettlement.factory_id==factory)) for ident in record.adjustment_ids}
    adjustments=list(db.scalars(select(m.SprayAdjustment).join(m.SpraySettlement,m.SprayAdjustment.settlement_id==m.SpraySettlement.id).where(
        m.SprayAdjustment.factory_id==factory,m.SprayAdjustment.business_date.startswith(period),m.SpraySettlement.customer==customer,m.SpraySettlement.currency==currency,m.SprayAdjustment.id.not_in(used))))
    return {"customer": customer, "period": period, "currency": currency, "amount": str(sum((v.amount for v in candidates+adjustments), D(0))), "lines": [serial(v) for v in candidates],"adjustments":[serial(v) for v in adjustments]}


def settle(db, factory, actor, p):
    values = settlement_preview(db, factory, p)
    if not values["lines"] and not values["adjustments"]:
        fail("此客户、月份和币种没有未结算送货明细")
    adjustment_ids=sorted(v["id"] for v in values["adjustments"])
    provided_adjustments=sorted(v["id"] for v in p.get("adjustments",[]))
    if p.get("line_ids") != sorted(v["id"] for v in values["lines"]) or p.get("amount") != values["amount"] or provided_adjustments!=adjustment_ids:
        fail("月结候选已变化，请重新预览", 409)
    item = add(db, m.SpraySettlement, factory, actor, **{k: values[k] for k in ("customer", "period", "currency", "amount")})
    item.adjustment_ids=sorted(v["id"] for v in values["adjustments"])
    for v in values["lines"]:
        add(db, m.SpraySettlementLine, factory, actor, settlement_id=item.id, shipment_line_id=v["id"], amount=D(v["amount"]))
    return {"id": item.id}


def purchase(db, factory, actor, p):
    conversion = number(p.get("conversion", 1), positive=True)
    unit, base = text(p.get("unit"), "采购单位", 16), text(p.get("base_unit"), "基本单位", 16)
    if unit == base and conversion != 1:
        fail("同单位换算系数必须为 1")
    evidence = text(p.get("conversion_evidence"), "包装换算依据", 2000) if unit != base else "同单位"
    item = add(db, m.SprayPurchase, factory, actor, document_no=text(p.get("document_no"), "采购单号", 128), supplier=text(p.get("supplier"), "供应商", 128),
               material=text(p.get("material"), "物料", 128), quantity=number(p.get("quantity"), positive=True), unit=unit, base_unit=base, conversion=conversion,
               conversion_evidence=evidence, price=number(p.get("price")), currency=p.get("currency", "CNY"))
    return {"id": item.id}


def material_event(db, factory, actor, p):
    item = find(db, m.SprayPurchase, factory, p.get("purchase_id"))
    kind = p.get("kind")
    if kind not in ("receipt", "issue", "return", "consume"):
        fail("物料事件类型无效")
    qty = number(p.get("quantity"), positive=True)
    events = list(db.scalars(select(m.SprayMaterialEvent).where(m.SprayMaterialEvent.purchase_id == item.id)))
    totals = {k: sum((e.quantity for e in events if e.kind == k), D(0)) for k in ("receipt", "issue", "return", "consume")}
    store_qty = totals["receipt"] - totals["issue"] + totals["return"]
    workshop_qty = totals["issue"] - totals["return"] - totals["consume"]
    if kind == "receipt" and totals["receipt"] + qty > item.quantity * item.conversion:
        fail("采购收货超过订购基本单位量", 409)
    if (kind == "issue" and qty > store_qty) or (kind in ("return", "consume") and qty > workshop_qty):
        fail("仓库/车间结存不足", 409)
    if p.get("order_id"):
        find(db, m.SprayOrder, factory, p["order_id"])
    event = add(db, m.SprayMaterialEvent, factory, actor, purchase_id=item.id, kind=kind, quantity=qty, business_date=day(p.get("business_date")),
                document_no=text(p.get("document_no"), "物料凭证号", 128), order_id=p.get("order_id") or None,
                cost=qty * item.price / item.conversion if kind == "consume" else D(0), reason=p.get("reason", ""))
    return {"id": event.id}


ACTIONS = {"orders": create_order, "order-update": update_order, "price-set": set_price, "prepare": prepare, "resources": resource, "receipts": receive,
           "schedule-preview": preview_plan, "schedule-apply": apply_plan, "task-state": task_action, "reports": report,
           "report-correct": correct_report, "quality": quality, "rates": make_rate, "rate-activate": activate_rate,
           "shipments": shipment, "returns": return_goods, "returnables": returnable, "settlements": settle,
           "purchases": purchase, "material-events": material_event}
