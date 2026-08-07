from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil, floor
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import BUSINESS_TIME_ZONE, business_now
from app.models.injection_scheduling import InjectionSchedulingMold
from app.models.injection_scheduling_execution import InjectionSchedulingOrder
from app.models.injection_scheduling_phase5 import InjectionSchedulingSpeedModel
from app.models.injection_scheduling_scheduler import (
    InjectionSchedulingMachineCalendar,
    InjectionSchedulingTransitionRule,
)
from app.services.injection_scheduling import DEFAULT_RULE_CONFIG, current_rule_set
from app.services.injection_scheduling_scheduler.anchor import next_feasible_start
from app.services.injection_scheduling_scheduler.transition import transition_impact

CALCULATION_VERSION = "injection-scheduling-calculation-v2"


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decimal(value: Decimal | float | str | None) -> Decimal:
    return Decimal(str(value or 0))


def _iso(value: datetime) -> str:
    return (
        value.astimezone(BUSINESS_TIME_ZONE)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


@dataclass(frozen=True, slots=True)
class CalculationContext:
    rule_set_id: str
    rule_revision: int
    config: dict[str, Any]
    speed_models: dict[str, dict[str, Any]]


def load_calculation_context(
    db: Session,
    *,
    factory_id: str,
    mold_ids: set[str] | None = None,
) -> CalculationContext:
    rules = current_rule_set(db, factory_id)
    try:
        stored_config = json.loads(rules.config_json or "{}")
    except json.JSONDecodeError:
        stored_config = {}
    transition_rows = list(
        db.scalars(
            select(InjectionSchedulingTransitionRule)
            .where(
                InjectionSchedulingTransitionRule.factory_id == factory_id,
                InjectionSchedulingTransitionRule.active.is_(True),
            )
            .order_by(
                InjectionSchedulingTransitionRule.revision.desc(),
                InjectionSchedulingTransitionRule.id,
            )
        ).all()
    )
    speed_statement = select(InjectionSchedulingSpeedModel).where(
        InjectionSchedulingSpeedModel.factory_id == factory_id,
        InjectionSchedulingSpeedModel.status == "ACTIVE",
    )
    if mold_ids:
        speed_statement = speed_statement.where(
            InjectionSchedulingSpeedModel.mold_id.in_(mold_ids)
        )
    speed_rows = list(db.scalars(speed_statement).all())
    config = {
        **DEFAULT_RULE_CONFIG,
        **stored_config,
        "default_units_per_hour": stored_config.get("default_units_per_hour", 40),
        "mold_change_minutes": stored_config.get("mold_change_minutes", 30),
        "material_change_minutes": stored_config.get(
            "material_change_minutes", 20
        ),
        "color_change_minutes": stored_config.get("color_change_minutes", 10),
        "dark_to_light_minutes": stored_config.get("dark_to_light_minutes", 60),
        "transition_rules": [
            {
                "from_material_group": item.from_material_group,
                "from_color_rank": item.from_color_rank,
                "to_material_group": item.to_material_group,
                "to_color_rank": item.to_color_rank,
                "mold_change_minutes": item.mold_change_minutes,
                "color_change_minutes": item.color_change_minutes,
                "material_change_minutes": item.material_change_minutes,
                "fixture_change_minutes": item.fixture_change_minutes,
                "revision": item.revision,
            }
            for item in transition_rows
        ],
    }
    speed_models = {
        item.mold_id: {
            "status": item.status,
            "units_per_hour": float(item.calibrated_units_per_hour),
            "cycle_seconds": float(item.calibrated_cycle_seconds),
            "units_per_cycle": float(item.units_per_cycle),
            "sample_count": item.sample_count,
            "confidence": float(item.confidence),
            "revision": item.revision,
        }
        for item in speed_rows
    }
    return CalculationContext(
        rule_set_id=rules.id,
        rule_revision=rules.revision,
        config=config,
        speed_models=speed_models,
    )


def quantity_metrics(
    *,
    order_quantity: Decimal | float | str,
    completed_quantity: Decimal | float | str,
    shift_target_quantity: Decimal | float | str,
) -> dict[str, Any]:
    order_quantity_value = max(_decimal(order_quantity), Decimal(0))
    completed = max(_decimal(completed_quantity), Decimal(0))
    outstanding = max(order_quantity_value - completed, Decimal(0))
    overproduction = max(completed - order_quantity_value, Decimal(0))
    completion_rate = (
        float(completed / order_quantity_value) if order_quantity_value > 0 else 0.0
    )
    shift_target = max(_decimal(shift_target_quantity), Decimal(0))
    remaining_shifts = (
        ceil(outstanding / shift_target)
        if outstanding > 0 and shift_target > 0
        else 0
    )
    return {
        "order_quantity": float(order_quantity_value),
        "completed_quantity": float(completed),
        "outstanding_quantity": float(outstanding),
        "overproduction_quantity": float(overproduction),
        "completion_rate": completion_rate,
        "shift_target_quantity": float(shift_target),
        "estimated_remaining_shifts": remaining_shifts,
    }


def project_task_window(
    *,
    order: InjectionSchedulingOrder,
    planned_quantity: Decimal | float | str,
    completed_quantity: Decimal | float | str,
    shift_target_quantity: Decimal | float | str,
    previous_mold: InjectionSchedulingMold | None,
    current_mold: InjectionSchedulingMold | None,
    earliest_start: datetime,
    calendars: list[InjectionSchedulingMachineCalendar],
    context: CalculationContext,
    continuation_anchor: dict[str, Any] | None = None,
    extra_downtime_minutes: int = 0,
) -> dict[str, Any]:
    planned = max(_decimal(planned_quantity), Decimal(0))
    completed = max(_decimal(completed_quantity), Decimal(0))
    outstanding = max(planned - completed, Decimal(0))
    speed_model = context.speed_models.get(order.mold_id or "")
    warnings: list[dict[str, str]] = []
    if speed_model is not None:
        units_per_hour = _decimal(speed_model["units_per_hour"])
        speed_source = "CALIBRATED_SPEED_MODEL"
        speed_revision = int(speed_model["revision"])
    else:
        units_per_hour = _decimal(context.config.get("default_units_per_hour", 40))
        speed_source = "RULE_DEFAULT"
        speed_revision = 0
        warnings.append(
            {
                "code": "SPEED_MODEL_MISSING",
                "message": "缺少 ACTIVE speed model，使用规则默认产速。",
            }
        )
    if units_per_hour <= 0:
        units_per_hour = Decimal(40)
        speed_source = "SAFE_DEFAULT"
        speed_revision = 0
        warnings.append(
            {
                "code": "SPEED_RATE_INVALID",
                "message": "产速配置无效，使用安全默认值 40 件/小时。",
            }
        )
    production_minutes = (
        max(1, ceil(float(outstanding / units_per_hour * Decimal(60))))
        if outstanding > 0
        else 0
    )
    if current_mold is None:
        setup_minutes = 0
        changeover_type = "MOLD_UNKNOWN"
        setup_breakdown = {
            "mold_change_minutes": 0,
            "material_change_minutes": 0,
            "color_change_minutes": 0,
        }
        warnings.append(
            {
                "code": "MOLD_MISSING",
                "message": "订单没有可用模具主数据，无法计算完整 transition。",
            }
        )
    else:
        transition = transition_impact(previous_mold, current_mold, context.config)
        setup_minutes = transition.setup_minutes
        changeover_type = transition.changeover_type
        setup_breakdown = {
            "mold_change_minutes": transition.mold_change_minutes,
            "material_change_minutes": transition.material_change_minutes,
            "color_change_minutes": transition.color_change_minutes,
        }
    shift_target = max(_decimal(shift_target_quantity), Decimal(0))
    if shift_target <= 0 and outstanding > 0:
        warnings.append(
            {
                "code": "SHIFT_TARGET_MISSING",
                "message": "缺少有效班目标，剩余班次不作为权威结果。",
            }
        )
    total_minutes = setup_minutes + production_minutes + max(extra_downtime_minutes, 0)
    duration = timedelta(minutes=max(total_minutes, 1))
    feasible_start = next_feasible_start(earliest_start, duration, calendars)
    calendar_delay_minutes = max(
        0, ceil((feasible_start - earliest_start).total_seconds() / 60)
    )
    estimated_finish = feasible_start + duration
    metrics = quantity_metrics(
        order_quantity=planned,
        completed_quantity=completed,
        shift_target_quantity=shift_target,
    )
    slack_days: int | None = None
    if order.delivery_due_date:
        try:
            due = datetime.fromisoformat(order.delivery_due_date).date()
            due_at = datetime.combine(
                due, datetime.max.time(), tzinfo=BUSINESS_TIME_ZONE
            )
            slack_days = floor((due_at - estimated_finish).total_seconds() / 86400)
        except ValueError:
            warnings.append(
                {
                    "code": "DELIVERY_DUE_DATE_INVALID",
                    "message": "订单交期无效，无法计算交期余量。",
                }
            )
    input_summary = {
        "planned_quantity": float(planned),
        "completed_quantity": float(completed),
        "shift_target_quantity": float(shift_target),
        "mold_id": order.mold_id or "",
        "earliest_start": _iso(earliest_start),
        "calendar_revisions": sorted(
            (item.id, item.revision, item.window_start, item.window_end, item.available)
            for item in calendars
        ),
        "rule_revision": context.rule_revision,
        "speed_model_revision": speed_revision,
        "extra_downtime_minutes": max(extra_downtime_minutes, 0),
    }
    return {
        **metrics,
        "calculation_version": CALCULATION_VERSION,
        "rule_set_id": context.rule_set_id,
        "rule_revision": context.rule_revision,
        "speed_source": speed_source,
        "speed_model_revision": speed_revision,
        "units_per_hour": float(units_per_hour),
        "production_minutes": production_minutes,
        "setup_minutes": setup_minutes,
        "setup_breakdown": setup_breakdown,
        "changeover_type": changeover_type,
        "reported_downtime_minutes": max(extra_downtime_minutes, 0),
        "calendar_delay_minutes": calendar_delay_minutes,
        "estimated_start": _iso(feasible_start),
        "estimated_finish": _iso(estimated_finish),
        "delivery_slack_days": slack_days,
        "continuation_anchor": continuation_anchor or {},
        "warnings": warnings,
        "input_summary": input_summary,
        "input_fingerprint": hashlib.sha256(
            _json(input_summary).encode("utf-8")
        ).hexdigest(),
        "calculated_at": business_now().isoformat(timespec="seconds"),
    }
