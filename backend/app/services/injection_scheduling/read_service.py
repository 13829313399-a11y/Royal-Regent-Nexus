from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.time import business_today
from app.models.injection_schedule import (
    InjectionScheduleFactorySettings,
    InjectionScheduleLine,
    InjectionScheduleMachine,
    InjectionScheduleMold,
    InjectionScheduleOrderDemand,
    InjectionScheduleShiftOutput,
)
from app.services.injection_scheduling.calculations import progress
from app.services.injection_scheduling.template_contract import (
    FACTORY_NAMES,
    INJECTION_FACTORY_IDS,
)

INJECTION_SCHEDULING_DEPARTMENTS = ("production", "molding")
SUPPORTED_IMPORT_PROFILES = (
    "UNIFIED_PLAN_V2",
    "WAREHOUSE_ORDER_FLAT_V1",
    "PRODUCTION_ORDER_FORM_V1",
    "HK_B_PLAN_V1",
    "HUA_XING_PLAN_V1",
)
ACTIVE_ORDER_STATUSES = ("PENDING", "SCHEDULED", "IN_PRODUCTION")


def require_factory(factory_id: str) -> str:
    normalized = factory_id.strip().lower()
    if normalized not in INJECTION_FACTORY_IDS:
        raise HTTPException(status_code=422, detail="当前厂区没有注塑部")
    return normalized


def _default_settings(factory_id: str) -> dict[str, object]:
    return {
        "factory_id": factory_id,
        "factory_name": FACTORY_NAMES.get(factory_id, factory_id),
        "timezone": "Asia/Shanghai",
        "business_date": business_today(),
        "current_shift": "DAY",
        "day_shift_start": "08:00",
        "day_shift_end": "20:00",
        "night_shift_start": "20:00",
        "night_shift_end": "08:00",
        "warehouse_buffer_days": 3,
        "fallback_water_ratio": Decimal("0.01"),
        "auto_schedule_mode": "PREVIEW_CONFIRM",
        "ai_enabled": False,
        "template_family": "unified_injection_schedule",
        "template_version": "2.0",
        "schedule_revision": 1,
        "schedule_horizon_days": 14,
        "freeze_hours": 12,
        "effective_hours_per_day": Decimal("24"),
    }


def get_settings(
    db: Session, factory_id: str
) -> InjectionScheduleFactorySettings | dict[str, object]:
    settings = db.scalar(
        select(InjectionScheduleFactorySettings).where(
            InjectionScheduleFactorySettings.factory_id == factory_id
        )
    )
    return settings or _default_settings(factory_id)


def default_board_range(
    settings: InjectionScheduleFactorySettings | dict[str, object],
) -> tuple[str, str]:
    if isinstance(settings, dict):
        business_date = settings.get("business_date")
        horizon = settings.get("schedule_horizon_days", 14)
    else:
        business_date = settings.business_date
        horizon = settings.schedule_horizon_days
    try:
        start = date.fromisoformat(str(business_date))
    except ValueError:
        start = date.fromisoformat(business_today())
    end = start + timedelta(days=int(horizon) - 1)
    return start.isoformat(), end.isoformat()


def _qualified_by_order_subquery():
    return (
        select(
            InjectionScheduleLine.order_demand_id.label("order_demand_id"),
            func.coalesce(
                func.sum(InjectionScheduleShiftOutput.qualified_shots), 0
            ).label("qualified_shots"),
        )
        .outerjoin(
            InjectionScheduleShiftOutput,
            and_(
                InjectionScheduleShiftOutput.schedule_line_id
                == InjectionScheduleLine.id,
                InjectionScheduleShiftOutput.factory_id
                == InjectionScheduleLine.factory_id,
            ),
        )
        .group_by(InjectionScheduleLine.order_demand_id)
        .subquery()
    )


