import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.molding_sample import MoldingSampleMaterialPrice


FORMULA_VERSION = "rr2-2026-v1"
FOUR_PLACES = Decimal("0.0001")
ZERO = Decimal("0")

DEFAULT_MATERIAL_PRICES = (
    ("ABS", "750SW", "8.50"),
    ("ABS", "抽粒料", "4.60"),
    ("透明ABS", "TR558/920", "12.50"),
    ("HIPS", "HI425", "7.80"),
    ("GP", "MW-1", "7.80"),
    ("1#PP", "JM350/K8009", "6.80"),
    ("1#PP", "7032 E3", "6.80"),
    ("透明PP", "5090T", "7.80"),
    ("POM", "F3003/M9044", "16.50"),
    ("POM", "PM820/DM220", "21.50"),
    ("PVC", "普通透明", "9.00"),
    ("PVC", "普通本白", "8.00"),
    ("LDPE", "G812", "7.80"),
    ("HDPE", "HMA016", "8.00"),
    ("TPR", "本白橡胶料", "15.00"),
    ("TPR", "透明橡胶料", "17.00"),
    ("K料", "KR-03NW", "15.00"),
    ("PC料", "2605", "12.50"),
)

DEFAULT_MACHINE_PRICES = (
    ("4A-6A", "80T", "940"),
    ("7A-9A", "60-80T", "1050"),
    ("10A-12A", "120T", "1160"),
    ("14A-16A", "150T", "1490"),
    ("18A", "180T", "1890"),
    ("20A", "200T", "1920"),
    ("24A", "260T", "1920"),
    ("30A-32A", "320T", "2220"),
    ("44A", "490T", "2500"),
    ("46A-49.9A", "待维护", "2800"),
    ("60A-65A", "500T", "3090"),
    ("80A", "待维护", "3590"),
    ("81.3A", "待维护", "3600"),
    ("105A", "800T", "4500"),
)

DEFAULT_TAX_RATES = {
    "carton": "0.10",
    "tax_1_percent": "0.0099",
    "slush": "0.03",
    "sewing_hair": "0.115",
    "sewing_clothes": "0.115",
    "blister": "0.06",
    "freight_tax_9": "0.0826",
    "tax_13_percent": "0.115",
}

DEFAULT_FREIGHT = {
    "capacity_cuft": {
        "truck_10t": "1166",
        "truck_5t": "750",
        "container_40": "1980",
        "container_20": "883",
    },
    "cost_hkd": {
        "hk_container_40": "8000",
        "hk_container_20": "7100",
        "yt_container_40": "7200",
        "yt_container_20": "6000",
        "hk_truck_10t": "14900",
        "yt_truck_10t": "11500",
        "hk_truck_5t": "12500",
        "yt_truck_5t": "11000",
    },
}

