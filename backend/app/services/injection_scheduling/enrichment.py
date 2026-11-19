from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import Demand, MoldMaster, Run, RunDemand

from .calculations import decimal, quantities, shots_for_units, timestamp
from .common import record, touch
from .field_registry import FIELDS
from .requirement_parser import normalize_code

PROCESS_KEYS = (
    "required_machine_a",
    "target_shots_per_day",
    "net_weight_g",
    "gross_weight_g",
    "price_per_shot",
    "material_raw",
    "resin",
    "material_grade",
    "color_name",
    "colorant_code",
    "effective_outputs_per_shot",
)
STATES = {"READY", "PAUSED", "WAIT_NOTICE", "MOLD_REPAIR", "WAIT_MATERIAL", "COMPLETED"}


def validate_requirements(value):
    if not isinstance(value, dict):
        raise HTTPException(422, "适机限制必须为对象")
    allowed = {
        "raw",
        "required_machine_a",
        "machine_family",
        "speed_class",
        "preferred_speed_class",
        "required_capabilities",
        "forbidden_machine_codes",
        "uncertain_qualifiers",
        "manipulator_requirement",
        "fixture_requirement",
    }
    if set(value) - allowed:
        raise HTTPException(422, "适机限制包含不支持的条件")
    if value.get("machine_family") not in (None, "HORIZONTAL", "VERTICAL", "TWO_COLOR"):
        raise HTTPException(422, "专用机型不正确")
    for key in (
        "required_capabilities",
        "forbidden_machine_codes",
        "uncertain_qualifiers",
    ):
        if key in value and (
            not isinstance(value[key], list)
            or len(value[key]) > 100
            or any(not isinstance(item, str) or len(item) > 200 for item in value[key])
        ):
            raise HTTPException(422, f"{key} 必须为文字列表")
    for key in ("speed_class", "preferred_speed_class"):
        if value.get(key) not in (None, "NORMAL", "HIGH_SPEED", "ELECTRIC"):
            raise HTTPException(422, "速度等级不正确")
    for key in ("raw", "manipulator_requirement", "fixture_requirement"):
        if key in value and value[key] is not None and not isinstance(value[key], str):
            raise HTTPException(422, f"{key} 必须为文字")
    return value


def match_mold(db, code):
    normalized = normalize_code(code)
    exact = db.scalar(
        select(MoldMaster).where(MoldMaster.normalized_code == normalized)
    )
    if exact:
        return exact
    matches = [
        m
        for m in db.scalars(select(MoldMaster))
        if normalized in [normalize_code(a) for a in m.alias_codes]
    ]
    if len(matches) > 1:
        raise HTTPException(409, "模具别名存在多个匹配，请选择准确模号")
    return matches[0] if matches else None


def update_quantities(demand, reported=0, good_units=0):
    values = quantities(record(demand), reported, good_units)
    changed = False
    for key, value in values.items():
        if hasattr(Demand, key):
            changed = changed or getattr(demand, key) != value
            setattr(demand, key, value)
    if changed:
        demand.revision = (demand.revision or 0) + 1
    return values


def enrich(db, demand, *, apply_latest=False):
    master = match_mold(db, demand.mold_code)
    if not master:
        return
    demand.mold_master_id = master.id
    sources = dict(demand.field_sources or {})
    defaults = {**master.defaults, "required_machine_a": master.required_machine_a}
    for key in PROCESS_KEYS:
        if defaults.get(key) is None:
            continue
        current = getattr(demand, key)
        source = sources.get(key, {}).get("kind")
        if (
            current is None
            or current == ""
            or apply_latest
            and source in {"MASTER", "LEGACY_CACHE"}
        ):
            setattr(demand, key, defaults[key])
            sources[key] = {
                "kind": "MASTER",
                "mold_id": master.id,
                "revision": master.revision,
            }
    if not demand.requirements_snapshot or apply_latest:
        # Explicit constraints on an order remain authoritative when applying defaults.
        demand.requirements_snapshot = {
            **master.requirements,
            **(demand.requirements_snapshot or {}),
        }
    demand.field_sources = sources


