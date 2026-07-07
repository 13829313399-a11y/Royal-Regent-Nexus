import re
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.molding_sample import (
    MoldingSampleAuditLog,
    MoldingSampleInventoryBatch,
    MoldingSampleInventoryMovement,
    MoldingSampleItem,
    MoldingSampleMaterialPrice,
    MoldingSampleNotification,
    MoldingSampleOrder,
    MoldingSampleProblem,
    MoldingSampleRequisition,
    MoldingSampleSensitiveAuditLog,
    MoldingSampleSetting,
)
from app.schemas.molding_sample import (
    InventoryBatchCreateRequest,
    MaterialPriceIn,
    MoldingSampleCreateRequest,
    MoldingSampleEditRequest,
    MoldingSampleItemIn,
    MoldingSampleNotificationUpdateRequest,
    MoldingSampleProblemCreateRequest,
    MoldingSampleProblemStatusRequest,
    MoldingSampleStatusRequest,
    RequisitionCreateRequest,
    RequisitionStatusRequest,
)
from app.services.auth import AuthContext, ensure_factory_scope, ensure_permission, has_factory_scope

KG_TO_LB = 2.20462
DEFAULT_RATE = 1.08
RATE_KEY = "exchange_rate_rmb_to_hkd"

DEFAULT_PRICES = [
    ("HIPS 425", 5.5, "经理默认价"),
    ("ABS 740", 8.0, "经理默认价"),
    ("PP AV161", 4.3, "经理默认价"),
    ("ABS 757", 8.2, "经理默认价"),
    ("PC 110", 9.6, "经理默认价"),
    ("POM 900P", 10.5, "经理默认价"),
    ("ABS 747", 8.1, "经理默认价"),
    ("ABS 750W", 8.6, "混合料匹配示例"),
]
SENSITIVE_AUDIT_LIST_LIMIT = 200
PRODUCTION_TASK_MODULE = "production_molding_sample_task"
ENGINEERING_MOLDING_SAMPLE_MODULE = "engineering_molding_sample"
PRODUCTION_TARGET_ROLE = "啤机部"
ENGINEERING_TARGET_ROLE = "工程部"
ENGINEERING_SUPERVISOR_TARGET_ROLE = "工程主管"
MANAGER_TARGET_ROLE = "经理"
NOTIFICATION_STATUSES = {"未读", "已读", "已处理"}
PROBLEM_STATUSES = {"待处理", "已解决"}

