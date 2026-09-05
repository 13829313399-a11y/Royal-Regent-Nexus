"""Transactional write boundary and frozen production costing for the 3D domain."""

import json
from decimal import Decimal
from functools import wraps
from hashlib import sha256
from inspect import signature

from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.exc import OperationalError

from app.core.time import business_now
from app.models import three_d_printing as models


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def atomic_write(function):
    """Serialize domain writes on the existing factory settings row, on SQLite/PG.

    A deterministic audit primary key binds a retry key to actor + full input.
    The operation, all ledger rows, and this receipt commit together.
    Inner functions must not commit. Permission checks stay in the HTTP layer.
    """
    sig = signature(function)

    @wraps(function)
    def wrapped(*args, **kwargs):
        values = sig.bind(*args, **kwargs).arguments
        db = values["db"]
        payload = values.get("payload")
        factory = payload.factory_id if payload else values["factory_id"]
        if factory != "huakang-a":
            raise HTTPException(403, "3D 打印仅支持华康A")
        user = values.get("user")
        key = getattr(payload, "idempotency_key", "") or values.get(
            "idempotency_key", ""
        )
        body = {
            k: (v.model_dump() if hasattr(v, "model_dump") else v)
            for k, v in values.items()
            if k not in ("db", "user", "request_id")
        }
        digest = sha256(
            encode([function.__name__, getattr(user, "id", ""), body]).encode()
        ).hexdigest()
        receipt_id = (
            "3dop-" + sha256((factory + ":" + key).encode()).hexdigest()
            if key
            else None
        )
        try:
            locked = db.execute(
                update(models.ThreeDPrintingSetting)
                .where(models.ThreeDPrintingSetting.factory_id == factory)
                .values(revision=models.ThreeDPrintingSetting.revision)
                .execution_options(synchronize_session=False)
            )
            if locked.rowcount != 1:
                raise HTTPException(409, "请先初始化3D工厂设置")
            # Permission queries may already have populated the session identity map.
            db.expire_all()
            receipt = (
                db.get(models.ThreeDPrintingAuditEvent, receipt_id)
                if receipt_id
                else None
            )
            if receipt:
                saved = json.loads(receipt.detail_json)
                if saved["digest"] != digest:
                    raise HTTPException(409, "幂等键已用于不同操作，请刷新后重试")
                result = (
                    db.get(getattr(models, saved["model"]), saved["id"])
                    if saved["model"]
                    else None
                )
                db.commit()
                return result
            result = function(*args, **kwargs)
            if receipt_id:
                db.add(
                    models.ThreeDPrintingAuditEvent(
                        id=receipt_id,
                        factory_id=factory,
                        entity_type="write_receipt",
                        entity_id=getattr(result, "id", "") or factory,
                        action=function.__name__,
                        detail_json=encode(
                            {
                                "digest": digest,
                                "model": type(result).__name__
                                if result is not None
                                else "",
                                "id": getattr(result, "id", factory),
                            }
                        ),
                        actor_id=getattr(user, "id", ""),
                        actor_name=getattr(user, "display_name", ""),
                        actor_type="user",
                        request_id=values.get("request_id", "")[:128],
                        created_at=business_now().isoformat(),
                    )
                )
            db.commit()
            if result is not None and not isinstance(result, list):
                db.refresh(result)
            return result
        except OperationalError as exc:
            db.rollback()
            if any(
                word in str(exc).lower()
                for word in ("locked", "deadlock", "serialization")
            ):
                raise HTTPException(409, "库存正在更新，请使用相同请求重试") from exc
            raise
        except Exception:
            db.rollback()
            raise

    return wrapped


def record_inputs(record):
    return {
        "productName": record.product_name,
        "material": record.material_name,
        "weight": str(record.weight_g),
        "time": str(record.duration_hours),
        "qty": record.quantity,
        "price": str(record.quoted_price),
        "customer": record.customer,
        "designFee": str(record.design_fee),
    }


