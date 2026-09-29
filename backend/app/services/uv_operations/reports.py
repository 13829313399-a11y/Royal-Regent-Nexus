from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from math import floor
from copy import deepcopy
from sqlalchemy import func, select
from app.models import uv_operations as m
from . import common as c


def quote(body):
    boards = body.available_seconds / body.cycle_seconds
    quantity = floor(boards) * body.pieces_per_board
    c.require(quantity > 0, "zero_capacity", "可用时间不足一整板，不能生成有效单件报价", 422)
    theoretical_quantity = boards * body.pieces_per_board
    unit = body.cost_amount / theoretical_quantity
    if body.pricing_mode == "margin":
        c.require(body.ratio < 1, "invalid_margin", "目标毛利率必须小于 100%", 422)
        price = unit / (1-body.ratio)
    else:
        price = unit * (1+body.ratio)
    return c.json_value(dict(theoretical_boards=boards, theoretical_quantity=theoretical_quantity, whole_boards=floor(boards), quantity=quantity, cost_unit=unit, achievable_cost_unit=body.cost_amount/quantity, cost_amount=body.cost_amount, quoted_unit_rate=price.quantize(Decimal("0.000001")), currency=body.currency, pricing_mode=body.pricing_mode, ratio=body.ratio))


def expense(db, user, body):
    start = date.fromisoformat(body.business_date)
    end = date.fromisoformat(body.allocation_end) if body.allocation_end else start
    c.require(start <= end and (end-start).days <= 366, "allocation_dates", "费用分摊区间需为不超过 366 天的有效日期", 422)
    if body.category == "direct":
        c.require(body.task_id is not None, "task_required", "直接费用需关联任务", 422)
    if body.task_id:
        c.get(db, m.UvOpsTask, body.task_id)
    for month in sorted({(start+timedelta(days=i)).strftime("%Y-%m") for i in range((end-start).days+1)}):
        c.lock_period(db, month+"-01")
    if body.task_id:
        task=c.get(db,m.UvOpsTask,body.task_id,lock=True)
        c.require(task.status!='cancelled','task_cancelled','不能对已取消任务登记费用')
    return c.record(c.add(db, m.UvOpsExpense, user, **c.values(body)))


def run_cost(db,user,body):
    from .payroll import split_money
    c.lock_period(db,body.business_date)
    allocations=list(db.scalars(c.query(m.UvOpsRunAllocation).where(m.UvOpsRunAllocation.run_id==body.run_id)))
    for key in sorted({x.task_id for x in allocations}): c.get(db,m.UvOpsTask,key,lock=True)
    run=c.get(db,m.UvOpsRun,body.run_id,lock=True,version=body.expected_version)
    c.require(run.match_evidence is not None,'run_unmatched','请先核对运行的拼版分配',422)
    c.require(db.scalar(c.query(m.UvOpsRunCost).where(m.UvOpsRunCost.run_id==run.id)) is None,'run_cost_exists','本次运行已有一份成本分配，不能重复计入')
    allocations=list(db.scalars(c.query(m.UvOpsRunAllocation).where(m.UvOpsRunAllocation.run_id==run.id)))
    pieces=split_money(body.cost_amount,{row.id:row.share for row in allocations})
    rows=[]
    for allocation in allocations:
        entry=c.add(db,m.UvOpsExpense,user,category='direct',task_id=allocation.task_id,business_date=body.business_date,cost_amount=pieces[allocation.id],currency=body.currency,evidence=body.evidence)
        rows.append(dict(allocation_id=allocation.id,expense_id=entry.id,task_id=allocation.task_id,share=str(allocation.share),cost_amount=str(pieces[allocation.id])))
    receipt=c.add(db,m.UvOpsRunCost,user,**c.values(body),cost_allocations=rows)
    return c.record(receipt)


def daily_allocation(amount, start, end):
    days = (end-start).days+1
    cents = int(c.money(amount)*100)
    each = cents//days
    return {str(start+timedelta(days=i)): Decimal(each if i < days-1 else cents-each*(days-1))/100 for i in range(days)}


def revenue(task, good):
    price = task.cost_price_snapshot
    if price is None:
        return None
    quantity = Decimal(good)
    if price["basis"] == "area":
        process = task.process_snapshot
        area = Decimal(price["measured_area_m2"]) if price["measured_area_m2"] is not None else Decimal(process["width_mm"])*Decimal(process["height_mm"])*process["faces"]/Decimal(1_000_000)
        quantity *= area
    return quantity*Decimal(price["rate"])


