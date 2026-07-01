import hashlib
import hmac
import secrets
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.molding_sample import (
    MoldingSampleAuditLog,
    MoldingSampleAuthPin,
    MoldingSampleItem,
    MoldingSampleMaterialPrice,
    MoldingSampleOrder,
    MoldingSampleSetting,
)
from app.schemas.molding_sample import (
    MaterialPriceIn,
    MoldingSampleCreateRequest,
    MoldingSampleEditRequest,
    MoldingSampleItemIn,
    MoldingSampleStatusRequest,
    PinChangeRequest,
    PinVerifyRequest,
)

KG_TO_LB = 2.20462
DEFAULT_RATE = 1.08
RATE_KEY = "exchange_rate_rmb_to_hkd"

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
DEFAULT_AUTH_USERS = [
    ("李主管", "主管"),
    ("王经理", "经理"),
]
DEFAULT_PIN = "1234"
PIN_HASH_ITERATIONS = 120_000

LOCKED_STATUSES = {"待经理审核", "待生产", "生产中", "已完成"}
ALLOWED_ITEM_PATCH_FIELDS = {
    "receipt_no",
    "collected_weight_kg",
    "actual_weight_kg",
    "actual_amount_hkd",
    "injection_cost",
}


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def round_money(value: float) -> float:
    return round(value + 1e-9, 2)


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256",
        pin.encode("utf-8"),
        salt.encode("utf-8"),
        PIN_HASH_ITERATIONS,
    ).hex()


def make_auth_pin(name: str, role: str, pin: str = DEFAULT_PIN) -> MoldingSampleAuthPin:
    salt = secrets.token_hex(16)
    return MoldingSampleAuthPin(
        id=f"{role}-{name}",
        name=name,
        role=role,
        pin_salt=salt,
        pin_hash=hash_pin(pin, salt),
        must_change=1,
        updated_at=now_text(),
    )


def normalize_material_name(value: str) -> str:
    fullwidth_digits = {ord(chr(code)): str(code - 0xFF10) for code in range(0xFF10, 0xFF1A)}
    normalized = value.lower().translate(fullwidth_digits).replace("度", "°")

    for token in (" ", "\t", "\n", "-", "_", "(", ")", "（", "）"):
        normalized = normalized.replace(token, "")

    return normalized


def seed_molding_sample_defaults(db: Session) -> None:
    if db.scalar(select(MoldingSampleSetting).where(MoldingSampleSetting.key == RATE_KEY)) is None:
        db.add(MoldingSampleSetting(key=RATE_KEY, value=str(DEFAULT_RATE)))

    existing_count = len(db.scalars(select(MoldingSampleMaterialPrice)).all())
    if existing_count == 0:
        for material, unit_price, notes in DEFAULT_PRICES:
            db.add(MoldingSampleMaterialPrice(material=material, unit_price=unit_price, notes=notes))

    for name, role in DEFAULT_AUTH_USERS:
        existing_pin = db.scalar(
            select(MoldingSampleAuthPin)
            .where(MoldingSampleAuthPin.name == name)
            .where(MoldingSampleAuthPin.role == role)
        )
        if existing_pin is None:
            db.add(make_auth_pin(name, role))

    db.commit()


def get_auth_pin(db: Session, name: str, role: str) -> MoldingSampleAuthPin | None:
    return db.scalar(
        select(MoldingSampleAuthPin)
        .where(MoldingSampleAuthPin.name == name)
        .where(MoldingSampleAuthPin.role == role)
    )


def require_valid_pin(db: Session, name: str, role: str, pin: str) -> MoldingSampleAuthPin:
    auth_pin = get_auth_pin(db, name, role)
    if not auth_pin or not pin:
        raise HTTPException(status_code=401, detail="PIN 无效")

    expected = hash_pin(pin, auth_pin.pin_salt)
    if not hmac.compare_digest(expected, auth_pin.pin_hash):
        raise HTTPException(status_code=401, detail="PIN 无效")

    return auth_pin


def list_auth_roles(db: Session) -> dict[str, list[dict[str, Any]]]:
    rows = list(db.scalars(select(MoldingSampleAuthPin).order_by(MoldingSampleAuthPin.role, MoldingSampleAuthPin.name)).all())
    supervisors = [
        {"name": row.name, "role": row.role, "must_change": bool(row.must_change)}
        for row in rows
        if row.role == "主管"
    ]
    managers = [
        {"name": row.name, "role": row.role, "must_change": bool(row.must_change)}
        for row in rows
        if row.role == "经理"
    ]
    return {"supervisors": supervisors, "managers": managers}


def verify_pin(db: Session, payload: PinVerifyRequest) -> dict[str, Any]:
    auth_pin = require_valid_pin(db, payload.name, payload.role, payload.pin)
    return {
        "valid": True,
        "name": auth_pin.name,
        "role": auth_pin.role,
        "must_change": bool(auth_pin.must_change),
    }


