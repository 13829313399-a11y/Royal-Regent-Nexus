"""Explicit painting cost allocation; operation totals are never charged twice."""
from decimal import Decimal, InvalidOperation


def split_painting_cost(row: dict, operation_total: Decimal) -> tuple[Decimal, Decimal] | None:
    values = []
    for key, label in (("paint_cost_hkd", "油漆"), ("labor_cost_hkd", "人工")):
        raw = row.get(key)
        if raw is None or raw == "":
            values.append(None)
            continue
        try:
            value = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError(f"{label}必须是有效的非负港币金额") from exc
        if not value.is_finite() or value < 0:
            raise ValueError(f"{label}必须是有效的非负港币金额")
        values.append(value)
    paint, labor = values
    if paint is None and labor is None:
        return None
    if paint is None:
        paint = operation_total - labor
    if labor is None:
        labor = operation_total - paint
    if paint < 0 or labor < 0:
        raise ValueError("油漆或人工不能超过工序总报价")
    if abs(paint + labor - operation_total) > Decimal("0.0001"):
        raise ValueError("油漆与人工合计必须等于工序总报价")
    return paint, labor
