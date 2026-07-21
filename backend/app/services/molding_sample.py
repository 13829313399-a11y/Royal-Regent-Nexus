import json
import re
import unicodedata
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from math import isfinite
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.time import business_now, business_today
from app.models.molding_sample import (
    MoldingSampleAuditLog,
    MoldingSampleDispatchLog,
    MoldingSampleInventoryBatch,
    MoldingSampleInventoryMovement,
    MoldingSampleItem,
    MoldingSampleMaterialPrice,
    MoldingSampleNotification,
    MoldingSampleOrder,
    MoldingSampleProblem,
    MoldingSampleRequisition,
    MoldingSampleSensitiveAuditLog,
    MoldingSampleSetting,
    MoldingSampleTrialReport,
)
from app.schemas.molding_sample import (
    InventoryBatchCreateRequest,
    MaterialPriceIn,
    MoldingSampleBoardStatus,
    MoldingSampleCreateRequest,
    MoldingSampleEditRequest,
    MoldingSampleItemIn,
    MoldingSampleNotificationUpdateRequest,
    MoldingSampleProductionAssignmentRequest,
    MoldingSampleProblemCreateRequest,
    MoldingSampleProblemStatusRequest,
    MoldingSampleStatusRequest,
    MoldingSampleTrialReportUpsertRequest,
    RequisitionCreateRequest,
    RequisitionStatusRequest,
)
from app.services.auth import AuthContext, add_auth_audit, can, ensure_permission
from app.services.business_authz import (
    CROSS_FACTORY_DEPARTMENTS,
    ENGINEERING_DEPARTMENTS,
    MANAGEMENT_DEPARTMENTS,
    MOLDING_CROSS_FACTORY_COST_PERMISSION,
    MOLDING_CROSS_FACTORY_READ_PERMISSION,
    PRODUCTION_DEPARTMENTS,
    SHARED_MOLDING_DEPARTMENTS,
    WAREHOUSE_DEPARTMENTS,
    can_view_molding_cost,
    ensure_general_molding_read,
    ensure_molding_local_write,
    ensure_molding_read,
    ensure_permission_for_departments,
    has_permission_for_departments,
    has_general_molding_read_access,
    molding_read_access,
)

KG_TO_LB = 2.20462
DEFAULT_RATE = 1.08
RATE_KEY = "exchange_rate_rmb_to_hkd"
RAW_MATERIAL_PRICES_MARKER_KEY = "raw_material_prices_server_v1"
RAW_MATERIAL_PRICES_PATH = Path(__file__).resolve().parents[1] / "data" / "raw_material_prices.json"
GENERATED_ORDER_ID_ATTEMPTS = 5

DEFAULT_PRICES = [
    ("HIPS 425", 5.5, "经理默认价"),
    ("ABS 740", 8.0, "经理默认价"),
    ("PP AV161", 4.3, "经理默认价"),
    ("ABS 757", 8.2, "经理默认价"),
    ("PC 110", 9.6, "经理默认价"),
    ("POM 900P", 10.5, "经理默认价"),
    ("ABS 747", 8.1, "经理默认价"),
    ("ABS 750W", 8.6, "混合料匹配示例"),
]
SENSITIVE_AUDIT_LIST_LIMIT = 200
PRODUCTION_TASK_MODULE = "production_molding_sample_task"
ENGINEERING_MOLDING_SAMPLE_MODULE = "engineering_molding_sample"
FIXED_PRODUCTION_TASK_ROLE_IDS = frozenset(
    {
        "position_molding_clerk",
        "position_molding_supervisor",
        "position_molding_manager",
    }
)
PRODUCTION_TARGET_ROLE = "啤机部"
ENGINEERING_TARGET_ROLE = "工程部"
ENGINEERING_SUPERVISOR_TARGET_ROLE = "工程主管"
MANAGER_TARGET_ROLE = "经理"
NOTIFICATION_STATUSES = {"未读", "已读", "已处理"}
PROBLEM_STATUSES = {"待处理", "已解决"}
BOARD_STATUSES: tuple[MoldingSampleBoardStatus, ...] = (
    "待审核",
    "待生产",
    "生产中",
    "已完成",
    "已驳回",
    "已撤回",
)
BOARD_SOURCE_STATUSES: dict[MoldingSampleBoardStatus, tuple[str, ...]] = {
    "待审核": ("待审核", "待经理审核"),
    "待生产": ("待生产",),
    "生产中": ("生产中",),
    "已完成": ("已完成",),
    "已驳回": ("已驳回",),
    "已撤回": ("已撤回",),
}

INITIAL_ORDER_STATUS = "待审核"
LOCKED_STATUSES = {"待经理审核", "待生产", "生产中", "已完成"}
PRODUCTION_TASK_STATUSES = frozenset({"待生产", "生产中", "已完成"})
DISPATCHABLE_STATUSES = frozenset({"待审核", "待经理审核", "已驳回", "已撤回", "待生产"})
MOLDING_FACTORY_CAPABILITIES: dict[str, dict[str, object]] = {
    "huakang-a": {
        "has_molding_department": True,
        "allowed_production_factory_ids": ("huakang-a",),
        "suggested_production_factory_id": "huakang-a",
    },
    "huakang-b": {
        "has_molding_department": True,
        "allowed_production_factory_ids": ("huakang-b",),
        "suggested_production_factory_id": "huakang-b",
    },
    "huakang-c": {
        "has_molding_department": False,
        "allowed_production_factory_ids": ("huakang-a", "huakang-b"),
        "suggested_production_factory_id": "huakang-a",
    },
    "huakang-d": {
        "has_molding_department": False,
        "allowed_production_factory_ids": ("huakang-a", "huakang-b"),
        "suggested_production_factory_id": "huakang-b",
    },
    "huadeng": {
        "has_molding_department": True,
        "allowed_production_factory_ids": ("huadeng",),
        "suggested_production_factory_id": "huadeng",
    },
    "huaxing": {
        "has_molding_department": True,
        "allowed_production_factory_ids": ("huaxing",),
        "suggested_production_factory_id": "huaxing",
    },
}
FACTORY_LABELS = {
    "huakang-a": "华康A",
    "huakang-b": "华康B",
    "huakang-c": "华康C",
    "huakang-d": "华康D",
    "huadeng": "华登",
    "huaxing": "华兴",
}
ALLOWED_ITEM_PATCH_FIELDS = {
    "receipt_no",
    "collected_weight_kg",
    "actual_weight_kg",
    "actual_amount_hkd",
    "injection_cost",
    "production_machine",
}
MATERIAL_SETTLEMENT_INPUT_FIELDS = (
    "material",
    "material_components",
    "required_material_kg",
    "collected_weight_kg",
    "actual_weight_kg",
    "actual_amount_hkd",
)
ENGINEERING_EDIT_DEPARTMENTS = (*ENGINEERING_DEPARTMENTS, *MANAGEMENT_DEPARTMENTS)


def factory_label(factory_id: str | None) -> str:
    if not factory_id:
        return "待派厂"
    return FACTORY_LABELS.get(factory_id, factory_id)


def molding_factory_capability(factory_id: str) -> dict[str, object]:
    capability = MOLDING_FACTORY_CAPABILITIES.get(factory_id)
    if capability is None:
        raise HTTPException(status_code=400, detail=f"无效厂区：{factory_id}")
    return capability


def list_molding_factory_capabilities() -> list[dict[str, object]]:
    return [
        {
            "factory_id": factory_id,
            "has_molding_department": bool(capability["has_molding_department"]),
            "allowed_production_factory_ids": list(
                capability["allowed_production_factory_ids"]
            ),
            "suggested_production_factory_id": str(
                capability["suggested_production_factory_id"]
            ),
        }
        for factory_id, capability in MOLDING_FACTORY_CAPABILITIES.items()
    ]


def normalize_production_factory_id(
    origin_factory_id: str,
    requested_production_factory_id: str | None,
    *,
    allow_unassigned: bool,
) -> str | None:
    capability = molding_factory_capability(origin_factory_id)
    allowed = tuple(capability["allowed_production_factory_ids"])
    requested = (requested_production_factory_id or "").strip() or None

    if requested is None:
        if bool(capability["has_molding_department"]):
            return origin_factory_id
        if allow_unassigned:
            return None
        raise HTTPException(status_code=400, detail="华康C/D啤办单必须选择华康A或华康B承接生产")

    if requested not in allowed:
        allowed_labels = "、".join(factory_label(factory_id) for factory_id in allowed)
        raise HTTPException(
            status_code=400,
            detail=f"{factory_label(origin_factory_id)}啤办单只能由{allowed_labels}承接生产",
        )
    return requested


def production_factory_id_for_order(
    order: MoldingSampleOrder,
    *,
    require_assigned: bool = True,
) -> str | None:
    resolved = normalize_production_factory_id(
        order.factory_id,
        order.production_factory_id,
        allow_unassigned=not require_assigned,
    )
    if require_assigned and resolved is None:
        raise HTTPException(status_code=400, detail="啤办单尚未分配生产承接厂")
    return resolved


def production_route_text(order: MoldingSampleOrder) -> str:
    return (
        f"{factory_label(order.factory_id)} → "
        f"{factory_label(production_factory_id_for_order(order, require_assigned=False))}"
    )


def now_text() -> str:
    return business_now().strftime("%Y-%m-%d %H:%M:%S")


def now_precise_text() -> str:
    return business_now().strftime("%Y-%m-%d %H:%M:%S.%f")


def generate_molding_sample_order_id() -> str:
    timestamp = business_now().strftime("%Y%m%d%H%M%S")
    return f"BP-{timestamp}-{uuid4().hex[:12].upper()}"


def round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def round_weight(value: float) -> float:
    return round(value + 1e-9, 3)


