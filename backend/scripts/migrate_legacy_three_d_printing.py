"""Analyze, import and reconcile authoritative SQLite/WAL snapshots.

Analysis and dry runs never load the Nexus database. Import/reconcile require
the installed v2 schema; schema upgrades are a separate Alembic operation.
The old JSON importer remains available only with explicit fallback + import.
"""
# ruff: noqa: TC004 -- Runtime aliases are populated by _load_import_runtime, never on analyze.

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from sqlalchemy import select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from legacy_sqlite_reader import (
    SnapshotError,
    assert_no_secrets,
    capture_snapshot,
    file_fingerprint,
    read_json,
)
from legacy_three_d_analysis import analyze_state
from scan_three_d_secrets import SafeParser

if TYPE_CHECKING:
    from app.core.config import settings
    from app.db import SessionLocal
    from app.models.three_d_printing import (
        ThreeDPrintingAuditEvent,
        ThreeDPrintingDayStatus,
        ThreeDPrintingInventory,
        ThreeDPrintingInventoryMovement,
        ThreeDPrintingMaintenance,
        ThreeDPrintingMaterial,
        ThreeDPrintingMigrationRun,
        ThreeDPrintingPrinter,
        ThreeDPrintingProduct,
        ThreeDPrintingProductImage,
        ThreeDPrintingProductionRecord,
        ThreeDPrintingSchedule,
        ThreeDPrintingSetting,
    )


def _load_import_runtime() -> None:
    """Legacy importer only. Analyze/help must not initialize app.db/settings."""
    from app.core.config import settings
    from app.db import SessionLocal
    from app.models import three_d_printing as models

    # Preserve the existing mapper API while deferring DB-specific dependencies.
    names = (
        "ThreeDPrintingAuditEvent", "ThreeDPrintingDayStatus", "ThreeDPrintingInventory",
        "ThreeDPrintingInventoryMovement", "ThreeDPrintingMaintenance", "ThreeDPrintingMaterial",
        "ThreeDPrintingMigrationRun", "ThreeDPrintingPrinter", "ThreeDPrintingProduct",
        "ThreeDPrintingProductImage", "ThreeDPrintingProductionRecord", "ThreeDPrintingSchedule",
        "ThreeDPrintingSetting",
    )
    globals().update({name: getattr(models, name) for name in names})
    globals().update(settings=settings, SessionLocal=SessionLocal)


FACTORY_ID = "huakang-a"
DATA_URI_RE = re.compile(
    r"^data:(image/(?:jpeg|jpg|png|webp));base64,(.+)$",
    re.IGNORECASE | re.DOTALL,
)


def now_text() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def value_text(value: Any, *, maximum: int = 4000) -> str:
    return str(value or "").strip()[:maximum]


def value_float(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def value_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def legacy_timestamp(value: Any, fallback: str) -> str:
    if value in (None, ""):
        return fallback
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value) / 1000, UTC).isoformat(
                timespec="seconds"
            )
        except (OSError, OverflowError, ValueError):
            return fallback
    text = value_text(value, maximum=32)
    if text:
        return text
    return fallback


def stable_id(prefix: str, legacy_id: Any, fallback_seed: str) -> str:
    raw = value_text(legacy_id, maximum=72)
    if not raw:
        raw = sha256(fallback_seed.encode("utf-8")).hexdigest()[:32]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", raw).strip("-") or "unknown"
    return f"{prefix}{safe}"[:96]


def load_source(path: Path) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"旧数据文件不是有效 UTF-8 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise TypeError("旧数据文件根节点必须是对象")
    required = {"settings", "materials", "products", "records", "inventory"}
    missing = sorted(required - payload.keys())
    if missing:
        raise ValueError(f"旧数据文件缺少字段：{', '.join(missing)}")
    return raw, payload


def analyze(payload: dict[str, Any], raw: bytes, source: Path) -> dict[str, Any]:
    products = payload.get("products") or []
    records_by_day = payload.get("records") or {}
    records = [
        item
        for day in records_by_day.values()
        if isinstance(day, dict)
        for item in day.get("items", [])
        if isinstance(item, dict)
    ]
    names = Counter(value_text(product.get("name")) for product in products)
    product_names = set(names)
    record_names = {value_text(record.get("productName")) for record in records}
    material_names = {
        value_text(material.get("name"))
        for material in payload.get("materials") or []
        if isinstance(material, dict)
    }
    inventory_names = set((payload.get("inventory") or {}).keys())
    images = sum(
        1
        for product in products
        if isinstance(product, dict) and value_text(product.get("image"))
    )
    return {
        "sourceFile": source.name,
        "sourceSizeBytes": len(raw),
        "sourceSha256": sha256(raw).hexdigest(),
        "factoryId": FACTORY_ID,
        "counts": {
            "materials": len(payload.get("materials") or []),
            "products": len(products),
            "productImages": images,
            "businessDates": len(records_by_day),
            "productionRecords": len(records),
            "softDeletedRecords": sum(bool(row.get("_deleted")) for row in records),
            "inventoryItems": len(payload.get("inventory") or {}),
            "stockInLogs": len(payload.get("stockInLogs") or []),
            "schedules": len(payload.get("schedules") or []),
            "maintenance": len(payload.get("maintenance") or []),
        },
        "anomalies": {
            "duplicateProductNames": sorted(
                name for name, count in names.items() if name and count > 1
            ),
            "recordProductNamesNotInCurrentLibrary": sorted(
                name for name in record_names - product_names if name
            ),
            "inventoryNamesNotInMaterialMaster": sorted(
                name for name in inventory_names - material_names if name
            ),
        },
    }