SECTION_INPUT_CONTRACTS: dict[str, dict[str, Any]] = {
    "sales": {
        "additional_tax_hkd": "decimal>=0",
        "indonesia_freight_hkd": "decimal>=0",
        "tax_categories": [{"code": "tax code", "amount_hkd": "decimal>=0", "rate": "optional decimal"}],
        "scenarios": [{
            "name": "text",
            "capacity_cuft": "decimal>0",
            "freight_cost_hkd": "decimal>=0",
            "carton_cuft": "decimal>0",
            "qty_per_carton": "decimal>0",
            "freight_share": "default 0.48",
            "lift_share": "default 0.52",
            "markup": "default 1.2",
            "settlement": "default 0.98",
        }],
        "customer_quote_fields": {
            "buzzbee": {
                "color_box_tiers": [
                    {"quote_price_hkd": "decimal>0", "fsc_price_hkd": "decimal>0", "moq": "text"},
                ],
            },
            "disney": {
                "item_number": "text",
                "quote_date": "YYYY-MM-DD",
                "revision": "integer>=0",
                "minimum_order_qty": "decimal>0",
                "moq_prices_usd": {"qty_3000": "decimal>0", "qty_5000": "decimal>0", "qty_10000": "decimal>0"},
                "transportation_usd": "decimal>=0",
                "model_cost_usd": "decimal>=0",
                "setup_charge_usd": "decimal>=0",
            },
            "dickie": {
                "client_name": "text",
                "quote_date": "YYYY-MM-DD",
                "attention": "text",
                "revision": "text",
                "from_name": "text",
                "project_name_en": "English text",
                "first_shot_time": "English text",
                "finish_time": "English text",
                "product_rows": [{"line_no": "integer>=0", "item_text_en": "English text", "units_per_carton": "text", "carton_cbm": "decimal>0", "color_box_size_cm": "text", "carton_size_cm": "text", "production_moq": "text", "price_40h_hkd": "decimal>0", "price_20h_hkd": "decimal>0", "price_lcl_hkd": "decimal>0"}],
                "remark_lines": [{"line_no": "integer>=0", "text_en": "English text"}],
                "material_prices_hkd": [{"material": "text", "price_hkd_lb": "decimal>0"}],
            },
            "caixing": {
                "product_type": "plastic|plush",
                "item_number": "text",
                "item_name": "text",
                "quote_date": "YYYY-MM-DD",
                "carton_length_in": "decimal>0",
                "carton_width_in": "decimal>0",
                "carton_height_in": "decimal>0",
                "carton_cuft": "decimal>0",
                "carton_cbm": "decimal>0",
                "pcs_per_carton": "decimal>0",
                "carton_price_hkd": "decimal>0",
                "cost_rows": [{"group": "special|electronic|purchase|packing|carton|fabric|spraying|tampo|assembly|packout|rooting|sewing|special_offer", "tax_tag": "text", "category": "text", "description": "text", "base_cost_hkd": "decimal>=0", "customer_cost_hkd": "decimal>=0"}],
            },
        },
    },
    "engineering": {
        "materials": [{"item": "text", "category": "hardware|auxiliary|packaging", "quantity": "decimal>=0", "unit_price_rmb": "decimal>=0", "disney_description": "text", "disney_section": "product|package", "disney_unit_price_usd": "decimal>=0", "disney_included": "decimal>=0"}],
        "molds": [{"item": "text", "quantity": "decimal>=0", "cost_rmb": "decimal>=0", "disney_mold_no": "text", "disney_parts": "text", "disney_material": "text", "disney_cavities": "decimal>0", "disney_parts_per_shot": "decimal>0", "disney_tool_cost_usd": "decimal>=0", "dickie_project_name_en": "English text", "dickie_mold_no": "text", "dickie_parts_en": "English text", "dickie_resin": "text", "dickie_mold_size": "text", "dickie_mold_material": "text", "dickie_cavities": "decimal>0", "dickie_parts_per_shot": "decimal>0", "dickie_mold_cost_hkd": "decimal>0", "dickie_remark_en": "English text", "caixing_tool_plan_ref": "text", "caixing_mold_cost_hkd": "decimal>=0", "caixing_customer_mold_cost_hkd": "decimal>0"}],
        "amortization_qty": "decimal>0 when mold cost exists",
        "customer_mold_subsidy_usd": "decimal>=0",
        "cartons": [{"length_in": "decimal>0", "width_in": "decimal>0", "height_in": "decimal>0", "qty_per_carton": "decimal>0", "flat_cards": "list", "disney_unit_price_usd": "decimal>=0"}],
    },
    "electronic": {
        "components": [{"item": "text", "quantity": "decimal>=0", "unit_price_hkd": "decimal>=0", "children": "recursive list"}],
        "bonding_hkd": "decimal>=0",
        "smt_hkd": "decimal>=0",
        "labor_hkd": "decimal>=0",
        "testing_hkd": "decimal>=0",
        "packaging_hkd": "decimal>=0",
        "profit_rate_percent": "default 10",
        "tax_credit_difference_hkd": "decimal>=0",
    },
    "molding": {
        "injection_lines": [{"material": "exact text", "grade": "exact text", "net_weight_g": "decimal>=0", "loss_rate_percent": "default 3", "machine_code": "A-code", "sets": "decimal>0", "target_output": "decimal>0", "quantity": "default 1", "disney_mold_no": "text", "disney_resin_cost_usd_kg": "decimal>0", "disney_cycle_time_seconds": "decimal>0", "disney_labor_rate_usd_hr": "decimal>0"}],
        "blow_lines": [{"material": "exact text", "grade": "exact text", "estimated_weight_g": "decimal>=0", "labor_hkd": "decimal>=0", "burr_hkd": "decimal>=0", "profit_multiplier": "default 1.05", "quantity": "default 1"}],
        "caixing_tool_plan_rows": [{"ref_no": "unique text", "process_type": "IN|BL|CP|DC|RC", "tool_no": "text", "tooling_cost_hkd": "decimal>=0", "description": "text", "sku_no": "text", "cavities": "decimal>0", "up": "decimal>0", "net_weight_g": "decimal>0", "material_code": "decimal>0", "material": "text", "color": "text", "material_cost_hkd": "decimal>0", "machine_size": "text", "cycle_time_seconds": "decimal>0", "process_cost_hkd": "decimal>0"}],
    },
    "painting": {"rows": [{"item": "text", "operations": "夹模/移印/散枪/边模/油色/浸油/抹油 quantity and unit_price_hkd"}], "disney_decorations": [{"application_type": "text", "rate_per_op_usd": "decimal>0", "operations": "decimal>0"}]},
    "slush": {"lines": [{"item": "text", "quantity": "decimal>=0", "unit_price_hkd": "decimal>=0"}]},
    "sewing": {"groups": [{"name": "text", "category": "clothes|hair", "materials": "list", "labor_rmb": "decimal>=0"}]},
    "assembly": {"groups": [{"name": "text", "category": "assembly|packaging", "processes": [{"persons": "decimal>=0", "teams": "decimal>=0", "production_qty": "decimal>0"}]}], "labor_base_hkd": "default 310"},
}


