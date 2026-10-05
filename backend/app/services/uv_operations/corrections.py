"""Voiding preserves original facts and adds a reasoned, immutable receipt."""
from datetime import date, timedelta
from sqlalchemy import select
from app.models import uv_operations as m
from . import common as c, production as p

MODELS = dict(quality=m.UvOpsQualityEntry, expense=m.UvOpsExpense,
              wage=m.UvOpsWageAccrual, run_cost=m.UvOpsRunCost, participation=m.UvOpsParticipation)


def void(db, user, kind, row, reason, business_date):
    c.require(row.active_key == 1, 'already_reversed', '凭证已撤销，请刷新查看原始记录')
    row.active_key = None
    c.touch(row)
    return c.add(db, m.UvOpsReversal, user, kind=kind, entity_id=row.id, business_date=business_date, reason=reason)


def reverse(db, user, entity_id, body, kind):
    c.require(len(body.reason.strip()) >= 5, 'reason_required', '撤销需说明具体纠错理由', 422)
    model = MODELS[kind]
    source = c.get(db, model, entity_id)
    if kind in {'wage', 'quality', 'participation'}:
        shift = p.shift_open(db, source.shift_id)
        day = shift.business_date
    else:
        day = source.business_date
        start, end = date.fromisoformat(day), date.fromisoformat(getattr(source, 'allocation_end', None) or day)
        for month in sorted({(start+timedelta(days=i)).strftime('%Y-%m') for i in range((end-start).days+1)}):
            c.lock_period(db, month+'-01')
    if kind == 'run_cost':
        c.get(db, m.UvOpsRun, source.run_id, lock=True)
    elif getattr(source, 'task_id', None):
        task = c.get(db, m.UvOpsTask, source.task_id)
        tasks = {key: c.get(db, m.UvOpsTask, key, lock=True) for key in sorted({task.id, task.parent_task_id}-{None})}
    row = c.get(db, model, entity_id, lock=True, version=body.expected_version)
    c.require(row.active_key == 1, 'already_reversed', '凭证已撤销')
    if kind == 'wage':
        participants = list(db.scalars(c.query(m.UvOpsParticipation).where(m.UvOpsParticipation.task_id == row.task_id, m.UvOpsParticipation.shift_id == row.shift_id)))
        for employee in sorted({x.employee_id for x in participants}):
            db.scalar(c.query(m.UvOpsWorker).where(m.UvOpsWorker.employee_id == employee).with_for_update())
    if kind in {'quality', 'participation'}:
        c.require(db.scalar(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.task_id == row.task_id, m.UvOpsWageAccrual.shift_id == row.shift_id)) is None, 'payroll_frozen', '请先撤销受影响的工资核准')
    if kind == 'participation':
        db.scalar(c.query(m.UvOpsWorker).where(m.UvOpsWorker.employee_id == row.employee_id).with_for_update())
        paid = db.scalar(select(m.UvOpsWageAccrual.id).join(m.UvOpsParticipation, (m.UvOpsParticipation.task_id == m.UvOpsWageAccrual.task_id) & (m.UvOpsParticipation.shift_id == m.UvOpsWageAccrual.shift_id)).where(m.UvOpsWageAccrual.active_key == 1, m.UvOpsParticipation.active_key == 1, m.UvOpsParticipation.employee_id == row.employee_id, m.UvOpsParticipation.start_at < row.end_at, m.UvOpsParticipation.end_at > row.start_at))
        c.require(paid is None, 'payroll_frozen', '重叠任务工资已核准，请先撤销受影响工资再纠正工时')
    if kind == 'quality':
        batch = c.get(db, m.UvOpsBatch, row.batch_id, lock=True)
        c.require(batch.active and batch.pass_index == row.pass_index, 'downstream_dependency', '品质数量已进入后续工序')
        task = tasks[row.task_id]
        bucket = 'intermediate' if row.disposition == 'good' and row.pass_index < task.process_snapshot['passes'] else row.disposition
        if row.disposition == 'rework':
            child = db.scalar(c.query(m.UvOpsTask).join(m.UvOpsReworkBinding, m.UvOpsReworkBinding.task_id == m.UvOpsTask.id).where(m.UvOpsReworkBinding.batch_id == batch.id, m.UvOpsTask.status != 'cancelled'))
            c.require(child is None, 'downstream_rework', '请先撤销返工报产并取消返工任务')
        c.require(getattr(batch, bucket) >= row.quantity, 'downstream_dependency', '处置数量已被后续处理消耗')
        setattr(batch, bucket, getattr(batch, bucket)-row.quantity)
        c.require(batch.good >= batch.reserved+batch.received, 'handover_dependency', '请先处理下游交接再撤销品质结论')
        batch.pending += row.quantity
        c.touch(batch)
    if kind == 'expense':
        # Child costs must be voided together, preserving the original pool sum.
        linked = any(any(x['expense_id'] == row.id for x in pool.cost_allocations) for pool in db.scalars(c.query(m.UvOpsRunCost)))
        c.require(not linked, 'run_cost_dependency', '这是拼版成本分摊凭证，请从原始运行成本池整体撤销')
    if kind == 'run_cost':
        for allocation in sorted(row.cost_allocations, key=lambda x: x['expense_id']):
            expense = c.get(db, m.UvOpsExpense, allocation['expense_id'], lock=True)
            void(db, user, 'expense', expense, body.reason, day)
    receipt = void(db, user, kind, row, body.reason, day)
    if kind == 'quality':
        db.flush()
        p.validate_timeline(db, batch)
        for task in tasks.values():
            task.status = 'in_progress'
            c.touch(task)
    return dict(original=c.record(row), reversal=c.record(receipt))
