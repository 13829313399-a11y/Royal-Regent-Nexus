from __future__ import annotations

import json
import os
import re
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import business_now, business_today, parse_business_timestamp
from app.models.three_d_printing import (
    ThreeDPrintingAuditEvent,
    ThreeDPrintingDayStatus,
    ThreeDPrintingEdgeAgent,
    ThreeDPrintingInventory,
    ThreeDPrintingInventoryMovement,
    ThreeDPrintingMaintenance,
    ThreeDPrintingMaterial,
    ThreeDPrintingPrinter,
    ThreeDPrintingPrinterCommand,
    ThreeDPrintingPrinterConnection,
    ThreeDPrintingProduct,
    ThreeDPrintingProductImage,
    ThreeDPrintingProductionRecord,
    ThreeDPrintingSchedule,
    ThreeDPrintingSetting,
)
from app.schemas.three_d_printing import (
    ThreeDDayStatusUpdate,
    ThreeDEdgeHeartbeat,
    ThreeDEdgePrinterStatus,
    ThreeDInventoryAdjustment,
    ThreeDMaintenanceInput,
    ThreeDMaintenanceUpdate,
    ThreeDMaterialInput,
    ThreeDMaterialUpdate,
    ThreeDPrinterCommandCreate,
    ThreeDProductInput,
    ThreeDProductionRecordInput,
    ThreeDProductionRecordUpdate,
    ThreeDProductUpdate,
    ThreeDRecordAction,
    ThreeDScheduleInput,
    ThreeDScheduleStatusUpdate,
    ThreeDScheduleUpdate,
    ThreeDSettingsUpdate,
    ThreeDStockInInput,
)
from app.services.auth import AuthContext, time_window_is_active
from app.services.three_d_connector import CONNECTED_OWNERS as CONNECTOR_OWNERS
from app.services.three_d_connector import create_command as create_connector_command
from app.services.three_d_consistency import (
    atomic_write,
    freeze_cost,
    frozen_totals,
    record_inputs,
)
from app.services.three_d_network_health import (
    network_blocks_control,
    network_health_snapshot,
)

THREE_D_FACTORY_ID = "huakang-a"
THREE_D_DEPARTMENTS = ("three-d-printing", "production", "management")
FINISHED_PRINTER_STATES = {"FINISH", "FAILED", "IDLE", "ERROR"}
IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_PRODUCT_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_DIMENSION = 1600


def _now() -> str:
    return business_now().isoformat(timespec="seconds")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_json(value: str, fallback: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


def _actor_name(user: AuthContext) -> str:
    return user.display_name or user.username


def require_three_d_factory(factory_id: str) -> str:
    normalized = factory_id.strip()
    if normalized != THREE_D_FACTORY_ID:
        raise HTTPException(status_code=400, detail="3D打印机管理当前仅归属华康A")
    return normalized


def add_audit(
    db: Session,
    *,
    factory_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_id: str,
    actor_name: str,
    actor_type: str = "user",
    detail: dict[str, Any] | None = None,
    request_id: str = "",
) -> None:
    db.add(
        ThreeDPrintingAuditEvent(
            id=f"3daudit-{uuid4().hex}",
            factory_id=factory_id,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            detail_json=_json(detail or {}),
            actor_id=actor_id,
            actor_name=actor_name,
            actor_type=actor_type,
            request_id=request_id[:128],
            created_at=_now(),
        )
    )


def ensure_settings(db: Session, factory_id: str) -> ThreeDPrintingSetting:
    factory_id = require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingSetting, factory_id)
    if record is not None:
        return record
    now = _now()
    record = ThreeDPrintingSetting(
        factory_id=factory_id,
        machine_count=11,
        electricity_per_machine_day=1.5,
        labor_per_day=220,
        material_loss_rate=1.2,
        profit_rate_percent=40,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def seed_three_d_printing_defaults(db: Session) -> None:
    """Seed the Huakang A shell for fresh local databases and first startup."""
    record = db.get(ThreeDPrintingSetting, THREE_D_FACTORY_ID)
    now = _now()
    if record is None:
        record = ThreeDPrintingSetting(
            factory_id=THREE_D_FACTORY_ID,
            machine_count=11,
            electricity_per_machine_day=1.5,
            labor_per_day=220,
            material_loss_rate=1.2,
            profit_rate_percent=40,
            revision=1,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        db.flush()
    for machine_no in range(1, record.machine_count + 1):
        existing = db.scalar(
            select(ThreeDPrintingPrinter.id).where(
                ThreeDPrintingPrinter.factory_id == THREE_D_FACTORY_ID,
                ThreeDPrintingPrinter.machine_no == machine_no,
            )
        )
        if existing is not None:
            continue
        db.add(
            ThreeDPrintingPrinter(
                id=f"3dprinter-{THREE_D_FACTORY_ID}-{machine_no}",
                factory_id=THREE_D_FACTORY_ID,
                legacy_id=str(machine_no),
                machine_no=machine_no,
                name=f"{machine_no}号机",
                printer_type="bambu",
                model="",
                enabled=True,
                connected=False,
                state="OFFLINE",
                current_file="",
                progress_percent=0,
                remaining_minutes=0,
                live_material="",
                nozzle_temperature=0,
                bed_temperature=0,
                error_text="",
                status_payload_json="{}",
                last_seen_at="",
                revision=1,
                created_at=now,
                updated_at=now,
            )
        )
    db.commit()


@atomic_write
def update_settings(
    db: Session,
    payload: ThreeDSettingsUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingSetting:
    record = ensure_settings(db, payload.factory_id)
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="设置已被其他用户更新，请刷新后重试")
    record.machine_count = payload.machine_count
    record.electricity_per_machine_day = payload.electricity_per_machine_day
    record.labor_per_day = payload.labor_per_day
    record.material_loss_rate = payload.material_loss_rate
    record.profit_rate_percent = payload.profit_rate_percent
    record.revision += 1
    record.updated_by = user.id
    record.updated_by_name = _actor_name(user)
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=record.factory_id,
        entity_type="settings",
        entity_id=record.factory_id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"revision": record.revision},
        request_id=request_id,
    )
    return record


def _material_by_name(
    db: Session,
    factory_id: str,
    name: str,
) -> ThreeDPrintingMaterial | None:
    return db.scalar(
        select(ThreeDPrintingMaterial).where(
            ThreeDPrintingMaterial.factory_id == factory_id,
            ThreeDPrintingMaterial.name == name.strip(),
        )
    )


def create_material(
    db: Session,
    payload: ThreeDMaterialInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingMaterial:
    factory_id = require_three_d_factory(payload.factory_id)
    name = payload.name.strip()
    if _material_by_name(db, factory_id, name):
        raise HTTPException(status_code=409, detail="材料名称已存在")
    now = _now()
    record = ThreeDPrintingMaterial(
        id=f"3dmat-{uuid4().hex}",
        factory_id=factory_id,
        name=name,
        material_type=payload.material_type.strip(),
        price_per_kg=payload.price_per_kg,
        is_active=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="material",
        entity_id=record.id,
        action="create",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"name": name},
        request_id=request_id,
    )
    _ensure_inventory(db, factory_id, name)
    db.commit()
    db.refresh(record)
    return record


@atomic_write
def update_material(
    db: Session,
    material_id: str,
    payload: ThreeDMaterialUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingMaterial:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.get(ThreeDPrintingMaterial, material_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="材料不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="材料已被其他用户更新")
    name = payload.name.strip()
    conflict = _material_by_name(db, factory_id, name)
    if conflict is not None and conflict.id != record.id:
        raise HTTPException(status_code=409, detail="材料名称已存在")
    old_name = record.name
    record.name = name
    record.material_type = payload.material_type.strip()
    record.price_per_kg = payload.price_per_kg
    record.revision += 1
    record.updated_at = _now()
    # Raw inventory buckets and immutable movements retain their original names.
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="material",
        entity_id=record.id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"oldName": old_name, "name": name, "revision": record.revision},
        request_id=request_id,
    )
    return record


def archive_material(
    db: Session,
    material_id: str,
    factory_id: str,
    user: AuthContext,
    request_id: str = "",
) -> None:
    factory_id = require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingMaterial, material_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="材料不存在")
    record.is_active = False
    record.revision += 1
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="material",
        entity_id=record.id,
        action="archive",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"name": record.name},
        request_id=request_id,
    )
    db.commit()


