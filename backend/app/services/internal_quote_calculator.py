import hashlib
import json
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal_quote import InternalQuotePricingBaseline
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

FREIGHT_ROUTE_DEFINITIONS = (
    ("hk40", "HK 40 柜", "cap_40", "container_40", "hk_container_40"),
    ("hk20", "HK 20 柜", "cap_20", "container_20", "hk_container_20"),
    ("yt40", "YT 40 柜", "cap_40", "container_40", "yt_container_40"),
    ("yt20", "YT 20 柜", "cap_20", "container_20", "yt_container_20"),
    ("hk10t", "HK 10 吨车", "cap_10t", "truck_10t", "hk_truck_10t"),
    ("yt10t", "YT 10 吨车", "cap_10t", "truck_10t", "yt_truck_10t"),
    ("hk5t", "HK 5 吨车", "cap_5t", "truck_5t", "hk_truck_5t"),
    ("yt5t", "YT 5 吨车", "cap_5t", "truck_5t", "yt_truck_5t"),
)

FREIGHT_CAPACITY_DEFAULT_KEYS = {
    "cap_10t": "truck_10t",
    "cap_5t": "truck_5t",
    "cap_40": "container_40",
    "cap_20": "container_20",
}


def _default_freight_routes() -> list[dict[str, str]]:
    return [
        {
            "route_key": route_key,
            "route_name": label,
            "capacity_key": capacity_key,
            "freight_hkd": DEFAULT_FREIGHT["cost_hkd"][default_cost_key],
            "lifting_hkd": "0",
        }
        for route_key, label, capacity_key, _default_capacity_key, default_cost_key
        in FREIGHT_ROUTE_DEFINITIONS
    ]


def _stored_freight_routes(value: str) -> list[dict[str, str]]:
    try:
        stored = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        stored = []
    if isinstance(stored, list):
        routes: list[dict[str, str]] = []
        route_keys: set[str] = set()
        for row in stored:
            if not isinstance(row, dict):
                continue
            route_key = str(row.get("route_key", "")).strip()
            route_name = str(row.get("route_name", "")).strip()
            capacity_key = str(row.get("capacity_key", "")).strip()
            freight_hkd = str(row.get("freight_hkd", "")).strip()
            lifting_hkd = str(row.get("lifting_hkd", "0")).strip()
            if (
                not route_key
                or route_key.lower() in route_keys
                or not route_name
                or capacity_key not in FREIGHT_CAPACITY_DEFAULT_KEYS
                or not freight_hkd
                or not lifting_hkd
            ):
                continue
            route_keys.add(route_key.lower())
            routes.append({
                "route_key": route_key,
                "route_name": route_name,
                "capacity_key": capacity_key,
                "freight_hkd": freight_hkd,
                "lifting_hkd": lifting_hkd,
            })
        if routes:
            return routes
    # Compatibility with the unreleased fixed-key baseline representation.
    if isinstance(stored, dict):
        return [
            {**row, "freight_hkd": str(stored.get(row["route_key"], row["freight_hkd"])).strip()}
            for row in _default_freight_routes()
        ]
    return _default_freight_routes()

