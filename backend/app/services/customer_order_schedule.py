"""Customer schedule read views over the existing authoritative order ledger."""
from decimal import Decimal

from sqlalchemy import func, or_, select

from app.models.customer_order_ledger import OrderLedgerLine as Line, OrderLedgerDispatch as Dispatch
from app.services import customer_order_ledger as ledger

# These are saved order facts. Original spreadsheet extensions remain in source details;
# manufacturing/material fields and prices are not promoted into this schedule view.
COLUMNS = (
    ("packaging", "包装"), ("units_per_carton", "装箱数"), ("carton_count", "箱数"),
    ("standard", "国家标准"), ("manual", "说明书"), ("label", "贴纸"),
    ("customer_label", "外箱贴纸"), ("carton_mark", "箱唛"), ("fabric_label", "布标"),
    ("date_code", "日期码"), ("barcode", "条码"), ("parent_product_no", "母货号"),
    ("country", "国家"), ("port", "港口"), ("printing_requirement", "印刷要求"),
    ("contact", "联系人"), ("merchandiser", "跟单员"), ("customer_release_no", "客户 Release 单号"),
    ("customer_q", "客 Q"), ("line_q", "行 Q"), ("note", "备注"), ("recheck_notice", "待复核说明"),
)


def read_schedule(db, *, factory, customer, customer_name, q, date_from, date_to, pages, page_size):
    base = select(Line).where(Line.factory_id == factory, Line.customer_code == customer)
    present = set()
    for data in db.scalars(select(Line.data).where(Line.factory_id == factory, Line.customer_code == customer).execution_options(yield_per=500)):
        present.update(key for key, _ in COLUMNS if isinstance(data.get(key), (str, int, float, bool)) and str(data[key]).strip())
    query = base
    if q.strip():
        query = query.where(or_(*(field.contains(q.strip(), autoescape=True) for field in (
            Line.reference_no, Line.product_no, Line.data["po_no"].as_string(), Line.data["contract_no"].as_string(),
            Line.data["product_name_zh"].as_string(), Line.data["product_name_en"].as_string(),
        ))))
    due = Line.data["requested_ship_date"].as_string()
    if date_from or date_to:
        query = query.where(due != "")
    if date_from:
        query = query.where(due >= date_from.isoformat())
    if date_to:
        query = query.where(due <= date_to.isoformat())
    summary = {"order_count": 0, "ordered_quantity": Decimal(0), "shipped_quantity": Decimal(0),
               "remaining_quantity": Decimal(0), "unknown_quantity_count": 0, "cancelled_count": 0}
    # Exact decimal accumulation; partial deliveries appear in two sections but count once here.
    for quantity, shipped, status in db.execute(query.with_only_columns(Line.quantity, Line.shipped_quantity, Line.status).execution_options(yield_per=500)):
        summary["order_count"] += 1
        summary["shipped_quantity"] += shipped
        if quantity is None:
            summary["unknown_quantity_count"] += 1
        else:
            summary["ordered_quantity"] += quantity
            if status != "cancelled":
                summary["remaining_quantity"] += quantity - shipped
        if status == "cancelled":
            summary["cancelled_count"] += 1
    filters = {
        "unshipped": (Line.status == "active", or_(Line.quantity.is_(None), Line.quantity > Line.shipped_quantity)),
        "shipped": (Line.shipped_quantity > 0,),
        "cancelled": (Line.status == "cancelled",),
    }
    sections, line_by_id = {}, {}
    for name, conditions in filters.items():
        section_query = query.where(*conditions)
        total = db.scalar(select(func.count()).select_from(section_query.subquery()))
        page = min(pages[name], max(1, (total + page_size - 1) // page_size))
        items = db.scalars(section_query.order_by(func.nullif(due, "").asc().nullslast(), Line.reference_no, Line.product_no, Line.id)
                           .offset((page - 1) * page_size).limit(page_size)).all()
        sections[name] = {"items": items, "total": total, "page": page, "page_size": page_size}
        line_by_id.update((line.id, line) for line in items)
    versions = {line_id: [] for line_id in line_by_id}
    if versions:
        for line_id, version in db.execute(select(Dispatch.line_id, Dispatch.version).where(Dispatch.line_id.in_(list(versions)))):
            versions[line_id].append(version)
    for section in sections.values():
        section["items"] = [ledger.line_out(db, line, dispatch_versions=versions[line.id]) for line in section["items"]]
    for field in ("ordered_quantity", "shipped_quantity", "remaining_quantity"):
        summary[field] = ledger.decimal_text(summary[field])
    return {"factory_id": factory, "customer_code": customer, "customer_name": customer_name,
            "columns": [{"key": key, "label": label} for key, label in COLUMNS if key in present],
            "summary": summary, "sections": sections}
