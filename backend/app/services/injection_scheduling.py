from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.injection_scheduling import (
    InjectionSchedulingMachine,
    InjectionSchedulingMold,
    InjectionSchedulingRuleSet,
)
from app.schemas.injection_scheduling import (
    InjectionSchedulingMachineCreate,
    InjectionSchedulingMachineOut,
    InjectionSchedulingMachineUpdate,
    InjectionSchedulingMoldCreate,
    InjectionSchedulingMoldOut,
    InjectionSchedulingMoldUpdate,
    InjectionSchedulingRuleSetOut,
    InjectionSchedulingRuleSetUpdate,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext

SCHEDULING_DEPARTMENTS = (
    "production",
    "molding",
    "pmc-warehouse",
    "warehouse",
    "management",
)

DEFAULT_RULE_CONFIG: dict[str, Any] = {
    "schema_version": "phase2-v1",
    "arm_coverage": {
        "none": ["none"],
        "single": ["none", "single"],
        "dual": ["none", "single", "dual"],
        "multi": ["none", "single", "dual", "multi"],
    },
    "required_dimension_fields": ["length_mm", "width_mm", "height_mm"],
    "process_rule_codes": [
        "pvc_screw",
        "pc_screw",
        "transparent_only",
        "no_core_pull",
        "high_pressure_limit",
        "two_color",
        "vertical",
        "semi_auto",
    ],
    "scoring_weights": {
        "delivery_urgency": 30,
        "business_priority": 20,
        "same_mold": 18,
        "same_material_color": 12,
        "machine_fit": 10,
        "queue_balance": 10,
    },
    "color_scale": [],
    "notes": "阶段2保守默认规则；缺失关键尺寸时必须人工复核。",
}


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def require_injection_scheduling_factory(factory_id: str) -> str:
    normalized = factory_id.strip()
    if normalized not in ALLOWED_FACTORY_IDS:
        raise HTTPException(status_code=400, detail="厂区参数无效")
    return normalized


def _decimal_or_none(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _float_or_none(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def _revision_conflict(entity: str, expected: int, current: int) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "message": f"{entity}已被其他操作更新",
            "expected_revision": expected,
            "current_revision": current,
        },
    )


def machine_out(record: InjectionSchedulingMachine) -> InjectionSchedulingMachineOut:
    return InjectionSchedulingMachineOut(
        id=record.id,
        factory_id=record.factory_id,
        machine_code=record.machine_code,
        area=record.area,
        position=record.position,
        machine_class=record.machine_class,
        clamping_force_tons=_float_or_none(record.clamping_force_tons),
        injection_capacity_g=_float_or_none(record.injection_capacity_g),
        tie_bar_x_mm=_float_or_none(record.tie_bar_x_mm),
        tie_bar_y_mm=_float_or_none(record.tie_bar_y_mm),
        platen_x_mm=_float_or_none(record.platen_x_mm),
        platen_y_mm=_float_or_none(record.platen_y_mm),
        min_mold_thickness_mm=_float_or_none(record.min_mold_thickness_mm),
        max_mold_thickness_mm=_float_or_none(record.max_mold_thickness_mm),
        opening_stroke_mm=_float_or_none(record.opening_stroke_mm),
        machine_type=record.machine_type,
        robot_capabilities=_load_json(record.robot_capabilities_json, []),
        fixture_capabilities=_load_json(record.fixture_capabilities_json, []),
        process_restrictions=_load_json(record.process_restrictions_json, []),
        status=record.status,
        revision=record.revision,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        updated_by=record.updated_by,
        updated_by_name=record.updated_by_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def mold_out(record: InjectionSchedulingMold) -> InjectionSchedulingMoldOut:
    return InjectionSchedulingMoldOut(
        id=record.id,
        factory_id=record.factory_id,
        mold_no=record.mold_no,
        name=record.name,
        length_mm=_float_or_none(record.length_mm),
        width_mm=_float_or_none(record.width_mm),
        height_mm=_float_or_none(record.height_mm),
        weight_kg=_float_or_none(record.weight_kg),
        recommended_machine_class=record.recommended_machine_class,
        whole_shot_net_weight_g=_float_or_none(record.whole_shot_net_weight_g),
        whole_shot_gross_weight_g=_float_or_none(record.whole_shot_gross_weight_g),
        required_arm_type=record.required_arm_type,
        required_fixture_type=record.required_fixture_type,
        material_code=record.material_code,
        material_name=record.material_name,
        color_profile=record.color_profile,
        process_requirements=_load_json(record.process_requirements_json, []),
        copy_count=record.copy_count,
        data_quality_status=record.data_quality_status,
        status=record.status,
        revision=record.revision,
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        updated_by=record.updated_by,
        updated_by_name=record.updated_by_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def rule_set_out(record: InjectionSchedulingRuleSet) -> InjectionSchedulingRuleSetOut:
    return InjectionSchedulingRuleSetOut(
        id=record.id,
        factory_id=record.factory_id,
        revision=record.revision,
        status=record.status,
        configured_max_utilization=float(record.configured_max_utilization),
        allow_mold_rotation_90=record.allow_mold_rotation_90,
        config=_load_json(record.config_json, {}),
        created_by=record.created_by,
        created_by_name=record.created_by_name,
        created_at=record.created_at,
        superseded_at=record.superseded_at,
    )


def _apply_machine(
    record: InjectionSchedulingMachine,
    payload: InjectionSchedulingMachineCreate | InjectionSchedulingMachineUpdate,
) -> None:
    record.machine_code = payload.machine_code
    record.area = payload.area
    record.position = payload.position
    record.machine_class = payload.machine_class
    record.clamping_force_tons = _decimal_or_none(payload.clamping_force_tons)
    record.injection_capacity_g = _decimal_or_none(payload.injection_capacity_g)
    record.tie_bar_x_mm = _decimal_or_none(payload.tie_bar_x_mm)
    record.tie_bar_y_mm = _decimal_or_none(payload.tie_bar_y_mm)
    record.platen_x_mm = _decimal_or_none(payload.platen_x_mm)
    record.platen_y_mm = _decimal_or_none(payload.platen_y_mm)
    record.min_mold_thickness_mm = _decimal_or_none(
        payload.min_mold_thickness_mm
    )
    record.max_mold_thickness_mm = _decimal_or_none(
        payload.max_mold_thickness_mm
    )
    record.opening_stroke_mm = _decimal_or_none(payload.opening_stroke_mm)
    record.machine_type = payload.machine_type
    record.robot_capabilities_json = _json(payload.robot_capabilities)
    record.fixture_capabilities_json = _json(payload.fixture_capabilities)
    record.process_restrictions_json = _json(payload.process_restrictions)
    record.status = payload.status


def _machine_update_values(
    payload: InjectionSchedulingMachineUpdate,
) -> dict[str, Any]:
    return {
        "machine_code": payload.machine_code,
        "area": payload.area,
        "position": payload.position,
        "machine_class": payload.machine_class,
        "clamping_force_tons": _decimal_or_none(payload.clamping_force_tons),
        "injection_capacity_g": _decimal_or_none(payload.injection_capacity_g),
        "tie_bar_x_mm": _decimal_or_none(payload.tie_bar_x_mm),
        "tie_bar_y_mm": _decimal_or_none(payload.tie_bar_y_mm),
        "platen_x_mm": _decimal_or_none(payload.platen_x_mm),
        "platen_y_mm": _decimal_or_none(payload.platen_y_mm),
        "min_mold_thickness_mm": _decimal_or_none(payload.min_mold_thickness_mm),
        "max_mold_thickness_mm": _decimal_or_none(payload.max_mold_thickness_mm),
        "opening_stroke_mm": _decimal_or_none(payload.opening_stroke_mm),
        "machine_type": payload.machine_type,
        "robot_capabilities_json": _json(payload.robot_capabilities),
        "fixture_capabilities_json": _json(payload.fixture_capabilities),
        "process_restrictions_json": _json(payload.process_restrictions),
        "status": payload.status,
    }


def _apply_mold(
    record: InjectionSchedulingMold,
    payload: InjectionSchedulingMoldCreate | InjectionSchedulingMoldUpdate,
) -> None:
    record.mold_no = payload.mold_no
    record.name = payload.name
    record.length_mm = _decimal_or_none(payload.length_mm)
    record.width_mm = _decimal_or_none(payload.width_mm)
    record.height_mm = _decimal_or_none(payload.height_mm)
    record.weight_kg = _decimal_or_none(payload.weight_kg)
    record.recommended_machine_class = payload.recommended_machine_class
    record.whole_shot_net_weight_g = _decimal_or_none(payload.whole_shot_net_weight_g)
    record.whole_shot_gross_weight_g = _decimal_or_none(
        payload.whole_shot_gross_weight_g
    )
    record.required_arm_type = payload.required_arm_type
    record.required_fixture_type = payload.required_fixture_type
    record.material_code = payload.material_code
    record.material_name = payload.material_name
    record.color_profile = payload.color_profile
    record.process_requirements_json = _json(payload.process_requirements)
    record.copy_count = payload.copy_count
    record.data_quality_status = payload.data_quality_status
    record.status = payload.status


def _mold_update_values(
    payload: InjectionSchedulingMoldUpdate,
) -> dict[str, Any]:
    return {
        "mold_no": payload.mold_no,
        "name": payload.name,
        "length_mm": _decimal_or_none(payload.length_mm),
        "width_mm": _decimal_or_none(payload.width_mm),
        "height_mm": _decimal_or_none(payload.height_mm),
        "weight_kg": _decimal_or_none(payload.weight_kg),
        "recommended_machine_class": payload.recommended_machine_class,
        "whole_shot_net_weight_g": _decimal_or_none(
            payload.whole_shot_net_weight_g
        ),
        "whole_shot_gross_weight_g": _decimal_or_none(
            payload.whole_shot_gross_weight_g
        ),
        "required_arm_type": payload.required_arm_type,
        "required_fixture_type": payload.required_fixture_type,
        "material_code": payload.material_code,
        "material_name": payload.material_name,
        "color_profile": payload.color_profile,
        "process_requirements_json": _json(payload.process_requirements),
        "copy_count": payload.copy_count,
        "data_quality_status": payload.data_quality_status,
        "status": payload.status,
    }


def list_machines(
    db: Session,
    factory_id: str,
    *,
    search: str = "",
    status: str = "",
) -> list[InjectionSchedulingMachine]:
    factory_id = require_injection_scheduling_factory(factory_id)
    statement = select(InjectionSchedulingMachine).where(
        InjectionSchedulingMachine.factory_id == factory_id
    )
    if status:
        statement = statement.where(InjectionSchedulingMachine.status == status)
    query = search.strip()
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                InjectionSchedulingMachine.machine_code.ilike(pattern),
                InjectionSchedulingMachine.machine_class.ilike(pattern),
                InjectionSchedulingMachine.area.ilike(pattern),
                InjectionSchedulingMachine.position.ilike(pattern),
            )
        )
    return list(
        db.scalars(statement.order_by(InjectionSchedulingMachine.machine_code)).all()
    )


def create_machine(
    db: Session,
    payload: InjectionSchedulingMachineCreate,
    user: AuthContext,
) -> InjectionSchedulingMachine:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    existing = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.factory_id == factory_id,
            InjectionSchedulingMachine.machine_code == payload.machine_code,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="同厂区机号已存在")
    now = _now()
    actor_name = _actor_name(user)
    record = InjectionSchedulingMachine(
        id=f"ismachine-{uuid4().hex}",
        factory_id=factory_id,
        machine_code=payload.machine_code,
        created_by=user.id,
        created_by_name=actor_name,
        updated_by=user.id,
        updated_by_name=actor_name,
        created_at=now,
        updated_at=now,
    )
    _apply_machine(record, payload)
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="同厂区机号已存在") from exc
    return record


