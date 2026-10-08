"""Preview and atomic copying of shared packaging between document products."""
from copy import deepcopy

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.models.internal_quote import InternalQuoteAlternative, InternalQuoteSection
from app.services.internal_quote_document import document_id, product_root
from app.services.internal_quote_calculator import canonical_json, content_hash
from app.services.internal_quote import (
    _get_quote, _get_section, _check_revision, _json_object, _ensure_active,
    ensure_quote_read, ensure_section_permission, ensure_quote_permission,
    ensure_quote_formula_current, _save_section_in_transaction, _derive_quote_status,
    _add_audit, quote_to_out, MUTABLE_SECTION_STATUSES,
)
from app.services.transaction_lock import lock_transaction
from app.services.internal_quote_sync import _preserve_local


class PackagingCopyTarget(BaseModel):
    quote_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)


class PackagingCopyRequest(BaseModel):
    revision: int = Field(ge=1)
    targets: list[PackagingCopyTarget] = Field(min_length=1, max_length=50)
    include_assembly: bool = False
    reason: str = Field(min_length=1, max_length=1000)
    preview_token: str = Field(default="", max_length=64)


SALES_FIELDS = (
    "packaging_materials", "cartons", "paper_price_factor", "inner_paper_price_factor",
    "flat_card_price_factor", "color_box_size_in", "color_box_size_cm", "color_box_size_unit",
    "pdq_size_in", "pdq_size_unit", "justplay_carton", "justplay_packaging",
)


def merge_packaging(before, source, code):
    result = deepcopy(before)
    if code == "sales":
        for field in SALES_FIELDS:
            if field in source:
                result[field] = deepcopy(source[field])
            else:
                result.pop(field, None)
    else:
        result["groups"] = [deepcopy(row) for row in before.get("groups", [])
                            if row.get("category", "assembly") != "packaging"] + [
            deepcopy(row) for row in source.get("groups", []) if row.get("category") == "packaging"]
    result = _preserve_local(result, before)
    # Shared packaging is product-level; component ownership and attachments
    # never travel across products, even in old imported packaging rows.
    def clean(value):
        if isinstance(value, dict):
            return {key: clean(child) for key, child in value.items()
                    if key not in {"pricing_component_id", "image_attachment_ids", "import_batch_id"}}
        if isinstance(value, list):
            return [clean(child) for child in value]
        return value
    if code == "sales":
        for field in SALES_FIELDS:
            if field in result:
                result[field] = clean(result[field])
    else:
        result["groups"] = [clean(row) if row.get("category") == "packaging" else row
                            for row in result["groups"]]
    return result


def _plan(db, quote_id, payload, user):
    ids = [quote_id, *(row.quote_id for row in payload.targets)]
    if len(ids) != len(set(ids)) or not payload.reason.strip():
        raise HTTPException(400, "请选择不同的目标款并填写复制说明")
    # Match the ordinary quote/family write lock order. All quote locks precede
    # family locks; stale source/target checks happen only after locks are held.
    quotes = [_get_quote(db, identity) for identity in ids]
    for quote in quotes:
        ensure_quote_read(db, user, quote.factory_id)
    for identity in sorted({f"{q.factory_id}:{q.batch_id or q.id}" for q in quotes}):
        lock_transaction(db, "internal-quote", identity)
    roots = [product_root(db, quote) for quote in quotes]
    for identity in sorted({root.id for root in roots}):
        lock_transaction(db, "internal-quote-family", identity)
    db.expire_all()
    source = _get_quote(db, quote_id)
    ensure_quote_permission(db, user, "internal_quote:clone", source.factory_id, ("sales-business", "engineering"))
    _check_revision(source.header_revision, payload.revision, "来源报价")
    _ensure_active(source)
    source_entry = db.get(InternalQuoteAlternative, source.id)
    if source_entry and source_entry.archived:
        raise HTTPException(409, "来源方案已归档，请先恢复")
    ensure_quote_formula_current(source, list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == source.id))))
    owner = document_id(db, source)
    codes = ["assembly", "sales"] if payload.include_assembly else ["sales"]
    source_payloads = {}
    for code in codes:
        section = _get_section(db, source.id, code)
        if not section.is_required or not section.filled_at or section.calculation_status != "valid" or section.dependency_status != "current":
            raise HTTPException(409, f"来源{section.department_name}须先保存并完成有效核算")
        source_payloads[code] = _json_object(section.payload_json)
    plans = []
    for selection in payload.targets:
        target = _get_quote(db, selection.quote_id)
        if (target.factory_id != source.factory_id or target.customer != source.customer
                or document_id(db, target) != owner or product_root(db, target).id == roots[0].id):
            raise HTTPException(400, "只能复制到同一报价单、客户和厂区内的其他产品")
        _ensure_active(target)
        entry = db.get(InternalQuoteAlternative, target.id)
        if entry and entry.archived:
            raise HTTPException(409, "目标方案已归档，请先恢复")
        if target.status not in {"drafting", "rejected"} or target.final_release_status in {"issued", "approved", "pending"}:
            raise HTTPException(409, "目标已提交或已输出，请先复制新版本后接收包装")
        _check_revision(target.header_revision, selection.revision, "目标报价")
        ensure_quote_formula_current(target, list(db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == target.id))))
        sections = []
        for code in codes:
            ensure_section_permission(db, user, target.factory_id, code, "edit")
            section = _get_section(db, target.id, code)
            if not section.is_required or section.status not in MUTABLE_SECTION_STATUSES:
                raise HTTPException(409, f"目标{section.department_name}当前不可编辑")
            before = _json_object(section.payload_json)
            after = merge_packaging(before, source_payloads[code], code)
            sections.append({"code": code, "revision": section.revision, "before": before, "after": after})
        plans.append({"quote_id": target.id, "product_name": target.product_name,
                      "revision": target.header_revision, "sections": sections})
    token = content_hash({"source": source.id, "revision": source.header_revision,
                          "inputs": source_payloads, "targets": plans, "reason": payload.reason.strip()})
    return source, plans, token


