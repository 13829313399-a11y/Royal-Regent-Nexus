from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import secrets
import json
from pydantic import ValidationError
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError, DataError
from app.models import uv_operations as m
from app.schemas import uv_operations as s
from . import common as c


def token_hash(value):
    return sha256(value.encode()).hexdigest()


def create_agent(db, user, body):
    code = secrets.token_urlsafe(32)
    row = c.add(db, m.UvOpsAgent, user, name=body.name, pairing_hash=token_hash(code), pairing_expires_at=c.ts(datetime.now(UTC)+timedelta(minutes=15)))
    return dict(agent=c.record(row), pairing_code=code, expires_at=row.pairing_expires_at)


def enroll(db, body):
    # The client generates and durably saves token + enrollment_id BEFORE sending.
    # Lost enrollment responses can be retried with that same proof of possession.
    row = db.scalar(c.query(m.UvOpsAgent).where(m.UvOpsAgent.token_hash == token_hash(body.token), m.UvOpsAgent.enrollment_id == body.enrollment_id, m.UvOpsAgent.enrollment_pairing_hash == token_hash(body.pairing_code)).with_for_update().execution_options(populate_existing=True))
    if row is not None and not row.revoked:
        return dict(agent_id=row.id, factory_id=m.FACTORY)
    row = db.scalar(c.query(m.UvOpsAgent).where(m.UvOpsAgent.pairing_hash == token_hash(body.pairing_code)).with_for_update().execution_options(populate_existing=True))
    c.require(row is not None and not row.revoked and row.pairing_expires_at >= c.ts(datetime.now(UTC)), "pairing_invalid", "配对码已失效、已使用或被撤销", 401)
    changed = db.execute(update(m.UvOpsAgent).where(m.UvOpsAgent.id == row.id, m.UvOpsAgent.pairing_hash == token_hash(body.pairing_code), m.UvOpsAgent.token_hash.is_(None), m.UvOpsAgent.revoked.is_(False)).values(pairing_hash=None, token_hash=token_hash(body.token), enrollment_id=body.enrollment_id, enrollment_pairing_hash=token_hash(body.pairing_code), version=m.UvOpsAgent.version+1, updated_at=m.now()))
    c.require(changed.rowcount == 1, "pairing_invalid", "配对码已经被其他请求使用", 401)
    db.commit()
    return dict(agent_id=row.id, factory_id=m.FACTORY)


def authenticate(db, authorization):
    c.require(authorization.startswith("Bearer "), "agent_unauthorized", "代理凭据无效", 401)
    token = authorization[7:]
    row = db.scalar(c.query(m.UvOpsAgent).where(m.UvOpsAgent.token_hash == token_hash(token)))
    c.require(row is not None and not row.revoked, "agent_unauthorized", "代理凭据已撤销或无效", 401)
    return row


def bind_source(db, user, body):
    agent = c.get(db, m.UvOpsAgent, body.agent_id, lock=True)
    c.require(not agent.revoked and agent.token_hash, "agent_not_enrolled", "请先完成代理配对")
    machine = c.get(db, m.UvOpsMachine, body.machine_id, lock=True)
    active_source_key = c.digest(dict(agent=agent.id, source=body.source_id))
    occupied = db.scalar(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.active_source_key == active_source_key))
    c.require(occupied is None or occupied.machine_id == machine.id, 'source_already_bound', '同一代理采集源已绑定其他机台；请先解除原绑定')
    old = db.scalar(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.active_key == machine.id))
    if old:
        old.active_key = None
        old.active_source_key = None
        c.touch(old)
        db.flush()
    versions = list(db.scalars(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.agent_id == agent.id, m.UvOpsSourceBinding.source_id == body.source_id)))
    version = max((x.binding_version for x in versions), default=0)+1
    # Capability truth is constrained to this shipped adapter, never browser claims.
    capabilities = dict(observeAvailability=True, observeRuntimeState=True, observeProgress=False, observeNativeJobId=True, observeCompletedJobs=True, observePieceCount=True, countUnit="unknown", observeInkUsage=False, inkEvidence="none", stageProductionFile=False, submitNativeJob=False, pauseNativeJob=False, cancelNativeJob=False, needsInteractiveSession=False, evidenceLevel="inferred" if body.adapter_type == "simulator" else "vendor_log", fixture_only=True)
    row = c.add(db, m.UvOpsSourceBinding, user, **c.values(body, "capabilities"), binding_version=version, active_key=machine.id, active_source_key=active_source_key, capabilities=capabilities)
    return c.record(row)