def round_component_weight(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def normalize_material_name(value: str) -> str:
    fullwidth_digits = {ord(chr(code)): str(code - 0xFF10) for code in range(0xFF10, 0xFF1A)}
    normalized = value.lower().translate(fullwidth_digits).replace("度", "°")
    normalized = re.sub(r"^\s*\d+\s*#", "", normalized)

    for token in (" ", "\t", "\n", "-", "_", "(", ")", "（", "）"):
        normalized = normalized.replace(token, "")

    return normalized


def load_seed_material_prices() -> list[tuple[str, float, str]]:
    try:
        source_rows = json.loads(RAW_MATERIAL_PRICES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("无法加载服务端原料价格种子数据") from exc

    prices: list[tuple[str, float, str]] = []
    seen_materials: set[str] = set()
    for row in source_rows:
        material = str(row.get("material", "")).strip()
        try:
            unit_price = float(row.get("unit_price", 0))
        except (TypeError, ValueError):
            continue
        normalized_material = normalize_material_name(material)
        if not normalized_material or unit_price <= 0 or normalized_material in seen_materials:
            continue
        prices.append((material, unit_price, "服务端原料数据库导入"))
        seen_materials.add(normalized_material)

    for material, unit_price, notes in DEFAULT_PRICES:
        normalized_material = normalize_material_name(material)
        if normalized_material in seen_materials:
            continue
        prices.append((material, unit_price, notes))
        seen_materials.add(normalized_material)
    return prices


def seed_molding_sample_defaults(db: Session) -> None:
    if db.scalar(select(MoldingSampleSetting).where(MoldingSampleSetting.key == RATE_KEY)) is None:
        db.add(MoldingSampleSetting(key=RATE_KEY, value=str(DEFAULT_RATE)))

    if db.get(MoldingSampleSetting, RAW_MATERIAL_PRICES_MARKER_KEY) is None:
        existing_materials = {
            normalize_material_name(price.material)
            for price in db.scalars(select(MoldingSampleMaterialPrice)).all()
            if normalize_material_name(price.material)
        }
        inserted_count = 0
        for material, unit_price, notes in load_seed_material_prices():
            normalized_material = normalize_material_name(material)
            if normalized_material in existing_materials:
                continue
            db.add(MoldingSampleMaterialPrice(material=material, unit_price=unit_price, notes=notes))
            existing_materials.add(normalized_material)
            inserted_count += 1
        db.add(
            MoldingSampleSetting(
                key=RAW_MATERIAL_PRICES_MARKER_KEY,
                value=f"completed:{inserted_count}",
            )
        )

    db.commit()


def append_sensitive_audit(
    db: Session,
    action: str,
    current_user: AuthContext,
    target_type: str,
    target_name: str,
    detail: str,
) -> None:
    db.add(
        MoldingSampleSensitiveAuditLog(
            action=action,
            actor_user_id=current_user.id,
            actor_name=current_user.display_name,
            actor_role=current_user.primary_role,
            actor_roles=", ".join(current_user.roles),
            factory_scope=", ".join(current_user.factory_scopes),
            target_type=target_type,
            target_name=target_name,
            detail=detail,
            created_at=now_precise_text(),
        )
    )


def list_sensitive_audit_logs(db: Session) -> list[MoldingSampleSensitiveAuditLog]:
    return list(
        db.scalars(
            select(MoldingSampleSensitiveAuditLog)
            .order_by(MoldingSampleSensitiveAuditLog.id.desc())
            .limit(SENSITIVE_AUDIT_LIST_LIMIT)
        ).all()
    )


def get_exchange_rate(db: Session) -> float:
    setting = db.get(MoldingSampleSetting, RATE_KEY)
    if not setting:
        return DEFAULT_RATE

    try:
        parsed = float(setting.value)
    except ValueError:
        return DEFAULT_RATE

    return parsed if parsed > 0 else DEFAULT_RATE


def get_prices(db: Session) -> list[MoldingSampleMaterialPrice]:
    return list(db.scalars(select(MoldingSampleMaterialPrice).order_by(MoldingSampleMaterialPrice.id)).all())


def resolve_material_price(material: str, prices: list[MoldingSampleMaterialPrice]) -> MoldingSampleMaterialPrice | None:
    price_map = {
        normalize_material_name(price.material): price
        for price in prices
        if price.unit_price > 0
    }
    direct = price_map.get(normalize_material_name(material))
    if direct:
        return direct

    mixed_parts = parse_legacy_material_components(material)
    if not mixed_parts:
        return None

    dominant = max(mixed_parts, key=lambda item: float(item["ratio_percent"]))
    return price_map.get(normalize_material_name(str(dominant["material"])))


def parse_legacy_material_components(material: str) -> list[dict[str, Any]] | None:
    normalized_material = material.replace("＋", "+")
    if not re.match(r"^\s*\d+(?:\.\d+)?\s*[%％]", normalized_material):
        return []
    if normalized_material.rstrip().endswith("+"):
        return None

    parts = re.split(r"\+\s*(?=\d+(?:\.\d+)?\s*[%％])", normalized_material)

    parsed: list[dict[str, Any]] = []
    total = 0.0
    for part in parts:
        match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*[%％]\s*(.+?)\s*$", part)
        if not match:
            return None
        ratio = float(match.group(1))
        if not isfinite(ratio) or ratio <= 0:
            return None
        label = match.group(2).strip()
        source_type = "runner" if "水口" in label else "virgin"
        base_material = re.sub(r"(?:水口料|水口)\s*$", "", label).strip()
        parsed.append(
            {
                "material": base_material,
                "ratio_percent": ratio,
                "source_type": source_type,
            }
        )
        total += ratio

    if not isfinite(total) or abs(total - 100) > 0.01:
        return None

    first_virgin = next(
        (component["material"] for component in parsed if component["source_type"] == "virgin" and component["material"]),
        "",
    )
    for component in parsed:
        if component["source_type"] == "runner" and not component["material"]:
            component["material"] = first_virgin
    return parsed if parsed and all(component["material"] for component in parsed) else None


def canonical_material_display(components: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for component in components:
        ratio = f"{float(component['ratio_percent']):g}"
        material = str(component["material"]).strip()
        if component["source_type"] == "runner" and not material.endswith("水口料"):
            material = f"{material} 水口料"
        parts.append(f"{ratio}% {material}")
    return " + ".join(parts)


def normalized_item_data(item_payload: MoldingSampleItemIn, *, exclude: set[str]) -> dict[str, Any]:
    item_data = item_payload.model_dump(exclude=exclude)
    item_data["actual_material_cost_components"] = []
    components = item_data.get("material_components") or []
    if components:
        item_data["material"] = canonical_material_display(components)
    return item_data


def material_settlement_inputs_match(existing_item: MoldingSampleItem, item_data: dict[str, Any]) -> bool:
    for field in MATERIAL_SETTLEMENT_INPUT_FIELDS:
        existing_value = getattr(existing_item, field, None)
        incoming_value = item_data.get(field)
        if field == "material_components":
            existing_value = existing_value or []
            incoming_value = incoming_value or []
        if existing_value != incoming_value:
            return False
    return True


def calculate_material_amount_hkd(
    material_weight_kg: float | None,
    material: str,
    material_components: list[dict[str, Any]],
    prices: list[MoldingSampleMaterialPrice],
) -> tuple[float | None, list[dict[str, Any]]]:
    if material_weight_kg is None or material_weight_kg <= 0:
        return None, []

    price_map = {
        normalize_material_name(price.material): price
        for price in prices
        if price.unit_price > 0
    }
    components: list[dict[str, Any]] | None = material_components
    if not components:
        direct_price = price_map.get(normalize_material_name(material))
        if direct_price is not None:
            components = [{"material": material.strip(), "ratio_percent": 100.0, "source_type": "virgin"}]
        else:
            components = parse_legacy_material_components(material)
    if not components:
        return None, []

    component_fees: list[float] = []
    snapshots: list[dict[str, Any]] = []
    for component in components:
        price = price_map.get(normalize_material_name(str(component["material"])))
        if price is None:
            return None, []
        component_weight = round_component_weight(
            material_weight_kg * float(component["ratio_percent"]) / 100
        )
        component_fee = round_money(component_weight * KG_TO_LB * price.unit_price)
        component_fees.append(component_fee)
        snapshots.append(
            {
                "material": str(component["material"]),
                "source_type": str(component["source_type"]),
                "ratio_percent": float(component["ratio_percent"]),
                "weight_kg": component_weight,
                "unit_price": float(price.unit_price),
                "amount_hkd": component_fee,
            }
        )
    return round_money(sum(component_fees)), snapshots


def is_external_order(order: MoldingSampleOrder) -> bool:
    return order.send_to in {"发至湖南", "发至模厂"} or order.workshop == "模厂"


def is_production_task_order(order: MoldingSampleOrder) -> bool:
    return order.status in PRODUCTION_TASK_STATUSES and not is_external_order(order)


def ensure_export_permission(db: Session, current_user: AuthContext, factory_id: str) -> None:
    ensure_molding_read(db, current_user, factory_id)
    # Export is an operating permission. A user with cross-factory read scope
    # may inspect the record, but must not turn that read-only scope into a
    # downloadable data export unless the position has cross-factory operate.
    ensure_molding_local_write(db, current_user, factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:export",
        factory_id,
        SHARED_MOLDING_DEPARTMENTS,
    )


def ensure_molding_cost_read(db: Session, current_user: AuthContext, factory_id: str) -> str:
    read_source = ensure_molding_read(db, current_user, factory_id)
    if can_view_molding_cost(current_user, factory_id, read_source):
        return read_source
    ensure_permission_for_departments(
        db,
        current_user,
        MOLDING_CROSS_FACTORY_COST_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    )
    raise AssertionError("unreachable")


def ensure_molding_create_access(db: Session, current_user: AuthContext, factory_id: str) -> None:
    ensure_molding_read(db, current_user, factory_id)
    ensure_molding_local_write(db, current_user, factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:create",
        factory_id,
        ENGINEERING_DEPARTMENTS,
    )


def user_factory_candidates(current_user: AuthContext) -> tuple[str, ...]:
    candidates = tuple(
        dict.fromkeys(
            (
                *(scope for scope in current_user.factory_scopes if scope),
                *(grant.factory_id for grant in current_user.grants if grant.factory_id),
                *(override.factory_id for override in current_user.overrides if override.factory_id),
            )
        )
    )
    return candidates or ("*",)


def ensure_permission_in_any_factory(
    db: Session,
    current_user: AuthContext,
    permission: str,
    departments: tuple[str, ...],
) -> None:
    factory_candidates = user_factory_candidates(current_user)
    for factory_id in factory_candidates:
        if has_permission_for_departments(current_user, permission, factory_id, departments):
            return
    ensure_permission_for_departments(
        db,
        current_user,
        permission,
        factory_candidates[0],
        departments,
    )
    raise AssertionError("unreachable")


def ensure_any_local_molding_read(db: Session, current_user: AuthContext) -> None:
    factory_candidates = user_factory_candidates(current_user)
    for factory_id in factory_candidates:
        if (
            molding_read_access(current_user, factory_id) == "local"
            and has_general_molding_read_access(current_user, factory_id)
        ):
            return
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:read",
        factory_candidates[0],
        SHARED_MOLDING_DEPARTMENTS,
    )
    raise AssertionError("unreachable")


def is_fixed_production_notification_only_access(
    current_user: AuthContext,
    factory_id: str,
) -> bool:
    fixed_task_grants = tuple(
        grant
        for grant in current_user.grants
        if grant.role_id in FIXED_PRODUCTION_TASK_ROLE_IDS
    )
    if not fixed_task_grants:
        return False

    fixed_task_context = replace(
        current_user,
        grants=fixed_task_grants,
        overrides=(),
    )
    fixed_task_read = any(
        can(
            fixed_task_context,
            "molding_sample:production_read",
            factory_id,
            department,
        )
        for department in PRODUCTION_DEPARTMENTS
    )
    if not fixed_task_read:
        return False

    nonfixed_context = replace(
        current_user,
        grants=tuple(
            grant
            for grant in current_user.grants
            if grant.role_id not in FIXED_PRODUCTION_TASK_ROLE_IDS
        ),
    )
    override_only_context = replace(current_user, grants=())
    has_independent_production_read = has_permission_for_departments(
        nonfixed_context,
        "molding_sample:production_read",
        factory_id,
        PRODUCTION_DEPARTMENTS,
    ) or any(
        can(
            override_only_context,
            "molding_sample:production_read",
            factory_id,
            department,
        )
        for department in PRODUCTION_DEPARTMENTS
    )
    # The fixed molding-position grant now intentionally includes general
    # engineering-board read access. Ignore that grant here so the existing
    # production-notification boundary remains intact. Independent custom
    # grants and explicit overrides stay additive.
    has_general_read = has_permission_for_departments(
        nonfixed_context,
        "molding_sample:read",
        factory_id,
        SHARED_MOLDING_DEPARTMENTS,
    ) or has_permission_for_departments(
        nonfixed_context,
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    ) or any(
        can(
            override_only_context,
            permission,
            factory_id,
            department,
        )
        for permission, departments in (
            ("molding_sample:read", SHARED_MOLDING_DEPARTMENTS),
            (MOLDING_CROSS_FACTORY_READ_PERMISSION, CROSS_FACTORY_DEPARTMENTS),
        )
        for department in departments
    )
    return not has_independent_production_read and not has_general_read


def has_order_read_access(current_user: AuthContext, order: MoldingSampleOrder) -> bool:
    origin_read_source = molding_read_access(current_user, order.factory_id)
    if origin_read_source is not None and has_general_molding_read_access(current_user, order.factory_id):
        return True

    production_factory_id = production_factory_id_for_order(order, require_assigned=False)
    if (
        production_factory_id
        and is_production_task_order(order)
        and has_permission_for_departments(
            current_user,
            "molding_sample:production_read",
            production_factory_id,
            PRODUCTION_DEPARTMENTS,
        )
    ):
        return True
    return False


def ensure_order_read_allowed(
    db: Session,
    current_user: AuthContext,
    order: MoldingSampleOrder,
) -> None:
    if has_order_read_access(current_user, order):
        return

    production_factory_id = production_factory_id_for_order(order, require_assigned=False)

    add_auth_audit(
        db,
        "permission_denied",
        username=current_user.username,
        user_id=current_user.id,
        detail=(
            f"禁止读取未授权啤办单：{order.id};"
            f"来源厂={order.factory_id};承接厂={production_factory_id or '未分配'}"
        ),
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无该啤办单查看权限")


def order_authorization_factory_id(
    current_user: AuthContext,
    order: MoldingSampleOrder,
) -> str:
    if (
        molding_read_access(current_user, order.factory_id) is not None
        and has_general_molding_read_access(current_user, order.factory_id)
    ):
        return order.factory_id

    production_factory_id = production_factory_id_for_order(order, require_assigned=False)
    if (
        production_factory_id
        and is_production_task_order(order)
        and has_permission_for_departments(
            current_user,
            "molding_sample:production_read",
            production_factory_id,
            PRODUCTION_DEPARTMENTS,
        )
    ):
        return production_factory_id
    return order.factory_id


def ensure_production_order_permission(
    db: Session,
    current_user: AuthContext,
    order: MoldingSampleOrder,
    permission: str,
) -> str:
    production_factory_id = production_factory_id_for_order(order)
    assert production_factory_id is not None
    ensure_molding_local_write(db, current_user, production_factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        permission,
        production_factory_id,
        PRODUCTION_DEPARTMENTS,
    )
    return production_factory_id


def load_order(db: Session, order_id: str, current_user: AuthContext | None = None) -> MoldingSampleOrder:
    order = db.scalar(
        select(MoldingSampleOrder)
        .where(MoldingSampleOrder.id == order_id)
        .options(
            selectinload(MoldingSampleOrder.items),
            selectinload(MoldingSampleOrder.audit_logs),
            selectinload(MoldingSampleOrder.dispatch_logs),
            selectinload(MoldingSampleOrder.notifications),
            selectinload(MoldingSampleOrder.problems),
            selectinload(MoldingSampleOrder.trial_reports),
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="啤办单不存在")

    if current_user is not None:
        ensure_order_read_allowed(db, current_user, order)

    return order


def order_statement():
    return select(MoldingSampleOrder).options(
        selectinload(MoldingSampleOrder.items),
        selectinload(MoldingSampleOrder.audit_logs),
        selectinload(MoldingSampleOrder.dispatch_logs),
        selectinload(MoldingSampleOrder.notifications),
        selectinload(MoldingSampleOrder.problems),
        selectinload(MoldingSampleOrder.trial_reports),
    )


def list_orders(
    db: Session,
    current_user: AuthContext,
    factory_id: str | None = None,
) -> list[MoldingSampleOrder]:
    if factory_id:
        ensure_molding_read(db, current_user, factory_id)

    statement = order_statement()
    if factory_id:
        statement = statement.where(MoldingSampleOrder.factory_id == factory_id)
        if not has_general_molding_read_access(current_user, factory_id):
            statement = statement.where(
                MoldingSampleOrder.status.in_(PRODUCTION_TASK_STATUSES),
                ~MoldingSampleOrder.send_to.in_(("发至湖南", "发至模厂")),
                MoldingSampleOrder.workshop != "模厂",
            )

    orders = list(
        db.scalars(
            statement.order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
        ).all()
    )
    return [
        order for order in orders
        if molding_read_access(current_user, order.factory_id) is not None
        and (
            has_general_molding_read_access(current_user, order.factory_id)
            or is_production_task_order(order)
        )
    ]


def list_production_tasks(
    db: Session,
    current_user: AuthContext,
    production_factory_id: str,
) -> list[MoldingSampleOrder]:
    capability = molding_factory_capability(production_factory_id)
    if not bool(capability["has_molding_department"]):
        raise HTTPException(status_code=400, detail="华康C/D没有啤机部，不能作为生产任务队列厂区")
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:production_read",
        production_factory_id,
        PRODUCTION_DEPARTMENTS,
    )

    statement = order_statement().where(
        MoldingSampleOrder.status.in_(PRODUCTION_TASK_STATUSES),
        ~MoldingSampleOrder.send_to.in_(("发至湖南", "发至模厂")),
        MoldingSampleOrder.workshop != "模厂",
        or_(
            MoldingSampleOrder.production_factory_id == production_factory_id,
            (
                (MoldingSampleOrder.production_factory_id.is_(None))
                & (MoldingSampleOrder.factory_id == production_factory_id)
            ),
        ),
    )
    return list(
        db.scalars(
            statement.order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
        ).all()
    )


def normalize_board_status(status: str) -> MoldingSampleBoardStatus | None:
    if status == "待经理审核":
        return "待审核"
    if status in BOARD_STATUSES:
        return status  # type: ignore[return-value]
    return None


def normalize_board_search_value(value: Any) -> str:
    if value is None:
        return ""

    normalized = unicodedata.normalize("NFKC", str(value)).casefold()
    return "".join(
        character
        for character in normalized
        if not character.isspace()
        and unicodedata.category(character)[0] not in {"P", "S"}
    )


def tokenize_board_search_keyword(keyword: str) -> list[str]:
    normalized_keyword = unicodedata.normalize("NFKC", keyword or "").strip()
    if not normalized_keyword:
        return []

    return [
        normalized
        for part in re.split(r"\s+", normalized_keyword)
        if (normalized := normalize_board_search_value(part))
    ]


def board_search_values(order: MoldingSampleOrder) -> list[str]:
    values: list[Any] = [
        order.id,
        order.order_number,
        order.doc_number,
        order.product_name,
        order.client_name,
        order.date,
        order.stage,
        order.order_type,
        order.workshop,
        order.send_to,
        order.supervisor,
        order.eng_name,
        order.reason,
        order.status,
        order.reject_reason,
        order.completed_date,
    ]
    presence_labels = {
        "in_factory": "在厂",
        "out_of_factory": "不在厂",
        "unknown": "待确认",
    }

    for item in order.items:
        values.extend(
            [
                item.id,
                item.order_id,
                item.mold_id,
                item.mold_name,
                item.mold_dimensions,
                item.mold_presence_status,
                presence_labels.get(item.mold_presence_status, "待确认"),
                item.machine_type,
                item.production_machine,
                item.material,
                item.material_usage_type,
                "试料" if item.material_usage_type == "trial" else "正式生产",
                item.color,
                item.pigment_no,
                item.quantity,
                item.shoot_qty,
                item.required_material_kg,
                item.mold_return_time,
                item.completion_time,
                item.notes,
                item.receipt_no,
            ]
        )

        components = item.material_components or parse_legacy_material_components(item.material) or []
        if (
            not components
            and item.material.strip()
            and not re.match(r"^\s*\d+(?:\.\d+)?\s*[%％]", item.material.replace("＋", "+"))
        ):
            components = [
                {
                    "material": item.material.strip(),
                    "source_type": "virgin",
                    "ratio_percent": 100,
                }
            ]
        for component in components:
            source_type = str(component.get("source_type", ""))
            values.extend(
                [
                    component.get("material", ""),
                    source_type,
                    "水口料" if source_type == "runner" else "原料",
                    component.get("ratio_percent", ""),
                ]
            )

    for problem in order.problems:
        values.extend(
            [
                problem.id,
                problem.order_number,
                problem.description,
                problem.reported_by,
                problem.status,
            ]
        )

    return [
        normalized
        for value in values
        if (normalized := normalize_board_search_value(value))
    ]


def matches_board_search(order: MoldingSampleOrder, tokens: list[str]) -> bool:
    if not tokens:
        return True

    search_values = board_search_values(order)
    return all(
        any(token in value for value in search_values)
        for token in tokens
    )


def _board_search_candidates(
    db: Session,
    factory_id: str,
    source_statuses: tuple[str, ...] | None = None,
) -> list[MoldingSampleOrder]:
    statement = (
        select(MoldingSampleOrder)
        .where(MoldingSampleOrder.factory_id == factory_id)
        .options(
            selectinload(MoldingSampleOrder.items),
            selectinload(MoldingSampleOrder.problems),
        )
    )
    if source_statuses is not None:
        statement = statement.where(MoldingSampleOrder.status.in_(source_statuses))

    return list(
        db.scalars(
            statement.order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
        ).all()
    )


def _load_full_board_orders(db: Session, order_ids: list[str]) -> list[MoldingSampleOrder]:
    if not order_ids:
        return []

    orders = list(
        db.scalars(
            order_statement().where(MoldingSampleOrder.id.in_(order_ids))
        ).all()
    )
    order_by_id = {order.id: order for order in orders}
    return [order_by_id[order_id] for order_id in order_ids if order_id in order_by_id]


def list_board_page(
    db: Session,
    current_user: AuthContext,
    *,
    factory_id: str,
    board_status: MoldingSampleBoardStatus,
    keyword: str,
    page: int,
    page_size: int,
) -> tuple[list[MoldingSampleOrder], int, int, int]:
    ensure_general_molding_read(db, current_user, factory_id)
    source_statuses = BOARD_SOURCE_STATUSES[board_status]
    tokens = tokenize_board_search_keyword(keyword)

    if tokens:
        candidates = _board_search_candidates(db, factory_id, source_statuses)
        matched_order_ids = [
            order.id for order in candidates
            if matches_board_search(order, tokens)
        ]
        total = len(matched_order_ids)
        page_count = max(1, (total + page_size - 1) // page_size)
        normalized_page = min(page, page_count)
        start = (normalized_page - 1) * page_size
        page_order_ids = matched_order_ids[start:start + page_size]
    else:
        filters = (
            MoldingSampleOrder.factory_id == factory_id,
            MoldingSampleOrder.status.in_(source_statuses),
        )
        total = int(
            db.scalar(
                select(func.count(MoldingSampleOrder.id)).where(*filters)
            )
            or 0
        )
        page_count = max(1, (total + page_size - 1) // page_size)
        normalized_page = min(page, page_count)
        page_order_ids = list(
            db.scalars(
                select(MoldingSampleOrder.id)
                .where(*filters)
                .order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
                .offset((normalized_page - 1) * page_size)
                .limit(page_size)
            ).all()
        )

    return _load_full_board_orders(db, page_order_ids), total, normalized_page, page_count


def _empty_board_status_counts() -> dict[MoldingSampleBoardStatus, int]:
    return {status: 0 for status in BOARD_STATUSES}


def _is_production_data_pending(order: MoldingSampleOrder) -> bool:
    return (
        order.status == "生产中"
        and not is_external_order(order)
        and any(not item.actual_weight_kg or item.actual_weight_kg <= 0 for item in order.items)
    )


def get_board_summary(
    db: Session,
    current_user: AuthContext,
    *,
    factory_id: str,
    keyword: str,
) -> dict[str, Any]:
    ensure_general_molding_read(db, current_user, factory_id)
    tokens = tokenize_board_search_keyword(keyword)
    status_counts = _empty_board_status_counts()

    if tokens:
        orders = [
            order
            for order in _board_search_candidates(db, factory_id)
            if matches_board_search(order, tokens)
        ]
        for order in orders:
            normalized_status = normalize_board_status(order.status)
            if normalized_status is not None:
                status_counts[normalized_status] += 1

        total = len(orders)
        unresolved_problem_count = sum(
            any(problem.status == "待处理" for problem in order.problems)
            for order in orders
        )
        production_data_pending_count = sum(_is_production_data_pending(order) for order in orders)
    else:
        total = int(
            db.scalar(
                select(func.count(MoldingSampleOrder.id)).where(
                    MoldingSampleOrder.factory_id == factory_id
                )
            )
            or 0
        )
        status_rows = db.execute(
            select(MoldingSampleOrder.status, func.count(MoldingSampleOrder.id))
            .where(MoldingSampleOrder.factory_id == factory_id)
            .group_by(MoldingSampleOrder.status)
        ).all()
        for source_status, count in status_rows:
            normalized_status = normalize_board_status(source_status)
            if normalized_status is not None:
                status_counts[normalized_status] += int(count)

        unresolved_problem_count = int(
            db.scalar(
                select(func.count(MoldingSampleOrder.id)).where(
                    MoldingSampleOrder.factory_id == factory_id,
                    exists(
                        select(MoldingSampleProblem.id).where(
                            MoldingSampleProblem.order_id == MoldingSampleOrder.id,
                            MoldingSampleProblem.status == "待处理",
                        )
                    ),
                )
            )
            or 0
        )
        production_data_pending_count = int(
            db.scalar(
                select(func.count(MoldingSampleOrder.id)).where(
                    MoldingSampleOrder.factory_id == factory_id,
                    MoldingSampleOrder.status == "生产中",
                    ~func.coalesce(MoldingSampleOrder.send_to, "").in_(("发至湖南", "发至模厂")),
                    func.coalesce(MoldingSampleOrder.workshop, "") != "模厂",
                    exists(
                        select(MoldingSampleItem.id).where(
                            MoldingSampleItem.order_id == MoldingSampleOrder.id,
                            or_(
                                MoldingSampleItem.actual_weight_kg.is_(None),
                                MoldingSampleItem.actual_weight_kg <= 0,
                            ),
                        )
                    ),
                )
            )
            or 0
        )

    return {
        "total": total,
        "status_counts": status_counts,
        "review_count": status_counts["待审核"],
        "production_count": status_counts["待生产"] + status_counts["生产中"],
        "completed_count": status_counts["已完成"],
        "rejected_count": status_counts["已驳回"],
        "withdrawn_count": status_counts["已撤回"],
        "unresolved_problem_count": unresolved_problem_count,
        "production_data_pending_count": production_data_pending_count,
    }


def append_audit(
    db: Session,
    order: MoldingSampleOrder,
    action: str,
    current_user: AuthContext,
    from_status: str,
    to_status: str,
    reason: str = "",
) -> None:
    db.add(
        MoldingSampleAuditLog(
            id=f"{order.id}-audit-{uuid4().hex[:12]}",
            order_id=order.id,
            action=action,
            actor_user_id=current_user.id,
            actor_name=current_user.display_name,
            actor_role=current_user.primary_role,
            actor_roles=", ".join(current_user.roles),
            factory_scope=", ".join(current_user.factory_scopes),
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            created_at=now_precise_text(),
        )
    )


def append_notification(
    db: Session,
    order: MoldingSampleOrder,
    target_module: str,
    target_role: str,
    event_type: str,
    title: str,
    message: str,
    from_status: str = "",
    to_status: str = "",
    status: str = "未读",
    actor_name: str = "",
    target_factory_id: str | None = None,
) -> MoldingSampleNotification:
    notification = MoldingSampleNotification(
        id=f"{order.id}-notice-{uuid4().hex[:12]}",
        order_id=order.id,
        factory_id=target_factory_id or order.factory_id,
        target_module=target_module,
        target_role=target_role,
        event_type=event_type,
        title=title,
        message=message,
        from_status=from_status,
        to_status=to_status,
        status=status,
        actor_name=actor_name,
        created_at=now_precise_text(),
    )
    db.add(notification)
    return notification


def mark_order_notifications_handled(
    db: Session,
    order_id: str,
    target_module: str,
    actor_name: str = "",
    target_factory_id: str | None = None,
) -> None:
    handled_at = now_text()
    statement = (
        select(MoldingSampleNotification)
        .where(MoldingSampleNotification.order_id == order_id)
        .where(MoldingSampleNotification.target_module == target_module)
        .where(MoldingSampleNotification.status != "已处理")
    )
    if target_factory_id:
        statement = statement.where(MoldingSampleNotification.factory_id == target_factory_id)
    notifications = db.scalars(statement).all()

    for notification in notifications:
        notification.status = "已处理"
        notification.actor_name = actor_name or notification.actor_name
        notification.read_at = notification.read_at or handled_at
        notification.handled_at = notification.handled_at or handled_at


def append_dispatch_log(
    db: Session,
    order: MoldingSampleOrder,
    current_user: AuthContext,
    *,
    from_production_factory_id: str | None,
    to_production_factory_id: str,
    action: str,
    reason: str,
) -> MoldingSampleDispatchLog:
    log = MoldingSampleDispatchLog(
        id=f"{order.id}-dispatch-{uuid4().hex[:12]}",
        order_id=order.id,
        origin_factory_id=order.factory_id,
        from_production_factory_id=from_production_factory_id,
        to_production_factory_id=to_production_factory_id,
        action=action,
        reason=reason,
        actor_user_id=current_user.id,
        actor_name=current_user.display_name,
        created_at=now_precise_text(),
    )
    db.add(log)
    return log


def append_supervisor_review_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str = "",
    actor_name: str = "",
) -> None:
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_SUPERVISOR_TARGET_ROLE,
        event_type="待主管审核",
        title="啤办单待主管审核",
        message=f"啤办单 {order.id} 已提交主管审核，请及时处理。",
        from_status=from_status,
        to_status="待审核",
        actor_name=actor_name,
    )


def append_manager_review_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str = "",
    actor_name: str = "",
) -> None:
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=MANAGER_TARGET_ROLE,
        event_type="待经理审核",
        title="啤办单待经理审核",
        message=f"啤办单 {order.id} 已提交经理终审，请及时处理。",
        from_status=from_status,
        to_status="待经理审核",
        actor_name=actor_name,
    )


def append_engineering_rework_notification(
    db: Session,
    order: MoldingSampleOrder,
    from_status: str,
    to_status: str,
    reason: str = "",
    actor_name: str = "",
) -> None:
    reason_text = f" 原因：{reason}" if reason else ""
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_TARGET_ROLE,
        event_type="审核驳回",
        title="啤办单被驳回",
        message=f"啤办单 {order.id} 已被驳回，请工程部修改后重提。{reason_text}",
        from_status=from_status,
        to_status=to_status,
        actor_name=actor_name,
    )


