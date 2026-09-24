from collections import defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
from app.models import uv_operations as m
from . import common as c
from .production import shift_open


def split_money(amount, weights):
    """Largest remainder in integer minor units; stable employee ID resolves ties."""
    total = sum(weights.values(), Decimal(0))
    c.require(total > 0, "missing_work_time", "缺少有效参与工时，不能计算工资", 422)
    cents = int(c.money(amount)*100)
    raw = {key: Decimal(cents)*value/total for key, value in weights.items()}
    assigned = {key: int(value.to_integral_value(rounding=ROUND_FLOOR)) for key, value in raw.items()}
    remainder = cents-sum(assigned.values())
    for key in sorted(raw, key=lambda key: (-(raw[key]-assigned[key]), key))[:remainder]:
        assigned[key] += 1
    return {key: Decimal(value)/100 for key, value in assigned.items()}


def weighted_seconds(db, target):
    result = defaultdict(Decimal)
    for employee_id in sorted({x.employee_id for x in target}):
        rows = list(db.scalars(c.query(m.UvOpsParticipation).where(m.UvOpsParticipation.employee_id == employee_id)))
        segments = []
        for row in rows:
            shift = c.get(db, m.UvOpsShift, row.shift_id)
            intervals = [(datetime.fromisoformat(row.start_at), datetime.fromisoformat(row.end_at))]
            for raw_a, raw_b in shift.breaks:
                a, b = datetime.fromisoformat(raw_a), datetime.fromisoformat(raw_b)
                next_intervals = []
                for start, end in intervals:
                    if b <= start or a >= end:
                        next_intervals.append((start, end))
                    else:
                        if start < a:
                            next_intervals.append((start, a))
                        if b < end:
                            next_intervals.append((b, end))
                intervals = next_intervals
            segments.extend((start, end, row) for start, end in intervals)
        points = sorted({point for start, end, _ in segments for point in (start, end)})
        target_ids = {x.id for x in target}
        for start, end in zip(points, points[1:]):
            active = [row for a, b, row in segments if a <= start and b >= end]
            if not active:
                continue
            seconds = Decimal(str((end-start).total_seconds())) / len(active)
            for row in active:
                if row.id in target_ids:
                    result[employee_id] += seconds * row.role_coefficient
    return dict(result)


def confirm(db, user, body):
    shift = shift_open(db, body.shift_id)
    task = c.get(db, m.UvOpsTask, body.task_id, lock=True)
    policy = task.payroll_policy_snapshot
    c.require(policy is not None, "missing_wage_policy", "任务创建时未确认工资规则，不能生成正式工资", 422)
    participants = list(db.scalars(c.query(m.UvOpsParticipation).where(m.UvOpsParticipation.shift_id == shift.id, m.UvOpsParticipation.task_id == task.id)))
    for employee in sorted({x.employee_id for x in participants}):
        db.scalar(c.query(m.UvOpsWorker).where(m.UvOpsWorker.employee_id == employee).with_for_update())
    weights = weighted_seconds(db, participants)
    entries = list(db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.shift_id == shift.id, m.UvOpsProductionEntry.task_id == task.id)))
    good = sum(x.good*x.direction for x in entries if x.final_pass)
    quality = list(db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.shift_id == shift.id, m.UvOpsQualityEntry.task_id == task.id, m.UvOpsQualityEntry.disposition == "good")))
    good += sum(x.quantity for x in quality if x.pass_index == task.process_snapshot["passes"])
    rate = Decimal(policy["rate"])
    if policy["basis"] == "piece":
        amount = rate * good
    else:
        amount = rate * sum(weights.values()) / Decimal(3600)
        if policy["basis"] == "base_bonus":
            amount += Decimal(policy["bonus_rate"]) * good
    allocations = split_money(amount, weights)
    accrual = c.add(db, m.UvOpsWageAccrual, user, task_id=task.id, shift_id=shift.id, business_date=shift.business_date, payroll_amount=c.money(amount), currency=policy["currency"], payroll_evidence=c.json_value(dict(policy=policy, final_good=good, weighted_seconds=weights)))
    rows = [c.add(db, m.UvOpsWageAllocation, user, accrual_id=accrual.id, employee_id=employee, payroll_weight_seconds=weights[employee], payroll_amount=amount) for employee, amount in allocations.items()]
    return dict(accrual=c.record(accrual), allocations=[c.record(x) for x in rows])
