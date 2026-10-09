"""Deterministic finite-capacity proposals; previews never reserve inventory."""
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_DOWN
from collections import defaultdict

from sqlalchemy import select

from app.models import spray_ops as m
from .common import DomainError, add, get, scoped, serialize, require, version, touch, timestamp, json_value, check_period
from .production import rows, readiness, completed, task_detail, piece_quantity


def environment(db, f, replace_ids):
    resources = {r.id: r for r in rows(db, m.SprayOpsResource, f)}
    steps = {step.id: step for step in rows(db, m.SprayOpsStep, f)}
    windows = rows(db, m.SprayOpsCalendar, f)
    capabilities = rows(db, m.SprayOpsCapability, f)
    tasks = list(db.scalars(scoped(db, m.SprayOpsTask, f).where(m.SprayOpsTask.status.in_(["planned", "started", "paused"])) ))
    replace = [get(db, m.SprayOpsTask, f, task_id) for task_id in replace_ids]
    require(all(task.status == "planned" and task.reported == 0 for task in replace), "frozen_task", "已开工任务不能被重排")
    credits = {}
    for task in replace:
        for allocation in rows(db, m.SprayOpsTaskAllocation, f, task_id=task.id):
            credits[allocation.stock_id] = credits.get(allocation.stock_id, Decimal(0)) + allocation.quantity
    occupancy = []
    for plan in rows(db, m.SprayOpsForecast, f, status="conditional"):
        step = steps[plan.step_id]
        for resource_id in {plan.resource_id, step.tool_id, step.crew_id} - {None}:
            occupancy.append((resource_id, plan.start_at, plan.end_at, plan.id))
    for task in tasks:
        if task.id in replace_ids:
            continue
        step = steps[task.step_id]
        for resource_id in {task.resource_id, step.tool_id, step.crew_id} - {None}:
            # Actual work has no inferred completion. Pauses retain occupancy.
            occupancy.append((resource_id, task.start_at, task.end_at if task.status == "planned" else "9999-12-31T00:00:00+00:00", task.id))
    return resources, steps, windows, capabilities, occupancy, credits


def create_forecast(db, f, b):
    require(b.expected_version == 0, "version_conflict", "新条件计划版本应为 0")
    resources, steps, windows, capabilities, occupancy, _ = environment(db, f, [])
    line = get(db, m.SprayOpsDemandLine, f, b.line_id)
    demand = get(db, m.SprayOpsDemand, f, line.demand_id)
    step = get(db, m.SprayOpsStep, f, b.step_id)
    require(demand.status == "confirmed" and step.route_id == line.route_id, "forecast_route", "需求及工艺版本须明确确认")
    require(get(db, m.SprayOpsRoute, f, line.route_id).status == "confirmed", "route_unconfirmed", "工艺须确认")
    require(b.start_at >= b.expected_ready_at and b.end_at > b.start_at, "forecast_interval", "条件计划开始不能早于预计齐备时间", 422)
    require(b.end_at - b.start_at <= timedelta(days=31), "forecast_interval", "计划窗口不能超过 31 天", 422)
    piece_quantity(b.quantity, step.input_unit)
    previous = sum(plan.quantity for plan in rows(db, m.SprayOpsForecast, f, line_id=line.id, step_id=step.id, status="conditional"))
    require(previous + b.quantity <= line.quantity, "forecast_quantity", "条件计划累计数量超过需求")
    cap = next((cap for cap in capabilities if cap.resource_id == b.resource_id and cap.capability == step.capability), None)
    require(cap and cap.hourly_capacity and cap.evidence, "resource_capability_missing", "资源产能须有确认依据")
    seconds = Decimal(str((b.end_at - b.start_at).total_seconds()))
    require(seconds * cap.hourly_capacity >= b.quantity * 3600, "capacity_exhausted", "条件计划时长不足")
    a, z = timestamp(b.start_at), timestamp(b.end_at)
    for rid in {b.resource_id, step.tool_id, step.crew_id} - {None}:
        require(rid in resources, "not_found", "工厂资源不存在", 404)
        check_window(resources[rid], windows, a, z, occupancy)
    check_period(db, f, (b.start_at + timedelta(hours=8)).date())
    plan = add(db, m.SprayOpsForecast, f, **{key:value for key,value in b.model_dump().items() if key not in {"factory_id", "operation_id", "expected_version", "start_at", "end_at", "expected_ready_at"}}, start_at=a,end_at=z,expected_ready_at=timestamp(b.expected_ready_at))
    return serialize(plan)


