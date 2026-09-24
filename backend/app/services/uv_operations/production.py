from decimal import Decimal
from sqlalchemy import select
from app.models import uv_operations as m
from . import common as c


def create_master(db, user, body, model):
    c.require(body.expected_version == 0, "version_conflict", "新建记录版本必须为 0")
    if model == m.UvOpsProcessVersion:
        c.get(db, m.UvOpsProduct, body.product_id)
        fixture = c.get(db, m.UvOpsFixture, body.fixture_id)
        c.require(body.pieces_per_board <= fixture.slots, "fixture_capacity", "每板件数不能超过治具槽位", 422)
        c.require(body.width_mm <= fixture.width_mm and body.height_mm <= fixture.height_mm, "fixture_size", "产品布局超出治具尺寸", 422)
    if model == m.UvOpsPricePolicy:
        c.get(db, m.UvOpsProduct, body.product_id)
    return c.record(c.add(db, model, user, **c.values(body)))


def create_demand(db, user, body):
    c.require(body.source_type == "manual" or body.source_line_id, "source_line_required", "订单需求必须有稳定来源行编号", 422)
    product = c.get(db, m.UvOpsProduct, body.product_id)
    values = c.values(body)
    values["due_at"] = c.ts(body.due_at)
    return c.record(c.add(db, m.UvOpsDemand, user, **values, customer_snapshot=product.customer, product_snapshot=product.name))


def create_task(db, user, body):
    demand = c.get(db, m.UvOpsDemand, body.demand_id, lock=True)
    process = c.get(db, m.UvOpsProcessVersion, body.process_version_id)
    file = c.get(db, m.UvOpsFileVersion, body.file_version_id)
    c.require(process.product_id == demand.product_id and file.process_version_id == process.id, "version_binding", "需求、工艺和文件版本不匹配", 422)
    c.require(file.role == "production" and file.confirmed_at and file.first_article_evidence, "preparation_missing", "生产文件尚未确认首件或明确豁免依据")
    c.require(demand.allocated + demand.cancelled + body.quantity <= demand.quantity, "over_allocation", "任务数量超出未分配需求")
    price = c.get(db, m.UvOpsPricePolicy, body.price_policy_id) if body.price_policy_id else None
    wage = c.get(db, m.UvOpsWagePolicy, body.wage_policy_id) if body.wage_policy_id else None
    c.require(not price or price.product_id == demand.product_id, "price_product_mismatch", "价格不属于该产品", 422)
    task = c.add(db, m.UvOpsTask, user, **c.values(body), product_snapshot=demand.product_snapshot, process_snapshot=c.record(process), cost_price_snapshot=c.record(price) if price else None, payroll_policy_snapshot=c.record(wage) if wage else None)
    c.add(db, m.UvOpsBatch, user, task_id=task.id, quantity=body.quantity, remaining=body.quantity)
    demand.allocated += body.quantity
    c.touch(demand)
    return task_detail(db, task)


def task_detail(db, task):
    db.flush()
    result = c.record(task)
    original_id = task.parent_task_id or task.id
    batches = c.query(m.UvOpsBatch).where(m.UvOpsBatch.task_id == original_id,m.UvOpsBatch.active.is_(True))
    if task.parent_task_id:
        batches = batches.where(m.UvOpsBatch.id.in_(select(m.UvOpsReworkBinding.batch_id).where(m.UvOpsReworkBinding.task_id==task.id)))
    result["batches"] = [c.record(x) for x in db.scalars(batches)]
    result["schedule"] = [c.record(x) for x in db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.task_id == task.id))]
    return result


def task_complete(db, task_id):
    db.flush()
    rows=list(db.scalars(c.query(m.UvOpsBatch).where(m.UvOpsBatch.task_id==task_id,m.UvOpsBatch.active.is_(True))))
    return bool(rows) and all(row.good+row.scrap==row.quantity for row in rows)