def freeze_cost(record, setting, material, *, reason="", initial=False):
    inputs = record_inputs(record)
    previous = json.loads(record.calculated_cost_snapshot_json or "{}")
    if not initial and not previous:
        # Missing historical rates cannot be reconstructed from today's settings.
        flags = set(json.loads(record.data_quality_flags_json or "[]"))
        flags.add("cost_snapshot_requires_review")
        record.data_quality_flags_json = encode(sorted(flags))
        return
    if previous:
        rates = previous["settings"]
        price = previous.get("material_price_kg")
        if inputs["material"] != previous["inputs"].get("material"):
            price = None  # A material correction has no proven historical unit price.
    else:
        rates = {
            "machines": setting.machine_count,
            "elecPerMachine": str(setting.electricity_per_machine_day),
            "laborPerDay": str(setting.labor_per_day),
            "lossRate": str(setting.material_loss_rate),
            "profitRate": str(setting.profit_rate_percent),
        }
        price = str(material.price_per_kg) if material else None
        record.cost_profile_version = (
            "nexus-v1-" + sha256(encode([rates, price]).encode()).hexdigest()[:16]
        )
    cost = {
        "formula_version": previous.get("formula_version", "nexus-v1"),
        "basis": previous.get("basis", "captured_at_record_creation"),
        "settings": rates,
        "material_price_kg": price,
        "inputs": inputs,
        "correction_reason": reason,
        "manual_override": {"quoted_price": str(record.quoted_price), "reason": reason},
        "material_cost_per_unit": None,
        "electricity_per_unit": None,
        "labor_per_unit": None,
        "suggested_price_per_unit": None,
        "quoted_total": Decimal(str(record.quoted_price)) * record.quantity
        + Decimal(str(record.design_fee)),
    }
    if (
        price is not None
        and all(v is not None for v in rates.values())
        and Decimal(str(rates["machines"])) > 0
    ):
        weight, hours = (
            Decimal(str(record.weight_g)),
            Decimal(str(record.duration_hours)),
        )
        mat = weight * Decimal(str(rates["lossRate"])) * Decimal(str(price)) / 1000
        elec = hours / 12 * Decimal(str(rates["elecPerMachine"]))
        labor = (
            hours
            / 12
            * Decimal(str(rates["laborPerDay"]))
            / Decimal(str(rates["machines"]))
        )
        cost.update(
            material_cost_per_unit=mat,
            electricity_per_unit=elec,
            labor_per_unit=labor,
            suggested_price_per_unit=(mat + elec + labor)
            * (1 + Decimal(str(rates["profitRate"])) / 100),
        )
    flags = set(json.loads(record.data_quality_flags_json or "[]"))
    if cost["suggested_price_per_unit"] is None:
        flags.add("cost_snapshot_requires_review")
    else:
        flags.discard("cost_snapshot_requires_review")
    record.data_quality_flags_json = encode(sorted(flags))
    record.calculated_cost_snapshot_json = encode(cost)
    record.product_snapshot_json = encode(inputs)


def frozen_totals(record):
    """Only frozen inputs/rates; absent evidence stays null, never current pricing."""
    cost = json.loads(record.calculated_cost_snapshot_json or "{}")
    inputs = cost.get("inputs", {})
    quantity = inputs.get("qty")

    def total(key):
        value = cost.get(key)
        return (
            float(Decimal(str(value)) * Decimal(str(quantity)))
            if value is not None and quantity is not None
            else None
        )

    suggested = total("suggested_price_per_unit")
    design = inputs.get("designFee")
    return {
        "materialCost": total("material_cost_per_unit"),
        "electricityCost": total("electricity_per_unit"),
        "laborCost": total("labor_per_unit"),
        "revenue": suggested + float(design or 0)
        if suggested is not None
        else float(cost["quoted_total"])
        if cost.get("quoted_total") is not None
        else None,
    }
