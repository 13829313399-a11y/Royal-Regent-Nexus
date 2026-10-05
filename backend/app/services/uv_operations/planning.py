"""Batch plans use resource locks; estimates never rewrite frozen process facts."""
from datetime import datetime, timedelta, UTC
from decimal import Decimal
from math import ceil
from hashlib import sha256
from sqlalchemy import select, text
from app.models import uv_operations as m
from . import common as c


def task_batches(db, task):
    statement = c.query(m.UvOpsBatch).where(m.UvOpsBatch.task_id == (task.parent_task_id or task.id), m.UvOpsBatch.active.is_(True))
    if task.parent_task_id:
        statement = statement.where(m.UvOpsBatch.id.in_(select(m.UvOpsReworkBinding.batch_id).where(m.UvOpsReworkBinding.task_id == task.id)))
    return list(db.scalars(statement.order_by(m.UvOpsBatch.id)))


def started(db, task, batch_id):
    if task.status in {'completed', 'cancelled'}:
        return True
    for model in (m.UvOpsProductionEntry, m.UvOpsRunAllocation, m.UvOpsExecution):
        statement = c.query(model).where(model.task_id == task.id)
        if batch_id:
            statement = statement.where(model.batch_id == batch_id)
        if db.scalar(statement.limit(1)) is not None:
            return True
    return False


def duration(task, batch, manual=None):
    cycle = task.process_snapshot.get('cycle_seconds')
    if cycle is None:
        return Decimal(manual) if manual is not None else None
    quantity = task.quantity if task.parent_task_id else batch.quantity
    return Decimal(str(cycle)) * ceil(quantity / task.process_snapshot['pieces_per_board']) * (1 if task.parent_task_id else task.process_snapshot['passes'])


def fixture_for(row, task):
    return row.fixture_id or task.process_snapshot['fixture_id']


def execution_windows(db, executions):
    plans = {x.id: x for x in db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.id.in_({x.schedule_id for x in executions}))) } if executions else {}
    now = m.now()
    # Future reservations use expected release; actual starts still require finish.
    return [(x, x.ended_at or max(plans[x.schedule_id].end_at, x.started_at, now)) for x in executions]


