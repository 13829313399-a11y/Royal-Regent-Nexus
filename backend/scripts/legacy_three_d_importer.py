"""Versioned SQLite migration with durable row ownership and resumable transactions.

The caller supplies an already migrated database session factory explicitly. This
module never initializes schema, selects a database, reads device config or sends
device commands. A frozen private copy pins the source across chunk commits.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
BACKEND = SCRIPTS.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.models import three_d_printing as models
from legacy_sqlite_reader import (
    SnapshotError,
    assert_no_secrets,
    connect_readonly,
    file_fingerprint,
    inspect_snapshot,
)
from legacy_three_d_analysis import _normalized, analyze_state, derive_run_status

FACTORY = "huakang-a"
SITE = "3dsite-huakang-a-heyuan"
SOURCE = "legacy-three-d-sqlite"
VERSION = "three-d-import-v2"
SUCCESS = {"imported", "updated", "skipped"}
MODEL_NAMES = {
    "settings": "ThreeDPrintingSetting", "printers": "ThreeDPrintingPrinter",
    "materials": "ThreeDPrintingMaterial", "products": "ThreeDPrintingProduct",
    "days": "ThreeDPrintingDayStatus", "records": "ThreeDPrintingProductionRecord",
    "inventory": "ThreeDPrintingInventory", "stock_in_logs": "ThreeDPrintingInventoryMovement",
    "schedules": "ThreeDPrintingSchedule", "maintenance": "ThreeDPrintingMaintenance",
    "images": "ThreeDPrintingProductImage", "material_aliases": "ThreeDPrintingMaterialAlias",
}


class MigrationError(ValueError):
    """Static public code; never include database exceptions or source values."""
    def __init__(self, code: str, *, batch_id: str | None = None):
        super().__init__(code)
        self.code = code
        self.batch_id = batch_id


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


def _json(value: Any) -> str:
    def scalar(item):
        if isinstance(item, Decimal):
            return format(item.normalize(), "f")
        raise TypeError("unsupported_report_type")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=scalar, allow_nan=False)


def _hash(value: Any) -> str:
    return sha256(_json(value).encode("utf-8")).hexdigest()


def _id(entity: str, legacy: str) -> str:
    return "3dm-" + uuid5(NAMESPACE_URL, f"{FACTORY}/{SITE}/{SOURCE}/{entity}/{legacy}").hex


def _text(value: Any, maximum: int = 255) -> str:
    if value is None:
        return ""
    if not isinstance(value, (str, int)) or isinstance(value, bool):
        raise MigrationError("invalid_text_field")
    text = str(value)
    if len(text) > maximum:
        raise MigrationError("text_field_too_long")
    return text


def _decimal(value: Any, *, integer=False, allow_negative=False) -> Decimal | int:
    if value is None or value == "":
        value = 0
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise MigrationError("invalid_numeric_field") from None
    if isinstance(value, bool) or not number.is_finite() or abs(number) >= Decimal("1e10"):
        raise MigrationError("invalid_numeric_field")
    if number < 0 and not allow_negative:
        raise MigrationError("negative_numeric_field")
    if integer:
        if number != number.to_integral_value() or abs(number) > 2147483647:
            raise MigrationError("invalid_integer_field")
        return int(number)
    if number != number.quantize(Decimal("0.0001")):
        raise MigrationError("numeric_precision_exceeds_schema")
    return number


def _timestamp(value: Any, *, milliseconds=False) -> str:
    if value is None or value == "":
        return ""
    try:
        if milliseconds:
            parsed = datetime.fromtimestamp(int(value) / 1000, UTC)
        else:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone_china())
        return parsed.astimezone(UTC).isoformat(timespec="milliseconds")
    except (ValueError, OverflowError, TypeError, OSError):
        raise MigrationError("invalid_timestamp") from None


def timezone_china():
    from datetime import timezone
    return timezone(timedelta(hours=8))


def _date(value: Any) -> str:
    text = _text(value, 10)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise MigrationError("invalid_business_date")
    _timestamp(text)
    return text


@dataclass
class Item:
    entity: str
    legacy: str
    raw: dict
    error: str = ""

    @property
    def source_hash(self):
        return _hash(self.raw)


def _items(state: dict, images: list[dict]) -> list[Item]:
    items = [Item("settings", FACTORY, state["settings"])]
    machines = _decimal(state["settings"].get("machines"), integer=True)
    if not 1 <= machines <= 1000:
        raise MigrationError("invalid_machine_count")
    items += [Item("printers", str(n), {"machine": n}) for n in range(1, machines + 1)]
    for domain, key in (("materials", "materials"), ("products", "products")):
        for index, row in enumerate(state[key]):
            legacy = _text(row.get("id"), 64)
            items.append(Item(domain, legacy or f"missing:{index}", row, "" if legacy else "missing_legacy_id"))
    raw_materials = {str(row.get("name", "")) for row in state["materials"]} | set(state["inventory"])
    items += [Item("material_aliases", name, {"raw_name": name}) for name in sorted(raw_materials) if name]
    for day, payload in sorted(state["records"].items()):
        items.append(Item("days", day, {"date": day, "off": payload.get("off", False)}))
    for day, payload in sorted(state["records"].items()):
        for index, row in enumerate(payload["items"]):
            legacy = _text(row.get("_id"), 96)
            items.append(Item("records", legacy or f"missing:{day}:{index}", {**row, "business_date": day}, "" if legacy else "missing_legacy_id"))
    items += [Item("inventory", name, {**row, "material": name}) for name, row in sorted(state["inventory"].items())]
    for domain, key in (("stock_in_logs", "stockInLogs"), ("schedules", "schedules"), ("maintenance", "maintenance")):
        for index, row in enumerate(state.get(key, [])):
            legacy = _text(row.get("id"), 96)
            items.append(Item(domain, legacy or f"missing:{index}", row, "" if legacy else "missing_legacy_id"))
    items += [Item("images", image["product_id"], image) for image in images]
    counts = Counter((item.entity, item.legacy) for item in items)
    for item in items:
        if counts[(item.entity, item.legacy)] > 1:
            item.error = "duplicate_legacy_id"
    # Keep one explicit failure checkpoint per duplicated identity; never pick a winner.
    return list({(item.entity, item.legacy): item for item in items}.values())


def _model(entity):
    return getattr(models, MODEL_NAMES[entity])


def _target_hash(row) -> str:
    # A legacy snapshot defines machine numbers, not the live connection or telemetry.
    if isinstance(row, models.ThreeDPrintingPrinter):
        return _hash({key: getattr(row, key) for key in ("id", "factory_id", "machine_no")})
    return _hash({column.name: getattr(row, column.name) for column in row.__table__.columns})


def _get_target(db, model, identity):
    primary_key = next(iter(model.__table__.primary_key.columns))
    return db.scalar(select(model).where(primary_key == identity).with_for_update().execution_options(populate_existing=True))


def _natural_query(item: Item):
    model = _model(item.entity)
    query = select(model).where(model.factory_id == FACTORY)
    field = {"settings": "factory_id", "printers": "machine_no", "days": "business_date",
             "inventory": "material_name", "material_aliases": "raw_name", "images": "product_id"}.get(item.entity, "legacy_id")
    value = int(item.legacy) if item.entity == "printers" else _id("products", item.legacy) if item.entity == "images" else item.legacy
    return query.where(getattr(model, field) == value)


def _owned(db, item: Item):
    Row, Batch = models.ThreeDPrintingMigrationRowResult, models.ThreeDPrintingMigrationBatch
    return db.scalar(select(Row).join(Batch, Row.batch_id == Batch.id).where(
        Batch.factory_id == FACTORY, Batch.site_id == SITE, Batch.source_system == SOURCE,
        Row.entity_type == item.entity, Row.legacy_id == item.legacy,
        Row.target_id != "", Row.target_hash != "", Row.source_hash != "",
    ).order_by(Batch.source_updated_at_ms.desc(), Row.updated_at.desc()).limit(1))


def _resolve(db, entity: str, legacy: str) -> str:
    provenance = _owned(db, Item(entity, legacy, {}))
    if provenance is None or db.get(_model(entity), provenance.target_id) is None:
        raise MigrationError("dependency_unavailable")
    return provenance.target_id


def _seed_can_be_adopted(db, item: Item, row) -> bool:
    if item.entity not in {"settings", "printers"} or row.revision != 1 or row.created_at != row.updated_at:
        return False
    if item.entity == "settings":
        if row.updated_by or row.updated_by_name:
            return False
        expected = {"machine_count": 11, "electricity_per_machine_day": Decimal("1.5"), "labor_per_day": 220,
                    "material_loss_rate": Decimal("1.2"), "profit_rate_percent": 40}
        if any(getattr(row, key) != value for key, value in expected.items()):
            return False
        for domain in ("materials", "products", "records", "inventory", "schedules", "maintenance"):
            if db.scalar(select(_model(domain)).where(_model(domain).factory_id == FACTORY).limit(1)):
                return False
        return True
    else:
        n = int(item.legacy)
        expected = {"id": f"3dprinter-{FACTORY}-{n}", "legacy_id": str(n), "name": f"{n}号机", "printer_type": "bambu",
                    "model": "", "enabled": True, "connected": False, "state": "OFFLINE", "current_file": "",
                    "progress_percent": 0, "remaining_minutes": 0, "live_material": "", "nozzle_temperature": 0,
                    "bed_temperature": 0, "error_text": "", "status_payload_json": "{}", "last_seen_at": ""}
        if any(getattr(row, key) != value for key, value in expected.items()):
            return False
        if db.scalar(select(models.ThreeDPrintingProductionRecord.id).where(models.ThreeDPrintingProductionRecord.factory_id == FACTORY,
                      models.ThreeDPrintingProductionRecord.machine_no == n).limit(1)):
            return False
    for model in (models.ThreeDPrintingPrinterCommand, models.ThreeDPrintingAuditEvent):
        if db.scalar(select(model.id).where(model.factory_id == FACTORY).limit(1)):
            return False
    return True


def _record_snapshots(raw, state, *, frozen_profile=None):
    keys = ("productName", "material", "weight", "time", "qty", "price", "customer", "designFee")
    snapshot = {key: raw.get(key) for key in keys}
    flags = [f"missing_{key}" for key in keys if raw.get(key) is None or raw.get(key) == ""]
    flags += [f"zero_{key}" for key in ("weight", "time", "price") if raw.get(key) == 0]
    rates = {key: state["settings"].get(key) for key in ("machines", "elecPerMachine", "laborPerDay", "lossRate", "profitRate")}
    material_rows = [row for row in state["materials"] if row.get("name") == raw.get("material")]
    price_kg = material_rows[0].get("priceKg") if len(material_rows) == 1 else None
    if frozen_profile is not None:
        rates = frozen_profile["settings"]
        price_kg = frozen_profile.get("material_price_kg") if raw.get("material") == frozen_profile["inputs"].get("material") else None
    if price_kg is None:
        flags.append("unknown_material_price")
    cost = {"formula_version": "legacy-v1", "basis": "source_snapshot_rates_not_historical_cost_evidence",
            "settings": rates, "material_price_kg": price_kg, "inputs": snapshot,
            "material_cost_per_unit": None, "electricity_per_unit": None, "labor_per_unit": None,
            "suggested_price_per_unit": None, "quoted_total": None}
    if all(value is not None for value in (price_kg, raw.get("weight"), raw.get("time"), *rates.values())):
        weight, duration, unit = _decimal(raw["weight"]), _decimal(raw["time"]), _decimal(price_kg)
        machines = _decimal(rates["machines"], integer=True)
        if machines > 0:
            material = weight * _decimal(rates["lossRate"]) * unit / 1000
            electricity = duration / 12 * _decimal(rates["elecPerMachine"])
            labor = duration / 12 * (_decimal(rates["laborPerDay"]) / machines)
            cost.update(material_cost_per_unit=material, electricity_per_unit=electricity, labor_per_unit=labor,
                        suggested_price_per_unit=(material + electricity + labor) * (1 + _decimal(rates["profitRate"]) / 100))
    if raw.get("qty") is not None and raw.get("price") is not None:
        cost["quoted_total"] = _decimal(raw["qty"], integer=True) * _decimal(raw["price"]) + _decimal(raw.get("designFee"))
    return snapshot, cost, flags


def _preserve_cost_profile(row, payload, item, state):
    """Source corrections may change inputs, never retrospectively adopt rates."""
    try:
        original = json.loads(row.calculated_cost_snapshot_json)
        financial = ("material", "weight", "time", "qty", "price", "designFee")
        changed = [key for key in financial if original["inputs"].get(key) != item.raw.get(key)]
        original_review = bool(original.get("correction", {}).get("requires_review"))
        if not changed:
            payload["calculated_cost_snapshot_json"] = row.calculated_cost_snapshot_json
            flags = set(json.loads(payload["data_quality_flags_json"]))
            if original.get("material_price_kg") is None:
                flags.add("unknown_material_price")
            if original_review or original.get("material_price_kg") is None:
                flags.add("cost_snapshot_requires_review")
            payload["data_quality_flags_json"] = _json(sorted(flags))
            return
        _, corrected, _ = _record_snapshots(item.raw, state, frozen_profile=original)
        material_changed = "material" in changed
        corrected["basis"] = "frozen_migration_rates_with_corrected_inputs"
        review_required = material_changed or original_review or corrected["material_price_kg"] is None
        corrected["correction"] = {"changed_inputs": changed, "requires_review": review_required}
        payload["calculated_cost_snapshot_json"] = _json(corrected)
        flags = set(json.loads(payload["data_quality_flags_json"]))
        if corrected["material_price_kg"] is None:
            flags.add("unknown_material_price")
        else:
            flags.discard("unknown_material_price")
        if review_required:
            flags.add("cost_snapshot_requires_review")
        payload["data_quality_flags_json"] = _json(sorted(flags))
    except (KeyError, TypeError, json.JSONDecodeError):
        raise MigrationError("invalid_owned_cost_snapshot") from None


def _payload(db, item: Item, state: dict, batch, timestamp: str) -> dict:
    raw, entity = item.raw, item.entity
    base = {"factory_id": FACTORY}
    if entity != "settings":
        base["id"] = _id(entity, item.legacy)
    if entity in {"materials", "products", "printers", "records", "stock_in_logs", "schedules", "maintenance"}:
        base["legacy_id"] = item.legacy
    if entity not in {"material_aliases"}:
        base["created_at"] = timestamp
    if entity not in {"images", "stock_in_logs", "material_aliases"}:
        base.update(updated_at=timestamp, revision=1)
    if entity == "settings":
        base.update(machine_count=_decimal(raw.get("machines"), integer=True), electricity_per_machine_day=_decimal(raw.get("elecPerMachine")),
                    labor_per_day=_decimal(raw.get("laborPerDay")), material_loss_rate=_decimal(raw.get("lossRate")), profit_rate_percent=_decimal(raw.get("profitRate")),
                    updated_by="legacy-migration", updated_by_name="旧系统迁移")
    elif entity == "printers":
        base.update(machine_no=int(item.legacy), name=f"{item.legacy}号机", printer_type="bambu", enabled=True,
                    connected=False, state="OFFLINE", site_id=SITE)
    elif entity == "materials":
        base.update(name=_text(raw.get("name")), material_type=_text(raw.get("type"), 64), price_per_kg=_decimal(raw.get("priceKg")), is_active=True)
    elif entity == "products":
        base.update(name=_text(raw.get("name")), customer=_text(raw.get("customer")), material_name=_text(raw.get("material")),
                    weight_g=_decimal(raw.get("weight")), duration_hours=_decimal(raw.get("time")),
                    default_quantity=_decimal(raw.get("qty"), integer=True), quoted_price=_decimal(raw.get("price")), is_active=True)
    elif entity == "material_aliases":
        raw_name = _text(raw["raw_name"])
        candidates = [row for row in state["materials"] if _normalized(row.get("name")) == _normalized(raw_name)]
        canonical = _resolve(db, "materials", str(candidates[0]["id"])) if len(candidates) == 1 else None
        base.update(raw_name=raw_name, normalized_name=_normalized(raw_name), canonical_material_id=canonical,
                    source=SOURCE, approved_by="", approved_at="")
    elif entity == "days":
        base.pop("created_at")
        if not isinstance(raw["off"], bool):
            raise MigrationError("invalid_boolean_field")
        base.update(business_date=_date(raw["date"]), is_day_off=raw["off"], updated_by="legacy-migration")
    elif entity == "records":
        for field in ("_deleted", "autoRecord"):
            if field in raw and not isinstance(raw[field], bool):
                raise MigrationError("invalid_boolean_field")
        start, end = _timestamp(raw.get("printStartTime")), _timestamp(raw.get("printEndTime"))
        updated = _timestamp(raw.get("_updatedAt"), milliseconds=True) or timestamp
        created = _timestamp(raw.get("createdAt")) or start or updated
        legacy_status = _text(raw.get("status"), 32)
        derived = derive_run_status(raw)
        run_status = {"running_pending_reconciliation": "unknown", "succeeded_with_incomplete_timing": "succeeded"}.get(derived, derived)
        snapshot, cost, flags = _record_snapshots(raw, state)
        if derived == "running_pending_reconciliation":
            flags.append("pending_device_reconciliation")
        if derived == "succeeded_with_incomplete_timing":
            flags.append("incomplete_timing")
        matches = [row for row in state["products"] if row.get("name") == raw.get("productName") and raw.get("productName")]
        product_id = _resolve(db, "products", str(matches[0]["id"])) if len(matches) == 1 else ""
        if not product_id:
            flags.append("unmatched_product" if not matches else "ambiguous_product")
        base.update(business_date=_date(raw["business_date"]), machine_no=_decimal(raw.get("machine"), integer=True),
                    status=legacy_status, legacy_status=legacy_status, product_id=product_id, product_name=_text(raw.get("productName")),
                    material_name=_text(raw.get("material")), weight_g=_decimal(raw.get("weight")), quantity=_decimal(raw.get("qty"), integer=True),
                    duration_hours=_decimal(raw.get("time")), design_fee=_decimal(raw.get("designFee")), quoted_price=_decimal(raw.get("price")),
                    customer=_text(raw.get("customer")), remark=_text(raw.get("remark"), 65536), auto_record=raw.get("autoRecord", False),
                    print_start_at=start, print_end_at=end, gcode_file=_text(raw.get("_gcodeFile"), 512), inventory_consumed=False,
                    legacy_updated_at=updated, deleted_at=updated if raw.get("_deleted") else "", created_at=created, updated_at=updated,
                    site_id=SITE, source_system=SOURCE, migration_batch_id=batch.id, run_status=run_status,
                    reconciliation_status="pending" if derived == "running_pending_reconciliation" else "none",
                    data_quality_flags_json=_json(sorted(set(flags))), product_snapshot_json=_json(snapshot), cost_profile_version="legacy-v1",
                    calculated_cost_snapshot_json=_json(cost), created_by="legacy-migration", created_by_name="旧系统迁移")
        if not 1 <= base["machine_no"] <= int(state["settings"]["machines"]):
            raise MigrationError("unknown_machine_number")
    elif entity == "inventory":
        base.update(material_name=_text(raw["material"]), stock_g=_decimal(raw.get("stockG"), allow_negative=True), min_stock_g=_decimal(raw.get("minStockG")))
    elif entity == "stock_in_logs":
        name = _text(raw.get("material"))
        inventory_id = _resolve(db, "inventory", name)
        inventory = db.get(models.ThreeDPrintingInventory, inventory_id)
        base.update(inventory_id=inventory_id, material_name=name, movement_type="legacy_history_only", delta_g=_decimal(raw.get("amountG")),
                    balance_after_g=inventory.stock_g, business_date=_date(raw.get("date")), vendor=_text(raw.get("vendor")), cost=_decimal(raw.get("cost")),
                    remark=_text(raw.get("remark"), 65536), actor_id="legacy-migration", actor_name="旧系统迁移", affects_balance=False,
                    raw_material_name=name, migration_batch_id=batch.id, idempotency_key=_id("stock_in_logs", item.legacy), movement_status="posted")
    elif entity in {"schedules", "maintenance"}:
        base.update(business_date=_date(raw.get("date")), machine_no=_decimal(raw.get("machine"), integer=True), remark=_text(raw.get("remark"), 65536),
                    created_by="legacy-migration", created_by_name="旧系统迁移")
        if entity == "schedules":
            base.update(product_name=_text(raw.get("productName")), customer=_text(raw.get("customer")), material_name=_text(raw.get("material")),
                        weight_g=_decimal(raw.get("weight")), quantity=_decimal(raw.get("qty"), integer=True), priority=_text(raw.get("priority") or "normal", 16),
                        status=_text(raw.get("status") or "pending", 24))
        else:
            base.update(maintenance_type=_text(raw.get("type"), 64), description=_text(raw.get("description"), 65536),
                        cost=_decimal(raw.get("cost")), vendor=_text(raw.get("vendor")))
    elif entity == "images":
        if raw.get("valid") is not True:
            raise MigrationError("invalid_source_image")
        product_id = _resolve(db, "products", item.legacy)
        suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[raw["mime_type"]]
        base.update(product_id=product_id, storage_key=f"{FACTORY}/{product_id}/{raw['content_sha256']}{suffix}", sha256=raw["content_sha256"], legacy_sha256=raw["legacy_sha256"],
                    mime_type=raw["mime_type"], size_bytes=raw["size_bytes"], width=raw["width"], height=raw["height"],
                    original_file_name=f"legacy{suffix}", uploaded_by="legacy-migration", uploaded_by_name="旧系统迁移", is_current=True)
    return base


def _asset_path(root: Path, key: str) -> Path:
    path = (root / key).resolve()
    if root not in path.parents or path.is_symlink():
        raise MigrationError("unsafe_asset_path")
    return path


def _asset_valid(root: Path, row) -> bool:
    path = _asset_path(root, row.storage_key)
    return path.is_file() and file_fingerprint(path) == {"sha256": row.sha256, "size_bytes": row.size_bytes}


def _write_asset(source_db, root: Path, item: Item, payload: dict) -> None:
    value = source_db.execute("SELECT image_data FROM product_images WHERE product_id=?", (item.legacy,)).fetchone()
    if not value or not isinstance(value[0], bytes) or sha256(value[0]).hexdigest() != item.raw["content_sha256"]:
        raise MigrationError("source_image_hash_mismatch")
    path = _asset_path(root, payload["storage_key"])
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if file_fingerprint(path) != {"sha256": payload["sha256"], "size_bytes": payload["size_bytes"]}:
                raise MigrationError("asset_content_conflict")
            return
        temporary = path.parent / ("." + uuid4().hex + ".tmp")
        try:
            with temporary.open("xb") as stream:
                stream.write(value[0])
                stream.flush()
                os.fsync(stream.fileno())
            # Migration lease serializes writers; no image re-encoding occurs.
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
    except OSError:
        raise MigrationError("asset_write_failed") from None


def _inventory_movement(db, row, previous_balance: Decimal, batch, timestamp: str, *, opening: bool) -> None:
    delta = Decimal(row.stock_g) - previous_balance
    identity = _id("opening" if opening else "inventory-adjustment", row.id if opening else batch.id + ":" + row.id)
    existing = db.get(models.ThreeDPrintingInventoryMovement, identity)
    if existing:
        raise MigrationError("inventory_movement_already_exists")
    db.add(models.ThreeDPrintingInventoryMovement(
        id=identity, factory_id=FACTORY, inventory_id=row.id, material_name=row.material_name,
        movement_type="migration_opening" if opening else "migration_adjustment", delta_g=delta, balance_after_g=row.stock_g,
        business_date=timestamp[:10], vendor="", cost=0, remark="", legacy_id=None,
        actor_id="legacy-migration", actor_name="旧系统迁移", created_at=timestamp,
        idempotency_key=identity, movement_status="posted", migration_batch_id=batch.id,
        raw_material_name=row.material_name, affects_balance=True,
    ))


def _import_item(db, item: Item, state: dict, batch, source_db, asset_root: Path, timestamp: str) -> tuple[str, str, str]:
    if item.error:
        raise MigrationError(item.error)
    model = _model(item.entity)
    previous = _owned(db, item)
    matches = db.scalars(_natural_query(item).with_for_update()).all()
    if len(matches) > 1:
        raise MigrationError("ambiguous_target_identity")
    row = matches[0] if matches else None
    if item.entity == "printers" and row is not None:
        # Bind history to the existing machine without changing its ID, mode or state.
        return "skipped", row.id, _target_hash(row)
    if previous:
        row = _get_target(db, model, previous.target_id)
        if row is None:
            raise MigrationError("owned_target_missing")
        if _target_hash(row) != previous.target_hash:
            raise MigrationError("target_edited_in_nexus")
        if previous.source_hash == item.source_hash:
            if item.entity == "images" and not _asset_valid(asset_root, row):
                payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
                _write_asset(source_db, asset_root, item, payload)
            return "skipped", previous.target_id, previous.target_hash
    elif row is not None and not _seed_can_be_adopted(db, item, row):
        raise MigrationError("target_has_no_migration_ownership")
    payload = _payload(db, item, state, batch, timestamp)
    created = row is None
    if not created and item.entity == "stock_in_logs":
        raise MigrationError("immutable_history_changed")
    if not created and item.entity == "records" and payload["legacy_updated_at"] < row.legacy_updated_at:
        raise MigrationError("stale_source_row")
    if not created and item.entity == "records":
        _preserve_cost_profile(row, payload, item, state)
    old_balance = Decimal(0) if created or item.entity != "inventory" else row.stock_g
    if row is None:
        row = model(**payload)
        db.add(row)
    else:
        payload.pop("id", None)
        payload.pop("created_at", None)
        if "revision" in payload:
            payload["revision"] = row.revision + 1
        for key, value in payload.items():
            setattr(row, key, value)
    if item.entity == "images":
        _write_asset(source_db, asset_root, item, payload)
    db.flush()
    if item.entity == "inventory" and (created or row.stock_g != old_balance):
        _inventory_movement(db, row, old_balance, batch, timestamp, opening=created)
        db.flush()
    # Re-read DB-normalized Numeric values before calculating durable ownership.
    db.refresh(row)
    return "imported" if created else "updated", row.factory_id if item.entity == "settings" else row.id, _target_hash(row)


def _lock_scope(db):
    if db.get_bind().dialect.name == "sqlite":
        db.connection().exec_driver_sql("BEGIN IMMEDIATE")
    site = db.scalar(select(models.ThreeDPrintingSite).where(models.ThreeDPrintingSite.id == SITE).with_for_update())
    if site is None or site.factory_id != FACTORY or site.site_code != "heyuan":
        raise MigrationError("migration_site_not_ready")


def _schema_ready(db):
    inspector = inspect(db.get_bind())
    required = (models.ThreeDPrintingMigrationBatch, models.ThreeDPrintingMigrationRowResult, models.ThreeDPrintingSite,
                *[_model(entity) for entity in MODEL_NAMES])
    for model in required:
        if not inspector.has_table(model.__tablename__):
            raise MigrationError("migration_schema_not_ready")
        actual = {column["name"] for column in inspector.get_columns(model.__tablename__)}
        if not {column.name for column in model.__table__.columns}.issubset(actual):
            raise MigrationError("migration_schema_not_ready")


def _expected(analysis: dict) -> dict:
    c = analysis["authoritative_sqlite"]
    return {"settings": 1, "materials": c["materials"], "products": c["products"], "product_images": c["product_images"],
            "business_date_keys": c["record_dates"], "production_records": c["records_stored"], "active_records": c["records_active"],
            "soft_deleted_records": c["records_tombstoned"], "inventory_items": c["inventory_items"], "stock_in_logs": c["stock_in_logs"],
            "schedules": c["schedules"], "maintenance": c["maintenance"], "configured_printers": int(c["settings"]["machines"]),
            "image_total_bytes": analysis["images_quality"]["total_bytes"],
            "inventory_total_g": analysis["materials_inventory_quality"]["inventory_total_g"]}


def _register(session_factory, manifest, checks, expected, *, batch_id, mode, resume, revision, lease):
    Batch = models.ThreeDPrintingMigrationBatch
    with session_factory() as db:
        _schema_ready(db)
        _lock_scope(db)
        scope = select(Batch).where(Batch.factory_id == FACTORY, Batch.site_id == SITE, Batch.source_system == SOURCE)
        batches = db.scalars(scope).all()
        now = _now()
        if any(b.lease_id and b.leased_until > now for b in batches):
            raise MigrationError("migration_lease_active")
        snapshot_sha = manifest["snapshot"]["sha256"]
        current = next((b for b in batches if b.source_sha256 == snapshot_sha), None)
        if batch_id and (current is None or current.id != batch_id):
            raise MigrationError("migration_batch_source_mismatch")
        if any(b.source_updated_at_ms > checks["state_updated_at_ms"] for b in batches):
            raise MigrationError("stale_source_snapshot")
        if current is None and any(b.source_updated_at_ms == checks["state_updated_at_ms"] for b in batches):
            raise MigrationError("source_timestamp_conflict")
        if current is None and mode == "reconcile":
            raise MigrationError("migration_batch_not_found")
        if current and current.status not in {"reconciled", "analyzed", "dry_run"} and mode == "import" and not resume:
            raise MigrationError("migration_resume_required")
        already = current is not None and current.status == "reconciled"
        if current is None:
            current = Batch(id="3dbatch-" + uuid4().hex, factory_id=FACTORY, site_id=SITE, source_system=SOURCE,
                            source_sha256=snapshot_sha, source_updated_at_ms=checks["state_updated_at_ms"],
                            source_size_bytes=manifest["snapshot"]["size_bytes"], image_count=expected["product_images"],
                            image_bytes=expected["image_total_bytes"], migration_version=VERSION, code_revision=revision,
                            status="importing", expected_counts_json=_json(expected), started_at=now)
            db.add(current)
        if current.migration_version != VERSION:
            raise MigrationError("migration_version_mismatch")
        current.lease_id = lease
        current.leased_until = (datetime.now(UTC) + timedelta(minutes=5)).isoformat(timespec="milliseconds")
        current.error_code = ""
        if mode == "import" and not already:
            current.status = "importing"
        db.commit()
        return current.id, already


def _guard(db, batch_id, lease):
    _lock_scope(db)
    batch = db.get(models.ThreeDPrintingMigrationBatch, batch_id)
    if batch is None or batch.lease_id != lease or batch.leased_until <= _now():
        raise MigrationError("migration_lease_lost")
    batch.leased_until = (datetime.now(UTC) + timedelta(minutes=5)).isoformat(timespec="milliseconds")
    return batch


def _checkpoint(db, batch, item, status, target_id="", target_hash="", error=""):
    Row = models.ThreeDPrintingMigrationRowResult
    row = db.scalar(select(Row).where(Row.batch_id == batch.id, Row.entity_type == item.entity, Row.legacy_id == item.legacy))
    if row is None:
        row = Row(id="3drow-" + uuid4().hex, factory_id=FACTORY, batch_id=batch.id, entity_type=item.entity, legacy_id=item.legacy,
                  status=status, source_hash=item.source_hash, attempt_count=0, updated_at=_now())
        db.add(row)
    row.status, row.error_code, row.updated_at = status, error, _now()
    # A failed retry is an attempt result, not revocation of a committed write.
    # source_hash always describes the last applied source when target_hash is
    # present. New-batch failures without a committed write have empty targets.
    if status in SUCCESS:
        row.target_id, row.target_hash, row.source_hash = target_id, target_hash, item.source_hash
    elif not row.target_hash:
        row.source_hash = item.source_hash
    row.attempt_count += 1
    db.flush()


def _reconcile(db, batch, items, state, analysis, root):
    Row = models.ThreeDPrintingMigrationRowResult
    row_results = {(r.entity_type, r.legacy_id): r for r in db.scalars(select(Row).where(Row.batch_id == batch.id))}
    expected = _expected(analysis)
    actual = {key: 0 for key in expected}
    issues, actual_rows = [], defaultdict(list)
    domain_counts = {"settings": "settings", "materials": "materials", "products": "products", "images": "product_images",
                     "days": "business_date_keys", "records": "production_records", "inventory": "inventory_items",
                     "stock_in_logs": "stock_in_logs", "schedules": "schedules", "maintenance": "maintenance", "printers": "configured_printers"}
    for item in items:
        checkpoint = row_results.get((item.entity, item.legacy))
        error = ""
        row = _get_target(db, _model(item.entity), checkpoint.target_id) if checkpoint and checkpoint.target_id else None
        if checkpoint is None or checkpoint.status not in SUCCESS:
            error = checkpoint.error_code if checkpoint and checkpoint.error_code else "row_not_imported"
        elif row is None or row.factory_id != FACTORY:
            error = "reconciliation_target_missing"
        elif checkpoint.source_hash != item.source_hash or (
            item.entity != "printers" and checkpoint.target_hash != _target_hash(row)
        ):
            error = "reconciliation_target_mismatch"
        if row is not None:
            actual_rows[item.entity].append(row)
            if item.entity in domain_counts:
                actual[domain_counts[item.entity]] += 1
        if not error and row is not None:
            origin = db.get(models.ThreeDPrintingMigrationBatch, row.migration_batch_id) if item.entity == "records" and row.migration_batch_id else batch
            source_timestamp = datetime.fromtimestamp(origin.source_updated_at_ms / 1000, UTC).isoformat()
            desired = _payload(db, item, state, batch, source_timestamp)
            # Generated timestamps/revisions, historical rate captures and prior
            # batch lineage intentionally remain frozen across newer snapshots.
            generated = {"id", "created_at", "updated_at", "revision", "migration_batch_id", "balance_after_g",
                         "calculated_cost_snapshot_json"}
            if item.entity == "printers":
                generated |= set(desired) - {"factory_id", "machine_no"}
            if item.entity == "records":
                # These capture the mapping/quality context at first migration;
                # product renames or newly available prices cannot rewrite it.
                generated |= {"product_id", "data_quality_flags_json"}
            if any(getattr(row, key) != value for key, value in desired.items() if key not in generated):
                error = "reconciliation_business_field_mismatch"
            if item.entity == "images" and not _asset_valid(root, row):
                error = "reconciliation_asset_mismatch"
            elif item.entity == "records":
                raw = item.raw
                # Verify business columns independently of stored checkpoint hashes.
                pairs = {"product_name": _text(raw.get("productName")), "material_name": _text(raw.get("material")),
                         "customer": _text(raw.get("customer")), "quantity": _decimal(raw.get("qty"), integer=True),
                         "weight_g": _decimal(raw.get("weight")), "quoted_price": _decimal(raw.get("price")),
                         "design_fee": _decimal(raw.get("designFee")), "duration_hours": _decimal(raw.get("time")),
                         "business_date": raw["business_date"], "legacy_status": _text(raw.get("status")),
                         "print_start_at": _timestamp(raw.get("printStartTime")), "print_end_at": _timestamp(raw.get("printEndTime"))}
                if any(getattr(row, key) != value for key, value in pairs.items()) or bool(row.deleted_at) != bool(raw.get("_deleted")):
                    error = "reconciliation_business_field_mismatch"
                derived = derive_run_status(raw)
                expected_status = {"running_pending_reconciliation": "unknown", "succeeded_with_incomplete_timing": "succeeded"}.get(derived, derived)
                if row.run_status != expected_status or (row.reconciliation_status == "pending") != (derived == "running_pending_reconciliation"):
                    error = "reconciliation_run_status_mismatch"
                if row.source_system != SOURCE or row.site_id != SITE or row.cost_profile_version != "legacy-v1":
                    error = "reconciliation_provenance_mismatch"
            elif item.entity == "inventory":
                if row.material_name != item.legacy or row.stock_g != _decimal(item.raw.get("stockG"), allow_negative=True) or row.min_stock_g != _decimal(item.raw.get("minStockG")):
                    error = "reconciliation_inventory_mismatch"
                movements = db.scalars(select(models.ThreeDPrintingInventoryMovement).where(
                    models.ThreeDPrintingInventoryMovement.inventory_id == row.id,
                    models.ThreeDPrintingInventoryMovement.affects_balance.is_(True))).all()
                if sum((m.delta_g for m in movements), Decimal(0)) != row.stock_g:
                    error = "reconciliation_inventory_ledger_mismatch"
            elif item.entity == "stock_in_logs" and (
                row.affects_balance or row.movement_type != "legacy_history_only"
                or row.delta_g != _decimal(item.raw.get("amountG")) or row.cost != _decimal(item.raw.get("cost"))
            ):
                error = "reconciliation_history_mismatch"
        if error:
            issues.append({"code": error, "entity_type": item.entity, "legacy_id": item.legacy})
    records = actual_rows["records"]
    active = [row for row in records if not row.deleted_at]
    actual["active_records"], actual["soft_deleted_records"] = len(active), len(records) - len(active)
    actual["image_total_bytes"] = sum(row.size_bytes for row in actual_rows["images"])
    actual["inventory_total_g"] = float(sum((row.stock_g for row in actual_rows["inventory"]), Decimal(0)))
    totals = {"quantity_total": float(sum((row.quantity for row in active), 0)),
              "planned_material_g_total": float(sum((row.weight_g * row.quantity for row in active), Decimal(0))),
              "design_fee_total": float(sum((row.design_fee for row in active), Decimal(0))),
              "quoted_revenue_total": float(sum((row.quoted_price * row.quantity for row in active), Decimal(0)))}
    if actual != expected:
        issues.append({"code": "reconciliation_counts_mismatch"})
    if totals != analysis["business_totals_active_records"]:
        issues.append({"code": "reconciliation_totals_mismatch"})
    # Historical rows absent from a newer source are not silently deleted.
    scope = db.scalars(select(models.ThreeDPrintingMigrationRowResult).join(models.ThreeDPrintingMigrationBatch).where(
        models.ThreeDPrintingMigrationBatch.factory_id == FACTORY, models.ThreeDPrintingMigrationBatch.site_id == SITE,
        models.ThreeDPrintingMigrationBatch.source_system == SOURCE,
        models.ThreeDPrintingMigrationRowResult.target_id != "",
        models.ThreeDPrintingMigrationRowResult.target_hash != "",
        models.ThreeDPrintingMigrationRowResult.source_hash != "")).all()
    current_keys = {(item.entity, item.legacy) for item in items}
    for key in sorted({(row.entity_type, row.legacy_id) for row in scope} - current_keys):
        issues.append({"code": "source_missing_previously_imported_row", "entity_type": key[0], "legacy_id": key[1]})
    return {"passed": not issues, "expected": expected, "actual": actual, "issues": issues,
            "business_totals": {"expected": analysis["business_totals_active_records"], "actual": totals}}


def run_migration(snapshot_path, manifest, *, session_factory, asset_dir, mode="import", migration_batch=None,
                  chunk_size=200, resume=False, code_revision="") -> dict:
    """Import or reconcile an exact standalone snapshot against an explicit DB.

    Same-snapshot replay always rechecks actual rows and asset bytes. Failed rows
    retry with ``resume=True``; successful rows retain their ownership checkpoint.
    Newer snapshots update only targets whose full persisted hash still matches.
    """
    if mode not in {"import", "reconcile"} or not isinstance(chunk_size, int) or not 1 <= chunk_size <= 500:
        raise MigrationError("invalid_migration_options")
    source, root = Path(snapshot_path).resolve(), Path(asset_dir).resolve()
    if source == root or root in source.parents or source in root.parents:
        raise MigrationError("asset_source_overlap")
    if not source.is_file() or Path(snapshot_path).is_symlink() or any(Path(str(source) + suffix).exists() for suffix in ("-wal", "-shm")):
        raise MigrationError("standalone_snapshot_required")
    if manifest.get("factory_id") != FACTORY or manifest.get("site_code") != "heyuan":
        raise MigrationError("migration_scope_mismatch")
    revision = _text(code_revision, 64)
    if revision and not re.fullmatch(r"[0-9a-fA-F]{7,64}", revision):
        raise MigrationError("invalid_code_revision")
    batch_id, lease = None, uuid4().hex
    with tempfile.TemporaryDirectory(prefix="three-d-import-") as directory:
        pinned = Path(directory) / "snapshot.sqlite"
        shutil.copyfile(source, pinned)
        fingerprint = file_fingerprint(pinned)
        if any(manifest.get("snapshot", {}).get(key) != value for key, value in fingerprint.items()):
            raise MigrationError("snapshot_manifest_mismatch")
        state, images, checks = inspect_snapshot(pinned)
        if manifest.get("checks", {}).get("state_updated_at_ms") != checks["state_updated_at_ms"]:
            raise MigrationError("snapshot_timestamp_mismatch")
        analysis = analyze_state(state, images)
        expected = _expected(analysis)
        items = _items(state, images)
        try:
            batch_id, already = _register(session_factory, manifest, checks, expected, batch_id=migration_batch,
                                         mode=mode, resume=resume, revision=revision, lease=lease)
        except SQLAlchemyError:
            raise MigrationError("migration_database_unavailable") from None
        try:
            with closing(connect_readonly(pinned)) as source_db:
                if mode == "import" and not already:
                    for offset in range(0, len(items), chunk_size):
                        with session_factory() as db:
                            batch = _guard(db, batch_id, lease)
                            for item in items[offset:offset + chunk_size]:
                                try:
                                    with db.begin_nested():
                                        status, target_id, target_hash = _import_item(db, item, state, batch, source_db, root, checks["state_updated_at_utc"])
                                    _checkpoint(db, batch, item, status, target_id, target_hash)
                                except MigrationError as exc:
                                    conflicts = {"target_edited_in_nexus", "target_has_no_migration_ownership", "ambiguous_target_identity", "owned_target_missing", "immutable_history_changed", "stale_source_row", "asset_content_conflict"}
                                    _checkpoint(db, batch, item, "conflict" if exc.code in conflicts else "failed", error=exc.code)
                                except IntegrityError:
                                    _checkpoint(db, batch, item, "failed", error="target_constraint_violation")
                            batch.checkpoint_json = _json({"completed_rows": min(offset + chunk_size, len(items)), "total_rows": len(items)})
                            db.commit()
                with session_factory() as db:
                    batch = _guard(db, batch_id, lease)
                    reconciliation = _reconcile(db, batch, items, state, analysis, root)
                    statuses = Counter(db.scalars(select(models.ThreeDPrintingMigrationRowResult.status).where(models.ThreeDPrintingMigrationRowResult.batch_id == batch_id)))
                    status = "already_reconciled" if reconciliation["passed"] and already and mode == "import" else "reconciled" if reconciliation["passed"] else "failed"
                    report = {"status": status, "batch_id": batch_id, "source_sha256": fingerprint["sha256"], "counts": reconciliation["actual"],
                              "row_status_counts": dict(statuses), "error_codes": sorted({issue["code"] for issue in reconciliation["issues"]}),
                              "reconciliation": reconciliation}
                    assert_no_secrets(report)
                    batch.status = "reconciled" if reconciliation["passed"] else "failed"
                    batch.summary_json = _json({key: value for key, value in report.items() if key != "reconciliation"})
                    batch.reconciliation_json, batch.completed_at = _json(reconciliation), _now()
                    batch.lease_id, batch.leased_until = "", ""
                    batch.error_code = "" if reconciliation["passed"] else "migration_reconciliation_failed"
                    db.add(models.ThreeDPrintingAuditEvent(id="3daudit-" + uuid4().hex, factory_id=FACTORY, entity_type="migration_batch", entity_id=batch.id,
                           action="migration_reconciled" if reconciliation["passed"] else "migration_failed", detail_json=_json({"batch_id": batch.id, "counts": report["counts"]}),
                           actor_id="legacy-migration", actor_name="旧系统迁移", actor_type="system", created_at=_now()))
                    db.commit()
                    return report
        except Exception as exc:  # noqa: BLE001 - redact every driver/runtime exception at the CLI boundary.
            code = exc.code if isinstance(exc, (MigrationError, SnapshotError)) else "migration_execution_failed"
            try:
                with session_factory() as db:
                    batch = db.get(models.ThreeDPrintingMigrationBatch, batch_id)
                    if batch is not None and batch.lease_id == lease:
                        batch.status, batch.error_code, batch.completed_at = "failed", code, _now()
                        batch.lease_id, batch.leased_until = "", ""
                        db.commit()
            except SQLAlchemyError:
                pass
            raise MigrationError(code, batch_id=batch_id) from None