SECTION_INPUT_CONTRACTS: dict[str, dict[str, Any]] = {
    "sales": {
        "paper_price_factor": "decimal>0; default 2.75",
        "flat_card_price_factor": "decimal>0; defaults to paper_price_factor",
        "testing_fee_total_usd": "decimal>=0; optional business testing-fee total",
        "testing_fee_moqs": "list of positive integer MOQ tiers when testing_fee_total_usd>0",
        "testing_fee_moq": "legacy single MOQ; read when testing_fee_moqs is absent",
        "packaging_materials": [{"item": "text", "specification": "text", "category": "blister|color_box_inner_card|leaflet_manual|other_purchase", "quantity": "decimal>=0", "unit_price_rmb": "decimal>=0", "tax_rate_percent": "0..100", "remark": "text", "disney_description": "text", "disney_unit_price_usd": "decimal>=0", "disney_included": "decimal>0"}],
        "product_size_in": {"length": "optional decimal>0 inch", "width": "optional decimal>0 inch", "height": "optional decimal>0 inch"},
        "color_box_size_unit": "cm|inch; display/input preference, default inch",
        "color_box_size_in": {"length": "decimal>0 canonical inch", "width": "decimal>0 canonical inch", "height": "decimal>0 canonical inch"},
        "legacy_dimension_aliases": "product_size_cm/color_box_size_cm remain readable as historical inch-valued keys",
        "cartons": [{"item": "text", "size_unit": "cm|inch display/input preference", "length_in": "decimal>0 canonical inch", "width_in": "decimal>0 canonical inch", "height_in": "decimal>0 canonical inch", "qty_per_carton": "decimal>0", "flat_cards": "list"}],
        "freight_calc": {
            "enabled": "boolean; default true",
            "cap_10t|cap_5t|cap_40|cap_20": "decimal>0 CUFT",
            "route key fields": "legacy quote override decimal>=0 HKD; absent uses frozen pricing-baseline route list and freight",
            "source": "first sales carton CUFT and qty_per_carton",
        },
        "shipping": {
            "markup_x": "legacy/current selected 0.01..9.99",
            "markup_tiers": [{"moq": "positive integer, ascending", "markup_x": "0.01..9.99"}],
            "selected_markup_moq": "optional MOQ value that must exist in markup_tiers",
            "misc_ratio": "0..1; default 0.02",
        },
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
        "materials": [{"item": "text", "category": "hardware|auxiliary|packaging; hardware is fixed", "specification": "text", "auxiliary_category": "五金(fixed for hardware)|吸塑|胶袋|彩盒/内卡|电池|利宝|电镀|其他外购", "quantity": "decimal>=0", "unit_price_rmb": "decimal>=0", "tax_rate_percent": "hardware fixed 13; others decimal>=0; record only", "remark": "text", "legacy_fields": "purpose/unit/material/surface_treatment/supplier/contact remain readable but are not editable or imported", "disney_description": "text", "disney_section": "product|package", "disney_unit_price_usd": "decimal>=0", "disney_included": "decimal>=0"}],
        "molds": [{"item": "text", "mold_no": "text", "chinese_name": "text", "mold_base_type": "text", "mold_base_material": "text", "structure": "text", "process": "text", "material": "text", "material_type": "text", "color": "text", "cavity": "text", "quantity": "sets; record only", "net_weight_g": "decimal>=0", "cycle_time_seconds": "decimal>=0", "mold_size": "text", "mold_specification": "text", "image_reference": "section attachment name/reference", "cost_rmb": "whole-mold quote RMB", "remark": "text", "disney_mold_no": "text", "disney_parts": "text", "disney_material": "text", "disney_cavities": "decimal>0", "disney_parts_per_shot": "decimal>0", "disney_tool_cost_usd": "decimal>=0", "dickie_project_name_en": "English text", "dickie_mold_no": "text", "dickie_parts_en": "English text", "dickie_resin": "text", "dickie_mold_size": "text", "dickie_mold_material": "text", "dickie_cavities": "decimal>0", "dickie_parts_per_shot": "decimal>0", "dickie_mold_cost_hkd": "decimal>0", "dickie_remark_en": "English text", "caixing_tool_plan_ref": "text", "caixing_mold_cost_hkd": "decimal>=0", "caixing_customer_mold_cost_hkd": "decimal>0"}],
        "mold_allocation_enabled": "boolean; default true; false preserves inputs but excludes all production mold/prototype/testing allocation",
        "production_mold_costs": [{"item": "text", "cost_rmb": "decimal>=0"}],
        "mold_fx_rmb_usd": "decimal>0; default frozen RMB/USD rate",
        "amortization_qty": "decimal>0 when production mold cost exists; default 20000",
        "customer_mold_subsidy_usd": "decimal>=0",
        "prototype_total_usd": "decimal>=0",
        "prototype_amortization_qty": "decimal>0 when prototype cost exists; default 50000",
        "testing_total_usd": "decimal>=0",
        "testing_amortization_qty": "decimal>0 when testing cost exists; default 2000",
        "cartons": "legacy compatibility only; new carton and flat-card input belongs to sales",
    },
    "electronic": {
        "pricing_currency": "RMB for the current contract; legacy HKD payloads remain readable",
        "quote_mode": "detail|quick; legacy defaults detail",
        "quick_quotes": [{"item": "text", "unit_price_rmb": "decimal>0", "unit_price_hkd": "calculated from frozen RMB/HKD rate", "tax_rate_percent": "0..100; default 13", "remark": "text"}],
        "components": [{"item": "text", "specification": "text", "quantity": "decimal>=0", "unit_price_rmb": "decimal>=0", "tax_rate_percent": "default 13", "remark": "text", "children": "recursive list; retained but ignored while quick mode is active"}],
        "bonding_rmb": "decimal>=0",
        "smt_rmb": "decimal>=0",
        "labor_rmb": "decimal>=0",
        "testing_rmb": "decimal>=0",
        "packaging_rmb": "decimal>=0",
        "profit_rate_percent": "default 10",
        "formula": "quick rows use quantity 1; tax difference = profit-inclusive price * 13% - component input-tax credit; tax payable = tax difference * 10%",
        "legacy_fields": "unit_price_hkd, *_hkd and tax_credit_difference_hkd remain readable",
    },
    "molding": {
        "injection_loss_rate_percent": "default 3; changing it applies to newly normalized rows",
        "injection_lines": [{"item": "mold name", "mold_no": "text", "material": "frozen material category", "grade": "frozen concrete grade", "color": "text", "net_weight_g": "decimal>=0", "loss_rate_percent": "default from section or snapshot", "machine_name": "record only", "machine_code": "A-code or imported bare numeric A-code", "cavity": "record only", "sets": "decimal>0", "target_output": "decimal>0", "cycle_time_seconds": "record only", "quantity": "default 1", "remark": "text", "disney_mold_no": "text", "disney_resin_cost_usd_kg": "decimal>0", "disney_cycle_time_seconds": "decimal>0", "disney_labor_rate_usd_hr": "decimal>0"}],
        "blow_lines": [{"item": "text", "daily_capacity": "record only", "material": "exact text", "grade": "exact text", "estimated_weight_g": "decimal>=0", "labor_hkd": "decimal>=0", "burr_hkd": "decimal>=0", "profit_multiplier": "default 1.05", "quantity": "default 1", "output_count": "record only", "mold_price_rmb": "record only", "remark": "text"}],
        "caixing_tool_plan_rows": [{"ref_no": "unique text", "process_type": "IN|BL|CP|DC|RC", "tool_no": "text", "tooling_cost_hkd": "decimal>=0", "description": "text", "sku_no": "text", "cavities": "decimal>0", "up": "decimal>0", "net_weight_g": "decimal>0", "material_code": "decimal>0", "material": "text", "color": "text", "material_cost_hkd": "decimal>0", "machine_size": "text", "cycle_time_seconds": "decimal>0", "process_cost_hkd": "decimal>0"}],
    },
    "painting": {"quote_mode": "detail|quick; legacy defaults detail", "quick_quote": {"spray_labor_hkd": "decimal>=0", "paint_hkd": "decimal>=0", "paint_tax_rate_percent": "fixed 13"}, "rows": [{"image_reference": "text", "name": "text", "position": "text", "operations": "夹模/移印/散枪/边模/油色/浸油/抹油/擦PP水 quantity and unit_price_hkd", "remark": "text"}], "disney_decorations": [{"application_type": "text", "rate_per_op_usd": "decimal>0", "operations": "decimal>0"}]},
    "slush": {"lines": [{"product_code": "text", "item": "glue part name", "material": "record only", "weight_g": "record only decimal>=0", "daily_output_24h": "record only decimal>=0", "quantity": "decimal>=0", "unit_price_hkd": "decimal>=0", "remark": "text"}], "formula": "line total HKD = quantity * unit price HKD; total RMB = total HKD * frozen RMB/HKD rate"},
    "sewing": {"quote_mode": "detail|quick; legacy defaults detail", "quick_quotes": [{"doll_name": "text", "unit_price_hkd": "decimal>0"}], "groups": [{"name": "text", "category": "clothes|hair", "materials": [{"item": "fabric name", "part": "text", "craft": "blank|电绣", "pieces": "record only decimal>=0", "usage": "decimal>=0", "unit_price_rmb": "decimal>=0", "markup": "blank/zero defaults 1", "remark": "text"}], "labor_rmb": "legacy compatible; added only when no labor detail line"}], "formula": "quick mode totals doll HKD prices; detail mode price RMB = usage * material price * markup, then HKD = RMB / frozen rate"},
    "assembly": {
        "groups": [{"name": "text", "category": "assembly|packaging", "production_qty": "decimal>0", "teams": "decimal>0", "processes": [{"name": "text", "persons": "decimal>=0", "remark": "text"}]}],
        "labor_base_hkd": "default 260; adjustable",
        "standard_work_hours": "default 11; adjustable reference value",
        "formula": "labor HKD/PCS = labor base HKD/person * total persons * teams / production quantity",
        "legacy_fields": "process-level teams and production_qty remain readable",
    },
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


def build_reference_snapshot(
    db: Session,
    *,
    factory_id: str = "",
    workshop_code: str = "",
) -> dict[str, Any]:
    legacy_prices = {
        row.material.strip(): decimal_text(Decimal(str(row.unit_price)))
        for row in db.scalars(select(MoldingSampleMaterialPrice).order_by(MoldingSampleMaterialPrice.material)).all()
    }
    baseline = None
    if factory_id and workshop_code:
        baseline = db.scalar(
            select(InternalQuotePricingBaseline).where(
                InternalQuotePricingBaseline.factory_id == factory_id,
                InternalQuotePricingBaseline.workshop_code == workshop_code,
            )
        )
    material_rows = DEFAULT_MATERIAL_PRICES
    machine_rows = DEFAULT_MACHINE_PRICES
    freight_routes = _default_freight_routes()
    baseline_revision = 0
    if baseline is not None:
        try:
            stored_material_rows = json.loads(baseline.material_prices_json)
            stored_machine_rows = json.loads(baseline.machine_prices_json)
        except (TypeError, json.JSONDecodeError):
            stored_material_rows = []
            stored_machine_rows = []
        try:
            freight_routes = _stored_freight_routes(baseline.freight_routes_json)
        except AttributeError:
            freight_routes = _default_freight_routes()
        if isinstance(stored_material_rows, list) and stored_material_rows:
            material_rows = tuple(
                (
                    str(row.get("material", "")).strip(),
                    str(row.get("grade", "")).strip(),
                    str(row.get("price_hkd_lb", "")).strip(),
                )
                for row in stored_material_rows
                if isinstance(row, dict)
            )
        if isinstance(stored_machine_rows, list) and stored_machine_rows:
            machine_rows = tuple(
                (
                    str(row.get("machine_range", "")).strip(),
                    str(row.get("machine", "")).strip(),
                    str(row.get("shift_price_hkd", "")).strip(),
                )
                for row in stored_machine_rows
                if isinstance(row, dict)
            )
        baseline_revision = baseline.revision
    return {
        "baseline_version": FORMULA_VERSION,
        "pricing_baseline_revision": baseline_revision,
        "fx": {"rmb_hkd": "0.85", "hkd_usd": "7.8", "rmb_usd": "7.75"},
        "material_prices": {
            f"{material}|{grade}": price
            for material, grade, price in material_rows
        },
        "legacy_material_prices": legacy_prices,
        "machine_prices": [
            {"range": machine_range, "machine": machine, "shift_price_hkd": price}
            for machine_range, machine, price in machine_rows
        ],
        "paper_price_factor": "2.75",
        "injection_loss_rate_percent": "3",
        "blow_profit_multiplier": "1.05",
        "electronic_profit_rate_percent": "10",
        "assembly_labor_base_hkd": "260",
        "assembly_standard_work_hours": "11",
        "tax_rates": DEFAULT_TAX_RATES,
        "freight": {
            "capacity_cuft": dict(DEFAULT_FREIGHT["capacity_cuft"]),
            "cost_hkd": dict(DEFAULT_FREIGHT["cost_hkd"]),
            "routes": freight_routes,
        },
        "freight_share": "0.48",
        "lift_share": "0.52",
        "markup": "1.2",
        "misc_ratio": "0.02",
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
    # Imported mold tables frequently store the A-code as a bare number (for
    # example "18"). It is the same reference key as "18A" in the baseline.
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)A?\s*", value, flags=re.IGNORECASE)
    return Decimal(match.group(1)) if match else None


def _machine_price(snapshot: dict[str, Any], machine_code: str) -> Decimal | None:
    code_value = _a_code(machine_code)
    rows = snapshot.get("machine_prices", [])
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        range_label = str(row.get("range", ""))
        machine_label = str(row.get("machine", "")).strip()
        if machine_code.strip().casefold() in {range_label.strip().casefold(), machine_label.casefold()}:
            return decimal_value(row.get("shift_price_hkd"), range_label or machine_label)
        if code_value is None:
            continue
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
        tax_rate = (
            Decimal("13")
            if category == "hardware"
            else decimal_value(row.get("tax_rate_percent"), f"工程材料第 {index + 1} 行税点")
        )
        material_category = "五金" if category == "hardware" else str(row.get("auxiliary_category", "其他外购"))
        category_hkd[category] += line_hkd
        material_rmb += line_rmb
        result["line_breakdown"].append({
            "kind": "material",
            "item": str(row.get("item", "")),
            "category": category,
            "auxiliary_category": material_category,
            "specification": str(row.get("specification", row.get("spec", ""))),
            "quantity": decimal_text(quantity),
            "unit": str(row.get("unit", "")),
            "unit_price_rmb": decimal_text(unit_price),
            "unit_price_hkd": decimal_text(unit_price / fx),
            "tax_rate_percent": decimal_text(tax_rate),
            "amount_rmb": decimal_text(line_rmb),
            "amount_hkd": decimal_text(line_hkd),
            "formula": "用量 × 单价 RMB ÷ 冻结 RMB→HKD 汇率（税点仅记录，不重复加价）",
        })

    mold_quote_total_rmb = ZERO
    for index, row in enumerate(payload.get("molds", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"模具第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), f"模具第 {index + 1} 行套数", "1")
        cost_rmb = decimal_value(row.get("cost_rmb"), f"模具第 {index + 1} 行价格")
        cost_hkd = cost_rmb / fx
        mold_quote_total_rmb += cost_rmb
        result["line_breakdown"].append({
            "kind": "mold_quote",
            "item": str(row.get("item", row.get("mold_no", ""))),
            "mold_no": str(row.get("mold_no", "")),
            "quantity": decimal_text(quantity),
            "amount_rmb": decimal_text(cost_rmb),
            "amount_hkd": decimal_text(cost_hkd),
            "reference_only": True,
            "formula": "整套模具价格 RMB ÷ 冻结 RMB→HKD 汇率；套数仅作模具资料记录",
        })

    allocation_enabled = payload.get("mold_allocation_enabled", True)
    if not isinstance(allocation_enabled, bool):
        raise CalculationInputError("是否启用生产模具费用分摊必须为布尔值")
    production_rows = payload.get("production_mold_costs")
    has_production_rows = isinstance(production_rows, list)
    mold_total_rmb = ZERO
    if allocation_enabled and has_production_rows:
        for index, row in enumerate(production_rows):
            if not isinstance(row, dict):
                raise CalculationInputError(f"生产模具费用第 {index + 1} 行格式无效")
            cost_rmb = decimal_value(row.get("cost_rmb"), f"生产模具费用第 {index + 1} 行金额")
            mold_total_rmb += cost_rmb
            result["line_breakdown"].append({
                "kind": "production_mold_cost",
                "item": str(row.get("item", "")),
                "amount_rmb": decimal_text(cost_rmb),
                "amount_hkd": decimal_text(cost_rmb / fx),
                "reference_only": True,
                "formula": "生产模具费用 RMB；按下方分摊套数转为每件成本",
            })
    elif allocation_enabled:
        # Historical payloads stored only the mold-detail table. Preserve their
        # accepted calculation until they are reopened and saved in the new form.
        mold_total_rmb = mold_quote_total_rmb

    amortization_rmb = ZERO
    amortization_usd = ZERO
    mold_share_rmb = ZERO
    mold_share_usd = ZERO
    prototype_share_rmb = ZERO
    prototype_share_usd = ZERO
    testing_share_rmb = ZERO
    testing_share_usd = ZERO
    allocation_fx = (
        positive_value(payload.get("mold_fx_rmb_usd"), "生产模具 RMB→USD 汇率", str(fx_rmb_usd))
        if allocation_enabled
        else fx_rmb_usd
    )
    if allocation_enabled and mold_total_rmb > ZERO:
        amortization_qty = positive_value(payload.get("amortization_qty"), "模具分摊数量", "20000")
        subsidy_usd = decimal_value(payload.get("customer_mold_subsidy_usd"), "客户模费补贴")
        mold_share_rmb = mold_total_rmb / amortization_qty
        mold_share_usd = (mold_total_rmb / allocation_fx - subsidy_usd) / amortization_qty
        if mold_share_usd < ZERO:
            raise CalculationInputError("客户模费补贴不能大于生产模具费用折算 USD 总额")

    prototype_total_usd = decimal_value(payload.get("prototype_total_usd"), "手板费总额") if allocation_enabled else ZERO
    if allocation_enabled and prototype_total_usd > ZERO:
        prototype_qty = positive_value(payload.get("prototype_amortization_qty"), "手板费分摊套数", "50000")
        prototype_share_usd = prototype_total_usd / prototype_qty
        prototype_share_rmb = prototype_share_usd * allocation_fx

    testing_total_usd = decimal_value(payload.get("testing_total_usd"), "测试费总额") if allocation_enabled else ZERO
    if allocation_enabled and testing_total_usd > ZERO:
        testing_qty = positive_value(payload.get("testing_amortization_qty"), "测试费分摊套数", "2000")
        testing_share_usd = testing_total_usd / testing_qty
        testing_share_rmb = testing_share_usd * allocation_fx

    amortization_rmb = mold_share_rmb + prototype_share_rmb + testing_share_rmb
    amortization_usd = mold_share_usd + prototype_share_usd + testing_share_usd
    allocation_lines = (
        ("生产模费分摊", mold_share_rmb, mold_share_usd, "生产模具 RMB 总额 ÷ 套数；USD =（RMB 总额 ÷ RMB→USD 汇率 − 客补贴 USD）÷ 套数"),
        ("手板费分摊", prototype_share_rmb, prototype_share_usd, "手板费总额 USD ÷ 分摊套数；RMB 按生产模具 RMB→USD 汇率反算"),
        ("测试费分摊", testing_share_rmb, testing_share_usd, "测试费总额 USD ÷ 分摊套数；RMB 按生产模具 RMB→USD 汇率反算"),
    )
    for item, share_rmb, share_usd, formula in allocation_lines:
        if share_rmb == ZERO and share_usd == ZERO:
            continue
        result["line_breakdown"].append({
            "kind": "mold_allocation",
            "item": item,
            "amount_rmb": decimal_text(share_rmb),
            "amount_usd": decimal_text(share_usd),
            "amount_hkd": decimal_text(share_rmb / fx),
            "formula": formula,
        })

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
        "mold_quote_total_rmb": decimal_text(mold_quote_total_rmb),
        "mold_quote_total_hkd": decimal_text(mold_quote_total_rmb / fx),
        "mold_total_rmb": decimal_text(mold_total_rmb),
        "mold_fx_rmb_usd": decimal_text(allocation_fx),
        "mold_share_rmb": decimal_text(mold_share_rmb),
        "mold_share_usd": decimal_text(mold_share_usd),
        "prototype_share_rmb": decimal_text(prototype_share_rmb),
        "prototype_share_usd": decimal_text(prototype_share_usd),
        "testing_share_rmb": decimal_text(testing_share_rmb),
        "testing_share_usd": decimal_text(testing_share_usd),
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


def _has_electronic_rmb_rows(rows: Any) -> bool:
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        if "unit_price_rmb" in row or _has_electronic_rmb_rows(row.get("children", [])):
            return True
    return False


def _component_cost_rmb(
    rows: Any,
    path: str,
    fx: Decimal,
    breakdown: list[dict[str, Any]],
) -> tuple[Decimal, Decimal]:
    total_rmb = ZERO
    deductible_input_tax_rmb = ZERO
    for index, row in enumerate(rows or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"{path}第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), f"{path}第 {index + 1} 行用量")
        if "unit_price_rmb" in row:
            unit_price_rmb = decimal_value(row.get("unit_price_rmb"), f"{path}第 {index + 1} 行人民币单价")
        else:
            unit_price_rmb = decimal_value(row.get("unit_price_hkd"), f"{path}第 {index + 1} 行港币单价") * fx
        tax_rate = decimal_value(row.get("tax_rate_percent"), f"{path}第 {index + 1} 行税点", "13")
        if tax_rate > 100:
            raise CalculationInputError(f"{path}第 {index + 1} 行税点不能大于 100%")
        line_rmb = quantity * unit_price_rmb
        line_input_tax_rmb = line_rmb * tax_rate / (100 + tax_rate) if tax_rate else ZERO
        child_rmb, child_input_tax_rmb = _component_cost_rmb(
            row.get("children", []),
            f"{path}第 {index + 1} 行子项",
            fx,
            breakdown,
        )
        total_rmb += line_rmb + child_rmb
        deductible_input_tax_rmb += line_input_tax_rmb + child_input_tax_rmb
        breakdown.append({
            "kind": "electronic_component",
            "item": str(row.get("item", "")),
            "specification": str(row.get("specification", "")),
            "quantity": decimal_text(quantity),
            "unit_price_rmb": decimal_text(unit_price_rmb),
            "unit_price_hkd": decimal_text(unit_price_rmb / fx),
            "tax_rate_percent": decimal_text(tax_rate),
            "amount_rmb": decimal_text(line_rmb),
            "amount_hkd": decimal_text(line_rmb / fx),
            "line_hkd": decimal_text(line_rmb / fx),
            "formula": "用量 × 单价 RMB ÷ 冻结 RMB/HKD 汇率",
            "input_tax_credit_rmb": decimal_text(line_input_tax_rmb),
            "children_rmb": decimal_text(child_rmb),
            "children_hkd": decimal_text(child_rmb / fx),
        })
    return total_rmb, deductible_input_tax_rmb


def _electronic_calculation_rows(payload: dict[str, Any]) -> Any:
    if str(payload.get("quote_mode", "detail")) != "quick":
        return payload.get("components", [])
    quick_rows = payload.get("quick_quotes", [])
    if not isinstance(quick_rows, list):
        return quick_rows
    return [
        {
            **row,
            "specification": "",
            "quantity": "1",
            "children": [],
        }
        if isinstance(row, dict) else row
        for row in quick_rows
    ]


def _electronic(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    calculation_rows = _electronic_calculation_rows(payload)
    uses_rmb_contract = str(payload.get("quote_mode", "detail")) == "quick" or payload.get("pricing_currency") == "RMB" or any(
        field in payload
        for field in ("bonding_rmb", "smt_rmb", "labor_rmb", "testing_rmb", "packaging_rmb")
    ) or _has_electronic_rmb_rows(calculation_rows)
    if uses_rmb_contract:
        fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
        component_rmb, deductible_input_tax_rmb = _component_cost_rmb(
            calculation_rows,
            "电子快捷报价" if str(payload.get("quote_mode", "detail")) == "quick" else "电子零件",
            fx,
            result["line_breakdown"],
        )
        extras_rmb = sum(
            (
                decimal_value(payload.get(rmb_field), label)
                if rmb_field in payload
                else decimal_value(payload.get(hkd_field), label) * fx
                for rmb_field, hkd_field, label in (
                    ("bonding_rmb", "bonding_hkd", "邦定成本"),
                    ("smt_rmb", "smt_hkd", "贴片成本"),
                    ("labor_rmb", "labor_hkd", "电子人工成本"),
                    ("testing_rmb", "testing_hkd", "测试费用"),
                    ("packaging_rmb", "packaging_hkd", "包装运输"),
                )
            ),
            ZERO,
        )
        pre_tax_rmb = component_rmb + extras_rmb
        profit_rate = decimal_value(
            payload.get("profit_rate_percent"),
            "电子利润率",
            str(snapshot.get("electronic_profit_rate_percent", "10")),
        )
        with_profit_rmb = pre_tax_rmb * (1 + profit_rate / 100)
        output_tax_rmb = with_profit_rmb * Decimal("0.13")
        tax_difference_rmb = output_tax_rmb - deductible_input_tax_rmb
        tax_payable_rmb = tax_difference_rmb * Decimal("0.10")
        total_rmb = with_profit_rmb + tax_difference_rmb + tax_payable_rmb
        total_hkd = total_rmb / fx
        result["currency_totals"] = {
            "HKD": decimal_text(total_hkd),
            "RMB": decimal_text(total_rmb),
            "USD": "0.0000",
        }
        result["totals"] = {
            "component_rmb": decimal_text(component_rmb),
            "component_hkd": decimal_text(component_rmb / fx),
            "extras_rmb": decimal_text(extras_rmb),
            "pre_tax_rmb": decimal_text(pre_tax_rmb),
            "pre_tax_hkd": decimal_text(pre_tax_rmb / fx),
            "with_profit_rmb": decimal_text(with_profit_rmb),
            "with_profit_hkd": decimal_text(with_profit_rmb / fx),
            "deductible_input_tax_rmb": decimal_text(deductible_input_tax_rmb),
            "output_tax_rmb": decimal_text(output_tax_rmb),
            "tax_credit_difference_rmb": decimal_text(tax_difference_rmb),
            "tax_credit_difference_hkd": decimal_text(tax_difference_rmb / fx),
            "tax_payable_rmb": decimal_text(tax_payable_rmb),
            "tax_payable_hkd": decimal_text(tax_payable_rmb / fx),
            "total_rmb": decimal_text(total_rmb),
            "total_hkd": decimal_text(total_hkd),
        }
        return

    component = _component_cost(calculation_rows, "电子零件", result["line_breakdown"])
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
            str(payload.get("injection_loss_rate_percent", snapshot.get("injection_loss_rate_percent", "3"))),
        )
        sets = positive_value(row.get("sets"), "套数")
        target_output = positive_value(row.get("target_output"), "目标数")
        quantity = decimal_value(row.get("quantity"), "成品用量", "1")
        material_cost = net_weight * (1 + loss_rate / 100) * material_price / 454
        molding_cost = machine_price / sets / target_output
        unit_total = material_cost + molding_cost
        line_total = unit_total * quantity
        injection_total += line_total
        result["line_breakdown"].append({
            "kind": "injection",
            "item": str(row.get("item", "")),
            "mold_no": str(row.get("mold_no", "")),
            "material": material,
            "grade": grade,
            "color": str(row.get("color", "")),
            "loss_rate_percent": decimal_text(loss_rate),
            "loss_weight_g": decimal_text(net_weight * (1 + loss_rate / 100)),
            "material_price_hkd_lb": decimal_text(material_price),
            "material_price_hkd_g": decimal_text(material_price / 454),
            "machine_shift_price_hkd": decimal_text(machine_price),
            "machine_name": str(row.get("machine_name", "")),
            "machine_code": machine_code,
            "cavity": str(row.get("cavity", "")),
            "sets": decimal_text(sets),
            "target_output": decimal_text(target_output),
            "material_cost_hkd": decimal_text(material_cost),
            "molding_cost_hkd": decimal_text(molding_cost),
            "unit_amount_hkd": decimal_text(unit_total),
            "quantity": decimal_text(quantity),
            "amount_hkd": decimal_text(line_total),
            "formula": "啤净重 × (1 + 损耗%) × 冻结材料价 HKD/lb ÷ 454 + 冻结机型台班价 ÷ 套数 ÷ 目标数",
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
        subtotal = material_cost + labor + burr
        unit_total = subtotal * multiplier
        line_total = unit_total * quantity
        blow_total += line_total
        result["line_breakdown"].append({
            "kind": "blow",
            "item": str(row.get("item", "")),
            "daily_capacity": str(row.get("daily_capacity", "")),
            "material": material,
            "grade": grade,
            "material_price_hkd_lb": decimal_text(material_price),
            "material_cost_hkd": decimal_text(material_cost),
            "labor_hkd": decimal_text(labor),
            "burr_hkd": decimal_text(burr),
            "subtotal_hkd": decimal_text(subtotal),
            "profit_multiplier": decimal_text(multiplier),
            "unit_amount_hkd": decimal_text(unit_total),
            "quantity": decimal_text(quantity),
            "amount_hkd": decimal_text(line_total),
            "formula": "(预估料重 × 冻结材料价 HKD/lb ÷ 454 + 吹工 + 披锋) × 利润倍率",
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
    if str(payload.get("quote_mode", "detail")) == "quick":
        quick = payload.get("quick_quote", {}) or {}
        if not isinstance(quick, dict):
            raise CalculationInputError("喷油快捷报价格式无效")
        spray_labor = decimal_value(quick.get("spray_labor_hkd"), "喷油工快捷报价")
        paint_base = decimal_value(quick.get("paint_hkd"), "油漆快捷报价")
        paint_tax_rate = Decimal("13")
        paint_tax = paint_base * paint_tax_rate / Decimal("100")
        paint_with_tax = paint_base + paint_tax
        total = spray_labor + paint_with_tax
        result["line_breakdown"].extend((
            {
                "kind": "painting_quick_labor",
                "item": "喷油工",
                "formula": "快捷报价：喷油工 HKD",
                "amount_hkd": decimal_text(spray_labor),
            },
            {
                "kind": "painting_quick_paint",
                "item": "油漆",
                "formula": "快捷报价：油漆 HKD",
                "amount_hkd": decimal_text(paint_base),
            },
            {
                "kind": "painting_quick_paint_tax",
                "item": "油漆税金 13%",
                "formula": "油漆 HKD × 13%",
                "amount_hkd": decimal_text(paint_tax),
            },
        ))
        if total <= ZERO:
            result["warnings"].append(_warning("painting_quick_quote_empty", "喷油快捷报价合计必须大于 0"))
        result["currency_totals"]["HKD"] = decimal_text(total)
        result["totals"] = {
            "quote_mode": "quick",
            "painting_labor_hkd": decimal_text(spray_labor),
            "paint_base_hkd": decimal_text(paint_base),
            "paint_tax_hkd": decimal_text(paint_tax),
            "paint_material_hkd": decimal_text(paint_with_tax),
            "total_hkd": decimal_text(total),
        }
        return
    operation_names = ("clamp", "pad_print", "spray", "edge", "paint", "dip", "wipe", "pp_water")
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
        name = str(row.get("name") or row.get("item") or "")
        position = str(row.get("position") or "")
        result["line_breakdown"].append({
            "kind": "painting",
            "item": position or name,
            "name": name,
            "position": position,
            "image_reference": str(row.get("image_reference") or ""),
            "remark": str(row.get("remark") or row.get("note") or ""),
            "operations": operation_breakdown,
            "amount_hkd": decimal_text(line_total),
        })
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {"total_hkd": decimal_text(total)}


def _slush(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
    total = ZERO
    for index, row in enumerate(payload.get("lines", []) or []):
        if not isinstance(row, dict):
            raise CalculationInputError(f"搪胶第 {index + 1} 行格式无效")
        quantity = decimal_value(row.get("quantity"), "搪胶用量")
        unit_price = decimal_value(row.get("unit_price_hkd"), "搪胶单价")
        weight_g = decimal_value(row.get("weight_g"), "搪胶料重")
        daily_output = decimal_value(row.get("daily_output_24h"), "搪胶日产量")
        line_total = quantity * unit_price
        total += line_total
        result["line_breakdown"].append({
            "kind": "slush",
            "product_code": str(row.get("product_code", "")),
            "item": str(row.get("item", "")),
            "material": str(row.get("material", "")),
            "weight_g": decimal_text(weight_g),
            "daily_output_24h": decimal_text(daily_output),
            "quantity": decimal_text(quantity),
            "unit_price_hkd": decimal_text(unit_price),
            "remark": str(row.get("remark", "")),
            "formula": "quantity * unit_price_hkd",
            "amount_hkd": decimal_text(line_total),
        })
    total_rmb = total * fx
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["currency_totals"]["RMB"] = decimal_text(total_rmb)
    result["totals"] = {"total_hkd": decimal_text(total), "total_rmb": decimal_text(total_rmb)}


def _sewing(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
    if str(payload.get("quote_mode", "detail")) == "quick":
        quick_quotes = payload.get("quick_quotes", []) or []
        if not isinstance(quick_quotes, list):
            raise CalculationInputError("车缝快捷报价格式无效")
        total_hkd = ZERO
        for index, row in enumerate(quick_quotes):
            if not isinstance(row, dict):
                raise CalculationInputError(f"车缝快捷报价第 {index + 1} 行格式无效")
            doll_name = str(row.get("doll_name", "")).strip()
            unit_price_hkd = decimal_value(row.get("unit_price_hkd"), f"车缝快捷报价第 {index + 1} 行公仔价钱")
            if not doll_name or unit_price_hkd <= ZERO:
                result["warnings"].append(
                    _warning(
                        "sewing_quick_quote_incomplete",
                        f"车缝快捷报价第 {index + 1} 行须填写公仔名称且价钱大于 0",
                    )
                )
            total_hkd += unit_price_hkd
            result["line_breakdown"].append({
                "kind": "sewing_quick",
                "item": doll_name or f"公仔 {index + 1}",
                "category": "clothes",
                "formula": "快捷报价：单个公仔 HKD",
                "amount_hkd": decimal_text(unit_price_hkd),
            })
        if not quick_quotes:
            result["warnings"].append(_warning("sewing_quick_quote_empty", "车缝快捷报价至少需要一个公仔"))
        total_rmb = total_hkd * fx
        result["currency_totals"] = {"HKD": decimal_text(total_hkd), "RMB": decimal_text(total_rmb), "USD": "0.0000"}
        result["totals"] = {
            "quote_mode": "quick",
            "clothes_rmb": decimal_text(total_rmb),
            "hair_rmb": "0.0000",
            "clothes_hkd": decimal_text(total_hkd),
            "hair_hkd": "0.0000",
            "total_rmb": decimal_text(total_rmb),
            "total_hkd": decimal_text(total_hkd),
        }
        return
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
            part = str(row.get("part", ""))
            contains_labor_line = contains_labor_line or "人工" in f"{item}{part}"
            pieces = decimal_value(row.get("pieces"), "车缝裁片数")
            usage = decimal_value(row.get("usage"), "车缝用量")
            unit_price = decimal_value(row.get("unit_price_rmb"), "车缝物料价")
            markup = decimal_value(row.get("markup"), "车缝码点", "1")
            if markup <= ZERO:
                markup = Decimal("1")
            price_rmb = usage * unit_price
            line_total = price_rmb * markup
            group_total += line_total
            result["line_breakdown"].append({
                "kind": "sewing_material",
                "group": str(group.get("name", "")),
                "category": category,
                "item": item,
                "part": part,
                "craft": str(row.get("craft", "")),
                "pieces": decimal_text(pieces),
                "usage": decimal_text(usage),
                "unit_price_rmb": decimal_text(unit_price),
                "price_rmb": decimal_text(price_rmb),
                "markup": decimal_text(markup),
                "remark": str(row.get("remark") or row.get("note") or ""),
                "source_row": row.get("source_row", ""),
                "formula": "usage * unit_price_rmb * markup",
                "amount_rmb": decimal_text(line_total),
            })
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
        "total_rmb": decimal_text(total_rmb),
        "total_hkd": decimal_text(total_hkd),
    }


def _assembly(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any]) -> None:
    labor_base = decimal_value(
        payload.get("labor_base_hkd"),
        "装配人工基数",
        str(snapshot.get("assembly_labor_base_hkd", "260")),
    )
    standard_work_hours = positive_value(
        payload.get("standard_work_hours"),
        "装配标准工时",
        str(snapshot.get("assembly_standard_work_hours", "11")),
    )
    category_total = {"assembly": ZERO, "packaging": ZERO}
    result["group_summaries"] = []
    for group_index, group in enumerate(payload.get("groups", []) or []):
        if not isinstance(group, dict):
            raise CalculationInputError(f"装配产品组第 {group_index + 1} 组格式无效")
        category = str(group.get("category", "assembly"))
        if category not in category_total:
            raise CalculationInputError(f"装配产品组第 {group_index + 1} 组分类无效")
        processes = group.get("processes", []) or []
        first_process = processes[0] if processes and isinstance(processes[0], dict) else {}
        uses_group_inputs = group.get("teams") not in (None, "") or group.get("production_qty") not in (None, "")
        group_teams = positive_value(group.get("teams", first_process.get("teams")), "装配小组数", "1")
        group_production_qty = positive_value(
            group.get("production_qty", first_process.get("production_qty")),
            "装配生产量",
        )
        group_total = ZERO
        total_persons = ZERO
        for process_index, process in enumerate(processes):
            if not isinstance(process, dict):
                raise CalculationInputError(f"装配第 {group_index + 1} 组工序 {process_index + 1} 格式无效")
            persons = decimal_value(process.get("persons"), "装配人数")
            total_persons += persons
            teams = group_teams if uses_group_inputs else positive_value(process.get("teams"), "装配小组数", str(group_teams))
            production_qty = group_production_qty if uses_group_inputs else positive_value(process.get("production_qty"), "装配生产量", str(group_production_qty))
            process_total = labor_base * persons * teams / production_qty
            group_total += process_total
            result["line_breakdown"].append({
                "kind": "assembly_process",
                "group": str(group.get("name", "")),
                "category": category,
                "process": str(process.get("name", "")),
                "persons": decimal_text(persons),
                "teams": decimal_text(teams),
                "production_qty": decimal_text(production_qty),
                "remark": str(process.get("remark", process.get("note", ""))),
                "formula": "人工基数 × 人数 × 小组数 ÷ 生产量",
                "amount_hkd_pcs": decimal_text(process_total),
            })
        result["group_summaries"].append({
            "category": category,
            "group": str(group.get("name", "")),
            "standard_work_hours": decimal_text(standard_work_hours),
            "labor_base_hkd": decimal_text(labor_base),
            "production_qty": decimal_text(group_production_qty),
            "teams": decimal_text(group_teams),
            "total_persons": decimal_text(total_persons),
            "amount_hkd_pcs": decimal_text(group_total),
            "formula": "人工基数 × 总人数 × 小组数 ÷ 生产量",
        })
        category_total[category] += group_total
    total = sum(category_total.values(), ZERO)
    result["currency_totals"]["HKD"] = decimal_text(total)
    result["totals"] = {
        "assembly_hkd": decimal_text(category_total["assembly"]),
        "packaging_hkd": decimal_text(category_total["packaging"]),
        "total_hkd": decimal_text(total),
    }


def _sales_packaging(
    payload: dict[str, Any],
    snapshot: dict[str, Any],
    result: dict[str, Any],
) -> tuple[Decimal, Decimal]:
    cartons = payload.get("cartons", []) or []
    if not cartons:
        return ZERO, ZERO

    for field, legacy_field, label in (
        ("product_size_in", "product_size_cm", "产品尺寸"),
        ("color_box_size_in", "color_box_size_cm", "彩盒尺寸"),
    ):
        dimensions = payload.get(field)
        if dimensions is None:
            dimensions = payload.get(legacy_field, {})
        dimensions = dimensions or {}
        if not isinstance(dimensions, dict):
            raise CalculationInputError(f"{label}格式无效")
        dimension_values = {
            "长度": decimal_value(dimensions.get("length"), f"{label}长度"),
            "宽度": decimal_value(dimensions.get("width"), f"{label}宽度"),
            "高度": decimal_value(dimensions.get("height"), f"{label}高度"),
        }
        # 产品和彩盒尺寸按 inch 留存，只作为业务资料，不参与纸箱成本公式。
        # `_cm` 是历史误命名别名；其既有数值同样按 inch 读取，不做二次换算。
        # 整组未填写（前端序列化为 0）时允许继续计算；一旦开始填写，三项必须完整。
        if any(value > ZERO for value in dimension_values.values()):
            for dimension_label, value in dimension_values.items():
                if value <= ZERO:
                    raise CalculationInputError(f"{label}{dimension_label} 必须大于 0")

    paper_factor = positive_value(
        payload.get("paper_price_factor"),
        "纸价系数",
        str(snapshot.get("paper_price_factor", "2.75")),
    )
    flat_card_factor = positive_value(
        payload.get("flat_card_price_factor"),
        "平卡纸价系数",
        str(paper_factor),
    )
    carton_total_hkd = ZERO
    carton_cuft = ZERO
    for index, row in enumerate(cartons):
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
            flat_length = positive_value(flat.get("length_in"), f"平卡第 {flat_index + 1} 行长度")
            flat_width = positive_value(flat.get("width_in"), f"平卡第 {flat_index + 1} 行宽度")
            flat_qty = decimal_value(flat.get("quantity"), f"平卡第 {flat_index + 1} 行数量", "1")
            flat_total += (flat_length + 1) * (flat_width + 1) * 2 * flat_card_factor / 1000 * flat_qty
        per_piece = (carton_price + flat_total) / qty_per_carton
        cuft = length * width * height / 1728
        carton_total_hkd += per_piece
        carton_cuft += cuft
        result["line_breakdown"].append({
            "kind": "carton",
            "owner": "sales",
            "item": str(row.get("item", "")),
            "paper_price_factor": decimal_text(paper_factor),
            "flat_card_price_factor": decimal_text(flat_card_factor),
            "carton_price_hkd": decimal_text(carton_price),
            "flat_card_price_hkd": decimal_text(flat_total),
            "per_piece_hkd": decimal_text(per_piece),
            "cuft": decimal_text(cuft),
            "qty_per_carton": decimal_text(qty_per_carton),
        })
    return carton_total_hkd, carton_cuft


def _sales_packaging_materials(
    payload: dict[str, Any],
    snapshot: dict[str, Any],
    result: dict[str, Any],
) -> tuple[Decimal, Decimal]:
    rows = payload.get("packaging_materials", []) or []
    if not rows:
        return ZERO, ZERO

    fx = positive_value(snapshot.get("fx", {}).get("rmb_hkd"), "RMB/HKD 汇率")
    allowed_categories = {
        "blister",
        "color_box_inner_card",
        "leaflet_manual",
        "other_purchase",
    }
    total_rmb = ZERO
    total_hkd = ZERO
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise CalculationInputError(f"包装材料第 {index + 1} 行格式无效")
        item = str(row.get("item", "")).strip()
        if not item:
            raise CalculationInputError(f"包装材料第 {index + 1} 行零件名称不能为空")
        category = str(row.get("category", "")).strip()
        if category not in allowed_categories:
            raise CalculationInputError(f"包装材料第 {index + 1} 行类别无效")
        quantity = decimal_value(row.get("quantity"), f"包装材料第 {index + 1} 行用量")
        unit_price_rmb = decimal_value(row.get("unit_price_rmb"), f"包装材料第 {index + 1} 行人民币单价")
        tax_rate = decimal_value(row.get("tax_rate_percent"), f"包装材料第 {index + 1} 行税点")
        if tax_rate > Decimal("100"):
            raise CalculationInputError(f"包装材料第 {index + 1} 行税点不能大于 100%")
        unit_price_hkd = unit_price_rmb / fx
        amount_rmb = quantity * unit_price_rmb
        amount_hkd = quantity * unit_price_hkd
        total_rmb += amount_rmb
        total_hkd += amount_hkd
        result["line_breakdown"].append({
            "kind": "packaging_material",
            "owner": "sales",
            "item": item,
            "specification": str(row.get("specification", "")),
            "category": category,
            "quantity": decimal_text(quantity),
            "unit_price_rmb": decimal_text(unit_price_rmb),
            "unit_price_hkd": decimal_text(unit_price_hkd),
            "tax_rate_percent": decimal_text(tax_rate),
            "amount_rmb": decimal_text(amount_rmb),
            "amount_hkd": decimal_text(amount_hkd),
            "remark": str(row.get("remark", "")),
        })
    return total_hkd, total_rmb


def _sales_freight_options(
    payload: dict[str, Any],
    snapshot: dict[str, Any],
    result: dict[str, Any],
) -> list[dict[str, Any]]:
    freight_source = payload.get("freight_calc")
    if freight_source is None:
        return []
    if not isinstance(freight_source, dict):
        raise CalculationInputError("运费与吊柜费计算格式无效")
    freight_enabled = freight_source.get("enabled", True)
    if not isinstance(freight_enabled, bool):
        raise CalculationInputError("是否启用运费与吊柜费计算必须为布尔值")
    if not freight_enabled:
        return []
    cartons = payload.get("cartons", []) or []
    if not cartons:
        return []
    primary_carton = cartons[0]
    if not isinstance(primary_carton, dict):
        raise CalculationInputError("主纸箱格式无效")
    length = positive_value(primary_carton.get("length_in"), "主纸箱长度")
    width = positive_value(primary_carton.get("width_in"), "主纸箱宽度")
    height = positive_value(primary_carton.get("height_in"), "主纸箱高度")
    qty_per_carton = positive_value(primary_carton.get("qty_per_carton"), "主纸箱每箱数量")
    carton_cuft = length * width * height / Decimal("1728")

    snapshot_freight = snapshot.get("freight", {})
    if not isinstance(snapshot_freight, dict):
        snapshot_freight = {}
    capacity_defaults = snapshot_freight.get("capacity_cuft", {})
    cost_defaults = snapshot_freight.get("cost_hkd", {})
    if not isinstance(capacity_defaults, dict):
        capacity_defaults = {}
    if not isinstance(cost_defaults, dict):
        cost_defaults = {}

    route_rows = snapshot_freight.get("routes")
    if not isinstance(route_rows, list) or not route_rows:
        route_rows = [
            {
                "route_key": route_key,
                "route_name": label,
                "capacity_key": capacity_key,
                "freight_hkd": cost_defaults.get(
                    default_cost_key,
                    DEFAULT_FREIGHT["cost_hkd"][default_cost_key],
                ),
            }
            for route_key, label, capacity_key, _default_capacity_key, default_cost_key
            in FREIGHT_ROUTE_DEFINITIONS
        ]

    options: list[dict[str, Any]] = []
    for row in route_rows:
        if not isinstance(row, dict):
            continue
        route_key = str(row.get("route_key", "")).strip()
        label = str(row.get("route_name", "")).strip()
        capacity_key = str(row.get("capacity_key", "")).strip()
        default_capacity_key = FREIGHT_CAPACITY_DEFAULT_KEYS.get(capacity_key)
        if not route_key or not label or default_capacity_key is None:
            continue
        capacity_default = capacity_defaults.get(
            default_capacity_key,
            DEFAULT_FREIGHT["capacity_cuft"][default_capacity_key],
        )
        cost_default = row.get("freight_hkd", "0")
        has_lifting_fee = "lifting_hkd" in row
        lifting_default = row.get("lifting_hkd", "0")
        capacity_cuft = positive_value(
            freight_source.get(capacity_key),
            f"{label}容量",
            str(capacity_default),
        )
        if capacity_cuft != capacity_cuft.to_integral_value():
            raise CalculationInputError(f"{label}容量必须为整数")
        freight_cost_hkd = decimal_value(
            freight_source.get(route_key),
            f"{label}运费",
            str(cost_default),
        )
        lifting_cost_hkd = decimal_value(
            lifting_default,
            f"{label}吊柜费",
        )
        if freight_cost_hkd < ZERO:
            raise CalculationInputError(f"{label}运费不能小于 0")
        if lifting_cost_hkd < ZERO:
            raise CalculationInputError(f"{label}吊柜费不能小于 0")
        total_cartons = max(
            (capacity_cuft / carton_cuft).quantize(Decimal("1"), rounding=ROUND_HALF_UP),
            Decimal("1"),
        )
        freight_per_piece_hkd = freight_cost_hkd / total_cartons / qty_per_carton
        lifting_per_piece_hkd = lifting_cost_hkd / total_cartons / qty_per_carton
        per_piece_hkd = freight_per_piece_hkd + lifting_per_piece_hkd
        option = {
            "kind": "freight_reference",
            "reference_only": True,
            "item": label,
            "route_key": route_key,
            "carton_item": str(primary_carton.get("item", "")),
            "capacity_cuft": format(capacity_cuft, "f"),
            "carton_cuft": decimal_text(carton_cuft),
            "qty_per_carton": decimal_text(qty_per_carton),
            "freight_cost_hkd": decimal_text(freight_cost_hkd),
            "lifting_cost_hkd": decimal_text(lifting_cost_hkd),
            "has_lifting_fee": has_lifting_fee,
            "total_cartons": decimal_text(total_cartons),
            "freight_per_piece_hkd": decimal_text(freight_per_piece_hkd),
            "lifting_per_piece_hkd": decimal_text(lifting_per_piece_hkd),
            "per_piece_hkd": decimal_text(per_piece_hkd),
            "formula": "（运费 + 吊柜费）分别 ÷ ROUND(柜/车容量 ÷ 主纸箱 CUFT) ÷ 每箱数量",
        }
        options.append(option)
        result["line_breakdown"].append(option)
    return options


def _sales(payload: dict[str, Any], snapshot: dict[str, Any], result: dict[str, Any], context: dict[str, Any]) -> None:
    base_factory_price = decimal_value(context.get("factory_price_hkd"), "出厂价")
    shipping_source = payload.get("shipping", {})
    if shipping_source in (None, ""):
        shipping_source = {}
    elif not isinstance(shipping_source, dict):
        raise CalculationInputError("业务报价系数格式无效")
    if "markup_x" in shipping_source:
        markup_x = decimal_value(shipping_source.get("markup_x"), "当前码数")
        if markup_x < Decimal("0.01") or markup_x > Decimal("9.99"):
            raise CalculationInputError("当前码数必须在 0.01 至 9.99 之间")
    markup_tiers = shipping_source.get("markup_tiers")
    tier_moqs: list[Decimal] = []
    if markup_tiers is not None:
        if not isinstance(markup_tiers, list) or not 1 <= len(markup_tiers) <= 10:
            raise CalculationInputError("分段码数必须包含 1 至 10 个 MOQ 档位")
        previous_moq = ZERO
        for index, tier in enumerate(markup_tiers):
            if not isinstance(tier, dict):
                raise CalculationInputError(f"分段码数第 {index + 1} 档格式无效")
            moq = decimal_value(tier.get("moq"), f"分段码数第 {index + 1} 档 MOQ")
            markup_x = decimal_value(tier.get("markup_x"), f"分段码数第 {index + 1} 档码数")
            if moq <= 0 or moq != moq.to_integral_value():
                raise CalculationInputError(f"分段码数第 {index + 1} 档 MOQ 必须是正整数")
            if moq <= previous_moq:
                raise CalculationInputError("分段码数 MOQ 必须由小到大排列，且不能重复")
            if markup_x < Decimal("0.01") or markup_x > Decimal("9.99"):
                raise CalculationInputError(f"分段码数第 {index + 1} 档码数必须在 0.01 至 9.99 之间")
            previous_moq = moq
            tier_moqs.append(moq)
    if "selected_markup_moq" in shipping_source:
        selected_moq = decimal_value(shipping_source.get("selected_markup_moq"), "本单采用 MOQ")
        if selected_moq not in tier_moqs:
            raise CalculationInputError("本单采用的 MOQ 必须来自分段码数档位")
    misc_ratio = decimal_value(shipping_source.get("misc_ratio"), "杂项系数", str(snapshot.get("misc_ratio", "0.02")))
    if misc_ratio < 0 or misc_ratio > 1:
        raise CalculationInputError("杂项系数必须在 0% 至 100% 之间")
    testing_fee_total_usd = decimal_value(payload.get("testing_fee_total_usd"), "业务部测试费用 USD")
    if testing_fee_total_usd < ZERO:
        raise CalculationInputError("业务部测试费用 USD 不能小于 0")
    testing_fee_moq_sources = payload.get("testing_fee_moqs")
    if testing_fee_moq_sources is None:
        legacy_testing_fee_moq = payload.get("testing_fee_moq")
        testing_fee_moq_sources = [] if legacy_testing_fee_moq in (None, "") else [legacy_testing_fee_moq]
    if not isinstance(testing_fee_moq_sources, list):
        raise CalculationInputError("业务部测试费 MOQ 档位格式无效")
    testing_fee_tiers: list[dict[str, str]] = []
    seen_testing_fee_moqs: set[Decimal] = set()
    for index, source in enumerate(testing_fee_moq_sources):
        moq = decimal_value(source, f"业务部测试费第 {index + 1} 档 MOQ")
        if moq < ZERO or moq != moq.to_integral_value():
            raise CalculationInputError(f"业务部测试费第 {index + 1} 档 MOQ 必须是正整数")
        if testing_fee_total_usd > ZERO and moq <= ZERO:
            raise CalculationInputError(f"填写业务部测试费用 USD 后，第 {index + 1} 档 MOQ 必须大于 0")
        if moq <= ZERO:
            continue
        if moq in seen_testing_fee_moqs:
            raise CalculationInputError("业务部测试费 MOQ 不能重复")
        seen_testing_fee_moqs.add(moq)
        testing_fee_tiers.append({
            "moq": decimal_text(moq),
            "unit_price_usd": decimal_text(testing_fee_total_usd / moq),
        })
    if testing_fee_total_usd > ZERO and not testing_fee_tiers:
        raise CalculationInputError("填写业务部测试费用 USD 后，至少需要一个大于 0 的 MOQ")
    primary_testing_fee_tier = testing_fee_tiers[0] if testing_fee_tiers else {
        "moq": decimal_text(ZERO),
        "unit_price_usd": decimal_text(ZERO),
    }
    testing_fee_moq = Decimal(primary_testing_fee_tier["moq"])
    testing_fee_unit_usd = Decimal(primary_testing_fee_tier["unit_price_usd"])
    if testing_fee_total_usd > ZERO:
        result["line_breakdown"].append({
            "kind": "sales_testing_fee",
            "owner": "sales",
            "item": "测试费",
            "total_usd": decimal_text(testing_fee_total_usd),
            "moq": decimal_text(testing_fee_moq),
            "unit_price_usd": decimal_text(testing_fee_unit_usd),
            "tiers": testing_fee_tiers,
            "formula": "测试费用 USD ÷ MOQ 数量",
            "reference_only": True,
        })
    packaging_material_total_hkd, packaging_material_total_rmb = _sales_packaging_materials(payload, snapshot, result)
    carton_total_hkd, carton_cuft = _sales_packaging(payload, snapshot, result)
    freight_options = _sales_freight_options(payload, snapshot, result)
    sales_total_hkd = packaging_material_total_hkd + carton_total_hkd
    factory_price = base_factory_price + sales_total_hkd
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
    result["currency_totals"]["HKD"] = decimal_text(sales_total_hkd)
    result["currency_totals"]["RMB"] = decimal_text(packaging_material_total_rmb)
    result["currency_totals"]["USD"] = decimal_text(testing_fee_unit_usd)
    result["totals"] = {
        "base_factory_price_hkd": decimal_text(base_factory_price),
        "factory_price_hkd": decimal_text(factory_price),
        "packaging_material_hkd": decimal_text(packaging_material_total_hkd),
        "packaging_material_rmb": decimal_text(packaging_material_total_rmb),
        "carton_hkd": decimal_text(carton_total_hkd),
        "carton_cuft": decimal_text(carton_cuft),
        "testing_fee_total_usd": decimal_text(testing_fee_total_usd),
        "testing_fee_moqs": [tier["moq"] for tier in testing_fee_tiers],
        "testing_fee_tiers": testing_fee_tiers,
        "testing_fee_moq": decimal_text(testing_fee_moq),
        "testing_fee_unit_usd": decimal_text(testing_fee_unit_usd),
        "freight_options": freight_options,
        "indonesia_freight_hkd": decimal_text(indonesia_freight),
        "additional_tax_hkd": decimal_text(additional_tax),
        "misc_ratio": decimal_text(misc_ratio),
        "shipping_floor_hkd": decimal_text(shipping_floor),
        "tax_deduction_hkd": decimal_text(tax_deduction),
        "after_tax_cost_hkd": decimal_text(max(factory_price - tax_deduction, ZERO)),
        "scenarios": scenario_results,
        "total_hkd": decimal_text(sales_total_hkd),
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
            "bonding_rmb",
            "smt_rmb",
            "labor_rmb",
            "testing_rmb",
            "packaging_rmb",
            "bonding_hkd",
            "smt_hkd",
            "labor_hkd",
            "testing_hkd",
            "packaging_hkd",
            "tax_credit_difference_hkd",
        ),
        "molding": ("injection_lines", "blow_lines", "caixing_tool_plan_rows"),
        "painting": ("rows", "quick_quote"),
        "slush": ("lines",),
        "sewing": ("groups", "quick_quotes"),
        "assembly": ("groups",),
    }
    fields = meaningful_fields.get(section_code)
    if payload and fields and not any(payload.get(field) for field in fields):
        result["warnings"].append(
            _warning("no_calculation_lines", "当前分段没有符合字段契约的可计算明细")
        )
    if (
        section_code == "sales"
        and any(field in payload for field in ("paper_price_factor", "packaging_materials", "product_size_in", "color_box_size_in", "product_size_cm", "color_box_size_cm", "cartons"))
        and not payload.get("cartons")
    ):
        result["warnings"].append(
            _warning("sales_carton_missing", "业务分段尚未填写纸箱与每箱数量")
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
        _slush(payload, snapshot, result)
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