def preview(db, body, *, lock=False):
    # Shared ordering with production/reshaping: task -> batch -> machine -> fixture.
    tasks = {key: c.get(db, m.UvOpsTask, key, lock=lock) for key in sorted({x.task_id for x in body.blocks})}
    selected = []
    for item in body.blocks:
        candidates = task_batches(db, tasks[item.task_id])
        if item.batch_id:
            candidates = [row for row in candidates if row.id == item.batch_id]
        c.require(len(candidates) == 1, 'batch_required', '请选择属于该任务的有效实体批次；拆批后必须逐批排程', 422)
        selected.append(candidates[0].id)
    c.require(len(set(zip((x.task_id for x in body.blocks), selected))) == len(selected), 'duplicate_batch', '一次计划不能重复分配同一任务批次', 422)
    batches = {key: c.get(db, m.UvOpsBatch, key, lock=lock) for key in sorted(set(selected))}
    existing_own = list(db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.task_id.in_(tasks))))
    machines = {key: c.get(db, m.UvOpsMachine, key, lock=lock) for key in sorted({x.machine_id for x in body.blocks} | {x.machine_id for x in existing_own})}
    fixture_ids = {x.fixture_id or tasks[x.task_id].process_snapshot['fixture_id'] for x in body.blocks}
    fixture_ids |= {fixture_for(x, tasks[x.task_id]) for x in existing_own}
    fixtures = {key: c.get(db, m.UvOpsFixture, key) for key in sorted(fixture_ids)}
    # Revisions of the same code describe ONE physical fixture. Advisory locks
    # also cover a newly created revision without requiring a factory-wide lock.
    if lock and db.bind.dialect.name == 'postgresql':
        for code in sorted({row.code for row in fixtures.values()}):
            key = int.from_bytes(sha256(('uv-fixture:'+code).encode()).digest()[:8], 'big', signed=True)
            db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key':key})
    lower, upper = min(c.ts(x.start_at) for x in body.blocks), max(c.ts(x.end_at) for x in body.blocks)
    occupied = list(db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.status != 'cancelled', m.UvOpsScheduleBlock.start_at < upper, m.UvOpsScheduleBlock.end_at > lower)))
    lookup = dict(tasks)
    missing = {x.task_id for x in occupied} - tasks.keys()
    if missing:
        lookup.update({x.id: x for x in db.scalars(c.query(m.UvOpsTask).where(m.UvOpsTask.id.in_(missing)))})
    missing_fixtures = {fixture_for(row, lookup[row.task_id]) for row in occupied} - fixtures.keys()
    if missing_fixtures:
        fixtures.update({x.id:x for x in db.scalars(c.query(m.UvOpsFixture).where(m.UvOpsFixture.id.in_(missing_fixtures)))})
    actuals=list(db.scalars(c.query(m.UvOpsExecution).where(m.UvOpsExecution.started_at<upper,(m.UvOpsExecution.ended_at.is_(None)) | (m.UvOpsExecution.ended_at>lower))))
    actual_windows=execution_windows(db,actuals)
    old_rows = []
    for item, batch_id in zip(body.blocks, selected):
        old = next((x for x in existing_own if x.task_id == item.task_id and x.batch_id == batch_id), None)
        legacy = next((x for x in existing_own if x.task_id == item.task_id and x.batch_id is None and x.status != 'cancelled'), None)
        if legacy:
            c.require(len(task_batches(db, tasks[item.task_id])) == 1 and old is None, 'legacy_plan', '请先撤销旧整任务计划，再按有效子批次重新排程')
            old = legacy
        old_rows.append(old)
    replacing = {x.id for x in old_rows if x}
    conflicts, blocks, changes, warnings = [], [], [], []
    for item, batch_id, old in zip(body.blocks, selected, old_rows):
        task, batch, machine = tasks[item.task_id], batches[batch_id], machines[item.machine_id]
        process = task.process_snapshot
        fixture = fixtures[item.fixture_id or process['fixture_id']]
        reasons = []
        if task.version != item.task_version or machine.version != item.machine_version or (old.version if old else 0) != item.block_version or (item.batch_version is not None and batch.version != item.batch_version):
            reasons.append('数据版本已变化')
        if not batch.active or started(db, task, batch.id) or (old and old.fixed and old.status != 'cancelled'):
            reasons.append('已开工、已匹配运行或固定计划不能重排；固定计划需先说明理由解锁')
        if machine.maintenance:
            reasons.append('机台维护中')
        if not machine.capability_evidence or machine.width_mm is None or machine.height_mm is None or machine.ink_family == 'unknown':
            reasons.append('机台能力尚未确认')
        elif max(fixture.width_mm, Decimal(str(process['width_mm']))) > machine.width_mm or max(fixture.height_mm, Decimal(str(process['height_mm']))) > machine.height_mm or machine.ink_family != process['ink_family']:
            reasons.append('尺寸或墨材不兼容')
        if fixture.id != process['fixture_id']:
            if fixture.version != item.fixture_version or not item.fixture_evidence or len(item.fixture_evidence.strip()) < 5:
                reasons.append('替代实体治具需要当前版本及兼容确认依据')
            if fixture.width_mm < Decimal(str(process['width_mm'])) or fixture.height_mm < Decimal(str(process['height_mm'])) or fixture.slots < process['pieces_per_board']:
                reasons.append('替代治具尺寸或槽位不足')
        file = c.get(db, m.UvOpsFileVersion, task.file_version_id)
        if not file.confirmed_at or not file.first_article_evidence:
            reasons.append('文件与首件未准备完成')
        start, end = c.ts(item.start_at), c.ts(item.end_at)
        seconds = duration(task, batch, item.manual_estimated_seconds)
        manual = process.get('cycle_seconds') is None
        if manual and (seconds is None or not item.estimate_reason or len(item.estimate_reason.strip()) < 5):
            reasons.append('节拍未知时请填写人工估时及依据')
        if not manual and item.manual_estimated_seconds is not None:
            reasons.append('已有冻结标准节拍，不允许用人工估时覆盖')
        if end <= start:
            reasons.append('结束时间必须晚于开始时间')
        elif seconds is not None and Decimal(str((item.end_at-item.start_at).total_seconds())) < seconds:
            reasons.append('时间窗口短于本批次所需时间')
        for other in occupied:
            if other.id in replacing or other.start_at >= end or other.end_at <= start:
                continue
            if other.machine_id == machine.id or fixtures[fixture_for(other, lookup[other.task_id])].code == fixture.code:
                reasons.append('机台或共享治具与现有任务冲突')
        for actual, expected_end in actual_windows:
            same_resource=actual.machine_id==machine.id or actual.fixture_code==fixture.code
            if actual.started_at<end and expected_end>start and same_resource:
                reasons.append('机台或治具已有实际执行占用，请先核对完工')
            elif same_resource and actual.ended_at is None:
                warnings.append('机台或治具尚未实际完工；本计划按预计释放时间预留，实际开工仍须先确认前批完工，超时需重排')
        for other in blocks:
            if other['start_at'] < end and other['end_at'] > start and (other['machine_id'] == machine.id or fixtures[other['fixture_id']].code == fixture.code):
                reasons.append('本次排程内机台或治具重复占用')
        if reasons:
            conflicts.append(dict(task_id=task.id, batch_id=batch.id, reasons=list(dict.fromkeys(reasons))))
        demand = c.get(db, m.UvOpsDemand, task.demand_id)
        changes.append(dict(task_id=task.id, batch_id=batch.id, previous_start_at=old.start_at if old else None, previous_end_at=old.end_at if old else None, due_at=demand.due_at, delay_seconds=max(0, (item.end_at-datetime.fromisoformat(demand.due_at)).total_seconds())))
        blocks.append(dict(task_id=task.id, batch_id=batch.id, machine_id=machine.id, fixture_id=fixture.id, fixture_evidence=item.fixture_evidence, start_at=start, end_at=end, fixed=item.fixed, estimate_basis='manual' if manual else 'standard', estimated_seconds=seconds, estimate_reason=item.estimate_reason if manual else None, block_id=old.id if old else None))
    return dict(blocks=blocks, conflicts=conflicts, changes=changes, warnings=list(dict.fromkeys(warnings)), can_commit=not conflicts, rationale='按实体批次数量、冻结节拍或人工估时检查机台与治具；只修改选中计划，不自动移动后续任务')


