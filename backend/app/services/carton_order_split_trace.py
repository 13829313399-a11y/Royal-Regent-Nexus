"""Read split provenance from exact, customer-bound schedule creation evidence."""
import json

from sqlalchemy import JSON, case, cast, func, select, type_coerce

from app.models.carton_procurement import CartonAuditEvent, CartonImportBatch
from app.services.carton_schedule_tracking import customer_key, effective_po, normalized


def _object(value):
    try:
        result = json.loads(value or "{}")
        return result if isinstance(result, dict) else {}
    except (TypeError, ValueError):
        return {}


def schedule_split_sources(db, orders):
    """Batch once per authorized order page; never infer links by contract/name."""
    if not orders:
        return {}
    factory = orders[0].factory_id
    if any(order.factory_id != factory for order in orders):
        raise ValueError("Split provenance must belong to one factory")
    by_id = {order.id: order for order in orders}
    # Restrict the JSON order ID in SQL. PostgreSQL uses the same JSON cast as
    # existing audit projections; SQLite also tolerates malformed legacy text.
    if db.bind.dialect.name == "sqlite":
        safe_detail = case((func.json_valid(CartonAuditEvent.detail_json), CartonAuditEvent.detail_json), else_="{}")
        json_detail = type_coerce(safe_detail, JSON)
    else:
        json_detail = cast(CartonAuditEvent.detail_json, JSON)
    evidence = []
    for event in db.scalars(select(CartonAuditEvent).where(
        CartonAuditEvent.factory_id == factory,
        CartonAuditEvent.event_type == "SCHEDULE_ORDER_LINKED",
        CartonAuditEvent.entity_type == "schedule_order_link",
        json_detail["order_id"].as_string().in_(list(by_id)),
    )):
        detail = _object(event.detail_json)
        order = by_id.get(detail.get("order_id"))
        if order is None or not detail.get("batch_id"):
            continue
        if any(not normalized(detail.get(key)) or normalized(detail.get(key)) != normalized(getattr(order, key))
               for key in ("order_no", "customer_code", "contract_no", "item_no")):
            continue
        evidence.append((order, detail))
    batch_ids = {detail["batch_id"] for _, detail in evidence}
    if not batch_ids:
        return {}
    summaries = {batch.id: _object(batch.parse_summary_json) for batch in db.scalars(
        select(CartonImportBatch).where(CartonImportBatch.factory_id == factory,
            CartonImportBatch.id.in_(batch_ids), CartonImportBatch.import_type == "WEEKLY_SCHEDULE"))}
    candidates = {}
    for order, detail in evidence:
        summary = summaries.get(detail["batch_id"], {})
        rows = summary.get("rows", [])
        if not isinstance(rows, list):
            continue
        source = [row for row in rows if isinstance(row, dict)
                  and row.get("source_sheet") == detail.get("source_sheet")
                  and row.get("source_row") == detail.get("source_row")]
        if len(source) != 1 or not detail.get("source_sheet") or not isinstance(detail.get("source_row"), int):
            continue
        row = source[0]
        # Legacy raw buyer names remain evidence; they never authorize a new mapping.
        if not customer_key(row) or customer_key(row) != detail.get("customer"):
            continue
        customer = summary.get("schedule_customer")
        batch_code = customer.get("customer_code") if isinstance(customer, dict) else None
        if any(code and normalized(code) != normalized(order.customer_code)
               for code in (row.get("schedule_customer_code"), batch_code)):
            continue
        if any(normalized(row.get(key)) != normalized(getattr(order, key)) for key in ("contract_no", "item_no")):
            continue
        if effective_po(row) and effective_po(row) != effective_po({"customer_po": order.customer_po}):
            continue
        source_contract = str(row.get("split_source") or "").strip()
        if not source_contract:
            continue
        trace = dict(source_contract_no=source_contract, current_contract_no=order.contract_no,
                     batch_id=detail["batch_id"], source_sheet=detail["source_sheet"], source_row=detail["source_row"])
        candidates.setdefault(order.id, []).append(trace)
    # Conflicting creation evidence is deliberately not guessed away.
    return {identifier: traces[0] for identifier, traces in candidates.items()
            if all(trace == traces[0] for trace in traces)}