def create_product(
    db: Session,
    payload: ThreeDProductInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingProduct:
    factory_id = require_three_d_factory(payload.factory_id)
    now = _now()
    record = ThreeDPrintingProduct(
        id=f"3dprod-{uuid4().hex}",
        factory_id=factory_id,
        name=payload.name.strip(),
        customer=payload.customer.strip(),
        material_name=payload.material_name.strip(),
        weight_g=payload.weight_g,
        duration_hours=payload.duration_hours,
        default_quantity=payload.default_quantity,
        quoted_price=payload.quoted_price,
        is_active=True,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="product",
        entity_id=record.id,
        action="create",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"name": record.name},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


@atomic_write
def update_product(
    db: Session,
    product_id: str,
    payload: ThreeDProductUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingProduct:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.get(ThreeDPrintingProduct, product_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="产品不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="产品已被其他用户更新")
    old_name = record.name
    record.name = payload.name.strip()
    record.customer = payload.customer.strip()
    record.material_name = payload.material_name.strip()
    record.weight_g = payload.weight_g
    record.duration_hours = payload.duration_hours
    record.default_quantity = payload.default_quantity
    record.quoted_price = payload.quoted_price
    record.revision += 1
    record.updated_at = _now()
    if old_name != record.name:
        for schedule in db.scalars(
            select(ThreeDPrintingSchedule).where(
                ThreeDPrintingSchedule.factory_id == factory_id,
                ThreeDPrintingSchedule.product_id == record.id,
                ThreeDPrintingSchedule.status == "pending",
            )
        ):
            schedule.product_name = record.name
            schedule.updated_at = record.updated_at
            schedule.revision += 1
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="product",
        entity_id=record.id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"oldName": old_name, "name": record.name, "revision": record.revision},
        request_id=request_id,
    )
    return record


def archive_product(
    db: Session,
    product_id: str,
    factory_id: str,
    user: AuthContext,
    request_id: str = "",
) -> None:
    factory_id = require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingProduct, product_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="产品不存在")
    record.is_active = False
    record.revision += 1
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="product",
        entity_id=record.id,
        action="archive",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"name": record.name},
        request_id=request_id,
    )
    db.commit()


def _asset_root() -> Path:
    root = Path(settings.three_d_asset_dir).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def product_image_path(image: ThreeDPrintingProductImage) -> Path:
    root = _asset_root()
    path = (root / image.storage_key).resolve()
    if root not in path.parents:
        raise HTTPException(status_code=500, detail="图片存储路径无效")
    return path


def save_product_image(
    db: Session,
    *,
    product_id: str,
    factory_id: str,
    file_name: str,
    mime_type: str,
    content: bytes,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingProductImage:
    factory_id = require_three_d_factory(factory_id)
    product = db.get(ThreeDPrintingProduct, product_id)
    if product is None or product.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="产品不存在")
    if not content:
        raise HTTPException(status_code=400, detail="图片内容为空")
    if len(content) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="单张图片不可超过5MB")
    if mime_type not in IMAGE_MIME_TYPES:
        raise HTTPException(status_code=415, detail="仅支持 JPEG、PNG 或 WebP 图片")
    try:
        source = Image.open(BytesIO(content))
        source.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=422, detail="图片内容损坏或格式不受支持") from exc
    image = source.convert("RGB")
    image.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION))
    output = BytesIO()
    image.save(output, format="JPEG", quality=85, optimize=True)
    encoded = output.getvalue()
    digest = sha256(encoded).hexdigest()
    storage_key = f"{factory_id}/{product_id}/{digest}.jpg"
    target = (_asset_root() / storage_key).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        # Keep the temporary name short enough for Windows edge/test hosts
        # while retaining an atomic same-directory replacement.
        temp_path = target.parent / f".{uuid4().hex[:8]}.tmp"
        temp_path.write_bytes(encoded)
        os.replace(temp_path, target)
    record = db.scalar(
        select(ThreeDPrintingProductImage).where(
            ThreeDPrintingProductImage.product_id == product_id
        )
    )
    now = _now()
    if record is None:
        record = ThreeDPrintingProductImage(
            id=f"3dimg-{uuid4().hex}",
            product_id=product_id,
            factory_id=factory_id,
            storage_key=storage_key,
            sha256=digest,
            mime_type="image/jpeg",
            size_bytes=len(encoded),
            width=image.width,
            height=image.height,
            original_file_name=file_name[:255],
            is_current=True,
            uploaded_by=user.id,
            uploaded_by_name=_actor_name(user),
            created_at=now,
        )
        db.add(record)
    else:
        record.storage_key = storage_key
        record.sha256 = digest
        record.mime_type = "image/jpeg"
        record.size_bytes = len(encoded)
        record.width = image.width
        record.height = image.height
        record.original_file_name = file_name[:255]
        record.uploaded_by = user.id
        record.uploaded_by_name = _actor_name(user)
        record.created_at = now
    product.revision += 1
    product.updated_at = now
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="product_image",
        entity_id=record.id,
        action="upload",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"productId": product_id, "sha256": digest, "sizeBytes": len(encoded)},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def remove_product_image(
    db: Session,
    *,
    product_id: str,
    factory_id: str,
    user: AuthContext,
    request_id: str = "",
) -> None:
    factory_id = require_three_d_factory(factory_id)
    product = db.get(ThreeDPrintingProduct, product_id)
    if product is None or product.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="产品不存在")
    record = db.scalar(
        select(ThreeDPrintingProductImage).where(
            ThreeDPrintingProductImage.product_id == product_id,
            ThreeDPrintingProductImage.factory_id == factory_id,
        )
    )
    if record is None:
        return
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="product_image",
        entity_id=record.id,
        action="remove",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"productId": product_id, "sha256": record.sha256},
        request_id=request_id,
    )
    db.delete(record)
    product.revision += 1
    product.updated_at = _now()
    db.commit()


def _inventory_by_name(
    db: Session,
    factory_id: str,
    material_name: str,
) -> ThreeDPrintingInventory | None:
    return db.scalar(
        select(ThreeDPrintingInventory).where(
            ThreeDPrintingInventory.factory_id == factory_id,
            ThreeDPrintingInventory.material_name == material_name,
        )
    )


def _ensure_inventory(
    db: Session,
    factory_id: str,
    material_name: str,
) -> ThreeDPrintingInventory:
    record = _inventory_by_name(db, factory_id, material_name)
    if record is not None:
        return record
    now = _now()
    record = ThreeDPrintingInventory(
        id=f"3dinv-{uuid4().hex}",
        factory_id=factory_id,
        material_name=material_name,
        stock_g=0,
        min_stock_g=3000,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def _move_inventory(
    db: Session,
    *,
    factory_id: str,
    material_name: str,
    delta_g: float,
    movement_type: str,
    business_date: str,
    actor_id: str,
    actor_name: str,
    vendor: str = "",
    cost: float = 0,
    remark: str = "",
    source_record_id: str = "",
    legacy_id: str | None = None,
    allow_negative: bool = False,
    idempotency_key: str | None = None,
    reversal_of: str | None = None,
) -> ThreeDPrintingInventoryMovement:
    inventory = _ensure_inventory(db, factory_id, material_name)
    current = Decimal(str(inventory.stock_g))
    target = (current + Decimal(str(delta_g))).quantize(Decimal("0.0001"))
    if target < 0 and Decimal(str(delta_g)) < 0 and not allow_negative:
        raise HTTPException(status_code=409, detail=f"{material_name}库存不足")
    actual_delta = target - current
    inventory.stock_g = target
    inventory.revision += 1
    inventory.updated_at = _now()
    movement = ThreeDPrintingInventoryMovement(
        id=f"3dmov-{uuid4().hex}",
        factory_id=factory_id,
        inventory_id=inventory.id,
        material_name=material_name,
        movement_type=movement_type,
        delta_g=actual_delta,
        idempotency_key=idempotency_key or f"move:{uuid4().hex}",
        reversal_of_movement_id=reversal_of,
        balance_after_g=target,
        business_date=business_date,
        vendor=vendor,
        cost=cost,
        remark=remark,
        source_record_id=source_record_id,
        legacy_id=legacy_id,
        actor_id=actor_id,
        actor_name=actor_name,
        created_at=_now(),
    )
    db.add(movement)
    return movement


@atomic_write
def adjust_inventory(
    db: Session,
    payload: ThreeDInventoryAdjustment,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingInventory:
    factory_id = require_three_d_factory(payload.factory_id)
    inventory = _ensure_inventory(db, factory_id, payload.material_name.strip())
    if inventory.revision != payload.revision and not (payload.revision == 0 and inventory.stock_g == 0 and inventory.revision == 1):
        raise HTTPException(409, "库存已更新，请刷新后重试")
    current = float(inventory.stock_g)
    _move_inventory(
        db,
        factory_id=factory_id,
        material_name=inventory.material_name,
        delta_g=payload.target_stock_g - current,
        movement_type="adjustment",
        business_date=business_today(),
        actor_id=user.id,
        actor_name=_actor_name(user),
        remark=payload.reason.strip(),
    )
    if payload.min_stock_g is not None:
        inventory.min_stock_g = payload.min_stock_g
        inventory.revision += 1
        inventory.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="inventory",
        entity_id=inventory.id,
        action="adjust",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"from": current, "to": payload.target_stock_g, "reason": payload.reason},
        request_id=request_id,
    )
    return inventory


