"""Shared demand calculation for entry, revisions and split previews."""
import json
from decimal import Decimal, ROUND_CEILING
from fastapi import HTTPException
from app.schemas.carton_quantity import PaperQuantityRule


def field(line, key, default=None):
    return line.get(key, default) if isinstance(line, dict) else getattr(line, key, default)


def rule(line):
    value = field(line, "quantity_rule")
    if value is None:
        return None
    return value if isinstance(value, PaperQuantityRule) else PaperQuantityRule.model_validate(value)


def rule_data(line, *, reusable=False):
    value = rule(line)
    if value is None:
        return None
    data = value.model_dump(mode="json")
    if reusable:
        data["manual_quantity"] = None
    return data


def rule_json(line):
    data = rule_data(line)
    return json.dumps(data, sort_keys=True, separators=(",", ":")) if data else None


def requirements(products, lines, *, manual_targets=None):
    """References are one-based paper positions, never guessed from paper names.

    Manual targets are used only for explicitly allocated split quantities.
    """
    rules = [rule(line) for line in lines]
    result = [None] * len(lines)
    products = Decimal(str(products or 0))
    for index, (line, value) in enumerate(zip(lines, rules)):
        if value and value.mode == "PER_CARTON":
            parent = value.carton_line_no - 1
            if parent == index or parent >= len(lines) or (rules[parent] and rules[parent].mode != "PACKING"):
                raise HTTPException(422, f"第 {index + 1} 条纸品须关联本订单中按装箱数计算的纸箱，不能关联自身或其他配卡")
            continue
        packing = field(line, "usage_quantity")
        if packing is None or Decimal(str(packing)) <= 0:
            raise HTTPException(422, f"第 {index + 1} 条纸品须填写每箱装产品数")
        result[index] = (products / Decimal(str(packing))).to_integral_value(rounding=ROUND_CEILING)
        if value and value.manual_quantity is not None:
            result[index] = Decimal(str((manual_targets or {}).get(index + 1, value.manual_quantity)))
    for index, value in enumerate(rules):
        if value and value.mode == "PER_CARTON":
            result[index] = (result[value.carton_line_no - 1] * value.per_carton_quantity).to_integral_value(rounding=ROUND_CEILING)
            if value.manual_quantity is not None:
                result[index] = Decimal(str((manual_targets or {}).get(index + 1, value.manual_quantity)))
    if any(value < 0 or value >= Decimal("100000000000000") for value in result):
        raise HTTPException(422, "纸品需求数量超出允许范围")
    return result
