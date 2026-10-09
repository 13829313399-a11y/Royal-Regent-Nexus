import json
from datetime import timedelta
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, or_, select

from app.core.time import business_now, parse_business_timestamp
from app.models import three_d_printing as m
from app.schemas.three_d_operations import (
    Demand,
    FileAlias,
    FileMetadata,
    Profile,
    RunEvidence,
    Spool,
)
from app.services import three_d_printing as business
from app.services.auth import has_permission_in_scope, time_window_is_active
from app.services.three_d_connector import notify
from app.services.three_d_consistency import atomic_write, encode
from app.services.three_d_network_health import network_health_snapshot

MODEL = m.ThreeDPrintingOperationsItem
SCHEMAS = {
    "spool": Spool,
    "request": Demand,
    "file_alias": FileAlias,
    "profile": Profile,
    "file": FileMetadata,
    "run_evidence": RunEvidence,
}


def fail(code, status=409):
    messages = {
        "revision_conflict": "记录已被其他人更新，请刷新后重新核对",
        "ams_slot_occupied": "该机台的 AMS 槽位已有卷材，请先调整原卷材位置",
        "department_scope_denied": "只能提交本人授权部门的打印需求",
        "supervisor_required": "审批需要本厂主管或管理员权限",
        "completion_evidence_required": "请选择产品和数量相符的成功生产记录作为完成凭证",
        "run_already_allocated": "该生产记录已用于其他需求，不能重复分配",
        "invalid_request_transition": "需求状态已变化，请刷新后重试",
        "product_not_available": "产品不存在或已归档，请重新选择",
        "file_not_found": "关联附件不存在，请重新上传或选择",
        "spool_not_found": "关联卷材不存在或已归档",
        "only_unmatched_connector_run_allowed": "只允许匹配尚未绑定产品、尚未扣料的云端设备任务",
        "resource_not_editable": "当前记录已经完成或取消",
        "resource_too_large": "关联内容过多，请减少附件或批次数量",
    }
    raise HTTPException(
        status,
        {"code": code, "message": messages.get(code, "记录无效或不存在，请刷新后核对")},
    )