def reshape_batch(db,user,entity_id,body,merge=False):
    source=c.get(db,m.UvOpsBatch,entity_id)
    task=c.get(db,m.UvOpsTask,source.task_id,lock=True)
    ids={entity_id,body.other_batch_id} if merge else {entity_id}
    rows={key:c.get(db,m.UvOpsBatch,key,lock=True) for key in sorted(ids)}
    c.require(rows[entity_id].version==body.expected_version,'version_conflict','批次已变化')
    if merge:
        c.require(len(ids)==2 and rows[body.other_batch_id].version==body.other_version,'version_conflict','合并来源已变化或重复')
    c.require(len(body.reason.strip())>=5,'reason_required','拆分或合并需说明实际流转依据',422)
    for row in rows.values():
        c.require(row.task_id==task.id and row.active and row.pass_index==1 and row.remaining==row.quantity,'batch_started','仅可拆分或合并同一任务尚未加工的首遍批次')
        c.require(db.scalar(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.batch_id==row.id)) is None,'batch_history','已有加工历史的批次不能重新编组')
        c.require(db.scalar(c.query(m.UvOpsRunAllocation).where(m.UvOpsRunAllocation.batch_id==row.id)) is None,'batch_run_allocated','已确认运行分配的批次不能重新编组')
    total=sum(row.quantity for row in rows.values())
    if merge:
        quantities=[total]
    else:
        c.require(0<body.quantity<total,'split_quantity','拆出数量必须小于原批次数量',422)
        quantities=[body.quantity,total-body.quantity]
    children=[c.add(db,m.UvOpsBatch,user,task_id=task.id,quantity=value,remaining=value) for value in quantities]
    for row in rows.values():
        row.active=False;c.touch(row)
        for child in children:
            c.add(db,m.UvOpsBatchRelation,user,source_id=row.id,target_id=child.id,quantity=row.quantity if merge else child.quantity,kind='merge' if merge else 'split')
    c.touch(task)
    return dict(batches=[c.record(row) for row in children],task=c.record(task))


def complete_accounting(db,user,entity_id,body):
    from . import authz
    c.require(len(body.reason.strip())>=5,'reason_required','补齐冻结核算规则必须说明依据',422)
    source=c.get(db,m.UvOpsTask,entity_id)
    c.require(source.parent_task_id is None,'root_task_required','请在原始任务上补齐规则，返工子任务会同步未填写部分',422)
    ids={source.id}|{x.id for x in db.scalars(c.query(m.UvOpsTask).where(m.UvOpsTask.parent_task_id==source.id))}
    dates={x.business_date for x in db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.task_id.in_(ids)))}
    dates|={x.business_date for x in db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.task_id.in_(ids)))}
    for date in sorted(dates):
        c.lock_period(db,date)
    tasks={key:c.get(db,m.UvOpsTask,key,lock=True) for key in sorted(ids)}
    task=tasks[source.id]
    c.require(task.version==body.expected_version,'version_conflict','任务已变化，请重新核对')
    c.require(body.price_policy_id or body.wage_policy_id,'policy_required','请至少选择一项待补齐规则',422)
    if body.price_policy_id:
        authz.authorize(user,m.FACTORY,'cost_read','cost_write')
        policy=c.get(db,m.UvOpsPricePolicy,body.price_policy_id)
        demand=c.get(db,m.UvOpsDemand,task.demand_id)
        c.require(task.cost_price_snapshot is None and policy.product_id==demand.product_id,'price_frozen','已有价格快照不能覆盖；新价格需属于同一产品')
        for item in tasks.values():
            if item.cost_price_snapshot is None:
                item.price_policy_id,item.cost_price_snapshot=policy.id,c.record(policy)
                c.touch(item)
    if body.wage_policy_id:
        authz.authorize(user,m.FACTORY,'payroll_read','payroll_write')
        policy=c.get(db,m.UvOpsWagePolicy,body.wage_policy_id)
        c.require(task.payroll_policy_snapshot is None,'wage_frozen','已有工资快照不能覆盖')
        for item in tasks.values():
            if item.payroll_policy_snapshot is None:
                item.wage_policy_id,item.payroll_policy_snapshot=policy.id,c.record(policy)
                c.touch(item)
    return task_detail(db,task)