def convert_forecast(db, f, plan_id, b, gate):
    from . import schemas as s
    plan = get(db, m.SprayOpsForecast, f, plan_id)
    version(plan, b.expected_version)
    require(plan.status == "conditional", "forecast_state", "只能兑现未处理的条件计划")
    require(sum(a.quantity for a in b.allocations) == plan.quantity, "forecast_quantity", "实际批次分配必须等于条件计划数量")
    for allocation in b.allocations:
        require(get(db, m.SprayOpsStock, f, allocation.stock_id).line_id == plan.line_id, "allocation_mismatch", "实际批次不属于条件计划订单")
    plan.status = "converting"
    db.flush()
    candidate = dict(step_id=plan.step_id,resource_id=plan.resource_id,start_at=plan.start_at,end_at=plan.end_at,allocations=[a.model_dump(mode="json") for a in b.allocations],note=plan.condition)
    preview_body=s.PlanPreview(factory_id=f,operation_id=b.operation_id,expected_version=0,label="兑现条件计划",start_at=plan.start_at,end_at=plan.end_at,tasks=[candidate])
    scenario=preview(db,f,preview_body,gate)
    published=publish(db,f,scenario['id'],s.PlanPublish(factory_id=f,operation_id=b.operation_id,expected_version=scenario['version'],base_revision=gate.revision),gate)
    plan.status,plan.task_id="converted",published['tasks'][0]['id']
    touch(plan)
    return {**serialize(plan),"task":published['tasks'][0]}


def cancel_forecast(db, f, plan_id, b):
    plan=get(db,m.SprayOpsForecast,f,plan_id)
    version(plan,b.expected_version)
    require(plan.status=="conditional","forecast_state","条件计划已处理")
    check_period(db,f,(datetime.fromisoformat(plan.start_at)+timedelta(hours=8)).date())
    plan.status="cancelled"
    plan.condition += "\n取消："+b.reason
    touch(plan)
    return serialize(plan)


def check_window(resource, windows, start, end, occupancy):
    require(resource.enabled, "resource_disabled", "资源已停用")
    matching = [w for w in windows if w.resource_id == resource.id]
    covered = start
    for window in sorted((w for w in matching if w.kind == "available"), key=lambda w: w.start_at):
        if window.start_at <= covered:
            covered = max(covered, window.end_at)
    require(covered >= end, "capacity_exhausted", "任务超出已确认工作日历")
    require(not any(w.kind != "available" and w.start_at < end and w.end_at > start for w in matching), "resource_unavailable", "时间段存在停机或缺勤")
    points = [(start, 1), (end, -1)]
    for resource_id, a, b, _ in occupancy:
        if resource_id == resource.id and a < end and b > start:
            points.extend([(max(start, a), 1), (min(end, b), -1)])
    active = 0
    for _, change in sorted(points, key=lambda p: (p[0], p[1])):
        active += change
        require(active <= resource.capacity, "resource_conflict", "资源、人员或工具在该时间段的并发容量不足", conflicts=[dict(entity_id=resource.id, start_at=start, end_at=end)])


