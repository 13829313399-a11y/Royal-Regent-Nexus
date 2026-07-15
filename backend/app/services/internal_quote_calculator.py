from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.schemas.internal_quote import (
    InternalQuoteCostLine,
    InternalQuoteLineCalculationOut,
    InternalQuoteSectionCalculationOut,
    InternalQuoteSectionPayload,
)


FORMULA_VERSION = "department-formulas-v1"
DEFAULT_FX_RMB_HKD = 0.85
DEFAULT_FX_HKD_USD = 7.8

DEFAULT_MATERIAL_PRICES = [
    {"name": "ABS", "model": "750SW", "price_hkd_lb": 8.50},
    {"name": "ABS", "model": "抽粒料", "price_hkd_lb": 4.60},
    {"name": "透明ABS", "model": "TR558/920", "price_hkd_lb": 12.50},
    {"name": "HIPS", "model": "HI425", "price_hkd_lb": 7.80},
    {"name": "GP", "model": "MW-1", "price_hkd_lb": 7.80},
    {"name": "1#PP", "model": "JM350/K8009", "price_hkd_lb": 6.80},
    {"name": "1#PP", "model": "7032 E3", "price_hkd_lb": 6.80},
    {"name": "透明PP", "model": "5090T", "price_hkd_lb": 7.80},
    {"name": "POM", "model": "F3003/M9044", "price_hkd_lb": 16.50},
    {"name": "POM", "model": "PM820/DM220", "price_hkd_lb": 21.50},
    {"name": "PVC", "model": "普通透明", "price_hkd_lb": 9.00},
    {"name": "PVC", "model": "普通本白", "price_hkd_lb": 8.00},
    {"name": "LDPE", "model": "G812", "price_hkd_lb": 7.80},
    {"name": "HDPE", "model": "HMA016", "price_hkd_lb": 8.00},
    {"name": "TPR", "model": "本白橡胶料", "price_hkd_lb": 15.00},
    {"name": "TPR", "model": "透明橡胶料", "price_hkd_lb": 17.00},
    {"name": "K料", "model": "KR-03NW", "price_hkd_lb": 15.00},
    {"name": "PC料", "model": "2605", "price_hkd_lb": 12.50},
]

DEFAULT_MACHINE_PRICES = [
    {"model": "4A-6A", "normal": "80T", "price_hkd_shift": 940},
    {"model": "7A-9A", "normal": "60-80T", "price_hkd_shift": 1050},
    {"model": "10A-12A", "normal": "120T", "price_hkd_shift": 1160},
    {"model": "14A-16A", "normal": "150T", "price_hkd_shift": 1490},
    {"model": "20A", "normal": "200T", "price_hkd_shift": 1920},
    {"model": "24A", "normal": "260T", "price_hkd_shift": 1920},
    {"model": "30A-32A", "normal": "320T", "price_hkd_shift": 2220},
    {"model": "44A", "normal": "490T", "price_hkd_shift": 2500},
    {"model": "46A-49.9A", "normal": "", "price_hkd_shift": 2800},
    {"model": "60A-65A", "normal": "500T", "price_hkd_shift": 3090},
    {"model": "80A", "normal": "", "price_hkd_shift": 3590},
    {"model": "81.3A", "normal": "", "price_hkd_shift": 3600},
    {"model": "105A", "normal": "800T", "price_hkd_shift": 4500},
]


def money(value: Decimal | float | int) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def number(value: Any, default: float = 0) -> float:
    try:
        parsed = float(value)
        return parsed if parsed >= 0 else default
    except (TypeError, ValueError):
        return default


def default_reference_snapshot() -> dict[str, Any]:
    return {
        "version": "rr2-2026-v1",
        "fx": {"rmb_hkd": DEFAULT_FX_RMB_HKD, "hkd_usd": DEFAULT_FX_HKD_USD},
        "material_prices": [dict(row) for row in DEFAULT_MATERIAL_PRICES],
        "machine_prices": [dict(row) for row in DEFAULT_MACHINE_PRICES],
    }