def create_shift(db, user, body):
    c.require(body.end_at > body.start_at and (body.end_at - body.start_at).total_seconds() <= 86400, "shift_interval", "班次需为不超过 24 小时的有效区间", 422)
    breaks = sorted(body.breaks)
    for i, (start, end) in enumerate(breaks):
        c.require(body.start_at <= start < end <= body.end_at and (i == 0 or breaks[i-1][1] <= start), "break_interval", "休息区间必须在班次内且不重叠", 422)
    c.lock_period(db, body.business_date)
    return c.record(c.add(db, m.UvOpsShift, user, **c.values(body, "start_at", "end_at", "breaks"), start_at=c.ts(body.start_at), end_at=c.ts(body.end_at), breaks=[[c.ts(a), c.ts(b)] for a, b in breaks]))


def shift_open(db, shift_id, *, lock=True):
    # Read date first, then obtain locks in period -> shift order.
    item = c.get(db, m.UvOpsShift, shift_id)
    c.lock_period(db, item.business_date)
    item = c.get(db, m.UvOpsShift, shift_id, lock=lock)
    c.require(item.status == "open", "shift_closed", "班次已关闭，请先说明理由并重开")
    return item


def participate(db, user, body):
    shift = shift_open(db, body.shift_id)
    c.require(db.scalar(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.shift_id == shift.id, m.UvOpsWageAccrual.task_id == body.task_id)) is None, 'payroll_frozen', '该任务本班工资已核准，不能追加参与人或工时')
    c.get(db, m.UvOpsTask, body.task_id, lock=True)
    start, end = c.ts(body.start_at), c.ts(body.end_at)
    c.require(shift.start_at <= start < end <= shift.end_at, "participation_interval", "参与时段必须在班次内", 422)
    c.insert_once(db, m.UvOpsWorker, dict(id=body.employee_id, factory_id=m.FACTORY, employee_id=body.employee_id, name=body.employee_name, version=1, created_at=m.now(), updated_at=m.now(), created_by=user.id), ["factory_id", "employee_id"])
    worker = db.scalar(c.query(m.UvOpsWorker).where(m.UvOpsWorker.employee_id == body.employee_id).with_for_update())
    c.require(worker is not None, "worker_missing", "员工记录未就绪")
    # Overlap is permitted across machines; payroll divides actual time among all
    # intersecting participations. Overlap on the same task is accidental duplication.
    existing = db.scalar(c.query(m.UvOpsParticipation).where(m.UvOpsParticipation.employee_id == body.employee_id, m.UvOpsParticipation.task_id == body.task_id, m.UvOpsParticipation.start_at < end, m.UvOpsParticipation.end_at > start))
    c.require(existing is None, "participation_overlap", "该员工在此任务上已有重叠时段")
    # Once any overlapping allocation is paid, changing its divisor is forbidden.
    paid = db.scalar(select(m.UvOpsWageAccrual.id).join(m.UvOpsParticipation, (m.UvOpsParticipation.task_id == m.UvOpsWageAccrual.task_id) & (m.UvOpsParticipation.shift_id == m.UvOpsWageAccrual.shift_id)).where(m.UvOpsParticipation.employee_id == body.employee_id, m.UvOpsParticipation.start_at < end, m.UvOpsParticipation.end_at > start))
    c.require(paid is None, "payroll_frozen", "重叠时段已有工资核准，不能改变其工时分母")
    return c.record(c.add(db, m.UvOpsParticipation, user, **c.values(body, "start_at", "end_at"), start_at=start, end_at=end))