def validate_tasks(db, f, candidates, replace_ids=(), *, allow_started=False):
    require(len(replace_ids) == len(set(replace_ids)), "duplicate_task", "不能重复选择重排任务", 422)
    resources, steps, windows, capabilities, occupancy, credits = environment(db, f, replace_ids)
    used_stock = {}
    for candidate in candidates:
        step = steps.get(candidate["step_id"])
        require(step is not None, "not_found", "当前工厂工序不存在", 404)
        resource = resources.get(candidate["resource_id"])
        require(resource is not None, "not_found", "当前工厂资源不存在", 404)
        start, end = timestamp(candidate["start_at"]), timestamp(candidate["end_at"])
        require(end > start, "invalid_interval", "结束时间必须晚于开始", 422)
        capability = next((c for c in capabilities if c.resource_id == resource.id and c.capability == step.capability), None)
        require(capability and capability.hourly_capacity and capability.evidence, "resource_capability_missing", "资源没有该工序的已确认产能")
        quantity = Decimal(0)
        identity = None
        seen = set()
        for allocation in candidate["allocations"]:
            require(allocation["stock_id"] not in seen, "duplicate_allocation", "同一任务不能重复分摊批次", 422)
            seen.add(allocation["stock_id"])
            stock = get(db, m.SprayOpsStock, f, allocation["stock_id"])
            qty = Decimal(allocation["quantity"])
            require(qty.is_finite() and qty > 0, "invalid_quantity", "计划数量必须为正数", 422)
            piece_quantity(qty, stock.unit)
            line, _ = readiness(db, f, stock, step, start)
            demand = get(db, m.SprayOpsDemand, f, line.demand_id)
            require(demand.status in {"confirmed", "in_progress"}, "demand_not_confirmed", "订单不可排期")
            current_identity = (line.item_no, line.part, line.color, line.route_id, stock.unit)
            require(identity is None or identity == current_identity, "merge_mismatch", "合并任务须同货号、部位、颜色、工艺和单位", 422)
            identity = current_identity
            require(line.split_allowed or qty == line.quantity, "split_not_allowed", "订单未允许分批加工")
            used_stock[stock.id] = used_stock.get(stock.id, Decimal(0)) + qty
            require(used_stock[stock.id] <= stock.quantity - stock.reserved + credits.get(stock.id, 0), "material_shortage", "方案中的累计预留超过可用来料", conflicts=[dict(entity_id=stock.id)])
            quantity += qty
        require(quantity >= step.transfer_min, "transfer_minimum", "计划数量低于工序最小转序量")
        seconds = Decimal(str((datetime.fromisoformat(end) - datetime.fromisoformat(start)).total_seconds()))
        require(seconds * capability.hourly_capacity >= quantity * 3600, "capacity_exhausted", "计划时长短于已确认产能所需时间")
        for resource_id in {resource.id, step.tool_id, step.crew_id} - {None}:
            auxiliary = resources.get(resource_id)
            require(auxiliary is not None, "tool_unavailable", "缺少工序所需工具或人员")
            check_window(auxiliary, windows, start, end, occupancy)
            occupancy.append((resource_id, start, end, "proposal"))
    return candidates


def _free_intervals(resource, windows, occupancy, start, end):
    """Sweep confirmed calendars and concurrent reservations once per resource."""
    if not resource.enabled:
        return []
    changes = defaultdict(lambda: [0, 0, 0])
    changes[start]; changes[end]
    for window in windows:
        a, z = max(start, window.start_at), min(end, window.end_at)
        if a < z:
            index = 0 if window.kind == "available" else 1
            changes[a][index] += 1
            changes[z][index] -= 1
    for a, z in occupancy:
        a, z = max(start, a), min(end, z)
        if a < z:
            changes[a][2] += 1
            changes[z][2] -= 1
    counts, result, previous = [0, 0, 0], [], None
    for at, change in sorted(changes.items()):
        if previous is not None and previous < at and counts[0] and not counts[1] and counts[2] < resource.capacity:
            if result and result[-1][1] == previous:
                result[-1] = (result[-1][0], at)
            else:
                result.append((previous, at))
        counts = [value + delta for value, delta in zip(counts, change)]
        previous = at
    return result


def _intersect(left, right):
    result, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        a, z = max(left[i][0], right[j][0]), min(left[i][1], right[j][1])
        if a < z:
            result.append((a, z))
        if left[i][1] <= right[j][1]:
            i += 1
        else:
            j += 1
    return result


