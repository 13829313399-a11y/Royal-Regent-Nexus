from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_schedule import (
    InjectionScheduleFactorySettings,
    InjectionScheduleImportBatch,
    InjectionScheduleImportIssue,
    InjectionScheduleImportRequestBinding,
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleMold,
    InjectionScheduleOrderDemand,
    InjectionScheduleShiftOutput,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling.audit import write_audit_event
from app.services.injection_scheduling.importer import parse_workbook_preview

IMPORT_CONTRACT_VERSION = "injection-import-v2"


def _refresh_preview_summary(parsed: dict[str, object]) -> None:
    issues = list(parsed.get("issues", []))
    summary = dict(parsed.get("summary", {}))
    summary["blocking_issue_count"] = sum(
        1 for issue in issues if issue.get("blocking")
    )
    summary["warning_count"] = sum(
        1 for issue in issues if issue.get("severity") == "WARNING"
    )
    parsed["summary"] = summary


def _enrich_from_master_data(
    db: Session, factory_id: str, parsed: dict[str, object]
) -> None:
    molds = db.scalars(
        select(InjectionScheduleMold).where(
            InjectionScheduleMold.factory_id == factory_id,
            InjectionScheduleMold.status == "ACTIVE",
        )
    ).all()
    exact = {(item.mold_code, item.product_code): item for item in molds}
    by_code = {item.mold_code: item for item in molds}
    issues = list(parsed.get("issues", []))
    for row in parsed.get("rows", []):
        mold = exact.get(
            (str(row.get("mold_code") or ""), str(row.get("product_code") or ""))
        )
        if mold is None:
            mold = by_code.get(str(row.get("mold_code") or ""))
        if mold is None:
            continue
        filled_fields: list[str] = []
        if (
            not row.get("required_machine_a_value")
            and mold.mold_ounce_requirement is not None
        ):
            row["required_machine_a_value"] = str(mold.mold_ounce_requirement)
            row["required_machine_a_label"] = (
                mold.required_machine_a_label or f"{mold.mold_ounce_requirement}A"
            )
            filled_fields.append("required_machine_a_value")
        if not row.get("daily_target") and mold.daily_target is not None:
            row["daily_target"] = str(mold.daily_target)
            filled_fields.append("daily_target")
        if not row.get("product_name") and mold.product_name:
            row["product_name"] = mold.product_name
            filled_fields.append("product_name")
        if not filled_fields:
            continue
        issues = [
            issue
            for issue in issues
            if not (
                issue.get("source_row") == row.get("source_row")
                and issue.get("field_name") in filled_fields
                and issue.get("blocking")
            )
        ]
        issues.append(
            {
                "source_row": row.get("source_row"),
                "field_name": ",".join(filled_fields),
                "raw_value": "",
                "severity": "WARNING",
                "error_type": "FILLED_FROM_MOLD_MASTER",
                "message": "缺失字段已从模具主数据补齐，请在预览中复核",
                "blocking": False,
            }
        )
        row["data_completeness_status"] = "COMPLETE"
    parsed["issues"] = issues
    _refresh_preview_summary(parsed)


def _annotate_preview_difference(
    db: Session, factory_id: str, parsed: dict[str, object]
) -> None:
    rows = list(parsed.get("rows", []))
    keys = [str(row["business_key"]) for row in rows]
    existing = (
        db.scalars(
            select(InjectionScheduleOrderDemand).where(
                InjectionScheduleOrderDemand.factory_id == factory_id,
                InjectionScheduleOrderDemand.business_key.in_(keys),
                InjectionScheduleOrderDemand.status.notin_(("COMPLETED", "CANCELLED")),
            )
        ).all()
        if keys
        else []
    )
    existing_by_key = {item.business_key: item for item in existing}
    create_count = update_count = unchanged_count = 0
    comparison_fields = (
        "order_no",
        "product_code",
        "mold_code",
        "product_name",
        "priority",
        "delivery_due_date",
        "color",
        "material_name",
        "remark",
    )
    decimal_fields = ("quantity_sets", "total_sets", "order_shots", "daily_target")
    for row in rows:
        current = existing_by_key.get(str(row["business_key"]))
        if current is None:
            row["change_action"] = "CREATE"
            create_count += 1
            continue
        changed = any(
            str(getattr(current, field) or "") != str(row.get(field) or "")
            for field in comparison_fields
        )
        changed = changed or any(
            (getattr(current, field) is None) != (row.get(field) in (None, ""))
            or (
                getattr(current, field) is not None
                and row.get(field) not in (None, "")
                and Decimal(str(getattr(current, field))) != Decimal(str(row[field]))
            )
            for field in decimal_fields
        )
        row["change_action"] = "UPDATE" if changed else "UNCHANGED"
        if changed:
            update_count += 1
        else:
            unchanged_count += 1
    summary = dict(parsed.get("summary", {}))
    summary.update(
        create_count=create_count,
        update_count=update_count,
        unchanged_count=unchanged_count,
    )
    parsed["summary"] = summary


def _now_text() -> str:
    return business_now().isoformat(timespec="seconds")


def _load_payload(batch: InjectionScheduleImportBatch) -> dict[str, object]:
    try:
        payload = json.loads(batch.summary_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail="导入预览数据损坏，请重新上传"
        ) from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=500, detail="导入预览数据损坏，请重新上传")
    return payload