def notification_departments(target_module: str, target_role: str) -> tuple[str, ...]:
    if target_module == PRODUCTION_TASK_MODULE:
        return PRODUCTION_DEPARTMENTS
    if target_role == MANAGER_TARGET_ROLE:
        return MANAGEMENT_DEPARTMENTS
    return ENGINEERING_DEPARTMENTS


def notification_module_permission(target_module: str) -> str:
    if target_module == PRODUCTION_TASK_MODULE:
        return "molding_sample:production_read"
    return "molding_sample:read"


def has_notification_scope_permission(
    current_user: AuthContext,
    permission: str,
    notification: MoldingSampleNotification,
) -> bool:
    if (
        notification.target_module != PRODUCTION_TASK_MODULE
        and is_fixed_production_notification_only_access(
            current_user,
            notification.factory_id,
        )
    ):
        return False

    fixed_contract_grants = tuple(
        grant
        for grant in current_user.grants
        if grant.unrestricted_department
        and "molding_sample:notification_read" in grant.permissions
    )
    departments = notification_departments(
        notification.target_module,
        notification.target_role,
    )
    fixed_contract_context = replace(
        current_user,
        grants=fixed_contract_grants,
    )
    fixed_contract_allowed = bool(fixed_contract_grants) and any(
        can(
            fixed_contract_context,
            permission,
            notification.factory_id,
            department,
        )
        for department in departments
    )
    compatibility_grants = tuple(
        grant
        for grant in current_user.grants
        if grant not in fixed_contract_grants
    )
    compatibility_allowed = has_permission_for_departments(
        replace(current_user, grants=compatibility_grants),
        permission,
        notification.factory_id,
        departments,
    )
    return fixed_contract_allowed or compatibility_allowed