def preview_packaging_copy(db, quote_id, payload, user):
    try:
        source, plans, token = _plan(db, quote_id, payload, user)
        sales = _json_object(_get_section(db, source.id, "sales").payload_json)
        materials = []
        for row in sales.get("packaging_materials", []):
            currency = str(row.get("unit_price_source_currency", "")).strip().upper()
            if currency not in {"RMB", "HKD"}:
                currency = "HKD" if row.get("unit_price_rmb") in (None, "") and row.get("unit_price_hkd") not in (None, "") else "RMB"
            materials.append({"item": row.get("item", ""), "quantity": row.get("quantity", ""),
                              "price": row.get(f"unit_price_{currency.lower()}", ""), "currency": currency,
                              "specification": row.get("specification", "")})
        return {"preview_token": token, "source_name": source.product_name, "material_details": materials, "targets": [
            {"quote_id": plan["quote_id"], "product_name": plan["product_name"],
             "changed": any(row["before"] != row["after"] for row in plan["sections"]),
             "packaging_material_count": len(next(row["after"] for row in plan["sections"] if row["code"] == "sales").get("packaging_materials", [])),
             "carton_count": len(next(row["after"] for row in plan["sections"] if row["code"] == "sales").get("cartons", [])),
             "replaces_existing": any(any(row["before"].get(key) for key in (
                 SALES_FIELDS if row["code"] == "sales" else ["groups"])) for row in plan["sections"])} for plan in plans]}
    finally:
        db.rollback()  # Read-only preview releases transaction locks.


def apply_packaging_copy(db, quote_id, payload, user, request=None):
    try:
        source, plans, token = _plan(db, quote_id, payload, user)
        if not payload.preview_token or token != payload.preview_token:
            raise HTTPException(409, "复制预览已失效，请重新预览后确认")
        result = []
        for plan in plans:
            target = _get_quote(db, plan["quote_id"])
            for row in plan["sections"]:
                section = _save_section_in_transaction(db, target, _get_section(db, target.id, row["code"]),
                                                       row["after"], payload.reason, user, request)
                if section.calculation_status != "valid" or section.dependency_status != "current":
                    raise HTTPException(409, f"{target.product_name}的{section.department_name}核算未通过，整批未复制，请补全目标款资料")
            _derive_quote_status(db, target)
            _add_audit(db, target, user, "packaging_copy", detail=canonical_json({
                "source_quote_id": source.id, "source_revision": payload.revision,
                "include_assembly": payload.include_assembly, "preview_token": token}),
                reason=payload.reason, request=request)
            result.append(quote_to_out(db, target))
        db.commit()
        return {"targets": result}
    except Exception:
        db.rollback()
        raise