def confirm(db, user, body):
    shift = shift_open(db, body.shift_id)
    c.require(db.scalar(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.shift_id == shift.id, m.UvOpsWageAccrual.task_id == body.task_id)) is None, "payroll_frozen", "该任务本班工资已核准，不能继续修改核数")
    task = c.get(db, m.UvOpsTask, body.task_id)
    locked_tasks = {key: c.get(db, m.UvOpsTask, key, lock=True) for key in sorted({task.id, task.parent_task_id} - {None})}
    task = locked_tasks[task.id]
    c.require(task.status != 'cancelled', 'task_cancelled', '返工任务已取消')
    batch = c.get(db, m.UvOpsBatch, body.batch_id, lock=True, version=body.expected_version)
    c.require(batch.active, "batch_superseded", "批次已拆分或合并，请选择有效子批次")
    c.require(batch.task_id == (task.parent_task_id or task.id), "batch_task", "批次不属于当前任务", 422)
    c.require(batch.pass_index == body.pass_index, "pass_conflict", "批次工序已变化，请重新核对")
    c.require(bool(task.parent_task_id) == (body.source_bucket == 'rework'), "rework_source", "返工数量需通过对应返工任务消耗，普通任务只消耗待加工数量", 422)
    c.require(getattr(batch, body.source_bucket) >= body.processed, "insufficient_batch", "核数超过该批次可加工数量")
    if body.source_bucket == 'rework':
        c.require(bucket_at(db,batch,'rework',shift.business_date)>=body.processed,'future_source','该业务日尚无足够返工来源，不能提前消耗后日数量')
    if batch.pass_index > 1:
        future = db.scalar(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.batch_id==batch.id,m.UvOpsProductionEntry.pass_index<batch.pass_index,m.UvOpsProductionEntry.business_date>shift.business_date))
        c.require(future is None,'future_source','后道工序业务日不能早于前道已确认来源')
        future_quality=db.scalar(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.batch_id==batch.id,m.UvOpsQualityEntry.pass_index<batch.pass_index,m.UvOpsQualityEntry.business_date>shift.business_date))
        c.require(future_quality is None,'future_source','后道工序业务日不能早于前道品质放行日期')
    if task.parent_task_id:
        binding=db.scalar(c.query(m.UvOpsReworkBinding).where(m.UvOpsReworkBinding.task_id==task.id))
        c.require(binding is not None and binding.batch_id==batch.id,"rework_batch","返工任务只能消耗其绑定的原批次")
        already = sum(x.processed*x.direction for x in db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.task_id == task.id)))
        c.require(already + body.processed <= task.quantity, "rework_overrun", "返工核数超过返工任务数量")
    final = body.pass_index == task.process_snapshot["passes"]
    setattr(batch, body.source_bucket, getattr(batch, body.source_bucket)-body.processed)
    good_bucket = "good" if final else "intermediate"
    setattr(batch, good_bucket, getattr(batch, good_bucket)+body.good)
    for name in ("rework", "scrap", "pending"):
        setattr(batch, name, getattr(batch, name)+getattr(body, name))
    entry = c.add(db, m.UvOpsProductionEntry, user, **c.values(body), business_date=shift.business_date, final_pass=final)
    completed = already + body.processed == task.quantity if task.parent_task_id else task_complete(db,batch.task_id)
    task.status = "completed" if completed else "in_progress"
    c.touch(task)
    if task.parent_task_id:
        parent = locked_tasks[task.parent_task_id]
        parent.status = "completed" if task_complete(db,batch.task_id) else "in_progress"
        c.touch(parent)
    c.touch(batch)
    db.flush()
    validate_timeline(db, batch)
    return dict(entry=c.record(entry), batch=c.record(batch), task=c.record(task))