LOCKED_STATUSES = {"待经理审核", "待生产", "生产中", "已完成"}
ALLOWED_ITEM_PATCH_FIELDS = {
    "receipt_no",
    "collected_weight_kg",
    "actual_weight_kg",
    "actual_amount_hkd",
    "injection_cost",
    "production_machine",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def now_precise_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def round_weight(value: float) -> float:
    return round(value + 1e-9, 3)


def normalize_material_name(value: str) -> str:
    fullwidth_digits = {ord(chr(code)): str(code - 0xFF10) for code in range(0xFF10, 0xFF1A)}
    normalized = value.lower().translate(fullwidth_digits).replace("度", "°")
    normalized = re.sub(r"^\s*\d+\s*#", "", normalized)

    for token in (" ", "\t", "\n", "-", "_", "(", ")", "（", "）"):
        normalized = normalized.replace(token, "")

    return normalized


def seed_molding_sample_defaults(db: Session) -> None:
    if db.scalar(select(MoldingSampleSetting).where(MoldingSampleSetting.key == RATE_KEY)) is None:
        db.add(MoldingSampleSetting(key=RATE_KEY, value=str(DEFAULT_RATE)))

    existing_count = len(db.scalars(select(MoldingSampleMaterialPrice)).all())
    if existing_count == 0:
        for material, unit_price, notes in DEFAULT_PRICES:
            db.add(MoldingSampleMaterialPrice(material=material, unit_price=unit_price, notes=notes))

    db.commit()


def append_sensitive_audit(
    db: Session,
    action: str,
    current_user: AuthContext,
    target_type: str,
    target_name: str,
    detail: str,
) -> None:
    db.add(
        MoldingSampleSensitiveAuditLog(
            action=action,
            actor_user_id=current_user.id,
            actor_name=current_user.display_name,
            actor_role=current_user.primary_role,
            actor_roles=", ".join(current_user.roles),
            factory_scope=", ".join(current_user.factory_scopes),
            target_type=target_type,
            target_name=target_name,
            detail=detail,
            created_at=now_precise_text(),
        )
    )


def list_sensitive_audit_logs(db: Session) -> list[MoldingSampleSensitiveAuditLog]:
    return list(
        db.scalars(
            select(MoldingSampleSensitiveAuditLog)
            .order_by(MoldingSampleSensitiveAuditLog.id.desc())
            .limit(SENSITIVE_AUDIT_LIST_LIMIT)
        ).all()
    )


def get_exchange_rate(db: Session) -> float:
    setting = db.get(MoldingSampleSetting, RATE_KEY)
    if not setting:
        return DEFAULT_RATE

    try:
        parsed = float(setting.value)
    except ValueError:
        return DEFAULT_RATE

    return parsed if parsed > 0 else DEFAULT_RATE


def get_prices(db: Session) -> list[MoldingSampleMaterialPrice]:
    return list(db.scalars(select(MoldingSampleMaterialPrice).order_by(MoldingSampleMaterialPrice.id)).all())


def resolve_material_price(material: str, prices: list[MoldingSampleMaterialPrice]) -> MoldingSampleMaterialPrice | None:
    price_map = {
        normalize_material_name(price.material): price
        for price in prices
        if price.unit_price > 0
    }
    direct = price_map.get(normalize_material_name(material))
    if direct:
        return direct

    mixed_parts: list[tuple[float, str]] = []
    for part in material.replace("＋", "+").split("+"):
        piece = part.strip()
        if "%" not in piece and "％" not in piece:
            continue

        normalized_piece = piece.replace("％", "%")
        ratio_text, material_text = normalized_piece.split("%", 1)
        try:
            mixed_parts.append((float(ratio_text.strip()), material_text.strip()))
        except ValueError:
            continue

    if not mixed_parts:
        return None

    mixed_parts.sort(key=lambda item: item[0], reverse=True)
    return price_map.get(normalize_material_name(mixed_parts[0][1]))


def is_external_order(order: MoldingSampleOrder) -> bool:
    return order.send_to in {"发至湖南", "发至模厂"} or order.workshop == "模厂"


def load_order(db: Session, order_id: str, current_user: AuthContext | None = None) -> MoldingSampleOrder:
    order = db.scalar(
        select(MoldingSampleOrder)
        .where(MoldingSampleOrder.id == order_id)
        .options(
            selectinload(MoldingSampleOrder.items),
            selectinload(MoldingSampleOrder.audit_logs),
            selectinload(MoldingSampleOrder.notifications),
            selectinload(MoldingSampleOrder.problems),
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="啤办单不存在")
    if current_user is not None:
        ensure_factory_scope(db, current_user, order.factory_id)

    return order


def scoped_order_statement(current_user: AuthContext):
    statement = select(MoldingSampleOrder).options(
        selectinload(MoldingSampleOrder.items),
        selectinload(MoldingSampleOrder.audit_logs),
        selectinload(MoldingSampleOrder.notifications),
        selectinload(MoldingSampleOrder.problems),
    )
    if "*" not in current_user.factory_scopes:
        statement = statement.where(MoldingSampleOrder.factory_id.in_(current_user.factory_scopes))
    return statement


def list_orders(db: Session, current_user: AuthContext) -> list[MoldingSampleOrder]:
    ensure_permission(db, current_user, "molding_sample:read")
    return list(
        db.scalars(
            scoped_order_statement(current_user)
            .order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
        ).all()
    )


def append_audit(
    db: Session,
    order: MoldingSampleOrder,
    action: str,
    current_user: AuthContext,
    from_status: str,
    to_status: str,
    reason: str = "",
) -> None:
    db.add(
        MoldingSampleAuditLog(
            id=f"{order.id}-audit-{uuid4().hex[:12]}",
            order_id=order.id,
            action=action,
            actor_user_id=current_user.id,
            actor_name=current_user.display_name,
            actor_role=current_user.primary_role,
            actor_roles=", ".join(current_user.roles),
            factory_scope=", ".join(current_user.factory_scopes),
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            created_at=now_precise_text(),
        )
    )


def append_notification(
    db: Session,
    order: MoldingSampleOrder,
    target_module: str,
    target_role: str,
    event_type: str,
    title: str,
    message: str,
    from_status: str = "",
    to_status: str = "",
    status: str = "未读",
    actor_name: str = "",
) -> MoldingSampleNotification:
    notification = MoldingSampleNotification(
        id=f"{order.id}-notice-{uuid4().hex[:12]}",
        order_id=order.id,
        factory_id=order.factory_id,
        target_module=target_module,
        target_role=target_role,
        event_type=event_type,
        title=title,
        message=message,
        from_status=from_status,
        to_status=to_status,
        status=status,
        actor_name=actor_name,
        created_at=now_precise_text(),
    )
    db.add(notification)
    return notification


def mark_order_notifications_handled(
    db: Session,
    order_id: str,
    target_module: str,
    actor_name: str = "",
) -> None:
    handled_at = now_text()
    notifications = db.scalars(
        select(MoldingSampleNotification)
        .where(MoldingSampleNotification.order_id == order_id)
        .where(MoldingSampleNotification.target_module == target_module)
        .where(MoldingSampleNotification.status != "已处理")
    ).all()

    for notification in notifications:
        notification.status = "已处理"
        notification.actor_name = actor_name or notification.actor_name
        notification.read_at = notification.read_at or handled_at
        notification.handled_at = notification.handled_at or handled_at


def append_supervisor_review_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str = "",
    actor_name: str = "",
) -> None:
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_SUPERVISOR_TARGET_ROLE,
        event_type="待主管审核",
        title="啤办单待主管审核",
        message=f"啤办单 {order.id} 已提交主管审核，请及时处理。",
        from_status=from_status,
        to_status="待审核",
        actor_name=actor_name,
    )


def append_manager_review_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str = "",
    actor_name: str = "",
) -> None:
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=MANAGER_TARGET_ROLE,
        event_type="待经理审核",
        title="啤办单待经理审核",
        message=f"啤办单 {order.id} 已提交经理终审，请及时处理。",
        from_status=from_status,
        to_status="待经理审核",
        actor_name=actor_name,
    )