def unbind_source(db, user, entity_id, body):
    source = c.get(db, m.UvOpsSourceBinding, entity_id)
    # Same identity -> machine -> binding order as enrollment/event writers.
    c.get(db, m.UvOpsAgent, source.agent_id, lock=True)
    c.get(db, m.UvOpsMachine, source.machine_id, lock=True)
    source = c.get(db, m.UvOpsSourceBinding, entity_id, lock=True, version=body.expected_version)
    c.require(source.active_key is not None, 'source_inactive', '采集源已经解除绑定')
    c.require(len(body.reason.strip()) >= 5, 'reason_required', '解除绑定需填写具体理由', 422)
    source.active_key = source.active_source_key = None
    c.touch(source)
    return c.record(source)


def revoke(db, user, entity_id, body):
    row = c.get(db, m.UvOpsAgent, entity_id, lock=True, version=body.expected_version)
    c.require(body.reason.strip(), "reason_required", "撤销代理需填写理由", 422)
    row.revoked = True
    row.pairing_hash = None
    c.touch(row)
    return c.record(row)


def decimal_or_none(value):
    if value is None:
        return None
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number >= Decimal("1000000000000") or number.as_tuple().exponent < -6:
            raise ValueError()
        return number
    except (InvalidOperation, ValueError, TypeError):
        raise c.DomainError("invalid_measurement", "原始计量值必须为有限非负数且至多六位小数", 422) from None