def reverse(db, user, entity_id, body):
    original = c.get(db, m.UvOpsProductionEntry, entity_id)
    shift_open(db, original.shift_id)
    task = c.get(db, m.UvOpsTask, original.task_id)
    locked_tasks = {key: c.get(db, m.UvOpsTask, key, lock=True) for key in sorted({task.id, task.parent_task_id} - {None})}
    task = locked_tasks[task.id]
    batch = c.get(db, m.UvOpsBatch, original.batch_id, lock=True, version=body.expected_version)
    c.require(body.reason.strip(), "reason_required", "冲销必须填写理由", 422)
    c.require(original.direction == 1 and batch.pass_index == original.pass_index, "downstream_dependency", "后续工序已使用该产量，不能直接冲销")
    c.require(db.scalar(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.production_entry_id==original.id)) is None,'downstream_quality','此核数的待检件已有品质处置，不能直接冲销')
    if original.rework:
        children=db.scalar(c.query(m.UvOpsTask).join(m.UvOpsReworkBinding,m.UvOpsReworkBinding.task_id==m.UvOpsTask.id).where(m.UvOpsReworkBinding.batch_id==batch.id,m.UvOpsTask.status!='cancelled'))
        c.require(children is None,'downstream_rework','返工来源已有子任务，请先处理该任务的取消或冲销链')
    c.require(db.scalar(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.task_id == original.task_id, m.UvOpsWageAccrual.shift_id == original.shift_id)) is None, "payroll_frozen", "该核数已用于工资核准")
    bucket = "good" if original.final_pass else "intermediate"
    for name, amount in ((bucket, original.good), ("rework", original.rework), ("scrap", original.scrap), ("pending", original.pending)):
        c.require(getattr(batch, name) >= amount, "downstream_dependency", "数量已被后续处理使用")
        setattr(batch, name, getattr(batch, name)-amount)
    c.require(batch.good >= batch.reserved + batch.received, "handover_dependency", "请先处理下游交接后再冲销")
    setattr(batch, original.source_bucket, getattr(batch, original.source_bucket)+original.processed)
    c.touch(batch)
    values = {key: getattr(original, key) for key in ("task_id", "batch_id", "shift_id", "business_date", "pass_index", "source_bucket", "processed", "good", "rework", "scrap", "pending", "final_pass")}
    entry = c.add(db, m.UvOpsProductionEntry, user, **values, reversal_of=original.id, direction=-1, evidence=body.reason)
    validate_timeline(db, batch)
    task.status = "in_progress"
    c.touch(task)
    if task.parent_task_id:
        locked_tasks[task.parent_task_id].status = "in_progress"
        c.touch(locked_tasks[task.parent_task_id])
    return dict(entry=c.record(entry), batch=c.record(batch))


def advance_pass(db, user, entity_id, body):
    source = c.get(db, m.UvOpsBatch, entity_id)
    task = c.get(db, m.UvOpsTask, source.task_id, lock=True)
    batch = c.get(db, m.UvOpsBatch, entity_id, lock=True, version=body.expected_version)
    c.require(batch.active, "batch_superseded", "批次已拆分或合并")
    c.require(batch.pass_index < task.process_snapshot["passes"], "last_pass", "已经是最终工序")
    c.require(batch.remaining == batch.pending == batch.rework == 0 and batch.intermediate > 0, "pass_incomplete", "请先完成当前工序的待加工、返工和待检核数")
    batch.pass_index += 1
    batch.remaining = batch.intermediate
    batch.intermediate = 0
    c.touch(batch)
    return c.record(batch)


def quality(db, user, body):
    shift = shift_open(db, body.shift_id)
    source = c.get(db, m.UvOpsBatch, body.batch_id)
    sources=list(db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.batch_id==source.id,m.UvOpsProductionEntry.pass_index==source.pass_index,m.UvOpsProductionEntry.pending>0,m.UvOpsProductionEntry.direction==1).order_by(m.UvOpsProductionEntry.business_date,m.UvOpsProductionEntry.created_at,m.UvOpsProductionEntry.id)))
    tasks={key:c.get(db,m.UvOpsTask,key,lock=True) for key in sorted({source.task_id}|{entry.task_id for entry in sources})}
    task = tasks[source.task_id]
    batch = c.get(db, m.UvOpsBatch, body.batch_id, lock=True, version=body.expected_version)
    c.require(batch.active, "batch_superseded", "批次已拆分或合并，请选择有效子批次")
    c.require(batch.pending >= body.quantity, "pending_insufficient", "处置数量超过待检数量")
    c.require(bucket_at(db,batch,'pending',shift.business_date)>=body.quantity,'future_source','该业务日尚无足够待检来源，不能提前处置后日数量')
    batch.pending -= body.quantity
    bucket = "intermediate" if body.disposition == "good" and batch.pass_index < task.process_snapshot["passes"] else body.disposition
    setattr(batch, bucket, getattr(batch, bucket)+body.quantity)
    c.touch(batch)
    task.status = "completed" if task_complete(db,batch.task_id) else "in_progress"
    c.touch(task)
    remaining,entries=body.quantity,[]
    for original in sources:
        if original.business_date>shift.business_date:
            continue
        if db.scalar(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.reversal_of==original.id)):
            continue
        disposed=sum(row.quantity for row in db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.production_entry_id==original.id)))
        take=min(remaining,original.pending-disposed)
        if take<=0:
            continue
        c.require(db.scalar(c.query(m.UvOpsWageAccrual).where(m.UvOpsWageAccrual.shift_id==shift.id,m.UvOpsWageAccrual.task_id==original.task_id)) is None,'payroll_frozen','品质来源任务本班工资已核准，不能变更计薪数量')
        entry=c.add(db,m.UvOpsQualityEntry,user,**c.values(body,'quantity'),quantity=take,task_id=original.task_id,production_entry_id=original.id,business_date=shift.business_date,pass_index=batch.pass_index)
        entries.append(c.record(entry))
        remaining-=take
        if remaining==0:
            break
    c.require(remaining==0,'pending_source_missing','待检来源台账不足，无法分配品质处置')
    return dict(entry=entries[0],entries=entries,batch=c.record(batch))


