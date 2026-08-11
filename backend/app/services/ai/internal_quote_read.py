from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.internal_quote import InternalQuote


@dataclass(frozen=True, slots=True)
class InternalQuoteAISummaryRow:
    quote_id: str
    quote_no: str
    customer: str
    status: str
    version_label: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class InternalQuoteAISummaryPage:
    factory_id: str
    as_of: str
    total: int
    limit: int
    offset: int
    truncated: bool
    items: tuple[InternalQuoteAISummaryRow, ...]


def list_internal_quote_ai_summaries(
    db: Session,
    factory_id: str,
    *,
    status: str = "",
    keyword: str = "",
    limit: int = 10,
    offset: int = 0,
) -> InternalQuoteAISummaryPage:
    """Read one minimal, factory-scoped page without loading quote ORM objects."""

    scope = select(
        InternalQuote.id.label("quote_id"),
        InternalQuote.quote_no.label("quote_no"),
        InternalQuote.customer.label("customer"),
        InternalQuote.status.label("status"),
        InternalQuote.version_label.label("version_label"),
        InternalQuote.updated_at.label("updated_at"),
    ).where(InternalQuote.factory_id == factory_id)
    if status:
        scope = scope.where(InternalQuote.status == status)
    normalized_keyword = keyword.strip()
    if normalized_keyword:
        scope = scope.where(
            or_(
                InternalQuote.quote_no.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                InternalQuote.customer.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
            )
        )

    scoped_quotes = scope.cte("ai_internal_quote_scope")
    total = (
        select(func.count().label("total"))
        .select_from(scoped_quotes)
        .cte("ai_internal_quote_total")
    )
    page = (
        select(scoped_quotes)
        .order_by(
            scoped_quotes.c.updated_at.desc(),
            scoped_quotes.c.quote_id.desc(),
        )
        .limit(limit)
        .offset(offset)
        .cte("ai_internal_quote_page")
    )
    statement = select(
        total.c.total,
        page.c.quote_id,
        page.c.quote_no,
        page.c.customer,
        page.c.status,
        page.c.version_label,
        page.c.updated_at,
    ).select_from(total.outerjoin(page, true()))
    results = db.execute(statement).mappings().all()
    total_count = int(results[0]["total"] or 0) if results else 0
    items = tuple(
        InternalQuoteAISummaryRow(
            quote_id=str(row["quote_id"]),
            quote_no=str(row["quote_no"] or ""),
            customer=str(row["customer"] or ""),
            status=str(row["status"] or ""),
            version_label=str(row["version_label"] or ""),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in results
        if row["quote_id"] is not None
    )
    return InternalQuoteAISummaryPage(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        total=total_count,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total_count,
        items=items,
    )
