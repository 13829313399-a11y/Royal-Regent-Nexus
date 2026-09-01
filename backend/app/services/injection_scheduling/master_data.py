from __future__ import annotations

from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_schedule import (
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleMold,
    InjectionScheduleOrderDemand,
)
from app.services.auth import AuthContext
from app.services.injection_scheduling.audit import write_audit_event
from app.services.injection_scheduling.operations import ensure_factory_settings
from app.services.injection_scheduling.template_contract import (
    INJECTION_FACTORY_IDS,
    SHARED_MOLD_SCOPE_ID,
    SHARED_MOLD_SCOPE_TYPE,
)


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _snapshot(item: object, fields: tuple[str, ...]) -> dict[str, object]:
    return {field: getattr(item, field) for field in fields}


ORDER_FIELDS = (
    "priority",
    "delivery_due_date",
    "material_status",
    "required_machine_a_label",
    "required_machine_a_value",
    "daily_target",
    "remark",
)
MACHINE_FIELDS = (
    "machine_code",
    "position",
    "machine_name",
    "machine_a_label",
    "machine_ounce_capacity",
    "tonnage",
    "is_automatic",
    "is_high_speed",
    "robot_arm_type",
    "supports_core_pull",
    "status",
    "raw_remark",
)
MOLD_FIELDS = (
    "mold_code",
    "product_code",
    "product_name",
    "required_machine_a_label",
    "mold_ounce_requirement",
    "min_machine_ounce",
    "max_machine_ounce",
    "cavity_count",
    "pieces_per_shot",
    "shot_weight_g",
    "recommended_tonnage",
    "required_robot_arm",
    "daily_target",
    "status",
    "remark",
)


def patch_order(
    db: Session,
    *,
    factory_id: str,
    order_id: str,
    version: int,
    reason: str,
    actor: AuthContext,
    **values: object,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleOrderDemand).where(
            InjectionScheduleOrderDemand.id == order_id,
            InjectionScheduleOrderDemand.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="订单不存在")
    if item.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "订单已更新", "latest_version": item.version},
        )
    before = _snapshot(item, ORDER_FIELDS)
    for field in ORDER_FIELDS:
        if field in values and values[field] is not None:
            setattr(item, field, values[field])
    if item.priority not in {"EXPEDITE", "URGENT", "NORMAL"}:
        raise HTTPException(status_code=422, detail="优先级不合法")
    item.data_completeness_status = (
        "COMPLETE"
        if item.required_machine_a_value is not None
        and item.delivery_due_date
        and item.order_shots > 0
        else "BLOCKED"
    )
    item.version += 1
    item.updated_by, item.updated_by_name, item.updated_at = (
        actor.id,
        actor.display_name,
        _now(),
    )
    for line in db.scalars(
        select(InjectionScheduleLine).where(
            InjectionScheduleLine.factory_id == factory_id,
            InjectionScheduleLine.order_demand_id == item.id,
            InjectionScheduleLine.status.notin_(("COMPLETED", "CANCELLED")),
        )
    ).all():
        line.priority = item.priority
        line.system_daily_target = item.daily_target
        if line.manual_daily_target is None:
            line.effective_daily_target = item.daily_target
        line.version += 1
        line.updated_by, line.updated_by_name, line.updated_at = (
            actor.id,
            actor.display_name,
            item.updated_at,
        )
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="ORDER_UPDATED",
        entity_type="ORDER",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        reason=reason,
        before=before,
        after=_snapshot(item, ORDER_FIELDS),
    )
    db.commit()
    return {
        "id": item.id,
        "version": item.version,
        "data_completeness_status": item.data_completeness_status,
        "schedule_revision": settings.schedule_revision,
    }


def create_machine(
    db: Session, *, factory_id: str, actor: AuthContext, **values: object
) -> dict[str, object]:
    code = str(values["machine_code"]).strip()
    if not code:
        raise HTTPException(status_code=422, detail="机号不能为空")
    if db.scalar(
        select(InjectionScheduleMachine.id).where(
            InjectionScheduleMachine.factory_id == factory_id,
            InjectionScheduleMachine.machine_code == code,
        )
    ):
        raise HTTPException(status_code=409, detail="同厂区机号已存在")
    now = _now()
    item = InjectionScheduleMachine(
        id=f"is-machine-{uuid4().hex}",
        factory_id=factory_id,
        created_by=actor.id,
        created_by_name=actor.display_name,
        updated_by=actor.id,
        updated_by_name=actor.display_name,
        created_at=now,
        updated_at=now,
        **{**values, "machine_code": code},
    )
    db.add(item)
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="MACHINE_CREATED",
        entity_type="MACHINE",
        entity_id=item.id,
        entity_version=1,
        actor=actor,
        after=_snapshot(item, MACHINE_FIELDS),
    )
    db.commit()
    return {"id": item.id, "version": item.version, **_snapshot(item, MACHINE_FIELDS)}