def _preview_out(batch: InjectionScheduleImportBatch) -> dict[str, object]:
    payload = _load_payload(batch)
    return {
        "batch_id": batch.id,
        "factory_id": batch.factory_id,
        "status": batch.status,
        **payload,
    }


def preview_import(
    db: Session,
    *,
    factory_id: str,
    content: bytes,
    file_name: str,
    request_id: str,
    profile_override: str,
    actor: AuthContext,
) -> dict[str, object]:
    request_id = request_id.strip()
    if not request_id or len(request_id) > 128:
        raise HTTPException(status_code=422, detail="request_id 必须为 1 到 128 个字符")

    existing_binding = db.scalar(
        select(InjectionScheduleImportRequestBinding).where(
            InjectionScheduleImportRequestBinding.factory_id == factory_id,
            InjectionScheduleImportRequestBinding.request_id == request_id,
        )
    )
    if existing_binding is not None:
        batch = db.scalar(
            select(InjectionScheduleImportBatch).where(
                InjectionScheduleImportBatch.id == existing_binding.batch_id,
                InjectionScheduleImportBatch.factory_id == factory_id,
            )
        )
        if batch is None:
            raise HTTPException(status_code=409, detail="导入请求绑定已存在但批次缺失")
        return _preview_out(batch)

    parsed = parse_workbook_preview(
        content=content,
        file_name=file_name,
        factory_id=factory_id,
        profile_override=profile_override,
    )
    _enrich_from_master_data(db, factory_id, parsed)
    _annotate_preview_difference(db, factory_id, parsed)
    existing_batch = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.factory_id == factory_id,
            InjectionScheduleImportBatch.source_file_sha256
            == parsed["source_file_sha256"],
            InjectionScheduleImportBatch.template_version == IMPORT_CONTRACT_VERSION,
        )
    )
    now = _now_text()
    if existing_batch is not None:
        db.add(
            InjectionScheduleImportRequestBinding(
                id=f"is-import-request-{uuid4().hex}",
                factory_id=factory_id,
                request_id=request_id,
                source_file_sha256=str(parsed["source_file_sha256"]),
                batch_id=existing_batch.id,
                created_at=now,
            )
        )
        db.commit()
        return _preview_out(existing_batch)

    issues = list(parsed.pop("issues"))
    public_payload = {**parsed, "issues": issues}
    summary = parsed.get("summary", {})
    blocking_count = int(summary.get("blocking_issue_count", 0))
    batch = InjectionScheduleImportBatch(
        id=f"is-import-{uuid4().hex}",
        factory_id=factory_id,
        source_file_name=str(parsed["source_file_name"]),
        source_file_sha256=str(parsed["source_file_sha256"]),
        source_size_bytes=int(parsed["source_size_bytes"]),
        source_sheet=str(parsed["source_sheet"]),
        template_family="injection_scheduling_import",
        template_version=IMPORT_CONTRACT_VERSION,
        contract_fingerprint=hashlib.sha256(
            f"{IMPORT_CONTRACT_VERSION}:{parsed['profile_code']}".encode()
        ).hexdigest(),
        document_type=str(parsed["document_type"]),
        import_profile_code=str(parsed["profile_code"]),
        header_payload_json=json.dumps(parsed.get("header", {}), ensure_ascii=False),
        status="PREVIEW" if blocking_count else "READY",
        summary_json=json.dumps(
            public_payload, ensure_ascii=False, separators=(",", ":")
        ),
        issue_count=len(issues),
        blocking_issue_count=blocking_count,
        preview_request_id=request_id,
        created_by=actor.id,
        created_by_name=actor.display_name,
        created_at=now,
    )
    db.add(batch)
    db.flush()
    db.add(
        InjectionScheduleImportRequestBinding(
            id=f"is-import-request-{uuid4().hex}",
            factory_id=factory_id,
            request_id=request_id,
            source_file_sha256=batch.source_file_sha256,
            batch_id=batch.id,
            created_at=now,
        )
    )
    for issue in issues:
        db.add(
            InjectionScheduleImportIssue(
                id=f"is-import-issue-{uuid4().hex}",
                factory_id=factory_id,
                batch_id=batch.id,
                source_sheet=batch.source_sheet,
                source_row=issue.get("source_row"),
                field_name=str(issue.get("field_name") or ""),
                raw_value=str(issue.get("raw_value") or ""),
                severity=str(issue["severity"]),
                error_type=str(issue["error_type"]),
                message=str(issue["message"]),
                blocking=bool(issue["blocking"]),
                created_at=now,
            )
        )
    db.commit()
    db.refresh(batch)
    return _preview_out(batch)


