from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from math import ceil
from typing import Any

from app.models.injection_scheduling_execution import InjectionSchedulingOrder


@dataclass(frozen=True, slots=True)
class ProductionEstimate:
    outstanding_quantity: Decimal
    planned_quantity: Decimal
    remaining_quantity: Decimal
    units_per_hour: Decimal
    production_minutes: int
    full_order_minutes: int
    capacity_source: str
    source_daily_capacity: Decimal

    @property
    def split_required(self) -> bool:
        return self.remaining_quantity > 0

    def explanation(self) -> dict[str, Any]:
        return {
            "capacity_source": self.capacity_source,
            "source_daily_capacity": float(self.source_daily_capacity),
            "units_per_hour": float(self.units_per_hour),
            "outstanding_quantity": float(self.outstanding_quantity),
            "planned_quantity": float(self.planned_quantity),
            "remaining_quantity": float(self.remaining_quantity),
            "production_minutes": self.production_minutes,
            "full_order_minutes": self.full_order_minutes,
            "split_required": self.split_required,
        }


def _lineage(order: InjectionSchedulingOrder) -> dict[str, Any]:
    try:
        value = json.loads(order.lineage_json or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _positive_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value or 0))
    except (TypeError, ValueError, ArithmeticError):
        return Decimal(0)
    return parsed if parsed > 0 else Decimal(0)


def production_estimate(
    order: InjectionSchedulingOrder,
    objective_config: dict[str, Any],
    *,
    already_allocated_quantity: Decimal = Decimal(0),
    max_production_minutes: int | None = None,
) -> ProductionEstimate:
    outstanding = max(
        Decimal(order.order_quantity)
        - Decimal(order.completed_quantity)
        - max(Decimal(already_allocated_quantity), Decimal(0)),
        Decimal(0),
    )
    lineage = _lineage(order)
    source_daily_capacity = _positive_decimal(
        lineage.get("source_daily_capacity")
    )
    mold_daily_capacity = _positive_decimal(lineage.get("mold_daily_capacity"))
    speed_models = objective_config.get("speed_models", {})
    speed_model = (
        speed_models.get(order.mold_id, {})
        if isinstance(speed_models, dict) and order.mold_id
        else {}
    )
    calibrated_rate = (
        _positive_decimal(speed_model.get("units_per_hour"))
        if isinstance(speed_model, dict) and speed_model.get("status") == "ACTIVE"
        else Decimal(0)
    )
    if source_daily_capacity > 0:
        units_per_hour = source_daily_capacity / Decimal(24)
        capacity_source = "SOURCE_DAILY_CAPACITY"
    elif calibrated_rate > 0:
        units_per_hour = calibrated_rate
        capacity_source = "ACTIVE_SPEED_MODEL"
    elif mold_daily_capacity > 0:
        units_per_hour = mold_daily_capacity / Decimal(24)
        capacity_source = "MOLD_DAILY_CAPACITY"
    else:
        units_per_hour = _positive_decimal(
            objective_config.get("default_units_per_hour", 40)
        ) or Decimal(40)
        capacity_source = "DEFAULT_UNITS_PER_HOUR"
    full_minutes = (
        max(1, ceil(float(outstanding / units_per_hour * Decimal(60))))
        if outstanding > 0
        else 0
    )
    planned_quantity = outstanding
    if (
        outstanding > 0
        and max_production_minutes is not None
        and full_minutes > max_production_minutes
    ):
        window_capacity = (
            units_per_hour * Decimal(max(1, max_production_minutes)) / Decimal(60)
        )
        planned_quantity = min(outstanding, window_capacity).quantize(
            Decimal("0.001"), rounding=ROUND_DOWN
        )
        if planned_quantity <= 0:
            planned_quantity = min(outstanding, Decimal("0.001"))
    production = (
        max(1, ceil(float(planned_quantity / units_per_hour * Decimal(60))))
        if planned_quantity > 0
        else 0
    )
    return ProductionEstimate(
        outstanding_quantity=outstanding,
        planned_quantity=planned_quantity,
        remaining_quantity=max(outstanding - planned_quantity, Decimal(0)),
        units_per_hour=units_per_hour,
        production_minutes=production,
        full_order_minutes=full_minutes,
        capacity_source=capacity_source,
        source_daily_capacity=source_daily_capacity,
    )


def production_minutes(
    order: InjectionSchedulingOrder,
    objective_config: dict[str, Any],
) -> int:
    return production_estimate(order, objective_config).production_minutes


def default_shift_target(order: InjectionSchedulingOrder) -> Decimal:
    outstanding = max(
        Decimal(order.order_quantity) - Decimal(order.completed_quantity),
        Decimal(0),
    )
    lineage = _lineage(order)
    source_daily_capacity = _positive_decimal(lineage.get("source_daily_capacity"))
    target = source_daily_capacity if source_daily_capacity > 0 else Decimal(40)
    return min(outstanding, target)
