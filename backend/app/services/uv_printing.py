"""Transactional UV commands and one authoritative production projection."""
from copy import deepcopy
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import importlib.util
import json
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, func, update, text
from app.models import uv_printing as m
from app.schemas.uv_printing import COMMAND_SCHEMAS

D = Decimal
FACTORY = "huakang-a"
ACTIVE = ("confirmed", "corrected")
ACTIONS = {}
QUALITY = ("reported_qty", "good_qty", "defective_qty", "pending_qty", "semi_finished_qty")


def fail(message, status=422):
    raise HTTPException(status, message)


def currency_places(currency):
    places = {"HKD": 2, "CNY": 2, "USD": 2, "EUR": 2, "GBP": 2, "JPY": 0}
    if currency not in places:
        fail("此币种的最小货币单位尚未配置")
    return places[currency]


def money(amount, currency):
    if amount is None or not currency:
        return None
    rounded = D(amount).quantize(D(1).scaleb(-currency_places(currency)), rounding=ROUND_HALF_UP)
    return {"currency": currency, "amount": format(rounded, "f")}


def sum_money(values):
    values = list(values)
    if not values or any(v is None for v in values):
        return None
    currencies = {v["currency"] for v in values}
    if len(currencies) != 1:
        return None
    return money(sum((D(v["amount"]) for v in values), D(0)), values[0]["currency"])


def serial(row, exclude=()):
    return {c.name: format(value, "f") if isinstance(value, D) else value
            for c in row.__table__.columns if c.name not in exclude
            for value in [getattr(row, c.name)]}


def find(db, cls, factory, ident):
    row = db.scalar(select(cls).where(cls.id == ident, cls.factory_id == factory))
    if row is None:
        fail("记录不存在或不在当前厂区", 404)
    return row


def lock(db, factory):
    if factory != FACTORY:
        fail("UV打印只允许华康A生产部", 403)
    # Serialize every UV factory write, including first-row creation and all
    # extensions. PostgreSQL advisory locks live until commit/rollback.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(20260913, 112)"))
    else:
        db.execute(update(m.UvFactory).where(m.UvFactory.factory_id == factory).values(version=m.UvFactory.version + 1))
    row = db.get(m.UvFactory, factory)
    if row is None:
        db.add(m.UvFactory(factory_id=factory, version=0))
        db.flush()


def guard_open(db, factory, business_date):
    if importlib.util.find_spec("app.services.uv_finance"):
        from app.services.uv_finance import ensure_open
        ensure_open(db, factory, business_date)


def version(row, expected):
    if (row.version if row else 0) != expected:
        fail("记录版本已变化，请刷新后重试", 409)


def bump(row):
    row.version += 1
    row.updated_at = m.now()


def data_fields(payload, exclude=()):
    return {k: v for k, v in payload.items() if k not in ("id", "factory_id", "operation_id", "expected_version", *exclude)}