def ensure_notification_scope_permission(
    db: Session,
    current_user: AuthContext,
    permission: str,
    notification: MoldingSampleNotification,
) -> None:
    if has_notification_scope_permission(current_user, permission, notification):
        return
    add_auth_audit(
        db,
        "permission_denied",
        username=current_user.username,
        user_id=current_user.id,
        detail=(
            f"缺少通知范围内权限：{permission}@{notification.factory_id}/"
            f"{notification.target_module}"
        ),
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无授权范围内通知权限")


def list_notifications(
    db: Session,
    current_user: AuthContext,
    target_module: str | None = None,
    target_role: str | None = None,
    factory_id: str | None = None,
    order_id: str | None = None,
    status: str | None = None,
) -> list[MoldingSampleNotification]:
    ensure_permission(db, current_user, "molding_sample:notification_read")
    statement = select(MoldingSampleNotification)
    if target_module:
        statement = statement.where(MoldingSampleNotification.target_module == target_module)
    if target_role:
        statement = statement.where(MoldingSampleNotification.target_role == target_role)
    if factory_id:
        statement = statement.where(MoldingSampleNotification.factory_id == factory_id)
    if order_id:
        statement = statement.where(MoldingSampleNotification.order_id == order_id)
    if status:
        statement = statement.where(MoldingSampleNotification.status == status)

    notifications = list(
        db.scalars(
            statement.order_by(MoldingSampleNotification.created_at.desc(), MoldingSampleNotification.id.desc())
        ).all()
    )
    return [
        notification for notification in notifications
        if has_notification_scope_permission(
            current_user,
            "molding_sample:notification_read",
            notification,
        )
        and has_notification_scope_permission(
            current_user,
            notification_module_permission(notification.target_module),
            notification,
        )
    ]


def update_notification(
    db: Session,
    notification_id: str,
    payload: MoldingSampleNotificationUpdateRequest,
    current_user: AuthContext,
) -> MoldingSampleNotification:
    notification = db.get(MoldingSampleNotification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="啤办通知不存在")
    ensure_molding_local_write(db, current_user, notification.factory_id)
    ensure_notification_scope_permission(
        db,
        current_user,
        "molding_sample:notification_read",
        notification,
    )
    ensure_notification_scope_permission(
        db,
        current_user,
        notification_module_permission(notification.target_module),
        notification,
    )
    if notification.target_module == PRODUCTION_TASK_MODULE:
        ensure_permission_for_departments(
            db,
            current_user,
            "molding_sample:production_fillback",
            notification.factory_id,
            PRODUCTION_DEPARTMENTS,
        )
    if payload.status not in NOTIFICATION_STATUSES:
        raise HTTPException(status_code=400, detail="通知状态无效")

    status_rank = {"未读": 0, "已读": 1, "已处理": 2}
    if status_rank[payload.status] < status_rank.get(notification.status, 0):
        return notification

    timestamp = now_text()
    notification.status = payload.status
    notification.actor_name = current_user.display_name
    if payload.status in {"已读", "已处理"}:
        notification.read_at = notification.read_at or timestamp
    if payload.status == "已处理":
        notification.handled_at = notification.handled_at or timestamp

    db.commit()
    db.refresh(notification)
    return notification


def list_problems(
    db: Session,
    current_user: AuthContext,
    order_id: str | None = None,
    status: str | None = None,
) -> list[MoldingSampleProblem]:
    statement = select(MoldingSampleProblem)

    if order_id:
        order = load_order(db, order_id, current_user)
        statement = statement.where(MoldingSampleProblem.order_id == order.id)
    if status:
        statement = statement.where(MoldingSampleProblem.status == status)

    problems = list(
        db.scalars(
            statement.order_by(MoldingSampleProblem.created_at.desc(), MoldingSampleProblem.id.desc())
        ).all()
    )
    problem_order_ids = {problem.order_id for problem in problems}
    orders_by_id = {
        order.id: order
        for order in db.scalars(
            select(MoldingSampleOrder).where(MoldingSampleOrder.id.in_(problem_order_ids))
        ).all()
    }
    return [
        problem for problem in problems
        if (order := orders_by_id.get(problem.order_id)) is not None
        and has_order_read_access(current_user, order)
    ]


def create_problem(
    db: Session,
    payload: MoldingSampleProblemCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleProblem:
    order = load_order(db, payload.order_id, current_user)
    production_factory_id = ensure_production_order_permission(
        db,
        current_user,
        order,
        "molding_sample:production_fillback",
    )
    if order.status not in {"待生产", "生产中"}:
        raise HTTPException(status_code=403, detail="只有待生产或生产中的啤办单可以反馈生产问题")
    acquire_production_transition_guard(
        db,
        order,
        production_factory_id,
        order.status,
    )

    description = payload.description.strip()
    if not description:
        raise HTTPException(status_code=400, detail="问题反馈不能为空")

    reported_by = payload.reported_by.strip() or current_user.display_name
    problem = MoldingSampleProblem(
        id=f"{order.id}-problem-{uuid4().hex[:12]}",
        factory_id=production_factory_id,
        order_type="injection",
        order_id=order.id,
        order_number=order.order_number,
        description=description,
        reported_by=reported_by,
        status="待处理",
        created_at=now_precise_text(),
    )
    db.add(problem)
    append_audit(
        db,
        order,
        "生产问题反馈",
        current_user,
        order.status,
        order.status,
        description,
    )
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_TARGET_ROLE,
        event_type="生产问题反馈",
        title="啤机部反馈生产问题",
        message=f"啤办单 {order.id} 反馈问题：{description}",
        from_status=order.status,
        to_status=order.status,
        actor_name=reported_by,
        target_factory_id=order.factory_id,
    )
    db.commit()
    db.refresh(problem)
    return problem


def update_problem_status(
    db: Session,
    problem_id: str,
    payload: MoldingSampleProblemStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleProblem:
    if payload.status not in PROBLEM_STATUSES:
        raise HTTPException(status_code=400, detail="问题状态无效")

    problem = db.get(MoldingSampleProblem, problem_id)
    if problem is None:
        raise HTTPException(status_code=404, detail="问题反馈不存在")

    order = load_order(db, problem.order_id, current_user)
    ensure_molding_local_write(db, current_user, order.factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:edit_draft",
        order.factory_id,
        ENGINEERING_EDIT_DEPARTMENTS,
    )

    problem.status = payload.status
    problem.resolved_at = now_text() if payload.status == "已解决" else ""

    append_audit(
        db,
        order,
        "生产问题处理",
        current_user,
        order.status,
        order.status,
        f"{problem.description} -> {payload.status}",
    )
    db.commit()
    db.refresh(problem)
    return problem


def create_order(db: Session, payload: MoldingSampleCreateRequest, current_user: AuthContext) -> MoldingSampleOrder:
    ensure_molding_create_access(db, current_user, payload.order.factory_id)
    molding_factory_capability(payload.order.factory_id)

    status = INITIAL_ORDER_STATUS
    created_at = now_text()
    external = payload.order.send_to in {"发至湖南", "发至模厂"} or payload.order.workshop == "模厂"
    production_factory_id = None if external else normalize_production_factory_id(
        payload.order.factory_id,
        payload.order.production_factory_id,
        allow_unassigned=True,
    )
    assignment_version = 1 if production_factory_id else 0
    supplied_order_id = payload.order.id
    generates_order_id = not supplied_order_id.strip()
    attempts = GENERATED_ORDER_ID_ATTEMPTS if generates_order_id else 1

    for attempt in range(attempts):
        order_id = generate_molding_sample_order_id() if generates_order_id else supplied_order_id
        order = MoldingSampleOrder(
            **payload.order.model_dump(
                exclude={
                    "id",
                    "status",
                    "completed_date",
                    "created_at",
                    "updated_at",
                    "production_factory_id",
                    "production_assigned_at",
                    "production_assigned_by",
                    "production_assignment_version",
                }
            ),
            id=order_id,
            production_factory_id=production_factory_id,
            production_assigned_at=created_at if production_factory_id else "",
            production_assigned_by=current_user.display_name if production_factory_id else "",
            production_assignment_version=assignment_version,
            status=status,
            completed_date="",
            created_at=created_at,
            updated_at=created_at,
        )
        db.add(order)
        try:
            # Flush the order header before adding dependent rows. This makes the
            # database primary key the concurrency authority and keeps a losing
            # concurrent insert from surfacing as an unhandled 500 response.
            db.flush()
        except IntegrityError as exc:
            db.rollback()
            if db.get(MoldingSampleOrder, order_id) is None:
                raise
            if generates_order_id and attempt + 1 < attempts:
                continue
            if generates_order_id:
                raise HTTPException(status_code=503, detail="暂时无法生成唯一啤办单编号，请重试") from exc
            raise HTTPException(status_code=409, detail="啤办单编号已存在") from exc
        break

    explicit_item_ids = {
        item_payload.id.strip()
        for item_payload in payload.items
        if item_payload.id.strip()
    }
    generated_item_sequence = 1
    for index, item_payload in enumerate(payload.items, start=1):
        supplied_item_id = item_payload.id.strip()
        generates_item_id = generates_order_id or not supplied_item_id
        excluded_item_fields = {"order_id", "sort_order"}
        if generates_item_id:
            excluded_item_fields.add("id")
        item_data = normalized_item_data(item_payload, exclude=excluded_item_fields)
        if generates_item_id:
            while True:
                generated_item_id = f"{order.id}-{generated_item_sequence:03d}"
                generated_item_sequence += 1
                if generated_item_id not in explicit_item_ids:
                    break
            item_data["id"] = generated_item_id
        else:
            item_data["id"] = supplied_item_id
        db.add(
            MoldingSampleItem(
                **item_data,
                order_id=order.id,
                sort_order=item_payload.sort_order or index,
            )
        )

    if production_factory_id:
        append_dispatch_log(
            db,
            order,
            current_user,
            from_production_factory_id=None,
            to_production_factory_id=production_factory_id,
            action="本厂承接" if production_factory_id == order.factory_id else "首次派厂",
            reason="工程开单时确认生产承接厂。",
        )
    append_audit(
        db,
        order,
        "工程提交主管审核",
        current_user,
        status,
        status,
        f"工程开单完成；生产关系：{production_route_text(order)}。" if not external else "工程外发开单完成。",
    )
    if status == "待审核":
        append_supervisor_review_notification(db, order, from_status=status, actor_name=current_user.display_name)
    db.commit()
    db.refresh(order)
    return load_order(db, order.id, current_user)


def ensure_order_write_allowed(
    db: Session,
    order: MoldingSampleOrder,
    current_user: AuthContext,
    permission: str,
) -> None:
    ensure_molding_local_write(db, current_user, order.factory_id)
    if order.status in LOCKED_STATUSES:
        if has_permission_for_departments(
            current_user,
            "molding_sample:manager_review",
            order.factory_id,
            MANAGEMENT_DEPARTMENTS,
        ):
            return
        raise HTTPException(status_code=403, detail="当前状态不允许普通工程师改删")

    ensure_permission_for_departments(
        db,
        current_user,
        permission,
        order.factory_id,
        ENGINEERING_EDIT_DEPARTMENTS,
    )

    if has_permission_for_departments(
        current_user,
        "molding_sample:manager_review",
        order.factory_id,
        MANAGEMENT_DEPARTMENTS,
    ):
        return

    if not is_opening_engineer(order, current_user):
        raise HTTPException(status_code=403, detail="普通工程师只能修改本人创建的啤办单")


def ensure_order_delete_allowed(db: Session, order: MoldingSampleOrder, current_user: AuthContext) -> None:
    ensure_molding_local_write(db, current_user, order.factory_id)
    if order.status in LOCKED_STATUSES:
        ensure_permission_for_departments(
            db,
            current_user,
            "system:user_manage",
            order.factory_id,
            MANAGEMENT_DEPARTMENTS,
        )
        return

    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:delete_draft",
        order.factory_id,
        ENGINEERING_EDIT_DEPARTMENTS,
    )

    if has_permission_for_departments(
        current_user,
        "molding_sample:manager_review",
        order.factory_id,
        MANAGEMENT_DEPARTMENTS,
    ):
        return

    if not is_opening_engineer(order, current_user):
        raise HTTPException(status_code=403, detail="普通工程师只能删除本人创建的啤办单")


def update_order(db: Session, order_id: str, payload: MoldingSampleEditRequest, current_user: AuthContext) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    if payload.order.id != order_id:
        raise HTTPException(status_code=400, detail="啤办单 ID 不一致")

    ensure_order_write_allowed(db, order, current_user, "molding_sample:edit_draft")
    if payload.order.factory_id != order.factory_id:
        raise HTTPException(status_code=400, detail="啤办单厂区归属不可通过编辑接口变更")
    current_status = order.status
    current_created_at = order.created_at
    current_completed_date = order.completed_date
    current_external = is_external_order(order)
    payload_external = payload.order.send_to in {"发至湖南", "发至模厂"} or payload.order.workshop == "模厂"
    if current_external != payload_external:
        raise HTTPException(
            status_code=400,
            detail="不可通过全单编辑切换内部生产与外发流程，请按对应流程重新建单",
        )
    existing_items_by_id = {item.id: item for item in order.items}
    prepared_items: list[tuple[MoldingSampleItemIn, dict[str, Any], int]] = []

    if current_status == "已完成" and (
        set(existing_items_by_id) != {item.id for item in payload.items}
    ):
        raise HTTPException(status_code=400, detail="已完成单不可增删已结算明细，请先撤回完成")

    for index, item_payload in enumerate(payload.items, start=1):
        item_data = normalized_item_data(item_payload, exclude={"order_id", "sort_order"})
        existing_item = existing_items_by_id.get(item_payload.id)
        settlement_unchanged = existing_item is not None and material_settlement_inputs_match(existing_item, item_data)

        if current_status == "已完成" and not settlement_unchanged:
            raise HTTPException(status_code=400, detail="已完成单不可通过全单编辑变更已结算用料，请先撤回完成")
        if settlement_unchanged and existing_item is not None:
            item_data["actual_material_cost_components"] = [
                dict(component) for component in (existing_item.actual_material_cost_components or [])
            ]
        prepared_items.append((item_payload, item_data, index))

    order_data = payload.order.model_dump(
        exclude={
            "id",
            "factory_id",
            "production_factory_id",
            "production_assigned_at",
            "production_assigned_by",
            "production_assignment_version",
            "status",
            "completed_date",
            "created_at",
            "updated_at",
        }
    )
    for field, value in order_data.items():
        setattr(order, field, value)

    order.status = current_status
    order.completed_date = current_completed_date
    order.created_at = current_created_at
    order.updated_at = now_text()

    for existing_item in list(order.items):
        db.delete(existing_item)
    db.flush()

    for item_payload, item_data, index in prepared_items:
        db.add(
            MoldingSampleItem(
                **item_data,
                order_id=order.id,
                sort_order=item_payload.sort_order or index,
            )
        )

    append_audit(
        db,
        order,
        "修改啤办单",
        current_user,
        current_status,
        current_status,
        "单头或明细已更新。",
    )
    db.commit()
    db.expire_all()
    return load_order(db, order_id, current_user)


def has_production_assignment_artifacts(db: Session, order: MoldingSampleOrder) -> bool:
    items = db.scalars(
        select(MoldingSampleItem)
        .where(MoldingSampleItem.order_id == order.id)
        .execution_options(populate_existing=True)
    ).all()
    item_has_production_data = any(
        item.production_machine
        or item.receipt_no
        or item.collected_weight_kg is not None
        or item.actual_weight_kg is not None
        or item.actual_amount_hkd is not None
        or item.injection_cost is not None
        or item.injection_cost_hkd is not None
        or bool(item.actual_material_cost_components)
        for item in items
    )
    if item_has_production_data:
        return True
    return bool(
        db.scalar(
            select(
                or_(
                    exists().where(MoldingSampleTrialReport.order_id == order.id),
                    exists().where(MoldingSampleProblem.order_id == order.id),
                    exists().where(MoldingSampleRequisition.order_id == order.id),
                )
            )
        )
    )


def update_production_assignment(
    db: Session,
    order_id: str,
    payload: MoldingSampleProductionAssignmentRequest,
    current_user: AuthContext,
) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    ensure_molding_local_write(db, current_user, order.factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:dispatch",
        order.factory_id,
        ENGINEERING_EDIT_DEPARTMENTS,
    )
    if is_external_order(order):
        raise HTTPException(status_code=400, detail="外发湖南或模厂的啤办单不进入内部跨厂派厂流程")
    capability = molding_factory_capability(order.factory_id)
    if bool(capability["has_molding_department"]):
        raise HTTPException(status_code=400, detail="该厂区啤办单固定由本厂承接，无需派厂")
    if order.status not in DISPATCHABLE_STATUSES:
        raise HTTPException(status_code=409, detail="生产已经开始或完成，不能改派承接厂")
    if has_production_assignment_artifacts(db, order):
        raise HTTPException(status_code=409, detail="单据已有生产、试模、问题或领料数据，不能直接改派")

    new_production_factory_id = normalize_production_factory_id(
        order.factory_id,
        payload.production_factory_id,
        allow_unassigned=False,
    )
    assert new_production_factory_id is not None
    old_production_factory_id = production_factory_id_for_order(order, require_assigned=False)
    if old_production_factory_id == new_production_factory_id:
        raise HTTPException(status_code=400, detail="新的生产承接厂与当前承接厂相同")
    if order.production_assignment_version != payload.expected_assignment_version:
        raise HTTPException(status_code=409, detail="派厂信息已被其他人更新，请刷新后重试")
    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="派厂或改派原因不能为空")

    timestamp = now_text()
    update_result = db.execute(
        update(MoldingSampleOrder)
        .where(
            MoldingSampleOrder.id == order.id,
            MoldingSampleOrder.production_assignment_version == payload.expected_assignment_version,
            MoldingSampleOrder.status.in_(DISPATCHABLE_STATUSES),
        )
        .values(
            production_factory_id=new_production_factory_id,
            production_assigned_at=timestamp,
            production_assigned_by=current_user.display_name,
            production_assignment_version=payload.expected_assignment_version + 1,
            updated_at=timestamp,
        )
        .execution_options(synchronize_session=False)
    )
    if update_result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="派厂信息或订单状态已变化，请刷新后重试")

    db.flush()
    db.refresh(order)
    if has_production_assignment_artifacts(db, order):
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="派厂期间已产生生产、试模、问题或领料数据，不能改派",
        )
    action = "首次派厂" if old_production_factory_id is None else "改派生产厂"
    append_dispatch_log(
        db,
        order,
        current_user,
        from_production_factory_id=old_production_factory_id,
        to_production_factory_id=new_production_factory_id,
        action=action,
        reason=reason,
    )
    append_audit(
        db,
        order,
        action,
        current_user,
        order.status,
        order.status,
        (
            f"{factory_label(old_production_factory_id)} → "
            f"{factory_label(new_production_factory_id)}；原因：{reason}"
        ),
    )

    if old_production_factory_id:
        mark_order_notifications_handled(
            db,
            order.id,
            PRODUCTION_TASK_MODULE,
            actor_name=current_user.display_name,
            target_factory_id=old_production_factory_id,
        )
    if order.status == "待生产":
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="生产改派" if old_production_factory_id else "生产派厂",
            title="收到跨厂啤办生产任务",
            message=f"啤办单 {order.id} 已派至本厂生产（{production_route_text(order)}）。",
            from_status=order.status,
            to_status=order.status,
            actor_name=current_user.display_name,
            target_factory_id=new_production_factory_id,
        )
    append_notification(
        db,
        order,
        target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
        target_role=ENGINEERING_TARGET_ROLE,
        event_type="生产派厂变更",
        title="啤办生产承接厂已更新",
        message=(
            f"啤办单 {order.id} 的生产关系已更新为 {production_route_text(order)}。"
            f"原因：{reason}"
        ),
        from_status=order.status,
        to_status=order.status,
        actor_name=current_user.display_name,
        target_factory_id=order.factory_id,
    )
    db.commit()
    db.expire_all()
    return load_order(db, order.id, current_user)