def commit(db, user, body):
    result = preview(db, body, lock=True)
    c.require(result['can_commit'], 'schedule_conflict', '；'.join(reason for x in result['conflicts'] for reason in x['reasons']))
    saved = []
    for block in result['blocks']:
        values = {key: value for key, value in block.items() if key != 'block_id'}
        if block['block_id']:
            row = c.get(db, m.UvOpsScheduleBlock, block['block_id'], lock=True)
            for key, value in values.items():
                setattr(row, key, value)
            row.status = 'planned'
            c.touch(row)
        else:
            row = c.add(db, m.UvOpsScheduleBlock, user, **values)
        saved.append(c.record(row))
    for task_id in sorted({row['task_id'] for row in saved}):
        task = c.get(db, m.UvOpsTask, task_id, lock=True)
        if task.status == 'ready':
            task.status = 'planned'
        c.touch(task)
    return dict(blocks=saved)


def change_plan(db, user, entity_id, body, *, cancel=False):
    source = c.get(db, m.UvOpsScheduleBlock, entity_id)
    task = c.get(db, m.UvOpsTask, source.task_id, lock=True)
    row = c.get(db, m.UvOpsScheduleBlock, entity_id, lock=True, version=body.expected_version)
    c.require(len(body.reason.strip()) >= 5, 'reason_required', '请说明撤销或解锁原因', 422)
    c.require(not started(db, task, row.batch_id), 'plan_started', '已有运行或核数的计划不能撤销或解锁')
    if cancel:
        row.status = 'cancelled'
    else:
        row.fixed = False
    c.touch(row)
    c.touch(task)
    return c.record(row)