def report(db, start_date, end_date, *, frozen=True):
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    c.require(start <= end and (end-start).days <= 366, "report_window", "请选择不超过 366 天的日期区间", 422)
    if frozen and start.day == 1 and (end+timedelta(days=1)).day == 1 and start.strftime('%Y-%m') == end.strftime('%Y-%m'):
        period = db.scalar(c.query(m.UvOpsPeriod).where(m.UvOpsPeriod.period == start.strftime('%Y-%m'), m.UvOpsPeriod.status == 'closed'))
        snapshot = db.scalar(c.query(m.UvOpsReportSnapshot).where(m.UvOpsReportSnapshot.period_id == period.id).order_by(m.UvOpsReportSnapshot.created_at.desc())) if period else None
        if snapshot:
            return deepcopy(snapshot.report) | dict(report_basis='closed_snapshot',snapshot_id=snapshot.id,ledger_revision=snapshot.ledger_revision)
    entries = list(db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.business_date.between(start_date, end_date))))
    quality = list(db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.business_date.between(start_date, end_date))))
    tasks = {x.id: x for x in db.scalars(c.query(m.UvOpsTask))}
    batches = {x.id: x for x in db.scalars(c.query(m.UvOpsBatch))}
    by_task = defaultdict(lambda: dict(processed=0, good=0, scrap=0, pending=0, rework=0))
    for entry in entries:
        original = tasks[entry.task_id].parent_task_id or entry.task_id
        row = by_task[original]
        row["processed"] += entry.processed*entry.direction
        row["good"] += entry.good*entry.direction if entry.final_pass else 0
        row["scrap"] += entry.scrap*entry.direction
        row["pending"] += entry.pending*entry.direction
        row["rework"] += entry.rework*entry.direction
        if entry.source_bucket == "rework":
            row["rework"] -= entry.processed*entry.direction
    for entry in quality:
        task = tasks[batches[entry.batch_id].task_id]
        row = by_task[task.id]
        row["pending"] -= entry.quantity
        if entry.disposition != "good" or entry.pass_index == task.process_snapshot["passes"]:
            row[entry.disposition] += entry.quantity
    currencies = defaultdict(lambda: dict(cost_revenue=Decimal(0), cost_amount=Decimal(0), payroll_total=Decimal(0)))
    missing = []
    details = []
    for task_id, row in by_task.items():
        task = tasks[task_id]
        value = revenue(task, row["good"])
        if value is None:
            missing.append(dict(task_id=task.id, code="missing_price"))
        else:
            currencies[task.cost_price_snapshot["currency"]]["cost_revenue"] += value
        details.append(dict(task_id=task_id, task_code=task.code, product=task.product_snapshot, **row, cost_revenue=value, currency=task.cost_price_snapshot['currency'] if task.cost_price_snapshot else None, price_policy_id=task.price_policy_id))
    cost_covered_tasks = set()
    for item in db.scalars(c.query(m.UvOpsExpense).where(m.UvOpsExpense.business_date <= end_date)):
        if item.category == "investment":
            continue
        allocations = daily_allocation(item.cost_amount, date.fromisoformat(item.business_date), date.fromisoformat(item.allocation_end or item.business_date))
        currencies[item.currency]["cost_amount"] += sum((value for key, value in allocations.items() if start_date <= key <= end_date), Decimal(0))
        if item.task_id and any(start_date <= key <= end_date for key in allocations):
            cost_covered_tasks.add(tasks[item.task_id].parent_task_id or item.task_id)
    for entry in db.scalars(c.query(m.UvOpsInkMovement).where(m.UvOpsInkMovement.business_date.between(start_date, end_date))):
        if entry.kind in {"consume", "stocktake_out"}:
            currencies[entry.currency]["cost_amount"] += entry.cost_value
            if entry.task_id:
                cost_covered_tasks.add(tasks[entry.task_id].parent_task_id or entry.task_id)
        elif entry.kind in {"reverse", "return"}:
            original = c.get(db, m.UvOpsInkMovement, entry.reversal_of)
            if original.kind in {"consume", "stocktake_out"}:
                currencies[entry.currency]["cost_amount"] -= entry.cost_value
    for entry in db.scalars(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.business_date.between(start_date, end_date))):
        currencies[entry.currency]["payroll_total"] += entry.payroll_amount
    paid = {(x.task_id, x.shift_id) for x in db.scalars(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.business_date.between(start_date, end_date)))}
    earning_pairs = {(x.task_id, x.shift_id) for x in entries} | {(x.task_id, x.shift_id) for x in quality if x.disposition == "good"}
    for task_id, shift_id in sorted(earning_pairs-paid):
        missing.append(dict(task_id=task_id, shift_id=shift_id, code="missing_payroll"))
    unmatched = db.scalar(select(func.count()).select_from(m.UvOpsRun).where(m.UvOpsRun.match_evidence.is_(None), m.UvOpsRun.started_at >= c.ts(start_date+"T00:00:00+08:00"), m.UvOpsRun.started_at < c.ts(str(end+timedelta(days=1))+"T00:00:00+08:00")))
    for task_id in by_task:
        if task_id not in cost_covered_tasks:
            missing.append(dict(task_id=task_id, code="missing_cost_evidence"))
    # Balance fields include opening facts, so next-day quality never shows a
    # negative pending quantity. Good/processed/scrap remain period flows.
    balances = defaultdict(lambda: dict(pending=0, rework=0))
    for entry in db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.business_date <= end_date)):
        key = tasks[entry.task_id].parent_task_id or entry.task_id
        balances[key]["pending"] += entry.pending*entry.direction
        balances[key]["rework"] += (entry.rework-(entry.processed if entry.source_bucket == "rework" else 0))*entry.direction
    for entry in db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.business_date <= end_date)):
        key = batches[entry.batch_id].task_id
        balances[key]["pending"] -= entry.quantity
        if entry.disposition == "rework":
            balances[key]["rework"] += entry.quantity
    for key in by_task:
        by_task[key].update(balances[key])
    for row in details:
        row.update(balances[row["task_id"]])
    pending = sum(x["pending"] for x in balances.values())
    totals = {key: sum(x[key] for x in by_task.values()) for key in ("processed", "good", "scrap", "pending", "rework")}
    denominator = totals["good"]+totals["scrap"]
    for currency in currencies.values():
        currency["cost_total"] = None if missing else c.money(currency["cost_amount"]+currency["payroll_total"])
        currency["cost_margin"] = None if missing or currency["cost_revenue"] == 0 else (currency["cost_revenue"]-currency["cost_total"])/currency["cost_revenue"]
        for field in ('cost_revenue','cost_amount','payroll_total'):
            currency[field] = c.money(currency[field])
    return c.json_value(dict(start_date=start_date, end_date=end_date, totals=totals, yield_ratio=None if denominator == 0 else Decimal(totals["good"])/denominator, details=details, cost_by_currency=currencies, cost_missing=missing, coverage=dict(state="complete" if not missing and not pending and not unmatched and len(currencies) <= 1 else "partial", unmatched_runs=unmatched, unconfirmed_output=pending, missing_cost_records=len(missing)), warnings=["多币种分列，未提供汇率快照，不生成跨币种合计"] if len(currencies)>1 else []))


