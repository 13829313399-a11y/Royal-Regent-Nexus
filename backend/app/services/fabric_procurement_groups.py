"""Read-only material follow-up groups; original purchase lines remain authoritative."""
from collections import defaultdict
from decimal import Decimal, localcontext

from app.services.fabric_procurement_parser import digest


def group_key(item):
    facts = item["facts"]
    identity = [facts.get(field, "") for field in ("supplier", "material_code", "material_name", "unit")]
    # Missing identities must not accidentally combine unrelated sources.
    if not all(identity):
        identity.append(item["id"])
    return digest(["purchase-material-v1", *identity])


def exact_sum(values):
    numbers = [Decimal(value) for value in values]
    with localcontext() as context:
        context.prec = max(28, sum(len(n.as_tuple().digits) + abs(n.as_tuple().exponent) for n in numbers) + 10)
        result = format(sum(numbers, Decimal(0)), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def material_groups(items, sort):
    buckets = defaultdict(list)
    # Input is already filtered and ordered, but has not yet been paginated.
    for item in items:
        buckets[group_key(item)].append(item)
    result = []
    for key, rows in buckets.items():
        facts = rows[0]["facts"]
        known = [row["warehouse_outstanding_quantity"] for row in rows
                 if row.get("warehouse_outstanding_quantity") is not None
                 and not any(row.get(flag) for flag in ("receipt_identity_review_required", "receipt_quantity_conflict", "receipt_reconciliation_required"))]
        unknown = len(rows) - len(known)
        received = [row["warehouse_received_quantity"] for row in rows
                    if row.get("warehouse_received_quantity") is not None
                    and not row.get("receipt_identity_review_required") and not row.get("receipt_reconciliation_required")]
        received_unknown = len(rows) - len(received)
        dates = sorted(row["promise_date"] for row in rows if row.get("promise_date"))
        quantity = exact_sum(known)
        result.append({
            "key": key, **{field: facts.get(field, "") for field in ("supplier", "material_code", "material_name", "unit")},
            "line_count": len(rows),
            "order_count": len({(row["facts"].get("source_category", "PURCHASE"), row["facts"].get("supplement_no") or row["facts"].get("order_no") or row["id"]) for row in rows}),
            "production_count": len({row["facts"]["production_no"] for row in rows if row["facts"].get("production_no")}),
            "supplement_count": sum(row["facts"].get("source_category") == "SUPPLEMENT" for row in rows),
            "remaining_quantity": None if unknown else quantity,
            "known_remaining_quantity": quantity, "unknown_quantity_count": unknown,
            "warehouse_received_quantity": None if received_unknown else exact_sum(received),
            "known_received_quantity": exact_sum(received), "unknown_received_count": received_unknown,
            "earliest_promise": dates[0] if dates else None, "latest_promise": dates[-1] if dates else None,
            **{f"{flag}_count": sum(bool(row.get("tracking", {}).get(flag)) for row in rows)
               for flag in ("overdue", "due_today", "awaiting_date", "changed")},
        })
    if sort in {"QUANTITY_ASC", "QUANTITY_DESC"}:
        known = [group for group in result if group["remaining_quantity"] is not None]
        unknown = [group for group in result if group["remaining_quantity"] is None]
        known.sort(key=lambda group: Decimal(group["remaining_quantity"]), reverse=sort == "QUANTITY_DESC")
        result = known + unknown
    return result