class CalculationInputError(ValueError):
    pass


def decimal_value(value: Any, field: str, default: str = "0", *, allow_negative: bool = False) -> Decimal:
    if value in (None, ""):
        value = default
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise CalculationInputError(f"{field} 必须是有效数字") from error
    if not result.is_finite():
        raise CalculationInputError(f"{field} 必须是有限数字")
    if not allow_negative and result < ZERO:
        raise CalculationInputError(f"{field} 不能小于 0")
    return result


def positive_value(value: Any, field: str, default: str = "0") -> Decimal:
    result = decimal_value(value, field, default)
    if result <= ZERO:
        raise CalculationInputError(f"{field} 必须大于 0")
    return result


def amount(value: Decimal) -> Decimal:
    return value.quantize(FOUR_PLACES, rounding=ROUND_HALF_UP)


def decimal_text(value: Decimal) -> str:
    return format(amount(value), "f")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def build_reference_snapshot(db: Session) -> dict[str, Any]:
    legacy_prices = {
        row.material.strip(): decimal_text(Decimal(str(row.unit_price)))
        for row in db.scalars(select(MoldingSampleMaterialPrice).order_by(MoldingSampleMaterialPrice.material)).all()
    }
    return {
        "baseline_version": FORMULA_VERSION,
        "fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8", "rmb_usd": "7.75"},
        "material_prices": {
            f"{material}|{grade}": price
            for material, grade, price in DEFAULT_MATERIAL_PRICES
        },
        "legacy_material_prices": legacy_prices,
        "machine_prices": [
            {"range": machine_range, "machine": machine, "shift_price_hkd": price}
            for machine_range, machine, price in DEFAULT_MACHINE_PRICES
        ],
        "paper_price_factor": "2.75",
        "injection_loss_rate_percent": "3",
        "blow_profit_multiplier": "1.05",
        "electronic_profit_rate_percent": "10",
        "assembly_labor_base_hkd": "310",
        "tax_rates": DEFAULT_TAX_RATES,
        "freight": DEFAULT_FREIGHT,
        "freight_share": "0.48",
        "lift_share": "0.52",
        "markup": "1.2",
        "settlement": "0.98",
    }


def _warning(code: str, message: str, severity: str = "blocking") -> dict[str, str]:
    return {"code": code, "message": message, "severity": severity}


def _material_price(snapshot: dict[str, Any], material: str, grade: str) -> Decimal | None:
    prices = snapshot.get("material_prices", {})
    key = f"{material.strip()}|{grade.strip()}"
    if isinstance(prices, dict) and key in prices:
        return decimal_value(prices[key], key)
    legacy = snapshot.get("legacy_material_prices", {})
    if isinstance(legacy, dict):
        for candidate in (f"{material.strip()} {grade.strip()}".strip(), material.strip(), grade.strip()):
            if candidate and candidate in legacy:
                return decimal_value(legacy[candidate], candidate)
    return None


def _a_code(value: str) -> Decimal | None:
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)A\s*", value, flags=re.IGNORECASE)
    return Decimal(match.group(1)) if match else None


def _machine_price(snapshot: dict[str, Any], machine_code: str) -> Decimal | None:
    code_value = _a_code(machine_code)
    if code_value is None:
        return None
    rows = snapshot.get("machine_prices", [])
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        range_label = str(row.get("range", ""))
        bounds = range_label.split("-", 1)
        lower = _a_code(bounds[0])
        upper = _a_code(bounds[1]) if len(bounds) == 2 else lower
        if lower is not None and upper is not None and lower <= code_value <= upper:
            return decimal_value(row.get("shift_price_hkd"), range_label)
    return None


def _base_result(section_code: str, payload: dict[str, Any], reference_snapshot_id: str) -> dict[str, Any]:
    return {
        "section_code": section_code,
        "formula_version": FORMULA_VERSION,
        "input_hash": content_hash(payload),
        "reference_snapshot_id": reference_snapshot_id,
        "line_breakdown": [],
        "currency_totals": {"HKD": "0.0000", "RMB": "0.0000", "USD": "0.0000"},
        "totals": {},
        "warnings": [],
        "dependencies": {},
    }


def _finish(result: dict[str, Any]) -> dict[str, Any]:
    warnings = result.get("warnings", [])
    result["status"] = "blocked" if any(item.get("severity") == "blocking" for item in warnings) else "valid"
    result["calculation_hash"] = content_hash(
        {key: value for key, value in result.items() if key != "calculation_hash"}
    )
    return result


