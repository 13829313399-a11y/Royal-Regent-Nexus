"""Match split destinations to their original purchase family before paging."""
from sqlalchemy import and_, false, tuple_

from app.models.carton_procurement import CartonOrder
from app.services.carton_order_split import plans


def destination_predicate(db, factory_id, search):
    term = search.strip().casefold()
    if not term:
        return false()
    identities = set()
    # The audit aggregate resolves confirmations/cancellations once per search,
    # not once per returned order. Parent query permissions still apply outside
    # this OR branch, and no destination becomes an independent purchase row.
    for plan in plans(db, factory_id):
        if plan.get("factory_id") != factory_id or plan.get("status") not in {"ACTIVE", "PENDING_WAREHOUSE"}:
            continue
        if not any(term in " ".join(str(target.get(key) or "") for key in ("contract_no", "customer_po")).casefold()
                   for target in plan.get("targets", [])):
            continue
        identity = tuple(str(plan.get(key) or "") for key in ("order_id", "order_no", "customer_code", "item_no"))
        if all(identity):
            identities.add(identity)
    if not identities:
        return false()
    return and_(CartonOrder.status != "CANCELLED", tuple_(
        CartonOrder.id, CartonOrder.order_no, CartonOrder.customer_code, CartonOrder.item_no,
    ).in_(sorted(identities)))