def bucket_at(db,batch,bucket,business_date):
    value=0
    for entry in db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.batch_id==batch.id,m.UvOpsProductionEntry.pass_index==batch.pass_index,m.UvOpsProductionEntry.business_date<=business_date)):
        value+=(getattr(entry,bucket)-(entry.processed if entry.source_bucket==bucket else 0))*entry.direction
    for entry in db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.batch_id==batch.id,m.UvOpsQualityEntry.pass_index==batch.pass_index,m.UvOpsQualityEntry.business_date<=business_date)):
        value+=-entry.quantity if bucket=='pending' else entry.quantity if entry.disposition==bucket else 0
    return value


def validate_timeline(db, batch):
    """A backdated write must preserve every later dated ledger balance."""
    from collections import defaultdict
    changes = defaultdict(lambda: dict(rework=0, pending=0, available=0))
    db.flush()
    for row in db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.batch_id == batch.id)):
        day = changes[row.business_date]
        if row.pass_index == batch.pass_index:
            for key in ('rework', 'pending'):
                day[key] += (getattr(row,key) - (row.processed if row.source_bucket == key else 0)) * row.direction
        if row.final_pass:
            day['available'] += row.good * row.direction
    for row in db.scalars(c.query(m.UvOpsQualityEntry).where(m.UvOpsQualityEntry.batch_id == batch.id)):
        day = changes[row.business_date]
        if row.pass_index == batch.pass_index:
            day['pending'] -= row.quantity
            if row.disposition == 'rework': day['rework'] += row.quantity
        if row.pass_index == batch.pass_index and row.disposition == 'good' and batch.good:
            day['available'] += row.quantity
    handovers = list(db.scalars(c.query(m.UvOpsHandover).where(m.UvOpsHandover.batch_id == batch.id)))
    for row in handovers:
        changes[row.business_date]['available'] -= row.quantity
    if handovers:
        for row in db.scalars(c.query(m.UvOpsHandoverEvent).where(m.UvOpsHandoverEvent.handover_id.in_([x.id for x in handovers]))):
            if row.kind in ('reject', 'return', 'cancel_reservation'):
                changes[row.business_date]['available'] += row.quantity
        for handover in handovers:
            receipts=defaultdict(int)
            for row in db.scalars(c.query(m.UvOpsHandoverEvent).where(m.UvOpsHandoverEvent.handover_id==handover.id)):
                receipts[row.business_date]+=row.quantity if row.kind=='receive' else -row.quantity if row.kind=='return' else 0
            received=0
            for day in sorted(receipts):
                received+=receipts[day]
                c.require(received>=0,'historical_receipt','回填退回会令后续业务日净签收为负')
    balances = dict(rework=0, pending=0, available=0)
    for day in sorted(changes):
        for key, delta in changes[day].items():
            balances[key] += delta
        c.require(min(balances.values()) >= 0, 'historical_balance', '回填会令后续业务日的返工、待检或可交良品为负，请按来源日期核对')