@atomic_write
def create_stock_in(
    db: Session,
    payload: ThreeDStockInInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingInventoryMovement:
    factory_id = require_three_d_factory(payload.factory_id)
    movement = _move_inventory(
        db,
        factory_id=factory_id,
        material_name=payload.material_name.strip(),
        delta_g=payload.amount_g,
        movement_type="stock_in",
        business_date=payload.business_date,
        actor_id=user.id,
        actor_name=_actor_name(user),
        vendor=payload.vendor.strip(),
        cost=payload.cost,
        remark=payload.remark.strip(),
    )
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="inventory_movement",
        entity_id=movement.id,
        action="stock_in",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"materialName": movement.material_name, "amountG": payload.amount_g},
        request_id=request_id,
    )
    return movement


def _approve_negative(payload, user: AuthContext) -> None:
    if not payload.allow_negative_stock:
        return
    if not payload.reason.strip():
        raise HTTPException(422, "批准负库存必须填写原因")
    if not any(grant.role_id in {"admin", "position_3d_supervisor", "position_3d_manager", "position_production_supervisor"}
               and grant.factory_id in {"*", payload.factory_id}
               and time_window_is_active(grant.valid_from, grant.valid_until) for grant in user.grants):
        raise HTTPException(403, "仅本厂主管或管理员可明确批准负库存")


def _require_workday(db, factory_id, business_date):
    day = db.scalar(select(ThreeDPrintingDayStatus).where(
        ThreeDPrintingDayStatus.factory_id == factory_id,
        ThreeDPrintingDayStatus.business_date == business_date))
    if day and day.is_day_off:
        raise HTTPException(409, "该日期已标为休息日，请先恢复工作日")


def _action_record(db, record_id, factory_id, revision):
    require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingProductionRecord, record_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(404, "生产记录不存在")
    if record.revision != revision:
        raise HTTPException(409, "生产记录已被其他用户更新，请刷新后重试")
    return record


def _consume_record(db, record, actor_id, actor_name, reason, allow_negative=False):
    flags = set(_load_json(record.data_quality_flags_json or "[]", []))
    was_shortage = "material_shortage" in flags
    flags.discard("material_shortage")
    flags.discard("negative_inventory_approved")
    record.inventory_consumed = False
    amount = (Decimal(str(record.weight_g)) * record.quantity).quantize(Decimal("0.0001"))
    if record.status not in {"running", "done"} or amount <= 0:
        record.data_quality_flags_json = _json(sorted(flags))
        return
    inventory = _ensure_inventory(db, record.factory_id, record.material_name) if record.material_name else None
    if inventory is None or (Decimal(str(inventory.stock_g)) < amount and not allow_negative):
        flags.add("material_shortage")
        record.reconciliation_status = "pending"
        record.data_quality_flags_json = _json(sorted(flags))
        return
    movement = _move_inventory(db, factory_id=record.factory_id, material_name=record.material_name,
                              delta_g=-amount, movement_type="production_consume", business_date=record.business_date,
                              actor_id=actor_id, actor_name=actor_name, source_record_id=record.id,
                              remark=reason, allow_negative=allow_negative,
                              idempotency_key=f"consume:{record.id}:{record.revision}")
    record.inventory_consumed = True
    if was_shortage and "pending_device_reconciliation" not in flags:
        record.reconciliation_status = "resolved"
    if movement.balance_after_g < 0:
        flags.add("negative_inventory_approved")
    record.data_quality_flags_json = _json(sorted(flags))


def _reverse_record(db, record, actor_id, actor_name, reason):
    db.flush()
    movements = list(db.scalars(select(ThreeDPrintingInventoryMovement).where(
        ThreeDPrintingInventoryMovement.factory_id == record.factory_id,
        ThreeDPrintingInventoryMovement.source_record_id == record.id,
        ThreeDPrintingInventoryMovement.affects_balance.is_(True))))
    reversed_ids = {m.reversal_of_movement_id for m in movements if m.reversal_of_movement_id}
    active = [m for m in movements if m.movement_type == "production_consume" and m.id not in reversed_ids]
    if record.inventory_consumed and not active:
        raise HTTPException(409, "缺少原扣料流水，不能推算返还数量，请先核对库存")
    for movement in active:
        # Reverse actual evidence (including old truncated amounts), never today's weight.
        _move_inventory(db, factory_id=record.factory_id, material_name=movement.material_name,
                        delta_g=-Decimal(str(movement.delta_g)), movement_type="production_reversal",
                        business_date=business_today(), actor_id=actor_id, actor_name=actor_name,
                        source_record_id=record.id, remark=reason, allow_negative=True,
                        idempotency_key=f"reverse:{movement.id}", reversal_of=movement.id)
    record.inventory_consumed = False


def _delete_record(db, record, user, reason, request_id):
    before = production_record_out(record)
    _reverse_record(db, record, user.id, _actor_name(user), reason)
    record.deleted_at = _now()
    record.updated_at = record.deleted_at
    record.revision += 1
    add_audit(db, factory_id=record.factory_id, entity_type="production_record", entity_id=record.id,
              action="soft_delete", actor_id=user.id, actor_name=_actor_name(user), request_id=request_id,
              detail={"before": before, "after": production_record_out(record), "reason": reason})


def _validate_record_payload(payload: ThreeDProductionRecordInput) -> None:
    if payload.status in {"running", "done"} and not payload.product_name.strip():
        raise HTTPException(status_code=422, detail="生产中记录必须填写产品名称")


@atomic_write
def create_production_record(
    db: Session,
    payload: ThreeDProductionRecordInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingProductionRecord:
    factory_id = require_three_d_factory(payload.factory_id)
    _validate_record_payload(payload)
    _require_workday(db, factory_id, payload.business_date)
    now = _now()
    record = ThreeDPrintingProductionRecord(
        id=f"3drec-{uuid4().hex}",
        factory_id=factory_id,
        legacy_id=None,
        business_date=payload.business_date,
        machine_no=payload.machine_no,
        status=payload.status,
        product_id=payload.product_id,
        product_name=payload.product_name.strip()
        if payload.status in {"running", "done"}
        else "空闲"
        if payload.status == "idle"
        else "故障",
        material_name=payload.material_name.strip() if payload.status in {"running", "done"} else "",
        weight_g=payload.weight_g if payload.status in {"running", "done"} else 0,
        quantity=payload.quantity if payload.status in {"running", "done"} else 0,
        duration_hours=payload.duration_hours if payload.status in {"running", "done"} else 0,
        design_fee=payload.design_fee if payload.status in {"running", "done"} else 0,
        quoted_price=payload.quoted_price if payload.status in {"running", "done"} else 0,
        customer=payload.customer.strip(),
        remark=payload.remark.strip(),
        auto_record=False,
        inventory_consumed=False,
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    _approve_negative(payload, user)
    _consume_record(db, record, user.id, _actor_name(user), payload.reason, payload.allow_negative_stock)
    freeze_cost(record, ensure_settings(db, factory_id), _material_by_name(db, factory_id, record.material_name), initial=True, reason=payload.reason)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="production_record",
        entity_id=record.id,
        action="create",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"after": production_record_out(record), "reason": payload.reason, "negativeStockApproved": payload.allow_negative_stock},
        request_id=request_id,
    )
    return record


