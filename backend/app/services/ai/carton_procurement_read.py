from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.carton_procurement import CartonOrder


@dataclass(frozen=True, slots=True)
class CartonProcurementAISummaryRow:
    order_id: str
    order_no: str
    customer_name: str
    contract_no: str
    item_no: str
    product_name: str
    order_date: str
    due_date: str
    status: str
    revision: int
    updated_at: str


@dataclass(frozen=True, slots=True)
class CartonProcurementAISummaryPage:
    factory_id: str
    as_of: str
    total: int
    limit: int
    offset: int
    truncated: bool
    items: tuple[CartonProcurementAISummaryRow, ...]


def list_carton_procurement_ai_summaries(
    db: Session,
    factory_id: str,
    *,
    status: str = "",
    keyword: str = "",
    limit: int = 10,
    offset: int = 0,
) -> CartonProcurementAISummaryPage:
    """Read a selected-column order page without loading lines or values."""

    scope = select(
        CartonOrder.id.label("order_id"),
        CartonOrder.order_no.label("order_no"),
        CartonOrder.customer_name.label("customer_name"),
        CartonOrder.contract_no.label("contract_no"),
        CartonOrder.item_no.label("item_no"),
        CartonOrder.product_name.label("product_name"),
        CartonOrder.order_date.label("order_date"),
        CartonOrder.due_date.label("due_date"),
        CartonOrder.status.label("status"),
        CartonOrder.revision.label("revision"),
        CartonOrder.updated_at.label("updated_at"),
    ).where(CartonOrder.factory_id == factory_id)
    if status:
        scope = scope.where(CartonOrder.status == status)
    normalized_keyword = keyword.strip()
    if normalized_keyword:
        scope = scope.where(
            or_(
                CartonOrder.order_no.contains(normalized_keyword, autoescape=True),
                CartonOrder.customer_name.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                CartonOrder.contract_no.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
                CartonOrder.item_no.contains(normalized_keyword, autoescape=True),
                CartonOrder.product_name.contains(
                    normalized_keyword,
                    autoescape=True,
                ),
            )
        )
    scoped_orders = scope.cte("ai_carton_procurement_scope")
    total = (
        select(func.count().label("total"))
        .select_from(scoped_orders)
        .cte("ai_carton_procurement_total")
    )
    page = (
        select(scoped_orders)
        .order_by(
            scoped_orders.c.updated_at.desc(),
            scoped_orders.c.order_id.desc(),
        )
        .limit(limit)
        .offset(offset)
        .cte("ai_carton_procurement_page")
    )
    statement = select(
        total.c.total,
        page.c.order_id,
        page.c.order_no,
        page.c.customer_name,
        page.c.contract_no,
        page.c.item_no,
        page.c.product_name,
        page.c.order_date,
        page.c.due_date,
        page.c.status,
        page.c.revision,
        page.c.updated_at,
    ).select_from(total.outerjoin(page, true()))
    results = db.execute(statement).mappings().all()
    total_count = int(results[0]["total"] or 0) if results else 0
    items = tuple(
        CartonProcurementAISummaryRow(
            order_id=str(row["order_id"]),
            order_no=str(row["order_no"] or ""),
            customer_name=str(row["customer_name"] or ""),
            contract_no=str(row["contract_no"] or ""),
            item_no=str(row["item_no"] or ""),
            product_name=str(row["product_name"] or ""),
            order_date=str(row["order_date"] or ""),
            due_date=str(row["due_date"] or ""),
            status=str(row["status"] or ""),
            revision=int(row["revision"] or 0),
            updated_at=str(row["updated_at"] or ""),
        )
        for row in results
        if row["order_id"] is not None
    )
    return CartonProcurementAISummaryPage(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        total=total_count,
        limit=limit,
        offset=offset,
        truncated=offset + len(items) < total_count,
        items=items,
    )