def rework_task(db, user, body):
    source = c.get(db, m.UvOpsBatch, body.batch_id)
    parent = c.get(db, m.UvOpsTask, source.task_id, lock=True)
    batch = c.get(db, m.UvOpsBatch, body.batch_id, lock=True, version=body.expected_version)
    c.require(batch.active, "batch_superseded", "批次已拆分或合并，请选择有效子批次")
    c.require(batch.rework >= body.quantity, "rework_insufficient", "返工任务数量超过待返工数量")
    for task in db.scalars(c.query(m.UvOpsTask).join(m.UvOpsReworkBinding,m.UvOpsReworkBinding.task_id==m.UvOpsTask.id).where(m.UvOpsReworkBinding.batch_id==batch.id, m.UvOpsTask.status.notin_(['completed','cancelled']))):
        c.require(False, "rework_task_open", "该批次已有未完成返工任务，请先处理")
    values = {key: getattr(parent, key) for key in ("demand_id", "process_version_id", "file_version_id", "wage_policy_id", "price_policy_id", "product_snapshot", "process_snapshot", "cost_price_snapshot", "payroll_policy_snapshot")}
    task = c.add(db, m.UvOpsTask, user, **values, parent_task_id=parent.id, code=body.code, quantity=body.quantity)
    c.add(db,m.UvOpsReworkBinding,user,task_id=task.id,batch_id=batch.id)
    return task_detail(db, task)


def handover_create(db, user, body):
    c.lock_period(db, body.business_date)
    batch = c.get(db, m.UvOpsBatch, body.batch_id, lock=True, version=body.expected_version)
    c.require(batch.active, "batch_superseded", "批次已拆分或合并，请选择有效子批次")
    if body.receiver_id and body.receiver_id!=user.id:
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context
        from .authz import allowed
        receiver=db.get(AuthUser,body.receiver_id)
        c.require(receiver is not None and receiver.status=='active' and allowed(build_auth_context(db,receiver),'handover_write'),'invalid_receiver','收方必须是有华康 A UV 交接权限的有效账号',422)
    c.require(batch.good - batch.reserved - batch.received >= body.quantity, "handover_insufficient", "交接数量超过可交良品")
    batch.reserved += body.quantity
    c.touch(batch)
    row = c.add(db, m.UvOpsHandover, user, **c.values(body, "receiver_id"), receiver_id=body.receiver_id or user.id)
    validate_timeline(db, batch)
    return c.record(row)


def cancel_handover(db,user,entity_id,body):
    source=c.get(db,m.UvOpsHandover,entity_id)
    c.lock_period(db,body.business_date)
    c.require(body.business_date>=source.business_date,"handover_date","取消日期不能早于发起日",422)
    row=c.get(db,m.UvOpsHandover,entity_id,lock=True,version=body.expected_version)
    c.require(user.id==row.created_by or user.id==row.receiver_id,'handover_owner','只有发起人或指定收方可撤销未签收余额',403)
    c.require(len(body.reason.strip())>=5,'reason_required','请填写取消未签收余额的理由',422)
    remaining=row.quantity-row.received-row.rejected
    c.require(remaining>0,'no_reservation','该交接已无未签收预留')
    batch=c.get(db,m.UvOpsBatch,row.batch_id,lock=True)
    batch.reserved-=remaining
    row.rejected+=remaining
    row.status='settled'
    c.touch(batch);c.touch(row)
    c.add(db,m.UvOpsHandoverEvent,user,handover_id=row.id,kind='cancel_reservation',quantity=remaining,business_date=body.business_date,evidence=body.reason)
    return dict(handover=c.record(row),batch=c.record(batch))


def cancel_rework(db,user,entity_id,body):
    source=c.get(db,m.UvOpsTask,entity_id)
    c.require(source.parent_task_id is not None,'not_rework','只有返工子任务可使用此取消动作')
    tasks={key:c.get(db,m.UvOpsTask,key,lock=True) for key in sorted({source.id,source.parent_task_id})}
    row=tasks[source.id]
    c.require(row.version==body.expected_version and row.status!='cancelled','version_conflict','返工任务状态或版本已变化')
    c.require(db.scalar(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.task_id==row.id)) is None,'rework_started','已有加工凭证的返工任务不能直接取消')
    c.require(len(body.reason.strip())>=5,'reason_required','取消返工任务需说明理由',422)
    row.status='cancelled';c.touch(row)
    for block in db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.task_id == row.id)):
        block.status='cancelled';c.touch(block)
    return c.record(row)