def close(db, user, period, body):
    first = date.fromisoformat(period+"-01")
    end = (first.replace(day=28)+timedelta(days=4)).replace(day=1)-timedelta(days=1)
    row = c.lock_period(db, str(first), closing=True)
    c.require(row.status == "open" and row.version == body.expected_version, "period_conflict", "账期状态或版本已变化", version=row.version)
    value = report(db, str(first), str(end))
    open_shifts = db.scalar(select(func.count()).select_from(m.UvOpsShift).where(m.UvOpsShift.business_date.between(str(first), str(end)), m.UvOpsShift.status != "closed"))
    late = db.scalar(select(func.count()).select_from(m.UvOpsAgentEventInbox).where(m.UvOpsAgentEventInbox.late_closed_period.is_(True),m.UvOpsAgentEventInbox.resolved_by.is_(None),m.UvOpsAgentEventInbox.observed_at>=c.ts(str(first)+'T00:00:00+08:00'),m.UvOpsAgentEventInbox.observed_at<c.ts(str(end+timedelta(days=1))+'T00:00:00+08:00')))
    c.require(not late,'late_evidence_unresolved','本月仍有未核对的封账后迟到证据，请先记录核对结论')
    c.require(not open_shifts and value["coverage"]["state"] == "complete", "close_incomplete", "账期仍有未结班、未匹配运行、待检或缺价/成本/工资记录，不能封账")
    row.status = "closed"
    row.close_reason = body.reason or "核对完成"
    c.touch(row)
    snapshot = c.add(db, m.UvOpsReportSnapshot, user, period_id=row.id, report=value, ledger_revision=str(c.revision(db)))
    return dict(period=c.record(row), snapshot=c.record(snapshot))


def reopen(db, user, period, body):
    row = c.lock_period(db, period+"-01", closing=True)
    c.require(row.status == "closed" and row.version == body.expected_version, "period_conflict", "账期状态或版本已变化", version=row.version)
    c.require(len(body.reason.strip()) >= 5, "reason_required", "重开账期必须说明具体理由", 422)
    row.status = "open"
    c.touch(row)
    return c.record(row)