def execute(db, factory, actor, action, payload):
    if action in COMMAND_SCHEMAS:
        try:
            payload = COMMAND_SCHEMAS[action].model_validate(payload).model_dump(mode="json")
        except ValidationError as exc:
            fail("；".join(e["msg"] for e in exc.errors()))
    if not payload.get("operation_id") or not isinstance(payload.get("operation_id"), str):
        fail("operation_id 必填")
    lock(db, factory)
    fingerprint = sha256(json.dumps({"action": action, "payload": payload}, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    receipt = db.scalar(select(m.UvOperation).where(m.UvOperation.factory_id == factory, m.UvOperation.actor_id == actor, m.UvOperation.operation_id == payload["operation_id"]))
    if receipt:
        if receipt.fingerprint != fingerprint:
            fail("同一 operation_id 已用于不同请求", 409)
        return {"entity": deepcopy(receipt.result["entity"]), "operation_id": receipt.operation_id, "replayed": True}
    if action not in ACTIONS:
        fail("此能力尚未启用", 503)
    entity = ACTIONS[action](db, factory, actor, payload)
    db.flush()
    result = {"entity": entity, "operation_id": payload["operation_id"], "replayed": False}
    db.add(m.UvOperation(factory_id=factory, actor_id=actor, operation_id=payload["operation_id"], command=action, fingerprint=fingerprint, result=result))
    db.flush()
    return result


def save_master(db, factory, actor, payload, cls):
    row = find(db, cls, factory, payload["id"]) if payload.get("id") else None
    version(row, payload["expected_version"])
    fields = data_fields(payload)
    if cls is m.UvMachine:
        if row is None and (not fields.get("code") or not fields.get("name")):
            fail("新机台必须填写机号与名称")
        fields = {k: v for k, v in fields.items() if v is not None or k == "price_group"}
    if cls is m.UvWorker and fields.get("employee_profile_id"):
        # No implicit link to identities outside this factory. A directory
        # linking workflow is intentionally separate from local worker CRUD.
        fail("员工档案绑定需经过独立身份核对；当前请使用UV工号")
    if row:
        for key, value in fields.items():
            setattr(row, key, value)
        bump(row)
    else:
        row = cls(factory_id=factory, **fields)
        db.add(row)
    db.flush()
    return entity_output(db, row)


def save_process(db, factory, actor, p):
    product = find(db, m.UvProduct, factory, p["product_id"])
    # A new immutable child uses version 0, independent of its parent.
    version(None, p["expected_version"])
    if not product.is_active:
        fail("产品已停用")
    fields = data_fields(p)
    fields["pricing_area_cm2"] = None if p["width_cm"] is None or p["length_cm"] is None else D(p["width_cm"]) * D(p["length_cm"])
    row = m.UvProcessVersion(factory_id=factory, **fields)
    db.add(row)
    db.flush()
    return serial(row)


def date_overlap(a, b, c, d):
    return a <= (d or "9999-12-31") and c <= (b or "9999-12-31")


def save_rate(db, factory, actor, p):
    currency_places(p["currency"])
    prior = None
    if p.get("id"):
        prior = find(db, m.UvRateVersion, factory, p["id"])
        version(prior, p["expected_version"])
        if p["effective_from"] <= prior.effective_from:
            fail("新价规必须使用晚于旧版本的生效日期", 409)
        if any(getattr(prior, k) != p[k] for k in ("rate_kind", "product_id", "process_version_id", "machine_id", "price_group", "currency")):
            fail("更新版本不能改变价规作用域；请另建价规")
        prior.effective_to = (date.fromisoformat(p["effective_from"]) - timedelta(days=1)).isoformat()
        bump(prior)
    else:
        version(None, p["expected_version"])
    for field, cls in (("product_id", m.UvProduct), ("process_version_id", m.UvProcessVersion), ("machine_id", m.UvMachine)):
        if p[field]:
            row = find(db, cls, factory, p[field])
            if field == "process_version_id" and row.product_id != p["product_id"]:
                fail("工艺与产品不匹配")
    scope_keys = ("rate_kind", "product_id", "process_version_id", "machine_id", "price_group", "currency")
    for row in db.scalars(select(m.UvRateVersion).where(m.UvRateVersion.factory_id == factory)):
        if all(getattr(row, key) == p[key] for key in scope_keys) and date_overlap(row.effective_from, row.effective_to, p["effective_from"], p["effective_to"]):
            fail("相同作用域的价规生效区间重叠")
    row = m.UvRateVersion(factory_id=factory, **data_fields(p))
    db.add(row)
    db.flush()
    return serial(row)


def save_template(db, factory, actor, p):
    if p.get("id"):
        find(db, m.UvShiftTemplate, factory, p["id"])
        fail("班次模板必须新增版本，不能更改历史模板", 409)
    version(None, p["expected_version"])
    for row in db.scalars(select(m.UvShiftTemplate).where(m.UvShiftTemplate.factory_id == factory, m.UvShiftTemplate.shift == p["shift"])):
        if date_overlap(row.effective_from, row.effective_to, p["effective_from"], p["effective_to"]):
            fail("同班次模板生效区间重叠")
    row = m.UvShiftTemplate(factory_id=factory, **data_fields(p))
    db.add(row)
    db.flush()
    return serial(row)


def validate_workers(db, factory, ids, day):
    workers = [find(db, m.UvWorker, factory, ident) for ident in ids]
    if any(w.employ_state == "left" and (w.left_on is None or day >= w.left_on) for w in workers):
        fail("报工日期存在已离职人员")
    return sorted(workers, key=lambda w: w.id)


def save_assignment(db, factory, actor, p):
    guard_open(db, factory, p["business_date"])
    find(db, m.UvMachine, factory, p["machine_id"])
    batch = db.scalar(select(m.UvAssignmentBatch).where(m.UvAssignmentBatch.factory_id == factory, m.UvAssignmentBatch.business_date == p["business_date"], m.UvAssignmentBatch.shift == p["shift"], m.UvAssignmentBatch.machine_id == p["machine_id"]))
    version(batch, p["expected_version"])
    workers = validate_workers(db, factory, p["worker_ids"], p["business_date"])
    if batch:
        bump(batch)
        for row in db.scalars(select(m.UvAssignment).where(m.UvAssignment.work_batch == batch.id, m.UvAssignment.active.is_(True))):
            row.active = False
    else:
        batch = m.UvAssignmentBatch(factory_id=factory, business_date=p["business_date"], shift=p["shift"], machine_id=p["machine_id"])
        db.add(batch)
        db.flush()
    rows = []
    for worker in workers:
        row = m.UvAssignment(factory_id=factory, version=batch.version, business_date=p["business_date"], shift=p["shift"], machine_id=p["machine_id"], worker_id=worker.id, work_batch=batch.id, share=1, note=p["note"])
        db.add(row)
        rows.append(row)
    db.flush()
    return [entity_output(db, row) for row in rows]


def resolve_rate(db, factory, report, kind):
    machine = find(db, m.UvMachine, factory, report.machine_id)
    candidates = []
    for row in db.scalars(select(m.UvRateVersion).where(m.UvRateVersion.factory_id == factory, m.UvRateVersion.rate_kind == kind)):
        if not (row.effective_from <= report.business_date <= (row.effective_to or "9999-12-31")):
            continue
        if row.product_id and row.product_id != report.product_id or row.process_version_id and row.process_version_id != report.process_version_id:
            continue
        if row.machine_id and row.machine_id != report.machine_id or row.price_group and row.price_group != machine.price_group:
            continue
        score = (3 if row.machine_id else 2 if row.price_group else 1, int(bool(row.process_version_id)), int(bool(row.product_id)))
        candidates.append((score, row))
    if not candidates:
        return None
    # A command cannot select a currency, so ambiguity is a missing price,
    # never an exchange-rate or cross-currency fallback.
    if len({row.currency for _, row in candidates}) > 1:
        return None
    top = max(score for score, _ in candidates)
    selected = [row for score, row in candidates if score == top]
    if len(selected) != 1:
        fail("适用价规冲突，请核对生效区间", 409)
    return selected[0]


def snapshot_rates(db, factory, report, copy_from=None):
    process = find(db, m.UvProcessVersion, factory, report.process_version_id)
    for kind in ("commercial", "piece_wage", "area"):
        old = db.scalar(select(m.UvRateSnapshot).where(m.UvRateSnapshot.report_id == copy_from, m.UvRateSnapshot.rate_kind == kind)) if copy_from else None
        rate = None if old else resolve_rate(db, factory, report, kind)
        db.add(m.UvRateSnapshot(factory_id=factory, report_id=report.id, rate_kind=kind,
            rate_version_id=old.rate_version_id if old else rate.id if rate else None,
            currency=old.currency if old else rate.currency if rate else None,
            unit_price=old.unit_price if old else rate.unit_price if rate else None,
            pricing_area_cm2=old.pricing_area_cm2 if old else process.pricing_area_cm2))
    db.flush()


def create_report(db, factory, actor, p, status="draft", replaces=None, reason="", copy_snapshots=None):
    version(None, p["expected_version"])
    guard_open(db, factory, p["business_date"])
    machine = find(db, m.UvMachine, factory, p["machine_id"])
    product = find(db, m.UvProduct, factory, p["product_id"])
    process = find(db, m.UvProcessVersion, factory, p["process_version_id"])
    template = find(db, m.UvShiftTemplate, factory, p["shift_template_version_id"])
    if not machine.enabled or machine.admin_status == "disabled" or not product.is_active:
        fail("机台或产品已停用")
    if process.product_id != product.id or process.effective_from > p["business_date"]:
        fail("工艺版本不属于产品或尚未生效")
    if template.shift != p["shift"] or not (template.effective_from <= p["business_date"] <= (template.effective_to or "9999-12-31")):
        fail("班次模板与报工日期不匹配")
    workers = validate_workers(db, factory, p["worker_ids"], p["business_date"])
    if len({a["job_id"] for a in p["source_allocations"]}) != len(p["source_allocations"]):
        fail("同一来源不能重复分配")
    allocated = sum(a["piece_qty"] for a in p["source_allocations"])
    if allocated > p["reported_qty"]:
        fail("来源分配总量超过报工数量")
    row = m.UvReport(factory_id=factory, created_by=actor,
        **data_fields(p, ("worker_ids", "source_allocations", "evidence_job_ids")), product_no=product.product_no,
        product_name=product.name, status=status, replaces_report_id=replaces, correction_reason=reason,
        source_kind="device" if allocated and allocated == p["reported_qty"] else "mixed" if allocated else "manual",
        confirmed_at=m.now() if status in ACTIVE else None)
    db.add(row)
    db.flush()
    for worker in workers:
        old_worker = db.scalar(select(m.UvReportWorker).where(m.UvReportWorker.report_id == copy_snapshots, m.UvReportWorker.worker_id == worker.id)) if copy_snapshots else None
        db.add(m.UvReportWorker(factory_id=factory, report_id=row.id, worker_id=worker.id, employee_no=old_worker.employee_no if old_worker else worker.employee_no, worker_name=old_worker.worker_name if old_worker else worker.display_name))
    for allocation in p["source_allocations"]:
        job = find(db, m.UvJob, factory, allocation["job_id"])
        version(job, allocation["job_version"])
        available = job_output(db, job)["available_piece_qty"]
        if job.machine_id != row.machine_id or job.product_id != row.product_id or job.process_version_id != row.process_version_id:
            fail("来源作业与报工机台/产品/工艺不匹配")
        if available is None or job.ignored or job.state != "completed":
            fail("来源单位或完成状态尚未核清，不能分配数量")
        if allocation["piece_qty"] > available:
            fail(f"来源剩余 {available} 件，分配超量")
        db.add(m.UvAllocation(factory_id=factory, report_id=row.id, job_id=job.id, piece_qty=allocation["piece_qty"]))
        if status in ACTIVE:
            bump(job)
    for ident in p["evidence_job_ids"]:
        job = find(db, m.UvJob, factory, ident)
        if job.machine_id != row.machine_id:
            fail("证据作业机台不匹配")
        db.add(m.UvReportEvidence(factory_id=factory, report_id=row.id, job_id=ident))
    if status in ACTIVE:
        snapshot_rates(db, factory, row, copy_snapshots)
    db.flush()
    return report_output(db, row)


def report_command(db, factory, actor, p, action):
    row = find(db, m.UvReport, factory, p["report_id"])
    version(row, p["expected_version"])
    guard_open(db, factory, row.business_date)
    if importlib.util.find_spec("app.services.uv_finance"):
        from app.services.uv_finance import ensure_report_mutable
        ensure_report_mutable(db, factory, row.id)
    if row.status == "voided":
        fail("记录已作废或被修订", 409)
    if action == "confirm":
        if row.status != "draft":
            fail("只有草稿可以确认", 409)
        for allocation in db.scalars(select(m.UvAllocation).where(m.UvAllocation.report_id == row.id, m.UvAllocation.reversed.is_(False))):
            job = find(db, m.UvJob, factory, allocation.job_id)
            available = job_output(db, job)["available_piece_qty"]
            if job.machine_id != row.machine_id or job.product_id != row.product_id or job.process_version_id != row.process_version_id:
                fail("草稿来源的机台、产品或工艺已经变化，请更正草稿", 409)
            if available is None or job.ignored or job.state != "completed":
                fail("草稿来源的单位或完工状态尚未核清")
            if allocation.piece_qty > available:
                fail(f"来源目前剩余 {available} 件，无法确认草稿")
            bump(job)
        row.status, row.confirmed_at = "confirmed", m.now()
        bump(row)
        snapshot_rates(db, factory, row)
        return report_output(db, row)
    if not p["reason"].strip():
        fail("必须填写修订原因")
    if action == "quality" and row.status == "draft":
        for key in QUALITY:
            setattr(row, key, p["quality"][key])
        allocated = sum(a.piece_qty for a in db.scalars(select(m.UvAllocation).where(m.UvAllocation.report_id == row.id, m.UvAllocation.reversed.is_(False))))
        if allocated > row.reported_qty:
            fail("报工数量小于已分配来源")
        row.correction_reason = p["reason"]
        bump(row)
        db.flush()
        return report_output(db, row)
    allocations = list(db.scalars(select(m.UvAllocation).where(m.UvAllocation.report_id == row.id, m.UvAllocation.reversed.is_(False))))
    if action == "correction":
        # Ordinary quantity/quality correction must never silently detach a
        # previously counted source and make that same source available again.
        correction = p["correction"]
        if not correction["source_allocations"] and allocations:
            correction["source_allocations"] = [{"job_id": a.job_id, "piece_qty": a.piece_qty,
                "job_version": find(db, m.UvJob, factory, a.job_id).version} for a in allocations]
        if sum(a["piece_qty"] for a in correction["source_allocations"]) > correction["reported_qty"]:
            fail("更正数量小于原来源分配量；必须明确重新核对来源分配，不能静默解除来源")
        if not correction["evidence_job_ids"]:
            correction["evidence_job_ids"] = list(db.scalars(select(m.UvReportEvidence.job_id).where(m.UvReportEvidence.report_id == row.id)))
        for requested in p["correction"]["source_allocations"]:
            version(find(db, m.UvJob, factory, requested["job_id"]), requested["job_version"])
    previous_status = row.status
    row.status, row.correction_reason = "voided", p["reason"]
    bump(row)
    for a in allocations:
        a.reversed = True
        bump(a)
        if previous_status in ACTIVE:
            bump(find(db, m.UvJob, factory, a.job_id))
    db.flush()
    if action == "void":
        return report_output(db, row)
    if action == "quality":
        if p["quality"]["reported_qty"] != row.reported_qty:
            fail("质量补录不能修改投入数，请使用更正")
        current = report_output(db, row)
        correction = {key: getattr(row, key) for key in ("business_date", "shift", "shift_template_version_id", "machine_id", "product_id", "process_version_id", "notes")}
        correction.update(p["quality"], expected_version=0, worker_ids=current["worker_ids"], evidence_job_ids=current["evidence_job_ids"],
            source_allocations=[{"job_id": a.job_id, "piece_qty": a.piece_qty, "job_version": find(db, m.UvJob, factory, a.job_id).version} for a in allocations])
    else:
        correction = p["correction"]
        if correction["factory_id"] != factory:
            fail("更正厂区不匹配")
        restored = {a.job_id for a in allocations}
        for requested in correction["source_allocations"]:
            if requested["job_id"] in restored:
                requested["job_version"] = find(db, m.UvJob, factory, requested["job_id"]).version
    return create_report(db, factory, actor, correction, "corrected" if previous_status in ACTIVE else "draft", row.id, p["reason"], row.id if action == "quality" else None)


def job_output(db, row):
    output = serial(row, ("ignored",))
    allocated = db.scalar(select(func.coalesce(func.sum(m.UvAllocation.piece_qty), 0)).join(m.UvReport, m.UvReport.id == m.UvAllocation.report_id).where(m.UvAllocation.job_id == row.id, m.UvAllocation.reversed.is_(False), m.UvReport.status.in_(ACTIVE)))
    available = None if row.raw_unit == "unknown" or row.suggested_piece_qty is None else row.suggested_piece_qty - allocated
    state = "ignored" if row.ignored else "needs_unit" if available is None else "unmatched" if not row.product_id else "allocated" if available == 0 else "partially_allocated" if allocated else "ready"
    output.update(available_piece_qty=available, reconciliation=state, candidates=[])
    return output


def reconcile(db, factory, actor, p):
    row = find(db, m.UvJob, factory, p["job_id"])
    version(row, p["expected_version"])
    if p["process_version_id"]:
        process = find(db, m.UvProcessVersion, factory, p["process_version_id"])
        if process.product_id != p["product_id"]:
            fail("工艺与产品不匹配")
    if p["product_id"]:
        find(db, m.UvProduct, factory, p["product_id"])
    allocated = db.scalar(select(func.coalesce(func.sum(m.UvAllocation.piece_qty), 0)).join(m.UvReport, m.UvReport.id == m.UvAllocation.report_id).where(m.UvAllocation.job_id == row.id, m.UvAllocation.reversed.is_(False), m.UvReport.status.in_(ACTIVE)))
    if allocated:
        fail("作业已有来源分配，须先更正相关报工再修改匹配", 409)
    if p["confirmed_unit"] == "unknown" and p["confirmed_piece_qty"] is not None:
        fail("未知单位不能直接确认件数")
    row.product_id, row.process_version_id = p["product_id"], p["process_version_id"]
    row.raw_unit, row.suggested_piece_qty = p["confirmed_unit"], p["confirmed_piece_qty"]
    row.reconcile_note, row.ignored = p["note"], p["ignore"]
    bump(row)
    db.flush()
    return job_output(db, row)


def entity_output(db, row):
    if isinstance(row, m.UvReport):
        return report_output(db, row)
    if isinstance(row, m.UvJob):
        return job_output(db, row)
    out = serial(row, ("active",))
    if isinstance(row, m.UvProduct):
        out["process_versions"] = [serial(v) for v in db.scalars(select(m.UvProcessVersion).where(m.UvProcessVersion.product_id == row.id).order_by(m.UvProcessVersion.effective_from.desc(), m.UvProcessVersion.id))]
    if isinstance(row, m.UvAssignment):
        out["share"] = float(row.share)
    if isinstance(row, m.UvMachine):
        fresh = "never_seen"
        if row.last_heartbeat_at:
            fresh = "fresh" if (datetime.now(UTC) - datetime.fromisoformat(row.last_heartbeat_at)).total_seconds() < 300 else "stale"
        out["freshness"] = fresh
        out["progress_pct"] = None if row.progress_pct is None else float(row.progress_pct)
    return out


def report_output(db, row):
    out = serial(row, ("created_by", "confirmed_at"))
    workers = list(db.scalars(select(m.UvReportWorker).where(m.UvReportWorker.report_id == row.id).order_by(m.UvReportWorker.worker_id)))
    out.update(worker_ids=[w.worker_id for w in workers], worker_names=[w.worker_name for w in workers],
        quality_status="pending" if row.pending_qty == row.reported_qty else "partial" if row.pending_qty or row.semi_finished_qty else "complete",
        allocation_total=db.scalar(select(func.coalesce(func.sum(m.UvAllocation.piece_qty), 0)).where(m.UvAllocation.report_id == row.id, m.UvAllocation.reversed.is_(False))))
    out["source_allocations"] = [dict(job_id=a.job_id, piece_qty=a.piece_qty, job_version=find(db, m.UvJob, row.factory_id, a.job_id).version)
        for a in db.scalars(select(m.UvAllocation).where(m.UvAllocation.report_id == row.id, m.UvAllocation.reversed.is_(False)).order_by(m.UvAllocation.job_id))]
    out["evidence_job_ids"] = list(db.scalars(select(m.UvReportEvidence.job_id).where(m.UvReportEvidence.report_id == row.id).order_by(m.UvReportEvidence.job_id)))
    rates = {v.rate_kind: v for v in db.scalars(select(m.UvRateSnapshot).where(m.UvRateSnapshot.report_id == row.id))}
    commercial, wage, area = (rates.get(k) for k in ("commercial", "piece_wage", "area"))
    output_value = money(D(row.good_qty) * commercial.unit_price, commercial.currency) if commercial and commercial.unit_price is not None else None
    area_value = money(D(row.good_qty) * area.unit_price * area.pricing_area_cm2, area.currency) if area and area.unit_price is not None and area.pricing_area_cm2 is not None else None
    amount = money(D(row.good_qty) * wage.unit_price, wage.currency) if wage and wage.unit_price is not None else None
    state = "unpriced" if amount is None else "provisional" if not workers or row.pending_qty or row.semi_finished_qty or row.status not in ACTIVE else "confirmed"
    out["commercial"] = dict(output_value=output_value, area_value=area_value, pricing_state="priced" if output_value is not None else "unpriced", basis="good_qty", unit_price=str(commercial.unit_price) if commercial and commercial.unit_price is not None else None, rate_version_id=commercial.rate_version_id if commercial else None)
    out["payroll"] = dict(amount=amount if workers else None, state=state, piece_wage=str(wage.unit_price) if wage and wage.unit_price is not None else None, rate_version_id=wage.rate_version_id if wage else None, worker_count=len(workers))
    shares = []
    units = int(D(amount["amount"]) * 10 ** currency_places(amount["currency"])) if amount and workers else None
    for index, worker in enumerate(workers):
        value = money(D(units // len(workers) + int(index < units % len(workers))) / 10 ** currency_places(amount["currency"]), amount["currency"]) if units is not None else None
        shares.append(dict(worker_id=worker.worker_id, worker_name=worker.worker_name, employee_no=worker.employee_no, amount=value, state=state, remainder_adjusted=bool(units is not None and index < units % len(workers))))
    out["worker_shares"] = shares
    return out


def query_rows(db, cls, factory, scope, active=False):
    query = select(cls).where(cls.factory_id == factory)
    if cls is m.UvMachine and scope.get("machine_id"):
        query = query.where(cls.id == scope["machine_id"])
    if cls is m.UvProduct and scope.get("product_id"):
        query = query.where(cls.id == scope["product_id"])
    day_column = getattr(cls, "business_date", None)
    if day_column is not None:
        for name, op in (("business_date", "eq"), ("date_from", "ge"), ("date_to", "le")):
            if scope.get(name):
                query = query.where({"eq": day_column == scope[name], "ge": day_column >= scope[name], "le": day_column <= scope[name]}[op])
    for field in ("shift", "machine_id", "product_id", "status"):
        if scope.get(field) and hasattr(cls, field):
            query = query.where(getattr(cls, field) == scope[field])
    if active and cls is m.UvReport:
        query = query.where(m.UvReport.status.in_(ACTIVE))
    if cls is m.UvAssignment:
        query = query.where(m.UvAssignment.active.is_(True))
    if scope.get("q"):
        columns = [getattr(cls, c) for c in ("product_no", "product_name", "name", "code", "raw_task_name", "employee_no", "display_name") if hasattr(cls, c)]
        if columns:
            from sqlalchemy import or_
            query = query.where(or_(*(col.contains(scope["q"], autoescape=True) for col in columns)))
    rows = list(db.scalars(query.order_by(cls.created_at.desc(), cls.id)))
    if cls is m.UvJob and scope.get("status"):
        rows = [r for r in rows if r.state == scope["status"] or job_output(db, r)["reconciliation"] == scope["status"]]
    if cls is m.UvMachine and scope.get("status"):
        rows = [r for r in rows if scope["status"] in (r.admin_status, r.runtime_status, entity_output(db, r)["freshness"])]
    if cls is m.UvJob and any(scope.get(k) for k in ("business_date", "date_from", "date_to", "shift")):
        templates = list(db.scalars(select(m.UvShiftTemplate).where(m.UvShiftTemplate.factory_id == factory)))
        rows = [r for r in rows if job_scope_matches(r, scope, templates)]
    return rows


def filtered_reports(db, factory, scope):
    return query_rows(db, m.UvReport, factory, scope, True)


def job_scope_matches(job, scope, templates):
    stamp = job.completed_at or job.started_at
    if stamp is None:
        return False
    try:
        day, shift, _ = business_slot(stamp, templates)
    except (HTTPException, ValueError, TypeError):
        return False
    return not (scope.get("business_date") and day != scope["business_date"] or scope.get("date_from") and day < scope["date_from"] or scope.get("date_to") and day > scope["date_to"] or scope.get("shift") and shift != scope["shift"])


def job_scope_warnings(db, factory, scope):
    if not any(scope.get(k) for k in ("business_date", "date_from", "date_to", "shift")):
        return []
    broad = {k: v for k, v in scope.items() if k not in ("business_date", "date_from", "date_to", "shift")}
    templates = list(db.scalars(select(m.UvShiftTemplate).where(m.UvShiftTemplate.factory_id == factory)))
    unknown = 0
    for job in query_rows(db, m.UvJob, factory, broad):
        try:
            stamp = job.completed_at or job.started_at
            if stamp is None:
                raise ValueError("missing time")
            business_slot(stamp, templates)
        except (HTTPException, ValueError, TypeError):
            unknown += 1
    return [dict(code="jobs_business_date_unknown", message=f"另有 {unknown} 条设备作业缺少可归属业务日的时间或模板，未纳入日期筛选", tone="warning")] if unknown else []


def report_trace(db, factory, report_id):
    requested = find(db, m.UvReport, factory, report_id)
    root, visited = requested, set()
    while root.replaces_report_id:
        if root.id in visited:
            fail("报工修订链存在循环，需核查", 409)
        visited.add(root.id)
        root = find(db, m.UvReport, factory, root.replaces_report_id)
    revisions, frontier = [root], [root.id]
    visited = {root.id}
    while frontier:
        children = list(db.scalars(select(m.UvReport).where(m.UvReport.factory_id == factory, m.UvReport.replaces_report_id.in_(frontier)).order_by(m.UvReport.created_at, m.UvReport.id)))
        frontier = []
        for child in children:
            if child.id in visited:
                fail("报工修订链存在循环，需核查", 409)
            visited.add(child.id)
            revisions.append(child)
            frontier.append(child.id)
    public = {r.id: report_output(db, r) for r in revisions}
    changes = []
    fields = (*QUALITY, "business_date", "shift", "shift_template_version_id", "machine_id", "product_id", "process_version_id", "worker_ids", "worker_names", "notes", "commercial", "payroll", "worker_shares")
    for row in revisions:
        if row.replaces_report_id in public:
            before, after = public[row.replaces_report_id], public[row.id]
            changes.append(dict(from_report_id=row.replaces_report_id, to_report_id=row.id, reason=row.correction_reason,
                changes={key: {"before": before[key], "after": after[key]} for key in fields if before[key] != after[key]}))
    allocations = []
    for row in db.scalars(select(m.UvAllocation).where(m.UvAllocation.factory_id == factory, m.UvAllocation.report_id.in_(visited)).order_by(m.UvAllocation.created_at, m.UvAllocation.id)):
        allocations.append({**serial(row), "effective": not row.reversed and public[row.report_id]["status"] in ACTIVE,
            "allocation_state": "reversed" if row.reversed else "allocated" if public[row.report_id]["status"] in ACTIVE else "draft_intent"})
    evidence = [serial(row) for row in db.scalars(select(m.UvReportEvidence).where(m.UvReportEvidence.factory_id == factory, m.UvReportEvidence.report_id.in_(visited)).order_by(m.UvReportEvidence.created_at, m.UvReportEvidence.id))]
    jobs = sorted({a["job_id"] for a in allocations} | {e["job_id"] for e in evidence})
    audit = []
    for row in db.scalars(select(m.UvOperation).where(m.UvOperation.factory_id == factory).order_by(m.UvOperation.created_at, m.UvOperation.id)):
        entity = row.result.get("entity")
        if not isinstance(entity, dict) or entity.get("id") not in visited:
            continue
        # Only these event facts are public. Receipts' full result, fingerprints,
        # request bodies and valuation snapshots never cross the audit boundary.
        audit.append(dict(operation_id=row.operation_id, command=row.command, accepted_at=row.created_at, actor_id=row.actor_id,
            report_id=entity["id"], version=entity.get("version"), status=entity.get("status"), reason=entity.get("correction_reason", ""),
            quality={k: entity[k] for k in QUALITY if k in entity}))
    return dict(report_id=requested.id, root_report_id=root.id, effective_report_ids=[r.id for r in revisions if r.status in ACTIVE],
        revisions=list(public.values()), changes=changes, allocations=allocations, evidence=evidence,
        source_jobs=[job_output(db, find(db, m.UvJob, factory, ident)) for ident in jobs], audit=audit)


def _instant(value):
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.astimezone(UTC) if result.tzinfo is not None else None
    except (AttributeError, ValueError):
        return None


def runtime_windows(db, factory, machine_id, scope):
    """Clip source intervals to versioned shifts; unobserved time stays a gap."""
    templates = list(db.scalars(select(m.UvShiftTemplate).where(m.UvShiftTemplate.factory_id == factory)))
    all_jobs = query_rows(db, m.UvJob, factory, {"machine_id": machine_id})
    first = scope.get("business_date") or scope.get("date_from")
    last = scope.get("business_date") or scope.get("date_to")
    candidate_days = set()
    if first and last:
        start_day, end_day = date.fromisoformat(first), date.fromisoformat(last)
        if (end_day - start_day).days > 366:
            fail("机台时序最多查询367个业务日，请缩小日期范围")
        candidate_days.update((start_day + timedelta(days=i)).isoformat() for i in range((end_day - start_day).days + 1))
    else:
        for job in all_jobs:
            for stamp in (job.started_at, job.completed_at):
                if stamp:
                    try:
                        day, _, _ = business_slot(stamp, templates)
                        if (not first or day >= first) and (not last or day <= last):
                            candidate_days.add(day)
                    except (HTTPException, ValueError):
                        pass
    now = datetime.now(UTC)
    base_intervals = []
    for day in sorted(candidate_days):
        for template in templates:
            if scope.get("shift") and template.shift != scope["shift"]:
                continue
            if not template.effective_from <= day <= (template.effective_to or "9999-12-31"):
                continue
            start = datetime.combine(date.fromisoformat(day), time.fromisoformat(template.start_local), ZoneInfo("Asia/Shanghai"))
            end = datetime.combine(date.fromisoformat(day), time.fromisoformat(template.end_local), ZoneInfo("Asia/Shanghai"))
            if end <= start:
                end += timedelta(days=1)
            start, end = start.astimezone(UTC), min(end.astimezone(UTC), now)
            if start < end:
                base_intervals.append((start, end))
    warnings = []
    if candidate_days and not base_intervals:
        warnings.append(dict(code="runtime_no_template", message="选定业务日没有有效班次或尚未开始，无法绘制运行时序", tone="warning"))
    evidence = []
    for job in all_jobs:
        start, end = _instant(job.started_at), _instant(job.completed_at)
        if start and end and start < end and job.time_evidence in ("observed", "inferred"):
            evidence.append((start, min(end, now), job))
    cuts = {point for interval in base_intervals for point in interval}
    for start, end, _ in evidence:
        for lower, upper in base_intervals:
            if start < upper and end > lower:
                cuts.update((max(start, lower), min(end, upper)))
    points = sorted(cuts)
    segments = []
    for start, end in zip(points, points[1:]):
        if not any(low <= start and end <= high for low, high in base_intervals):
            continue
        matches = [job for low, high, job in evidence if low <= start and end <= high]
        job = matches[0] if len(matches) == 1 else None
        kind, label, proof = ("run", job.raw_task_name, job.time_evidence) if job else ("gap", "作业时间重叠，运行状态待核" if matches else "缺少完整运行证据", "unknown")
        if segments and segments[-1]["end_at"] == start.isoformat() and (segments[-1]["kind"], segments[-1]["job_id"], segments[-1]["label"], segments[-1]["evidence"]) == (kind, job.id if job else None, label, proof):
            segments[-1]["end_at"] = end.isoformat()
            segments[-1]["duration_minutes"] += (end-start).total_seconds()/60
        else:
            segments.append(dict(id=sha256(f"{machine_id}/{start.isoformat()}/{kind}".encode()).hexdigest()[:32], machine_id=machine_id, start_at=start.isoformat(), end_at=end.isoformat(), duration_minutes=(end-start).total_seconds()/60, kind=kind, job_id=job.id if job else None, label=label, evidence=proof))
    if any(v["kind"] == "gap" for v in segments):
        warnings.append(dict(code="runtime_gaps", message="时序缺口表示未取得完整设备证据，不等同停机或空闲", tone="warning"))
    return segments, warnings


def machine_expenses(db, factory, machine_id, scope):
    if not importlib.util.find_spec("app.services.uv_finance"):
        return [], [dict(code="expenses_unavailable", message="费用明细能力尚未启用", tone="warning")]
    from app.models.uv_finance import UvExpense
    from app.services.uv_finance import expense_output
    query = select(UvExpense).where(UvExpense.factory_id == factory, UvExpense.machine_id == machine_id)
    for key, expression in (("business_date", UvExpense.occurred_on == scope.get("business_date")), ("date_from", UvExpense.occurred_on >= (scope.get("date_from") or "")), ("date_to", UvExpense.occurred_on <= (scope.get("date_to") or "9999-12-31"))):
        if scope.get(key):
            query = query.where(expression)
    warnings = []
    if scope.get("shift") or scope.get("product_id"):
        return [], [dict(code="expenses_no_shift_product", message="费用未分配到具体班次或产品，当前筛选不归入这些费用", tone="info")]
    return [expense_output(r) for r in db.scalars(query.order_by(UvExpense.occurred_on.desc(), UvExpense.created_at.desc(), UvExpense.id))], warnings


def page(items, scope):
    number, size = scope.get("page", 1), scope.get("page_size", 50)
    return dict(items=items[(number - 1) * size:number * size], total=len(items), page=number, page_size=size)


def payroll_preview(db, factory, scope):
    reports = [report_output(db, r) for r in query_rows(db, m.UvReport, factory, scope, True)]
    lines = {}
    for report in reports:
        for share in report["worker_shares"]:
            line = lines.setdefault(share["worker_id"], dict(worker_id=share["worker_id"], worker_name=share["worker_name"], employee_no=share["employee_no"], report_count=0, good_qty=0, amount=None, state="confirmed", allocation_basis="同工作批次按员工ID稳定等分", remainder_adjusted=False, reason="", amounts=[]))
            line["report_count"] += 1
            line["good_qty"] += report["good_qty"]
            line["amounts"].append(share["amount"])
            line["remainder_adjusted"] |= share["remainder_adjusted"]
            if share["state"] != "confirmed":
                line["state"] = "unpriced" if share["state"] == "unpriced" else "provisional" if line["state"] != "unpriced" else "unpriced"
    adjustments = []
    if scope.get("include_adjustments", True) and importlib.util.find_spec("app.services.uv_finance"):
        from app.services.uv_finance import payroll_adjustments
        adjustments = payroll_adjustments(db, factory, scope)
    for adjustment in adjustments:
        worker = find(db, m.UvWorker, factory, adjustment["worker_id"])
        line = lines.setdefault(adjustment["worker_id"], dict(worker_id=adjustment["worker_id"], worker_name=adjustment["worker_name"], employee_no=worker.employee_no,
            report_count=0, good_qty=0, amount=None, state="confirmed", allocation_basis="已确认工资调整", remainder_adjusted=False, reason="", amounts=[]))
        line["amounts"].append(money(D(adjustment["amount"]), adjustment["currency"]))
        line.setdefault("adjustment_batch_ids", []).append(adjustment["batch_id"])
        line.setdefault("adjustment_reasons", []).append(adjustment["reason"])
        if line["state"] == "confirmed":
            line["state"] = "adjusted"
    for line in lines.values():
        line["amount"] = sum_money(line.pop("amounts"))
        if line["amount"] is None:
            line["state"], line["reason"] = "unpriced", "存在未定工价或多个币种，不能合并"
        elif line["state"] == "provisional":
            line["reason"] = "质量尚未核清"
        if line.get("adjustment_reasons"):
            line["reason"] = "；".join(filter(None, [line["reason"], "已计入工资调整：" + "；".join(dict.fromkeys(line["adjustment_reasons"]))]))
            line["adjustment_batch_ids"] = list(dict.fromkeys(line["adjustment_batch_ids"]))
    total = sum_money([r["payroll"]["amount"] for r in reports] + [money(D(a["amount"]), a["currency"]) for a in adjustments])
    unpriced = sum(r["payroll"]["piece_wage"] is None for r in reports)
    unassigned = sum(not r["worker_ids"] for r in reports)
    pending = sum(r["quality_status"] != "complete" for r in reports)
    warnings = []
    if (reports or adjustments) and total is None:
        warnings.append(dict(code="payroll_incomplete", message="工资存在未定价、未排班或混合币种", tone="warning"))
    if pending:
        warnings.append(dict(code="quality_pending", message="质量未核清，工资仅供预览", tone="warning"))
    return dict(date_from=scope.get("date_from") or scope.get("business_date") or "", date_to=scope.get("date_to") or scope.get("business_date") or "", shift=scope.get("shift") or "all", currency=total["currency"] if total else "", batch_total=total, lines=sorted(lines.values(), key=lambda v: v["worker_id"]), unpriced_reports=unpriced, unassigned_reports=unassigned, quality_pending_reports=pending, coverage="no_data" if not reports and not adjustments else "partial" if warnings else "complete", warnings=warnings)


def daily_projection(db, factory, scope):
    reports = query_rows(db, m.UvReport, factory, scope, True)
    day_set = {r.business_date for r in reports}
    if importlib.util.find_spec("app.services.uv_finance"):
        from app.services import uv_finance
        if hasattr(uv_finance, "cost_dates"):
            day_set.update(uv_finance.cost_dates(db, factory, scope))
    days = sorted(day_set)
    rows = []
    for day in days:
        selected = [report_output(db, r) for r in reports if r.business_date == day]
        good = sum(r["good_qty"] for r in selected)
        defective = sum(r["defective_qty"] for r in selected)
        costs = dict(ink_cost=None, expense_amount=None, provisional_reasons=["经营费用尚未核齐"])
        planned_day_off = False
        if importlib.util.find_spec("app.services.uv_finance"):
            from app.services.uv_finance import day_costs, latest_policy
            costs = day_costs(db, factory, day, scope.get("machine_id"))
            policy = latest_policy(db, factory, day[:7])
            planned_day_off = policy is not None and day not in policy.working_days
        if scope.get("shift") or scope.get("product_id"):
            costs = dict(ink_cost=None, expense_amount=None, provisional_reasons=["费用未分配到具体班次或产品"])
        adjustments = []
        if importlib.util.find_spec("app.services.uv_finance"):
            from app.services.uv_finance import payroll_adjustments
            adjustments = payroll_adjustments(db, factory, {**scope, "business_date": day})
        output = sum_money(r["commercial"]["output_value"] for r in selected)
        payroll = sum_money([r["payroll"]["amount"] for r in selected] + [money(D(a["amount"]), a["currency"]) for a in adjustments])
        if not selected:
            known_currencies = {v["currency"] for v in (payroll, costs["ink_cost"], costs["expense_amount"]) if v is not None}
            if len(known_currencies) == 1:
                code = next(iter(known_currencies))
                output = money(D(0), code)
                if not adjustments:
                    payroll = money(D(0), code)
        reasons = list(costs.get("provisional_reasons", []))
        if selected and output is None:
            reasons.append("商业产值未定价或多个币种不能合并")
        if (selected or adjustments) and payroll is None:
            reasons.append("工资存在未定价、未排班或多个币种")
        if any(r["quality_status"] != "complete" for r in selected):
            reasons.append("质量尚未核清")
        operating = None
        all_money = [output, payroll, costs["ink_cost"], costs["expense_amount"]]
        if len({v["currency"] for v in all_money if v}) > 1:
            reasons.append("经营收支币种不一致")
        if not reasons and all(v is not None for v in all_money) and len({v["currency"] for v in all_money}) == 1:
            operating = money(D(output["amount"]) - sum(D(v["amount"]) for v in all_money[1:]), output["currency"])
        rows.append(dict(business_date=day, good_qty=good, defective_qty=defective, reported_qty=sum(r["reported_qty"] for r in selected), yield_rate=str(D(good) / (good + defective)) if good + defective else None,
            output_value=output, area_value=sum_money(r["commercial"]["area_value"] for r in selected), payroll_amount=payroll, ink_cost=costs["ink_cost"], expense_amount=costs["expense_amount"], operating_result=operating,
            unpriced_reports=sum(r["commercial"]["pricing_state"] == "unpriced" for r in selected), quality_pending_reports=sum(r["quality_status"] != "complete" for r in selected), planned_day_off=planned_day_off, off_plan_production=planned_day_off and bool(selected),
            provisional_reasons=list(dict.fromkeys(reasons)), cost_coverage="complete" if operating is not None else "partial"))
    return rows


def monthly_projection(db, factory, scope):
    days = daily_projection(db, factory, scope)
    months = []
    for month in sorted({d["business_date"][:7] for d in days}):
        selected = [d for d in days if d["business_date"].startswith(month)]
        good, defective = sum(d["good_qty"] for d in selected), sum(d["defective_qty"] for d in selected)
        output, payroll, operating = [sum_money(d[field] for d in selected) for field in ("output_value", "payroll_amount", "operating_result")]
        def ratio(value):
            return str(D(value["amount"]) / D(output["amount"])) if value and output and value["currency"] == output["currency"] and D(output["amount"]) else None
        months.append(dict(month=month, good_qty=good, reported_qty=sum(d["reported_qty"] for d in selected), yield_rate=str(D(good)/(good+defective)) if good+defective else None, output_value=output, payroll_amount=payroll, payroll_ratio=ratio(payroll), operating_result=operating, result_ratio=ratio(operating), cost_coverage="complete" if operating is not None else "partial"))
    return dict(month=(scope.get("business_date") or scope.get("date_from") or "")[:7], months=months, structure=[], coverage_note="仅有效报工；良率为合格总量 / 已判总量；费用按发生日", provisional_reasons=["未完整核齐的成本或不同币种不能合并"] if any(v["cost_coverage"] != "complete" for v in months) else [])


def business_slot(instant, templates):
    local = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    if local.tzinfo is None:
        fail("时间必须带明确时区")
    local = local.astimezone(ZoneInfo("Asia/Shanghai"))
    matches = []
    for day in (local.date(), local.date() - timedelta(days=1)):
        for template in templates:
            if not (template.effective_from <= day.isoformat() <= (template.effective_to or "9999-12-31")):
                continue
            start = datetime.combine(day, time.fromisoformat(template.start_local), local.tzinfo)
            end = datetime.combine(day, time.fromisoformat(template.end_local), local.tzinfo)
            if end <= start:
                end += timedelta(days=1)
            if start <= local < end:
                matches.append((day.isoformat(), template.shift, template.id))
    if len(matches) == 1:
        return matches[0]
    fail("时间没有唯一有效班次模板")


for name, cls in (("product", m.UvProduct), ("machine", m.UvMachine), ("worker", m.UvWorker)):
    ACTIONS[name] = lambda db, f, a, p, cls=cls: save_master(db, f, a, p, cls)
ACTIONS.update(process=save_process, rate=save_rate, report=create_report, assignment=save_assignment, reconcile=reconcile)
ACTIONS["rate-create"] = save_rate
ACTIONS["shift-template"] = save_template
for action in ("confirm", "quality", "correction", "void"):
    ACTIONS[action] = lambda db, f, a, p, action=action: report_command(db, f, a, p, action)