def handover_action(db, user, entity_id, body, kind):
    c.lock_period(db, body.business_date)
    handover = c.get(db, m.UvOpsHandover, entity_id, lock=True, version=body.expected_version)
    c.require(body.business_date >= handover.business_date, 'handover_date', '签收、拒收或退回日期不能早于发起日', 422)
    c.require(handover.receiver_id == user.id, "receiver_required", "只有交接单指定收方可以签收、拒收或退回", 403)
    batch = c.get(db, m.UvOpsBatch, handover.batch_id, lock=True)
    if kind == "return":
        dated_received = sum((x.quantity if x.kind == 'receive' else -x.quantity if x.kind == 'return' else 0) for x in db.scalars(c.query(m.UvOpsHandoverEvent).where(m.UvOpsHandoverEvent.handover_id == handover.id, m.UvOpsHandoverEvent.business_date <= body.business_date)))
        c.require(dated_received >= body.quantity, 'return_date', '退回日尚无足够已签收数量，不能提前退回后日签收数量')
        c.require(body.quantity <= handover.received - handover.returned, "return_insufficient", "退回数量超过已签收数量")
        handover.returned += body.quantity
        batch.received -= body.quantity
    else:
        c.require(body.quantity <= handover.quantity - handover.received - handover.rejected, "receipt_insufficient", "签收或拒收超过剩余交接数量")
        batch.reserved -= body.quantity
        if kind == "receive":
            handover.received += body.quantity
            batch.received += body.quantity
        else:
            handover.rejected += body.quantity
    handover.status = "settled" if handover.received + handover.rejected == handover.quantity else "partial"
    c.touch(handover)
    c.touch(batch)
    c.add(db, m.UvOpsHandoverEvent, user, handover_id=handover.id, kind=kind, quantity=body.quantity, business_date=body.business_date, evidence=body.evidence)
    validate_timeline(db, batch)
    return dict(handover=c.record(handover), batch=c.record(batch))


def shift_gaps(db, shift):
    entries = list(db.scalars(c.query(m.UvOpsProductionEntry).where(m.UvOpsProductionEntry.shift_id == shift.id)))
    task_ids = {x.task_id for x in entries}
    participants = {x.task_id for x in db.scalars(c.query(m.UvOpsParticipation).where(m.UvOpsParticipation.shift_id == shift.id))}
    pending = list(db.scalars(c.query(m.UvOpsBatch).where(m.UvOpsBatch.task_id.in_(task_ids), m.UvOpsBatch.pending > 0)))
    runs = list(db.scalars(c.query(m.UvOpsRun).where(m.UvOpsRun.started_at < shift.end_at, (m.UvOpsRun.ended_at.is_(None)) | (m.UvOpsRun.ended_at >= shift.start_at), m.UvOpsRun.match_evidence.is_(None))))
    return dict(missing_participation=sorted(task_ids-participants), pending_quality=[x.id for x in pending], unmatched_runs=[x.id for x in runs],totals={key:sum(getattr(x,key)*x.direction for x in entries) for key in ('processed','good','rework','scrap','pending')})


def close_shift(db, user, entity_id, body):
    shift = shift_open(db, entity_id)
    c.require(shift.version == body.expected_version, "version_conflict", "班次已更新", version=shift.version)
    gaps = shift_gaps(db, shift)
    c.require(not any(gaps[key] for key in ('missing_participation','pending_quality','unmatched_runs')) or len(body.wip_handover.strip()) >= 5, "shift_gaps", "仍有核数缺口，请处理或明确在制交班说明")
    shift.status = "closed"
    shift.close_reason = body.wip_handover or "核对完成"
    c.touch(shift)
    return dict(shift=c.record(shift), gaps=gaps)
