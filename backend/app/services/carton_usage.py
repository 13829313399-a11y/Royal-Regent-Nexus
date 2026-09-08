"""Current issue status derived from typed movements, independently of procurement status."""
from collections import defaultdict
from decimal import Decimal
from sqlalchemy import select
from app.models.carton_procurement import CartonInventoryMovement
from app.services.carton_positions import inventory_key

LABELS = {"NOT_RECEIVED": "未入库", "UNUSED": "未领用", "PARTIAL": "部分领用",
          "EXHAUSTED": "当前已领完", "CLEARED": "库存已结清", "UNKNOWN": "领用待核实"}


def usage_by_key(db, factory):
    rows = list(db.scalars(select(CartonInventoryMovement).where(CartonInventoryMovement.factory_id == factory)))
    by_id = {row.id: row for row in rows}
    groups = defaultdict(lambda: {"balance": Decimal(0), "usage": Decimal(0), "other": Decimal(0), "unknown": Decimal(0)})
    for row in rows:
        data = groups[inventory_key(row)]
        data["balance"] += row.quantity
        original = by_id.get(row.reversal_of_movement_id, row)
        if original.movement_type == "OUTBOUND":
            field = "usage" if original.issue_kind == "USAGE" else "other"
            data[field] -= row.quantity
            if original.issue_kind == "UNKNOWN" and original.source_type != "ORDER_RETURN":
                data["unknown"] -= row.quantity
        elif original.movement_type == "ADJUSTMENT" and original.quantity < 0:
            data["other"] -= row.quantity
    result = {}
    for key, data in groups.items():
        if data["unknown"] != 0 or data["balance"] < 0 or data["usage"] < 0:
            status = "UNKNOWN"
        elif data["balance"] > 0:
            status = "PARTIAL" if data["usage"] > 0 else "UNUSED"
        elif data["other"] > 0:
            status = "CLEARED"
        elif data["usage"] > 0:
            status = "EXHAUSTED"
        else:
            status = "NOT_RECEIVED"
        result[key] = {**data, "status": status, "label": LABELS[status]}
    return result


def aggregate_status(states, total_usage=Decimal(0)):
    states = set(states)
    if "UNKNOWN" in states: return "UNKNOWN"
    if not states or states <= {"NOT_RECEIVED"}: return "NOT_RECEIVED"
    if states.intersection({"UNUSED", "PARTIAL"}):
        return "PARTIAL" if total_usage > 0 or "PARTIAL" in states or "EXHAUSTED" in states else "UNUSED"
    if states <= {"NOT_RECEIVED", "CLEARED", "EXHAUSTED"}:
        return "CLEARED" if "CLEARED" in states else "EXHAUSTED"
    return "PARTIAL"
