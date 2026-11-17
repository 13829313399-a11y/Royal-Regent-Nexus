"""Explicit, atomic freeze/unfreeze of every current product in a document."""
from fastapi import HTTPException
from sqlalchemy import select

from app.models.internal_quote import InternalQuoteAlternative, InternalQuoteSection
from app.services.auth import now_text
from app.services.internal_quote import (
    _get_quote, _check_revision, _add_audit, _add_revision, _invalidate_final_release,
    ensure_quote_read, quote_to_out,
)
from app.services.internal_quote_alternatives import (
    _manage, _write_family, issue_alternative, list_alternatives,
)
from app.services.internal_quote_artifacts import _ensure_export_permission
from app.services.internal_quote_calculator import canonical_json
from app.services.internal_quote_document import (
    document_products, product_root, lock_documents, ensure_not_archived, document_archive,
)
from app.services.transaction_lock import lock_transaction


def _authorize(db, quote, user):
    ensure_quote_read(db, user, quote.factory_id)
    _manage(db, quote, user)
    _ensure_export_permission(db, quote, user)


def get_freeze_options(db, quote_id, user):
    quote = _get_quote(db, quote_id)
    _authorize(db, quote, user)
    if document_archive(db, quote):
        raise HTTPException(409, "整单报价已归档，请先恢复整单")
    products = []
    for root in document_products(db, quote):
        _authorize(db, root, user)
        family = list_alternatives(db, root.id, user)
        products.append({
            "product_root_id": root.id, "product_name": root.product_name,
            "family_revision": family["revision"],
            "options": [item for item in family["items"] if not item["archived"]],
        })
    return {"products": products}


def set_document_frozen(db, quote_id, payload, user, request=None):
    try:
        source = _get_quote(db, quote_id)
        quotes = [_get_quote(db, item.quote_id) for item in payload.products]
        for quote in [source, *quotes]:
            _authorize(db, quote, user)
        lock_documents(db, [source, *quotes])
        roots = document_products(db, source)
        for identity in sorted({f"{q.factory_id}:{q.batch_id or q.id}" for q in [source, *quotes, *roots]}):
            lock_transaction(db, "internal-quote", identity)
        for identity in sorted({product_root(db, q).id for q in [source, *quotes, *roots]}):
            lock_transaction(db, "internal-quote-family", identity)
        db.expire_all()
        source = _get_quote(db, quote_id)
        roots = document_products(db, source)
        quotes = [_get_quote(db, item.quote_id) for item in payload.products]
        selected = {product_root(db, q).id: q for q in quotes}
        if len(selected) != len(quotes) or set(selected) != {q.id for q in roots}:
            raise HTTPException(409, "冻结或解除冻结须包含本报价全部产品，每款一个当前版本，不能遗漏、重复或跨报价")
        if document_archive(db, source):
            raise HTTPException(409, "整单报价已归档，请先恢复整单")
        requests = {item.quote_id: item for item in payload.products}
        # Validate the entire document before changing any member.
        families = {}
        for quote in quotes:
            _authorize(db, quote, user)
            ensure_not_archived(db, quote)
            if quote.module_version != "v4":
                raise HTTPException(409, "历史审核报价保留原审核流程，请复制为直接输出版本后操作")
            _check_revision(quote.header_revision, requests[quote.id].revision, quote.product_name)
            family = _write_family(db, quote, requests[quote.id].family_revision)
            families[quote.id] = family
            if not payload.frozen and family.selected_quote_id == quote.id:
                raise HTTPException(409, f"{quote.product_name} 已被客户采用，请先取消采用再解除冻结")
        for root in roots:
            quote = selected[root.id]
            was_frozen = quote.final_release_status == "issued"
            if was_frozen == payload.frozen:
                continue
            if payload.frozen:
                # Freeze a verified current calculation and keep its exact downloadable file.
                issue_alternative(db, quote.id, requests[quote.id], user, request, commit=False, freeze=True)
            else:
                _invalidate_final_release(db, quote, reason=f"解除冻结：{payload.reason}")
                quote.status = "drafting"
                quote.header_revision += 1
                quote.updated_at = now_text()
                for section in db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)):
                    if section.status == "sealed":
                        section.status = "draft"
                        section.revision += 1
                        _add_revision(db, quote, section, user, reason="manual_unfreeze")
                # Reporting belongs to an immutable output, not to subsequent edits.
                db.get(InternalQuoteAlternative, quote.id).reported_at = ""
                families[quote.id].revision += 1
            _add_audit(db, quote, user, "manual_freeze" if payload.frozen else "manual_unfreeze",
                       reason=payload.reason, detail=canonical_json({
                           "document_quote_id": roots[0].id,
                           "products": [selected[item.id].id for item in roots],
                           "frozen": payload.frozen,
                       }), request=request)
        db.flush()
        result = [quote_to_out(db, selected[root.id]) for root in roots]
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