def update_machine(
    db: Session,
    machine_id: str,
    payload: InjectionSchedulingMachineUpdate,
    user: AuthContext,
) -> InjectionSchedulingMachine:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    record = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.id == machine_id,
            InjectionSchedulingMachine.factory_id == factory_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="机台不存在")
    if record.revision != payload.expected_revision:
        raise _revision_conflict("机台资料", payload.expected_revision, record.revision)
    conflict = db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.factory_id == factory_id,
            InjectionSchedulingMachine.machine_code == payload.machine_code,
            InjectionSchedulingMachine.id != machine_id,
        )
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="同厂区机号已存在")
    try:
        result = db.execute(
            update(InjectionSchedulingMachine)
            .where(
                InjectionSchedulingMachine.id == machine_id,
                InjectionSchedulingMachine.factory_id == factory_id,
                InjectionSchedulingMachine.revision == payload.expected_revision,
            )
            .values(
                **_machine_update_values(payload),
                revision=payload.expected_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=_now(),
            )
        )
        if result.rowcount != 1:
            db.rollback()
            latest = db.scalar(
                select(InjectionSchedulingMachine).where(
                    InjectionSchedulingMachine.id == machine_id,
                    InjectionSchedulingMachine.factory_id == factory_id,
                )
            )
            if latest is None:
                raise HTTPException(status_code=404, detail="机台不存在")
            raise _revision_conflict(
                "机台资料", payload.expected_revision, latest.revision
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="同厂区机号已存在") from exc
    return db.scalar(
        select(InjectionSchedulingMachine).where(
            InjectionSchedulingMachine.id == machine_id,
            InjectionSchedulingMachine.factory_id == factory_id,
        )
    )