@atomic_write
def update_production_record(
    db: Session,
    record_id: str,
    payload: ThreeDProductionRecordUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingProductionRecord:
    factory_id = require_three_d_factory(payload.factory_id)
    _validate_record_payload(payload)
    record = db.get(ThreeDPrintingProductionRecord, record_id)
    if record is None or record.factory_id != factory_id or record.deleted_at:
        raise HTTPException(status_code=404, detail="生产记录不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="生产记录已被其他用户更新")
    _approve_negative(payload, user)
    if not payload.reason.strip():
        raise HTTPException(422, "修改历史记录必须填写原因")
    _require_workday(db, factory_id, payload.business_date)
    before = production_record_out(record)
    previous_inputs = record_inputs(record)
    previous_ledger = (record.status in {"running", "done"}, record.material_name, float(record.weight_g), record.quantity)
    record.business_date = payload.business_date
    record.machine_no = payload.machine_no
    record.status = payload.status
    record.product_id = payload.product_id
    record.product_name = (
        payload.product_name.strip()
        if payload.status in {"running", "done"}
        else "空闲"
        if payload.status == "idle"
        else "故障"
    )
    record.material_name = payload.material_name.strip() if payload.status in {"running", "done"} else ""
    record.weight_g = payload.weight_g if payload.status in {"running", "done"} else 0
    record.quantity = payload.quantity if payload.status in {"running", "done"} else 0
    record.duration_hours = payload.duration_hours if payload.status in {"running", "done"} else 0
    record.design_fee = payload.design_fee if payload.status in {"running", "done"} else 0
    record.quoted_price = payload.quoted_price if payload.status in {"running", "done"} else 0
    record.customer = payload.customer.strip()
    record.remark = payload.remark.strip()
    record.revision += 1
    record.updated_at = _now()
    next_ledger = (record.status in {"running", "done"}, record.material_name, float(record.weight_g), record.quantity)
    historical = record.source_system != "nexus" or record.legacy_id is not None
    if next_ledger != previous_ledger or "material_shortage" in _load_json(record.data_quality_flags_json, []):
        if historical:
            if not payload.history_only_correction:
                raise HTTPException(409, "迁移记录无逐笔扣料凭证，请明确选择仅修正历史；余额差异须单独盘点调整")
            if record.inventory_consumed:
                raise HTTPException(409, "历史记录存在未对账扣料，请先核对原流水")
        else:
            _reverse_record(db, record, user.id, _actor_name(user), payload.reason)
            _consume_record(db, record, user.id, _actor_name(user), payload.reason, payload.allow_negative_stock)
    cost_fields = ("weight", "time", "qty", "price", "designFee", "material")
    if previous_inputs["material"] != record.material_name or any(Decimal(str(previous_inputs[k])) != Decimal(str(record_inputs(record)[k])) for k in cost_fields if k != "material"):
        freeze_cost(record, ensure_settings(db, factory_id), None, reason=payload.reason)
    record.product_snapshot_json = _json(record_inputs(record))
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="production_record",
        entity_id=record.id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"before": before, "after": production_record_out(record), "reason": payload.reason, "historyOnlyCorrection": payload.history_only_correction},
        request_id=request_id,
    )
    return record


@atomic_write
def delete_production_record(
    db: Session, record_id: str, factory_id: str, user: AuthContext,
    request_id: str = "", *, revision: int, reason: str, idempotency_key: str,
) -> None:
    record = _action_record(db, record_id, factory_id, revision)
    if record.deleted_at:
        raise HTTPException(409, "记录已经撤销")
    if not reason.strip():
        raise HTTPException(422, "请填写撤销原因")
    _delete_record(db, record, user, reason, request_id)


@atomic_write
def restore_production_record(db: Session, record_id: str, payload: ThreeDRecordAction,
                              user: AuthContext, request_id: str = "") -> ThreeDPrintingProductionRecord:
    record = _action_record(db, record_id, payload.factory_id, payload.revision)
    if not record.deleted_at:
        raise HTTPException(409, "记录未被撤销")
    if not payload.reason.strip():
        raise HTTPException(422, "请填写恢复原因")
    _approve_negative(payload, user)
    _require_workday(db, payload.factory_id, record.business_date)
    before = production_record_out(record)
    record.deleted_at = ""
    record.revision += 1
    record.updated_at = _now()
    # Legacy opening balances already include old activity; never replay it.
    if record.source_system == "nexus" and record.legacy_id is None:
        _consume_record(db, record, user.id, _actor_name(user), payload.reason, payload.allow_negative_stock)
    add_audit(db, factory_id=record.factory_id, entity_type="production_record", entity_id=record.id,
              action="restore", actor_id=user.id, actor_name=_actor_name(user), request_id=request_id,
              detail={"before": before, "after": production_record_out(record), "reason": payload.reason})
    return record


@atomic_write
def update_day_status(
    db: Session,
    payload: ThreeDDayStatusUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingDayStatus:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.scalar(
        select(ThreeDPrintingDayStatus).where(
            ThreeDPrintingDayStatus.factory_id == factory_id,
            ThreeDPrintingDayStatus.business_date == payload.business_date,
        )
    )
    if (record.revision if record else 0) != payload.revision:
        raise HTTPException(409, "日期状态已更新，请刷新后重试")
    if not payload.reason.strip():
        raise HTTPException(422, "请填写批量操作原因")
    now = _now()
    if record is None:
        record = ThreeDPrintingDayStatus(
            id=f"3dday-{uuid4().hex}",
            factory_id=factory_id,
            business_date=payload.business_date,
            is_day_off=payload.is_day_off,
            revision=1,
            updated_by=user.id,
            updated_at=now,
        )
        db.add(record)
    else:
        record.is_day_off = payload.is_day_off
        record.revision += 1
        record.updated_by = user.id
        record.updated_at = now
    affected = 0
    if payload.is_day_off:
        for production_record in db.scalars(
            select(ThreeDPrintingProductionRecord).where(
                ThreeDPrintingProductionRecord.factory_id == factory_id,
                ThreeDPrintingProductionRecord.business_date == payload.business_date,
                ThreeDPrintingProductionRecord.deleted_at == "",
            )
        ):
            _delete_record(db, production_record, user, payload.reason, request_id)
            affected += 1
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="day_status",
        entity_id=record.id,
        action="mark_day_off" if payload.is_day_off else "restore_workday",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"businessDate": payload.business_date, "softDeletedRecords": affected},
        request_id=request_id,
    )
    return record


def create_schedule(
    db: Session,
    payload: ThreeDScheduleInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingSchedule:
    factory_id = require_three_d_factory(payload.factory_id)
    now = _now()
    record = ThreeDPrintingSchedule(
        id=f"3dsch-{uuid4().hex}",
        factory_id=factory_id,
        legacy_id=None,
        business_date=payload.business_date,
        product_id=payload.product_id,
        product_name=payload.product_name.strip(),
        customer=payload.customer.strip(),
        material_name=payload.material_name.strip(),
        weight_g=payload.weight_g,
        quantity=payload.quantity,
        machine_no=payload.machine_no,
        priority=payload.priority,
        status=payload.status,
        remark=payload.remark.strip(),
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="schedule",
        entity_id=record.id,
        action="create",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"businessDate": record.business_date, "productName": record.product_name},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def update_schedule(
    db: Session,
    schedule_id: str,
    payload: ThreeDScheduleUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingSchedule:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.get(ThreeDPrintingSchedule, schedule_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="排期不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="排期已被其他用户更新")
    for key, value in (
        ("business_date", payload.business_date),
        ("product_id", payload.product_id),
        ("product_name", payload.product_name.strip()),
        ("customer", payload.customer.strip()),
        ("material_name", payload.material_name.strip()),
        ("weight_g", payload.weight_g),
        ("quantity", payload.quantity),
        ("machine_no", payload.machine_no),
        ("priority", payload.priority),
        ("status", payload.status),
        ("remark", payload.remark.strip()),
    ):
        setattr(record, key, value)
    record.revision += 1
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="schedule",
        entity_id=record.id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"revision": record.revision},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def update_schedule_status(
    db: Session,
    schedule_id: str,
    payload: ThreeDScheduleStatusUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingSchedule:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.get(ThreeDPrintingSchedule, schedule_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="排期不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="排期已被其他用户更新")
    old_status = record.status
    record.status = payload.status
    record.revision += 1
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="schedule",
        entity_id=record.id,
        action="status_update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"from": old_status, "to": record.status},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def delete_schedule(
    db: Session,
    schedule_id: str,
    factory_id: str,
    user: AuthContext,
    request_id: str = "",
) -> None:
    factory_id = require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingSchedule, schedule_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="排期不存在")
    if record.status in {"done", "cancelled"}:
        raise HTTPException(status_code=409, detail="已完成或已取消排期不能删除")
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="schedule",
        entity_id=record.id,
        action="delete",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"productName": record.product_name},
        request_id=request_id,
    )
    db.delete(record)
    db.commit()