def append_engineering_rework_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str,
    to_status: str,
    reason: str = "",
    actor_name: str = "",
) -> None:
    reason_text = f" 原因：{reason}" if reason else ""
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_TARGET_ROLE,
        event_type="审核驳回",
        title="啤办单被驳回",
        message=f"啤办单 {order.id} 已被驳回，请工程部修改后重提。{reason_text}",
        from_status=from_status,
        to_status=to_status,
        actor_name=actor_name,
    )


def list_notifications(
    db: Session,
    current_user: AuthContext,
    target_module: str | None = None,
    target_role: str | None = None,
    factory_id: str | None = None,
    order_id: str | None = None,
    status: str | None = None,
) -> list[MoldingSampleNotification]:
    ensure_permission(db, current_user, "molding_sample:notification_read")
    statement = select(MoldingSampleNotification)
    if "*" not in current_user.factory_scopes:
        statement = statement.where(MoldingSampleNotification.factory_id.in_(current_user.factory_scopes))
    if target_module:
        statement = statement.where(MoldingSampleNotification.target_module == target_module)
    elif "molding_sample:production_read" not in current_user.permissions and "*" not in current_user.factory_scopes:
        statement = statement.where(MoldingSampleNotification.target_module != PRODUCTION_TASK_MODULE)
    if target_role:
        statement = statement.where(MoldingSampleNotification.target_role == target_role)
    if factory_id:
        ensure_factory_scope(db, current_user, factory_id)
        statement = statement.where(MoldingSampleNotification.factory_id == factory_id)
    if order_id:
        statement = statement.where(MoldingSampleNotification.order_id == order_id)
    if status:
        statement = statement.where(MoldingSampleNotification.status == status)

    return list(
        db.scalars(
            statement.order_by(MoldingSampleNotification.created_at.desc(), MoldingSampleNotification.id.desc())
        ).all()
    )


def update_notification(
    db: Session,
    notification_id: str,
    payload: MoldingSampleNotificationUpdateRequest,
    current_user: AuthContext,
) -> MoldingSampleNotification:
    ensure_permission(db, current_user, "molding_sample:notification_read")
    notification = db.get(MoldingSampleNotification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="啤办通知不存在")
    ensure_factory_scope(db, current_user, notification.factory_id)
    if payload.status not in NOTIFICATION_STATUSES:
        raise HTTPException(status_code=400, detail="通知状态无效")

    timestamp = now_text()
    notification.status = payload.status
    notification.actor_name = current_user.display_name
    if payload.status in {"已读", "已处理"}:
        notification.read_at = notification.read_at or timestamp
    if payload.status == "已处理":
        notification.handled_at = notification.handled_at or timestamp

    db.commit()
    db.refresh(notification)
    return notification


def list_problems(
    db: Session,
    current_user: AuthContext,
    order_id: str | None = None,
    status: str | None = None,
) -> list[MoldingSampleProblem]:
    ensure_permission(db, current_user, "molding_sample:read")
    statement = select(MoldingSampleProblem)

    if "*" not in current_user.factory_scopes:
        statement = statement.where(MoldingSampleProblem.factory_id.in_(current_user.factory_scopes))
    if order_id:
        order = load_order(db, order_id, current_user)
        statement = statement.where(MoldingSampleProblem.order_id == order.id)
    if status:
        statement = statement.where(MoldingSampleProblem.status == status)

    return list(
        db.scalars(
            statement.order_by(MoldingSampleProblem.created_at.desc(), MoldingSampleProblem.id.desc())
        ).all()
    )


def create_problem(
    db: Session,
    payload: MoldingSampleProblemCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleProblem:
    ensure_permission(db, current_user, "molding_sample:production_fillback")
    order = load_order(db, payload.order_id, current_user)
    if order.status not in {"待生产", "生产中"}:
        raise HTTPException(status_code=403, detail="只有待生产或生产中的啤办单可以反馈生产问题")

    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="问题反馈不能为空")

    reported_by = payload.reported_by.strip() or current_user.display_name
    problem = MoldingSampleProblem(
        id=f"{order.id}-problem-{uuid4().hex[:12]}",
        factory_id=order.factory_id,
        order_type="injection",
        order_id=order.id,
        order_number=order.order_number,
        description=description,
        reported_by=reported_by,
        status="待处理",
        created_at=now_precise_text(),
    )
    db.add(problem)
    append_audit(
        db,
        order,
        "生产问题反馈",
        current_user,
        order.status,
        order.status,
        description,
    )
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_TARGET_ROLE,
        event_type="生产问题反馈",
        title="啤机部反馈生产问题",
        message=f"啤办单 {order.id} 反馈问题：{description}",
        from_status=order.status,
        to_status=order.status,
        actor_name=reported_by,
    )
    db.commit()
    db.refresh(problem)
    return problem