def list_molds(
    db: Session,
    factory_id: str,
    *,
    search: str = "",
    status: str = "",
) -> list[InjectionSchedulingMold]:
    factory_id = require_injection_scheduling_factory(factory_id)
    statement = select(InjectionSchedulingMold).where(
        InjectionSchedulingMold.factory_id == factory_id
    )
    if status:
        statement = statement.where(InjectionSchedulingMold.status == status)
    query = search.strip()
    if query:
        pattern = f"%{query}%"
        statement = statement.where(
            or_(
                InjectionSchedulingMold.mold_no.ilike(pattern),
                InjectionSchedulingMold.name.ilike(pattern),
                InjectionSchedulingMold.material_code.ilike(pattern),
                InjectionSchedulingMold.material_name.ilike(pattern),
            )
        )
    return list(db.scalars(statement.order_by(InjectionSchedulingMold.mold_no)).all())


def create_mold(
    db: Session,
    payload: InjectionSchedulingMoldCreate,
    user: AuthContext,
) -> InjectionSchedulingMold:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    existing = db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.factory_id == factory_id,
            InjectionSchedulingMold.mold_no == payload.mold_no,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="同厂区模号已存在")
    now = _now()
    actor_name = _actor_name(user)
    record = InjectionSchedulingMold(
        id=f"ismold-{uuid4().hex}",
        factory_id=factory_id,
        mold_no=payload.mold_no,
        created_by=user.id,
        created_by_name=actor_name,
        updated_by=user.id,
        updated_by_name=actor_name,
        created_at=now,
        updated_at=now,
    )
    _apply_mold(record, payload)
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="同厂区模号已存在") from exc
    return record