def create_maintenance(
    db: Session,
    payload: ThreeDMaintenanceInput,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingMaintenance:
    factory_id = require_three_d_factory(payload.factory_id)
    now = _now()
    record = ThreeDPrintingMaintenance(
        id=f"3dmaint-{uuid4().hex}",
        factory_id=factory_id,
        legacy_id=None,
        business_date=payload.business_date,
        machine_no=payload.machine_no,
        maintenance_type=payload.maintenance_type.strip(),
        description=payload.description.strip(),
        cost=payload.cost,
        vendor=payload.vendor.strip(),
        remark=payload.remark.strip(),
        revision=1,
        created_by=user.id,
        created_by_name=_actor_name(user),
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="maintenance",
        entity_id=record.id,
        action="create",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"machineNo": record.machine_no, "cost": float(record.cost)},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def update_maintenance(
    db: Session,
    maintenance_id: str,
    payload: ThreeDMaintenanceUpdate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingMaintenance:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.get(ThreeDPrintingMaintenance, maintenance_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="维修记录不存在")
    if record.revision != payload.revision:
        raise HTTPException(status_code=409, detail="维修记录已被其他用户更新")
    record.business_date = payload.business_date
    record.machine_no = payload.machine_no
    record.maintenance_type = payload.maintenance_type.strip()
    record.description = payload.description.strip()
    record.cost = payload.cost
    record.vendor = payload.vendor.strip()
    record.remark = payload.remark.strip()
    record.revision += 1
    record.updated_at = _now()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="maintenance",
        entity_id=record.id,
        action="update",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"revision": record.revision},
        request_id=request_id,
    )
    db.commit()
    db.refresh(record)
    return record


def delete_maintenance(
    db: Session,
    maintenance_id: str,
    factory_id: str,
    user: AuthContext,
    request_id: str = "",
) -> None:
    factory_id = require_three_d_factory(factory_id)
    record = db.get(ThreeDPrintingMaintenance, maintenance_id)
    if record is None or record.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="维修记录不存在")
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="maintenance",
        entity_id=record.id,
        action="delete",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={"businessDate": record.business_date},
        request_id=request_id,
    )
    db.delete(record)
    db.commit()


def register_edge_agent(
    db: Session,
    payload: ThreeDEdgeHeartbeat,
) -> ThreeDPrintingEdgeAgent:
    factory_id = require_three_d_factory(payload.factory_id)
    record = db.scalar(
        select(ThreeDPrintingEdgeAgent).where(
            ThreeDPrintingEdgeAgent.factory_id == factory_id,
            ThreeDPrintingEdgeAgent.agent_key == payload.agent_key,
        )
    )
    now = _now()
    if record is None:
        record = ThreeDPrintingEdgeAgent(
            id=f"3dagent-{uuid4().hex}",
            factory_id=factory_id,
            agent_key=payload.agent_key,
            name=payload.name.strip(),
            version=payload.version.strip(),
            status="online",
            host_fingerprint=payload.host_fingerprint.strip(),
            capabilities_json=_json(sorted(set(payload.capabilities))),
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
    else:
        record.name = payload.name.strip()
        record.version = payload.version.strip()
        record.status = "online"
        record.host_fingerprint = payload.host_fingerprint.strip()
        record.capabilities_json = _json(sorted(set(payload.capabilities)))
        record.last_seen_at = now
        record.updated_at = now
    db.commit()
    db.refresh(record)
    return record


def _normalize_gcode_name(value: str) -> str:
    name = re.sub(r"^.*[/\\\\]", "", value or "")
    name = re.sub(r"\.gcode\.3mf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"\.(3mf|gcode)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"_\d+$", "", name).strip()


def _match_product_from_gcode(
    db: Session,
    factory_id: str,
    gcode_file: str,
) -> ThreeDPrintingProduct | None:
    normalized = _normalize_gcode_name(gcode_file)
    if not normalized:
        return None
    products = list(
        db.scalars(
            select(ThreeDPrintingProduct).where(
                ThreeDPrintingProduct.factory_id == factory_id,
                ThreeDPrintingProduct.is_active.is_(True),
            )
        )
    )
    for product in products:
        if normalized == product.name:
            return product
    for product in products:
        if len(product.name) >= 3 and (
            normalized in product.name or product.name in normalized
        ):
            return product
    return None


def _open_auto_record(
    db: Session,
    factory_id: str,
    machine_no: int,
) -> ThreeDPrintingProductionRecord | None:
    return db.scalar(
        select(ThreeDPrintingProductionRecord)
        .where(
            ThreeDPrintingProductionRecord.factory_id == factory_id,
            ThreeDPrintingProductionRecord.machine_no == machine_no,
            ThreeDPrintingProductionRecord.auto_record.is_(True),
            ThreeDPrintingProductionRecord.source_system == "nexus",
            ThreeDPrintingProductionRecord.legacy_id.is_(None),
            ThreeDPrintingProductionRecord.print_end_at == "",
            ThreeDPrintingProductionRecord.deleted_at == "",
        )
        .order_by(ThreeDPrintingProductionRecord.created_at.desc())
    )


def _create_auto_record(
    db: Session,
    *,
    factory_id: str,
    status: ThreeDEdgePrinterStatus,
    observed_at: str,
    agent: ThreeDPrintingEdgeAgent,
) -> ThreeDPrintingProductionRecord:
    product = _match_product_from_gcode(db, factory_id, status.current_file)
    now = observed_at or _now()
    product_name = product.name if product else (_normalize_gcode_name(status.current_file) or "未知产品")
    material_name = product.material_name if product else status.live_material
    record = ThreeDPrintingProductionRecord(
        id=f"3drec-{uuid4().hex}",
        factory_id=factory_id,
        legacy_id=None,
        business_date=(parse_business_timestamp(now) or business_now()).date().isoformat(),
        machine_no=status.machine_no,
        status="running",
        product_id=product.id if product else "",
        product_name=product_name,
        material_name=material_name,
        weight_g=float(product.weight_g) if product else 0,
        quantity=product.default_quantity if product else 1,
        duration_hours=float(product.duration_hours) if product else 0,
        design_fee=0,
        quoted_price=float(product.quoted_price) if product else 0,
        customer=product.customer if product else "",
        remark="" if product or material_name else "更换材料",
        auto_record=True,
        print_start_at=now,
        print_end_at="",
        gcode_file=status.current_file,
        inventory_consumed=False,
        revision=1,
        created_by=agent.id,
        created_by_name=agent.name,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    _consume_record(db, record, agent.id, agent.name, "打印机开始任务自动扣减")
    freeze_cost(record, ensure_settings(db, factory_id), _material_by_name(db, factory_id, record.material_name), initial=True)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="production_record",
        entity_id=record.id,
        action="auto_create",
        actor_id=agent.id,
        actor_name=agent.name,
        actor_type="edge_agent",
        detail={
            "machineNo": status.machine_no,
            "gcodeFile": status.current_file,
            "productMatched": bool(product),
        },
    )
    return record


@atomic_write
def apply_edge_status_batch(
    db: Session,
    *,
    factory_id: str,
    agent_key: str,
    statuses: list[ThreeDEdgePrinterStatus],
) -> list[ThreeDPrintingPrinter]:
    factory_id = require_three_d_factory(factory_id)
    agent = db.scalar(
        select(ThreeDPrintingEdgeAgent).where(
            ThreeDPrintingEdgeAgent.factory_id == factory_id,
            ThreeDPrintingEdgeAgent.agent_key == agent_key,
        )
    )
    if agent is None:
        raise HTTPException(status_code=409, detail="边缘代理尚未注册，请先发送心跳")
    now = _now()
    agent.status = "online"
    agent.last_seen_at = now
    agent.updated_at = now
    network_unavailable = network_blocks_control(db)
    results: list[ThreeDPrintingPrinter] = []
    for status in statuses:
        printer = db.scalar(
            select(ThreeDPrintingPrinter).where(
                ThreeDPrintingPrinter.factory_id == factory_id,
                ThreeDPrintingPrinter.machine_no == status.machine_no,
            )
        )
        if printer is None:
            printer = ThreeDPrintingPrinter(
                id=f"3dprinter-{uuid4().hex}",
                factory_id=factory_id,
                legacy_id=str(status.machine_no),
                machine_no=status.machine_no,
                name=status.name.strip() or f"#{status.machine_no} 3D打印机",
                printer_type=status.printer_type.strip(),
                model=status.model.strip(),
                enabled=True,
                connected=False,
                state="OFFLINE",
                created_at=now,
                updated_at=now,
            )
            db.add(printer)
            db.flush()
        connection = db.get(ThreeDPrintingPrinterConnection, printer.id)
        if connection is not None and connection.connection_owner in CONNECTOR_OWNERS:
            # Cloud-owned devices cannot be overwritten or auto-settled by the old Edge.
            results.append(printer)
            continue
        observed_at = status.observed_at or now
        printer.name = status.name.strip() or printer.name
        printer.printer_type = status.printer_type.strip() or printer.printer_type
        printer.model = status.model.strip() or printer.model
        printer.connected = status.connected
        printer.state = status.state.strip().upper() or "UNKNOWN"
        printer.current_file = status.current_file
        printer.progress_percent = status.progress_percent
        printer.remaining_minutes = status.remaining_minutes
        printer.live_material = status.live_material
        printer.nozzle_temperature = status.nozzle_temperature
        printer.bed_temperature = status.bed_temperature
        printer.error_text = status.error_text
        printer.status_payload_json = _json(status.raw)
        printer.last_seen_at = observed_at
        printer.revision += 1
        printer.updated_at = now
        open_record = _open_auto_record(db, factory_id, status.machine_no)
        if printer.connected and not network_unavailable and printer.state == "RUNNING":
            if open_record is None:
                _create_auto_record(
                    db,
                    factory_id=factory_id,
                    status=status,
                    observed_at=observed_at,
                    agent=agent,
                )
            elif not open_record.material_name and status.live_material:
                open_record.material_name = status.live_material
                freeze_cost(open_record, ensure_settings(db, factory_id), None, reason="设备补充材料信息")
                _consume_record(db, open_record, agent.id, agent.name, "设备补充材料信息")
                open_record.updated_at = now
                open_record.revision += 1
        elif status.connected and not network_unavailable and open_record is not None and printer.state in FINISHED_PRINTER_STATES:
            open_record.print_end_at = observed_at
            open_record.updated_at = now
            open_record.revision += 1
            if printer.state in {"FAILED", "ERROR"} and "打印失败" not in open_record.remark:
                open_record.remark = f"{open_record.remark} 打印失败".strip()
            add_audit(
                db,
                factory_id=factory_id,
                entity_type="production_record",
                entity_id=open_record.id,
                action="auto_complete",
                actor_id=agent.id,
                actor_name=agent.name,
                actor_type="edge_agent",
                detail={"machineNo": status.machine_no, "state": printer.state},
            )
        results.append(printer)
    return results


def create_printer_command(
    db: Session,
    *,
    printer_id: str,
    payload: ThreeDPrinterCommandCreate,
    user: AuthContext,
    request_id: str = "",
) -> ThreeDPrintingPrinterCommand:
    factory_id = require_three_d_factory(payload.factory_id)
    if network_blocks_control(db):
        raise HTTPException(409, "站点网络不可用或探测过期，暂停远程指令")
    printer = db.get(ThreeDPrintingPrinter, printer_id)
    if printer is None or printer.factory_id != factory_id:
        raise HTTPException(status_code=404, detail="打印机不存在")
    connection = db.get(ThreeDPrintingPrinterConnection, printer_id)
    if connection is not None and connection.connection_owner in CONNECTOR_OWNERS:
        return create_connector_command(db, printer_id=printer_id, payload=payload, user=user)
    existing = db.scalar(
        select(ThreeDPrintingPrinterCommand).where(
            ThreeDPrintingPrinterCommand.factory_id == factory_id,
            ThreeDPrintingPrinterCommand.idempotency_key == payload.idempotency_key,
        )
    )
    if existing is not None:
        return existing
    now_dt = business_now()
    command = ThreeDPrintingPrinterCommand(
        id=f"3dcmd-{uuid4().hex}",
        factory_id=factory_id,
        printer_id=printer_id,
        action=payload.action,
        status="pending",
        idempotency_key=payload.idempotency_key,
        reason=payload.reason.strip(),
        requested_by=user.id,
        requested_by_name=_actor_name(user),
        requested_at=now_dt.isoformat(timespec="seconds"),
        expires_at=(now_dt + timedelta(seconds=settings.three_d_command_ttl_seconds)).isoformat(
            timespec="seconds"
        ),
    )
    db.add(command)
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="printer_command",
        entity_id=command.id,
        action="request",
        actor_id=user.id,
        actor_name=_actor_name(user),
        detail={
            "printerId": printer_id,
            "machineNo": printer.machine_no,
            "command": payload.action,
            "reason": payload.reason,
        },
        request_id=request_id,
    )
    db.commit()
    db.refresh(command)
    return command