def change_pin(db: Session, payload: PinChangeRequest) -> dict[str, Any]:
    if len(payload.new_pin.strip()) < 4:
        raise HTTPException(status_code=400, detail="新 PIN 至少需要 4 位")

    auth_pin = require_valid_pin(db, payload.name, payload.role, payload.old_pin)
    salt = secrets.token_hex(16)
    auth_pin.pin_salt = salt
    auth_pin.pin_hash = hash_pin(payload.new_pin.strip(), salt)
    auth_pin.must_change = 0
    auth_pin.updated_at = now_text()
    db.commit()

    return {
        "valid": True,
        "name": auth_pin.name,
        "role": auth_pin.role,
        "must_change": False,
    }


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

    mixed_parts: list[tuple[float, str]] = []
    for part in material.replace("＋", "+").split("+"):
        piece = part.strip()
        if "%" not in piece and "％" not in piece:
            continue

        normalized_piece = piece.replace("％", "%")
        ratio_text, material_text = normalized_piece.split("%", 1)
        try:
            mixed_parts.append((float(ratio_text.strip()), material_text.strip()))
        except ValueError:
            continue

    if not mixed_parts:
        return None

    mixed_parts.sort(key=lambda item: item[0], reverse=True)
    return price_map.get(normalize_material_name(mixed_parts[0][1]))


def is_external_order(order: MoldingSampleOrder) -> bool:
    return order.send_to in {"发至湖南", "发至模厂"} or order.workshop == "模厂"


def load_order(db: Session, order_id: str) -> MoldingSampleOrder:
    order = db.scalar(
        select(MoldingSampleOrder)
        .where(MoldingSampleOrder.id == order_id)
        .options(
            selectinload(MoldingSampleOrder.items),
            selectinload(MoldingSampleOrder.audit_logs),
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="啤办单不存在")

    return order


def list_orders(db: Session) -> list[MoldingSampleOrder]:
    return list(
        db.scalars(
            select(MoldingSampleOrder)
            .options(selectinload(MoldingSampleOrder.items), selectinload(MoldingSampleOrder.audit_logs))
            .order_by(MoldingSampleOrder.created_at.desc(), MoldingSampleOrder.id.desc())
        ).all()
    )


def append_audit(
    db: Session,
    order: MoldingSampleOrder,
    action: str,
    actor_name: str,
    actor_role: str,
    from_status: str,
    to_status: str,
    reason: str = "",
) -> None:
    db.add(
        MoldingSampleAuditLog(
            id=f"{order.id}-audit-{uuid4().hex[:12]}",
            order_id=order.id,
            action=action,
            actor_name=actor_name,
            actor_role=actor_role,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            created_at=now_text(),
        )
    )


def create_order(db: Session, payload: MoldingSampleCreateRequest) -> MoldingSampleOrder:
    if db.get(MoldingSampleOrder, payload.order.id):
        raise HTTPException(status_code=409, detail="啤办单编号已存在")

    status = payload.order.status or "待审核"
    order = MoldingSampleOrder(
        **payload.order.model_dump(exclude={"status", "created_at", "updated_at"}),
        status=status,
        created_at=payload.order.created_at or now_text(),
        updated_at=payload.order.updated_at or now_text(),
    )
    db.add(order)

    for index, item_payload in enumerate(payload.items, start=1):
        item_data = item_payload.model_dump(exclude={"order_id", "sort_order"})
        db.add(
            MoldingSampleItem(
                **item_data,
                order_id=order.id,
                sort_order=item_payload.sort_order or index,
            )
        )

    append_audit(db, order, "工程提交主管审核", order.eng_name, "工程部", status, status, "工程开单完成。")
    db.commit()
    db.refresh(order)
    return load_order(db, order.id)


def ensure_order_write_allowed(
    db: Session,
    order: MoldingSampleOrder,
    actor_name: str,
    actor_role: str,
    pin: str = "",
) -> None:
    if order.status not in LOCKED_STATUSES and actor_role == "工程部":
        return

    if actor_role == "经理":
        require_valid_pin(db, actor_name, "经理", pin)
        return

    if actor_role == "主管":
        if actor_name != order.supervisor:
            raise HTTPException(status_code=403, detail="只有指定主管可以改动该啤办单")
        require_valid_pin(db, actor_name, "主管", pin)
        return

    raise HTTPException(status_code=403, detail="当前状态不允许普通工程部改删")


def update_order(db: Session, order_id: str, payload: MoldingSampleEditRequest) -> MoldingSampleOrder:
    order = load_order(db, order_id)
    if payload.order.id != order_id:
        raise HTTPException(status_code=400, detail="啤办单 ID 不一致")

    ensure_order_write_allowed(db, order, payload.actor_name, payload.actor_role, payload.pin)
    current_status = order.status
    current_created_at = order.created_at

    order_data = payload.order.model_dump(exclude={"id", "status", "created_at", "updated_at"})
    for field, value in order_data.items():
        setattr(order, field, value)

    order.status = current_status
    order.created_at = current_created_at
    order.updated_at = now_text()

    for existing_item in list(order.items):
        db.delete(existing_item)
    db.flush()

    for index, item_payload in enumerate(payload.items, start=1):
        item_data = item_payload.model_dump(exclude={"order_id", "sort_order"})
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
        payload.actor_name,
        payload.actor_role,
        current_status,
        current_status,
        "单头或明细已更新。",
    )
    db.commit()
    db.expire_all()
    return load_order(db, order_id)