def update_mold(
    db: Session,
    mold_id: str,
    payload: InjectionSchedulingMoldUpdate,
    user: AuthContext,
) -> InjectionSchedulingMold:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    record = db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.id == mold_id,
            InjectionSchedulingMold.factory_id == factory_id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="模具不存在")
    if record.revision != payload.expected_revision:
        raise _revision_conflict("模具资料", payload.expected_revision, record.revision)
    conflict = db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.factory_id == factory_id,
            InjectionSchedulingMold.mold_no == payload.mold_no,
            InjectionSchedulingMold.id != mold_id,
        )
    )
    if conflict is not None:
        raise HTTPException(status_code=409, detail="同厂区模号已存在")
    try:
        result = db.execute(
            update(InjectionSchedulingMold)
            .where(
                InjectionSchedulingMold.id == mold_id,
                InjectionSchedulingMold.factory_id == factory_id,
                InjectionSchedulingMold.revision == payload.expected_revision,
            )
            .values(
                **_mold_update_values(payload),
                revision=payload.expected_revision + 1,
                updated_by=user.id,
                updated_by_name=_actor_name(user),
                updated_at=_now(),
            )
        )
        if result.rowcount != 1:
            db.rollback()
            latest = db.scalar(
                select(InjectionSchedulingMold).where(
                    InjectionSchedulingMold.id == mold_id,
                    InjectionSchedulingMold.factory_id == factory_id,
                )
            )
            if latest is None:
                raise HTTPException(status_code=404, detail="模具不存在")
            raise _revision_conflict(
                "模具资料", payload.expected_revision, latest.revision
            )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="同厂区模号已存在") from exc
    return db.scalar(
        select(InjectionSchedulingMold).where(
            InjectionSchedulingMold.id == mold_id,
            InjectionSchedulingMold.factory_id == factory_id,
        )
    )