def claim_printer_commands(
    db: Session,
    *,
    factory_id: str,
    agent_key: str,
    limit: int,
) -> list[ThreeDPrintingPrinterCommand]:
    factory_id = require_three_d_factory(factory_id)
    agent = db.scalar(
        select(ThreeDPrintingEdgeAgent).where(
            ThreeDPrintingEdgeAgent.factory_id == factory_id,
            ThreeDPrintingEdgeAgent.agent_key == agent_key,
        )
    )
    if agent is None:
        raise HTTPException(status_code=409, detail="边缘代理尚未注册")
    if network_blocks_control(db):
        return []
    now_dt = business_now()
    now = now_dt.isoformat(timespec="seconds")
    pending = list(
        db.scalars(
            select(ThreeDPrintingPrinterCommand)
            .where(
                ThreeDPrintingPrinterCommand.factory_id == factory_id,
                ThreeDPrintingPrinterCommand.status == "pending",
                ~select(ThreeDPrintingPrinterConnection.printer_id).where(
                    ThreeDPrintingPrinterConnection.printer_id == ThreeDPrintingPrinterCommand.printer_id,
                    ThreeDPrintingPrinterConnection.connection_owner.in_(CONNECTOR_OWNERS),
                ).exists(),
            )
            .order_by(ThreeDPrintingPrinterCommand.requested_at)
            .limit(limit)
        )
    )
    claimed: list[ThreeDPrintingPrinterCommand] = []
    for command in pending:
        expires = parse_business_timestamp(command.expires_at)
        if expires is not None and expires <= now_dt:
            command.status = "expired"
            command.completed_at = now
            command.result_message = "指令超过有效期，未下发"
            continue
        command.status = "claimed"
        command.agent_id = agent.id
        command.claimed_at = now
        claimed.append(command)
    db.commit()
    for command in claimed:
        db.refresh(command)
    return claimed


def acknowledge_printer_command(
    db: Session,
    *,
    command_id: str,
    factory_id: str,
    agent_key: str,
    status: str,
    message: str,
) -> ThreeDPrintingPrinterCommand:
    factory_id = require_three_d_factory(factory_id)
    agent = db.scalar(
        select(ThreeDPrintingEdgeAgent).where(
            ThreeDPrintingEdgeAgent.factory_id == factory_id,
            ThreeDPrintingEdgeAgent.agent_key == agent_key,
        )
    )
    command = db.get(ThreeDPrintingPrinterCommand, command_id)
    if (
        agent is None
        or command is None
        or command.factory_id != factory_id
        or command.agent_id != agent.id
    ):
        raise HTTPException(status_code=404, detail="待确认指令不存在")
    if command.status in {"succeeded", "failed", "expired"}:
        return command
    command.status = status
    command.completed_at = _now()
    command.result_message = message.strip()
    add_audit(
        db,
        factory_id=factory_id,
        entity_type="printer_command",
        entity_id=command.id,
        action=f"ack_{status}",
        actor_id=agent.id,
        actor_name=agent.name,
        actor_type="edge_agent",
        detail={"message": message, "command": command.action},
    )
    db.commit()
    db.refresh(command)
    return command


def _float(value: Any) -> float:
    return float(value or 0)