def get_import_batch(db: Session, factory_id: str, batch_id: str) -> dict[str, object]:
    batch = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.id == batch_id,
            InjectionScheduleImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    return _preview_out(batch)


def reject_import(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
    reason: str,
    actor: AuthContext,
) -> dict[str, object]:
    batch = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.id == batch_id,
            InjectionScheduleImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status == "CONFIRMED":
        raise HTTPException(status_code=409, detail="已确认导入的批次不能拒绝")
    batch.status = "REJECTED"
    batch.confirmed_by = actor.id
    batch.confirmed_by_name = actor.display_name
    batch.confirmed_at = _now_text()
    batch.version += 1
    payload = _load_payload(batch)
    payload["rejection_reason"] = reason.strip()
    batch.summary_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="IMPORT_REJECTED",
        entity_type="IMPORT_BATCH",
        entity_id=batch.id,
        entity_version=batch.version,
        actor=actor,
        reason=reason,
        after={"status": batch.status},
    )
    db.commit()
    db.refresh(batch)
    return _preview_out(batch)


def _decimal_or_none(value: object) -> Decimal | None:
    return Decimal(str(value)) if value not in (None, "") else None


ORDER_MUTABLE_FIELDS = (
    "order_no",
    "product_code",
    "mold_code",
    "product_name",
    "priority",
    "order_date",
    "delivery_start_date",
    "delivery_due_date",
    "warehouse",
    "delivery_location",
    "ordered_by_name",
    "operator_name",
    "color",
    "pigment_code",
    "material_name",
    "required_machine_a_label",
    "data_completeness_status",
    "remark",
)
ORDER_DECIMAL_FIELDS = (
    "quantity_sets",
    "total_sets",
    "order_shots",
    "water_ratio",
    "net_weight_g",
    "gross_weight_g",
    "material_weight_kg",
    "daily_target",
    "required_machine_a_value",
)