def validate_fields(data, *, imported=False):
    clean = {}
    for key, value in data.items():
        if key not in FIELDS or not FIELDS[key].editable:
            raise HTTPException(422, f"字段不可编辑：{key}")
        spec = FIELDS[key]
        if value == "":
            value = None
        if value is None:
            if key in {
                "mold_code",
                "dispatch_state",
                "allocation_mode",
                "target_basis_hours",
                "allowance_rate",
                "adjustment_shots",
                "priority_level",
                "pieces_per_set",
                "effective_outputs_per_shot",
                "downstream_lead_days",
                "weight_basis",
            }:
                raise HTTPException(422, f"{spec.label} 不能为空")
            clean[key] = None
            continue
        if spec.value_type in {"number", "integer"}:
            number = decimal(value)
            if number is None or abs(number) >= 1e14:
                raise HTTPException(422, f"{spec.label} 必须是有效数字")
            if key != "adjustment_shots" and number < 0:
                raise HTTPException(422, f"{spec.label} 不能为负数")
            if (
                key
                in {
                    "target_basis_hours",
                    "effective_outputs_per_shot",
                    "pieces_per_set",
                }
                and number <= 0
            ):
                raise HTTPException(422, f"{spec.label} 必须大于零")
            if key == "required_machine_a" and number <= 0:
                raise HTTPException(
                    422, "模具机安必须大于零；专用机型可留空并填写适机限制"
                )
            if (
                spec.value_type == "integer" or key == "planned_shots" and not imported
            ) and number % 1:
                raise HTTPException(422, f"{spec.label} 必须为整数")
            if key == "color_depth_rank" and number > 5:
                raise HTTPException(422, "颜色深浅等级为 0–5")
            if key == "target_basis_hours" and number > 24:
                raise HTTPException(422, "日目标折算小时不能超过 24")
            clean[key] = int(number) if spec.value_type == "integer" else number
        elif spec.value_type == "datetime":
            try:
                clean[key] = timestamp(value)
            except (ValueError, TypeError):
                raise HTTPException(422, f"{spec.label} 日期不正确") from None
        elif spec.value_type == "json":
            if not isinstance(value, dict):
                raise HTTPException(422, f"{spec.label} 必须为对象")
            clean[key] = value
            if key == "requirements_snapshot":
                clean[key] = validate_requirements(value)
        else:
            clean[key] = str(value).strip()
            limit = (
                4000
                if key in {"order_note", "production_note"}
                else 1000
                if key == "warehouse_note"
                else 200
                if key == "mold_code"
                else 255
            )
            if len(clean[key]) > limit:
                raise HTTPException(422, f"{spec.label} 太长，最多 {limit} 字符")
    if "dispatch_state" in clean and clean["dispatch_state"] not in STATES:
        raise HTTPException(422, "需求状态不正确")
    if "allocation_mode" in clean and clean["allocation_mode"] not in {
        "SEQUENTIAL_SHOTS",
        "CO_OUTPUT_UNITS",
        "LEGACY_UNRESOLVED",
    }:
        raise HTTPException(422, "报工分配口径不正确")
    return clean


def apply_demand_fields(db, demand, data, actor, *, new=False):
    clean = validate_fields(data)
    if demand.id and {
        "allocation_mode",
        "effective_outputs_per_shot",
        "output_configuration",
        "item_no",
    }.intersection(clean):
        has_actual = db.scalar(
            select(Run.id)
            .join(RunDemand, RunDemand.run_id == Run.id)
            .where(RunDemand.demand_id == demand.id, Run.actual_start_at.is_not(None))
            .limit(1)
        )
        current = record(demand)
        if has_actual and any(
            current.get(key) != value
            for key, value in clean.items()
            if key
            in {
                "allocation_mode",
                "effective_outputs_per_shot",
                "output_configuration",
                "item_no",
            }
        ):
            raise HTTPException(
                409, "需求已有实际报工口径，不能更改产物或计量配置；请另建新需求"
            )
    sources = dict(demand.field_sources or {})
    if "mold_code" in clean and normalize_code(clean["mold_code"]) != normalize_code(
        demand.mold_code
    ):
        demand.mold_master_id = None
        for key in PROCESS_KEYS:
            if key not in clean and sources.get(key, {}).get("kind") == "MASTER":
                setattr(demand, key, 1 if key == "effective_outputs_per_shot" else None)
                sources.pop(key, None)
        if (
            "requirements_snapshot" not in clean
            and sources.get("requirements_snapshot", {}).get("kind") != "ORDER_OVERRIDE"
        ):
            demand.requirements_snapshot = {}
    if "material_raw" not in clean and {"resin", "material_grade"}.intersection(clean):
        clean["material_raw"] = (
            " ".join(
                str(value)
                for value in (
                    clean.get("resin", demand.resin),
                    clean.get("material_grade", demand.material_grade),
                )
                if value
            )
            or None
        )
    if "material_raw" in clean:
        parts = str(clean["material_raw"] or "").split(maxsplit=1)
        inferred = parts[0].upper() if parts else None
        if "resin" in clean and clean["resin"] and clean["resin"].upper() != inferred:
            raise HTTPException(422, "树脂与用料原文不一致，请统一材料资料")
        clean["resin"] = inferred
        clean["material_grade"] = parts[1] if len(parts) > 1 else None
    extras = dict(demand.extras or {})
    for key, value in clean.items():
        if hasattr(Demand, key):
            setattr(demand, key, value)
        else:
            extras[key] = value
        sources[key] = {"kind": "ORDER_OVERRIDE", "actor_id": actor}
    from .common import jsonable

    demand.extras, demand.field_sources = jsonable(extras), sources
    if not demand.mold_code:
        raise HTTPException(422, "请填写模号")
    if new and "planned_shots" not in data and demand.demand_sets is not None:
        demand.planned_shots = shots_for_units(
            demand.demand_sets,
            demand.pieces_per_set or 1,
            demand.effective_outputs_per_shot or 1,
        )
    enrich(db, demand)
    touch(demand, actor)
