from __future__ import annotations

from decimal import Decimal
from math import ceil
from typing import Any

from app.models.injection_scheduling_execution import InjectionSchedulingOrder


def production_minutes(
    order: InjectionSchedulingOrder,
    objective_config: dict[str, Any],
) -> int:
    outstanding = max(
        Decimal(order.order_quantity) - Decimal(order.completed_quantity),
        Decimal(0),
    )
    speed_models = objective_config.get("speed_models", {})
    speed_model = (
        speed_models.get(order.mold_id, {})
        if isinstance(speed_models, dict) and order.mold_id
        else {}
    )
    calibrated_rate = (
        speed_model.get("units_per_hour")
        if isinstance(speed_model, dict) and speed_model.get("status") == "ACTIVE"
        else None
    )
    units_per_hour = Decimal(
        str(calibrated_rate or objective_config.get("default_units_per_hour", 40))
    )
    if units_per_hour <= 0:
        units_per_hour = Decimal(40)
    return max(1, ceil(float(outstanding / units_per_hour * Decimal(60))))


def default_shift_target(order: InjectionSchedulingOrder) -> Decimal:
    outstanding = max(
        Decimal(order.order_quantity) - Decimal(order.completed_quantity),
        Decimal(0),
    )
    return min(outstanding, Decimal(40))
