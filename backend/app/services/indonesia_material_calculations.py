"""Decimal quantities and distinct production/calendar-day planning."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP, localcontext
from functools import wraps
from fastapi import HTTPException

ZERO = Decimal(0)


def precise_decimals(function):
    @wraps(function)
    def calculate(*args, **kwargs):
        # Bounded inputs may multiply three 12-digit values and divide by 1e-8.
        # Keep intermediate precision local to this calculation, including threads.
        with localcontext() as context:
            context.prec = 80
            return function(*args, **kwargs)
    return calculate


def require(condition, message, status=409):
    if not condition:
        raise HTTPException(status, message)


def number(value):
    return Decimal(str(value))


def decimal_text(value):
    return format(number(value), 'f')


def production_plan(quantity, capacity, due, transport_days):
    if capacity is None:
        return None
    days = int((number(quantity) / number(capacity)).to_integral_value(rounding=ROUND_CEILING))
    require(days <= 10000, '生产周期超过 10000 个工作日，请核对数量和日产能', 422)
    start = date.fromisoformat(due)
    remaining = days
    # Delivery is the boundary after production. Subtract complete working days.
    while remaining:
        start -= timedelta(days=1)
        if start.weekday() < 5:
            remaining -= 1
    dispatch = start - timedelta(days=transport_days)
    return dict(production_days=days, start_date=start.isoformat(), dispatch_date=dispatch.isoformat(),
                required_date=dispatch.isoformat(), transport_days=transport_days, preparation_days=0)


@precise_decimals
def packaging_totals(packages, lines):
    """Per package apportionment; physical cartons/CBM counted once, no pallets."""
    packed = {key: [ZERO, ZERO] for key in lines}
    totals = {key: dict(net=ZERO, carton=ZERO, cbm=ZERO) for key in lines}
    cartons = 0
    cbm = ZERO
    groups = []
    for group in packages:
        quantity_by_line = {}
        for item in group['items']:
            key = item['allocation_id']
            require(key in lines, '装箱物料必须来自本次选中的出货明细', 422)
            require(key not in quantity_by_line, '同包装组不能重复选择同一分配行', 422)
            normal, spare = number(item['normal_quantity']), number(item['spare_quantity'])
            require(normal + spare > 0, '包装组的实装数量必须大于零', 422)
            packed[key][0] += normal
            packed[key][1] += spare
            weight = lines[key]['material'].get('net_weight_kg')
            require(weight is not None and number(weight) > 0, '请补齐物料单件净重（kg），不能以零重量计算', 422)
            quantity_by_line[key] = (normal + spare) * number(weight)
        weight_sum = sum(quantity_by_line.values(), ZERO)
        box_weight = number(group['carton_weight_kg']) * group['cartons']
        volume = number(group['length_cm']) * number(group['width_cm']) * number(group['height_cm']) / Decimal('28316.75') * Decimal('0.0283')
        group_cbm = (volume * group['cartons']).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
        cartons += group['cartons']
        cbm += group_cbm
        for key, weight in quantity_by_line.items():
            totals[key]['net'] += weight
            totals[key]['carton'] += box_weight * weight / weight_sum
            totals[key]['cbm'] += group_cbm * weight / weight_sum
        groups.append(dict(**group, single_cbm=decimal_text(volume), total_cbm=decimal_text(group_cbm)))
    for key, line in lines.items():
        require(packed[key] == [number(line['normal_quantity']), number(line['spare_quantity'])],
                '装箱正常量及备品量必须分别等于本次出货数量', 422)
    return dict(cartons=cartons, cbm=decimal_text(cbm), groups=groups,
                lines={key: dict(net_weight_kg=decimal_text(v['net']),
                                gross_weight_kg=decimal_text(v['net'] + v['carton']),
                                carton_weight_kg=decimal_text(v['carton']), cbm=decimal_text(v['cbm']))
                       for key, v in totals.items()})