def update_problem_status(
    db: Session,
    problem_id: str,
    payload: MoldingSampleProblemStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleProblem:
    ensure_permission(db, current_user, "molding_sample:edit_draft")
    if payload.status not in PROBLEM_STATUSES:
        raise HTTPException(status_code=400, detail="问题状态无效")

    problem = db.get(MoldingSampleProblem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="问题反馈不存在")

    ensure_factory_scope(db, current_user, problem.factory_id)
    problem.status = payload.status
    problem.resolved_at = now_text() if payload.status == "已解决" else ""

    order = load_order(db, problem.order_id, current_user)
    append_audit(
        db,
        order,
        "生产问题处理",
        current_user,
        order.status,
        order.status,
        f"{problem.description} -> {payload.status}",
    )
    db.commit()
    db.refresh(problem)
    return problem


def create_order(db: Session, payload: MoldingSampleCreateRequest, current_user: AuthContext) -> MoldingSampleOrder:
    ensure_permission(db, current_user, "molding_sample:create")
    ensure_factory_scope(db, current_user, payload.order.factory_id)
    if db.get(MoldingSampleOrder, payload.order.id):
        raise HTTPException(status_code=409, detail="啤办单编号已存在")

    status = payload.order.status or "待审核"
    order = MoldingSampleOrder(
        **payload.order.model_dump(exclude={"status", "created_at", "updated_at"}),
        status=status,
        created_at=payload.order.created_at or now_text(),
        updated_at=payload.order.updated_at or now_text(),
    )
    db.add(order)

    for index, item_payload in enumerate(payload.items, start=1):
        item_data = item_payload.model_dump(exclude={"order_id", "sort_order"})
        db.add(
            MoldingSampleItem(
                **item_data,
                order_id=order.id,
                sort_order=item_payload.sort_order or index,
            )
        )

    append_audit(db, order, "工程提交主管审核", current_user, status, status, "工程开单完成。")
    if status == "待审核":
        append_supervisor_review_notification(db, order, from_status=status, actor_name=current_user.display_name)
    db.commit()
    db.refresh(order)
    return load_order(db, order.id, current_user)


def ensure_order_write_allowed(
    db: Session,
    order: MoldingSampleOrder,
    current_user: AuthContext,
    permission: str,
) -> None:
    ensure_factory_scope(db, current_user, order.factory_id)
    if order.status not in LOCKED_STATUSES:
        ensure_permission(db, current_user, permission)
        return

    if "molding_sample:manager_review" in current_user.permissions:
        return

    raise HTTPException(status_code=403, detail="当前状态不允许改删")


def ensure_order_delete_allowed(db: Session, order: MoldingSampleOrder, current_user: AuthContext) -> None:
    ensure_factory_scope(db, current_user, order.factory_id)
    if order.status in LOCKED_STATUSES:
        ensure_permission(db, current_user, "system:user_manage")
        return

    ensure_permission(db, current_user, "molding_sample:delete_draft")


def update_order(db: Session, order_id: str, payload: MoldingSampleEditRequest, current_user: AuthContext) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    if payload.order.id != order_id:
        raise HTTPException(status_code=400, detail="啤办单 ID 不一致")

    ensure_order_write_allowed(db, order, current_user, "molding_sample:edit_draft")
    current_status = order.status
    current_created_at = order.created_at

    order_data = payload.order.model_dump(exclude={"id", "status", "created_at", "updated_at"})
    for field, value in order_data.items():
        setattr(order, field, value)

    order.status = current_status
    order.created_at = current_created_at
    order.updated_at = now_text()

    for existing_item in list(order.items):
        db.delete(existing_item)
    db.flush()

    for index, item_payload in enumerate(payload.items, start=1):
        item_data = item_payload.model_dump(exclude={"order_id", "sort_order"})
        db.add(
            MoldingSampleItem(
                **item_data,
                order_id=order.id,
                sort_order=item_payload.sort_order or index,
            )
        )

    append_audit(
        db,
        order,
        "修改啤办单",
        current_user,
        current_status,
        current_status,
        "单头或明细已更新。",
    )
    db.commit()
    db.expire_all()
    return load_order(db, order_id, current_user)


def delete_order(
    db: Session,
    order_id: str,
    current_user: AuthContext,
) -> None:
    order = load_order(db, order_id, current_user)
    ensure_order_delete_allowed(db, order, current_user)
    db.delete(order)
    db.commit()


def list_inventory_batches(db: Session, material: str | None = None) -> list[MoldingSampleInventoryBatch]:
    statement = select(MoldingSampleInventoryBatch).order_by(
        MoldingSampleInventoryBatch.material,
        MoldingSampleInventoryBatch.batch_no,
    )
    if material:
        statement = statement.where(MoldingSampleInventoryBatch.material == material.strip())

    return list(db.scalars(statement).all())


def create_inventory_batch(
    db: Session,
    payload: InventoryBatchCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleInventoryBatch:
    ensure_permission(db, current_user, "molding_sample:inventory_issue")
    if payload.initial_weight_kg <= 0:
        raise HTTPException(status_code=400, detail="批次初始重量必须大于 0")

    material = payload.material.strip()
    batch_no = payload.batch_no.strip()
    existing_batch = db.scalar(
        select(MoldingSampleInventoryBatch).where(
            MoldingSampleInventoryBatch.material == material,
            MoldingSampleInventoryBatch.batch_no == batch_no,
        )
    )
    if existing_batch:
        raise HTTPException(status_code=409, detail="库存批次已存在")

    now = now_text()
    batch = MoldingSampleInventoryBatch(
        id=f"batch-{uuid4().hex}",
        material=material,
        batch_no=batch_no,
        location=payload.location.strip(),
        initial_weight_kg=round_weight(payload.initial_weight_kg),
        available_weight_kg=round_weight(payload.initial_weight_kg),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    append_inventory_movement(
        db,
        batch=batch,
        movement_type="新增批次",
        quantity_kg=batch.initial_weight_kg,
        before_weight_kg=0,
        after_weight_kg=batch.available_weight_kg,
        actor_name=current_user.display_name,
        reason="新增库存批次。",
    )
    db.commit()
    db.refresh(batch)
    return batch


def append_inventory_movement(
    db: Session,
    batch: MoldingSampleInventoryBatch,
    movement_type: str,
    quantity_kg: float,
    before_weight_kg: float,
    after_weight_kg: float,
    requisition: MoldingSampleRequisition | None = None,
    actor_name: str = "仓库",
    reason: str = "",
) -> None:
    db.add(
        MoldingSampleInventoryMovement(
            batch_id=batch.id,
            batch_no=batch.batch_no,
            requisition_id=requisition.id if requisition else "",
            req_number=requisition.req_number if requisition else "",
            material=batch.material,
            movement_type=movement_type,
            quantity_kg=round_weight(quantity_kg),
            before_weight_kg=round_weight(before_weight_kg),
            after_weight_kg=round_weight(after_weight_kg),
            actor_name=actor_name,
            reason=reason,
            created_at=now_precise_text(),
        )
    )


def list_inventory_movements(
    db: Session,
    batch_id: str | None = None,
    material: str | None = None,
    requisition_id: str | None = None,
) -> list[MoldingSampleInventoryMovement]:
    statement = select(MoldingSampleInventoryMovement).order_by(MoldingSampleInventoryMovement.id.desc())
    if batch_id:
        statement = statement.where(MoldingSampleInventoryMovement.batch_id == batch_id)
    if material:
        statement = statement.where(MoldingSampleInventoryMovement.material == material.strip())
    if requisition_id:
        statement = statement.where(MoldingSampleInventoryMovement.requisition_id == requisition_id)

    return list(db.scalars(statement).all())


def next_requisition_number(db: Session, date: str) -> str:
    date_token = date.replace("-", "")
    prefix = f"LL-{date_token}-"
    existing_numbers = db.scalars(
        select(MoldingSampleRequisition.req_number).where(MoldingSampleRequisition.req_number.like(f"{prefix}%"))
    ).all()
    max_sequence = 0

    for req_number in existing_numbers:
        try:
            max_sequence = max(max_sequence, int(req_number.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue

    return f"{prefix}{max_sequence + 1:03d}"


def list_requisitions(db: Session, order_id: str | None = None) -> list[MoldingSampleRequisition]:
    statement = select(MoldingSampleRequisition).order_by(
        MoldingSampleRequisition.date.desc(),
        MoldingSampleRequisition.req_number.desc(),
    )
    if order_id:
        statement = statement.where(MoldingSampleRequisition.order_id == order_id)

    return list(db.scalars(statement).all())


def create_requisition(
    db: Session,
    payload: RequisitionCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleRequisition:
    ensure_permission(db, current_user, "molding_sample:warehouse_requisition")
    if payload.requested_weight_kg <= 0:
        raise HTTPException(status_code=400, detail="申请重量必须大于 0")

    order = load_order(db, payload.order_id, current_user)
    material = payload.material.strip()
    notes = payload.notes.strip()
    if notes:
        existing_requisition = db.scalar(
            select(MoldingSampleRequisition).where(
                MoldingSampleRequisition.order_id == order.id,
                MoldingSampleRequisition.material == material,
                MoldingSampleRequisition.notes == notes,
            )
        )
        if existing_requisition:
            raise HTTPException(status_code=409, detail="该明细已生成领料单")

    requisition = MoldingSampleRequisition(
        id=f"req-{uuid4().hex}",
        req_number=next_requisition_number(db, payload.date),
        date=payload.date,
        order_id=order.id,
        order_number=order.order_number,
        material=material,
        requested_weight_kg=payload.requested_weight_kg,
        applicant=payload.applicant.strip(),
        notes=notes,
        inventory_batch_id="",
        inventory_batch_no="",
        status="待出库",
        issued_at="",
        created_at=now_text(),
        updated_at=now_text(),
    )
    db.add(requisition)
    db.commit()
    db.refresh(requisition)
    return requisition


def update_requisition_status(
    db: Session,
    requisition_id: str,
    payload: RequisitionStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleRequisition:
    ensure_permission(db, current_user, "molding_sample:inventory_issue")
    requisition = db.get(MoldingSampleRequisition, requisition_id)
    if not requisition:
        raise HTTPException(status_code=404, detail="领料单不存在")
    if payload.status not in {"待出库", "已出库"}:
        raise HTTPException(status_code=400, detail="领料单状态无效")

    previous_status = requisition.status
    if payload.status == "已出库" and payload.inventory_batch_id:
        if previous_status == "已出库" and requisition.inventory_batch_id:
            raise HTTPException(status_code=400, detail="领料单已出库")

        batch = db.get(MoldingSampleInventoryBatch, payload.inventory_batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="库存批次不存在")
        if batch.material != requisition.material:
            raise HTTPException(status_code=400, detail="批次原料不匹配")
        if batch.available_weight_kg < requisition.requested_weight_kg:
            raise HTTPException(status_code=400, detail="库存不足")

        before_weight = batch.available_weight_kg
        after_weight = round_weight(before_weight - requisition.requested_weight_kg)
        batch.available_weight_kg = after_weight
        batch.updated_at = now_text()
        requisition.inventory_batch_id = batch.id
        requisition.inventory_batch_no = batch.batch_no
        append_inventory_movement(
            db,
            batch=batch,
            movement_type="出库扣减",
            quantity_kg=-requisition.requested_weight_kg,
            before_weight_kg=before_weight,
            after_weight_kg=after_weight,
            requisition=requisition,
            actor_name=current_user.display_name,
            reason="领料单出库扣减库存。",
        )

    if payload.status == "待出库" and previous_status == "已出库" and requisition.inventory_batch_id:
        batch = db.get(MoldingSampleInventoryBatch, requisition.inventory_batch_id)
        if batch:
            before_weight = batch.available_weight_kg
            after_weight = round_weight(before_weight + requisition.requested_weight_kg)
            batch.available_weight_kg = after_weight
            batch.updated_at = now_text()
            append_inventory_movement(
                db,
                batch=batch,
                movement_type="撤回出库",
                quantity_kg=requisition.requested_weight_kg,
                before_weight_kg=before_weight,
                after_weight_kg=after_weight,
                requisition=requisition,
                actor_name=current_user.display_name,
                reason="领料单状态退回待出库，恢复库存。",
            )
        requisition.inventory_batch_id = ""
        requisition.inventory_batch_no = ""

    requisition.status = payload.status
    requisition.issued_at = payload.issued_at if payload.status == "已出库" else ""
    if payload.status == "已出库" and not requisition.issued_at:
        requisition.issued_at = now_text()
    requisition.updated_at = now_text()
    db.commit()
    db.refresh(requisition)
    return requisition


def delete_requisition(db: Session, requisition_id: str, current_user: AuthContext) -> None:
    ensure_permission(db, current_user, "molding_sample:warehouse_requisition")
    requisition = db.get(MoldingSampleRequisition, requisition_id)
    if not requisition:
        raise HTTPException(status_code=404, detail="领料单不存在")

    if requisition.status == "已出库" and requisition.inventory_batch_id:
        batch = db.get(MoldingSampleInventoryBatch, requisition.inventory_batch_id)
        if batch:
            before_weight = batch.available_weight_kg
            after_weight = round_weight(before_weight + requisition.requested_weight_kg)
            batch.available_weight_kg = after_weight
            batch.updated_at = now_text()
            append_inventory_movement(
                db,
                batch=batch,
                movement_type="删除领料单恢复",
                quantity_kg=requisition.requested_weight_kg,
                before_weight_kg=before_weight,
                after_weight_kg=after_weight,
                requisition=requisition,
                actor_name=current_user.display_name,
                reason="删除已出库领料单，恢复库存。",
            )

    db.delete(requisition)
    db.commit()


def completion_missing_item_ids(order: MoldingSampleOrder) -> list[str]:
    if is_external_order(order):
        return []

    return [
        item.id
        for item in order.items
        if not item.actual_weight_kg or item.actual_weight_kg <= 0
    ]


def is_opening_engineer(order: MoldingSampleOrder, current_user: AuthContext) -> bool:
    def same_text(left: str | None, right: str | None) -> bool:
        return bool(left and right and left.strip() == right.strip())

    if order.eng_name == "" or same_text(order.eng_name, current_user.display_name):
        return True

    submit_actions = ("工程提交", "工程开单")
    submitter_user_ids = {
        audit.actor_user_id
        for audit in order.audit_logs
        if audit.action.startswith(submit_actions) and audit.actor_user_id
    }
    if current_user.id in submitter_user_ids:
        return True

    submitter_names = {
        audit.actor_name.strip()
        for audit in order.audit_logs
        if audit.action.startswith(submit_actions) and audit.actor_name and audit.actor_name.strip()
    }
    if current_user.display_name.strip() in submitter_names:
        return True

    return False


def calculate_item_costs(
    db: Session,
    order: MoldingSampleOrder,
    item: MoldingSampleItem,
    force_material_amount: bool = False,
) -> None:
    prices = get_prices(db)
    rate = get_exchange_rate(db)
    external = is_external_order(order)
    material_weight = item.collected_weight_kg or item.required_material_kg if external else item.actual_weight_kg
    material_price = resolve_material_price(item.material, prices)

    if external:
        item.actual_weight_kg = material_weight

    if material_weight and material_price and (force_material_amount or not item.actual_amount_hkd):
        item.actual_amount_hkd = round_money(material_weight * KG_TO_LB * material_price.unit_price)

    if external:
        item.injection_cost_hkd = None
        item.exchange_rate_at_save = None
    elif item.injection_cost is not None:
        item.injection_cost_hkd = round_money(item.injection_cost * rate)
        item.exchange_rate_at_save = rate


def recalculate_order_costs(db: Session, order: MoldingSampleOrder, force_material_amount: bool = False) -> None:
    for item in order.items:
        calculate_item_costs(db, order, item, force_material_amount=force_material_amount)


def update_order_items(
    db: Session,
    order_id: str,
    items: list[MoldingSampleItemIn],
    current_user: AuthContext,
) -> MoldingSampleOrder:
    ensure_permission(db, current_user, "molding_sample:production_fillback")
    order = load_order(db, order_id, current_user)
    items_by_id = {item.id: item for item in order.items}

    for patch in items:
        item = items_by_id.get(patch.id)
        if not item:
            raise HTTPException(status_code=404, detail=f"明细不存在：{patch.id}")

        patch_data = patch.model_dump(exclude_unset=True)
        invalid_fields = set(patch_data) - ALLOWED_ITEM_PATCH_FIELDS - {"id", "order_id"}
        if invalid_fields:
            raise HTTPException(status_code=400, detail=f"不允许更新字段：{', '.join(sorted(invalid_fields))}")

        for field in ALLOWED_ITEM_PATCH_FIELDS:
            if field in patch_data:
                setattr(item, field, patch_data[field])

        calculate_item_costs(db, order, item, force_material_amount=True)

    order.updated_at = now_text()
    db.commit()
    return load_order(db, order_id, current_user)


def transition_status(
    db: Session,
    order_id: str,
    request: MoldingSampleStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    from_status = order.status
    action = request.action
    next_status: str | None = None

    if action == "主管通过":
        ensure_permission(db, current_user, "molding_sample:supervisor_review")
        if order.status != "待审核":
            raise HTTPException(status_code=403, detail="只有指定主管可以审核待审核单")
        if is_external_order(order):
            next_status = "已完成"
            order.completed_date = request.today or order.date
            recalculate_order_costs(db, order, force_material_amount=True)
        else:
            next_status = "待生产"
    elif action == "主管驳回":
        ensure_permission(db, current_user, "molding_sample:supervisor_review")
        if order.status != "待审核":
            raise HTTPException(status_code=403, detail="只有指定主管可以驳回待审核单")
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "经理通过":
        ensure_permission(db, current_user, "molding_sample:manager_review")
        if order.status != "待经理审核":
            raise HTTPException(status_code=403, detail="只有经理可以终审待经理审核单")
        if is_external_order(order):
            next_status = "已完成"
            order.completed_date = request.today or order.date
            recalculate_order_costs(db, order, force_material_amount=True)
        else:
            next_status = "待生产"
    elif action == "经理驳回":
        ensure_permission(db, current_user, "molding_sample:manager_review")
        if order.status != "待经理审核":
            raise HTTPException(status_code=403, detail="只有经理可以驳回待经理审核单")
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "工程重提":
        ensure_permission(db, current_user, "molding_sample:edit_draft")
        if order.status not in {"已驳回", "已撤回"}:
            raise HTTPException(status_code=403, detail="只有工程部可以重提已驳回或已撤回单")
        next_status = "待审核"
        order.reject_reason = ""
    elif action == "工程撤回":
        ensure_permission(db, current_user, "molding_sample:edit_draft")
        if order.status != "待审核":
            raise HTTPException(status_code=403, detail="只有开单工程师可以撤回待审核单")
        if not is_opening_engineer(order, current_user):
            raise HTTPException(status_code=403, detail="只有开单工程师可以撤回本人提交的待审核单")
        next_status = "已撤回"
    elif action == "开始处理":
        ensure_permission(db, current_user, "molding_sample:production_start")
        if order.status != "待生产":
            raise HTTPException(status_code=403, detail="只有啤机部可以开始处理待生产单")
        next_status = "生产中"
    elif action == "撤回开始生产":
        ensure_permission(db, current_user, "molding_sample:production_start")
        if order.status != "生产中":
            raise HTTPException(status_code=403, detail="只有啤机部可以撤回生产中单")
        next_status = "待生产"
        order.completed_date = ""
    elif action == "标记完成":
        ensure_permission(db, current_user, "molding_sample:production_complete")
        if order.status != "生产中":
            raise HTTPException(status_code=403, detail="只有啤机部可以完成生产中单")

        missing_ids = completion_missing_item_ids(order)
        if missing_ids:
            raise HTTPException(status_code=400, detail=f"actual_weight_kg 缺失：{', '.join(missing_ids[:5])}")

        next_status = "已完成"
        order.completed_date = request.today or order.date
        recalculate_order_costs(db, order, force_material_amount=True)
    elif action == "撤回完成":
        ensure_permission(db, current_user, "molding_sample:production_complete")
        if order.status != "已完成":
            raise HTTPException(status_code=403, detail="只有啤机部可以撤回已完成单")

        next_status = "生产中"
        order.completed_date = ""
    else:
        raise HTTPException(status_code=400, detail="未知状态动作")

    order.status = next_status
    order.updated_at = now_text()
    append_audit(db, order, action, current_user, from_status, next_status, request.reason)
    if action in {"主管通过", "主管驳回", "经理通过", "经理驳回", "工程撤回", "工程重提"}:
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            actor_name=current_user.display_name,
        )

    if action == "工程重提":
        append_supervisor_review_notification(
            db,
            order,
            from_status=from_status,
            actor_name=current_user.display_name,
        )
    elif action in {"主管驳回", "经理驳回"}:
        append_engineering_rework_notification(
            db,
            order,
            from_status=from_status,
            to_status=next_status,
            reason=request.reason,
            actor_name=current_user.display_name,
        )
    elif action in {"主管通过", "经理通过"} and next_status == "待经理审核":
        append_manager_review_notification(
            db,
            order,
            from_status=from_status,
            actor_name=current_user.display_name,
        )
    elif action in {"主管通过", "经理通过"} and next_status == "待生产":
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="待生产",
            title="啤办单已到待生产",
            message=f"啤办单 {order.id} 已审核通过，啤机部可以开始生产执行。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
        )
    elif action == "开始处理":
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=PRODUCTION_TASK_MODULE,
            actor_name=current_user.display_name,
        )
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="生产开始",
            title="啤机部已开始生产",
            message=f"啤办单 {order.id} 已由啤机部开始处理。",
            from_status=from_status,
            to_status=next_status,
            status="已处理",
            actor_name=current_user.display_name,
        )
    elif action == "撤回开始生产":
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="生产开始撤回",
            title="啤办开始生产已撤回",
            message=f"啤机部已撤回啤办单 {order.id} 的开始生产动作，任务回到待生产。",
            from_status=from_status,
            to_status=next_status,
            status="已处理",
            actor_name=current_user.display_name,
        )
    elif action == "标记完成":
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=PRODUCTION_TASK_MODULE,
            actor_name=current_user.display_name,
        )
        append_notification(
            db,
            order,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            target_role=ENGINEERING_TARGET_ROLE,
            event_type="生产完成回传",
            title="啤办生产完成",
            message=f"啤机部已完成啤办单 {order.id}，实际用料和啤办费已回传。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
        )
    elif action == "撤回完成":
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            actor_name=current_user.display_name,
        )
        append_notification(
            db,
            order,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            target_role=ENGINEERING_TARGET_ROLE,
            event_type="生产完成撤回",
            title="啤办完成回传已撤回",
            message=f"啤机部已撤回啤办单 {order.id} 的完成回传，单据回到生产中等待修正后重新完成。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
        )
    db.commit()
    db.expire_all()
    return load_order(db, order_id, current_user)


def replace_material_prices(
    db: Session,
    prices: list[MaterialPriceIn],
    rmb_to_hkd_rate: float,
    current_user: AuthContext,
) -> dict[str, Any]:
    if rmb_to_hkd_rate <= 0:
        raise HTTPException(status_code=400, detail="汇率必须大于 0")
    ensure_permission(db, current_user, "molding_sample:price_update")

    db.query(MoldingSampleMaterialPrice).delete()
    for price in prices:
        if price.unit_price <= 0:
            raise HTTPException(status_code=400, detail=f"{price.material} 原料单价必须大于 0")
        db.add(MoldingSampleMaterialPrice(material=price.material.strip(), unit_price=price.unit_price, notes=price.notes))

    setting = db.get(MoldingSampleSetting, RATE_KEY)
    if setting:
        setting.value = str(rmb_to_hkd_rate)
    else:
        db.add(MoldingSampleSetting(key=RATE_KEY, value=str(rmb_to_hkd_rate)))

    append_sensitive_audit(
        db,
        action="经理更新价格口径",
        current_user=current_user,
        target_type="material_prices",
        target_name="原料价格表",
        detail=f"更新 {len(prices)} 条原料价格，汇率 {rmb_to_hkd_rate}。",
    )
    db.commit()
    return {"prices": get_prices(db), "rmb_to_hkd_rate": get_exchange_rate(db)}


def build_total_cost_summary(order: MoldingSampleOrder) -> dict[str, Any]:
    external = is_external_order(order)
    missing_price_ids: list[str] = []
    missing_injection_ids: list[str] = []
    item_rows: list[dict[str, Any]] = []
    total_material = 0.0
    total_injection = 0.0

    for item in order.items:
        material_cost = item.actual_amount_hkd or 0.0
        injection_cost = 0.0 if external else (item.injection_cost_hkd if item.injection_cost_hkd is not None else item.injection_cost or 0.0)

        if item.actual_weight_kg and item.actual_amount_hkd is None:
            missing_price_ids.append(item.id)
        if not external and item.injection_cost is None and item.injection_cost_hkd is None:
            missing_injection_ids.append(item.id)

        total_material += material_cost
        total_injection += injection_cost
        item_rows.append(
            {
                "item_id": item.id,
                "mold_id": item.mold_id,
                "mold_name": item.mold_name,
                "actual_amount_hkd": item.actual_amount_hkd,
                "injection_cost": item.injection_cost,
                "injection_cost_hkd": item.injection_cost_hkd,
                "total_cost": round_money(material_cost + injection_cost),
            }
        )

    total_material = round_money(total_material)
    total_injection = round_money(0.0 if external else total_injection)

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "doc_number": order.doc_number,
        "product_name": order.product_name,
        "client_name": order.client_name,
        "completed_date": order.completed_date,
        "workshop": order.workshop,
        "send_to": order.send_to,
        "status": order.status,
        "total_material_cost": total_material,
        "total_injection_cost": total_injection,
        "total_cost": round_money(total_material + total_injection),
        "has_missing_price": bool(missing_price_ids),
        "has_missing_injection_cost": bool(missing_injection_ids),
        "item_rows": item_rows,
    }
