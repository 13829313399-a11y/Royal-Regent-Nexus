"""Read-only ledger predicates shared by the native list and assistant.

Callers must authorize customer_order:read in the requested factory. No writes,
implicit reconciliation, or manufacturing totals belong to this projection.
"""
from datetime import date
from decimal import Decimal
import re

from sqlalchemy import func, or_, select

from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.services import customer_order_ledger as ledger
from app.services.customer_order_360_dates import shanghai_today


def statement(factory_id, *, customer_code="", view="all", q="", resource_id=None, date_from=None, date_to=None):
    if view not in {"all", "unshipped", "shipped", "cancelled"}:
        raise ValueError("unsupported ledger view")
    query = select(Line).where(Line.factory_id == factory_id)
    if customer_code:
        query = query.where(Line.customer_code == customer_code)
    if resource_id:
        query = query.where(Line.id == resource_id)
    if view == "unshipped":
        query = query.where(Line.status == "active", or_(Line.quantity.is_(None), Line.quantity > Line.shipped_quantity))
    elif view == "shipped":
        query = query.where(Line.shipped_quantity > 0)
    elif view == "cancelled":
        query = query.where(Line.status == "cancelled")
    if q.strip():
        query = query.where(or_(*(field.contains(q.strip(), autoescape=True) for field in (
            Line.reference_no, Line.product_no, Line.data["po_no"].as_string(),
            Line.data["contract_no"].as_string(), Line.customer_name,
        ))))
    due = Line.data["requested_ship_date"].as_string()
    if date_from:
        query = query.where(due >= date_from.isoformat())
    if date_to:
        query = query.where(due != "", due <= date_to.isoformat())
    return query


def page(db, query, *, page_number=1, page_size=50):
    if type(page_number) is not int or page_number < 1 or type(page_size) is not int or not 1 <= page_size <= 200:
        raise ValueError("invalid ledger pagination")
    return read_slice(db, query, offset=(page_number - 1) * page_size, limit=page_size)


def read_slice(db, query, *, offset=0, limit=50):
    if type(offset) is not int or offset < 0 or type(limit) is not int or not 1 <= limit <= 200:
        raise ValueError("invalid ledger pagination")
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Line.updated_at.desc(), Line.id)
                      .offset(offset).limit(limit)).all()
    return total, rows


def requested_date(data):
    """Only real ISO calendar dates count as a known requested shipping date."""
    value = data.get("requested_ship_date") if isinstance(data, dict) else None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def progress(db, query, *, today=None):
    """Exact filtered totals, never a sum of a returned page or two schedule tabs.

    Quantities use the native ledger's original quantity unit; they do not assert
    a conversion of sets/cartons to pieces. Null quantities remain incomplete.
    Cancellation contributes no remaining quantity; shipments are independent.
    """
    today = today or shanghai_today()
    result = dict(order_count=0, unfinished_count=0, cancelled_count=0,
                  unknown_quantity_count=0, remaining_unknown_count=0,
                  overdue_count=0, overdue_unknown_count=0,
                  ordered_quantity=Decimal(0), shipped_quantity=Decimal(0), remaining_quantity=Decimal(0))
    facts = query.with_only_columns(Line.quantity, Line.shipped_quantity, Line.status, Line.data)
    for quantity, shipped, status, data in db.execute(facts.execution_options(yield_per=500)):
        result["order_count"] += 1
        result["shipped_quantity"] += shipped
        if quantity is None:
            result["unknown_quantity_count"] += 1
        else:
            result["ordered_quantity"] += quantity
        if status == "cancelled":
            result["cancelled_count"] += 1
            continue
        if quantity is None:
            result["remaining_unknown_count"] += 1
        else:
            result["remaining_quantity"] += quantity - shipped
        if status == "active" and (quantity is None or quantity > shipped):
            result["unfinished_count"] += 1
            due = requested_date(data)
            if quantity is None or due is None:
                result["overdue_unknown_count"] += 1
            elif due < today:
                result["overdue_count"] += 1
    for key in ("ordered_quantity", "shipped_quantity", "remaining_quantity"):
        result[key] = ledger.decimal_text(result[key])
    result["as_of_date"] = today.isoformat()
    result["timezone"] = "Asia/Shanghai"
    return result