def propose(db, f, b):
    start, end = timestamp(b.start_at), timestamp(b.end_at)
    require(end > start and b.end_at - b.start_at <= timedelta(days=31), "planning_window", "排期窗口须大于 0 且不超过 31 天", 422)
    resources, steps, windows, capabilities, occupancy, credits = environment(db, f, b.replace_task_ids)
    lines_query = scoped(db, m.SprayOpsDemandLine, f)
    if b.line_ids:
        for line_id in b.line_ids:
            get(db, m.SprayOpsDemandLine, f, line_id)
        lines_query = lines_query.where(m.SprayOpsDemandLine.id.in_(b.line_ids))
    lines = list(db.scalars(lines_query.order_by(m.SprayOpsDemandLine.priority.desc(), m.SprayOpsDemandLine.due_date, m.SprayOpsDemandLine.id)))
    stocks = list(db.scalars(scoped(db, m.SprayOpsStock, f).where(m.SprayOpsStock.quantity > 0, m.SprayOpsStock.state.in_(["white", "wip"]), m.SprayOpsStock.line_id.in_([line.id for line in lines])).order_by(m.SprayOpsStock.ready_at, m.SprayOpsStock.id)))
    # All business references are prefetched. Candidate exploration performs no
    # repeated SQL and never revalidates the entire growing proposal per slot.
    routes = {r.id: r for r in rows(db, m.SprayOpsRoute, f)}
    demands = {d.id: d for d in rows(db, m.SprayOpsDemand, f)}
    done_by_stock, predecessors, stock_by_line = defaultdict(set), defaultdict(set), defaultdict(list)
    for edge in rows(db, m.SprayOpsCompletedStep, f):
        done_by_stock[edge.stock_id].add(edge.step_id)
    for edge in rows(db, m.SprayOpsPredecessor, f):
        predecessors[edge.step_id].add(edge.predecessor_id)
    for stock in stocks:
        stock_by_line[stock.line_id].append(stock)
    preparations = {(p.batch_id, p.step_id): p for p in rows(db, m.SprayOpsPreparation, f)}
    windows_by_resource, busy_by_resource = defaultdict(list), defaultdict(list)
    for window in windows:
        windows_by_resource[window.resource_id].append(window)
    for rid, a, z, _ in occupancy:
        busy_by_resource[rid].append((a, z))
    cache = {}
    def free(rid):
        if rid not in cache:
            cache[rid] = _free_intervals(resources[rid], windows_by_resource[rid], busy_by_resource[rid], start, end) if rid in resources else []
        return cache[rid]
    caps = sorted(capabilities, key=lambda c: (resources[c.resource_id].code, c.id))
    proposals, unplanned = [], []
    for line in lines:
        route = routes.get(line.route_id)
        if not route or route.status != "confirmed" or demands[line.demand_id].status not in {"confirmed", "in_progress"}:
            unplanned.append(dict(line_id=line.id, code="route_unconfirmed", message="工艺未确认"))
            continue
        material = [stock for stock in stock_by_line[line.id] if stock.quantity - stock.reserved + credits.get(stock.id, 0) > 0]
        if not material:
            unplanned.append(dict(line_id=line.id, code="material_shortage", message="当前没有可分配的合格来料"))
            continue
        for stock in material:
            done = done_by_stock[stock.id]
            candidates = [step for step in steps.values() if step.route_id == line.route_id and step.id not in done and predecessors[step.id] <= done and step.input_unit == stock.unit]
            if not candidates:
                unplanned.append(dict(line_id=line.id, stock_id=stock.id, code="predecessor_not_ready", message="没有可推进的工序"))
                continue
            # One physical lot cannot be cloned to both DAG branches. Plan its next
            # ready operation; later proposals use the actual resulting state set.
            step = sorted(candidates, key=lambda st: (st.code, st.id))[0]
            remaining = stock.quantity - stock.reserved + credits.get(stock.id, 0)
            prep = preparations.get((stock.batch_id, step.id))
            usable = [c for c in caps if c.capability == step.capability and c.hourly_capacity and c.evidence]
            code = "capacity_exhausted" if usable else "resource_capability_missing"
            if step.prep_required and (prep is None or prep.expires_at and prep.expires_at < max(start, stock.ready_at, prep.ready_at)):
                code = "preparation_not_ready"
            elif not line.split_allowed and remaining != line.quantity:
                code = "split_not_allowed"
            else:
                while remaining > 0:
                    possible = []
                    for cap in usable:
                        intervals = free(cap.resource_id)
                        for rid in {step.tool_id, step.crew_id} - {None, cap.resource_id}:
                            intervals = _intersect(intervals, free(rid))
                        for a, z in intervals:
                            at = max(a, stock.ready_at, prep.ready_at if prep else a)
                            if at >= z or step.prep_required and prep.expires_at and at > prep.expires_at:
                                continue
                            capacity = Decimal(str((datetime.fromisoformat(z)-datetime.fromisoformat(at)).total_seconds())) * cap.hourly_capacity / 3600
                            quantum = Decimal(1) if stock.unit in {"件", "个", "套", "只", "PCS", "pcs"} else Decimal("0.000001")
                            qty = min(remaining, capacity.quantize(quantum, rounding=ROUND_DOWN))
                            if qty <= 0 or qty < step.transfer_min or not line.split_allowed and qty != remaining:
                                continue
                            seconds = int((qty / cap.hourly_capacity * 3600).to_integral_value(rounding=ROUND_CEILING))
                            until = timestamp(datetime.fromisoformat(at) + timedelta(seconds=seconds))
                            if until > z:
                                continue
                            possible.append(dict(step_id=step.id, resource_id=cap.resource_id, start_at=at, end_at=until, allocations=[dict(stock_id=stock.id, quantity=str(qty))], note="按优先级、交期、准备时间和稳定编号排序；按允许的批次跨班次安排"))
                            break
                    if not possible:
                        break
                    chosen = min(possible, key=lambda c: (c["end_at"], c["start_at"], resources[c["resource_id"]].code))
                    proposals.append(chosen)
                    remaining -= Decimal(chosen["allocations"][0]["quantity"])
                    for rid in {chosen["resource_id"], step.tool_id, step.crew_id} - {None}:
                        busy_by_resource[rid].append((chosen["start_at"], chosen["end_at"]))
                        cache.pop(rid, None)
            if remaining:
                messages = {"preparation_not_ready": "准备未完成或已失效", "capacity_exhausted": "窗口内剩余产能不足", "resource_capability_missing": "尚未登记已确认工序产能", "split_not_allowed": "订单禁止拆分且实际来料未齐"}
                unplanned.append(dict(line_id=line.id, stock_id=stock.id, quantity=str(remaining), code=code, message=messages[code]))
    return proposals, unplanned