def delete_order(
    db: Session,
    order_id: str,
    actor_name: str,
    actor_role: str,
    pin: str = "",
) -> None:
    order = load_order(db, order_id)
    ensure_order_write_allowed(db, order, actor_name, actor_role, pin)
    db.delete(order)
    db.commit()


def completion_missing_item_ids(order: MoldingSampleOrder) -> list[str]:
    if is_external_order(order):
        return []

    return [
        item.id
        for item in order.items
        if not item.actual_weight_kg or item.actual_weight_kg <= 0
    ]


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
    material_price = resolve_material_price(item.material, prices)

    if external:
        item.actual_weight_kg = material_weight

    if material_weight and material_price and (force_material_amount or not item.actual_amount_hkd):
        item.actual_amount_hkd = round_money(material_weight * KG_TO_LB * material_price.unit_price)

    if external:
        item.injection_cost_hkd = None
        item.exchange_rate_at_save = None
    elif item.injection_cost is not None:
        item.injection_cost_hkd = round_money(item.injection_cost * rate)
        item.exchange_rate_at_save = rate


def recalculate_order_costs(db: Session, order: MoldingSampleOrder, force_material_amount: bool = False) -> None:
    for item in order.items:
        calculate_item_costs(db, order, item, force_material_amount=force_material_amount)


def update_order_items(db: Session, order_id: str, items: list[MoldingSampleItemIn]) -> MoldingSampleOrder:
    order = load_order(db, order_id)
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
    return load_order(db, order_id)


def transition_status(db: Session, order_id: str, request: MoldingSampleStatusRequest) -> MoldingSampleOrder:
    order = load_order(db, order_id)
    from_status = order.status
    action = request.action
    next_status: str | None = None

    if action == "主管通过":
        if order.status != "待审核" or request.reviewer_role != "主管" or request.reviewer_name != order.supervisor:
            raise HTTPException(status_code=403, detail="只有指定主管可以审核待审核单")
        require_valid_pin(db, request.reviewer_name, request.reviewer_role, request.pin)
        next_status = "待经理审核"
    elif action == "主管驳回":
        if order.status != "待审核" or request.reviewer_role != "主管" or request.reviewer_name != order.supervisor:
            raise HTTPException(status_code=403, detail="只有指定主管可以驳回待审核单")
        require_valid_pin(db, request.reviewer_name, request.reviewer_role, request.pin)
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "经理通过":
        if order.status != "待经理审核" or request.reviewer_role != "经理":
            raise HTTPException(status_code=403, detail="只有经理可以终审待经理审核单")
        require_valid_pin(db, request.reviewer_name, request.reviewer_role, request.pin)
        if is_external_order(order):
            next_status = "已完成"
            order.completed_date = request.today or order.date
            recalculate_order_costs(db, order, force_material_amount=True)
        else:
            next_status = "待生产"
    elif action == "经理驳回":
        if order.status != "待经理审核" or request.reviewer_role != "经理":
            raise HTTPException(status_code=403, detail="只有经理可以驳回待经理审核单")
        require_valid_pin(db, request.reviewer_name, request.reviewer_role, request.pin)
        next_status = "已驳回"
        order.reject_reason = request.reason
    elif action == "工程重提":
        if order.status != "已驳回" or request.reviewer_role != "工程部":
            raise HTTPException(status_code=403, detail="只有工程部可以重提已驳回单")
        next_status = "待审核"
        order.reject_reason = ""
    elif action == "开始处理":
        if order.status != "待生产" or request.reviewer_role != "啤机部":
            raise HTTPException(status_code=403, detail="只有啤机部可以开始处理待生产单")
        next_status = "生产中"
    elif action == "标记完成":
        if order.status != "生产中" or request.reviewer_role != "啤机部":
            raise HTTPException(status_code=403, detail="只有啤机部可以完成生产中单")

        missing_ids = completion_missing_item_ids(order)
        if missing_ids:
            raise HTTPException(status_code=400, detail=f"actual_weight_kg 缺失：{', '.join(missing_ids[:5])}")

        next_status = "已完成"
        order.completed_date = request.today or order.date
        recalculate_order_costs(db, order, force_material_amount=True)
    else:
        raise HTTPException(status_code=400, detail="未知状态动作")

    order.status = next_status
    order.updated_at = now_text()
    append_audit(db, order, action, request.reviewer_name, request.reviewer_role, from_status, next_status, request.reason)
    db.commit()
    return load_order(db, order_id)


def replace_material_prices(
    db: Session,
    prices: list[MaterialPriceIn],
    rmb_to_hkd_rate: float,
    manager_name: str = "",
    manager_pin: str = "",
) -> dict[str, Any]:
    if rmb_to_hkd_rate <= 0:
        raise HTTPException(status_code=400, detail="汇率必须大于 0")
    require_valid_pin(db, manager_name, "经理", manager_pin)

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
