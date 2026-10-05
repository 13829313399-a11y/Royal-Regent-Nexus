"""Explicit manual execution evidence, separate from device Run and output."""
from hashlib import sha256
from decimal import Decimal
from sqlalchemy import text
from app.models import uv_operations as m
from . import common as c, production as p, planning


def start(db, user, entity_id, body):
    shift = p.shift_open(db, body.shift_id)
    source = c.get(db, m.UvOpsScheduleBlock, entity_id)
    task = c.get(db, m.UvOpsTask, source.task_id, lock=True)
    source = c.get(db, m.UvOpsScheduleBlock, entity_id, lock=True, version=body.expected_version)
    candidates = planning.task_batches(db, task)
    batch_id = source.batch_id or (candidates[0].id if len(candidates) == 1 else None)
    c.require(batch_id is not None, 'batch_required', '旧整任务计划无法确定实体批次，请先撤销重排')
    batch = c.get(db, m.UvOpsBatch, batch_id, lock=True)
    machine = c.get(db, m.UvOpsMachine, source.machine_id, lock=True)
    plan = c.get(db, m.UvOpsScheduleBlock, entity_id, lock=True, version=body.expected_version)
    fixture = c.get(db, m.UvOpsFixture, planning.fixture_for(plan, task))
    if db.bind.dialect.name == 'postgresql':
        key = int.from_bytes(sha256(('uv-fixture:'+fixture.code).encode()).digest()[:8], 'big', signed=True)
        db.execute(text('SELECT pg_advisory_xact_lock(:key)'), dict(key=key))
    c.require(plan.status != 'cancelled' and task.status not in {'cancelled','completed'} and batch.active and not machine.maintenance, 'execution_unavailable', '计划、批次或机台当前不可开工')
    process=task.process_snapshot
    c.require(machine.capability_evidence and machine.width_mm and machine.height_mm and machine.width_mm>=max(fixture.width_mm,Decimal(str(process['width_mm']))) and machine.height_mm>=max(fixture.height_mm,Decimal(str(process['height_mm']))) and machine.ink_family==process['ink_family'], 'machine_capability', '机台能力已变化，请重新核对布局与墨材',422)
    c.require(not planning.started(db, task, batch.id), 'batch_started', '本任务批次已有开工或核数依据，不能重复开工')
    started = c.ts(body.started_at)
    c.require(shift.start_at <= started < shift.end_at, 'execution_shift', '开工时间必须在所选班次内', 422)
    busy = db.scalar(c.query(m.UvOpsExecution).where(m.UvOpsExecution.active_key == 1, (m.UvOpsExecution.machine_id == machine.id) | (m.UvOpsExecution.batch_id == batch.id) | (m.UvOpsExecution.fixture_code == fixture.code)))
    c.require(busy is None, 'resource_running', '机台、治具或批次仍有未完工记录，请先核对')
    # Backfilled completed intervals cannot overlap either physical resource.
    overlap = db.scalar(c.query(m.UvOpsExecution).where((m.UvOpsExecution.machine_id == machine.id) | (m.UvOpsExecution.fixture_code == fixture.code) | (m.UvOpsExecution.batch_id == batch.id), (m.UvOpsExecution.ended_at.is_(None)) | (m.UvOpsExecution.ended_at > started)))
    c.require(overlap is None, 'execution_overlap', '实际时间与已有运行区间重叠，请核对开工时间')
    row = c.add(db, m.UvOpsExecution, user, task_id=task.id, batch_id=batch.id, machine_id=machine.id, schedule_id=plan.id, fixture_code=fixture.code, shift_id=shift.id, started_at=started, start_evidence=body.evidence)
    task.status = 'in_progress'
    c.touch(task)
    return c.record(row)


def finish(db, user, entity_id, body):
    source = c.get(db, m.UvOpsExecution, entity_id)
    shift = p.shift_open(db, body.shift_id)
    c.get(db, m.UvOpsTask, source.task_id, lock=True)
    c.get(db, m.UvOpsBatch, source.batch_id, lock=True)
    c.get(db, m.UvOpsMachine, source.machine_id, lock=True)
    row = c.get(db, m.UvOpsExecution, entity_id, lock=True, version=body.expected_version)
    ended = c.ts(body.ended_at)
    c.require(row.active_key == 1 and row.ended_at is None, 'execution_finished', '该执行记录已完工')
    c.require(ended > row.started_at, 'execution_interval', '完工时间必须晚于开工时间', 422)
    c.require(shift.start_at <= ended <= shift.end_at, 'execution_shift', '完工时间必须在当前完工班次内', 422)
    row.ended_shift_id = shift.id
    row.ended_at, row.end_evidence, row.active_key = ended, body.evidence, None
    c.touch(row)
    return c.record(row)
