from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, business_now
from app.models.injection_scheduling import (
    InjectionSchedulingAuditEvent,
    InjectionSchedulingImportBatch,
    InjectionSchedulingImportIssue,
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
    InjectionSchedulingOrder,
    InjectionSchedulingPlan,
    InjectionSchedulingPlanRevision,
    InjectionSchedulingPublishedSnapshot,
    InjectionSchedulingRuleSet,
    InjectionSchedulingTask,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext
from app.services.injection_scheduling_import import ParsedInjectionScheduleImport


SCHEDULING_DEPARTMENTS = ("production", "molding", "management")
DEFAULT_RULE_CONFIG = {
    "version": "default-v1",
    "changeover": {
        "sameMoldHours": 0,
        "moldChangeHours": 1.5,
        "colorLightToDarkHours": 0.5,
        "colorDarkToLightHours": 1.5,
    },
    "calendar": {"timezone": "Asia/Shanghai", "mode": "continuous"},
    "notes": "首版默认规则；缺失工艺参数的机台和模具必须人工复核。",
}


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _sha(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _require_factory(factory_id: str) -> str:
    normalized = factory_id.strip()
    if normalized not in ALLOWED_FACTORY_IDS:
        raise HTTPException(status_code=400, detail="厂区参数无效")
    return normalized


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def _add_audit(
    db: Session,
    *,
    factory_id: str,
    plan_id: str,
    action: str,
    reason: str,
    user: AuthContext,
    old_revision: int | None = None,
    new_revision: int | None = None,
    detail: dict[str, Any] | None = None,
    request_id: str = "",
) -> None:
    db.add(
        InjectionSchedulingAuditEvent(
            id=f"isaudit-{uuid4().hex}",
            factory_id=factory_id,
            plan_id=plan_id,
            action=action,
            old_revision=old_revision,
            new_revision=new_revision,
            reason=reason,
            detail_json=_json(detail or {}),
            actor_id=user.id,
            actor_name=_actor_name(user),
            request_id=request_id[:128],
            created_at=_now(),
        )
    )


def create_import_preview(
    db: Session,
    *,
    parsed: ParsedInjectionScheduleImport,
    user: AuthContext,
    request_id: str = "",
) -> InjectionSchedulingImportBatch:
    factory_id = _require_factory(parsed.factory_id)
    preview_revision = int(
        db.scalar(
            select(func.max(InjectionSchedulingImportBatch.preview_revision)).where(
                InjectionSchedulingImportBatch.factory_id == factory_id,
                InjectionSchedulingImportBatch.business_date == parsed.business_date,
            )
        )
        or 0
    ) + 1
    now = _now()
    batch = InjectionSchedulingImportBatch(
        id=f"isimport-{uuid4().hex}",
        factory_id=factory_id,
        source_file_name=parsed.source_file_name[:255],
        source_sha256=parsed.source_sha256,
        source_size_bytes=parsed.source_size_bytes,
        business_date=parsed.business_date,
        parser_version=parsed.parser_version,
        preview_revision=preview_revision,
        status="preview",
        normalized_json=_json(parsed.normalized),
        summary_json=_json(parsed.summary),
        blocker_count=parsed.blocker_count,
        warning_count=parsed.warning_count,
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
    )
    db.add(batch)
    db.flush()
    for index, issue in enumerate(parsed.issues):
        db.add(
            InjectionSchedulingImportIssue(
                id=f"{batch.id}:issue:{index + 1}",
                batch_id=batch.id,
                factory_id=factory_id,
                severity=issue.severity,
                code=issue.code,
                sheet_name=issue.sheet_name,
                source_row=issue.source_row,
                field=issue.field,
                source_value=issue.source_value[:4000],
                message=issue.message,
            )
        )
    _add_audit(
        db,
        factory_id=factory_id,
        plan_id="",
        action="import_preview",
        reason="预览 Excel 导入",
        user=user,
        detail={
            "batchId": batch.id,
            "sourceSha256": parsed.source_sha256,
            "summary": parsed.summary,
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(batch)
    return batch


def list_import_issues(
    db: Session,
    batch_id: str,
    factory_id: str,
) -> list[InjectionSchedulingImportIssue]:
    return list(
        db.scalars(
            select(InjectionSchedulingImportIssue)
            .where(
                InjectionSchedulingImportIssue.batch_id == batch_id,
                InjectionSchedulingImportIssue.factory_id == factory_id,
            )
            .order_by(
                InjectionSchedulingImportIssue.severity,
                InjectionSchedulingImportIssue.source_row,
                InjectionSchedulingImportIssue.id,
            )
        ).all()
    )


def _ensure_rule_set(
    db: Session,
    *,
    factory_id: str,
    user: AuthContext,
) -> InjectionSchedulingRuleSet:
    rule_set = db.scalar(
        select(InjectionSchedulingRuleSet)
        .where(
            InjectionSchedulingRuleSet.factory_id == factory_id,
            InjectionSchedulingRuleSet.status == "active",
        )
        .order_by(InjectionSchedulingRuleSet.revision.desc())
    )
    if rule_set is not None:
        return rule_set
    rule_set = InjectionSchedulingRuleSet(
        id=f"isrules-{uuid4().hex}",
        factory_id=factory_id,
        revision=1,
        status="active",
        config_json=_json(DEFAULT_RULE_CONFIG),
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=_now(),
    )
    db.add(rule_set)
    db.flush()
    return rule_set


def _upsert_masters(
    db: Session,
    *,
    batch: InjectionSchedulingImportBatch,
    normalized: dict[str, Any],
    now: str,
) -> None:
    factory_id = batch.factory_id
    for item in normalized.get("machines", []):
        machine = db.get(InjectionSchedulingMachine, item["id"])
        if machine is not None and machine.factory_id != factory_id:
            raise HTTPException(status_code=409, detail="机台主键厂区冲突")
        if machine is None:
            machine = InjectionSchedulingMachine(
                id=item["id"],
                factory_id=factory_id,
                machine_code=item["machineCode"],
                machine_name=item["machineName"],
                source_batch_id=batch.id,
                created_at=now,
                updated_at=now,
            )
            db.add(machine)
        else:
            machine.revision += 1
        machine.machine_code = item["machineCode"]
        machine.machine_name = item["machineName"]
        machine.workshop = item.get("workshop", "")
        machine.state = item.get("state", "idle")
        machine.machine_class = item.get("machineClass", "")
        machine.tonnage = item.get("tonnage")
        machine.injection_capacity_g = str(item.get("injectionCapacityG") or "")
        machine.safety_utilization = str(item.get("safetyUtilization") or 0.82)
        machine.mold_width_mm = str(item.get("moldWidthMm") or "")
        machine.mold_height_mm = str(item.get("moldHeightMm") or "")
        machine.robot_level = item.get("robotLevel", "none")
        machine.capabilities_json = _json(
            {
                **item.get("capabilities", {}),
                "kind": item.get("kind", "普通机"),
            }
        )
        machine.restrictions_json = _json(item.get("restrictions", []))
        machine.completeness = item.get("completeness", "needs_review")
        machine.source_batch_id = batch.id
        machine.source_lineage_json = _json(item.get("sourceLineage", {}))
        machine.updated_at = now
    db.flush()

    for item in normalized.get("molds", []):
        mold = db.get(InjectionSchedulingMold, item["id"])
        if mold is not None and mold.factory_id != factory_id:
            raise HTTPException(status_code=409, detail="模具主键厂区冲突")
        if mold is None:
            mold = InjectionSchedulingMold(
                id=item["id"],
                factory_id=factory_id,
                mold_no=item["moldNo"],
                source_batch_id=batch.id,
                created_at=now,
                updated_at=now,
            )
            db.add(mold)
        else:
            mold.revision += 1
        mold.mold_no = item["moldNo"]
        mold.product_name = item.get("productName", "")
        mold.status = item.get("status", "available")
        mold.machine_class_requirement = item.get("machineClassRequirement", "")
        mold.length_mm = str(item.get("lengthMm") or "")
        mold.width_mm = str(item.get("widthMm") or "")
        mold.thickness_mm = str(item.get("thicknessMm") or "")
        mold.shot_weight_g = str(item.get("shotWeightG") or "")
        mold.material = item.get("material", "")
        mold.robot_requirement = item.get("robotRequirement", "none")
        mold.core_pull_required = bool(item.get("corePullRequired"))
        mold.unscrew_required = bool(item.get("unscrewRequired"))
        mold.attributes_json = _json(item.get("attributes", {}))
        mold.completeness = item.get("completeness", "needs_review")
        mold.source_batch_id = batch.id
        mold.source_lineage_json = _json(item.get("sourceLineage", {}))
        mold.updated_at = now
    db.flush()

    for item in normalized.get("orders", []):
        order = db.get(InjectionSchedulingOrder, item["id"])
        if order is not None and order.factory_id != factory_id:
            raise HTTPException(status_code=409, detail="订单主键厂区冲突")
        if order is None:
            order = InjectionSchedulingOrder(
                id=item["id"],
                factory_id=factory_id,
                natural_key=item["naturalKey"],
                order_no=item["orderNo"],
                mold_id=item["moldId"],
                source_batch_id=batch.id,
                created_at=now,
                updated_at=now,
            )
            db.add(order)
        else:
            order.revision += 1
        order.natural_key = item["naturalKey"]
        order.order_no = item["orderNo"]
        order.item_no = item.get("itemNo", "")
        order.mold_id = item["moldId"]
        order.product_name = item.get("productName", "")
        order.order_qty = int(item.get("orderQty") or 0)
        order.completed_qty = int(item.get("completedQty") or 0)
        order.remaining_qty = int(item.get("remainingQty") or 0)
        order.daily_target = int(item.get("dailyTarget") or 0)
        order.material = item.get("material", "")
        order.color = item.get("color", "")
        order.delivery_due_at = item.get("deliveryDueAt", "")
        order.priority_code = item.get("priorityCode", "P2")
        order.priority_flag = item.get("priorityFlag", "")
        order.requirement_json = _json(item.get("requirement", {}))
        order.completeness = item.get("completeness", "needs_review")
        order.source_batch_id = batch.id
        order.source_lineage_json = _json(item.get("sourceLineage", {}))
        order.updated_at = now
    db.flush()


def _as_float(value: str | int | float | None) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(value: str) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=BUSINESS_TIME_ZONE)
    return parsed.astimezone(BUSINESS_TIME_ZONE)


PUBLIC_WORKSHEET_FIELDS = {
    "automationMode",
    "remark",
    "warehouse",
    "machineClassRequirement",
    "setQuantity",
    "waterRatio",
    "colorPowder",
    "netWeightGrams",
    "grossWeightGrams",
    "materialWeightKg",
    "orderDate",
    "deliveryStartAt",
    "deliveryDueAt",
    "moldChangeReferenceHours",
    "colorChangeReferenceHours",
    "changeoverHours",
    "downtimeHours",
    "plannedProductionAt",
    "plannedCompletionAt",
    "plannedCompletionMonth",
    "inboundAt",
    "deliverySlackDays",
    "sprayPaint",
    "productionDays",
    "materialShortage",
    "allocatedMaterialQuantity",
    "shiftEndAt",
    "shiftTime",
    "shiftTarget",
    "dayShiftQuantity",
    "nightShiftQuantity",
    "sourceSheet",
    "sourceRow",
}


def _sanitize_public_worksheet(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    return {
        key: deepcopy(value)
        for key, value in raw.items()
        if key in PUBLIC_WORKSHEET_FIELDS
    }


def _public_worksheet(order: dict[str, Any]) -> dict[str, Any]:
    return _sanitize_public_worksheet(
        order.get("requirement", {}).get("worksheet", {})
    )


def _public_task_worksheet(
    task: dict[str, Any],
    order: dict[str, Any],
    previous_task: dict[str, Any] | None = None,
) -> dict[str, Any]:
    for raw in (
        task.get("worksheet"),
        (previous_task or {}).get("worksheet"),
        order.get("requirement", {}).get("worksheet", {}),
    ):
        sanitized = _sanitize_public_worksheet(raw)
        if sanitized:
            return sanitized
    return {}


def _snapshot_from_import(
    *,
    batch: InjectionSchedulingImportBatch,
    plan: InjectionSchedulingPlan,
    normalized: dict[str, Any],
    rule_set: InjectionSchedulingRuleSet,
) -> dict[str, Any]:
    machines_raw = normalized.get("machines", [])
    molds_by_id = {item["id"]: item for item in normalized.get("molds", [])}
    orders_by_id = {item["id"]: item for item in normalized.get("orders", [])}
    task_ids_by_machine: dict[str, list[str]] = {
        machine["id"]: [] for machine in machines_raw
    }
    frontend_tasks: list[dict[str, Any]] = []
    machine_anchor: dict[str, datetime] = {}
    anchor = _parse_dt(normalized.get("anchorAt", "")) or business_now()

    for task in sorted(
        normalized.get("tasks", []),
        key=lambda item: (item["machineId"], int(item.get("sequence") or 0)),
    ):
        order = orders_by_id[task["orderId"]]
        mold = molds_by_id[order["moldId"]]
        machine_id = task["machineId"]
        duration = float(task.get("productionDurationHours") or 0)
        start = _parse_dt(task.get("plannedStart", "")) or machine_anchor.get(machine_id) or anchor
        end = _parse_dt(task.get("plannedEnd", "")) or (start + timedelta(hours=duration))
        machine_anchor[machine_id] = end
        sequence = len(task_ids_by_machine[machine_id]) + 1
        task_ids_by_machine[machine_id].append(task["id"])
        frontend_tasks.append(
            {
                "id": task["id"],
                "machineId": machine_id,
                "requirement": {
                    "productName": order.get("productName", ""),
                    "orderNo": order.get("orderNo", ""),
                    "itemNo": order.get("itemNo", ""),
                    "color": order.get("color", ""),
                    "colorFamily": order.get("requirement", {}).get("colorFamily", "special"),
                    "material": order.get("material", ""),
                    "mold": {
                        "moldNo": mold.get("moldNo", ""),
                        "widthMm": mold.get("widthMm"),
                        "heightMm": mold.get("lengthMm"),
                        "thicknessMm": mold.get("thicknessMm"),
                        "shotWeightGrams": mold.get("shotWeightG"),
                        "material": mold.get("material", ""),
                        "armRequirement": mold.get("robotRequirement", "none"),
                        "requiresCorePull": bool(mold.get("corePullRequired")),
                        "requiresUnscrewing": bool(mold.get("unscrewRequired")),
                        "state": "available",
                    },
                    "priorityCode": order.get("priorityCode", "P2"),
                    "priorityFlag": order.get("priorityFlag", ""),
                },
                "production": {
                    "orderQuantity": int(order.get("orderQty") or 0),
                    "completedQuantity": int(order.get("completedQty") or 0),
                    "remainingQuantity": int(order.get("remainingQty") or 0),
                    "effectiveDailyTarget": int(order.get("dailyTarget") or 0),
                    "productionDurationHours": duration,
                },
                "timing": {
                    "plannedStart": start.isoformat(timespec="seconds"),
                    "plannedEnd": end.isoformat(timespec="seconds"),
                    "inboundAt": task.get("inboundAt", ""),
                    "deliveryDueAt": order.get("deliveryDueAt", ""),
                    "slackHours": float(task.get("slackHours") or 0),
                },
                "changeover": {
                    "status": "ok",
                    "moldChangeHours": 0 if sequence == 1 else 1.5,
                    "colorChangeHours": 0,
                    "totalHours": 0 if sequence == 1 else 1.5,
                    "pathLabel": "导入队列",
                    "reason": "来自只读工作簿；发布前须复核换模与转色规则。",
                },
                "sequence": sequence,
                "current": bool(task.get("current")),
                "locked": bool(task.get("locked")),
                "risk": task.get("risk", "normal"),
                "remark": task.get("remark", ""),
                "worksheet": _public_task_worksheet(task, order),
            }
        )

    frontend_machines: list[dict[str, Any]] = []
    for machine in machines_raw:
        capabilities = machine.get("capabilities", {})
        task_ids = task_ids_by_machine[machine["id"]]
        frontend_machines.append(
            {
                "id": machine["id"],
                "name": machine.get("machineName", machine.get("machineCode", "")),
                "code": machine.get("machineCode", ""),
                "workshop": machine.get("workshop", ""),
                "kind": machine.get("kind", "普通机"),
                "capability": {
                    "machineClass": machine.get("machineClass") or "待复核",
                    "tonnage": int(machine.get("tonnage") or 0),
                    "shotCapacityGrams": _as_float(machine.get("injectionCapacityG")),
                    "safetyUtilization": _as_float(machine.get("safetyUtilization") or 0.82),
                    "tieBarWidthMm": _as_float(machine.get("moldWidthMm")),
                    "tieBarHeightMm": _as_float(machine.get("moldHeightMm")),
                    "minMoldThicknessMm": 0,
                    "maxMoldThicknessMm": 0,
                    "openingStrokeMm": 0,
                    "ejectionStrokeMm": 0,
                    "armType": machine.get("robotLevel", "none"),
                    "supportsCorePull": bool(capabilities.get("supportsCorePull")),
                    "supportsUnscrewing": bool(capabilities.get("supportsUnscrewing")),
                    "compatibleMaterials": capabilities.get("compatibleMaterials", []),
                    "screwType": capabilities.get("screwType", "standard"),
                },
                "restriction": "；".join(machine.get("restrictions", [])),
                "load": min(100, len(task_ids) * 10),
                "state": (
                    machine.get("state", "idle")
                    if machine.get("state") != "idle"
                    else ("running" if task_ids else "idle")
                ),
                "resourceState": (
                    "available"
                    if machine.get("completeness") == "complete"
                    else "warning"
                ),
                "taskIds": task_ids,
            }
        )

    scheduled_order_ids = {task["orderId"] for task in normalized.get("tasks", [])}
    backlog: list[dict[str, Any]] = []
    for order in normalized.get("orders", []):
        if order["id"] in scheduled_order_ids:
            continue
        mold = molds_by_id[order["moldId"]]
        backlog.append(
            {
                "id": order["id"],
                "requirement": {
                    "productName": order.get("productName", ""),
                    "orderNo": order.get("orderNo", ""),
                    "itemNo": order.get("itemNo", ""),
                    "color": order.get("color", ""),
                    "colorFamily": order.get("requirement", {}).get("colorFamily", "special"),
                    "material": order.get("material", ""),
                    "mold": {
                        "moldNo": mold.get("moldNo", ""),
                        "widthMm": mold.get("widthMm"),
                        "heightMm": mold.get("lengthMm"),
                        "thicknessMm": mold.get("thicknessMm"),
                        "shotWeightGrams": mold.get("shotWeightG"),
                        "material": mold.get("material", ""),
                        "armRequirement": mold.get("robotRequirement", "none"),
                        "requiresCorePull": bool(mold.get("corePullRequired")),
                        "requiresUnscrewing": bool(mold.get("unscrewRequired")),
                        "state": "available",
                    },
                    "priorityCode": order.get("priorityCode", "P2"),
                    "priorityFlag": order.get("priorityFlag", ""),
                },
                "production": {
                    "orderQuantity": int(order.get("orderQty") or 0),
                    "completedQuantity": int(order.get("completedQty") or 0),
                    "remainingQuantity": int(order.get("remainingQty") or 0),
                    "effectiveDailyTarget": int(order.get("dailyTarget") or 0),
                    "productionDurationHours": (
                        round(
                            int(order.get("remainingQty") or 0)
                            / int(order.get("dailyTarget") or 1)
                            * 24,
                            2,
                        )
                    ),
                },
                "requiredDate": order.get("deliveryDueAt", ""),
                "candidates": [],
                "worksheet": _public_worksheet(order),
                "noMatchReason": "能力参数或候选排序尚待复核",
            }
        )

    overdue_count = sum(task["risk"] == "overdue" for task in frontend_tasks)
    review_count = sum(
        machine.get("completeness") != "complete" for machine in machines_raw
    )
    calendar_end = anchor + timedelta(days=120)
    snapshot_at = _now()
    return {
        "factoryId": batch.factory_id,
        "sourceLabel": batch.source_file_name,
        "snapshotAt": snapshot_at,
        "notice": (
            f"正式后端草案；来源 {batch.source_file_name}，"
            f"导入批次 {batch.id}。能力参数缺失项仍需人工复核。"
        ),
        "plan": {
            "id": plan.id,
            "label": plan.label,
            "revision": plan.revision,
            "rulesVersion": f"rules-v{rule_set.revision}",
            "status": plan.status,
            "anchorAt": plan.anchor_at,
        },
        "calendar": {
            "timezone": "Asia/Shanghai",
            "availabilityWindows": [
                {
                    "startAt": anchor.isoformat(timespec="seconds"),
                    "endAt": calendar_end.isoformat(timespec="seconds"),
                    "label": "导入计划连续生产窗口",
                }
            ],
            "downtimeWindows": [],
        },
        "kpis": [
            {
                "label": "机台",
                "value": str(len(frontend_machines)),
                "detail": "当前厂区",
                "tone": "teal",
            },
            {
                "label": "排程任务",
                "value": str(len(frontend_tasks)),
                "detail": f"逾期 {overdue_count}",
                "tone": "amber" if overdue_count else "default",
                "action": "alerts",
            },
            {
                "label": "待排订单",
                "value": str(len(backlog)),
                "detail": "未分配机台",
                "tone": "violet",
                "action": "backlog",
            },
            {
                "label": "待复核",
                "value": str(review_count),
                "detail": "机台能力参数",
                "tone": "red" if review_count else "default",
                "action": "alerts",
            },
        ],
        "machines": frontend_machines,
        "tasks": frontend_tasks,
        "backlog": backlog,
    }


def _persist_tasks_from_snapshot(
    db: Session,
    *,
    plan: InjectionSchedulingPlan,
    snapshot: dict[str, Any],
    revision: int,
    now: str,
) -> None:
    factory_id = plan.factory_id
    machine_ids = set(
        db.scalars(
            select(InjectionSchedulingMachine.id).where(
                InjectionSchedulingMachine.factory_id == factory_id
            )
        ).all()
    )
    orders = list(
        db.scalars(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.factory_id == factory_id
            )
        ).all()
    )
    order_by_key = {
        (
            order.order_no.strip(),
            order.item_no.strip(),
            db.get(InjectionSchedulingMold, order.mold_id).mold_no.strip(),
        ): order
        for order in orders
    }
    existing_tasks = {
        task.id: task
        for task in db.scalars(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.factory_id == factory_id,
            )
        ).all()
    }
    received_ids: set[str] = set()
    normalized_tasks: list[dict[str, Any]] = []
    for task in snapshot.get("tasks", []):
        task_id = str(task.get("id", "")).strip()
        machine_id = str(task.get("machineId", "")).strip()
        if not task_id or machine_id not in machine_ids:
            raise HTTPException(status_code=422, detail="排程任务引用了无效机台")
        if task_id in received_ids:
            raise HTTPException(status_code=422, detail="排程任务 ID 重复")
        received_ids.add(task_id)
        old_task = existing_tasks.get(task_id)
        if old_task is not None:
            order = db.get(InjectionSchedulingOrder, old_task.order_id)
            if old_task.locked and (
                old_task.machine_id != machine_id
                or old_task.sequence != int(task.get("sequence") or 0)
            ):
                raise HTTPException(status_code=409, detail="当前任务已锁定，不能移动或调整顺序")
        else:
            requirement = task.get("requirement", {})
            mold = requirement.get("mold", {})
            key = (
                str(requirement.get("orderNo", "")).strip(),
                str(requirement.get("itemNo", "")).strip(),
                str(mold.get("moldNo", "")).strip(),
            )
            order = order_by_key.get(key)
        if order is None or order.factory_id != factory_id:
            raise HTTPException(status_code=422, detail="排程任务引用了无效订单")
        order_payload = {"requirement": _load_json(order.requirement_json, {})}
        previous_task_payload = (
            _load_json(old_task.task_json, {})
            if old_task is not None
            else None
        )
        task["worksheet"] = _public_task_worksheet(
            task,
            order_payload,
            previous_task_payload,
        )
        normalized_tasks.append(
            {
                "task": task,
                "machine_id": machine_id,
                "order_id": order.id,
            }
        )

    db.execute(
        delete(InjectionSchedulingTask).where(
            InjectionSchedulingTask.plan_id == plan.id,
            InjectionSchedulingTask.factory_id == factory_id,
        )
    )
    db.flush()
    lane_sequences: set[tuple[str, int]] = set()
    for item in normalized_tasks:
        task = item["task"]
        sequence = int(task.get("sequence") or 0)
        key = (item["machine_id"], sequence)
        if sequence < 1 or key in lane_sequences:
            raise HTTPException(status_code=422, detail="机台队列顺序无效或重复")
        lane_sequences.add(key)
        timing = task.get("timing", {})
        db.add(
            InjectionSchedulingTask(
                id=task["id"],
                plan_id=plan.id,
                factory_id=factory_id,
                machine_id=item["machine_id"],
                order_id=item["order_id"],
                sequence=sequence,
                is_current=bool(task.get("current")),
                locked=bool(task.get("locked")),
                planned_start=timing.get("plannedStart", ""),
                planned_end=timing.get("plannedEnd", ""),
                risk=task.get("risk", "normal"),
                task_json=_json(task),
                revision=revision,
                created_at=now,
                updated_at=now,
            )
        )
    db.flush()


def confirm_import(
    db: Session,
    *,
    batch_id: str,
    factory_id: str,
    preview_revision: int,
    reason: str,
    user: AuthContext,
    request_id: str = "",
) -> tuple[InjectionSchedulingPlan, InjectionSchedulingImportBatch, dict[str, Any]]:
    factory_id = _require_factory(factory_id)
    batch = db.scalar(
        select(InjectionSchedulingImportBatch).where(
            InjectionSchedulingImportBatch.id == batch_id,
            InjectionSchedulingImportBatch.factory_id == factory_id,
        )
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="找不到该厂区的导入预览")
    if batch.status != "preview":
        raise HTTPException(status_code=409, detail="该导入预览已确认或已失效")
    if batch.preview_revision != preview_revision:
        raise HTTPException(status_code=409, detail="导入预览版本已变化，请重新预览")
    if batch.blocker_count:
        raise HTTPException(status_code=422, detail="导入预览仍有阻断项，不能确认")

    normalized = _load_json(batch.normalized_json, {})
    if normalized.get("factoryId") != factory_id:
        raise HTTPException(status_code=409, detail="导入内容厂区不一致")

    now = _now()
    _upsert_masters(db, batch=batch, normalized=normalized, now=now)
    rule_set = _ensure_rule_set(db, factory_id=factory_id, user=user)
    current_plans = list(
        db.scalars(
            select(InjectionSchedulingPlan).where(
                InjectionSchedulingPlan.factory_id == factory_id,
                InjectionSchedulingPlan.is_current.is_(True),
            )
        ).all()
    )
    for current in current_plans:
        current.is_current = False
        current.status = "superseded"
        current.updated_at = now
        db.execute(
            delete(InjectionSchedulingTask).where(
                InjectionSchedulingTask.plan_id == current.id,
                InjectionSchedulingTask.factory_id == factory_id,
            )
        )
    db.flush()

    plan = InjectionSchedulingPlan(
        id=f"isplan-{uuid4().hex}",
        factory_id=factory_id,
        label=f"{batch.business_date} 导入草案",
        status="draft",
        is_current=True,
        revision=1,
        published_revision=0,
        anchor_at=normalized["anchorAt"],
        rule_set_id=rule_set.id,
        source_batch_id=batch.id,
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
        updated_by=user.id,
        updated_by_name=_actor_name(user),
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    snapshot = _snapshot_from_import(
        batch=batch,
        plan=plan,
        normalized=normalized,
        rule_set=rule_set,
    )
    _persist_tasks_from_snapshot(
        db,
        plan=plan,
        snapshot=snapshot,
        revision=1,
        now=now,
    )
    digest = _sha(snapshot)
    db.add(
        InjectionSchedulingPlanRevision(
            id=f"{plan.id}:r1",
            plan_id=plan.id,
            factory_id=factory_id,
            revision=1,
            status="draft",
            reason=reason,
            snapshot_json=_json(snapshot),
            snapshot_sha256=digest,
            created_by=user.id,
            created_by_name=_actor_name(user),
            created_at=now,
        )
    )
    batch.status = "confirmed"
    batch.confirmed_by = user.id
    batch.confirmed_by_name = _actor_name(user)
    batch.confirmed_at = now
    batch.confirm_reason = reason
    _add_audit(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        action="import_confirm",
        reason=reason,
        user=user,
        old_revision=None,
        new_revision=1,
        detail={
            "batchId": batch.id,
            "sourceSha256": batch.source_sha256,
            "summary": _load_json(batch.summary_json, {}),
            "snapshotSha256": digest,
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(plan)
    db.refresh(batch)
    return plan, batch, snapshot


def current_plan_snapshot(
    db: Session,
    *,
    factory_id: str,
) -> tuple[InjectionSchedulingPlan, dict[str, Any]]:
    factory_id = _require_factory(factory_id)
    plan = db.scalar(
        select(InjectionSchedulingPlan).where(
            InjectionSchedulingPlan.factory_id == factory_id,
            InjectionSchedulingPlan.is_current.is_(True),
        )
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="该厂区尚无正式后端排程草案")
    revision = db.scalar(
        select(InjectionSchedulingPlanRevision).where(
            InjectionSchedulingPlanRevision.plan_id == plan.id,
            InjectionSchedulingPlanRevision.factory_id == factory_id,
            InjectionSchedulingPlanRevision.revision == plan.revision,
        )
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="排程草案版本不完整")
    snapshot = deepcopy(_load_json(revision.snapshot_json, {}))
    if snapshot.get("factoryId") != factory_id:
        raise HTTPException(status_code=409, detail="排程快照厂区不一致")
    plan_payload = {
        **snapshot.get("plan", {}),
        "id": plan.id,
        "label": plan.label,
        "revision": plan.revision,
        "status": plan.status,
    }
    if plan.status == "published" and plan.published_revision == plan.revision:
        published = db.scalar(
            select(InjectionSchedulingPublishedSnapshot).where(
                InjectionSchedulingPublishedSnapshot.plan_id == plan.id,
                InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
                InjectionSchedulingPublishedSnapshot.plan_revision == plan.revision,
                InjectionSchedulingPublishedSnapshot.is_current.is_(True),
            )
        )
        if published is not None:
            plan_payload["publishedAt"] = published.published_at
    else:
        plan_payload.pop("publishedAt", None)
    snapshot["plan"] = plan_payload
    return plan, snapshot


def validate_move(
    db: Session,
    *,
    factory_id: str,
    revision: int,
    task_id: str | None,
    backlog_id: str | None,
    target_machine_id: str,
) -> dict[str, Any]:
    plan, _ = current_plan_snapshot(db, factory_id=factory_id)
    if plan.revision != revision:
        raise HTTPException(status_code=409, detail="草案版本冲突，请刷新后重试")
    target = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.id == target_machine_id,
            InjectionSchedulingMachine.factory_id == factory_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=422, detail="目标机台不属于当前厂区")
    reasons: list[str] = []
    complete = target.completeness == "complete"
    if task_id:
        task = db.scalar(
            select(InjectionSchedulingTask).where(
                InjectionSchedulingTask.id == task_id,
                InjectionSchedulingTask.plan_id == plan.id,
                InjectionSchedulingTask.factory_id == factory_id,
            )
        )
        if task is None:
            raise HTTPException(status_code=404, detail="找不到当前厂区的排程任务")
        if task.locked or task.is_current:
            reasons.append("当前任务已锁定，不能移动")
    elif backlog_id:
        order = db.scalar(
            select(InjectionSchedulingOrder).where(
                InjectionSchedulingOrder.id == backlog_id,
                InjectionSchedulingOrder.factory_id == factory_id,
            )
        )
        if order is None:
            raise HTTPException(status_code=404, detail="找不到当前厂区的待排订单")
    else:
        raise HTTPException(status_code=422, detail="必须指定排程任务或待排订单")
    if not complete:
        reasons.append("目标机台能力参数不完整，需人工复核")
    allowed = not any("锁定" in reason for reason in reasons)
    return {
        "allowed": allowed,
        "eligibility": {
            "eligible": allowed,
            "complete": complete,
            "status": "eligible" if allowed and complete else ("incomplete" if allowed else "ineligible"),
            "checks": [
                {
                    "code": "factory_scope",
                    "label": "厂区隔离",
                    "passed": True,
                    "severity": "hard",
                    "reason": "目标机台属于当前厂区",
                },
                {
                    "code": "capability_completeness",
                    "label": "能力参数完整性",
                    "passed": complete,
                    "severity": "warning",
                    "reason": (
                        "能力参数完整"
                        if complete
                        else "能力参数不完整，确认前需人工复核"
                    ),
                },
            ],
        },
        "reasons": reasons or ["硬约束校验通过"],
        "affected_task_count": 1,
    }


def save_draft(
    db: Session,
    *,
    factory_id: str,
    revision: int,
    snapshot: dict[str, Any],
    reason: str,
    user: AuthContext,
    request_id: str = "",
) -> tuple[InjectionSchedulingPlan, str, str]:
    plan, current_snapshot = current_plan_snapshot(db, factory_id=factory_id)
    if plan.revision != revision:
        raise HTTPException(status_code=409, detail="草案版本冲突，请刷新后重试")
    if snapshot.get("factoryId") != factory_id:
        raise HTTPException(status_code=422, detail="草案快照厂区不一致")
    if snapshot.get("plan", {}).get("id") != plan.id:
        raise HTTPException(status_code=422, detail="草案计划标识不一致")

    new_revision = revision + 1
    now = _now()
    saved_snapshot = deepcopy(snapshot)
    saved_snapshot["snapshotAt"] = now
    saved_plan_payload = {
        **saved_snapshot.get("plan", {}),
        "id": plan.id,
        "revision": new_revision,
        "status": "draft",
        "label": f"草案 v{new_revision}.0",
    }
    saved_plan_payload.pop("publishedAt", None)
    saved_snapshot["plan"] = saved_plan_payload
    _persist_tasks_from_snapshot(
        db,
        plan=plan,
        snapshot=saved_snapshot,
        revision=new_revision,
        now=now,
    )
    digest = _sha(saved_snapshot)
    db.add(
        InjectionSchedulingPlanRevision(
            id=f"{plan.id}:r{new_revision}",
            plan_id=plan.id,
            factory_id=factory_id,
            revision=new_revision,
            status="draft",
            reason=reason,
            snapshot_json=_json(saved_snapshot),
            snapshot_sha256=digest,
            created_by=user.id,
            created_by_name=_actor_name(user),
            created_at=now,
        )
    )
    plan.revision = new_revision
    plan.status = "draft"
    plan.label = f"草案 v{new_revision}.0"
    plan.updated_by = user.id
    plan.updated_by_name = _actor_name(user)
    plan.updated_at = now
    _add_audit(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        action="draft_save",
        reason=reason,
        user=user,
        old_revision=revision,
        new_revision=new_revision,
        detail={
            "previousSnapshotSha256": _sha(current_snapshot),
            "snapshotSha256": digest,
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(plan)
    return plan, now, digest


def publish_plan(
    db: Session,
    *,
    factory_id: str,
    revision: int,
    reason: str,
    user: AuthContext,
    request_id: str = "",
) -> InjectionSchedulingPublishedSnapshot:
    plan, snapshot = current_plan_snapshot(db, factory_id=factory_id)
    if plan.revision != revision:
        raise HTTPException(status_code=409, detail="草案版本冲突，请刷新后重试")
    now = _now()
    previous = list(
        db.scalars(
            select(InjectionSchedulingPublishedSnapshot).where(
                InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
                InjectionSchedulingPublishedSnapshot.is_current.is_(True),
            )
        ).all()
    )
    for item in previous:
        item.is_current = False
        item.superseded_at = now
    publish_sequence = int(
        db.scalar(
            select(func.count(InjectionSchedulingPublishedSnapshot.id)).where(
                InjectionSchedulingPublishedSnapshot.factory_id == factory_id
            )
        )
        or 0
    ) + 1
    version = f"{business_now().strftime('%Y%m%d')}.{publish_sequence}"
    published_snapshot = deepcopy(snapshot)
    published_snapshot["snapshotAt"] = now
    published_snapshot["plan"] = {
        **published_snapshot.get("plan", {}),
        "status": "published",
        "publishedAt": now,
    }
    digest = _sha(published_snapshot)
    result = InjectionSchedulingPublishedSnapshot(
        id=f"ispublish-{uuid4().hex}",
        plan_id=plan.id,
        factory_id=factory_id,
        version=version,
        plan_revision=plan.revision,
        snapshot_json=_json(published_snapshot),
        snapshot_sha256=digest,
        is_current=True,
        rollback_of_snapshot_id=None,
        published_by=user.id,
        published_by_name=_actor_name(user),
        published_at=now,
    )
    db.add(result)
    previous_published_revision = plan.published_revision
    plan.status = "published"
    plan.published_revision = plan.revision
    plan.updated_by = user.id
    plan.updated_by_name = _actor_name(user)
    plan.updated_at = now
    _add_audit(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        action="publish",
        reason=reason,
        user=user,
        old_revision=previous_published_revision if previous else None,
        new_revision=plan.revision,
        detail={"version": version, "snapshotSha256": digest},
        request_id=request_id,
    )
    db.commit()
    db.refresh(result)
    return result


def current_published_snapshot(
    db: Session,
    *,
    factory_id: str,
) -> tuple[InjectionSchedulingPublishedSnapshot, dict[str, Any]]:
    factory_id = _require_factory(factory_id)
    published = db.scalar(
        select(InjectionSchedulingPublishedSnapshot).where(
            InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
            InjectionSchedulingPublishedSnapshot.is_current.is_(True),
        )
    )
    if published is None:
        raise HTTPException(status_code=404, detail="该厂区尚无已发布排程")
    snapshot = _load_json(published.snapshot_json, {})
    if snapshot.get("factoryId") != factory_id:
        raise HTTPException(status_code=409, detail="已发布快照厂区不一致")
    return published, snapshot


def rollback_plan(
    db: Session,
    *,
    factory_id: str,
    version: str,
    revision: int,
    reason: str,
    user: AuthContext,
    request_id: str = "",
) -> tuple[InjectionSchedulingPlan, dict[str, Any], str]:
    plan, _ = current_plan_snapshot(db, factory_id=factory_id)
    if plan.revision != revision:
        raise HTTPException(status_code=409, detail="草案版本冲突，请刷新后重试")
    source = db.scalar(
        select(InjectionSchedulingPublishedSnapshot).where(
            InjectionSchedulingPublishedSnapshot.factory_id == factory_id,
            InjectionSchedulingPublishedSnapshot.version == version,
        )
    )
    if source is None:
        raise HTTPException(status_code=404, detail="找不到该厂区的发布版本")
    source_snapshot = _load_json(source.snapshot_json, {})
    if source_snapshot.get("factoryId") != factory_id:
        raise HTTPException(status_code=409, detail="回滚源快照厂区不一致")
    new_revision = revision + 1
    now = _now()
    snapshot = deepcopy(source_snapshot)
    snapshot["snapshotAt"] = now
    snapshot["notice"] = f"由发布版本 {version} 回滚生成的新草案；尚未重新发布。"
    rollback_plan_payload = {
        **snapshot.get("plan", {}),
        "id": plan.id,
        "revision": new_revision,
        "status": "draft",
        "label": f"回滚草案 v{new_revision}.0",
    }
    rollback_plan_payload.pop("publishedAt", None)
    snapshot["plan"] = rollback_plan_payload
    _persist_tasks_from_snapshot(
        db,
        plan=plan,
        snapshot=snapshot,
        revision=new_revision,
        now=now,
    )
    digest = _sha(snapshot)
    db.add(
        InjectionSchedulingPlanRevision(
            id=f"{plan.id}:r{new_revision}",
            plan_id=plan.id,
            factory_id=factory_id,
            revision=new_revision,
            status="draft",
            reason=reason,
            snapshot_json=_json(snapshot),
            snapshot_sha256=digest,
            created_by=user.id,
            created_by_name=_actor_name(user),
            created_at=now,
        )
    )
    plan.revision = new_revision
    plan.status = "draft"
    plan.label = f"回滚草案 v{new_revision}.0"
    plan.updated_by = user.id
    plan.updated_by_name = _actor_name(user)
    plan.updated_at = now
    _add_audit(
        db,
        factory_id=factory_id,
        plan_id=plan.id,
        action="rollback",
        reason=reason,
        user=user,
        old_revision=revision,
        new_revision=new_revision,
        detail={
            "sourceVersion": version,
            "sourceSnapshotId": source.id,
            "snapshotSha256": digest,
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(plan)
    return plan, snapshot, now
