from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

ZERO = Decimal("0")
ONE_HUNDRED = Decimal("100")
PERCENT_QUANTUM = Decimal("0.01")
MACHINE_A_PATTERN = re.compile(
    r"(?P<whole>\d+(?:\.\d+)?)\s*A(?:\s*(?P<half>半))?", re.IGNORECASE
)


def as_decimal(
    value: Decimal | int | float | str | None, *, default: Decimal = ZERO
) -> Decimal:
    if value is None or value == "":
        return default
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"无法转换为数值：{value}") from exc


def parse_machine_a_value(label: str | None) -> Decimal | None:
    """Normalize 5A, 2A半 and 50A 400T while retaining the source label elsewhere."""

    normalized = (label or "").strip()
    if not normalized:
        return None
    match = MACHINE_A_PATTERN.search(normalized)
    if not match:
        return None
    result = Decimal(match.group("whole"))
    if match.group("half"):
        result += Decimal("0.5")
    return result


def normalize_ratio(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, str) and value.strip().endswith("%"):
        return as_decimal(value.strip()[:-1]) / ONE_HUNDRED
    ratio = as_decimal(value)
    if ratio > 1 and ratio <= 100:
        return ratio / ONE_HUNDRED
    if ratio < ZERO or ratio > 1:
        raise ValueError("比例必须介于 0 和 1 之间")
    return ratio


def qualified_shots(
    reported_shots: Decimal | int | float | str | None,
    defect_shots: Decimal | int | float | str | None,
) -> Decimal:
    return max(as_decimal(reported_shots) - as_decimal(defect_shots), ZERO)


def progress(
    order_shots: Decimal | int | float | str | None,
    completed_shots: Decimal | int | float | str | None,
) -> tuple[Decimal, Decimal, Decimal]:
    required = max(as_decimal(order_shots), ZERO)
    completed = max(as_decimal(completed_shots), ZERO)
    remaining = max(required - completed, ZERO)
    if required == ZERO:
        percent = ZERO
    else:
        percent = min(
            (completed / required * ONE_HUNDRED).quantize(
                PERCENT_QUANTUM, rounding=ROUND_HALF_UP
            ),
            ONE_HUNDRED,
        )
    return completed, remaining, percent


def estimated_material_kg(
    remaining_shots: Decimal | int | float | str | None,
    net_weight_g: Decimal | int | float | str | None,
    water_ratio: Decimal | int | float | str | None,
) -> Decimal | None:
    if net_weight_g is None or net_weight_g == "":
        return None
    ratio = normalize_ratio(water_ratio) or ZERO
    grams = max(as_decimal(remaining_shots), ZERO) * max(as_decimal(net_weight_g), ZERO)
    return (grams * (Decimal("1") + ratio) / Decimal("1000")).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )


def effective_changeover_hours(
    suggested_hours: Decimal | int | float | str | None,
    manual_hours: Decimal | int | float | str | None,
) -> Decimal:
    if manual_hours is not None and manual_hours != "":
        return max(as_decimal(manual_hours), ZERO)
    return max(as_decimal(suggested_hours), ZERO)