def acquire_production_transition_guard(
    db: Session,
    order: MoldingSampleOrder,
    production_factory_id: str,
    expected_status: str,
) -> None:
    """Serialize production state changes against concurrent reassignment."""
    assignment_version = order.production_assignment_version
    assignment_matches = or_(
        MoldingSampleOrder.production_factory_id == production_factory_id,
        and_(
            MoldingSampleOrder.production_factory_id.is_(None),
            MoldingSampleOrder.factory_id == production_factory_id,
        ),
    )
    guard_result = db.execute(
        update(MoldingSampleOrder)
        .where(
            MoldingSampleOrder.id == order.id,
            MoldingSampleOrder.status == expected_status,
            MoldingSampleOrder.production_assignment_version == assignment_version,
            assignment_matches,
        )
        .values(updated_at=MoldingSampleOrder.updated_at)
        .execution_options(synchronize_session=False)
    )
    if guard_result.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="生产状态或承接厂已变化，请刷新任务后重试",
        )
    db.flush()
    db.refresh(order)


def acquire_approval_transition_guard(
    db: Session,
    order_id: str,
    current_user: AuthContext,
    *,
    expected_status: str,
    idempotent_statuses: frozenset[str],
    invalid_status_detail: str,
) -> tuple[MoldingSampleOrder, bool]:
    """Lock an approval row while accepting a completed retry as idempotent."""

    for _attempt in range(3):
        order = load_order(db, order_id, current_user)
        if order.status != expected_status:
            if order.status in idempotent_statuses:
                return order, True
            raise HTTPException(status_code=403, detail=invalid_status_detail)

        guard_result = db.execute(
            update(MoldingSampleOrder)
            .where(
                MoldingSampleOrder.id == order.id,
                MoldingSampleOrder.status == expected_status,
                MoldingSampleOrder.production_assignment_version
                == order.production_assignment_version,
            )
            .values(updated_at=MoldingSampleOrder.updated_at)
            .execution_options(synchronize_session=False)
        )
        if guard_result.rowcount == 1:
            db.flush()
            db.refresh(order)
            return order, False
        db.rollback()

    raise HTTPException(
        status_code=409,
        detail="审批状态或生产承接厂已变化，请刷新后重试",
    )