def _order_out(
    order: InjectionScheduleOrderDemand, completed: Decimal | int | None
) -> dict[str, object]:
    qualified, remaining, completion_percent = progress(order.order_shots, completed)
    return {
        "id": order.id,
        "factory_id": order.factory_id,
        "order_no": order.order_no,
        "product_code": order.product_code,
        "product_name": order.product_name,
        "mold_code": order.mold_code,
        "quantity_sets": order.quantity_sets,
        "total_sets": order.total_sets,
        "order_shots": order.order_shots,
        "qualified_shots": qualified,
        "remaining_shots": remaining,
        "completion_percent": completion_percent,
        "priority": order.priority,
        "status": order.status,
        "delivery_due_date": order.delivery_due_date,
        "warehouse": order.warehouse,
        "color": order.color,
        "pigment_code": order.pigment_code,
        "material_name": order.material_name,
        "material_status": order.material_status,
        "required_machine_a_label": order.required_machine_a_label,
        "required_machine_a_value": order.required_machine_a_value,
        "daily_target": order.daily_target,
        "material_weight_kg": order.material_weight_kg,
        "data_completeness_status": order.data_completeness_status,
        "remark": order.remark,
        "version": order.version,
    }


def list_orders(
    db: Session,
    factory_id: str,
    *,
    search: str = "",
    status: str = "",
    priority: str = "",
) -> list[dict[str, object]]:
    output = _qualified_by_order_subquery()
    statement = (
        select(InjectionScheduleOrderDemand, output.c.qualified_shots)
        .outerjoin(output, output.c.order_demand_id == InjectionScheduleOrderDemand.id)
        .where(InjectionScheduleOrderDemand.factory_id == factory_id)
        .order_by(
            InjectionScheduleOrderDemand.delivery_due_date,
            InjectionScheduleOrderDemand.priority,
            InjectionScheduleOrderDemand.order_no,
        )
    )
    normalized_search = search.strip()
    if normalized_search:
        pattern = f"%{normalized_search}%"
        statement = statement.where(
            or_(
                InjectionScheduleOrderDemand.order_no.ilike(pattern),
                InjectionScheduleOrderDemand.product_code.ilike(pattern),
                InjectionScheduleOrderDemand.product_name.ilike(pattern),
                InjectionScheduleOrderDemand.mold_code.ilike(pattern),
            )
        )
    if status:
        statement = statement.where(InjectionScheduleOrderDemand.status == status)
    if priority:
        statement = statement.where(InjectionScheduleOrderDemand.priority == priority)
    return [
        _order_out(order, completed) for order, completed in db.execute(statement).all()
    ]


def list_machines(
    db: Session, factory_id: str, *, include_disabled: bool = False
) -> list[dict[str, object]]:
    statement = (
        select(InjectionScheduleMachine)
        .where(InjectionScheduleMachine.factory_id == factory_id)
        .order_by(
            InjectionScheduleMachine.display_order,
            InjectionScheduleMachine.machine_code,
        )
    )
    if not include_disabled:
        statement = statement.where(InjectionScheduleMachine.status != "DISABLED")
    return [
        {
            "id": item.id,
            "factory_id": item.factory_id,
            "machine_code": item.machine_code,
            "position": item.position,
            "machine_name": item.machine_name,
            "machine_a_label": item.machine_a_label,
            "machine_ounce_capacity": item.machine_ounce_capacity,
            "tonnage": item.tonnage,
            "is_automatic": item.is_automatic,
            "is_high_speed": item.is_high_speed,
            "robot_arm_type": item.robot_arm_type,
            "supports_core_pull": item.supports_core_pull,
            "status": item.status,
            "available_from": item.available_from,
            "raw_remark": item.raw_remark,
            "version": item.version,
        }
        for item in db.scalars(statement).all()
    ]


def list_molds(
    db: Session, factory_id: str, *, include_disabled: bool = False
) -> list[dict[str, object]]:
    statement = select(InjectionScheduleMold).order_by(
        InjectionScheduleMold.mold_code, InjectionScheduleMold.product_code
    )
    if not include_disabled:
        statement = statement.where(InjectionScheduleMold.status != "DISABLED")
    return [
        {
            "id": item.id,
            "factory_id": item.factory_id,
            "scope_type": item.scope_type,
            "mold_code": item.mold_code,
            "product_code": item.product_code,
            "product_name": item.product_name,
            "required_machine_a_label": item.required_machine_a_label,
            "mold_ounce_requirement": item.mold_ounce_requirement,
            "min_machine_ounce": item.min_machine_ounce,
            "max_machine_ounce": item.max_machine_ounce,
            "cavity_count": item.cavity_count,
            "pieces_per_shot": item.pieces_per_shot,
            "shot_weight_g": item.shot_weight_g,
            "recommended_tonnage": item.recommended_tonnage,
            "required_robot_arm": item.required_robot_arm,
            "status": item.status,
            "daily_target": item.daily_target,
            "remark": item.remark,
            "version": item.version,
        }
        for item in db.scalars(statement).all()
    ]