def _engineering(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
    fx_rmb_usd = positive_value(snapshot.get("fx", {}).get("rmb_usd"), "RMB/USD 汇率")
    category_hkd = {"hardware": ZERO, "auxiliary": ZERO, "packaging": ZERO}
    material_rmb = ZERO
    for index, row in enumerate(payload.get("materials", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"工程材料第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), f"工程材料第 {index + 1} 行数量")
        unit_price = decimal_value(row.get("unit_price_rmb"), f"工程材料第 {index + 1} 行人民币单价")
        line_rmb = quantity * unit_price
        line_hkd = line_rmb / fx
        category = str(row.get("category", "auxiliary"))
        if category not in category_hkd:
            raise CalculationInputError(f"工程材料第 {index + 1} 行分类无效")
        category_hkd[category] += line_hkd
        material_rmb += line_rmb
        result["line_breakdown"].append({
            "kind": "material",
            "item": str(row.get("item", "")),
            "category": category,
            "amount_rmb": decimal_text(line_rmb),
            "amount_hkd": decimal_text(line_hkd),
        })

    mold_total_rmb = ZERO
    for index, row in enumerate(payload.get("molds", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"模具第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), f"模具第 {index + 1} 行数量", "1")
        mold_total_rmb += quantity * decimal_value(row.get("cost_rmb"), f"模具第 {index + 1} 行费用")

    amortization_rmb = ZERO
    amortization_usd = ZERO
    if mold_total_rmb > ZERO:
        amortization_qty = positive_value(payload.get("amortization_qty"), "模具分摊数量")
        subsidy_usd = decimal_value(payload.get("customer_mold_subsidy_usd"), "客户模费补贴")
        amortization_rmb = mold_total_rmb / amortization_qty
        amortization_usd = (mold_total_rmb / fx_rmb_usd - subsidy_usd) / amortization_qty

    paper_factor = positive_value(snapshot.get("paper_price_factor"), "纸价系数", "2.75")
    carton_total_hkd = ZERO
    carton_cuft = ZERO
    for index, row in enumerate(payload.get("cartons", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"纸箱第 {index + 1} 行格式无效")
        length = positive_value(row.get("length_in"), f"纸箱第 {index + 1} 行长度")
        width = positive_value(row.get("width_in"), f"纸箱第 {index + 1} 行宽度")
        height = positive_value(row.get("height_in"), f"纸箱第 {index + 1} 行高度")
        qty_per_carton = positive_value(row.get("qty_per_carton"), f"纸箱第 {index + 1} 行每箱数量")
        carton_price = (length + width + 2) * (width + height + 1) * 2 * paper_factor / 1000
        flat_total = ZERO
        for flat_index, flat in enumerate(row.get("flat_cards", []) or []):
            if not isinstance(flat, dict):
                raise CalculationInputError(f"纸箱第 {index + 1} 行平卡 {flat_index + 1} 格式无效")
            flat_length = positive_value(flat.get("length_in"), "平卡长度")
            flat_width = positive_value(flat.get("width_in"), "平卡宽度")
            flat_qty = decimal_value(flat.get("quantity"), "平卡数量", "1")
            flat_total += (flat_length + 1) * (flat_width + 1) * 2 / 1000 * flat_qty
        per_piece = (carton_price + flat_total) / qty_per_carton
        carton_total_hkd += per_piece
        carton_cuft += length * width * height / 1728
        result["line_breakdown"].append({
            "kind": "carton",
            "item": str(row.get("item", "")),
            "carton_price_hkd": decimal_text(carton_price),
            "flat_card_price_hkd": decimal_text(flat_total),
            "per_piece_hkd": decimal_text(per_piece),
            "cuft": decimal_text(length * width * height / 1728),
        })

    total_hkd = sum(category_hkd.values(), carton_total_hkd)
    result["currency_totals"] = {
        "HKD": decimal_text(total_hkd),
        "RMB": decimal_text(material_rmb + mold_total_rmb),
        "USD": decimal_text(amortization_usd),
    }
    result["totals"] = {
        "hardware_hkd": decimal_text(category_hkd["hardware"]),
        "auxiliary_hkd": decimal_text(category_hkd["auxiliary"]),
        "packaging_hkd": decimal_text(category_hkd["packaging"]),
        "carton_hkd": decimal_text(carton_total_hkd),
        "carton_cuft": decimal_text(carton_cuft),
        "mold_total_rmb": decimal_text(mold_total_rmb),
        "mold_amortization_rmb": decimal_text(amortization_rmb),
        "mold_amortization_usd": decimal_text(amortization_usd),
        "total_hkd": decimal_text(total_hkd),
    }


def _component_cost(rows: Any, path: str, breakdown: list[dict[str, Any]]) -> Decimal:
    total = ZERO
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"{path}第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), f"{path}第 {index + 1} 行用量")
        unit_price = decimal_value(row.get("unit_price_hkd"), f"{path}第 {index + 1} 行单价")
        line_total = quantity * unit_price
        child_total = _component_cost(row.get("children", []), f"{path}子项", breakdown)
        total += line_total + child_total
        breakdown.append({
            "kind": "electronic_component",
            "item": str(row.get("item", "")),
            "line_hkd": decimal_text(line_total),
            "children_hkd": decimal_text(child_total),
        })
    return total


def _electronic(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    component = _component_cost(payload.get("components", []), "电子零件", result["line_breakdown"])
    extras = sum(
        (
            decimal_value(payload.get(field), label)
            for field, label in (
                ("bonding_hkd", "邦定"),
                ("smt_hkd", "SMT/贴片"),
                ("labor_hkd", "电子人工"),
                ("testing_hkd", "测试维修"),
                ("packaging_hkd", "包装运输"),
            )
        ),
        ZERO,
    )
    pre_tax = component + extras
    profit_rate = decimal_value(
        payload.get("profit_rate_percent"),
        "电子利润率",
        str(snapshot.get("electronic_profit_rate_percent", "10")),
    )
    with_profit = pre_tax * (1 + profit_rate / 100)
    tax_difference = decimal_value(payload.get("tax_credit_difference_hkd"), "抵税差额")
    tax_payable = tax_difference * Decimal("0.10")
    total = with_profit + tax_difference + tax_payable
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {
        "component_hkd": decimal_text(component),
        "pre_tax_hkd": decimal_text(pre_tax),
        "with_profit_hkd": decimal_text(with_profit),
        "tax_credit_difference_hkd": decimal_text(tax_difference),
        "tax_payable_hkd": decimal_text(tax_payable),
        "total_hkd": decimal_text(total),
    }


def _molding(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    injection_total = ZERO
    blow_total = ZERO
    for index, row in enumerate(payload.get("injection_lines", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"注塑第 {index + 1} 行格式无效")
        material = str(row.get("material", "")).strip()
        grade = str(row.get("grade", "")).strip()
        material_price = _material_price(snapshot, material, grade)
        machine_code = str(row.get("machine_code", "")).strip()
        machine_price = _machine_price(snapshot, machine_code)
        if material_price is None:
            result["warnings"].append(_warning("material_price_missing", f"注塑第 {index + 1} 行未匹配材料价：{material} + {grade}"))
        if machine_price is None:
            result["warnings"].append(_warning("machine_price_missing", f"注塑第 {index + 1} 行未匹配机型价：{machine_code}"))
        if material_price is None or machine_price is None:
            result["line_breakdown"].append({"kind": "injection", "item": str(row.get("item", "")), "amount_hkd": None})
            continue
        net_weight = decimal_value(row.get("net_weight_g"), "啤净重")
        loss_rate = decimal_value(
            row.get("loss_rate_percent"),
            "注塑损耗率",
            str(snapshot.get("injection_loss_rate_percent", "3")),
        )
        sets = positive_value(row.get("sets"), "套数")
        target_output = positive_value(row.get("target_output"), "目标数")
        quantity = decimal_value(row.get("quantity"), "成品用量", "1")
        material_cost = net_weight * (1 + loss_rate / 100) * material_price / 454
        molding_cost = machine_price / sets / target_output
        line_total = (material_cost + molding_cost) * quantity
        injection_total += line_total
        result["line_breakdown"].append({
            "kind": "injection",
            "item": str(row.get("item", "")),
            "material_price_hkd_lb": decimal_text(material_price),
            "machine_shift_price_hkd": decimal_text(machine_price),
            "material_cost_hkd": decimal_text(material_cost),
            "molding_cost_hkd": decimal_text(molding_cost),
            "amount_hkd": decimal_text(line_total),
        })

    for index, row in enumerate(payload.get("blow_lines", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"吹气第 {index + 1} 行格式无效")
        material = str(row.get("material", "")).strip()
        grade = str(row.get("grade", "")).strip()
        material_price = _material_price(snapshot, material, grade)
        if material_price is None:
            result["warnings"].append(_warning("material_price_missing", f"吹气第 {index + 1} 行未匹配材料价：{material} + {grade}"))
            result["line_breakdown"].append({"kind": "blow", "item": str(row.get("item", "")), "amount_hkd": None})
            continue
        weight = decimal_value(row.get("estimated_weight_g"), "吹气预估料重")
        labor = decimal_value(row.get("labor_hkd"), "吹气人工")
        burr = decimal_value(row.get("burr_hkd"), "披锋")
        multiplier = decimal_value(
            row.get("profit_multiplier"),
            "吹气利润倍率",
            str(snapshot.get("blow_profit_multiplier", "1.05")),
        )
        quantity = decimal_value(row.get("quantity"), "吹气成品用量", "1")
        material_cost = weight * material_price / 454
        line_total = (material_cost + labor + burr) * multiplier * quantity
        blow_total += line_total
        result["line_breakdown"].append({
            "kind": "blow",
            "item": str(row.get("item", "")),
            "material_cost_hkd": decimal_text(material_cost),
            "amount_hkd": decimal_text(line_total),
        })

    caixing_rows = payload.get("caixing_tool_plan_rows", []) or []
    if not isinstance(caixing_rows, list):
        raise CalculationInputError("彩星 Tool Plan 必须是数组")
    if len(caixing_rows) > 51:
        raise CalculationInputError("彩星 Tool Plan 最多允许 51 行")
    caixing_refs: set[str] = set()
    for index, row in enumerate(caixing_rows):
        label = f"彩星 Tool Plan 第 {index + 1} 行"
        if not isinstance(row, dict):
            raise CalculationInputError(f"{label}格式无效")
        ref_no = str(row.get("ref_no", "")).strip()
        if not ref_no:
            raise CalculationInputError(f"{label} Ref 不能为空")
        if ref_no in caixing_refs:
            raise CalculationInputError(f"{label} Ref 重复：{ref_no}")
        caixing_refs.add(ref_no)
        process_type = str(row.get("process_type", "")).strip().upper()
        if process_type not in {"IN", "BL", "CP", "DC", "RC"}:
            raise CalculationInputError(f"{label}工艺必须是 IN、BL、CP、DC 或 RC")
        description = str(row.get("description", "")).strip()
        sku_no = str(row.get("sku_no", "")).strip()
        material = str(row.get("material", "")).strip()
        machine_size = str(row.get("machine_size", "")).strip()
        if not description or not sku_no or not material or not machine_size:
            raise CalculationInputError(f"{label}产品、SKU、物料及机型不能为空")
        cavities = positive_value(row.get("cavities"), f"{label} Cav")
        up = positive_value(row.get("up"), f"{label} Up")
        net_weight = positive_value(row.get("net_weight_g"), f"{label} 净重")
        material_code = positive_value(row.get("material_code"), f"{label} Material Code")
        material_cost = positive_value(row.get("material_cost_hkd"), f"{label} Material Cost")
        cycle_time = positive_value(row.get("cycle_time_seconds"), f"{label} Cycle Time")
        process_cost = positive_value(row.get("process_cost_hkd"), f"{label} Process Cost")
        tooling_cost = decimal_value(row.get("tooling_cost_hkd"), f"{label} Tooling Cost")
        if process_type == "IN":
            positive_value(machine_size, f"{label} Machine Size")
        result["line_breakdown"].append({
            "kind": "caixing_tool_plan",
            "customer_only": True,
            "ref_no": ref_no,
            "process_type": process_type,
            "item": description,
            "sku_no": sku_no,
            "cavities": decimal_text(cavities),
            "up": decimal_text(up),
            "net_weight_g": decimal_text(net_weight),
            "material_code": decimal_text(material_code),
            "material": material,
            "machine_size": machine_size,
            "cycle_time_seconds": decimal_text(cycle_time),
            "tooling_cost_hkd": decimal_text(tooling_cost),
            "material_cost_hkd": decimal_text(material_cost),
            "process_cost_hkd": decimal_text(process_cost),
            "amount_hkd": "0.0000",
        })
    total = injection_total + blow_total
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {
        "injection_hkd": decimal_text(injection_total),
        "blow_hkd": decimal_text(blow_total),
        "total_hkd": decimal_text(total),
    }


def _painting(payload: dict[str, Any], result: dict[str, Any]) -> None:
    operation_names = ("clamp", "pad_print", "spray", "edge", "paint", "dip", "wipe")
    total = ZERO
    for index, row in enumerate(payload.get("rows", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"喷油第 {index + 1} 行格式无效")
        line_total = ZERO
        operations = row.get("operations", {}) or {}
        if not isinstance(operations, dict):
            raise CalculationInputError(f"喷油第 {index + 1} 行工序格式无效")
        operation_breakdown: dict[str, str] = {}
        for operation in operation_names:
            values = operations.get(operation, {}) or {}
            if not isinstance(values, dict):
                raise CalculationInputError(f"喷油第 {index + 1} 行 {operation} 格式无效")
            operation_total = decimal_value(values.get("quantity"), "工序数量") * decimal_value(values.get("unit_price_hkd"), "工序单价")
            line_total += operation_total
            operation_breakdown[operation] = decimal_text(operation_total)
        total += line_total
        result["line_breakdown"].append({"kind": "painting", "item": str(row.get("item", "")), "operations": operation_breakdown, "amount_hkd": decimal_text(line_total)})
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {"total_hkd": decimal_text(total)}


def _slush(payload: dict[str, Any], result: dict[str, Any]) -> None:
    total = ZERO
    for index, row in enumerate(payload.get("lines", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"搪胶第 {index + 1} 行格式无效")
        line_total = decimal_value(row.get("quantity"), "搪胶数量") * decimal_value(row.get("unit_price_hkd"), "搪胶单价")
        total += line_total
        result["line_breakdown"].append({"kind": "slush", "item": str(row.get("item", "")), "amount_hkd": decimal_text(line_total)})
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {"total_hkd": decimal_text(total)}


def _sewing(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
    category_rmb = {"clothes": ZERO, "hair": ZERO}
    for group_index, group in enumerate(payload.get("groups", []) or []):
        if not isinstance(group, dict):
            raise CalculationInputError(f"车缝产品组第 {group_index + 1} 组格式无效")
        category = str(group.get("category", "clothes"))
        if category not in category_rmb:
            raise CalculationInputError(f"车缝产品组第 {group_index + 1} 组分类无效")
        group_total = ZERO
        contains_labor_line = False
        for row_index, row in enumerate(group.get("materials", []) or []):
            if not isinstance(row, dict):
                raise CalculationInputError(f"车缝第 {group_index + 1} 组第 {row_index + 1} 行格式无效")
            item = str(row.get("item", ""))
            contains_labor_line = contains_labor_line or "人工" in item
            line_total = (
                decimal_value(row.get("usage"), "车缝用量")
                * decimal_value(row.get("unit_price_rmb"), "车缝物料价")
                * decimal_value(row.get("markup"), "车缝码点", "1")
            )
            group_total += line_total
            result["line_breakdown"].append({"kind": "sewing_material", "group": str(group.get("name", "")), "item": item, "amount_rmb": decimal_text(line_total)})
        labor = ZERO if contains_labor_line else decimal_value(group.get("labor_rmb"), "车缝产品组人工")
        group_total += labor
        category_rmb[category] += group_total
    total_rmb = sum(category_rmb.values(), ZERO)
    total_hkd = total_rmb / fx
    result["currency_totals"] = {"HKD": decimal_text(total_hkd), "RMB": decimal_text(total_rmb), "USD": "0.0000"}
    result["totals"] = {
        "clothes_rmb": decimal_text(category_rmb["clothes"]),
        "hair_rmb": decimal_text(category_rmb["hair"]),
        "clothes_hkd": decimal_text(category_rmb["clothes"] / fx),
        "hair_hkd": decimal_text(category_rmb["hair"] / fx),
        "total_hkd": decimal_text(total_hkd),
    }


def _assembly(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    labor_base = decimal_value(
        payload.get("labor_base_hkd"),
        "装配人工基数",
        str(snapshot.get("assembly_labor_base_hkd", "310")),
    )
    category_total = {"assembly": ZERO, "packaging": ZERO}
    for group_index, group in enumerate(payload.get("groups", []) or []):
        if not isinstance(group, dict):
            raise CalculationInputError(f"装配产品组第 {group_index + 1} 组格式无效")
        category = str(group.get("category", "assembly"))
        if category not in category_total:
            raise CalculationInputError(f"装配产品组第 {group_index + 1} 组分类无效")
        group_total = ZERO
        for process_index, process in enumerate(group.get("processes", []) or []):
            if not isinstance(process, dict):
                raise CalculationInputError(f"装配第 {group_index + 1} 组工序 {process_index + 1} 格式无效")
            persons = decimal_value(process.get("persons"), "装配人数")
            teams = decimal_value(process.get("teams"), "装配小组数")
            production_qty = positive_value(process.get("production_qty"), "装配生产量")
            process_total = labor_base * persons * teams / production_qty
            group_total += process_total
            result["line_breakdown"].append({"kind": "assembly_process", "group": str(group.get("name", "")), "process": str(process.get("name", "")), "amount_hkd_pcs": decimal_text(process_total)})
        category_total[category] += group_total
    total = sum(category_total.values(), ZERO)
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {
        "assembly_hkd": decimal_text(category_total["assembly"]),
        "packaging_hkd": decimal_text(category_total["packaging"]),
        "total_hkd": decimal_text(total),
    }


def _sales(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any], context: dict[str, Any]) -> None:
    factory_price = decimal_value(context.get("factory_price_hkd"), "出厂价")
    additional_tax = decimal_value(payload.get("additional_tax_hkd"), "附加税")
    indonesia_freight = decimal_value(payload.get("indonesia_freight_hkd"), "印尼运费")
    shipping_floor = factory_price + additional_tax
    tax_rates = snapshot.get("tax_rates", {})
    tax_deduction = ZERO
    for index, row in enumerate(payload.get("tax_categories", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"减税第 {index + 1} 行格式无效")
        code = str(row.get("code", "")).strip()
        category_amount = decimal_value(row.get("amount_hkd"), "减税分类金额")
        rate_source = row.get("rate")
        if rate_source in (None, ""):
            if not isinstance(tax_rates, dict) or code not in tax_rates:
                result["warnings"].append(_warning("tax_rate_missing", f"未找到减税分类税率：{code}"))
                continue
            rate_source = tax_rates[code]
        rate = decimal_value(rate_source, "减税率")
        deduction = category_amount * rate
        tax_deduction += deduction
        result["line_breakdown"].append({"kind": "tax", "code": code, "amount_hkd": decimal_text(category_amount), "rate": decimal_text(rate), "deduction_hkd": decimal_text(deduction)})

    mold_amortization_usd = decimal_value(context.get("mold_amortization_usd"), "模具分摊 USD")
    fx_hkd_usd = positive_value(snapshot.get("fx", {}).get("hkd_usd"), "HKD/USD 汇率")
    scenario_results: list[dict[str, Any]] = []
    for index, row in enumerate(payload.get("scenarios", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"出货场景第 {index + 1} 行格式无效")
        capacity = positive_value(row.get("capacity_cuft"), "运输容量 CUFT")
        carton_cuft = positive_value(row.get("carton_cuft"), "单箱 CUFT")
        qty_per_carton = positive_value(row.get("qty_per_carton"), "每箱数量")
        freight_cost = decimal_value(row.get("freight_cost_hkd"), "运输费用")
        total_cartons = max((capacity / carton_cuft).quantize(Decimal("1"), rounding=ROUND_HALF_UP), Decimal("1"))
        per_piece = freight_cost / total_cartons / qty_per_carton
        freight_share = decimal_value(row.get("freight_share"), "运费占比", str(snapshot.get("freight_share", "0.48")))
        lift_share = decimal_value(row.get("lift_share"), "吊柜费占比", str(snapshot.get("lift_share", "0.52")))
        markup = decimal_value(row.get("markup"), "码点", str(snapshot.get("markup", "1.2")))
        settlement = positive_value(row.get("settlement"), "找数", str(snapshot.get("settlement", "0.98")))
        freight = per_piece * freight_share
        lift = per_piece * lift_share
        with_freight = shipping_floor + freight + lift
        after_markup = with_freight * markup
        after_settlement = after_markup / settlement
        total_usd = after_settlement / fx_hkd_usd + mold_amortization_usd
        scenario_results.append({
            "name": str(row.get("name", f"场景{index + 1}")),
            "total_cartons": decimal_text(total_cartons),
            "freight_hkd": decimal_text(freight),
            "lift_hkd": decimal_text(lift),
            "after_settlement_hkd": decimal_text(after_settlement),
            "total_usd": decimal_text(total_usd),
        })
    result["line_breakdown"].extend({"kind": "shipping_scenario", **row} for row in scenario_results)
    result["currency_totals"]["HKD"] = decimal_text(shipping_floor)
    result["totals"] = {
        "factory_price_hkd": decimal_text(factory_price),
        "indonesia_freight_hkd": decimal_text(indonesia_freight),
        "additional_tax_hkd": decimal_text(additional_tax),
        "shipping_floor_hkd": decimal_text(shipping_floor),
        "tax_deduction_hkd": decimal_text(tax_deduction),
        "after_tax_cost_hkd": decimal_text(max(factory_price - tax_deduction, ZERO)),
        "scenarios": scenario_results,
    }


def calculate_section(
    section_code: str,
    payload: dict[str, Any],
    snapshot: dict[str, Any],
    reference_snapshot_id: str,
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if section_code not in SECTION_INPUT_CONTRACTS:
        raise CalculationInputError("未知内部报价分段")
    if not isinstance(payload, dict):
        raise CalculationInputError("分段输入必须是对象")
    result = _base_result(section_code, payload, reference_snapshot_id)
    meaningful_fields = {
        "engineering": ("materials", "molds", "cartons"),
        "electronic": (
            "components",
            "bonding_hkd",
            "smt_hkd",
            "labor_hkd",
            "testing_hkd",
            "packaging_hkd",
            "tax_credit_difference_hkd",
        ),
        "molding": ("injection_lines", "blow_lines", "caixing_tool_plan_rows"),
        "painting": ("rows",),
        "slush": ("lines",),
        "sewing": ("groups",),
        "assembly": ("groups",),
    }
    fields = meaningful_fields.get(section_code)
    if payload and fields and not any(payload.get(field) for field in fields):
        result["warnings"].append(
            _warning("no_calculation_lines", "当前分段没有符合字段契约的可计算明细")
        )
    calculator_context = context or {}
    if section_code == "engineering":
        _engineering(payload, snapshot, result)
    elif section_code == "electronic":
        _electronic(payload, snapshot, result)
    elif section_code == "molding":
        _molding(payload, snapshot, result)
    elif section_code == "painting":
        _painting(payload, result)
    elif section_code == "slush":
        _slush(payload, result)
    elif section_code == "sewing":
        _sewing(payload, snapshot, result)
    elif section_code == "assembly":
        _assembly(payload, snapshot, result)
    elif section_code == "sales":
        _sales(payload, snapshot, result, calculator_context)
    dependencies = calculator_context.get("dependencies", {})
    result["dependencies"] = dependencies if isinstance(dependencies, dict) else {}
    result["dependency_hash"] = content_hash(result["dependencies"])
    return _finish(result)


def total_from_calculation(calculation: dict[str, Any], key: str = "total_hkd") -> Decimal:
    totals = calculation.get("totals", {})
    if not isinstance(totals, dict):
        return ZERO
    return decimal_value(totals.get(key), key)
