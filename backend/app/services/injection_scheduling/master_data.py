from fastapi import HTTPException
from sqlalchemy import select

from app.models.injection_scheduling import (
    CalendarEvent,
    FactorySettings,
    Machine,
    MoldAsset,
    MoldMaster,
    Run,
)

from .calculations import decimal, timestamp
from .common import check_revision, jsonable, record, scoped, touch
from .defaults import DEFAULTS
from .enrichment import validate_fields, validate_requirements
from .requirement_parser import machine_requirement, normalize_code, state_from_text

MASTER_FIELDS = {
    "mold_code",
    "part_name",
    "alias_codes",
    "required_machine_a",
    "requirement_raw",
    "requirements",
    "defaults",
    "notes",
}
MACHINE_FIELDS = {
    "code",
    "workshop",
    "machine_a",
    "clamp_ton",
    "machine_family",
    "speed_class",
    "manipulator",
    "capabilities",
    "restrictions",
    "notes",
    "current_setup",
}
ASSET_FIELDS = {
    "master_id",
    "asset_code",
    "current_factory_id",
    "status",
    "available_at",
    "notes",
}
EVENT_FIELDS = {"resource_type", "resource_id", "start_at", "end_at", "kind", "notes"}


def write_master(db, kind, factory, data, actor, identity=None, record_revision=None):
    cls, allowed = {
        "molds": (MoldMaster, MASTER_FIELDS),
        "machines": (Machine, MACHINE_FIELDS),
        "mold-assets": (MoldAsset, ASSET_FIELDS),
        "calendar-events": (CalendarEvent, EVENT_FIELDS),
    }[kind]
    if set(data) - allowed:
        raise HTTPException(422, f"不可编辑字段：{', '.join(set(data) - allowed)}")
    obj = (
        (
            db.get(cls, identity)
            if cls is MoldMaster
            else scoped(db, cls, identity, factory)
        )
        if identity
        else cls()
    )
    if obj is None:
        raise HTTPException(404, "主数据不存在")
    if identity:
        check_revision(obj, record_revision)
    values = {**record(obj), **data}
    for key in {
        "capabilities",
        "restrictions",
        "requirements",
        "current_setup",
        "defaults",
    }.intersection(data):
        if not isinstance(data[key], dict):
            raise HTTPException(422, "能力、限制和默认参数必须为对象")
    if kind == "molds":
        code = str(values.get("mold_code") or "").strip()
        if not code or len(code) > 200:
            raise HTTPException(422, "模号不能为空且不超过 200 字符")
        aliases = values.get("alias_codes") or []
        if (
            not isinstance(aliases, list)
            or len(aliases) > 100
            or any(not isinstance(a, str) or len(a) > 200 for a in aliases)
        ):
            raise HTTPException(422, "别名格式不正确")
        proposed = {normalize_code(code), *(normalize_code(a) for a in aliases)}
        if "" in proposed:
            raise HTTPException(422, "别名不能为空")
        for other in db.scalars(
            select(MoldMaster).where(MoldMaster.id != identity if identity else True)
        ):
            if proposed & {
                other.normalized_code,
                *(normalize_code(a) for a in other.alias_codes),
            }:
                raise HTTPException(409, "模号或别名已被其他模具使用")
        obj.normalized_code = normalize_code(code)
        obj.created_from_factory_id = obj.created_from_factory_id or factory
        if "requirement_raw" in data:
            parsed = machine_requirement(data["requirement_raw"])
            data = {
                **data,
                "required_machine_a": data.get(
                    "required_machine_a", parsed["required_machine_a"]
                ),
                "requirements": {**parsed, **data.get("requirements", {})},
            }
        if "defaults" in data:
            data = {**data, "defaults": jsonable(validate_fields(data["defaults"]))}
        if "requirements" in data:
            validate_requirements(data["requirements"])
    elif kind == "machines":
        obj.factory_id = factory
        if not str(values.get("code") or "").strip():
            raise HTTPException(422, "请填写机号")
        code = str(values["code"]).strip()
        if any(
            normalize_code(other.code) == normalize_code(code)
            for other in db.scalars(
                select(Machine).where(
                    Machine.factory_id == factory,
                    Machine.id != identity if identity else True,
                )
            )
        ):
            raise HTTPException(409, "本厂已有此机号")
        data = {**data, "code": code}
        if "notes" in data and state_from_text(data["notes"]) == "MAINTENANCE":
            raise HTTPException(
                422, "备注显示设备需要检修，请使用设备状态操作同步暂停与重算"
            )
        if values.get("machine_family") not in {
            None,
            "HORIZONTAL",
            "VERTICAL",
            "TWO_COLOR",
        } or values.get("speed_class") not in {
            None,
            "NORMAL",
            "HIGH_SPEED",
            "ELECTRIC",
        }:
            raise HTTPException(422, "机型或速度等级不正确")
        capabilities = data.get("capabilities", {})
        for key, value in capabilities.items():
            if key == "fixtures":
                if not isinstance(value, list) or any(
                    not isinstance(item, str) for item in value
                ):
                    raise HTTPException(422, "工装能力必须为文字列表")
            elif type(value) is not bool:
                raise HTTPException(422, "机器能力必须使用 true/false")
        restrictions = data.get("restrictions", {})
        if set(restrictions) - {
            "forbidden_resins",
            "only_resin",
            "only_grade",
            "transparent_only",
        }:
            raise HTTPException(422, "设备材料限制包含不支持的条件")
        forbidden = restrictions.get("forbidden_resins", [])
        if not isinstance(forbidden, list) or any(
            not isinstance(item, str) for item in forbidden
        ):
            raise HTTPException(422, "禁止树脂必须为文字列表")
        if (
            "transparent_only" in restrictions
            and type(restrictions["transparent_only"]) is not bool
        ):
            raise HTTPException(422, "透明件限制必须使用 true/false")
        if any(
            restrictions.get(key) is not None and not isinstance(restrictions[key], str)
            for key in ("only_resin", "only_grade")
        ):
            raise HTTPException(422, "树脂和牌号限制必须为文字")
        if "restrictions" in data:
            data = {
                **data,
                "restrictions": {
                    **restrictions,
                    "forbidden_resins": [value.upper() for value in forbidden],
                    "only_resin": restrictions["only_resin"].upper()
                    if restrictions.get("only_resin")
                    else None,
                },
            }
    elif kind == "mold-assets":
        if not db.get(MoldMaster, values.get("master_id")):
            raise HTTPException(422, "请选择公共模具")
        if not values.get("asset_code"):
            raise HTTPException(422, "请填写实物资产编号")
        destination = values.get("current_factory_id") or factory
        if destination != factory:
            # Relocation is a separate two-factory-authorized service action.
            raise HTTPException(422, "位置变更请使用实物模具调厂操作")
        obj.current_factory_id = factory
        if values.get("status") not in {
            None,
            "AVAILABLE",
            "MAINTENANCE",
            "UNAVAILABLE",
            "IN_TRANSIT",
        }:
            raise HTTPException(422, "模具资产状态不正确")
        if identity and any(
            k in data for k in ("master_id", "status", "current_factory_id")
        ):
            busy = db.scalar(
                select(Run.id)
                .where(
                    Run.mold_asset_id == identity,
                    Run.status.in_(["PLANNED", "RUNNING", "PAUSED"]),
                )
                .limit(1)
            )
            if busy:
                raise HTTPException(409, "实物模具仍有计划或执行占用，请先调整相关任务")
    else:
        obj.factory_id = factory
        resource = values.get("resource_type")
        if resource not in {"FACTORY", "MACHINE", "MOLD"}:
            raise HTTPException(422, "日历资源类型不正确")
        if resource != "FACTORY":
            scoped(
                db,
                Machine if resource == "MACHINE" else MoldAsset,
                values.get("resource_id"),
                factory,
            )
        if not values.get("start_at"):
            raise HTTPException(422, "请填写事件开始时间")
        try:
            if values.get("end_at") and timestamp(values["end_at"]) <= timestamp(
                values["start_at"]
            ):
                raise HTTPException(422, "结束时间必须晚于开始时间")
        except (ValueError, TypeError):
            raise HTTPException(422, "日历日期格式不正确") from None
    for key, value in data.items():
        if key in {"start_at", "end_at", "available_at"}:
            try:
                value = timestamp(value)
            except (ValueError, TypeError):
                raise HTTPException(422, "日期格式不正确") from None
        if (
            key in {"machine_a", "clamp_ton", "required_machine_a"}
            and value is not None
        ):
            value = decimal(value)
            if value is None or value <= 0:
                raise HTTPException(422, "机安和吨位必须为正数或空值")
        if key in {
            "capabilities",
            "restrictions",
            "requirements",
            "current_setup",
        } and not isinstance(value, dict):
            raise HTTPException(422, "能力和限制必须是对象")
        limit = getattr(cls.__table__.columns[key].type, "length", 4000) or 4000
        if isinstance(value, str) and len(value) > limit:
            raise HTTPException(422, "字段内容过长")
        setattr(obj, key, value)
    touch(obj, actor)
    db.add(obj)
    db.flush()
    return obj