def out(row):
    return {
        "id": row.id,
        "kind": row.kind,
        "resource_key": row.resource_key,
        "status": row.status,
        "data": json.loads(row.data_json),
        "revision": row.revision,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def resources(db, kind, page=1, page_size=50, q=""):
    if kind not in (*SCHEMAS, "file"):
        fail("unknown_resource", 404)
    filters = [
        MODEL.factory_id == "huakang-a",
        MODEL.kind == kind,
        MODEL.status != "archived",
    ]
    if q.strip():
        filters.append(
            or_(
                MODEL.resource_key.contains(q.strip(), autoescape=True),
                MODEL.data_json.contains(q.strip(), autoescape=True),
                MODEL.id == q.strip(),
            )
        )
    total = db.scalar(select(func.count()).select_from(MODEL).where(*filters))
    rows = db.scalars(
        select(MODEL)
        .where(*filters)
        .order_by(MODEL.created_at.desc(), MODEL.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "items": [out(r) for r in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def product(db, value):
    row = db.get(m.ThreeDPrintingProduct, value)
    if row is None or row.factory_id != "huakang-a" or not row.is_active:
        fail("product_not_available", 422)
    return row


def audit(db, row, user, reason, action, before=None):
    business.add_audit(
        db,
        factory_id="huakang-a",
        entity_type="operations",
        entity_id=row.id,
        action=action,
        actor_id=user.id,
        actor_name=user.display_name,
        detail={"reason": reason, "before": before, "after": out(row)},
    )
    notify(db, "operations", row.id)


@atomic_write
def save(db, *, kind, payload, user):
    if kind not in SCHEMAS:
        fail("unknown_resource", 404)
    try:
        data = SCHEMAS[kind].model_validate(payload.data).model_dump(mode="json")
    except ValidationError as error:
        raise HTTPException(
            422,
            {
                "code": "invalid_resource_data",
                "message": "字段格式或范围不正确，请检查机号、槽位、数量、日期和必填项",
                "fields": [list(e["loc"]) for e in error.errors()],
            },
        ) from error
    if len(encode(data)) > 16000:
        fail("resource_too_large", 422)
    if "product_id" in data:
        product(db, data["product_id"])
    for value in data.get("product_ids", []):
        product(db, value)
    for value in data.get("file_ids", []) + (
        [data["file_id"]] if data.get("file_id") else []
    ):
        f = db.get(MODEL, value)
        if f is None or f.factory_id != "huakang-a" or f.kind != "file":
            fail("file_not_found", 422)
    if not payload.resource_key.strip():
        fail("resource_key_required", 422)
    if kind == "request":
        permitted = has_permission_in_scope(
            user, "three_d_printing:operate", "huakang-a", data["department"]
        )
        # Position capabilities may span departments elsewhere in Nexus. A
        # demand's department is accounting provenance, so require an actual
        # active binding to that department as well, without changing global IAM.
        bound = any(
            grant.factory_id in {"*", "huakang-a"}
            and grant.department in {"*", data["department"]}
            and time_window_is_active(grant.valid_from, grant.valid_until)
            and (
                "three_d_printing:operate" in grant.permissions
                or grant.role_id == "admin"
            )
            for grant in user.grants
        )
        if not permitted or not bound:
            fail("department_scope_denied", 403)
    if kind == "run_evidence":
        record = db.get(m.ThreeDPrintingProductionRecord, data["record_id"])
        if not record or record.factory_id != "huakang-a" or record.deleted_at:
            fail("run_not_found", 404)
        data["spool_snapshots"] = []
        for identifier in data["spool_ids"]:
            spool = db.get(MODEL, identifier)
            if (
                not spool
                or spool.factory_id != "huakang-a"
                or spool.kind != "spool"
                or spool.status != "active"
            ):
                fail("spool_not_found", 422)
            data["spool_snapshots"].append(out(spool))
    if kind == "file_alias":
        key = data["file_name"].replace("\\", "/").rsplit("/", 1)[-1].strip().casefold()
        if not key:
            fail("file_name_required", 422)
        key = sha256(key.encode()).hexdigest()
    elif kind == "run_evidence":
        key = data["record_id"]
    elif kind == "profile":
        key = str(data["machine_no"])
    else:
        key = payload.resource_key.strip()
    row = db.scalar(
        select(MODEL).where(
            MODEL.factory_id == "huakang-a",
            MODEL.kind == kind,
            MODEL.resource_key == key,
        )
    )
    if row and row.revision != payload.revision:
        fail("revision_conflict")
    if row and row.status not in {"active", "submitted"}:
        fail("resource_not_editable")
    if row is None and payload.revision:
        fail("resource_not_found", 404)
    if kind == "spool" and data["machine_no"] is not None:
        for other in db.scalars(
            select(MODEL).where(
                MODEL.kind == "spool",
                MODEL.factory_id == "huakang-a",
                MODEL.status == "active",
            )
        ):
            values = json.loads(other.data_json)
            if other is not row and (values["machine_no"], values["slot"]) == (
                data["machine_no"],
                data["slot"],
            ):
                fail("ams_slot_occupied")
    if len(encode(data)) > 16000:
        fail("resource_too_large", 422)
    before = out(row) if row else None
    now = business_now().isoformat()
    if row is None:
        row = MODEL(
            id="3dops-" + uuid4().hex,
            factory_id="huakang-a",
            kind=kind,
            resource_key=key,
            status="submitted" if kind == "request" else "active",
            created_by=user.id,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.revision += 1
    row.data_json, row.updated_at = encode(data), now
    audit(db, row, user, payload.reason, "save", before)
    return row


@atomic_write
def act(db, *, item_id, payload, user):
    row = db.get(MODEL, item_id)
    if row is None or row.factory_id != "huakang-a":
        fail("resource_not_found", 404)
    if row.revision != payload.revision:
        fail("revision_conflict")
    before = out(row)
    data = before["data"]
    if payload.action == "archive" and row.kind != "request":
        row.status = "archived"
    elif row.kind == "request":
        transitions = {
            ("submitted", "schedule"): "scheduled",
            ("submitted", "approve"): "approved",
            ("submitted", "reject"): "rejected",
            ("approved", "schedule"): "scheduled",
            ("scheduled", "complete"): "completed",
            ("submitted", "cancel"): "cancelled",
            ("approved", "cancel"): "cancelled",
            ("scheduled", "cancel"): "cancelled",
        }
        target = transitions.get((row.status, payload.action))
        if not target:
            fail("invalid_request_transition")
        if payload.action in {"approve", "reject"} and not any(
            g.role_id
            in {
                "admin",
                "position_3d_supervisor",
                "position_3d_manager",
                "position_production_supervisor",
            }
            and g.factory_id in {"*", "huakang-a"}
            and time_window_is_active(g.valid_from, g.valid_until)
            for g in user.grants
        ):
            fail("supervisor_required", 403)
        if payload.action == "schedule":
            p = product(db, data["product_id"])
            schedule = m.ThreeDPrintingSchedule(
                id="3dsched-" + uuid4().hex,
                factory_id="huakang-a",
                business_date=data["due_date"],
                product_id=p.id,
                product_name=p.name,
                customer=p.customer,
                material_name=p.material_name,
                weight_g=p.weight_g,
                quantity=data["quantity"],
                machine_no=0,
                priority=data["priority"],
                status="pending",
                remark="内部需求 " + row.id,
                revision=1,
                created_by=user.id,
                created_by_name=user.display_name,
                created_at=business_now().isoformat(),
                updated_at=business_now().isoformat(),
            )
            db.add(schedule)
            data["schedule_id"] = schedule.id
        if payload.action == "complete":
            record = db.get(m.ThreeDPrintingProductionRecord, payload.target_id)
            if (
                not record
                or record.factory_id != "huakang-a"
                or record.deleted_at
                or record.run_status != "succeeded"
                or record.product_id != data["product_id"]
                or record.quantity < data["quantity"]
            ):
                fail("completion_evidence_required")
            for other in db.scalars(
                select(MODEL).where(
                    MODEL.kind == "request", MODEL.status == "completed"
                )
            ):
                if json.loads(other.data_json).get("record_id") == record.id:
                    fail("run_already_allocated")
            data["record_id"] = record.id
            data["feedback"] = payload.feedback
            schedule = db.get(m.ThreeDPrintingSchedule, data.get("schedule_id"))
            if schedule and schedule.factory_id == "huakang-a":
                schedule.status = "done"
                schedule.revision += 1
                schedule.updated_at = business_now().isoformat()
        if payload.action == "cancel" and data.get("schedule_id"):
            schedule = db.get(m.ThreeDPrintingSchedule, data["schedule_id"])
            if schedule and schedule.factory_id == "huakang-a":
                schedule.status = "cancelled"
                schedule.revision += 1
                schedule.updated_at = business_now().isoformat()
        row.status = target
    else:
        fail("unsupported_action", 422)
    row.data_json = encode(data)
    row.revision += 1
    row.updated_at = business_now().isoformat()
    audit(db, row, user, payload.reason, payload.action, before)
    return row


def analytics(db, days=30):
    now = business_now()
    begin = now - timedelta(days=days)
    record = m.ThreeDPrintingProductionRecord
    records = list(
        db.execute(
            select(record.machine_no, record.business_date, record.print_start_at,
                   record.print_end_at, record.duration_hours, record.quantity,
                   record.run_status).where(
                m.ThreeDPrintingProductionRecord.factory_id == "huakang-a",
                m.ThreeDPrintingProductionRecord.deleted_at == "",
                or_(
                    m.ThreeDPrintingProductionRecord.business_date
                    >= begin.date().isoformat(),
                    m.ThreeDPrintingProductionRecord.print_end_at
                    >= begin.date().isoformat(),
                ),
            ).execution_options(yield_per=500)
        )
    )
    from app.services.three_d_efficiency import counters

    measured = counters(db, days)
    maintained = dict(db.execute(select(
        m.ThreeDPrintingMaintenance.machine_no,
        func.max(m.ThreeDPrintingMaintenance.business_date),
    ).where(m.ThreeDPrintingMaintenance.factory_id == "huakang-a")
      .group_by(m.ThreeDPrintingMaintenance.machine_no)).all())
    profiles = dict(db.execute(select(MODEL.resource_key, MODEL.data_json).where(
        MODEL.factory_id == "huakang-a", MODEL.kind == "profile", MODEL.status == "active",
    )).all())
    result = []
    for number in range(1, 12):
        rows = [r for r in records if r.machine_no == number]
        occupied = expected = 0.0
        timed_records = 0
        for row in rows:
            start, end = (
                parse_business_timestamp(row.print_start_at),
                parse_business_timestamp(row.print_end_at),
            )
            if start and end and end > start:
                overlap = max(
                    0, (min(end, now) - max(start, begin)).total_seconds() / 3600
                )
                if not overlap:
                    continue
                timed_records += 1
                occupied += overlap
                elapsed = (end - start).total_seconds() / 3600
                expected += float(row.duration_hours) * row.quantity * overlap / elapsed
        completed = [r for r in rows if r.run_status in {"succeeded", "failed"}]
        quality = (
            sum(r.run_status == "succeeded" for r in completed) / len(completed)
            if completed
            else None
        )
        availability = min(1, occupied / (days * 24)) if timed_records else None
        performance = min(1, expected / occupied) if occupied and expected else None
        maintenance = maintained.get(number)
        profile = profiles.get(str(number))
        interval = (
            json.loads(profile)["service_interval_hours"] if profile else 250
        )
        service_hours = 0.0
        for row in rows:
            if maintenance and row.business_date <= maintenance:
                continue
            start, end = (
                parse_business_timestamp(row.print_start_at),
                parse_business_timestamp(row.print_end_at),
            )
            if start and end and end > start:
                service_hours += (end - start).total_seconds() / 3600
        result.append(
            {
                "machine_no": number,
                "occupied_hours": round(occupied, 2),
                "availability": availability,
                "records_with_timing": timed_records,
                "records_without_timing": len(rows) - timed_records,
                "performance": performance,
                "quality": quality,
                "oee": availability * performance * quality
                if availability is not None
                and performance is not None
                and quality is not None
                else None,
                "completed": len(completed),
                "failed": sum(r.run_status == "failed" for r in completed),
                "hours_since_service_in_window": round(service_hours, 2),
                "maintenance_due": measured[number]["lifetime_hours_since_service"]
                >= interval
                or bool(measured[number]["maintenance_reasons"]),
                **measured[number],
                "service_interval_hours": interval,
            }
        )
    return {
        "days": days,
        "basis": "24h calendar window; completed task elapsed time includes pauses; unknown timing excluded; maintenance hours are lower bounds within window",
        "machines": result,
    }


def recommendations(db):
    health = network_health_snapshot(db)
    live = health["configured"] and health["status"] == "healthy"
    now = business_now()
    printers = {
        p.machine_no: business.printer_out(p)
        for p in db.scalars(
            select(m.ThreeDPrintingPrinter).where(
                m.ThreeDPrintingPrinter.factory_id == "huakang-a"
            )
        )
    }
    profiles = {
        json.loads(r.data_json)["machine_no"]: json.loads(r.data_json)
        for r in db.scalars(
            select(MODEL).where(
                MODEL.factory_id == "huakang-a",
                MODEL.kind == "profile",
                MODEL.status == "active",
            )
        )
    }
    spools = [
        json.loads(r.data_json)
        for r in db.scalars(
            select(MODEL).where(
                MODEL.factory_id == "huakang-a",
                MODEL.kind == "spool",
                MODEL.status == "active",
            )
        )
    ]
    jobs = list(
        db.scalars(
            select(m.ThreeDPrintingSchedule).where(
                m.ThreeDPrintingSchedule.factory_id == "huakang-a",
                m.ThreeDPrintingSchedule.status == "pending",
            )
        )
    )
    jobs.sort(
        key=lambda j: (
            0 if j.machine_no else 1,
            {"high": 0, "normal": 1, "low": 2}.get(j.priority, 1),
            j.business_date,
            j.id,
        )
    )
    load = {
        n: max(0, p["remaining_minutes"])
        if live and p["connected"] and p["state"] == "RUNNING"
        else 0
        for n, p in printers.items()
    }
    proposed = []
    for job in jobs:
        candidates = []
        needed = float(job.weight_g) * job.quantity
        details = {
            "schedule_id": job.id,
            "schedule": business.schedule_out(job),
            "product_name": job.product_name,
            "quantity": job.quantity,
            "due_date": job.business_date,
            "assigned": bool(job.machine_no),
        }
        p = db.get(m.ThreeDPrintingProduct, job.product_id)
        duration = float(p.duration_hours) * job.quantity * 60 if p else 0
        if duration <= 0:
            proposed.append(
                {
                    **details,
                    "machine_no": None,
                    "reason": "产品工时缺失，请先补充产品资料",
                }
            )
            continue
        for n, printer in printers.items():
            if job.machine_no and job.machine_no != n:
                continue
            profile = profiles.get(n)
            fresh = live and printer["connected"]
            if (
                (profile and profile["maintenance_blocked"])
                or not printer["enabled"]
                or (
                    fresh
                    and (
                        bool(printer["error_text"])
                        or printer["nozzle_temperature"] > 320
                        or printer["bed_temperature"] > 130
                        or printer["state"] not in {"IDLE", "FINISH", "RUNNING"}
                    )
                )
            ):
                continue
            if profile and (
                job.material_name not in profile["materials"]
                or (
                    profile["product_ids"]
                    and job.product_id not in profile["product_ids"]
                )
            ):
                continue
            mounted = [
                s
                for s in spools
                if s["machine_no"] == n and s["material"] == job.material_name
            ]
            available = sum(s["remaining_g"] for s in mounted) if mounted else None
            if available is not None and available < needed:
                continue
            warnings = []
            if not fresh:
                warnings.append("离线估算，机台可用时间待现场核实")
            if not profile:
                warnings.append("未设置机台适配，请核实材料与产品")
            if available is None:
                warnings.append("未登记该材料卷材，余量待核实")
            if needed <= 0:
                warnings.append("计划重量缺失，耗材量待补充")
            # Prefer complete machine/material evidence, then the earliest slot.
            candidates.append((len(warnings), load[n], n, available, warnings))
        if not candidates:
            proposed.append(
                {
                    **details,
                    "machine_no": None,
                    "reason": "指定机台不可用、材料不适配或已登记卷材不足"
                    if job.machine_no
                    else "机台暂停排程、材料不适配或已登记卷材不足",
                }
            )
            continue
        _, minutes, n, available, warnings = min(candidates)
        eta = now + timedelta(minutes=minutes + duration)
        proposed.append(
            {
                **details,
                "machine_no": n,
                "eta": eta.isoformat(),
                "late": eta.date().isoformat() > job.business_date,
                "reason": "保留现有机台分配并计入队列"
                if job.machine_no
                else (
                    "按计划工时推荐机台，未核实信息见提示"
                    if warnings
                    else "按优先级与交期排序，选择适配且余料充足的最早可用机台"
                ),
                "available_g": available,
                "warnings": warnings,
                "estimated": bool(warnings),
            }
        )
        load[n] += duration
        left = needed
        for spool in spools:
            if spool["machine_no"] == n and spool["material"] == job.material_name:
                used = min(left, spool["remaining_g"])
                spool["remaining_g"] -= used
                left -= used
    return {
        "mode": "recommend_only",
        "items": proposed,
        "notice": ""
        if live
        else "实时网络未就绪，仍可离线排程；开工时间与余料请按现场情况调整。",
    }


@atomic_write
def match_run(db, *, record_id, payload, user):
    if payload.action != "match":
        fail("match_action_required", 422)
    record = db.get(m.ThreeDPrintingProductionRecord, record_id)
    if not record or record.factory_id != "huakang-a" or record.deleted_at:
        fail("run_not_found", 404)
    if record.revision != payload.revision:
        fail("revision_conflict")
    if (
        record.source_system != "cloud-connector"
        or record.product_id
        or record.inventory_consumed
    ):
        fail("only_unmatched_connector_run_allowed")
    p = product(db, payload.target_id)
    before = business.production_record_out(record)
    record.product_id, record.product_name, record.material_name = (
        p.id,
        p.name,
        p.material_name,
    )
    record.weight_g, record.quantity, record.duration_hours = (
        p.weight_g,
        p.default_quantity,
        p.duration_hours,
    )
    record.quoted_price, record.customer = p.quoted_price, p.customer
    flags = set(json.loads(record.data_quality_flags_json))
    flags.discard("product_match_required")
    record.data_quality_flags_json = encode(sorted(flags))
    record.reconciliation_status = "pending" if flags else "resolved"
    record.revision += 1
    record.updated_at = business_now().isoformat()
    business._consume_record(db, record, user.id, user.display_name, payload.reason)
    # Preserve captured historical rates; a changed material remains explicitly unpriced.
    business.freeze_cost(
        record, business.ensure_settings(db, "huakang-a"), None, reason=payload.reason
    )
    business.add_audit(
        db,
        factory_id="huakang-a",
        entity_type="production_record",
        entity_id=record.id,
        action="manual_match",
        actor_id=user.id,
        actor_name=user.display_name,
        detail={
            "before": before,
            "after": business.production_record_out(record),
            "reason": payload.reason,
        },
    )
    notify(db, "print_run", record.id)
    return record


def digital_thread(db, record_id):
    record = db.get(m.ThreeDPrintingProductionRecord, record_id)
    if not record or record.factory_id != "huakang-a" or record.deleted_at:
        fail("run_not_found", 404)
    # Only frozen file associations captured for this run are evidence of the printed version.
    aliases = []
    events = db.scalars(
        select(m.ThreeDPrintingAuditEvent).where(
            m.ThreeDPrintingAuditEvent.factory_id == "huakang-a",
            m.ThreeDPrintingAuditEvent.entity_id == record.id,
            m.ThreeDPrintingAuditEvent.action == "auto_create",
        )
    )
    for event in events:
        link = json.loads(event.detail_json).get("file_version")
        if link:
            aliases.append(link)
    requests = [
        out(r)
        for r in db.scalars(
            select(MODEL).where(
                MODEL.factory_id == "huakang-a", MODEL.kind == "request"
            )
        )
        if json.loads(r.data_json).get("record_id") == record.id
    ]
    movements = db.scalars(
        select(m.ThreeDPrintingInventoryMovement).where(
            m.ThreeDPrintingInventoryMovement.factory_id == "huakang-a",
            m.ThreeDPrintingInventoryMovement.source_record_id == record.id,
        )
    )
    image = db.scalar(
        select(m.ThreeDPrintingProductImage).where(
            m.ThreeDPrintingProductImage.product_id == record.product_id,
            m.ThreeDPrintingProductImage.factory_id == "huakang-a",
        )
    )
    return {
        "record": business.production_record_out(record),
        "file_versions": aliases,
        "requests": requests,
        "inventory_movements": [business.inventory_movement_out(r) for r in movements],
        "current_product_image": business.product_out(
            db.get(m.ThreeDPrintingProduct, record.product_id), image
        ).get("image_url")
        if image
        else None,
        "cost_snapshot": json.loads(record.calculated_cost_snapshot_json),
        "quality_flags": json.loads(record.data_quality_flags_json),
        "run_evidence": [
            out(r)
            for r in db.scalars(
                select(MODEL).where(
                    MODEL.factory_id == "huakang-a",
                    MODEL.kind == "run_evidence",
                    MODEL.resource_key == record.id,
                    MODEL.status == "active",
                )
            )
        ],
        "material_lot_evidence": "Operator-confirmed spool snapshots; no automatic spool stock deduction",
    }
