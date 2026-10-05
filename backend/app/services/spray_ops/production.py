"""Demand, physical flow and reports. Mutators run inside common.command."""
from datetime import datetime, time, UTC, timedelta
from decimal import Decimal

from sqlalchemy import select, func, delete

from app.models import spray_ops as m
from . import schemas as s
from .common import add, get, scoped, serialize, require, version, touch, timestamp, check_period


def rows(db, model, factory, **filters):
    return list(db.scalars(scoped(db, model, factory).filter_by(**filters)))


def piece_quantity(quantity, unit):
    if unit in {"件", "个", "套", "只", "pcs", "PCS"}:
        require(quantity == quantity.to_integral_value(), "discrete_quantity", "件、个、套等离散单位必须为整数", 422)


def create_resource(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新资源版本应为 0")
    require(len({c.capability for c in b.capabilities}) == len(b.capabilities), "duplicate_capability", "能力不能重复", 422)
    for cap in b.capabilities:
        require(cap.hourly_capacity is None or cap.evidence, "capacity_unconfirmed", "产能须附确认依据", 422)
    resource = add(db, m.SprayOpsResource, f, **b.model_dump(include={"code", "name", "kind", "capacity"}))
    for cap in b.capabilities:
        add(db, m.SprayOpsCapability, f, resource_id=resource.id, **cap.model_dump())
    for window in b.calendar:
        add(db, m.SprayOpsCalendar, f, resource_id=resource.id, **window.model_dump(exclude={"start_at", "end_at"}), start_at=timestamp(window.start_at), end_at=timestamp(window.end_at))
    return resource_detail(db, f, resource)


def resource_detail(db, f, resource):
    return {**serialize(resource), "capabilities": [serialize(c) for c in rows(db, m.SprayOpsCapability, f, resource_id=resource.id)], "calendar": [serialize(c) for c in rows(db, m.SprayOpsCalendar, f, resource_id=resource.id)]}


def set_calendar(db, f, resource_id, b):
    resource = get(db, m.SprayOpsResource, f, resource_id)
    version(resource, b.expected_version)
    # Never silently move already published work when removing availability.
    tasks = list(db.scalars(scoped(db, m.SprayOpsTask, f).where(m.SprayOpsTask.status.in_(["planned", "started", "paused"]))))
    steps = {step.id: step for step in rows(db, m.SprayOpsStep, f)}
    for task in tasks:
        if resource.id in {task.resource_id, steps[task.step_id].tool_id, steps[task.step_id].crew_id}:
            active = [w for w in b.calendar if w.kind == "available" and timestamp(w.start_at) <= task.start_at and timestamp(w.end_at) >= task.end_at]
            blocked = [w for w in b.calendar if w.kind != "available" and timestamp(w.start_at) < task.end_at and timestamp(w.end_at) > task.start_at]
            require(active and not blocked, "published_task_conflict", "新日历与已发布任务冲突", conflicts=[dict(entity_id=task.id)])
    for old in rows(db, m.SprayOpsCalendar, f, resource_id=resource.id):
        db.delete(old)
    for window in b.calendar:
        add(db, m.SprayOpsCalendar, f, resource_id=resource.id, start_at=timestamp(window.start_at), end_at=timestamp(window.end_at), kind=window.kind, reason=window.reason)
    touch(resource)
    return resource_detail(db, f, resource)


def validate_dag(steps):
    graph = {step.code: set(step.predecessors) for step in steps}
    require(len(graph) == len(steps), "duplicate_step", "工序编码不能重复", 422)
    require(all(pred <= graph.keys() for pred in graph.values()), "unknown_predecessor", "前置工序不存在", 422)
    done = set()
    while len(done) < len(graph):
        ready = {code for code, predecessors in graph.items() if code not in done and predecessors <= done}
        require(ready, "route_cycle", "工艺不能包含循环依赖", 422)
        done |= ready


def create_route(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新工艺版本应为 0")
    validate_dag(b.steps)
    require(not b.confirmed or b.evidence, "route_evidence_required", "确认工艺须附依据", 422)
    route = add(db, m.SprayOpsRoute, f, code=b.code, label=b.label, revision=b.revision, status="confirmed" if b.confirmed else "draft", evidence=b.evidence)
    created = {}
    for step in b.steps:
        for field, kind in [("tool_id", "tool"), ("crew_id", "crew")]:
            if getattr(step, field):
                resource = get(db, m.SprayOpsResource, f, getattr(step, field))
                require(resource.kind == kind and resource.enabled, "resource_kind", "辅助资源类型不匹配", 422)
        require(step.input_unit == step.output_unit and step.output_ratio == 1 or b.evidence, "unit_unconfirmed", "工序单位换算须附确认依据", 422)
        created[step.code] = add(db, m.SprayOpsStep, f, route_id=route.id, **step.model_dump(exclude={"predecessors"}))
    for step in b.steps:
        for predecessor in step.predecessors:
            add(db, m.SprayOpsPredecessor, f, step_id=created[step.code].id, predecessor_id=created[predecessor].id)
    return route_detail(db, f, route)


def route_detail(db, f, route):
    steps = rows(db, m.SprayOpsStep, f, route_id=route.id)
    edges = list(db.scalars(scoped(db, m.SprayOpsPredecessor, f).where(m.SprayOpsPredecessor.step_id.in_([step.id for step in steps]))))
    return {**serialize(route), "steps": [{**serialize(step), "predecessors": [edge.predecessor_id for edge in edges if edge.step_id == step.id]} for step in steps]}


def demand_detail(db, f, demand):
    lines = rows(db, m.SprayOpsDemandLine, f, demand_id=demand.id)
    line_ids = [line.id for line in lines]
    lots = list(db.scalars(scoped(db, m.SprayOpsStock, f).where(m.SprayOpsStock.line_id.in_(line_ids), m.SprayOpsStock.quantity > 0)))
    batches = list(db.scalars(scoped(db, m.SprayOpsBatch, f).where(m.SprayOpsBatch.line_id.in_(line_ids))))
    return {**serialize(demand), "lines": [{**serialize(line), "received": str(sum(batch.accepted for batch in batches if batch.line_id == line.id and batch.kind == "arrival")), "opening_balance": str(sum(batch.accepted for batch in batches if batch.line_id == line.id and batch.kind == "opening")), "balances": {state: str(sum(lot.quantity for lot in lots if lot.line_id == line.id and lot.state == state and lot.unit == line.unit)) for state in ("white", "wip", "hold", "finished")}, "balances_by_unit": {state: {unit: str(sum(lot.quantity for lot in lots if lot.line_id == line.id and lot.state == state and lot.unit == unit)) for unit in sorted({lot.unit for lot in lots if lot.line_id == line.id and lot.state == state})} for state in ("white", "wip", "hold", "finished")}} for line in lines]}


def create_demand(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新订单版本应为 0")
    demand = add(db, m.SprayOpsDemand, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "lines", "confirm", "business_date"}), business_date=str(b.business_date), status="confirmed" if b.confirm else "draft")
    for line in b.lines:
        piece_quantity(line.quantity, line.unit)
        if line.route_id:
            get(db, m.SprayOpsRoute, f, line.route_id)
        require(line.commercial_price is None or line.price_evidence, "price_unconfirmed", "单价须附确认依据", 422)
        add(db, m.SprayOpsDemandLine, f, demand_id=demand.id, **line.model_dump(exclude={"due_date", "expected_arrival"}), due_date=str(line.due_date), expected_arrival=str(line.expected_arrival) if line.expected_arrival else None)
    return demand_detail(db, f, demand)


def demand_journey(db, f, demand_id):
    """Detail-only process totals; do not run this for every order list row."""
    line_ids = [line.id for line in rows(db, m.SprayOpsDemandLine, f, demand_id=demand_id)]
    task_allocations = list(db.scalars(scoped(db, m.SprayOpsTaskAllocation, f).where(m.SprayOpsTaskAllocation.line_id.in_(line_ids))))
    by_allocation = {a.id: a for a in task_allocations}
    tasks = {t.id: t for t in db.scalars(scoped(db, m.SprayOpsTask, f).where(m.SprayOpsTask.id.in_([a.task_id for a in task_allocations])))}
    reports = {r.id: r for r in db.scalars(scoped(db, m.SprayOpsReportRow, f).join(m.SprayOpsReport, m.SprayOpsReport.id == m.SprayOpsReportRow.report_id).where(m.SprayOpsReport.status == 'confirmed', m.SprayOpsReportRow.task_id.in_(tasks)))}
    allocations = list(db.scalars(scoped(db, m.SprayOpsReportAllocation, f).where(m.SprayOpsReportAllocation.row_id.in_(reports))))
    steps = {s.id: s for s in rows(db, m.SprayOpsStep, f)}
    stocks = {s.id: s for s in db.scalars(scoped(db, m.SprayOpsStock, f).where(m.SprayOpsStock.id.in_([a.stock_id for a in task_allocations])))}
    result = {}
    for allocation in allocations:
        source = by_allocation.get(allocation.task_allocation_id)
        if source is None:
            continue
        step = steps[tasks[source.task_id].step_id]
        key = source.line_id, step.id
        if key not in result:
            result[key] = dict(line_id=source.line_id, step_id=step.id, processed=Decimal(0), good=Decimal(0), rework_processed=Decimal(0), input_unit=step.input_unit, output_unit=step.output_unit)
        item = result[key]
        item['processed'] += allocation.processed
        item['good'] += allocation.good * step.output_ratio
        if stocks[source.stock_id].rework_origin:
            item['rework_processed'] += allocation.processed
    return list(result.values())


def amend_demand(db, f, demand_id, b):
    demand = get(db, m.SprayOpsDemand, f, demand_id)
    version(demand, b.expected_version)
    check_period(db, f, demand.business_date)
    line = get(db, m.SprayOpsDemandLine, f, b.line_id)
    require(line.demand_id == demand.id, "line_mismatch", "订单行不属于此订单", 422)
    piece_quantity(b.quantity, line.unit)
    received = sum(batch.quantity for batch in rows(db, m.SprayOpsBatch, f, line_id=line.id))
    require(b.quantity >= received, "downstream_impact", "订单数量不能小于已关联来料，请先处理下游记录", conflicts=[dict(entity_id=line.id, received=str(received))])
    if b.route_id and b.route_id != line.route_id:
        route = get(db, m.SprayOpsRoute, f, b.route_id)
        require(route.status == "confirmed", "route_unconfirmed", "请选择已确认工艺")
        require(not rows(db, m.SprayOpsTaskAllocation, f, line_id=line.id), "downstream_impact", "已有排期或实绩不能替换工艺版本")
        line.route_id = route.id
    line.quantity, line.due_date, line.priority = b.quantity, str(b.due_date), b.priority
    demand.note += f"\n修订：{b.reason}"
    touch(line)
    touch(demand)
    return demand_detail(db, f, demand)


def completed(db, f, stock_id):
    return {row.step_id for row in rows(db, m.SprayOpsCompletedStep, f, stock_id=stock_id)}


def confirm_demand(db, f, demand_id, b):
    demand = get(db, m.SprayOpsDemand, f, demand_id)
    version(demand, b.expected_version)
    check_period(db, f, demand.business_date)
    require(demand.status == "draft", "demand_state", "只能确认草稿订单")
    demand.status = "confirmed"
    touch(demand)
    return demand_detail(db, f, demand)


def make_stock(db, f, batch_id, line_id, quantity, unit, state, ready_at, steps=(), pending_step_id=None, rework_origin=None):
    stock = add(db, m.SprayOpsStock, f, batch_id=batch_id, line_id=line_id, quantity=quantity, unit=unit, state=state, ready_at=ready_at, pending_step_id=pending_step_id, rework_origin=rework_origin)
    for step in sorted(steps):
        add(db, m.SprayOpsCompletedStep, f, stock_id=stock.id, step_id=step)
    return stock


def movement(db, f, source, target, qty, out_qty, kind, reference, day, reason="", reversal_of=None):
    return add(db, m.SprayOpsMovement, f, from_stock_id=source.id if source else None, to_stock_id=target.id if target else None, quantity=qty, output_quantity=out_qty, kind=kind, reference_id=reference, business_date=str(day), reason=reason, reversal_of=reversal_of)


def check_batch_line(db, f, b, line):
    demand = get(db, m.SprayOpsDemand, f, line.demand_id)
    require(demand.status in {"confirmed", "in_progress"}, "demand_not_confirmed", "订单未确认或已结束")
    require((line.item_no, line.part, line.unit) == (b.item_no, b.part, b.unit), "item_mismatch", "来料货号、部位、单位须与订单行一致", 422)
    total = sum(row.quantity for row in rows(db, m.SprayOpsBatch, f, line_id=line.id) if row.id != getattr(b, "id", None))
    require(total + b.quantity <= line.quantity, "arrival_exceeds_demand", "关联来料超过订单数量；超收请保留为待匹配来料")


def create_batch(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新来料版本应为 0")
    piece_quantity(b.quantity, b.unit)
    for qty in (b.accepted, b.held, b.rejected):
        piece_quantity(qty, b.unit)
    if b.line_id:
        check_batch_line(db, f, b, get(db, m.SprayOpsDemandLine, f, b.line_id))
    batch = add(db, m.SprayOpsBatch, f, **b.model_dump(exclude={"factory_id", "operation_id", "expected_version", "business_date"}), business_date=str(b.business_date))
    stocks = []
    ready_at = timestamp(datetime.combine(b.business_date, time(), tzinfo=UTC) - timedelta(hours=8))
    for state, qty in [("white", b.accepted), ("hold", b.held)]:
        if qty:
            stock = make_stock(db, f, batch.id, b.line_id, qty, b.unit, state, ready_at)
            movement(db, f, None, stock, qty, qty, "arrival", batch.id, b.business_date)
            stocks.append(serialize(stock))
    return {**serialize(batch), "stock": stocks}


def match_batch(db, f, batch_id, b):
    batch = get(db, m.SprayOpsBatch, f, batch_id)
    version(batch, b.expected_version)
    check_period(db, f, batch.business_date)
    require(batch.line_id is None, "already_matched", "此来料已有订单归属")
    line = get(db, m.SprayOpsDemandLine, f, b.line_id)
    check_batch_line(db, f, batch, line)
    batch.line_id = line.id
    for stock in rows(db, m.SprayOpsStock, f, batch_id=batch.id):
        require(stock.reserved == 0, "reserved_stock", "来料已被预留")
        stock.line_id = line.id
        touch(stock)
    touch(batch)
    return serialize(batch)


def prepare(db, f, b):
    batch = get(db, m.SprayOpsBatch, f, b.batch_id)
    step = get(db, m.SprayOpsStep, f, b.step_id)
    require(batch.line_id, "unmatched_batch", "先将来料匹配订单")
    line = get(db, m.SprayOpsDemandLine, f, batch.line_id)
    require(line.route_id == step.route_id, "route_mismatch", "准备工序不属于订单工艺", 422)
    require(b.expires_at is None or b.expires_at > b.ready_at, "prep_expiry", "有效期必须晚于准备完成时间", 422)
    prep = db.scalar(scoped(db, m.SprayOpsPreparation, f).where(m.SprayOpsPreparation.batch_id == batch.id, m.SprayOpsPreparation.step_id == step.id))
    values = dict(ready_at=timestamp(b.ready_at), expires_at=timestamp(b.expires_at) if b.expires_at else None, evidence=b.evidence)
    if prep:
        version(prep, b.expected_version)
        for field, value in values.items():
            setattr(prep, field, value)
        touch(prep)
    else:
        require(b.expected_version == 0, "version_conflict", "新准备记录版本应为 0")
        prep = add(db, m.SprayOpsPreparation, f, batch_id=batch.id, step_id=step.id, **values)
    return serialize(prep)


def readiness(db, f, stock, step, at):
    require(stock.state in {"white", "wip"}, "stock_not_available", "该库存状态不可投入生产")
    require(stock.line_id, "unmatched_batch", "来料尚未匹配订单")
    line = get(db, m.SprayOpsDemandLine, f, stock.line_id)
    route = get(db, m.SprayOpsRoute, f, step.route_id)
    require(line.route_id == route.id and route.status == "confirmed", "route_unconfirmed", "订单工艺未确认或不匹配")
    done = completed(db, f, stock.id)
    preds = {edge.predecessor_id for edge in rows(db, m.SprayOpsPredecessor, f, step_id=step.id)}
    require(step.id not in done and preds <= done, "predecessor_not_ready", "前置工序未完成或当前工序已完成")
    require(stock.unit == step.input_unit, "unit_mismatch", "工序输入单位不匹配", 422)
    require(stock.ready_at <= at, "drying_not_ready", "库存尚未到可转序时间")
    if step.prep_required:
        prep = db.scalar(scoped(db, m.SprayOpsPreparation, f).where(m.SprayOpsPreparation.batch_id == stock.batch_id, m.SprayOpsPreparation.step_id == step.id))
        require(prep is not None and prep.ready_at <= at and (prep.expires_at is None or prep.expires_at >= at), "preparation_not_ready", "准备未完成或已经失效")
    return line, done


def start_task(db, f, task_id, b):
    task = get(db, m.SprayOpsTask, f, task_id)
    version(task, b.expected_version)
    require(task.status == "planned", "task_state", "只能开工已发布待开工任务")
    at = timestamp(b.actual_start)
    require(b.actual_start <= datetime.now(UTC) + timedelta(minutes=5), "future_actual", "实际开工不能在未来", 422)
    step = get(db, m.SprayOpsStep, f, task.step_id)
    for allocation in rows(db, m.SprayOpsTaskAllocation, f, task_id=task.id):
        stock = get(db, m.SprayOpsStock, f, allocation.stock_id)
        readiness(db, f, stock, step, at)
        require(stock.quantity >= allocation.quantity and stock.reserved >= allocation.quantity, "material_shortage", "预留库存不足")
    from .scheduling import validate_tasks
    actual = {"step_id": task.step_id, "resource_id": task.resource_id, "start_at": at,
              "end_at": timestamp(b.actual_start + (datetime.fromisoformat(task.end_at) - datetime.fromisoformat(task.start_at))),
              "allocations": [{"stock_id": a.stock_id, "quantity": str(a.quantity)} for a in rows(db, m.SprayOpsTaskAllocation, f, task_id=task.id)], "note": task.note}
    validate_tasks(db, f, [actual], [task.id], allow_started=False)
    task.actual_start, task.status = at, "started"
    # The actual occupancy remains visible and blocks competing reservations.
    task.start_at, task.end_at = actual["start_at"], actual["end_at"]
    touch(task)
    return task_detail(db, f, task)


def task_detail(db, f, task):
    return {**serialize(task), "allocations": [serialize(a) for a in rows(db, m.SprayOpsTaskAllocation, f, task_id=task.id)]}


def report_detail(db, f, report):
    rr = rows(db, m.SprayOpsReportRow, f, report_id=report.id)
    return {**serialize(report), "rows": [{**serialize(row), "allocations": [serialize(a) for a in rows(db, m.SprayOpsReportAllocation, f, row_id=row.id)], "labor": [serialize(l) for l in rows(db, m.SprayOpsLabor, f, row_id=row.id, active=True)]} for row in rr]}


def task_pause(db, f, task_id, b, resume=False):
    task = get(db, m.SprayOpsTask, f, task_id)
    version(task, b.expected_version)
    check_period(db, f, (datetime.fromisoformat(task.start_at) + timedelta(hours=8)).date())
    require(task.status == ("paused" if resume else "started"), "task_state", "当前任务状态不支持此操作")
    task.status = "started" if resume else "paused"
    task.note += f"\n{b.business_date} {'恢复' if resume else '暂停'}：{b.reason}"
    touch(task)
    return task_detail(db, f, task)


def set_report_labor(db, f, report_id, b):
    report = get(db, m.SprayOpsReport, f, report_id)
    version(report, b.expected_version)
    check_period(db, f, report.business_date)
    payroll_day_mutable(db, f, report.business_date)
    require(report.status in {"draft", "confirmed"}, "report_state", "冲回日报不可修改工时")
    row = get(db, m.SprayOpsReportRow, f, b.row_id)
    require(row.report_id == report.id, "row_mismatch", "工时行不属于该日报", 422)
    for person in b.labor:
        require(get(db, m.SprayOpsEmployee, f, person.employee_id).enabled, "employee_disabled", "员工已停用")
        require(not person.nonproductive_hours or person.reason, "labor_reason", "非生产工时须记录原因", 422)
    previous = rows(db, m.SprayOpsLabor, f, row_id=row.id, active=True)
    before = [serialize(item) for item in previous]
    for item in previous:
        item.active = False
        touch(item)
    db.flush()
    for person in b.labor:
        add(db, m.SprayOpsLabor, f, row_id=row.id, **person.model_dump())
    touch(row)
    touch(report)
    return {**report_detail(db, f, report), "previous_labor": before, "correction_reason": b.reason}


def create_report(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新日报版本应为 0")
    payroll_day_mutable(db, f, str(b.business_date))
    report = add(db, m.SprayOpsReport, f, document_no=b.document_no, business_date=str(b.business_date), shift=b.shift, source_ref=b.source_ref)
    store_report_rows(db, f, report, b.rows)
    if b.confirm:
        confirm_report(db, f, report.id, 1)
    return report_detail(db, f, report)


def amend_report(db, f, report_id, b):
    report = get(db, m.SprayOpsReport, f, report_id)
    version(report, b.expected_version)
    require(report.status == 'draft', 'report_frozen', '已确认实绩不能直接改写，请使用冲销更正')
    check_period(db, f, report.business_date)
    payroll_day_mutable(db, f, str(b.business_date))
    previous = report_detail(db, f, report)
    ids = [row.id for row in rows(db, m.SprayOpsReportRow, f, report_id=report.id)]
    for model in (m.SprayOpsReportAllocation, m.SprayOpsLabor):
        db.execute(delete(model).where(model.factory_id == f, model.row_id.in_(ids)))
    db.execute(delete(m.SprayOpsReportRow).where(m.SprayOpsReportRow.factory_id == f, m.SprayOpsReportRow.report_id == report.id))
    report.document_no, report.business_date, report.shift, report.source_ref = b.document_no, str(b.business_date), b.shift, b.source_ref
    store_report_rows(db, f, report, b.rows)
    touch(report)
    if b.confirm:
        confirm_report(db, f, report.id, report.version)
    return {**report_detail(db, f, report), 'previous_draft': previous, 'amendment_reason': b.reason}


def store_report_rows(db, f, report, source_rows):
    for row in source_rows:
        get(db, m.SprayOpsTask, f, row.task_id)
        rr = add(db, m.SprayOpsReportRow, f, report_id=report.id, **row.model_dump(exclude={"allocations", "labor"}))
        for allocation in row.allocations:
            ta = get(db, m.SprayOpsTaskAllocation, f, allocation.task_allocation_id)
            require(ta.task_id == row.task_id, "allocation_mismatch", "分摊不属于本任务", 422)
            add(db, m.SprayOpsReportAllocation, f, row_id=rr.id, **allocation.model_dump())
        for labor in row.labor:
            employee = get(db, m.SprayOpsEmployee, f, labor.employee_id)
            require(employee.enabled, "employee_disabled", "员工已停用")
            require(labor.nonproductive_hours == 0 or labor.reason, "labor_reason", "无产值工时须填写原因", 422)
            add(db, m.SprayOpsLabor, f, row_id=rr.id, **labor.model_dump())


def confirm_report(db, f, report_id, expected):
    report = get(db, m.SprayOpsReport, f, report_id)
    version(report, expected)
    check_period(db, f, report.business_date)
    from .history import guard_date
    guard_date(db, f, report.business_date)
    payroll_day_mutable(db, f, report.business_date)
    require(report.status == "draft", "report_state", "只能确认草稿日报")
    for row in rows(db, m.SprayOpsReportRow, f, report_id=report.id):
        task = get(db, m.SprayOpsTask, f, row.task_id)
        require(task.status == "started", "task_not_started", "任务必须先开工才能报工")
        require(task.reported + row.processed <= task.quantity, "report_overflow", "报工超过任务剩余数量")
        step = get(db, m.SprayOpsStep, f, task.step_id)
        route_steps = {st.id for st in rows(db, m.SprayOpsStep, f, route_id=step.route_id)}
        for allocation in rows(db, m.SprayOpsReportAllocation, f, row_id=row.id):
            ta = get(db, m.SprayOpsTaskAllocation, f, allocation.task_allocation_id)
            stock = get(db, m.SprayOpsStock, f, ta.stock_id)
            require(ta.consumed + allocation.processed <= ta.quantity and stock.quantity >= allocation.processed and stock.reserved >= allocation.processed, "material_shortage", "报工分摊超过预留或可用库存")
            piece_quantity(allocation.processed, stock.unit)
            done = completed(db, f, stock.id)
            next_done = done | {step.id}
            ready = timestamp(datetime.now(UTC) + timedelta(minutes=step.drying_minutes))
            for state, qty, completed_ids, pending in [
                ("finished" if route_steps <= next_done else "wip", allocation.good, next_done, None),
                ("hold", allocation.hold, done, step.id),
            ]:
                if qty:
                    output_qty = qty * step.output_ratio
                    piece_quantity(output_qty, step.output_unit)
                    target = make_stock(db, f, stock.batch_id, stock.line_id, output_qty, step.output_unit, state, ready, completed_ids, pending, stock.rework_origin)
                    movement(db, f, stock, target, qty, output_qty, "production_good" if state != "hold" else "production_hold", row.id, report.business_date)
            if allocation.scrap:
                movement(db, f, stock, None, allocation.scrap, 0, "production_scrap", row.id, report.business_date, row.reason)
            stock.quantity -= allocation.processed
            stock.reserved -= allocation.processed
            ta.consumed += allocation.processed
            touch(stock)
            touch(ta)
        task.reported += row.processed
        if task.reported == task.quantity:
            task.status, task.actual_end = "completed", m.now()
        touch(task)
    report.status = "confirmed"
    touch(report)
    return report_detail(db, f, report)


def quality(db, f, stock_id, b):
    stock = get(db, m.SprayOpsStock, f, stock_id)
    version(stock, b.expected_version)
    require(stock.state == "hold", "quality_state", "只能处置待判库存")
    total = b.good + b.rework + b.scrap
    require(total > 0 and total <= stock.quantity - stock.reserved, "quality_overflow", "质量处置数量超过待判可用数量")
    for qty in (b.good, b.rework, b.scrap):
        piece_quantity(qty, stock.unit)
    done = completed(db, f, stock.id)
    rework_done = done.copy()
    if b.rework and b.rework_step_id:
        step = get(db, m.SprayOpsStep, f, b.rework_step_id)
        line = get(db, m.SprayOpsDemandLine, f, stock.line_id)
        require(step.route_id == line.route_id and step.input_unit == stock.unit and step.output_ratio == 1, "rework_route_required", "返工工序须属于原确认路线且物料单位一致")
        redo = {step.id}
        edges = rows(db, m.SprayOpsPredecessor, f)
        while True:
            expanded = redo | {edge.step_id for edge in edges if edge.predecessor_id in redo}
            if expanded == redo:
                break
            redo = expanded
        rework_done -= redo
    elif b.rework and not stock.pending_step_id and done:
        require(False, "rework_route_required", "退回成品须明确选择返工起始工序")
    good_done = done.copy()
    good_state = "white" if not done else "wip"
    if stock.pending_step_id:
        step = get(db, m.SprayOpsStep, f, stock.pending_step_id)
        good_done.add(step.id)
        route_steps = {st.id for st in rows(db, m.SprayOpsStep, f, route_id=step.route_id)}
        good_state = "finished" if route_steps <= good_done else "wip"
    elif stock.line_id:
        line = get(db, m.SprayOpsDemandLine, f, stock.line_id)
        route_steps = {st.id for st in rows(db, m.SprayOpsStep, f, route_id=line.route_id)} if line.route_id else set()
        if route_steps and route_steps <= good_done:
            good_state = "finished"
    result = []
    for state, qty, steps, origin, kind in [(good_state, b.good, good_done, stock.rework_origin, "quality_good"), ("wip" if rework_done else "white", b.rework, rework_done, stock.id, "quality_rework")]:
        if qty:
            # A failed operation with a unit conversion cannot be reversed without
            # a confirmed rework route. Do not invent an inverse material mapping.
            if kind == "quality_rework" and stock.pending_step_id:
                step = get(db, m.SprayOpsStep, f, stock.pending_step_id)
                require(step.input_unit == stock.unit and step.output_ratio == 1, "rework_route_required", "单位已转换，需建立确认的返工工艺")
            target = make_stock(db, f, stock.batch_id, stock.line_id, qty, stock.unit, state, stock.ready_at, steps, rework_origin=origin)
            movement(db, f, stock, target, qty, qty, kind, stock.id, b.business_date, b.reason)
            result.append(serialize(target))
    if b.scrap:
        movement(db, f, stock, None, b.scrap, 0, "quality_scrap", stock.id, b.business_date, b.reason)
    stock.quantity -= total
    touch(stock)
    return {**serialize(stock), "outputs": result}


def reverse_report(db, f, report_id, b):
    report = get(db, m.SprayOpsReport, f, report_id)
    version(report, b.expected_version)
    check_period(db, f, report.business_date)
    payroll_day_mutable(db, f, report.business_date)
    require(report.status == "confirmed", "report_state", "只能冲销已确认日报")
    rr = rows(db, m.SprayOpsReportRow, f, report_id=report.id)
    allocation_ids = [allocation.id for row in rr for allocation in rows(db, m.SprayOpsReportAllocation, f, row_id=row.id)]
    valued = db.scalar(scoped(db, m.SprayOpsValuation, f).where(m.SprayOpsValuation.report_allocation_id.in_(allocation_ids)))
    require(valued is None, "downstream_valuation", "日报已登记工序产值，不能直接冲销")
    moves = list(db.scalars(scoped(db, m.SprayOpsMovement, f).where(m.SprayOpsMovement.reference_id.in_([r.id for r in rr]), m.SprayOpsMovement.kind.like("production_%"))))
    for move in moves:
        if move.to_stock_id:
            target = get(db, m.SprayOpsStock, f, move.to_stock_id)
            require(target.quantity == move.output_quantity and target.reserved == 0,
                    "downstream_impact", "产出已有下游使用，不能直接冲销", conflicts=[dict(entity_id=target.id)])
    reversal = add(db, m.SprayOpsReport, f, document_no=report.document_no + "-R-" + b.operation_id[:8], business_date=str(b.business_date), shift=report.shift, status="reversal", correction_of=report.id, source_ref=b.reason)
    for move in moves:
        source = get(db, m.SprayOpsStock, f, move.from_stock_id)
        target = get(db, m.SprayOpsStock, f, move.to_stock_id) if move.to_stock_id else None
        source.quantity += move.quantity
        source.reserved += move.quantity
        touch(source)
        if target:
            target.quantity = 0
            touch(target)
        movement(db, f, target, source, move.output_quantity, move.quantity, "report_reversal", reversal.id, b.business_date, b.reason, move.id)
    for row in rr:
        task = get(db, m.SprayOpsTask, f, row.task_id)
        task.reported -= row.processed
        task.status, task.actual_end = "started", None
        touch(task)
        for allocation in rows(db, m.SprayOpsReportAllocation, f, row_id=row.id):
            ta = get(db, m.SprayOpsTaskAllocation, f, allocation.task_allocation_id)
            ta.consumed -= allocation.processed
            touch(ta)
    report.status = "reversed"
    touch(report)
    return serialize(reversal)


def payroll_day_mutable(db, f, day):
    official = db.scalar(scoped(db, m.SprayOpsPayroll, f).where(m.SprayOpsPayroll.business_date == day, m.SprayOpsPayroll.status == "confirmed"))
    require(official is None, "payroll_frozen", "该日工资已正式确认，报工变更须通过后续期间调整")