def patch_machine(
    db: Session,
    *,
    factory_id: str,
    machine_id: str,
    version: int,
    reason: str,
    actor: AuthContext,
    **values: object,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleMachine).where(
            InjectionScheduleMachine.id == machine_id,
            InjectionScheduleMachine.factory_id == factory_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="机台不存在")
    if item.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "机台已更新", "latest_version": item.version},
        )
    duplicate = db.scalar(
        select(InjectionScheduleMachine.id).where(
            InjectionScheduleMachine.factory_id == factory_id,
            InjectionScheduleMachine.machine_code
            == str(values["machine_code"]).strip(),
            InjectionScheduleMachine.id != machine_id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="同厂区机号已存在")
    before = _snapshot(item, MACHINE_FIELDS)
    for field in MACHINE_FIELDS:
        setattr(item, field, values[field])
    item.machine_code = item.machine_code.strip()
    item.version += 1
    item.updated_by, item.updated_by_name, item.updated_at = (
        actor.id,
        actor.display_name,
        _now(),
    )
    settings = ensure_factory_settings(db, factory_id, actor)
    settings.schedule_revision += 1
    write_audit_event(
        db,
        factory_id=factory_id,
        event_type="MACHINE_UPDATED",
        entity_type="MACHINE",
        entity_id=item.id,
        entity_version=item.version,
        actor=actor,
        reason=reason,
        before=before,
        after=_snapshot(item, MACHINE_FIELDS),
    )
    db.commit()
    return {"id": item.id, "version": item.version, **_snapshot(item, MACHINE_FIELDS)}


def create_mold(
    db: Session, *, factory_id: str, actor: AuthContext, **values: object
) -> dict[str, object]:
    mold_code, product_code = (
        str(values["mold_code"]).strip(),
        str(values["product_code"]).strip(),
    )
    if not mold_code or not product_code:
        raise HTTPException(status_code=422, detail="工模和货号不能为空")
    if db.scalar(
        select(InjectionScheduleMold.id).where(
            InjectionScheduleMold.mold_code == mold_code,
            InjectionScheduleMold.product_code == product_code,
        )
    ):
        raise HTTPException(status_code=409, detail="共享模具库中工模与货号组合已存在")
    now = _now()
    item = InjectionScheduleMold(
        id=f"is-mold-{uuid4().hex}",
        factory_id=SHARED_MOLD_SCOPE_ID,
        scope_type=SHARED_MOLD_SCOPE_TYPE,
        created_by=actor.id,
        created_by_name=actor.display_name,
        updated_by=actor.id,
        updated_by_name=actor.display_name,
        created_at=now,
        updated_at=now,
        **{**values, "mold_code": mold_code, "product_code": product_code},
    )
    db.add(item)
    for shared_factory_id in sorted(INJECTION_FACTORY_IDS):
        settings = ensure_factory_settings(db, shared_factory_id, actor)
        settings.schedule_revision += 1
        write_audit_event(
            db,
            factory_id=shared_factory_id,
            event_type="SHARED_MOLD_CREATED",
            entity_type="SHARED_MOLD",
            entity_id=item.id,
            entity_version=1,
            actor=actor,
            after=_snapshot(item, MOLD_FIELDS),
        )
    db.commit()
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "scope_type": item.scope_type,
        "version": item.version,
        **_snapshot(item, MOLD_FIELDS),
    }


def patch_mold(
    db: Session,
    *,
    factory_id: str,
    mold_id: str,
    version: int,
    reason: str,
    actor: AuthContext,
    **values: object,
) -> dict[str, object]:
    item = db.scalar(
        select(InjectionScheduleMold).where(
            InjectionScheduleMold.id == mold_id,
        )
    )
    if item is None:
        raise HTTPException(status_code=404, detail="模具不存在")
    if item.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "模具已更新", "latest_version": item.version},
        )
    mold_code, product_code = (
        str(values["mold_code"]).strip(),
        str(values["product_code"]).strip(),
    )
    if not mold_code or not product_code:
        raise HTTPException(status_code=422, detail="工模和货号不能为空")
    duplicate = db.scalar(
        select(InjectionScheduleMold.id).where(
            InjectionScheduleMold.mold_code == mold_code,
            InjectionScheduleMold.product_code == product_code,
            InjectionScheduleMold.id != mold_id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="共享模具库中工模与货号组合已存在")
    before = _snapshot(item, MOLD_FIELDS)
    for field in MOLD_FIELDS:
        setattr(item, field, values[field])
    item.mold_code, item.product_code = mold_code, product_code
    item.version += 1
    item.updated_by, item.updated_by_name, item.updated_at = (
        actor.id,
        actor.display_name,
        _now(),
    )
    for shared_factory_id in sorted(INJECTION_FACTORY_IDS):
        settings = ensure_factory_settings(db, shared_factory_id, actor)
        settings.schedule_revision += 1
        write_audit_event(
            db,
            factory_id=shared_factory_id,
            event_type="SHARED_MOLD_UPDATED",
            entity_type="SHARED_MOLD",
            entity_id=item.id,
            entity_version=item.version,
            actor=actor,
            reason=reason,
            before=before,
            after=_snapshot(item, MOLD_FIELDS),
        )
    db.commit()
    return {
        "id": item.id,
        "factory_id": item.factory_id,
        "scope_type": item.scope_type,
        "version": item.version,
        **_snapshot(item, MOLD_FIELDS),
    }