def delete_order(
    db: Session,
    order_id: str,
    current_user: AuthContext,
) -> None:
    order = load_order(db, order_id, current_user)
    ensure_order_delete_allowed(db, order, current_user)
    db.delete(order)
    db.commit()


def resolve_inventory_factory_id(
    db: Session,
    current_user: AuthContext,
    permission: str,
    requested_factory_id: str | None = None,
) -> str:
    requested = (requested_factory_id or "").strip()
    if requested:
        molding_factory_capability(requested)
        ensure_molding_local_write(db, current_user, requested)
        ensure_permission_for_departments(
            db,
            current_user,
            permission,
            requested,
            WAREHOUSE_DEPARTMENTS,
        )
        return requested

    primary_factory_id = current_user.profile.primary_factory_id.strip() if current_user.profile else ""
    candidates = tuple(dict.fromkeys((primary_factory_id, *user_factory_candidates(current_user))))
    for factory_id in candidates:
        if not factory_id or factory_id == "*":
            continue
        if has_permission_for_departments(
            current_user,
            permission,
            factory_id,
            WAREHOUSE_DEPARTMENTS,
        ):
            return factory_id
    ensure_permission_in_any_factory(db, current_user, permission, WAREHOUSE_DEPARTMENTS)
    raise HTTPException(status_code=400, detail="无法确定库存操作厂区，请明确传入 factory_id")


def list_inventory_batches(
    db: Session,
    current_user: AuthContext,
    factory_id: str | None = None,
    material: str | None = None,
) -> list[MoldingSampleInventoryBatch]:
    statement = select(MoldingSampleInventoryBatch).order_by(
        MoldingSampleInventoryBatch.factory_id,
        MoldingSampleInventoryBatch.material,
        MoldingSampleInventoryBatch.batch_no,
    )
    if factory_id:
        resolve_inventory_factory_id(
            db,
            current_user,
            "molding_sample:inventory_issue",
            factory_id,
        )
        statement = statement.where(MoldingSampleInventoryBatch.factory_id == factory_id)
    else:
        ensure_permission_in_any_factory(
            db,
            current_user,
            "molding_sample:inventory_issue",
            WAREHOUSE_DEPARTMENTS,
        )
    if material:
        statement = statement.where(MoldingSampleInventoryBatch.material == material.strip())

    return [
        batch
        for batch in db.scalars(statement).all()
        if has_permission_for_departments(
            current_user,
            "molding_sample:inventory_issue",
            batch.factory_id,
            WAREHOUSE_DEPARTMENTS,
        )
    ]


