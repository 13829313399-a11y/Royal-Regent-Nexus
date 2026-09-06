from datetime import datetime, timedelta
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")
D = Decimal


def decimal(value, default=None):
    if value is None or value == "" or isinstance(value, bool):
        return default
    try:
        result = D(str(value))
        return result if result.is_finite() else default
    except (InvalidOperation, ValueError):
        return default


def timestamp(value):
    if value is None or value == "":
        return None
    dt = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    )
    return dt.replace(tzinfo=TZ) if dt.tzinfo is None else dt.astimezone(TZ)


def now():
    return datetime.now(TZ)


def quantities(data, reported_shots=0, good_units=0):
    planned = decimal(data.get("planned_shots"))
    opening = decimal(data.get("opening_shots"), D(0))
    completed = opening + decimal(reported_shots, D(0))
    adjustment = decimal(data.get("adjustment_shots"), D(0))
    signed = None if planned is None else planned + adjustment - completed
    remaining = None if signed is None else max(D(0), signed)
    mode = data.get("allocation_mode", "SEQUENTIAL_SHOTS")
    units = decimal(data.get("required_units"))
    remaining_units = None
    if mode == "CO_OUTPUT_UNITS":
        remaining_units = (
            max(D(0), units - decimal(good_units, D(0))) if units is not None else None
        )
        outputs = decimal(data.get("effective_outputs_per_shot"))
        remaining = (
            (remaining_units / outputs).to_integral_value(rounding=ROUND_CEILING)
            if remaining_units is not None and outputs and outputs > 0
            else None
        )
    rate = decimal(data.get("target_shots_per_day"))
    basis = decimal(data.get("target_basis_hours"), D(24))
    hourly = rate / basis if rate and rate > 0 and basis and basis > 0 else None
    weight = decimal(data.get("net_weight_g"))
    price = decimal(data.get("price_per_shot"))
    allowance = decimal(data.get("allowance_rate"), D("0.01"))
    return {
        "completed_shots": completed,
        "signed_remaining_shots": signed,
        "remaining_shots": remaining,
        "overproduced_shots": max(D(0), -signed) if signed is not None else D(0),
        "good_units": decimal(good_units, D(0)),
        "remaining_units": remaining_units,
        "shots_per_hour": hourly,
        "production_duration_hours": remaining / hourly
        if remaining is not None and hourly
        else None,
        "remaining_material_kg": remaining * weight / 1000 * (1 + allowance)
        if remaining is not None and weight is not None
        else None,
        "remaining_processing_amount": remaining * price
        if remaining is not None and price is not None
        else None,
    }


def shots_for_units(sets, pieces, outputs):
    if decimal(outputs, D(0)) <= 0:
        raise ValueError("每啤出件必须大于零")
    return (D(str(sets)) * D(str(pieces)) / D(str(outputs))).to_integral_value(
        rounding=ROUND_CEILING
    )


def co_output_shots(items):
    return max(
        (
            shots_for_units(x["remaining_units"], 1, x["outputs_per_shot"])
            for x in items
        ),
        default=D(0),
    )


def remaining_for_group(demands):
    if not demands:
        return D(0)
    if demands[0].get("allocation_mode") != "CO_OUTPUT_UNITS":
        return sum((decimal(d.get("remaining_shots"), D(0)) for d in demands), D(0))
    products = {}
    for demand in demands:
        product = demand.get("item_no") or demand.get("mold_code")
        units, outputs = products.get(
            product, (D(0), decimal(demand.get("effective_outputs_per_shot"), D(1)))
        )
        products[product] = (
            units + decimal(demand.get("remaining_units"), D(0)),
            outputs,
        )
    return max(
        (shots_for_units(units, 1, outputs) for units, outputs in products.values()),
        default=D(0),
    )


def sequential_allocate(physical_shots, remaining):
    left = D(str(physical_shots))
    allocations = []
    for qty in remaining:
        assigned = min(left, max(D(0), D(str(qty))))
        allocations.append(assigned)
        left -= assigned
    return allocations, left


def delivery(end, due, lead_days=3):
    ready = timestamp(end) + timedelta(days=float(lead_days))
    return ready, (timestamp(due) - ready).total_seconds() / 3600 if due else None