def event(db, agent_id, raw):
    body = s.AgentEvent.model_validate(raw)
    # Hold the identity lock only for this event transaction. Revocation takes
    # the same row lock and is rechecked before every subsequent event.
    agent = c.get(db, m.UvOpsAgent, agent_id, lock=True)
    c.require(not agent.revoked, "agent_revoked", "代理凭据已撤销", 401)
    digest = c.digest(body.model_dump(mode="json"))
    duplicate = db.scalar(c.query(m.UvOpsAgentEventInbox).where(m.UvOpsAgentEventInbox.agent_id == agent.id, or_(m.UvOpsAgentEventInbox.event_id == body.event_id, (m.UvOpsAgentEventInbox.stream_id == body.stream_id) & (m.UvOpsAgentEventInbox.sequence == body.sequence))))
    if duplicate:
        c.require(duplicate.payload_hash == digest, "event_payload_conflict", "事件编号或序号已用于其他载荷")
        return dict(event_id=body.event_id, status="duplicate", sequence=body.sequence)
    c.get(db, m.UvOpsMachine, body.machine_id, lock=True)
    binding = db.scalar(c.query(m.UvOpsSourceBinding).where(m.UvOpsSourceBinding.agent_id == agent.id, m.UvOpsSourceBinding.machine_id == body.machine_id, m.UvOpsSourceBinding.source_id == body.source_id, m.UvOpsSourceBinding.binding_version == body.binding_version).with_for_update().execution_options(populate_existing=True))
    c.require(binding is not None and binding.adapter_type == body.adapter_type, "binding_invalid", "机台、采集源或绑定版本不属于此代理", 403)
    c.require(body.observed_at <= datetime.now(UTC)+timedelta(minutes=5), "future_event", "设备时间超前超过五分钟", 422)
    payload = body.payload
    for key, maximum in [('native_job_id',128), ('file_name',200), ('file_hash',64), ('task_token',64)]:
        value = payload.get(key)
        c.require(value is None or isinstance(value,str) and len(value) <= maximum, 'invalid_payload_field', '原始作业字段类型或长度不符合约定', 422)
    c.require(len(json.dumps(body.model_dump(mode='json')).encode()) <= 128*1024, 'event_size', '单条事件证据超过 128 KB', 422)
    machine_code = body.evidence.get('machine_code')
    if machine_code is not None:
        machine = c.get(db, m.UvOpsMachine, body.machine_id)
        c.require(machine_code == machine.code, 'source_machine_mismatch', '日志机台编号与绑定机台不一致', 422)
    cursor = db.scalar(c.query(m.UvOpsSourceCursor).where(m.UvOpsSourceCursor.binding_id == binding.id))
    c.require(not binding.active_key or cursor is None or cursor.stream_id == body.stream_id, 'stream_rebind_required', '本地事件流已更换，需管理员重新确认采集源绑定', 409)
    unit, mode = payload.get("count_unit", "unknown"), payload.get("counter_mode", "unknown")
    c.require(unit in {"pcs", "board", "pass", "unknown"} and mode in {"cumulative", "delta", "unknown"}, "count_semantics", "计量单位或计数模式无效", 422)
    count, ink = decimal_or_none(payload.get("count")), decimal_or_none(payload.get("ink_total_ml"))
    c.require(count is None or (unit != "unknown" and mode != "unknown"), "count_semantics", "有计数时必须明确单位和累计/增量语义", 422)
    observed = c.ts(body.observed_at)
    period = c.lock_period(db, body.observed_at.astimezone(__import__('zoneinfo').ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d'), allow_closed=True)
    evidence = body.model_dump(mode="json") | dict(data_mode="synthetic" if binding.adapter_type == "simulator" else "fixture_log")
    inbox = c.add(db, m.UvOpsAgentEventInbox, agent_id=agent.id, machine_id=body.machine_id, binding_id=binding.id, event_id=body.event_id, stream_id=body.stream_id, sequence=body.sequence, observed_at=observed, kind=body.kind, payload_hash=digest, evidence=evidence, late_closed_period=bool(period and period.status == "closed"))
    if period.status == 'closed':
        # Preserve late evidence in the review inbox without changing any
        # previously closed run, live cursor, wage or report projection.
        db.commit()
        return dict(event_id=inbox.event_id,status='persisted',sequence=body.sequence,disposition='late_evidence_review')
    native_id = payload.get("native_job_id")
    if body.kind != "snapshot":
        c.require(isinstance(native_id, str) and 0 < len(native_id) <= 128, "native_job_required", "运行事件必须有稳定原生任务编号", 422)
        generation = str(body.source_identity.get("generation", ""))
        c.require(generation, "generation_required", "必须提供采集源代次", 422)
        job_identity = body.source_identity.get('job_identity') or c.digest(dict(generation=generation,native_job_id=native_id))
        c.require(isinstance(job_identity,str) and len(job_identity)<=128, 'job_identity_invalid', '作业生命周期标识无效',422)
        native_identity = c.digest(dict(agent_id=agent.id,source_id=body.source_id,job_identity=job_identity))
        run = db.scalar(c.query(m.UvOpsRun).where(m.UvOpsRun.native_identity == native_identity))
        c.require(run is None or run.machine_id == body.machine_id, 'job_machine_changed', '同一原生作业不能跨机台重绑定',409)
        if run is None:
            run = c.add(db, m.UvOpsRun, machine_id=body.machine_id, binding_id=binding.id, native_job_id=native_id, native_identity=native_identity, started_at=observed, last_observed_at=observed, last_sequence=0, file_name=str(payload.get("file_name", ""))[:200], file_hash=payload.get("file_hash"), task_token=payload.get("task_token"), count_unit=unit, counter_mode=mode)
        c.require(run.count_unit in {unit, "unknown"} and run.counter_mode in {mode, "unknown"}, "count_semantics_changed", "运行中的计数语义发生变化，需核实新作业身份", 422)
        run.started_at = min(run.started_at, observed)
        newer = body.binding_version >= run.last_binding_version and (observed > run.last_observed_at or observed == run.last_observed_at and (body.binding_version > run.last_binding_version or run.last_stream_id == body.stream_id and body.sequence > run.last_sequence or run.last_stream_id is None))
        if count is not None:
            if mode == "delta":
                run.raw_count = (run.raw_count or Decimal(0))+count
            elif newer:
                c.require(run.raw_count is None or count >= run.raw_count, "counter_reset", "累计计数回退，需确认是否开始了新原生作业", 422)
                run.raw_count = count
            run.count_unit, run.counter_mode = unit, mode
        if newer:
            run.last_observed_at = observed
            run.last_sequence = body.sequence
            run.last_stream_id = body.stream_id
            run.last_binding_version = body.binding_version
            if ink is not None:
                run.ink_total_ml = ink
            if body.kind in {"job_complete", "job_failed", "job_cancelled"}:
                run.state = {"job_complete":"completed", "job_failed":"failed", "job_cancelled":"cancelled"}[body.kind]
                run.ended_at = observed
        c.touch(run)
    if binding.active_key and cursor is None:
        cursor = c.add(db, m.UvOpsSourceCursor, binding_id=binding.id, stream_id=body.stream_id, sequence=0, observed_at=observed)
    if binding.active_key and cursor.stream_id == body.stream_id and body.sequence > cursor.sequence and observed >= cursor.observed_at:
        state = payload.get("work_state", "unknown")
        c.require(state in {"idle", "running", "paused", "fault", "unknown"}, "work_state", "工作状态无效", 422)
        cursor.sequence, cursor.observed_at = body.sequence, observed
        cursor.work_state, cursor.native_job_id = state, native_id
        cursor.progress = None  # Current adapters do not prove actual print progress.
        cursor.progress_meaning = "unknown"
        c.touch(cursor)
    db.commit()
    return dict(event_id=inbox.event_id, status="persisted", sequence=body.sequence)


def batch(db, agent_id, body):
    results = []
    for raw in body.events:
        try:
            results.append(event(db, agent_id, raw))
        except (c.DomainError, ValidationError, IntegrityError, DataError) as error:
            db.rollback()
            results.append(dict(event_id=raw.get("event_id"), status="rejected", retryable=isinstance(error,c.DomainError) and error.body["code"]=="stream_rebind_required", code=error.body["code"] if isinstance(error, c.DomainError) else "invalid_event", message=error.body["message"] if isinstance(error, c.DomainError) else "事件格式或身份冲突，已隔离；其他事件可继续传输"))
    # A maximum sequence is deliberately not an acknowledgment of missing events.
    return dict(batch_id=body.batch_id, results=results)


def match_run(db, user, entity_id, body):
    run = c.get(db, m.UvOpsRun, entity_id, lock=True, version=body.expected_version)
    c.require(run.match_evidence is None, "already_matched", "该运行已有确认分配，不允许覆盖")
    c.require(sum((x.share for x in body.allocations), Decimal(0)) == 1, "allocation_shares", "运行成本与工时分摊比例之和必须为 100%", 422)
    # Serialize with task cancellation and batch split/merge. Lock shared roots
    # in stable order before their batches, matching production's lock order.
    task_ids = {item.task_id for item in body.allocations}
    task_ids |= {task.parent_task_id for key in sorted(task_ids) if (task := c.get(db,m.UvOpsTask,key)).parent_task_id}
    tasks = {key:c.get(db,m.UvOpsTask,key,lock=True) for key in sorted(task_ids)}
    batches = {key:c.get(db,m.UvOpsBatch,key,lock=True) for key in sorted({item.batch_id for item in body.allocations})}
    occupied, allocations, pass_fixtures = set(), [], {}
    for item in body.allocations:
        task = tasks[item.task_id]
        batch = batches[item.batch_id]
        fixture = c.get(db, m.UvOpsFixture, task.process_snapshot["fixture_id"])
        c.require(pass_fixtures.setdefault(item.pass_index,fixture.id)==fixture.id,"allocation_fixture","同一运行工序的拼版必须使用同一物理治具",422)
        if task.parent_task_id:
            binding=db.scalar(c.query(m.UvOpsReworkBinding).where(m.UvOpsReworkBinding.task_id==task.id))
            c.require(binding and binding.batch_id==batch.id,"allocation_task","返工任务只能分配到其绑定批次",422)
        c.require(batch.active and task.status!="cancelled","batch_superseded","不能分配到已替换批次或已取消任务")
        c.require(batch.task_id == (task.parent_task_id or task.id) and 1 <= item.pass_index <= task.process_snapshot["passes"], "allocation_task", "分配批次或工序与任务不符", 422)
        slots = {(item.pass_index, slot) for slot in item.slots}
        c.require(len(slots) == len(item.slots) and all(1 <= slot <= fixture.slots for slot in item.slots) and not (occupied & slots), "allocation_slots", "同一工序槽位不得重复占用且必须在治具范围内", 422)
        c.require(item.tail_pieces <= len(item.slots), "tail_board", "尾板件数不能超过占用槽位数", 422)
        occupied |= slots
        allocation = c.add(db, m.UvOpsRunAllocation, user, run_id=run.id, **item.model_dump())
        allocations.append(c.record(allocation) | dict(suggested_pieces=item.full_boards*len(item.slots)+item.tail_pieces, quantity_source="confirmed_layout_suggestion"))
    run.match_evidence = body.evidence
    c.touch(run)
    return dict(run=c.record(run), allocations=allocations, production_created=False)