def _settings_out(record: ThreeDPrintingSetting) -> dict[str, Any]:
    return {
        "factory_id": record.factory_id,
        "machine_count": record.machine_count,
        "electricity_per_machine_day": _float(record.electricity_per_machine_day),
        "labor_per_day": _float(record.labor_per_day),
        "material_loss_rate": _float(record.material_loss_rate),
        "profit_rate_percent": _float(record.profit_rate_percent),
        "revision": record.revision,
        "updated_at": record.updated_at,
    }


def material_out(record: ThreeDPrintingMaterial) -> dict[str, Any]:
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "legacy_id": record.legacy_id or "",
        "name": record.name,
        "material_type": record.material_type,
        "price_per_kg": _float(record.price_per_kg),
        "is_active": record.is_active,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def product_out(
    record: ThreeDPrintingProduct,
    image: ThreeDPrintingProductImage | None = None,
) -> dict[str, Any]:
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "legacy_id": record.legacy_id or "",
        "name": record.name,
        "customer": record.customer,
        "material_name": record.material_name,
        "weight_g": _float(record.weight_g),
        "duration_hours": _float(record.duration_hours),
        "default_quantity": record.default_quantity,
        "quoted_price": _float(record.quoted_price),
        "image_url": (
            f"/api/three-d-printing/products/{record.id}/image"
            f"?factory_id={record.factory_id}"
        )
        if image
        else "",
        "image_size_bytes": image.size_bytes if image else 0,
        "image_sha256": image.sha256 if image else "",
        "is_active": record.is_active,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def production_record_out(record: ThreeDPrintingProductionRecord) -> dict[str, Any]:
    return {
        "run_status": record.run_status,
        "reconciliation_status": record.reconciliation_status,
        "source_system": record.source_system,
        "inventory_consumed": record.inventory_consumed,
        "material_status": "material_shortage" if "material_shortage" in _load_json(record.data_quality_flags_json, []) else "consumed" if record.inventory_consumed else "not_consumed",
        "data_quality_flags": _load_json(record.data_quality_flags_json, []),
        "cost_profile_version": record.cost_profile_version,
        "calculated_cost_snapshot": _load_json(record.calculated_cost_snapshot_json, {}),
        "frozen_totals": frozen_totals(record),
        "deleted_at": record.deleted_at,
        "id": record.id,
        "factory_id": record.factory_id,
        "legacy_id": record.legacy_id or "",
        "business_date": record.business_date,
        "machine_no": record.machine_no,
        "status": record.status,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "material_name": record.material_name,
        "weight_g": _float(record.weight_g),
        "quantity": record.quantity,
        "duration_hours": _float(record.duration_hours),
        "design_fee": _float(record.design_fee),
        "quoted_price": _float(record.quoted_price),
        "customer": record.customer,
        "remark": record.remark,
        "auto_record": record.auto_record,
        "print_start_at": record.print_start_at,
        "print_end_at": record.print_end_at,
        "gcode_file": record.gcode_file,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def inventory_out(record: ThreeDPrintingInventory) -> dict[str, Any]:
    stock_g = _float(record.stock_g)
    min_stock_g = _float(record.min_stock_g)
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "material_name": record.material_name,
        "stock_g": stock_g,
        "min_stock_g": min_stock_g,
        "is_low": stock_g < min_stock_g,
        "revision": record.revision,
        "updated_at": record.updated_at,
    }


def inventory_movement_out(record: ThreeDPrintingInventoryMovement) -> dict[str, Any]:
    return {
        "reversal_of_movement_id": record.reversal_of_movement_id or "",
        "idempotency_key": record.idempotency_key or "",
        "affects_balance": record.affects_balance,
        "id": record.id,
        "factory_id": record.factory_id,
        "material_name": record.material_name,
        "movement_type": record.movement_type,
        "delta_g": _float(record.delta_g),
        "balance_after_g": _float(record.balance_after_g),
        "business_date": record.business_date,
        "vendor": record.vendor,
        "cost": _float(record.cost),
        "remark": record.remark,
        "source_record_id": record.source_record_id,
        "created_at": record.created_at,
    }


def schedule_out(record: ThreeDPrintingSchedule) -> dict[str, Any]:
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "legacy_id": record.legacy_id or "",
        "business_date": record.business_date,
        "product_id": record.product_id,
        "product_name": record.product_name,
        "customer": record.customer,
        "material_name": record.material_name,
        "weight_g": _float(record.weight_g),
        "quantity": record.quantity,
        "machine_no": record.machine_no,
        "priority": record.priority,
        "status": record.status,
        "remark": record.remark,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def maintenance_out(record: ThreeDPrintingMaintenance) -> dict[str, Any]:
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "legacy_id": record.legacy_id or "",
        "business_date": record.business_date,
        "machine_no": record.machine_no,
        "maintenance_type": record.maintenance_type,
        "description": record.description,
        "cost": _float(record.cost),
        "vendor": record.vendor,
        "remark": record.remark,
        "revision": record.revision,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def printer_out(record: ThreeDPrintingPrinter, *, network_stale: bool = False) -> dict[str, Any]:
    telemetry = json.loads(record.status_payload_json or "{}").get("connector", {})
    last_seen = parse_business_timestamp(record.last_seen_at)
    age = (business_now() - last_seen).total_seconds() if last_seen else None
    stale = network_stale or age is None or age > 30 or age < -5
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "machine_no": record.machine_no,
        "name": record.name,
        "printer_type": record.printer_type,
        "model": record.model,
        "enabled": record.enabled,
        "connected": record.connected and not stale,
        "state": ("STALE" if record.last_seen_at or network_stale else "OFFLINE") if stale else record.state,
        "current_file": record.current_file,
        "progress_percent": record.progress_percent,
        "remaining_minutes": record.remaining_minutes,
        "live_material": record.live_material,
        "nozzle_temperature": _float(record.nozzle_temperature),
        "bed_temperature": _float(record.bed_temperature),
        "error_text": record.error_text,
        "last_seen_at": record.last_seen_at,
        "status_stale": stale,
        **{key: telemetry[key] for key in ("nozzle_target", "bed_target", "layer_num", "total_layers") if key in telemetry},
    }


def command_out(record: ThreeDPrintingPrinterCommand) -> dict[str, Any]:
    return {
        "id": record.id,
        "factory_id": record.factory_id,
        "printer_id": record.printer_id,
        "action": record.action,
        "status": record.status,
        "reason": record.reason,
        "requested_by_name": record.requested_by_name,
        "requested_at": record.requested_at,
        "expires_at": record.expires_at,
        "claimed_at": record.claimed_at,
        "completed_at": record.completed_at,
        "result_message": record.result_message,
    }