def commit_import(
    db: Session,
    *,
    factory_id: str,
    batch_id: str,
    request_id: str,
    actor: AuthContext,
) -> dict[str, object]:
    batch = db.scalar(
        select(InjectionScheduleImportBatch).where(
            InjectionScheduleImportBatch.id == batch_id,
            InjectionScheduleImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入批次不存在")
    if batch.status == "REJECTED":
        raise HTTPException(status_code=409, detail="已拒绝的批次不能确认导入")
    payload = _load_payload(batch)
    if batch.status == "CONFIRMED":
        if batch.commit_request_id != request_id:
            raise HTTPException(status_code=409, detail="该批次已由其他请求确认")
        return dict(payload["commit_result"])
    if batch.blocking_issue_count:
        raise HTTPException(status_code=409, detail="批次仍有阻塞错误，不能确认导入")
    if not request_id.strip() or len(request_id) > 128:
        raise HTTPException(status_code=422, detail="request_id 必须为 1 到 128 个字符")

    settings = db.scalar(
        select(InjectionScheduleFactorySettings).where(
            InjectionScheduleFactorySettings.factory_id == factory_id
        )
    )
    fallback_water_ratio = (
        settings.fallback_water_ratio if settings else Decimal("0.01")
    )
    now = _now_text()
    created_count = updated_count = skipped_count = 0
    lines_by_business_key: dict[str, InjectionScheduleLine] = {}
    for machine_row in payload.get("machines", []):
        machine_code = str(machine_row.get("machine_code") or "").strip()
        if not machine_code:
            continue
        machine = db.scalar(
            select(InjectionScheduleMachine).where(
                InjectionScheduleMachine.factory_id == factory_id,
                InjectionScheduleMachine.machine_code == machine_code,
            )
        )
        machine_label = str(machine_row.get("machine_a_label") or "")
        machine_value = _decimal_or_none(machine_row.get("machine_a_value"))
        if machine is None:
            db.add(
                InjectionScheduleMachine(
                    id=f"is-machine-{uuid4().hex}",
                    factory_id=factory_id,
                    machine_code=machine_code,
                    position=machine_code,
                    machine_name="",
                    machine_a_label=machine_label,
                    machine_ounce_capacity=machine_value,
                    status="AVAILABLE",
                    created_by=actor.id,
                    created_by_name=actor.display_name,
                    updated_by=actor.id,
                    updated_by_name=actor.display_name,
                    created_at=now,
                    updated_at=now,
                )
            )
        elif machine_label and not machine.machine_a_label:
            machine.machine_a_label = machine_label
            machine.machine_ounce_capacity = (
                machine.machine_ounce_capacity or machine_value
            )
            machine.updated_by = actor.id
            machine.updated_by_name = actor.display_name
            machine.updated_at = now
            machine.version += 1

    for row in payload.get("rows", []):
        business_key = str(row["business_key"])
        existing = db.scalar(
            select(InjectionScheduleOrderDemand).where(
                InjectionScheduleOrderDemand.factory_id == factory_id,
                InjectionScheduleOrderDemand.business_key == business_key,
                InjectionScheduleOrderDemand.status.notin_(("COMPLETED", "CANCELLED")),
            )
        )
        values: dict[str, object] = {
            field: row.get(field, "") for field in ORDER_MUTABLE_FIELDS
        }
        values.update(
            {field: _decimal_or_none(row.get(field)) for field in ORDER_DECIMAL_FIELDS}
        )
        if values["water_ratio"] is None:
            values["water_ratio"] = fallback_water_ratio
        values["spray_required"] = bool(row.get("spray_required"))
        if existing is None:
            order = InjectionScheduleOrderDemand(
                id=f"is-order-{uuid4().hex}",
                factory_id=factory_id,
                source_batch_id=batch.id,
                source_sheet=str(row["source_sheet"]),
                source_row=int(row["source_row"]),
                demand_line_no=str(row["demand_line_no"]),
                business_key=business_key,
                raw_total_sets=_decimal_or_none(row.get("total_sets")),
                raw_source_json=json.dumps(
                    row.get("raw_source", {}), ensure_ascii=False
                ),
                material_status="UNPREPARED",
                status="PENDING",
                created_by=actor.id,
                created_by_name=actor.display_name,
                updated_by=actor.id,
                updated_by_name=actor.display_name,
                created_at=now,
                updated_at=now,
                **values,
            )
            db.add(order)
            db.flush()
            mold = db.scalar(
                select(InjectionScheduleMold).where(
                    InjectionScheduleMold.factory_id == factory_id,
                    InjectionScheduleMold.mold_code == order.mold_code,
                    InjectionScheduleMold.product_code == order.product_code,
                )
            )
            line = InjectionScheduleLine(
                    id=f"is-line-{uuid4().hex}",
                    factory_id=factory_id,
                    order_demand_id=order.id,
                    mold_id=mold.id if mold else None,
                    status="PENDING",
                    priority=order.priority,
                    system_daily_target=order.daily_target,
                    effective_daily_target=order.daily_target,
                    schedule_revision=1,
                    schedule_source="IMPORT",
                    created_by=actor.id,
                    created_by_name=actor.display_name,
                    updated_by=actor.id,
                    updated_by_name=actor.display_name,
                    created_at=now,
                    updated_at=now,
                )
            db.add(line)
            lines_by_business_key[business_key] = line
            created_count += 1
            continue

        changed = any(
            getattr(existing, field) != value for field, value in values.items()
        )
        if not changed:
            skipped_count += 1
            line = db.scalar(
                select(InjectionScheduleLine).where(
                    InjectionScheduleLine.factory_id == factory_id,
                    InjectionScheduleLine.order_demand_id == existing.id,
                    InjectionScheduleLine.status.notin_(("COMPLETED", "CANCELLED")),
                )
            )
            if line is not None:
                lines_by_business_key[business_key] = line
            continue
        if existing.status == "IN_PRODUCTION":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"订单 {existing.order_no} 已进入生产，关键字段变更需单独人工确认"
                ),
            )
        for field, value in values.items():
            setattr(existing, field, value)
        existing.source_batch_id = batch.id
        existing.source_sheet = str(row["source_sheet"])
        existing.source_row = int(row["source_row"])
        existing.raw_source_json = json.dumps(
            row.get("raw_source", {}), ensure_ascii=False
        )
        existing.updated_by = actor.id
        existing.updated_by_name = actor.display_name
        existing.updated_at = now
        existing.version += 1
        updated_count += 1

        line = db.scalar(
            select(InjectionScheduleLine).where(
                InjectionScheduleLine.factory_id == factory_id,
                InjectionScheduleLine.order_demand_id == existing.id,
                InjectionScheduleLine.status.notin_(("COMPLETED", "CANCELLED")),
            )
        )
        if line is not None:
            lines_by_business_key[business_key] = line
            line.priority = existing.priority
            line.system_daily_target = existing.daily_target
            if line.manual_daily_target is None:
                line.effective_daily_target = existing.daily_target
            line.updated_by = actor.id
            line.updated_by_name = actor.display_name
            line.updated_at = now
            line.version += 1

    history_created_count = history_updated_count = history_unchanged_count = 0
    for history_row in payload.get("history_outputs", []):
        line = lines_by_business_key.get(str(history_row.get("business_key") or ""))
        if line is None:
            continue
        production_date = str(history_row["production_date"])
        shift = str(history_row["shift"])
        reported_shots = Decimal(str(history_row["reported_shots"]))
        output = db.scalar(
            select(InjectionScheduleShiftOutput).where(
                InjectionScheduleShiftOutput.factory_id == factory_id,
                InjectionScheduleShiftOutput.schedule_line_id == line.id,
                InjectionScheduleShiftOutput.production_date == production_date,
                InjectionScheduleShiftOutput.shift == shift,
            )
        )
        if output is None:
            db.add(
                InjectionScheduleShiftOutput(
                    id=f"is-shift-{uuid4().hex}",
                    factory_id=factory_id,
                    schedule_line_id=line.id,
                    production_date=production_date,
                    shift=shift,
                    reported_shots=reported_shots,
                    defect_shots=Decimal("0"),
                    qualified_shots=reported_shots,
                    remark=(
                        f"从 {batch.source_file_name} 第 "
                        f"{history_row.get('source_row')} 行迁移"
                    ),
                    reported_by=actor.id,
                    reported_by_name=actor.display_name,
                    reported_at=now,
                    updated_at=now,
                )
            )
            history_created_count += 1
            continue
        if output.reported_shots == reported_shots and output.defect_shots == 0:
            history_unchanged_count += 1
            continue
        output.reported_shots = reported_shots
        output.defect_shots = Decimal("0")
        output.qualified_shots = reported_shots
        output.reported_by = actor.id
        output.reported_by_name = actor.display_name
        output.reported_at = now
        output.updated_at = now
        output.version += 1
        history_updated_count += 1

    result = {
        "batch_id": batch.id,
        "factory_id": factory_id,
        "status": "CONFIRMED",
        "created_count": created_count,
        "updated_count": updated_count,
        "skipped_count": skipped_count,
        "history_created_count": history_created_count,
        "history_updated_count": history_updated_count,
        "history_unchanged_count": history_unchanged_count,
    }
    batch.status = "CONFIRMED"
    batch.commit_request_id = request_id
    batch.confirmed_by = actor.id
    batch.confirmed_by_name = actor.display_name
    batch.confirmed_at = now
    batch.version += 1
    payload["commit_result"] = result
    batch.summary_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="IMPORT_CONFIRMED",
        entity_type="IMPORT_BATCH",
        entity_id=batch.id,
        entity_version=batch.version,
        actor=actor,
        after=result,
    )
    db.commit()
    return result