def _active_rule_set(db: Session, factory_id: str) -> InjectionSchedulingRuleSet:
    factory_id = require_injection_scheduling_factory(factory_id)
    record = db.scalar(
        select(InjectionSchedulingRuleSet)
        .where(
            InjectionSchedulingRuleSet.factory_id == factory_id,
            InjectionSchedulingRuleSet.status == "active",
        )
        .order_by(InjectionSchedulingRuleSet.revision.desc())
    )
    if record is None:
        raise HTTPException(status_code=404, detail="当前厂区尚未配置规则")
    return record


def current_rule_set(db: Session, factory_id: str) -> InjectionSchedulingRuleSet:
    return _active_rule_set(db, factory_id)


def update_rule_set(
    db: Session,
    payload: InjectionSchedulingRuleSetUpdate,
    user: AuthContext,
) -> InjectionSchedulingRuleSet:
    factory_id = require_injection_scheduling_factory(payload.factory_id)
    current = _active_rule_set(db, factory_id)
    if current.revision != payload.expected_revision:
        raise _revision_conflict(
            "规则配置", payload.expected_revision, current.revision
        )
    now = _now()
    current.status = "superseded"
    current.superseded_at = now
    record = InjectionSchedulingRuleSet(
        id=f"isrules-{uuid4().hex}",
        factory_id=factory_id,
        revision=current.revision + 1,
        status="active",
        configured_max_utilization=Decimal(
            str(payload.configured_max_utilization)
        ),
        allow_mold_rotation_90=payload.allow_mold_rotation_90,
        config_json=_json(payload.config.model_dump(mode="json")),
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
        superseded_at="",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        latest = _active_rule_set(db, factory_id)
        raise _revision_conflict(
            "规则配置", payload.expected_revision, latest.revision
        ) from exc
    return record


def seed_injection_scheduling_defaults(db: Session) -> None:
    timestamp = "2026-07-31T00:00:00+08:00"
    changed = False
    for factory_id in sorted(ALLOWED_FACTORY_IDS):
        existing = db.scalar(
            select(InjectionSchedulingRuleSet.id).where(
                InjectionSchedulingRuleSet.factory_id == factory_id
            )
        )
        if existing is not None:
            continue
        db.add(
            InjectionSchedulingRuleSet(
                id=f"isrules-default-{factory_id}",
                factory_id=factory_id,
                revision=1,
                status="active",
                configured_max_utilization=Decimal("1.0"),
                allow_mold_rotation_90=False,
                config_json=_json(DEFAULT_RULE_CONFIG),
                created_by="system-seed",
                created_by_name="系统初始化",
                created_at=timestamp,
                superseded_at="",
            )
        )
        changed = True
    if changed:
        db.commit()