def recommendations(db, task, *, batch_id=None, earliest_at=None, manual_seconds=None):
    candidates = task_batches(db, task)
    if batch_id:
        candidates = [x for x in candidates if x.id == batch_id]
    if len(candidates) != 1:
        return []
    batch = candidates[0]
    seconds = duration(task, batch, manual_seconds)
    if seconds is None:
        return []
    process = task.process_snapshot
    fixture = c.get(db, m.UvOpsFixture, process['fixture_id'])
    demand = c.get(db, m.UvOpsDemand, task.demand_id)
    def minute_ceiling(value):
        return value.replace(second=0,microsecond=0)+(timedelta(minutes=1) if value.second or value.microsecond else timedelta())
    earliest = minute_ceiling(datetime.fromisoformat(c.ts(earliest_at or datetime.now(UTC))))
    plans = list(db.scalars(c.query(m.UvOpsScheduleBlock).where(m.UvOpsScheduleBlock.status != 'cancelled', m.UvOpsScheduleBlock.end_at > c.ts(earliest))))
    lookup = {x.id: x for x in db.scalars(c.query(m.UvOpsTask).where(m.UvOpsTask.id.in_({x.task_id for x in plans} | {task.id})))}
    fixture_codes = {x.id:x.code for x in db.scalars(c.query(m.UvOpsFixture))}
    running=list(db.scalars(c.query(m.UvOpsExecution).where(m.UvOpsExecution.ended_at.is_(None))))
    actual_windows=execution_windows(db,running)
    results = []
    for machine in db.scalars(c.query(m.UvOpsMachine)):
        compatible = bool(machine.capability_evidence and not machine.maintenance and machine.width_mm and machine.height_mm and machine.width_mm >= max(fixture.width_mm, Decimal(str(process['width_mm']))) and machine.height_mm >= max(fixture.height_mm, Decimal(str(process['height_mm']))) and machine.ink_family == process['ink_family'])
        current=[(x,end) for x,end in actual_windows if x.machine_id==machine.id or x.fixture_code==fixture.code]
        occupied = [x for x in plans if not (x.task_id == task.id and x.batch_id in {None, batch.id}) and (x.machine_id == machine.id or fixture_codes[fixture_for(x, lookup[x.task_id])] == fixture.code)]
        start = earliest
        # The operator's datetime-local form has minute precision. Reserve a
        # complete minute-aligned duration before looking for a free window.
        delta = timedelta(minutes=ceil(seconds/60))
        windows=[(x.start_at,x.end_at) for x in occupied]+[(x.started_at,end) for x,end in current]
        for begin,finish in sorted(windows):
            a, b = datetime.fromisoformat(begin), datetime.fromisoformat(finish)
            if b <= start:
                continue
            if a >= start + delta:
                break
            start = minute_ceiling(b)
        machine_plans = [x for x in plans if x.machine_id == machine.id]
        load = sum((datetime.fromisoformat(x.end_at)-datetime.fromisoformat(x.start_at)).total_seconds() for x in machine_plans)
        previous = max((x for x in machine_plans if x.end_at <= c.ts(start)), key=lambda x: x.end_at, default=None)
        same_setup = bool(previous and lookup[previous.task_id].process_version_id == task.process_version_id)
        results.append(dict(machine_id=machine.id, batch_id=batch.id, compatible=compatible, start_at=c.ts(start), end_at=c.ts(start+delta), earliest_after=c.ts(start), estimated_seconds=seconds, estimate_basis='manual' if process.get('cycle_seconds') is None else 'standard', planned_tasks=len(machine_plans), load_seconds=load, same_setup=same_setup, delay_seconds=max(0, (start+delta-datetime.fromisoformat(demand.due_at)).total_seconds()), reason='可用窗口，已避开机台与共享治具；同工艺相邻可减少换型' if compatible else '能力未知、维护或尺寸/墨材不兼容'))
        if compatible and current:
            results[-1]['reason']+='；资源尚在执行，按预计释放时间预留，实际开工前必须核对完工'
    return sorted(results, key=lambda x: (not x['compatible'], x['end_at'], not x['same_setup'], x['load_seconds'], x['machine_id']))
