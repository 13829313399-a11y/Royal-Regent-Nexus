"""Logical quotation membership, separate from immutable version storage."""
from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.orm import aliased

from app.models.internal_quote import (
    InternalQuote, InternalQuoteAlternative, InternalQuoteFamily,
    InternalQuoteExportFile, InternalQuoteArtifactHandoff,
)


def product_root(db, quote):
    entry = db.get(InternalQuoteAlternative, quote.id)
    root = db.get(InternalQuote, entry.family_id) if entry else quote
    if root is None or root.factory_id != quote.factory_id:
        raise HTTPException(409, "报价方案所属产品不存在或厂区不一致")
    return root


def document_products(db, quote):
    root = product_root(db, quote)
    rows = list(db.scalars(select(InternalQuote).where(
        InternalQuote.factory_id == root.factory_id,
        InternalQuote.batch_id == (root.batch_id or root.id),
    ).order_by(InternalQuote.batch_position, InternalQuote.id)))
    return rows or [root]


def document_id(db, quote):
    return document_products(db, quote)[0].id


def document_counts(db, quote):
    roots = document_products(db, quote)
    root_ids = [root.id for root in roots]
    variants = list(db.scalars(select(InternalQuoteAlternative).where(
        InternalQuoteAlternative.family_id.in_(root_ids),
        ~InternalQuoteAlternative.quote_id.in_(root_ids),
    )))
    return len(roots), len(roots) + len(variants)


def document_list_condition():
    # Family roots are the product slots. Other versions remain accessible in
    # the document but must never become extra homepage rows or extra products.
    return ~select(InternalQuoteAlternative.quote_id).where(
        InternalQuoteAlternative.quote_id == InternalQuote.id,
        InternalQuoteAlternative.family_id != InternalQuote.id,
    ).exists()


def document_filter_condition(match):
    """A matching product/version finds its document, including old families."""
    root = aliased(InternalQuote)
    version = aliased(InternalQuote)
    entry = aliased(InternalQuoteAlternative)
    return or_(
        match(InternalQuote),
        select(root.id).where(root.factory_id == InternalQuote.factory_id,
                              root.batch_id == InternalQuote.batch_id, match(root)).exists(),
        select(version.id).join(entry, entry.quote_id == version.id).join(root, root.id == entry.family_id).where(
            root.factory_id == InternalQuote.factory_id,
            version.factory_id == InternalQuote.factory_id,
            root.batch_id == InternalQuote.batch_id,
            match(version),
        ).exists(),
    )


def deletion_reason(db, quote):
    rows = list(db.scalars(select(InternalQuote).where(
        InternalQuote.factory_id == quote.factory_id,
        InternalQuote.batch_id == (quote.batch_id or quote.id),
    ))) or [quote]
    ids = [row.id for row in rows]
    if any(row.status in {"released", "fully_approved", "exported", "final_reviewing", "pending_review"}
           or row.final_release_status in {"approved", "issued", "pending"}
           or row.final_release_revision > 0 for row in rows):
        return "已提交、已放行或已输出的报价不能删除，请使用归档保留审计记录"
    for model in (InternalQuoteExportFile, InternalQuoteArtifactHandoff):
        if db.scalar(select(model.id).where(model.quote_id.in_(ids)).limit(1)):
            return "已导出或已交接的报价不能删除，请使用归档保留审计记录"
    entries = list(db.scalars(select(InternalQuoteAlternative).where(InternalQuoteAlternative.quote_id.in_(ids))))
    if any(row.issued_at or row.reported_at for row in entries):
        return "已输出或已报客的方案版本不能删除，请使用归档"
    if db.scalar(select(InternalQuoteFamily.id).where(InternalQuoteFamily.selected_quote_id.in_(ids)).limit(1)):
        return "客户采用的版本不能删除，请保留采用记录"
    if db.scalar(select(InternalQuote.id).where(
        InternalQuote.cloned_from_quote_id.in_(ids), ~InternalQuote.id.in_(ids),
    ).limit(1)) or db.scalar(select(InternalQuoteAlternative.quote_id).where(
        InternalQuoteAlternative.source_quote_id.in_(ids), ~InternalQuoteAlternative.quote_id.in_(ids),
    ).limit(1)):
        return "已有后续方案、版本或报价引用，不能删除来源资料，请归档"
    if db.scalar(select(InternalQuoteAlternative.quote_id).where(
        InternalQuoteAlternative.family_id.in_(ids), ~InternalQuoteAlternative.quote_id.in_(ids),
    ).limit(1)):
        return "本产品仍有其他方案版本，请先清理未使用草稿或归档"
    return ""
