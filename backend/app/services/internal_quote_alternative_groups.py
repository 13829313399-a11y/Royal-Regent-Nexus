"""Atomic product-family copies; group membership is immutable audit evidence."""
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.models.internal_quote import InternalQuote, InternalQuoteAuditLog
from app.schemas.internal_quote_alternatives import AlternativeCopyRequest
from app.services.internal_quote import (
    _get_quote, _check_revision, _add_audit, _json_object, _initiator_department,
    ensure_quote_read, ensure_permission_in_scope,
)
from app.services.internal_quote_alternatives import copy_alternative, list_alternatives
from app.services.internal_quote_calculator import canonical_json
from app.services.internal_quote_document import document_products, product_root, lock_documents, ensure_not_archived
from app.services.transaction_lock import lock_transaction


def get_alternative_group(db, quote_id, user):
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    event = db.scalar(select(InternalQuoteAuditLog).where(
        InternalQuoteAuditLog.quote_id == quote.id,
        InternalQuoteAuditLog.factory_id == quote.factory_id,
        InternalQuoteAuditLog.action == "alternative_group_copy",
    ).order_by(InternalQuoteAuditLog.created_at.desc(), InternalQuoteAuditLog.id.desc()).limit(1))
    if event is None:
        return None
    data = _json_object(event.detail)
    roots = {q.id for q in document_products(db, quote)}
    # Missing/deleted members are still identified so the UI requests an
    # explicit replacement instead of silently mixing in original versions.
    if {p.get("product_root_id") for p in data.get("products", [])} != roots:
        raise HTTPException(409, "方案组产品清单已变化，请重新选择各款版本")
    return data


def copy_alternative_group(db, quote_id, payload, user, request=None):
    try:
        source = _get_quote(db, quote_id)
        sources = [_get_quote(db, p.quote_id) for p in payload.products]
        for quote in [source, *sources]:
            ensure_quote_read(db, user, quote.factory_id)
            department = _initiator_department(user, quote.factory_id)
            for permission in ("internal_quote:create", "internal_quote:clone"):
                ensure_permission_in_scope(db, user, permission, quote.factory_id, department)
            if quote.factory_id != source.factory_id or quote.customer != source.customer:
                raise HTTPException(400, "整组方案只能复制同厂区、同客户、同一报价的产品")
        lock_documents(db, [source, *sources])
        roots = document_products(db, source)
        for identity in sorted({f"{q.factory_id}:{q.batch_id or q.id}" for q in [source, *sources, *roots]}):
            lock_transaction(db, "internal-quote", identity)
        for identity in sorted({product_root(db, q).id for q in [source, *sources, *roots]}):
            lock_transaction(db, "internal-quote-family", identity)
        db.expire_all()
        source = _get_quote(db, quote_id)
        roots = document_products(db, source)
        sources = [_get_quote(db, p.quote_id) for p in payload.products]
        by_root = {product_root(db, q).id: q for q in sources}
        if len(by_root) != len(sources) or set(by_root) != {q.id for q in roots}:
            raise HTTPException(409, "请完整选择本报价每款产品的一个来源版本，不能重复、遗漏或加入其他报价")
        by_id = {p.quote_id: p for p in payload.products}
        for quote in [source, *sources]:
            ensure_not_archived(db, quote)
        for quote in sources:
            _check_revision(quote.header_revision, by_id[quote.id].revision, quote.product_name)
            _check_revision(list_alternatives(db, quote.id, user)["revision"], by_id[quote.id].family_revision, f"{quote.product_name}方案列表")
        copies = []
        members = []
        for root in roots:
            quote = by_root[root.id]
            row = by_id[quote.id]
            created = copy_alternative(db, quote.id, AlternativeCopyRequest(
                revision=row.revision, family_revision=row.family_revision,
                kind=payload.kind, name=payload.name, change_note=payload.change_note,
            ), user, request, commit=False)
            copies.append(created)
            members.append({"product_root_id": root.id, "source_quote_id": quote.id, "quote_id": created.id})
        group = {"group_id": f"IQG-{uuid4().hex}", "document_quote_id": roots[0].id,
                 "kind": payload.kind, "name": payload.name, "products": members}
        for copy in copies:
            _add_audit(db, db.get(InternalQuote, copy.id), user, "alternative_group_copy",
                       detail=canonical_json(group), reason=payload.change_note, request=request)
        db.commit()
        return {"group": group, "quotes": copies}
    except Exception:
        db.rollback()
        raise