def decode_legacy_image(data_uri: str) -> tuple[bytes, str, int, int]:
    match = DATA_URI_RE.match(data_uri.strip())
    if not match:
        raise ValueError("图片不是受支持的 data URI")
    try:
        content = base64.b64decode(match.group(2), validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError("图片 Base64 损坏") from exc
    try:
        image = Image.open(BytesIO(content))
        image.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError("图片内容损坏") from exc
    detected = (image.format or "").upper()
    if detected not in {"JPEG", "PNG", "WEBP"}:
        raise ValueError(f"图片格式不受支持：{detected or 'unknown'}")
    suffix = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}[detected]
    return content, suffix, image.width, image.height


def upsert_image(
    db,
    *,
    product: ThreeDPrintingProduct,
    data_uri: str,
    asset_root: Path,
    timestamp: str,
) -> None:
    content, suffix, width, height = decode_legacy_image(data_uri)
    digest = sha256(content).hexdigest()
    storage_key = f"{FACTORY_ID}/{product.id}/{digest}{suffix}"
    target = (asset_root / storage_key).resolve()
    if asset_root not in target.parents:
        raise ValueError("图片存储路径越界")
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.parent / f".{uuid4().hex[:8]}.tmp"
        temporary.write_bytes(content)
        temporary.replace(target)
    image = db.scalar(
        select(ThreeDPrintingProductImage).where(
            ThreeDPrintingProductImage.product_id == product.id
        )
    )
    mime_type = {
        ".jpg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }[suffix]
    if image is None:
        image = ThreeDPrintingProductImage(
            id=f"3dimg-{uuid4().hex}",
            product_id=product.id,
            factory_id=FACTORY_ID,
            storage_key=storage_key,
            sha256=digest,
            mime_type=mime_type,
            size_bytes=len(content),
            width=width,
            height=height,
            original_file_name=f"legacy-{product.legacy_id}{suffix}",
            is_current=True,
            uploaded_by="legacy-migration",
            uploaded_by_name="旧系统迁移",
            created_at=timestamp,
        )
        db.add(image)
        return
    image.storage_key = storage_key
    image.sha256 = digest
    image.mime_type = mime_type
    image.size_bytes = len(content)
    image.width = width
    image.height = height
    image.original_file_name = f"legacy-{product.legacy_id}{suffix}"
    image.is_current = True


def migrate(
    payload: dict[str, Any],
    report: dict[str, Any],
    *,
    source: Path,
    asset_dir: Path | None,
) -> dict[str, Any]:
    _load_import_runtime()
    source_sha = report["sourceSha256"]
    started_at = now_text()
    asset_dir = asset_dir or Path(settings.three_d_asset_dir)
    asset_root = asset_dir.expanduser().resolve()
    asset_root.mkdir(parents=True, exist_ok=True)
    run_id = f"3dmigration-{uuid4().hex}"

    with SessionLocal() as db:
        migration_run = db.scalar(
            select(ThreeDPrintingMigrationRun).where(
                ThreeDPrintingMigrationRun.factory_id == FACTORY_ID,
                ThreeDPrintingMigrationRun.source_sha256 == source_sha,
            )
        )
        if migration_run is not None and migration_run.status == "completed":
            previous = json.loads(migration_run.summary_json or "{}")
            return {
                **report,
                "status": "already_completed",
                "migrationRunId": migration_run.id,
                "previousResult": previous,
            }
        if migration_run is None:
            migration_run = ThreeDPrintingMigrationRun(
                id=run_id,
                factory_id=FACTORY_ID,
                source_file_name=source.name[:255],
                source_sha256=source_sha,
                source_size_bytes=report["sourceSizeBytes"],
                status="running",
                summary_json="{}",
                started_at=started_at,
                completed_at="",
            )
            db.add(migration_run)
        else:
            migration_run.status = "running"
            migration_run.summary_json = "{}"
            migration_run.started_at = started_at
            migration_run.completed_at = ""
            run_id = migration_run.id
        db.commit()

        counters: Counter[str] = Counter()
        try:
            legacy_settings = payload.get("settings") or {}
            setting = db.get(ThreeDPrintingSetting, FACTORY_ID)
            if setting is None:
                setting = ThreeDPrintingSetting(
                    factory_id=FACTORY_ID,
                    created_at=started_at,
                    updated_at=started_at,
                )
                db.add(setting)
            setting.machine_count = max(1, value_int(legacy_settings.get("machines"), 11))
            setting.electricity_per_machine_day = value_float(
                legacy_settings.get("elecPerMachine"),
                1.5,
            )
            setting.labor_per_day = value_float(legacy_settings.get("laborPerDay"), 220)
            setting.material_loss_rate = value_float(
                legacy_settings.get("lossRate"),
                1.2,
            )
            setting.profit_rate_percent = value_float(
                legacy_settings.get("profitRate"),
                40,
            )
            setting.revision = max(1, setting.revision or 1)
            setting.updated_by = "legacy-migration"
            setting.updated_by_name = "旧系统迁移"
            setting.updated_at = started_at
            counters["settings"] = 1

            for machine_no in range(1, setting.machine_count + 1):
                printer = db.scalar(
                    select(ThreeDPrintingPrinter).where(
                        ThreeDPrintingPrinter.factory_id == FACTORY_ID,
                        ThreeDPrintingPrinter.machine_no == machine_no,
                    )
                )
                if printer is None:
                    printer = ThreeDPrintingPrinter(
                        id=f"3dprinter-{FACTORY_ID}-{machine_no}",
                        factory_id=FACTORY_ID,
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
                        created_at=started_at,
                        updated_at=started_at,
                    )
                    db.add(printer)
                counters["printers"] += 1

            material_by_name: dict[str, ThreeDPrintingMaterial] = {}
            for index, item in enumerate(payload.get("materials") or []):
                if not isinstance(item, dict):
                    continue
                name = value_text(item.get("name"), maximum=255)
                if not name:
                    continue
                legacy_id = value_text(item.get("id"), maximum=64)
                material = db.scalar(
                    select(ThreeDPrintingMaterial).where(
                        ThreeDPrintingMaterial.factory_id == FACTORY_ID,
                        ThreeDPrintingMaterial.legacy_id == legacy_id,
                    )
                )
                if material is None:
                    material = db.scalar(
                        select(ThreeDPrintingMaterial).where(
                            ThreeDPrintingMaterial.factory_id == FACTORY_ID,
                            ThreeDPrintingMaterial.name == name,
                        )
                    )
                if material is None:
                    material = ThreeDPrintingMaterial(
                        id=stable_id("3dmat-legacy-", legacy_id, f"{index}:{name}"),
                        factory_id=FACTORY_ID,
                        legacy_id=legacy_id,
                        name=name,
                        material_type="",
                        price_per_kg=0,
                        is_active=True,
                        revision=1,
                        created_at=started_at,
                        updated_at=started_at,
                    )
                    db.add(material)
                material.legacy_id = legacy_id
                material.name = name
                material.material_type = value_text(item.get("type"), maximum=64)
                material.price_per_kg = max(0, value_float(item.get("priceKg")))
                material.is_active = True
                material.updated_at = started_at
                material_by_name[name] = material
                counters["materials"] += 1

            product_name_groups: dict[str, list[ThreeDPrintingProduct]] = {}
            for index, item in enumerate(payload.get("products") or []):
                if not isinstance(item, dict):
                    continue
                name = value_text(item.get("name"), maximum=255)
                if not name:
                    continue
                legacy_id = value_text(item.get("id"), maximum=64)
                product = db.scalar(
                    select(ThreeDPrintingProduct).where(
                        ThreeDPrintingProduct.factory_id == FACTORY_ID,
                        ThreeDPrintingProduct.legacy_id == legacy_id,
                    )
                )
                if product is None:
                    product = ThreeDPrintingProduct(
                        id=stable_id("3dprod-legacy-", legacy_id, f"{index}:{name}"),
                        factory_id=FACTORY_ID,
                        legacy_id=legacy_id,
                        name=name,
                        customer="",
                        material_name="",
                        weight_g=0,
                        duration_hours=0,
                        default_quantity=1,
                        quoted_price=0,
                        is_active=True,
                        revision=1,
                        created_at=started_at,
                        updated_at=started_at,
                    )
                    db.add(product)
                product.name = name
                product.customer = value_text(item.get("customer"), maximum=255)
                product.material_name = value_text(item.get("material"), maximum=255)
                product.weight_g = max(0, value_float(item.get("weight")))
                product.duration_hours = max(0, value_float(item.get("time")))
                product.default_quantity = max(1, value_int(item.get("qty"), 1))
                product.quoted_price = max(0, value_float(item.get("price")))
                product.is_active = True
                product.updated_at = started_at
                product_name_groups.setdefault(name, []).append(product)
                image_uri = value_text(item.get("image"), maximum=40_000_000)
                if image_uri:
                    upsert_image(
                        db,
                        product=product,
                        data_uri=image_uri,
                        asset_root=asset_root,
                        timestamp=started_at,
                    )
                    counters["productImages"] += 1
                counters["products"] += 1
            db.flush()

            unique_products = {
                name: rows[0] for name, rows in product_name_groups.items() if len(rows) == 1
            }
            records_by_day = payload.get("records") or {}
            for business_date, day in records_by_day.items():
                if not isinstance(day, dict):
                    continue
                day_status = db.scalar(
                    select(ThreeDPrintingDayStatus).where(
                        ThreeDPrintingDayStatus.factory_id == FACTORY_ID,
                        ThreeDPrintingDayStatus.business_date == business_date,
                    )
                )
                if day_status is None:
                    day_status = ThreeDPrintingDayStatus(
                        id=stable_id(
                            "3dday-legacy-",
                            business_date,
                            business_date,
                        ),
                        factory_id=FACTORY_ID,
                        business_date=value_text(business_date, maximum=10),
                        is_day_off=bool(day.get("off")),
                        revision=1,
                        updated_by="legacy-migration",
                        updated_at=started_at,
                    )
                    db.add(day_status)
                else:
                    day_status.is_day_off = bool(day.get("off"))
                    day_status.updated_at = started_at
                counters["businessDates"] += 1

                for index, item in enumerate(day.get("items") or []):
                    if not isinstance(item, dict):
                        continue
                    legacy_id = value_text(item.get("_id"), maximum=96)
                    fallback_seed = (
                        f"{business_date}:{index}:{item.get('machine')}:"
                        f"{item.get('productName')}:{item.get('printStartTime')}"
                    )
                    record = db.scalar(
                        select(ThreeDPrintingProductionRecord).where(
                            ThreeDPrintingProductionRecord.factory_id == FACTORY_ID,
                            ThreeDPrintingProductionRecord.legacy_id == legacy_id,
                        )
                    )
                    if record is None:
                        record = ThreeDPrintingProductionRecord(
                            id=stable_id("3drec-legacy-", legacy_id, fallback_seed),
                            factory_id=FACTORY_ID,
                            legacy_id=legacy_id or sha256(
                                fallback_seed.encode("utf-8")
                            ).hexdigest()[:32],
                            business_date=value_text(business_date, maximum=10),
                            machine_no=0,
                            status="idle",
                            product_id="",
                            product_name="",
                            material_name="",
                            weight_g=0,
                            quantity=1,
                            duration_hours=0,
                            design_fee=0,
                            quoted_price=0,
                            customer="",
                            remark="",
                            auto_record=False,
                            print_start_at="",
                            print_end_at="",
                            gcode_file="",
                            inventory_consumed=False,
                            legacy_updated_at="",
                            deleted_at="",
                            revision=1,
                            created_by="legacy-migration",
                            created_by_name="旧系统迁移",
                            created_at=started_at,
                            updated_at=started_at,
                        )
                        db.add(record)
                    product_name = value_text(item.get("productName"), maximum=255)
                    matched_product = unique_products.get(product_name)
                    updated_at = legacy_timestamp(item.get("_updatedAt"), started_at)
                    record.business_date = value_text(business_date, maximum=10)
                    record.machine_no = max(0, value_int(item.get("machine")))
                    record.status = value_text(item.get("status"), maximum=32) or "idle"
                    record.product_id = matched_product.id if matched_product else ""
                    record.product_name = product_name
                    record.material_name = value_text(item.get("material"), maximum=255)
                    record.weight_g = max(0, value_float(item.get("weight")))
                    record.quantity = max(0, value_int(item.get("qty"), 1))
                    record.duration_hours = max(0, value_float(item.get("time")))
                    record.design_fee = max(0, value_float(item.get("designFee")))
                    record.quoted_price = max(0, value_float(item.get("price")))
                    record.customer = value_text(item.get("customer"), maximum=255)
                    record.remark = value_text(item.get("remark"))
                    record.auto_record = bool(item.get("autoRecord"))
                    record.print_start_at = value_text(
                        item.get("printStartTime"),
                        maximum=32,
                    )
                    record.print_end_at = value_text(
                        item.get("printEndTime"),
                        maximum=32,
                    )
                    record.gcode_file = value_text(item.get("_gcodeFile"), maximum=512)
                    record.inventory_consumed = False
                    record.legacy_updated_at = updated_at
                    record.deleted_at = updated_at if item.get("_deleted") else ""
                    record.created_at = legacy_timestamp(
                        item.get("createdAt"),
                        record.print_start_at or updated_at,
                    )
                    record.updated_at = updated_at
                    counters["productionRecords"] += 1
                    if record.deleted_at:
                        counters["softDeletedRecords"] += 1

            for material_name, item in (payload.get("inventory") or {}).items():
                if not isinstance(item, dict):
                    continue
                name = value_text(material_name, maximum=255)
                inventory = db.scalar(
                    select(ThreeDPrintingInventory).where(
                        ThreeDPrintingInventory.factory_id == FACTORY_ID,
                        ThreeDPrintingInventory.material_name == name,
                    )
                )
                if inventory is None:
                    inventory = ThreeDPrintingInventory(
                        id=stable_id("3dinv-legacy-", "", name),
                        factory_id=FACTORY_ID,
                        material_name=name,
                        stock_g=0,
                        min_stock_g=3000,
                        revision=1,
                        created_at=started_at,
                        updated_at=started_at,
                    )
                    db.add(inventory)
                inventory.stock_g = max(0, value_float(item.get("stockG")))
                inventory.min_stock_g = max(0, value_float(item.get("minStockG"), 3000))
                inventory.updated_at = started_at
                db.flush()
                opening_legacy_id = f"inventory-snapshot:{name}"
                opening = db.scalar(
                    select(ThreeDPrintingInventoryMovement).where(
                        ThreeDPrintingInventoryMovement.factory_id == FACTORY_ID,
                        ThreeDPrintingInventoryMovement.legacy_id == opening_legacy_id,
                    )
                )
                if opening is None:
                    opening = ThreeDPrintingInventoryMovement(
                        id=stable_id("3dmov-legacy-", "", opening_legacy_id),
                        factory_id=FACTORY_ID,
                        inventory_id=inventory.id,
                        material_name=name,
                        movement_type="migration_opening",
                        delta_g=inventory.stock_g,
                        balance_after_g=inventory.stock_g,
                        business_date=started_at[:10],
                        vendor="",
                        cost=0,
                        remark="旧系统迁移时的库存快照；不重放历史入库以免重复计入",
                        source_record_id="",
                        legacy_id=opening_legacy_id,
                        actor_id="legacy-migration",
                        actor_name="旧系统迁移",
                        created_at=started_at,
                    )
                    db.add(opening)
                else:
                    opening.delta_g = inventory.stock_g
                    opening.balance_after_g = inventory.stock_g
                counters["inventoryItems"] += 1

            inventory_map = {
                row.material_name: row
                for row in db.scalars(
                    select(ThreeDPrintingInventory).where(
                        ThreeDPrintingInventory.factory_id == FACTORY_ID
                    )
                )
            }
            for index, item in enumerate(payload.get("stockInLogs") or []):
                if not isinstance(item, dict):
                    continue
                name = value_text(item.get("material"), maximum=255)
                inventory = inventory_map.get(name)
                if inventory is None:
                    inventory = ThreeDPrintingInventory(
                        id=stable_id("3dinv-legacy-", "", name),
                        factory_id=FACTORY_ID,
                        material_name=name,
                        stock_g=0,
                        min_stock_g=3000,
                        revision=1,
                        created_at=started_at,
                        updated_at=started_at,
                    )
                    db.add(inventory)
                    db.flush()
                    inventory_map[name] = inventory
                legacy_id = f"stock-in:{value_text(item.get('id')) or index}"
                movement = db.scalar(
                    select(ThreeDPrintingInventoryMovement).where(
                        ThreeDPrintingInventoryMovement.factory_id == FACTORY_ID,
                        ThreeDPrintingInventoryMovement.legacy_id == legacy_id,
                    )
                )
                if movement is None:
                    movement = ThreeDPrintingInventoryMovement(
                        id=stable_id("3dmov-legacy-", "", legacy_id),
                        factory_id=FACTORY_ID,
                        inventory_id=inventory.id,
                        material_name=name,
                        movement_type="legacy_stock_in",
                        delta_g=max(0, value_float(item.get("amountG"))),
                        balance_after_g=inventory.stock_g,
                        business_date=value_text(item.get("date"), maximum=10),
                        vendor=value_text(item.get("vendor"), maximum=255),
                        cost=max(0, value_float(item.get("cost"))),
                        remark=(
                            value_text(item.get("remark"))
                            + "（历史流水已保留；库存以迁移快照为准）"
                        ).strip(),
                        source_record_id="",
                        legacy_id=legacy_id,
                        actor_id="legacy-migration",
                        actor_name="旧系统迁移",
                        created_at=started_at,
                    )
                    db.add(movement)
                counters["stockInLogs"] += 1

            for model, source_key, prefix, counter_key, mapper in (
                (
                    ThreeDPrintingSchedule,
                    "schedules",
                    "3dschedule-legacy-",
                    "schedules",
                    _map_schedule,
                ),
                (
                    ThreeDPrintingMaintenance,
                    "maintenance",
                    "3dmaint-legacy-",
                    "maintenance",
                    _map_maintenance,
                ),
            ):
                for index, item in enumerate(payload.get(source_key) or []):
                    if not isinstance(item, dict):
                        continue
                    legacy_id = value_text(item.get("id"), maximum=96)
                    fallback_seed = f"{source_key}:{index}:{json.dumps(item, ensure_ascii=False, sort_keys=True)}"
                    row = db.scalar(
                        select(model).where(
                            model.factory_id == FACTORY_ID,
                            model.legacy_id == legacy_id,
                        )
                    )
                    if row is None:
                        row = mapper(
                            stable_id(prefix, legacy_id, fallback_seed),
                            legacy_id
                            or sha256(fallback_seed.encode("utf-8")).hexdigest()[:32],
                            item,
                            started_at,
                        )
                        db.add(row)
                    else:
                        mapper(row.id, row.legacy_id or "", item, started_at, row=row)
                    counters[counter_key] += 1

            completed_at = now_text()
            result = {
                **report,
                "status": "completed",
                "migrationRunId": run_id,
                "migrated": dict(counters),
                "assetDirectory": str(asset_root),
                "startedAt": started_at,
                "completedAt": completed_at,
            }
            db.add(
                ThreeDPrintingAuditEvent(
                    id=f"3daudit-{uuid4().hex}",
                    factory_id=FACTORY_ID,
                    entity_type="migration_run",
                    entity_id=run_id,
                    action="legacy_import_completed",
                    detail_json=json.dumps(
                        {
                            "sourceFile": source.name,
                            "sourceSha256": source_sha,
                            "migrated": dict(counters),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    actor_id="legacy-migration",
                    actor_name="旧系统迁移",
                    actor_type="system",
                    request_id="",
                    created_at=completed_at,
                )
            )
            migration_run.status = "completed"
            migration_run.summary_json = json.dumps(
                result,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            migration_run.completed_at = completed_at
            db.commit()
            return result
        except Exception as exc:
            db.rollback()
            failed_run = db.get(ThreeDPrintingMigrationRun, run_id)
            if failed_run is not None:
                failed_run.status = "failed"
                failed_run.summary_json = json.dumps(
                    {"error": str(exc)},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                failed_run.completed_at = now_text()
                db.commit()
            raise


def _map_schedule(
    row_id: str,
    legacy_id: str,
    item: dict[str, Any],
    timestamp: str,
    *,
    row: ThreeDPrintingSchedule | None = None,
) -> ThreeDPrintingSchedule:
    row = row or ThreeDPrintingSchedule(
        id=row_id,
        factory_id=FACTORY_ID,
        legacy_id=legacy_id,
        business_date="",
        product_id="",
        product_name="",
        customer="",
        material_name="",
        weight_g=0,
        quantity=1,
        machine_no=0,
        priority="normal",
        status="pending",
        remark="",
        revision=1,
        created_by="legacy-migration",
        created_by_name="旧系统迁移",
        created_at=timestamp,
        updated_at=timestamp,
    )
    row.business_date = value_text(item.get("date"), maximum=10)
    row.product_name = value_text(
        item.get("productName") or item.get("product"),
        maximum=255,
    )
    row.customer = value_text(item.get("customer"), maximum=255)
    row.material_name = value_text(item.get("material"), maximum=255)
    row.weight_g = max(0, value_float(item.get("weight")))
    row.quantity = max(1, value_int(item.get("qty"), 1))
    row.machine_no = max(0, value_int(item.get("machine")))
    priority = value_text(item.get("priority"), maximum=16)
    row.priority = priority if priority in {"high", "normal", "low"} else "normal"
    status = value_text(item.get("status"), maximum=24)
    row.status = status if status in {"pending", "running", "completed"} else "pending"
    row.remark = value_text(item.get("remark"))
    row.updated_at = timestamp
    return row


def _map_maintenance(
    row_id: str,
    legacy_id: str,
    item: dict[str, Any],
    timestamp: str,
    *,
    row: ThreeDPrintingMaintenance | None = None,
) -> ThreeDPrintingMaintenance:
    row = row or ThreeDPrintingMaintenance(
        id=row_id,
        factory_id=FACTORY_ID,
        legacy_id=legacy_id,
        business_date="",
        machine_no=0,
        maintenance_type="other",
        description="",
        cost=0,
        vendor="",
        remark="",
        revision=1,
        created_by="legacy-migration",
        created_by_name="旧系统迁移",
        created_at=timestamp,
        updated_at=timestamp,
    )
    row.business_date = value_text(item.get("date"), maximum=10)
    row.machine_no = max(0, value_int(item.get("machine")))
    row.maintenance_type = (
        value_text(item.get("type"), maximum=64) or "other"
    )
    row.description = value_text(
        item.get("description") or item.get("content"),
        maximum=4000,
    )
    row.cost = max(0, value_float(item.get("cost")))
    row.vendor = value_text(item.get("vendor"), maximum=255)
    row.remark = value_text(item.get("remark"))
    row.updated_at = timestamp
    return row


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = SafeParser(description="迁移旧版3D打印机管理数据")
    sources = parser.add_mutually_exclusive_group(required=True)
    sources.add_argument("--source", type=Path, help="SQLite快照或显式兼容JSON")
    sources.add_argument("--source-dir", type=Path, help="含SQLite/WAL的冻结目录")
    sources.add_argument("--source-zip", type=Path, help="旧ZIP，只读取白名单文件")
    parser.add_argument(
        "--asset-dir",
        type=Path,
        help="产品图片持久化目录；默认使用 THREE_D_ASSET_DIR",
    )
    parser.add_argument("--factory-id", default=FACTORY_ID, choices=[FACTORY_ID])
    parser.add_argument("--site-code", default="heyuan", choices=["heyuan"])
    parser.add_argument("--mode", choices=["analyze", "dry-run", "import", "reconcile"], default="analyze")
    parser.add_argument("--allow-json-fallback", action="store_true", help="允许分析可能过期的JSON；不能用于本次正式切换")
    parser.add_argument("--wal-checkpoint-confirmed", action="store_true")
    parser.add_argument("--snapshot-dir", type=Path, help="可选，保留一致性快照的新目录")
    parser.add_argument("--expected-audit", type=Path, help="可选，核对本次上传审计的验收基线")
    parser.add_argument("--dry-run", action="store_true", help="仅校验和统计，不写数据库")
    parser.add_argument("--migration-batch", help="续跑或对账的迁移批次 ID；对账时必填")
    parser.add_argument("--resume", action="store_true", help="从指定批次已提交的 checkpoint 续跑")
    parser.add_argument("--chunk-size", type=int, default=200, choices=range(100, 501), metavar="100..500")
    parser.add_argument("--report", type=Path, help="可选的 JSON 报告输出路径")
    return parser.parse_args(argv)


def _load_target_runtime(args: argparse.Namespace, source: Path, snapshot: Path | None = None) -> tuple[Any, Path]:
    """Load application dependencies only after read-only source validation."""
    from app.core.config import settings
    from sqlalchemy.engine import make_url

    # Refuse a configured target that is the authoritative source itself. This
    # check precedes app.db import, which can initialize SQLite directories.
    target = make_url(settings.database_url)
    protected_roots = [source if source.is_dir() else source.parent]
    if snapshot is not None:
        protected_roots.append(snapshot.resolve().parent)
    if target.get_backend_name() == "sqlite" and target.database not in (None, "", ":memory:"):
        target_path = Path(target.database).expanduser().resolve()
        if any(root in target_path.parents or target_path == root for root in protected_roots):
            raise SnapshotError("target_database_overlaps_source")
        if args.report and args.report.expanduser().resolve() == target_path:
            raise SnapshotError("report_output_overlaps_target_database")
    asset_dir = (args.asset_dir or Path(settings.three_d_asset_dir)).expanduser().resolve()
    if any(asset_dir == root or root in asset_dir.parents or asset_dir in root.parents for root in protected_roots):
        raise SnapshotError("asset_directory_overlaps_source")
    if args.report and (args.report.expanduser().resolve() == asset_dir or asset_dir in args.report.expanduser().resolve().parents):
        raise SnapshotError("report_output_overlaps_asset_directory")

    from app.db import SessionLocal, ensure_three_d_printing_schema_ready

    try:
        ensure_three_d_printing_schema_ready()
    except RuntimeError:
        raise SnapshotError("target_schema_upgrade_required") from None
    return SessionLocal, asset_dir


def _run_sqlite_migration(args: argparse.Namespace, captured: Any, source: Path) -> dict[str, Any]:
    session_factory, asset_dir = _load_target_runtime(args, source, captured.path)
    from legacy_three_d_importer import MigrationError, run_migration

    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=BACKEND_DIR, capture_output=True,
            text=True, timeout=10, check=False,
        )
        code_revision = revision.stdout.strip() if revision.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        code_revision = ""
    if not re.fullmatch(r"[0-9a-f]{40,64}", code_revision):
        code_revision = ""
    try:
        return run_migration(
            captured.path, captured.manifest, session_factory=session_factory,
            asset_dir=asset_dir, mode=args.mode, migration_batch=args.migration_batch,
            chunk_size=args.chunk_size, resume=args.resume, code_revision=code_revision,
        )
    except MigrationError as exc:
        batch_id = getattr(exc, "batch_id", None)
        if isinstance(batch_id, str) and re.fullmatch(r"3dbatch-[0-9a-f]{32}", batch_id):
            return {"status": "failed", "batch_id": batch_id, "error_codes": [exc.code],
                    "reconciliation": {"passed": False, "issues": [{"code": exc.code}]}}
        raise SnapshotError(exc.code) from None


def _baseline_check(report: dict[str, Any], audit_path: Path) -> dict[str, Any]:
    audit = json.loads(audit_path.read_text(encoding="utf-8-sig"))
    keys = {
        "authoritative_sqlite": ("materials", "products", "product_images", "record_dates", "date_min", "date_max",
                                 "records_stored", "records_active", "records_tombstoned", "inventory_items", "stock_in_logs", "schedules", "maintenance"),
        "records_quality": ("open_records_missing_end_time", "records_with_start_and_end", "status_counts"),
        "images_quality": ("rows", "total_bytes", "orphan_image_rows", "products_with_image"),
        "materials_inventory_quality": ("inventory_total_g", "stock_in_total_g", "stock_in_total_cost"),
        "business_totals_active_records": ("quantity_total", "planned_material_g_total", "design_fee_total", "quoted_revenue_total"),
    }
    checked: list[str] = []
    mismatches: list[str] = []
    for section, fields in keys.items():
        for field in fields:
            label = section + "." + field
            checked.append(label)
            if section not in audit or field not in audit[section] or report.get(section, {}).get(field) != audit[section][field]:
                mismatches.append(label)
    manifest = report.get("manifest", {})
    if manifest.get("source", {}).get("kind") == "zip":
        checked.append("source.zip_sha256")
        if manifest["source"]["sha256"] != audit.get("source", {}).get("zip_sha256"):
            mismatches.append("source.zip_sha256")
    checked.append("source.sqlite_updated_at_ms")
    if manifest.get("checks", {}).get("state_updated_at_ms") != audit.get("source", {}).get("sqlite_updated_at_ms"):
        mismatches.append("source.sqlite_updated_at_ms")
    return {"status": "passed" if not mismatches else "failed", "checked_fields": checked, "mismatched_fields": mismatches}


def _analyze_source(args: argparse.Namespace) -> dict[str, Any]:
    source = (args.source_dir or args.source_zip or args.source).expanduser().resolve()
    if source.is_dir():
        if (source / "data.sqlite").is_file():
            pass  # SQLite always wins, even if a JSON filename was supplied.
        elif (source / "snapshot.sqlite").is_file():
            source = source / "snapshot.sqlite"
        else:
            source = source / "data.json"
    elif source.suffix.lower() == ".json" and (source.parent / "data.sqlite").is_file():
        source = source.parent
    if source.suffix.lower() == ".json" and source.is_file():
        if args.mode == "reconcile" or args.migration_batch or args.resume:
            raise SnapshotError("checkpoint_migration_requires_sqlite")
        if args.expected_audit:
            raise SnapshotError("authoritative_audit_requires_sqlite")
        if not args.allow_json_fallback:
            raise SnapshotError("json_fallback_requires_explicit_allow")
        print("警告：JSON可能过期，不是本次生产切换的权威数据源。", file=sys.stderr)
        payload = read_json(source)
        if args.mode == "import" and not args.dry_run:
            _session_factory, asset_dir = _load_target_runtime(args, source)
            raw, payload = load_source(source)
            assert_no_secrets(payload)
            report = migrate(payload, analyze(payload, raw, source), source=source, asset_dir=asset_dir)
            report["warnings"] = ["legacy_json_import_not_authoritative_for_cutover"]
            return report
        report = analyze_state(payload, [], source_kind="json_fallback")
        report["source"] = file_fingerprint(source)
        return report
    # Default analysis leaves no transport artifacts. --snapshot-dir retains a bundle.
    with tempfile.TemporaryDirectory(prefix="three-d-analysis-") as temporary:
        captured = capture_snapshot(source, args.snapshot_dir or Path(temporary) / "snapshot",
                                    wal_checkpoint_confirmed=args.wal_checkpoint_confirmed)
        report = analyze_state(captured.state, captured.images)
        report["manifest"] = captured.manifest
        report["image_manifest"] = captured.images
        if captured.fallback_state is not None:
            json_report = analyze_state(captured.fallback_state, [], source_kind="json_fallback")
            report["data_json_snapshot"] = json_report["data_json_snapshot"]
            report["data_json_gap_vs_sqlite"] = {
                key: value - json_report["data_json_snapshot"].get(key, 0)
                for key, value in report["authoritative_sqlite"].items()
                if type(value) is int and type(json_report["data_json_snapshot"].get(key)) is int
            }
            report.setdefault("warnings", []).append("compatibility_json_compared_only_never_imported")
        if args.expected_audit:
            report["baseline_validation"] = _baseline_check(report, args.expected_audit)
        # A failed acceptance baseline must never be followed by target writes.
        if args.mode in {"import", "reconcile"} and not args.dry_run:
            if report.get("baseline_validation", {}).get("status") == "failed":
                report["status"] = "analyzed_with_errors"
                return report
            report.update(_run_sqlite_migration(args, captured, source))
        return report


def main() -> int:
    try:
        args = parse_args()
        # Refuse existing reports, including any source JSON supplied by mistake.
        if args.report and args.report.expanduser().resolve().exists():
            raise SnapshotError("report_output_already_exists")
        source_path = (args.source_dir or args.source_zip or args.source).expanduser().resolve()
        if source_path.is_dir() and args.report and source_path in args.report.expanduser().resolve().parents:
            raise SnapshotError("report_output_overlaps_source")
        if args.snapshot_dir and args.report:
            snapshot_root = args.snapshot_dir.expanduser().resolve()
            report_path = args.report.expanduser().resolve()
            if report_path == snapshot_root or snapshot_root in report_path.parents:
                raise SnapshotError("report_output_overlaps_snapshot_directory")
        if args.mode == "reconcile" and not args.migration_batch:
            raise SnapshotError("reconcile_requires_migration_batch")
        if args.resume and (args.mode != "import" or not args.migration_batch or args.dry_run):
            raise SnapshotError("resume_requires_import_and_migration_batch")
        if args.migration_batch and args.mode not in {"import", "reconcile"}:
            raise SnapshotError("migration_batch_requires_import_or_reconcile")
        report = _analyze_source(args)
        report.update(schema_version=1, factory_id=FACTORY_ID, site_code="heyuan")
        report.setdefault("status", "dry_run" if args.dry_run or args.mode == "dry-run" else "analyzed")
        blocking = report.get("images_quality", {}).get("invalid_images", 0) > 0
        blocking = blocking or report.get("baseline_validation", {}).get("status") == "failed"
        blocking = blocking or report.get("status") in {"failed", "imported_with_errors", "reconciliation_failed"}
        blocking = blocking or report.get("reconciliation", {}).get("passed") is False
        if report.get("source_kind") == "sqlite" and args.mode in {"import", "reconcile"} and not args.dry_run:
            blocking = blocking or report.get("status") not in {"reconciled", "already_reconciled"}
            blocking = blocking or report.get("reconciliation", {}).get("passed") is not True
        if blocking and report.get("status") in {"analyzed", "dry_run"}:
            report["status"] = "analyzed_with_errors"
        assert_no_secrets(report)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            report_path = args.report.expanduser().resolve()
            report_path.parent.mkdir(parents=True, exist_ok=True)
            with report_path.open("x", encoding="utf-8") as stream:
                stream.write(rendered + "\n")
            # Keep terminal logs small and exclude source business names/row data.
            print(json.dumps({"status": report["status"], "report_written": True,
                              "batch_id": report.get("batch_id"),
                              "counts": report.get("authoritative_sqlite", report.get("data_json_snapshot", {})),
                              "reconciliation_passed": report.get("reconciliation", {}).get("passed"),
                              "baseline_validation": report.get("baseline_validation")}, ensure_ascii=False))
        else:
            print(rendered)
        return 2 if blocking else 0
    except Exception:  # noqa: BLE001 -- CLI boundary must never expose source data or connection secrets.
        exc = sys.exc_info()[1]
        print(json.dumps({"status": "failed", "error_code": exc.code if isinstance(exc, SnapshotError) else "analysis_failed"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