def update_settings(db, factory, data):
    if set(data) - DEFAULTS.keys():
        raise HTTPException(422, "未知排产参数")
    params = {**db.get(FactorySettings, factory).parameters, **data}
    if params["business_timezone"] != "Asia/Shanghai":
        raise HTTPException(422, "业务时区固定为 Asia/Shanghai")
    for key in ("day_start", "night_start"):
        from datetime import time

        try:
            time.fromisoformat(params[key])
        except (ValueError, TypeError):
            raise HTTPException(422, "班次时间格式应为 HH:MM") from None
    if params["day_start"] == params["night_start"]:
        raise HTTPException(422, "白夜班开始时间不能相同")
    for key in (
        "target_basis_hours",
        "downstream_lead_days",
        "allowance_rate",
        "material_change_minutes",
    ):
        value = decimal(params[key])
        if (
            value is None
            or value < 0
            or key == "target_basis_hours"
            and not 0 < value <= 24
        ):
            raise HTTPException(422, f"排产参数不正确：{key}")
    days = params["working_days"]
    if (
        not isinstance(days, list)
        or not days
        or any(type(d) is not int or not 0 <= d <= 6 for d in days)
    ):
        raise HTTPException(422, "工作日必须为 0–6 的非空列表")
    if not isinstance(params["allowed_upsize"], dict) or not isinstance(
        params["changeover_reference"], dict
    ):
        raise HTTPException(422, "机安上放和转换参考必须为对象")
    for a, values in params["allowed_upsize"].items():
        required = decimal(a)
        if (
            required is None
            or required <= 0
            or not isinstance(values, list)
            or any(decimal(v) is None or decimal(v) < required for v in values)
        ):
            raise HTTPException(422, "允许上放不得包含小于模具机安的等级")
    if not params["changeover_reference"]:
        raise HTTPException(422, "换模参考表不能为空")
    for a, values in params["changeover_reference"].items():
        if (
            decimal(a) is None
            or decimal(a) <= 0
            or not isinstance(values, list)
            or len(values) != 2
            or any(decimal(v) is None or decimal(v) < 0 for v in values)
        ):
            raise HTTPException(422, "换模/色参考时间格式不正确")
    if not isinstance(params["daily_breaks"], list) or len(params["daily_breaks"]) > 24:
        raise HTTPException(422, "休息时段必须为不超过24项的列表")
    if type(params["setup_interruptible"]) is not bool:
        raise HTTPException(422, "换模可中断必须使用 true/false")
    if not isinstance(params["cleaning_matrix"], dict) or any(
        decimal(value) is None or decimal(value) < 0
        for value in params["cleaning_matrix"].values()
    ):
        raise HTTPException(422, "清洗矩阵时间必须为非负分钟数")
    for period in params["daily_breaks"]:
        try:
            time.fromisoformat(period["start"])
            time.fromisoformat(period["end"])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, "休息时段格式不正确") from None
    db.get(FactorySettings, factory).parameters = params
    return params