def create_inventory_batch(
    db: Session,
    payload: InventoryBatchCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleInventoryBatch:
    factory_id = resolve_inventory_factory_id(
        db,
        current_user,
        "molding_sample:inventory_issue",
        payload.factory_id,
    )
    if payload.initial_weight_kg <= 0:
        raise HTTPException(status_code=400, detail="批次初始重量必须大于 0")

    material = payload.material.strip()
    batch_no = payload.batch_no.strip()
    existing_batch = db.scalar(
        select(MoldingSampleInventoryBatch).where(
            MoldingSampleInventoryBatch.factory_id == factory_id,
            MoldingSampleInventoryBatch.material == material,
            MoldingSampleInventoryBatch.batch_no == batch_no,
        )
    )
    if existing_batch:
        raise HTTPException(status_code=409, detail="库存批次已存在")

    now = now_text()
    batch = MoldingSampleInventoryBatch(
        id=f"batch-{uuid4().hex}",
        factory_id=factory_id,
        material=material,
        batch_no=batch_no,
        location=payload.location.strip(),
        initial_weight_kg=round_weight(payload.initial_weight_kg),
        available_weight_kg=round_weight(payload.initial_weight_kg),
        created_at=now,
        updated_at=now,
    )
    db.add(batch)
    append_inventory_movement(
        db,
        batch=batch,
        movement_type="新增批次",
        quantity_kg=batch.initial_weight_kg,
        before_weight_kg=0,
        after_weight_kg=batch.available_weight_kg,
        actor_name=current_user.display_name,
        reason="新增库存批次。",
    )
    db.commit()
    db.refresh(batch)
    return batch


def append_inventory_movement(
    db: Session,
    batch: MoldingSampleInventoryBatch,
    movement_type: str,
    quantity_kg: float,
    before_weight_kg: float,
    after_weight_kg: float,
    requisition: MoldingSampleRequisition | None = None,
    actor_name: str = "仓库",
    reason: str = "",
) -> None:
    db.add(
        MoldingSampleInventoryMovement(
            factory_id=batch.factory_id,
            batch_id=batch.id,
            batch_no=batch.batch_no,
            requisition_id=requisition.id if requisition else "",
            req_number=requisition.req_number if requisition else "",
            material=batch.material,
            movement_type=movement_type,
            quantity_kg=round_weight(quantity_kg),
            before_weight_kg=round_weight(before_weight_kg),
            after_weight_kg=round_weight(after_weight_kg),
            actor_name=actor_name,
            reason=reason,
            created_at=now_precise_text(),
        )
    )


def list_inventory_movements(
    db: Session,
    current_user: AuthContext,
    factory_id: str | None = None,
    batch_id: str | None = None,
    material: str | None = None,
    requisition_id: str | None = None,
) -> list[MoldingSampleInventoryMovement]:
    statement = select(MoldingSampleInventoryMovement).order_by(MoldingSampleInventoryMovement.id.desc())
    if factory_id:
        resolve_inventory_factory_id(
            db,
            current_user,
            "molding_sample:inventory_issue",
            factory_id,
        )
        statement = statement.where(MoldingSampleInventoryMovement.factory_id == factory_id)
    else:
        ensure_permission_in_any_factory(
            db,
            current_user,
            "molding_sample:inventory_issue",
            WAREHOUSE_DEPARTMENTS,
        )
    if batch_id:
        statement = statement.where(MoldingSampleInventoryMovement.batch_id == batch_id)
    if material:
        statement = statement.where(MoldingSampleInventoryMovement.material == material.strip())
    if requisition_id:
        statement = statement.where(MoldingSampleInventoryMovement.requisition_id == requisition_id)

    return [
        movement
        for movement in db.scalars(statement).all()
        if has_permission_for_departments(
            current_user,
            "molding_sample:inventory_issue",
            movement.factory_id,
            WAREHOUSE_DEPARTMENTS,
        )
    ]


def next_requisition_number(db: Session, date: str) -> str:
    date_token = date.replace("-", "")
    prefix = f"LL-{date_token}-"
    existing_numbers = db.scalars(
        select(MoldingSampleRequisition.req_number).where(MoldingSampleRequisition.req_number.like(f"{prefix}%"))
    ).all()
    max_sequence = 0

    for req_number in existing_numbers:
        try:
            max_sequence = max(max_sequence, int(req_number.rsplit("-", 1)[1]))
        except (IndexError, ValueError):
            continue

    return f"{prefix}{max_sequence + 1:03d}"


def list_requisitions(
    db: Session,
    current_user: AuthContext,
    order_id: str | None = None,
) -> list[MoldingSampleRequisition]:
    ensure_permission_in_any_factory(
        db,
        current_user,
        "molding_sample:warehouse_requisition",
        WAREHOUSE_DEPARTMENTS,
    )
    statement = select(MoldingSampleRequisition).order_by(
        MoldingSampleRequisition.date.desc(),
        MoldingSampleRequisition.req_number.desc(),
    )
    if order_id:
        order = load_order(db, order_id)
        if not is_production_task_order(order):
            raise HTTPException(status_code=403, detail="只有正式生产阶段可以查看领料单")
        production_factory_id = production_factory_id_for_order(order)
        assert production_factory_id is not None
        ensure_molding_local_write(db, current_user, production_factory_id)
        ensure_permission_for_departments(
            db,
            current_user,
            "molding_sample:warehouse_requisition",
            production_factory_id,
            WAREHOUSE_DEPARTMENTS,
        )
        statement = statement.where(MoldingSampleRequisition.order_id == order_id)

    requisitions = list(db.scalars(statement).all())
    return [
        requisition
        for requisition in requisitions
        if has_permission_for_departments(
            current_user,
            "molding_sample:warehouse_requisition",
            requisition.factory_id,
            WAREHOUSE_DEPARTMENTS,
        )
    ]


def create_requisition(
    db: Session,
    payload: RequisitionCreateRequest,
    current_user: AuthContext,
) -> MoldingSampleRequisition:
    if payload.requested_weight_kg <= 0:
        raise HTTPException(status_code=400, detail="申请重量必须大于 0")

    order = load_order(db, payload.order_id)
    if order.status not in {"待生产", "生产中"} or is_external_order(order):
        raise HTTPException(status_code=403, detail="只有待生产或生产中的内部啤办单可以创建领料单")
    production_factory_id = production_factory_id_for_order(order)
    assert production_factory_id is not None
    ensure_molding_local_write(db, current_user, production_factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:warehouse_requisition",
        production_factory_id,
        WAREHOUSE_DEPARTMENTS,
    )
    acquire_production_transition_guard(
        db,
        order,
        production_factory_id,
        order.status,
    )
    material = payload.material.strip()
    notes = payload.notes.strip()
    if notes:
        existing_requisition = db.scalar(
            select(MoldingSampleRequisition).where(
                MoldingSampleRequisition.order_id == order.id,
                MoldingSampleRequisition.material == material,
                MoldingSampleRequisition.notes == notes,
            )
        )
        if existing_requisition:
            raise HTTPException(status_code=409, detail="该明细已生成领料单")

    requisition = MoldingSampleRequisition(
        id=f"req-{uuid4().hex}",
        factory_id=production_factory_id,
        req_number=next_requisition_number(db, payload.date),
        date=payload.date,
        order_id=order.id,
        order_number=order.order_number,
        material=material,
        requested_weight_kg=payload.requested_weight_kg,
        applicant=payload.applicant.strip(),
        notes=notes,
        inventory_batch_id="",
        inventory_batch_no="",
        status="待出库",
        issued_at="",
        created_at=now_text(),
        updated_at=now_text(),
    )
    db.add(requisition)
    db.commit()
    db.refresh(requisition)
    return requisition


def update_requisition_status(
    db: Session,
    requisition_id: str,
    payload: RequisitionStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleRequisition:
    requisition = db.get(MoldingSampleRequisition, requisition_id)
    if not requisition:
        raise HTTPException(status_code=404, detail="领料单不存在")
    if payload.status not in {"待出库", "已出库"}:
        raise HTTPException(status_code=400, detail="领料单状态无效")
    order = load_order(db, requisition.order_id)
    production_factory_id = production_factory_id_for_order(order)
    assert production_factory_id is not None
    if requisition.factory_id != production_factory_id:
        raise HTTPException(status_code=409, detail="领料单厂区与当前生产承接厂不一致")
    ensure_molding_local_write(db, current_user, production_factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:inventory_issue",
        production_factory_id,
        WAREHOUSE_DEPARTMENTS,
    )

    previous_status = requisition.status
    if payload.status == "已出库" and payload.inventory_batch_id:
        if previous_status == "已出库" and requisition.inventory_batch_id:
            raise HTTPException(status_code=400, detail="领料单已出库")

        batch = db.get(MoldingSampleInventoryBatch, payload.inventory_batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="库存批次不存在")
        if batch.factory_id != requisition.factory_id:
            raise HTTPException(status_code=400, detail="不能跨厂区使用库存批次")
        if batch.material != requisition.material:
            raise HTTPException(status_code=400, detail="批次原料不匹配")
        if batch.available_weight_kg < requisition.requested_weight_kg:
            raise HTTPException(status_code=400, detail="库存不足")

        before_weight = batch.available_weight_kg
        after_weight = round_weight(before_weight - requisition.requested_weight_kg)
        batch.available_weight_kg = after_weight
        batch.updated_at = now_text()
        requisition.inventory_batch_id = batch.id
        requisition.inventory_batch_no = batch.batch_no
        append_inventory_movement(
            db,
            batch=batch,
            movement_type="出库扣减",
            quantity_kg=-requisition.requested_weight_kg,
            before_weight_kg=before_weight,
            after_weight_kg=after_weight,
            requisition=requisition,
            actor_name=current_user.display_name,
            reason="领料单出库扣减库存。",
        )

    if payload.status == "待出库" and previous_status == "已出库" and requisition.inventory_batch_id:
        batch = db.get(MoldingSampleInventoryBatch, requisition.inventory_batch_id)
        if batch:
            before_weight = batch.available_weight_kg
            after_weight = round_weight(before_weight + requisition.requested_weight_kg)
            batch.available_weight_kg = after_weight
            batch.updated_at = now_text()
            append_inventory_movement(
                db,
                batch=batch,
                movement_type="撤回出库",
                quantity_kg=requisition.requested_weight_kg,
                before_weight_kg=before_weight,
                after_weight_kg=after_weight,
                requisition=requisition,
                actor_name=current_user.display_name,
                reason="领料单状态退回待出库，恢复库存。",
            )
        requisition.inventory_batch_id = ""
        requisition.inventory_batch_no = ""

    requisition.status = payload.status
    requisition.issued_at = payload.issued_at if payload.status == "已出库" else ""
    if payload.status == "已出库" and not requisition.issued_at:
        requisition.issued_at = now_text()
    requisition.updated_at = now_text()
    db.commit()
    db.refresh(requisition)
    return requisition


def delete_requisition(db: Session, requisition_id: str, current_user: AuthContext) -> None:
    requisition = db.get(MoldingSampleRequisition, requisition_id)
    if not requisition:
        raise HTTPException(status_code=404, detail="领料单不存在")
    order = load_order(db, requisition.order_id)
    production_factory_id = production_factory_id_for_order(order)
    assert production_factory_id is not None
    if requisition.factory_id != production_factory_id:
        raise HTTPException(status_code=409, detail="领料单厂区与当前生产承接厂不一致")
    ensure_molding_local_write(db, current_user, production_factory_id)
    ensure_permission_for_departments(
        db,
        current_user,
        "molding_sample:warehouse_requisition",
        production_factory_id,
        WAREHOUSE_DEPARTMENTS,
    )

    if requisition.status == "已出库" and requisition.inventory_batch_id:
        batch = db.get(MoldingSampleInventoryBatch, requisition.inventory_batch_id)
        if batch:
            before_weight = batch.available_weight_kg
            after_weight = round_weight(before_weight + requisition.requested_weight_kg)
            batch.available_weight_kg = after_weight
            batch.updated_at = now_text()
            append_inventory_movement(
                db,
                batch=batch,
                movement_type="删除领料单恢复",
                quantity_kg=requisition.requested_weight_kg,
                before_weight_kg=before_weight,
                after_weight_kg=after_weight,
                requisition=requisition,
                actor_name=current_user.display_name,
                reason="删除已出库领料单，恢复库存。",
            )

    db.delete(requisition)
    db.commit()


def completion_missing_item_ids(order: MoldingSampleOrder) -> list[str]:
    if is_external_order(order):
        return []

    return [
        item.id
        for item in order.items
        if not item.actual_weight_kg or item.actual_weight_kg <= 0
    ]


def is_opening_engineer(order: MoldingSampleOrder, current_user: AuthContext) -> bool:
    def same_text(left: str | None, right: str | None) -> bool:
        return bool(left and right and left.strip() == right.strip())

    submit_actions = ("工程提交", "工程开单")
    submitter_user_ids = {
        audit.actor_user_id
        for audit in order.audit_logs
        if audit.action.startswith(submit_actions) and audit.actor_user_id
    }
    if submitter_user_ids:
        return current_user.id in submitter_user_ids

    submitter_names = {
        audit.actor_name.strip()
        for audit in order.audit_logs
        if audit.action.startswith(submit_actions) and audit.actor_name and audit.actor_name.strip()
    }
    if submitter_names:
        return current_user.display_name.strip() in submitter_names

    return same_text(order.eng_name, current_user.display_name)


def calculate_item_costs(
    db: Session,
    order: MoldingSampleOrder,
    item: MoldingSampleItem,
    force_material_amount: bool = False,
) -> None:
    prices = get_prices(db)
    rate = get_exchange_rate(db)
    external = is_external_order(order)
    material_weight = item.collected_weight_kg or item.required_material_kg if external else item.actual_weight_kg
    material_amount_hkd, material_cost_components = calculate_material_amount_hkd(
        material_weight,
        item.material,
        item.material_components,
        prices,
    )

    if external:
        item.actual_weight_kg = material_weight

    if force_material_amount or not item.actual_amount_hkd:
        item.actual_amount_hkd = material_amount_hkd
        item.actual_material_cost_components = material_cost_components if material_amount_hkd is not None else []

    if external:
        item.injection_cost_hkd = None
        item.exchange_rate_at_save = None
    elif item.injection_cost is not None:
        item.injection_cost_hkd = round_money(item.injection_cost * rate)
        item.exchange_rate_at_save = rate


def recalculate_order_costs(db: Session, order: MoldingSampleOrder, force_material_amount: bool = False) -> None:
    for item in order.items:
        calculate_item_costs(db, order, item, force_material_amount=force_material_amount)


def update_order_items(
    db: Session,
    order_id: str,
    items: list[MoldingSampleItemIn],
    current_user: AuthContext,
) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    production_factory_id = ensure_production_order_permission(
        db,
        current_user,
        order,
        "molding_sample:production_fillback",
    )
    if order.status not in {"待生产", "生产中"}:
        raise HTTPException(status_code=403, detail="只有待生产或生产中的啤办单可以回填生产数据")
    acquire_production_transition_guard(
        db,
        order,
        production_factory_id,
        order.status,
    )

    items_by_id = {item.id: item for item in order.items}

    for patch in items:
        item = items_by_id.get(patch.id)
        if not item:
            raise HTTPException(status_code=404, detail=f"明细不存在：{patch.id}")

        patch_data = patch.model_dump(exclude_unset=True)
        invalid_fields = set(patch_data) - ALLOWED_ITEM_PATCH_FIELDS - {"id", "order_id"}
        if invalid_fields:
            raise HTTPException(status_code=400, detail=f"不允许更新字段：{', '.join(sorted(invalid_fields))}")

        for field in ALLOWED_ITEM_PATCH_FIELDS:
            if field in patch_data:
                setattr(item, field, patch_data[field])

        calculate_item_costs(db, order, item, force_material_amount=True)

    order.updated_at = now_text()
    db.commit()
    return load_order(db, order_id, current_user)


def upsert_trial_report(
    db: Session,
    order_id: str,
    item_id: str,
    payload: MoldingSampleTrialReportUpsertRequest,
    current_user: AuthContext,
) -> MoldingSampleTrialReport:
    """Persist the printable trial report separately from production cost/fillback rows."""

    order = load_order(db, order_id, current_user)
    production_factory_id = ensure_production_order_permission(
        db,
        current_user,
        order,
        "molding_sample:production_fillback",
    )
    if order.status not in {"待生产", "生产中"}:
        raise HTTPException(status_code=403, detail="只有待生产或生产中的啤办单可以填写试模报告")
    acquire_production_transition_guard(
        db,
        order,
        production_factory_id,
        order.status,
    )

    if item_id not in {item.id for item in order.items}:
        raise HTTPException(status_code=404, detail=f"模具明细不存在：{item_id}")

    report = db.scalar(
        select(MoldingSampleTrialReport).where(
            MoldingSampleTrialReport.order_id == order.id,
            MoldingSampleTrialReport.item_id == item_id,
        )
    )
    timestamp = now_precise_text()
    report_data = payload.data.model_dump()

    if report is None:
        report = MoldingSampleTrialReport(
            id=f"{order.id}-trial-{uuid4().hex[:12]}",
            factory_id=production_factory_id,
            order_id=order.id,
            item_id=item_id,
            data=report_data,
            created_by=current_user.display_name,
            created_at=timestamp,
            updated_by=current_user.display_name,
            updated_at=timestamp,
        )
        db.add(report)
        audit_action = "填写试模报告"
    else:
        report.data = report_data
        report.updated_by = current_user.display_name
        report.updated_at = timestamp
        audit_action = "更新试模报告"

    order.updated_at = now_text()
    append_audit(
        db,
        order,
        audit_action,
        current_user,
        order.status,
        order.status,
        f"模具明细：{item_id}",
    )
    db.commit()
    db.refresh(report)
    return report


def transition_status(
    db: Session,
    order_id: str,
    request: MoldingSampleStatusRequest,
    current_user: AuthContext,
) -> MoldingSampleOrder:
    order = load_order(db, order_id, current_user)
    from_status = order.status
    action = request.action
    next_status: str | None = None

    if action == "主管通过":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:supervisor_review", order.factory_id, ENGINEERING_DEPARTMENTS
        )
        order, approval_already_applied = acquire_approval_transition_guard(
            db,
            order.id,
            current_user,
            expected_status="待审核",
            idempotent_statuses=frozenset({"待经理审核", *PRODUCTION_TASK_STATUSES}),
            invalid_status_detail="只有指定主管可以审核待审核单",
        )
        if approval_already_applied:
            return order
        from_status = order.status
        if is_external_order(order):
            next_status = "已完成"
            order.completed_date = business_today()
            recalculate_order_costs(db, order, force_material_amount=True)
        else:
            production_factory_id_for_order(order)
            next_status = "待生产"
    elif action == "主管驳回":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:supervisor_review", order.factory_id, ENGINEERING_DEPARTMENTS
        )
        if order.status != "待审核":
            raise HTTPException(status_code=403, detail="只有指定主管可以驳回待审核单")
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "经理通过":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:manager_review", order.factory_id, MANAGEMENT_DEPARTMENTS
        )
        order, approval_already_applied = acquire_approval_transition_guard(
            db,
            order.id,
            current_user,
            expected_status="待经理审核",
            idempotent_statuses=PRODUCTION_TASK_STATUSES,
            invalid_status_detail="只有经理可以终审待经理审核单",
        )
        if approval_already_applied:
            return order
        from_status = order.status
        if is_external_order(order):
            next_status = "已完成"
            order.completed_date = business_today()
            recalculate_order_costs(db, order, force_material_amount=True)
        else:
            production_factory_id_for_order(order)
            next_status = "待生产"
    elif action == "经理驳回":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:manager_review", order.factory_id, MANAGEMENT_DEPARTMENTS
        )
        if order.status != "待经理审核":
            raise HTTPException(status_code=403, detail="只有经理可以驳回待经理审核单")
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "工程重提":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:edit_draft", order.factory_id, ENGINEERING_EDIT_DEPARTMENTS
        )
        if order.status not in {"已驳回", "已撤回"}:
            raise HTTPException(status_code=403, detail="只有工程部可以重提已驳回或已撤回单")
        next_status = "待审核"
        order.reject_reason = ""
    elif action == "工程撤回":
        ensure_molding_local_write(db, current_user, order.factory_id)
        ensure_permission_for_departments(
            db, current_user, "molding_sample:edit_draft", order.factory_id, ENGINEERING_EDIT_DEPARTMENTS
        )
        if order.status != "待审核":
            raise HTTPException(status_code=403, detail="只有开单工程师可以撤回待审核单")
        if not is_opening_engineer(order, current_user):
            raise HTTPException(status_code=403, detail="只有开单工程师可以撤回本人提交的待审核单")
        next_status = "已撤回"
    elif action == "开始处理":
        production_factory_id = ensure_production_order_permission(
            db,
            current_user,
            order,
            "molding_sample:production_start",
        )
        if order.status != "待生产":
            raise HTTPException(status_code=403, detail="只有啤机部可以开始处理待生产单")
        acquire_production_transition_guard(db, order, production_factory_id, "待生产")
        next_status = "生产中"
    elif action == "撤回开始生产":
        production_factory_id = ensure_production_order_permission(
            db,
            current_user,
            order,
            "molding_sample:production_start",
        )
        if order.status != "生产中":
            raise HTTPException(status_code=403, detail="只有啤机部可以撤回生产中单")
        acquire_production_transition_guard(db, order, production_factory_id, "生产中")
        next_status = "待生产"
        order.completed_date = ""
    elif action == "标记完成":
        production_factory_id = ensure_production_order_permission(
            db,
            current_user,
            order,
            "molding_sample:production_complete",
        )
        if order.status != "生产中":
            raise HTTPException(status_code=403, detail="只有啤机部可以完成生产中单")
        acquire_production_transition_guard(db, order, production_factory_id, "生产中")

        missing_ids = completion_missing_item_ids(order)
        if missing_ids:
            raise HTTPException(status_code=400, detail=f"actual_weight_kg 缺失：{', '.join(missing_ids[:5])}")

        next_status = "已完成"
        order.completed_date = business_today()
        recalculate_order_costs(db, order, force_material_amount=True)
    elif action == "撤回完成":
        production_factory_id = ensure_production_order_permission(
            db,
            current_user,
            order,
            "molding_sample:production_complete",
        )
        if order.status != "已完成":
            raise HTTPException(status_code=403, detail="只有啤机部可以撤回已完成单")
        acquire_production_transition_guard(db, order, production_factory_id, "已完成")

        next_status = "生产中"
        order.completed_date = ""
    else:
        raise HTTPException(status_code=400, detail="未知状态动作")

    order.status = next_status
    order.updated_at = now_text()
    append_audit(db, order, action, current_user, from_status, next_status, request.reason)
    if action in {"主管通过", "主管驳回", "经理通过", "经理驳回", "工程撤回", "工程重提"}:
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            actor_name=current_user.display_name,
        )

    if action == "工程重提":
        append_supervisor_review_notification(
            db,
            order,
            from_status=from_status,
            actor_name=current_user.display_name,
        )
    elif action in {"主管驳回", "经理驳回"}:
        append_engineering_rework_notification(
            db,
            order,
            from_status=from_status,
            to_status=next_status,
            reason=request.reason,
            actor_name=current_user.display_name,
        )
    elif action in {"主管通过", "经理通过"} and next_status == "待经理审核":
        append_manager_review_notification(
            db,
            order,
            from_status=from_status,
            actor_name=current_user.display_name,
        )
    elif action in {"主管通过", "经理通过"} and next_status == "待生产":
        production_factory_id = production_factory_id_for_order(order)
        assert production_factory_id is not None
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="待生产",
            title="啤办单已到待生产",
            message=f"啤办单 {order.id} 已审核通过，请按 {production_route_text(order)} 执行生产。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
            target_factory_id=production_factory_id,
        )
    elif action == "开始处理":
        production_factory_id = production_factory_id_for_order(order)
        assert production_factory_id is not None
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=PRODUCTION_TASK_MODULE,
            actor_name=current_user.display_name,
            target_factory_id=production_factory_id,
        )
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="生产开始",
            title="啤机部已开始生产",
            message=f"啤办单 {order.id} 已由 {factory_label(production_factory_id)} 啤机部开始处理。",
            from_status=from_status,
            to_status=next_status,
            status="已处理",
            actor_name=current_user.display_name,
            target_factory_id=production_factory_id,
        )
    elif action == "撤回开始生产":
        production_factory_id = production_factory_id_for_order(order)
        assert production_factory_id is not None
        append_notification(
            db,
            order,
            target_module=PRODUCTION_TASK_MODULE,
            target_role=PRODUCTION_TARGET_ROLE,
            event_type="生产开始撤回",
            title="啤办开始生产已撤回",
            message=f"{factory_label(production_factory_id)}啤机部已撤回啤办单 {order.id} 的开始生产动作，任务回到待生产。",
            from_status=from_status,
            to_status=next_status,
            status="已处理",
            actor_name=current_user.display_name,
            target_factory_id=production_factory_id,
        )
    elif action == "标记完成":
        production_factory_id = production_factory_id_for_order(order)
        assert production_factory_id is not None
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=PRODUCTION_TASK_MODULE,
            actor_name=current_user.display_name,
            target_factory_id=production_factory_id,
        )
        append_notification(
            db,
            order,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            target_role=ENGINEERING_TARGET_ROLE,
            event_type="生产完成回传",
            title="啤办生产完成",
            message=f"{factory_label(production_factory_id)}啤机部已完成啤办单 {order.id}，实际用料和啤办费已回传至{factory_label(order.factory_id)}。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
            target_factory_id=order.factory_id,
        )
    elif action == "撤回完成":
        mark_order_notifications_handled(
            db,
            order_id=order.id,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            actor_name=current_user.display_name,
        )
        append_notification(
            db,
            order,
            target_module=ENGINEERING_MOLDING_SAMPLE_MODULE,
            target_role=ENGINEERING_TARGET_ROLE,
            event_type="生产完成撤回",
            title="啤办完成回传已撤回",
            message=f"{factory_label(production_factory_id_for_order(order))}啤机部已撤回啤办单 {order.id} 的完成回传，单据回到生产中等待修正后重新完成。",
            from_status=from_status,
            to_status=next_status,
            actor_name=current_user.display_name,
            target_factory_id=order.factory_id,
        )
    db.commit()
    db.expire_all()
    return load_order(db, order_id, current_user)