def preview(db, f, b, gate):
    require(b.expected_version == 0, "version_conflict", "新方案版本应为 0")
    if b.tasks is None:
        candidates, unplanned = propose(db, f, b)
    else:
        candidates = [json_value(task.model_dump()) for task in b.tasks]
        validate_tasks(db, f, candidates, b.replace_task_ids)
        unplanned = []
    # Snapshot the before and after under the same factory lock. Publishing only
    # touches the explicit replacement subset, never the entire schedule.
    original = [task_detail(db, f, get(db, m.SprayOpsTask, f, task_id)) for task_id in b.replace_task_ids]
    scenario = add(db, m.SprayOpsScenario, f, label=b.label, base_revision=gate.revision,
                   snapshot=dict(tasks=candidates, unplanned=unplanned, replace_task_ids=b.replace_task_ids, original=original, start_at=timestamp(b.start_at), end_at=timestamp(b.end_at)))
    return serialize(scenario)


def publish(db, f, scenario_id, b, gate):
    scenario = get(db, m.SprayOpsScenario, f, scenario_id)
    version(scenario, b.expected_version)
    require(scenario.status == "draft", "scenario_state", "方案已经发布")
    require(b.base_revision == scenario.base_revision == gate.revision, "stale_scenario", "排期依据已变更，请重新预览比较", conflicts=[dict(expected=scenario.base_revision, actual=gate.revision)])
    candidates, replace_ids = scenario.snapshot["tasks"], scenario.snapshot["replace_task_ids"]
    require(candidates or replace_ids, "empty_scenario", "没有可发布的排期变更", 422)
    validate_tasks(db, f, candidates, replace_ids)
    for task_id in replace_ids:
        old = get(db, m.SprayOpsTask, f, task_id)
        check_period(db, f, (datetime.fromisoformat(old.start_at) + timedelta(hours=8)).date())
        for allocation in rows(db, m.SprayOpsTaskAllocation, f, task_id=old.id):
            stock = get(db, m.SprayOpsStock, f, allocation.stock_id)
            stock.reserved -= allocation.quantity
            touch(stock)
        old.status = "cancelled"
        touch(old)
    created = []
    for candidate in candidates:
        check_period(db, f, (datetime.fromisoformat(candidate["start_at"]) + timedelta(hours=8)).date())
        qty = sum(Decimal(a["quantity"]) for a in candidate["allocations"])
        task = add(db, m.SprayOpsTask, f, scenario_id=scenario.id, step_id=candidate["step_id"], resource_id=candidate["resource_id"], start_at=timestamp(candidate["start_at"]), end_at=timestamp(candidate["end_at"]), quantity=qty, note=candidate.get("note", ""))
        for allocation in candidate["allocations"]:
            stock = get(db, m.SprayOpsStock, f, allocation["stock_id"])
            stock.reserved += Decimal(allocation["quantity"])
            touch(stock)
            add(db, m.SprayOpsTaskAllocation, f, task_id=task.id, stock_id=stock.id, line_id=stock.line_id, quantity=Decimal(allocation["quantity"]))
        created.append(task_detail(db, f, task))
    scenario.status = "published"
    touch(scenario)
    return {**serialize(scenario), "tasks": created}