def dashboard_snapshot(
    db: Session,
    *,
    factory_id: str,
    date_from: str = "",
    date_to: str = "",
    compact: bool = False,
) -> dict[str, Any]:
    factory_id = require_three_d_factory(factory_id)
    setting = ensure_settings(db, factory_id)
    materials = list(
        db.scalars(
            select(ThreeDPrintingMaterial)
            .where(
                ThreeDPrintingMaterial.factory_id == factory_id,
                ThreeDPrintingMaterial.is_active.is_(True),
            )
            .order_by(ThreeDPrintingMaterial.name)
        )
    )
    products = list(
        db.scalars(
            select(ThreeDPrintingProduct)
            .where(
                ThreeDPrintingProduct.factory_id == factory_id,
                ThreeDPrintingProduct.is_active.is_(True),
            )
            .order_by(ThreeDPrintingProduct.name, ThreeDPrintingProduct.id)
            .limit(50 if compact else None)
        )
    )
    images = {
        image.product_id: image
        for image in db.scalars(
            select(ThreeDPrintingProductImage).where(
                ThreeDPrintingProductImage.factory_id == factory_id,
                ThreeDPrintingProductImage.is_current.is_(True),
                ThreeDPrintingProductImage.product_id.in_([p.id for p in products]),
            )
        )
    }
    record_filters = [
        ThreeDPrintingProductionRecord.factory_id == factory_id,
        ThreeDPrintingProductionRecord.deleted_at == "",
    ]
    if date_from:
        record_filters.append(ThreeDPrintingProductionRecord.business_date >= date_from)
    if date_to:
        record_filters.append(ThreeDPrintingProductionRecord.business_date <= date_to)
    records = list(
        db.scalars(
            select(ThreeDPrintingProductionRecord)
            .where(*record_filters)
            .order_by(
                ThreeDPrintingProductionRecord.business_date.desc(),
                ThreeDPrintingProductionRecord.machine_no,
                ThreeDPrintingProductionRecord.created_at,
            ).limit(50 if compact else None)
        )
    )
    inventories = list(
        db.scalars(
            select(ThreeDPrintingInventory)
            .where(ThreeDPrintingInventory.factory_id == factory_id)
            .order_by(ThreeDPrintingInventory.material_name)
        )
    )
    movements = list(
        db.scalars(
            select(ThreeDPrintingInventoryMovement)
            .where(ThreeDPrintingInventoryMovement.factory_id == factory_id)
            .order_by(
                ThreeDPrintingInventoryMovement.business_date.desc(),
                ThreeDPrintingInventoryMovement.created_at.desc(),
            )
            .limit(50 if compact else 500)
        )
    )
    schedules = list(
        db.scalars(
            select(ThreeDPrintingSchedule)
            .where(ThreeDPrintingSchedule.factory_id == factory_id)
            .order_by(
                ThreeDPrintingSchedule.business_date,
                ThreeDPrintingSchedule.priority,
                ThreeDPrintingSchedule.id,
            ).limit(50 if compact else None)
        )
    )
    maintenance = list(
        db.scalars(
            select(ThreeDPrintingMaintenance)
            .where(ThreeDPrintingMaintenance.factory_id == factory_id)
            .order_by(
                ThreeDPrintingMaintenance.business_date.desc(),
                ThreeDPrintingMaintenance.id,
            ).limit(50 if compact else None)
        )
    )
    printers = list(
        db.scalars(
            select(ThreeDPrintingPrinter)
            .where(ThreeDPrintingPrinter.factory_id == factory_id)
            .order_by(ThreeDPrintingPrinter.machine_no)
        )
    )
    day_off_dates = list(
        db.scalars(
            select(ThreeDPrintingDayStatus.business_date)
            .where(
                ThreeDPrintingDayStatus.factory_id == factory_id,
                ThreeDPrintingDayStatus.is_day_off.is_(True),
            )
            .order_by(ThreeDPrintingDayStatus.business_date)
        )
    )
    revenue = material_cost = electricity_cost = labor_cost = 0.0
    incomplete_cost_records = 0
    production_dates: set[str] = set()
    summary_records = db.scalars(select(ThreeDPrintingProductionRecord).where(*record_filters)).yield_per(250) if compact else records
    record_count = 0
    daily = {}
    legacy_days = {}
    machine_hours = {p.machine_no: 0.0 for p in printers}
    for record in summary_records:
        record_count += 1
        if record.status not in {"running", "done"}:
            continue
        totals = frozen_totals(record)
        # The old operating view charges one full labor day, while immutable
        # record snapshots retain their original per-record cost allocation.
        if record.business_date not in day_off_dates:
            legacy_day = legacy_days.setdefault(record.business_date, {
                "date": record.business_date, "revenue": 0.0, "materialCost": 0.0,
                "electricityCost": 0.0, "laborCost": _float(setting.labor_per_day),
                "hours": 0.0, "machines": set(),
            })
            for key in ("revenue", "materialCost", "electricityCost"):
                legacy_day[key] += totals[key] or 0
            legacy_day["hours"] += _float(record.duration_hours) * record.quantity
            legacy_day["machines"].add(record.machine_no)
        incomplete_cost_records += int(any(value is None for value in totals.values()))
        revenue += totals["revenue"] or 0
        material_cost += totals["materialCost"] or 0
        electricity_cost += totals["electricityCost"] or 0
        labor_cost += totals["laborCost"] or 0
        production_dates.add(record.business_date)
        day = daily.setdefault(record.business_date, {"date": record.business_date, "revenue": 0.0, "totalCost": 0.0})
        day["revenue"] += totals["revenue"] or 0
        day["totalCost"] += sum(totals[k] or 0 for k in ("materialCost", "electricityCost", "laborCost"))
        machine_hours[record.machine_no] = machine_hours.get(record.machine_no, 0) + _float(record.duration_hours) * record.quantity
    maintenance_filters = [ThreeDPrintingMaintenance.factory_id == factory_id]
    if date_from:
        maintenance_filters.append(ThreeDPrintingMaintenance.business_date >= date_from)
    if date_to:
        maintenance_filters.append(ThreeDPrintingMaintenance.business_date <= date_to)
    maintenance_cost = 0.0
    for repair in db.scalars(select(ThreeDPrintingMaintenance).where(*maintenance_filters)):
        cost = _float(repair.cost)
        maintenance_cost += cost
        daily.setdefault(repair.business_date, {"date": repair.business_date, "revenue": 0.0, "totalCost": 0.0})["totalCost"] += cost
    total_cost = material_cost + electricity_cost + labor_cost + maintenance_cost
    legacy_daily = []
    for _, day in sorted(legacy_days.items()):
        cost = sum(day[key] for key in ("materialCost", "electricityCost", "laborCost"))
        legacy_daily.append({
            **{key: round(day[key], 2) for key in ("revenue", "materialCost", "electricityCost", "laborCost")},
            "date": day["date"], "totalCost": round(cost, 2),
            "balance": round(day["revenue"] - cost, 2),
            "runningMachines": len(day["machines"]),
            "utilization": day["hours"] / (12 * max(1, setting.machine_count)),
        })
    legacy_display = {key: round(sum(day[key] for day in legacy_daily), 2)
                      for key in ("revenue", "materialCost", "electricityCost", "laborCost", "totalCost", "balance")}
    legacy_display.update(daily=legacy_daily, productionDays=len(legacy_daily),
                          maintenanceCost=round(maintenance_cost, 2), costBasis="daily_fixed_labor")
    network = network_health_snapshot(db)
    return {
        "factory_id": factory_id,
        "generated_at": _now(),
        "settings": _settings_out(setting),
        "network_health": network,
        "printers": [printer_out(item, network_stale=network["configured"] and network["status"] != "healthy") for item in printers],
        "materials": [material_out(item) for item in materials],
        "products": [product_out(item, images.get(item.id)) for item in products],
        "records": [production_record_out(item) for item in records],
        "inventory": [inventory_out(item) for item in inventories],
        "inventory_movements": [inventory_movement_out(item) for item in movements],
        "schedules": [schedule_out(item) for item in schedules],
        "maintenance": [maintenance_out(item) for item in maintenance],
        "day_off_dates": day_off_dates,
        "day_statuses": [{"business_date": day.business_date, "revision": day.revision, "is_day_off": day.is_day_off} for day in db.scalars(select(ThreeDPrintingDayStatus).where(ThreeDPrintingDayStatus.factory_id == factory_id))],
        "summary": {
            "legacyDisplay": legacy_display,
            "daily": [{**d, "revenue": round(d["revenue"], 2), "totalCost": round(d["totalCost"], 2), "balance": round(d["revenue"] - d["totalCost"], 2)} for _, d in sorted(daily.items())],
            "machineHours": [{"machine_no": n, "hours": round(hours, 2)} for n, hours in sorted(machine_hours.items())],
            "incompleteCostRecordCount": incomplete_cost_records,
            "costBasis": "frozen_record_allocated_labor",
            "revenue": round(revenue, 2),
            "materialCost": round(material_cost, 2),
            "electricityCost": round(electricity_cost, 2),
            "laborCost": round(labor_cost, 2),
            "maintenanceCost": round(maintenance_cost, 2),
            "totalCost": round(total_cost, 2),
            "balance": round(revenue - total_cost, 2),
            "productionDays": len(production_dates),
            "recordCount": record_count,
            "productCount": db.scalar(select(func.count()).select_from(ThreeDPrintingProduct).where(ThreeDPrintingProduct.factory_id == factory_id, ThreeDPrintingProduct.is_active.is_(True))),
            "lowInventoryCount": sum(
                1 for item in inventories if _float(item.stock_g) < _float(item.min_stock_g)
            ),
        },
    }


def list_audit_events(
    db: Session,
    *,
    factory_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    factory_id = require_three_d_factory(factory_id)
    events = list(
        db.scalars(
            select(ThreeDPrintingAuditEvent)
            .where(ThreeDPrintingAuditEvent.factory_id == factory_id)
            .order_by(ThreeDPrintingAuditEvent.created_at.desc())
            .limit(limit)
        )
    )
    return [
        {
            "id": event.id,
            "factory_id": event.factory_id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "action": event.action,
            "detail": _load_json(event.detail_json, {}),
            "actor_name": event.actor_name,
            "actor_type": event.actor_type,
            "request_id": event.request_id,
            "created_at": event.created_at,
        }
        for event in events
    ]