def board_lines(
    db: Session, factory_id: str, start_date: str, end_date: str
) -> list[dict[str, object]]:
    output = _qualified_by_order_subquery()
    statement = (
        select(
            InjectionScheduleLine,
            InjectionScheduleOrderDemand,
            InjectionScheduleMachine.machine_code,
            InjectionScheduleMold.mold_code,
            output.c.qualified_shots,
        )
        .join(
            InjectionScheduleOrderDemand,
            and_(
                InjectionScheduleOrderDemand.id
                == InjectionScheduleLine.order_demand_id,
                InjectionScheduleOrderDemand.factory_id
                == InjectionScheduleLine.factory_id,
            ),
        )
        .outerjoin(
            InjectionScheduleMachine,
            and_(
                InjectionScheduleMachine.id == InjectionScheduleLine.machine_id,
                InjectionScheduleMachine.factory_id == InjectionScheduleLine.factory_id,
            ),
        )
        .outerjoin(
            InjectionScheduleMold,
            InjectionScheduleMold.id == InjectionScheduleLine.mold_id,
        )
        .outerjoin(output, output.c.order_demand_id == InjectionScheduleOrderDemand.id)
        .where(
            InjectionScheduleLine.factory_id == factory_id,
            InjectionScheduleLine.status != "CANCELLED",
            or_(
                InjectionScheduleLine.planned_start_at == "",
                and_(
                    InjectionScheduleLine.planned_start_at < f"{end_date}T23:59:59",
                    InjectionScheduleLine.planned_finish_at >= f"{start_date}T00:00:00",
                ),
            ),
        )
        .order_by(
            InjectionScheduleMachine.display_order,
            InjectionScheduleMachine.machine_code,
            InjectionScheduleLine.sequence_no,
            InjectionScheduleOrderDemand.delivery_due_date,
        )
    )
    items: list[dict[str, object]] = []
    for line, order, machine_code, mold_code, completed in db.execute(statement).all():
        qualified, remaining, completion_percent = progress(
            order.order_shots, completed
        )
        items.append(
            {
                "id": line.id,
                "factory_id": line.factory_id,
                "order_demand_id": line.order_demand_id,
                "machine_id": line.machine_id,
                "machine_code": machine_code or "未排机台",
                "mold_id": line.mold_id,
                "mold_code": mold_code or order.mold_code,
                "order_no": order.order_no,
                "product_code": order.product_code,
                "product_name": order.product_name,
                "color": order.color,
                "material_name": order.material_name,
                "sequence_no": line.sequence_no,
                "status": line.status,
                "is_locked": line.is_locked,
                "priority": line.priority,
                "planned_start_at": line.planned_start_at,
                "planned_finish_at": line.planned_finish_at,
                "qualified_shots": qualified,
                "remaining_shots": remaining,
                "completion_percent": completion_percent,
                "effective_daily_target": line.effective_daily_target,
                "warehouse_date": line.warehouse_date,
                "delivery_gap_days": line.delivery_gap_days,
                "schedule_revision": line.schedule_revision,
                "schedule_source": line.schedule_source,
                "version": line.version,
            }
        )
    return items


def kpis(db: Session, factory_id: str) -> dict[str, int]:
    today = business_today()
    rows = db.execute(
        select(
            InjectionScheduleOrderDemand.status,
            InjectionScheduleOrderDemand.delivery_due_date,
        ).where(
            InjectionScheduleOrderDemand.factory_id == factory_id,
            InjectionScheduleOrderDemand.status.in_(ACTIVE_ORDER_STATUSES),
        )
    ).all()
    active = len(rows)
    scheduled = sum(status in {"SCHEDULED", "IN_PRODUCTION"} for status, _ in rows)
    return {
        "active_order_count": active,
        "scheduled_order_count": scheduled,
        "unscheduled_order_count": active - scheduled,
        "in_production_order_count": sum(
            status == "IN_PRODUCTION" for status, _ in rows
        ),
        "overdue_order_count": sum(bool(due and due < today) for _, due in rows),
    }
