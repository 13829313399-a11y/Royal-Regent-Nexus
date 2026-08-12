from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.molding_sample import MoldingSampleOrder


@dataclass(frozen=True, slots=True)
class MoldingSampleAISummaryRow:
    order_id: str
    order_number: str
    product_name: str
    client_name: str
    status: str
    stage: str
    order_date: str
    production_factory_id: str | None
    updated_at: str


@dataclass(frozen=True, slots=True)
class MoldingSampleAISummaryPage:
    factory_id: str
    as_of: str
    total: int
    limit: int
    offset: int
    truncated: bool
    items: tuple[MoldingSampleAISummaryRow, ...]


def list_molding_sample_ai_summaries(
    db: Session,
    factory_id: str,
    *,
    status: str = "",
    keyword: str = "",
    limit: int = 10,
    offset: int = 0,
) -> MoldingSampleAISummaryPage:
    """Return one selected-column page without loading sensitive relationships."""

    scope = select(
        MoldingSampleOrder.id.label("order_id"),
        MoldingSampleOrder.order_number.label("order_number"),
        MoldingSampleOrder.product_name.label("product_name"),
        MoldingSampleOrder.client_name.label("client_name"),
        MoldingSampleOrder.status.label("status"),
        MoldingSampleOrder.stage.label("stage"),
        MoldingSampleOrder.date.label("order_date"),
        MoldingSampleOrder.production_factory_id.label("production_factory_id"),
        MoldingSampleOrder.updated_at.label("updated_at"),
    ).where(MoldingSampleOrder.factory_id == factory_id)
    if status:
        scope = scope.where(MoldingSampleOrder.status == status)
    normalized_keyword = keyword.strip()
    if normalized_keyword:
        scope = scope.where(
            or_(
                MoldingSampleOrder.id.contains(normalized_keyword, autoescape=True),
                MoldingSampleOrder.order_number.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                MoldingSampleOrder.product_name.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                MoldingSampleOrder.client_name.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
            )
        )

    scoped_orders = scope.cte("ai_molding_sample_scope")
    total = (
        select(func.count().label("total"))
        .select_from(scoped_orders)
        .cte("ai_molding_sample_total")
    )
    page = (
        select(scoped_orders)
        .order_by(
            scoped_orders.c.updated_at.desc(),
            scoped_orders.c.order_id.desc(),
        )
        .limit(limit)
        .offset(offset)
        .cte("ai_molding_sample_page")
    )
    statement = select(
        total.c.total,
        page.c.order_id,
        page.c.order_number,
        page.c.product_name,
        page.c.client_name,
        page.c.status,
        page.c.stage,
        page.c.order_date,
        page.c.production_factory_id,
        page.c.updated_at,
    ).select_from(total.outerjoin(page, true()))
    results = db.execute(statement).mappings().all()
    total_count = int(results[0]["total"] or 0) if results else 0
    items = tuple(
        MoldingSampleAISummaryRow(
            order_id=str(row["order_id"]),
            order_number=str(row["order_number"] or ""),
            product_name=str(row["product_name"] or ""),
            client_name=str(row["client_name"] or ""),
            status=str(row["status"] or ""),
            stage=str(row["stage"] or ""),
            order_date=str(row["order_date"] or ""),
            production_factory_id=(
                str(row["production_factory_id"])
                if row["production_factory_id"]
                else None
            ),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in results
        if row["order_id"] is not None
    )
    return MoldingSampleAISummaryPage(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        total=total_count,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total_count,
        items=items,
    )
