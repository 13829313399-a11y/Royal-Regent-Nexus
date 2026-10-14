"""Versioned Dickie classification/defaults, scoped and fail-closed on conflicts."""
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from uuid import uuid4
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import inspect, select
from app.models.customer_order_products import OrderProductCatalog as Catalog, OrderProductChange as Change, OrderProductExportEvidence as Evidence
from app.services.transaction_lock import lock_transaction
from app.schemas.customer_order_products import ProductChoice

FACTORY, CUSTOMER = "huaxing", "dickie"
TABLES = {m.__tablename__ for m in (Catalog, Change, Evidence)}
MAX_PRODUCTS = 2000


def key(product):
    return re.sub(r"[^A-Z0-9]", "", str(product).upper())


def checksum(value):
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def ready(db):
    # Use the owned connection: another pooled connection can roll back a
    # StaticPool SQLite transaction, and cannot inspect this transaction's DDL.
    return TABLES.issubset(inspect(db.connection()).get_table_names())


def snapshot(db):
    if not ready(db):
        return {"available": False, "revision": 0, "sha256": "", "products": {}}
    row = db.get(Catalog, (FACTORY, CUSTOMER))
    products = deepcopy(row.products) if row else {}
    return {"available": True, "revision": row.revision if row else 0,
            "sha256": checksum(products), "products": products}


def choices(raw):
    if len(raw) > 500000:
        raise HTTPException(400, "产品补录内容过大")
    try:
        values = TypeAdapter(list[ProductChoice]).validate_json(raw)
    except ValidationError as exc:
        raise HTTPException(400, "产品补录格式、分类、装箱数或核对原因无效") from exc
    if len(values) > 500 or len({key(v.product_no) for v in values}) != len(values):
        raise HTTPException(400, "单批最多补录500个货号，不能重复")
    return [v.model_dump() for v in values]


def save(db, body, actor):
    if not ready(db):
        raise HTTPException(503, "新货号维护尚未执行迁移 20261014_0161")
    lock_transaction(db, "order-product-catalog", FACTORY + ":" + CUSTOMER)
    current = db.get(Catalog, (FACTORY, CUSTOMER))
    revision = current.revision if current else 0
    if revision != body.expected_revision:
        raise HTTPException(409, "货号规则已被更新，请刷新并重新核对，不会覆盖别人的修改")
    product_key = key(body.product_no)
    products = deepcopy(current.products) if current else {}
    before = products.get(product_key)
    value = body.model_dump(exclude={"expected_revision", "reason"})
    if before and {k: before.get(k) for k in value} == value:
        return snapshot(db)
    if product_key not in products and len(products) >= MAX_PRODUCTS:
        raise HTTPException(400, "已达到2000个货号，请先整理现有规则")
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    value.update(rule_revision=revision + 1, actor=actor, updated_at=now)
    products[product_key] = value
    if current:
        current.products, current.revision = products, revision + 1
    else:
        db.add(Catalog(factory_id=FACTORY, customer_code=CUSTOMER, revision=1, products=products))
    db.add(Change(id=uuid4().hex, factory_id=FACTORY, customer_code=CUSTOMER, revision=revision + 1,
        product_key=product_key, actor=actor, created_at=now,
        data={"before": before, "after": value, "reason": body.reason}))
    db.flush()
    return snapshot(db)


def ensure_current(db, registration):
    if registration is None:
        return
    lock_transaction(db, "order-product-catalog", FACTORY + ":" + CUSTOMER)
    current = snapshot(db)
    if any(current.get(k) != registration.get(k) for k in ("available", "revision", "sha256")):
        raise HTTPException(409, "货号规则在核对期间发生变化，请重新预览；不会使用旧规则保存或导出")


def apply(preview, registry, selected, history, sheets):
    """Only called for the explicitly scoped unified Dickie writer."""
    from app.services import customer_order_unified as unified
    registry = registry or {"available": False, "revision": 0, "sha256": "", "products": {}}
    if selected and not registry["available"]:
        raise ValueError("新货号维护尚未执行迁移 20261014_0161，请联系管理员")
    known = {key(r.get("product_no")) for r in preview["rows"]}
    selection = {key(v["product_no"]): v for v in selected}
    if len(selection) != len(selected) or any(k not in known for k in selection):
        raise ValueError("产品补录重复或不属于当前PO货号，请重新核对")
    registration = {k: registry[k] for k in ("available", "revision", "sha256")}
    registration.update(sheets=sheets, choices=selected, applied=[], conflicts=[])
    for row in preview["rows"]:
        product_key = key(row.get("product_no"))
        rule = selection.get(product_key)
        origin = "本次人工核对"
        if rule is None:
            candidate = registry["products"].get(product_key)
            rule = candidate if candidate and candidate.get("active") else None
            origin = "已保存货号规则"
        if not rule:
            continue
        target = rule["item_sheet_name"]
        lanes = {h.source_sheet for h in history if key(h.product_no) == product_key}
        conflict = target not in sheets or (origin == "已保存货号规则" and lanes and lanes != {target})
        if conflict:
            message = "货号规则与当前排期分类冲突或目标分类页缺失，请人工重新选择，不能自动放行"
            row["issues"].append(unified._issue("blocked", "product_rule_conflict", "item_sheet_name", message))
            registration["conflicts"].append({"product_no": row["product_no"], "message": message})
            unified._refresh_status(row)
            continue
        row["item_sheet_name"] = target
        filled = set()
        protected = row.get('_dickie_po_fields', {})
        # PO fields win. Never carry a historic quote, quantity, date or price.
        for field in ("product_name_zh", "product_name_en"):
            if not protected.get(field) and rule.get(field):
                row[field] = rule[field]; filled.add(field)
        if not protected.get('units_per_carton') and rule.get("default_pack"):
            row["units_per_carton"] = rule["default_pack"]; filled.add("units_per_carton")
        row["issues"] = [i for i in row["issues"] if i["code"] not in {"unmapped_item_sheet", "product_rule_conflict"}
            and not (i["field"] in filled and i["code"].startswith("missing_"))]
        row.setdefault("lineage", {})["item_sheet_name"] = origin + " → " + target
        for field in filled:
            row["lineage"][field] = origin + "（原PO未提供时的默认值，仍须核对）"
        row["_product_registration_key"] = product_key
        unified._recalculate_preview_row(row)
        unified._refresh_status(row)
        registration["applied"].append({"row_id": row["id"], "product_no": row["product_no"], "origin": origin, "rule": rule})
    preview["product_registration"] = registration
    preview["summary"] = {"total": len(preview["rows"]), **{s: sum(r["status"] == s for r in preview["rows"]) for s in ("valid", "warning", "blocked")}}
    return preview