def replace_material_prices(
    db: Session,
    prices: list[MaterialPriceIn],
    rmb_to_hkd_rate: float,
    current_user: AuthContext,
) -> dict[str, Any]:
    if rmb_to_hkd_rate <= 0:
        raise HTTPException(status_code=400, detail="汇率必须大于 0")
    ensure_permission_in_any_factory(
        db,
        current_user,
        "molding_sample:price_update",
        MANAGEMENT_DEPARTMENTS,
    )

    db.query(MoldingSampleMaterialPrice).delete()
    for price in prices:
        if price.unit_price <= 0:
            raise HTTPException(status_code=400, detail=f"{price.material} 原料单价必须大于 0")
        db.add(MoldingSampleMaterialPrice(material=price.material.strip(), unit_price=price.unit_price, notes=price.notes))

    setting = db.get(MoldingSampleSetting, RATE_KEY)
    if setting:
        setting.value = str(rmb_to_hkd_rate)
    else:
        db.add(MoldingSampleSetting(key=RATE_KEY, value=str(rmb_to_hkd_rate)))

    append_sensitive_audit(
        db,
        action="经理更新价格口径",
        current_user=current_user,
        target_type="material_prices",
        target_name="原料价格表",
        detail=f"更新 {len(prices)} 条原料价格，汇率 {rmb_to_hkd_rate}。",
    )
    db.commit()
    return {"prices": get_prices(db), "rmb_to_hkd_rate": get_exchange_rate(db)}


def build_total_cost_summary(order: MoldingSampleOrder) -> dict[str, Any]:
    external = is_external_order(order)
    missing_price_ids: list[str] = []
    missing_injection_ids: list[str] = []
    item_rows: list[dict[str, Any]] = []
    total_material = 0.0
    total_injection = 0.0

    for item in order.items:
        material_cost = item.actual_amount_hkd or 0.0
        injection_cost = 0.0 if external else (item.injection_cost_hkd if item.injection_cost_hkd is not None else item.injection_cost or 0.0)

        if item.actual_weight_kg and item.actual_amount_hkd is None:
            missing_price_ids.append(item.id)
        if not external and item.injection_cost is None and item.injection_cost_hkd is None:
            missing_injection_ids.append(item.id)

        total_material += material_cost
        total_injection += injection_cost
        item_rows.append(
            {
                "item_id": item.id,
                "mold_id": item.mold_id,
                "mold_name": item.mold_name,
                "actual_amount_hkd": item.actual_amount_hkd,
                "injection_cost": item.injection_cost,
                "injection_cost_hkd": item.injection_cost_hkd,
                "total_cost": round_money(material_cost + injection_cost),
            }
        )

    total_material = round_money(total_material)
    total_injection = round_money(0.0 if external else total_injection)

    return {
        "order_id": order.id,
        "order_number": order.order_number,
        "doc_number": order.doc_number,
        "product_name": order.product_name,
        "client_name": order.client_name,
        "completed_date": order.completed_date,
        "workshop": order.workshop,
        "send_to": order.send_to,
        "status": order.status,
        "total_material_cost": total_material,
        "total_injection_cost": total_injection,
        "total_cost": round_money(total_material + total_injection),
        "has_missing_price": bool(missing_price_ids),
        "has_missing_injection_cost": bool(missing_injection_ids),
        "item_rows": item_rows,
    }