def merge_reference_snapshot(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    defaults = default_reference_snapshot()
    incoming = dict(snapshot or {})
    incoming_fx = incoming.get("fx") if isinstance(incoming.get("fx"), dict) else {}
    incoming["version"] = str(incoming.get("version") or defaults["version"])
    incoming["fx"] = {
        "rmb_hkd": number(incoming_fx.get("rmb_hkd"), DEFAULT_FX_RMB_HKD) or DEFAULT_FX_RMB_HKD,
        "hkd_usd": number(incoming_fx.get("hkd_usd"), DEFAULT_FX_HKD_USD) or DEFAULT_FX_HKD_USD,
    }
    if not isinstance(incoming.get("material_prices"), list) or not incoming["material_prices"]:
        incoming["material_prices"] = defaults["material_prices"]
    if not isinstance(incoming.get("machine_prices"), list) or not incoming["machine_prices"]:
        incoming["machine_prices"] = defaults["machine_prices"]
    return incoming


def _normalized(value: Any) -> str:
    return "".join(str(value or "").upper().split())


def lookup_material_price(fields: dict[str, Any], snapshot: dict[str, Any]) -> float | None:
    material = _normalized(fields.get("material"))
    grade = _normalized(fields.get("material_grade"))
    if not material or not grade:
        return None
    for item in snapshot.get("material_prices", []):
        if _normalized(item.get("name")) == material and _normalized(item.get("model")) == grade:
            return number(item.get("price_hkd_lb"))
    return None


def lookup_machine_price(fields: dict[str, Any], snapshot: dict[str, Any]) -> float | None:
    target = _normalized(fields.get("machine_model")).replace("A", "")
    if not target:
        return None
    try:
        target_number = float(target)
    except ValueError:
        target_number = -1
    for item in snapshot.get("machine_prices", []):
        model = _normalized(item.get("model"))
        plain = model.replace("A", "")
        if "-" in plain:
            start, end = plain.split("-", 1)
            try:
                if float(start) <= target_number <= float(end):
                    return number(item.get("price_hkd_shift"))
            except ValueError:
                pass
        if model == _normalized(fields.get("machine_model")):
            return number(item.get("price_hkd_shift"))
    return None


def _generic_amount(row: InternalQuoteCostLine) -> tuple[float, str]:
    return number(row.quantity) * number(row.unit_price_hkd), "数量 × HKD单价"


def _engineering_amount(row: InternalQuoteCostLine, fx: float) -> tuple[float, str]:
    fields = row.fields
    if fields.get("mode") != "mold":
        return _generic_amount(row)
    amortization = max(number(fields.get("amortization_qty"), 1), 1)
    return number(fields.get("mold_price_rmb")) / amortization / fx, "模具RMB总价 ÷ 摊销数量 ÷ RMB/HKD汇率"


def _molding_amount(
    row: InternalQuoteCostLine,
    snapshot: dict[str, Any],
    warnings: list[str],
) -> tuple[float, str]:
    fields = row.fields
    if not fields:
        return _generic_amount(row)
    material_price = number(fields.get("material_price_hkd_lb"))
    if not material_price:
        material_price = lookup_material_price(fields, snapshot) or 0
        if fields.get("material") and fields.get("material_grade") and not material_price:
            warnings.append(f"{row.item_name or '未命名行'}：参考表未找到匹配料价")
    weight = number(fields.get("weight_g"))
    if fields.get("mode") == "blow":
        amount = (
            weight * material_price / 454
            + number(fields.get("blow_labor_hkd"))
            + number(fields.get("flash_hkd"))
        ) * (number(fields.get("profit_multiplier"), 1) or 1)
        return amount, "(克重 × HK$/Lb ÷ 454 + 吹气人工 + 水口) × 利润倍数"

    loss_pct = number(fields.get("loss_pct"), 3)
    shot_price = number(fields.get("shot_price_hkd"))
    if not shot_price:
        machine_shift = lookup_machine_price(fields, snapshot) or 0
        sets = max(number(fields.get("sets"), 1), 1)
        target = max(number(fields.get("target"), 1), 1)
        shot_price = machine_shift / sets / target if machine_shift else 0
        if fields.get("machine_model") and not machine_shift:
            warnings.append(f"{row.item_name or '未命名行'}：参考表未找到匹配机型价")
    return weight * (1 + loss_pct / 100) * material_price / 454 + shot_price, "克重 × (1+损耗%) × HK$/Lb ÷ 454 + 啤价"


def _sewing_amount(row: InternalQuoteCostLine) -> tuple[float, str]:
    if not row.fields:
        return _generic_amount(row)
    return (
        number(row.fields.get("usage"))
        * number(row.fields.get("material_price_hkd"))
        * (number(row.fields.get("markup"), 1) or 1),
        "用量 × 材料单价 × 加成倍数",
    )


def _assembly_amount(row: InternalQuoteCostLine) -> tuple[float, str]:
    fields = row.fields
    if fields.get("mode") != "process":
        return _generic_amount(row)
    production_qty = max(number(fields.get("production_qty"), 1), 1)
    return (
        number(fields.get("base_rate_hkd"), 310)
        * number(fields.get("people_count"))
        * number(fields.get("team_count"), 1)
        / production_qty,
        "台班基准 × 工序人数 × 组数 ÷ 每组产量",
    )


def calculate_section(
    department: str,
    payload: InternalQuoteSectionPayload,
) -> tuple[InternalQuoteSectionPayload, InternalQuoteSectionCalculationOut]:
    snapshot = merge_reference_snapshot(payload.reference_snapshot)
    fx = snapshot["fx"]
    rmb_hkd = number(fx.get("rmb_hkd"), DEFAULT_FX_RMB_HKD) or DEFAULT_FX_RMB_HKD
    hkd_usd = number(fx.get("hkd_usd"), DEFAULT_FX_HKD_USD) or DEFAULT_FX_HKD_USD
    warnings: list[str] = []
    normalized_rows: list[InternalQuoteCostLine] = []
    breakdown: list[InternalQuoteLineCalculationOut] = []
    raw_subtotal = 0.0

    electronic_specialized = department == "electronic" and (
        any(row.fields for row in payload.rows) or any(number(value) for value in payload.parameters.values())
    )
    for row in payload.rows:
        if department == "engineering" and row.fields:
            amount, formula = _engineering_amount(row, rmb_hkd)
        elif department == "molding":
            amount, formula = _molding_amount(row, snapshot, warnings)
        elif department == "sewing":
            amount, formula = _sewing_amount(row)
        elif department == "assembly" and row.fields:
            amount, formula = _assembly_amount(row)
        elif electronic_specialized:
            amount = number(row.quantity) * number(row.fields.get("unit_price_rmb")) / rmb_hkd
            formula = "数量 × RMB单价 ÷ RMB/HKD汇率"
        else:
            amount, formula = _generic_amount(row)
        rounded_amount = money(amount)
        normalized_rows.append(row.model_copy(update={"amount_hkd": rounded_amount}))
        breakdown.append(InternalQuoteLineCalculationOut(
            line_id=row.id,
            label=row.item_name,
            formula=formula,
            amount_hkd=rounded_amount,
        ))
        raw_subtotal += rounded_amount

    subtotal = raw_subtotal
    loss_amount = 0.0
    if electronic_specialized:
        parameters = payload.parameters
        parts_rmb = raw_subtotal * rmb_hkd
        extras_rmb = sum(number(parameters.get(key)) for key in (
            "bonding_cost_rmb", "smt_cost_rmb", "labor_cost_rmb",
            "test_repair_rmb", "packing_shipping_rmb",
        ))
        profit_price_rmb = (parts_rmb + extras_rmb) * (1 + number(parameters.get("profit_pct")) / 100)
        tax_diff_rmb = number(parameters.get("tax_diff_rmb"))
        subtotal = (profit_price_rmb + tax_diff_rmb * 1.1) / rmb_hkd
    elif all(not row.fields for row in payload.rows):
        loss_amount = subtotal * number(payload.loss_pct) / 100
    elif department == "sewing" and not any("人工" in (row.item_name or "") for row in payload.rows):
        subtotal += number(payload.parameters.get("labor_hkd"))
    elif department == "sales":
        loss_amount = subtotal * number(payload.loss_pct) / 100

    rounded_subtotal = money(subtotal)
    rounded_loss = money(loss_amount)
    total = money(rounded_subtotal + rounded_loss)
    normalized_payload = payload.model_copy(update={
        "rows": normalized_rows,
        "reference_snapshot": snapshot,
    })
    return normalized_payload, InternalQuoteSectionCalculationOut(
        formula_version=FORMULA_VERSION,
        subtotal_hkd=rounded_subtotal,
        loss_amount_hkd=rounded_loss,
        total_hkd=total,
        total_rmb=money(total * rmb_hkd),
        total_usd=money(total / hkd_usd),
        line_breakdown=breakdown,
        warnings=warnings,
        reference_snapshot=snapshot,
    )
