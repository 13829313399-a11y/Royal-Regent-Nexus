"""Shipping schedule rules: planned dates, warehouse truck split, container split and task states.

Pure functions only. The caller owns persistence, permissions and factory scope; these
rules decide what a valid schedule is and refuse to guess when the input is incomplete.
"""
import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Sequence

# 交仓单车体积上限：裕泰仓现网口径，与前端示例数据的 35 CBM 一致。
DEFAULT_TRUCK_CAP_CBM = Decimal('35')
# 超过该体积且未指定吨车时，必须人工确认车型，不能自动推荐。
MANUAL_TRUCK_CBM = Decimal('50')
# 只容忍数值序列化误差，不放宽业务上限。
CBM_TOLERANCE = Decimal('0.000001')

_MONTH_NAMES = {
    'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
    'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12,
}
_ISO_DATE = re.compile(r'(?P<y>20\d{2})[-/.](?P<m>\d{1,2})[-/.](?P<d>\d{1,2})')
_SLASH_DATE = re.compile(r'(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>20\d{2})')
_CN_DATE = re.compile(r'(?:(?P<y>20\d{2})\s*年\s*)?(?P<m>\d{1,2})\s*月\s*(?P<d>\d{1,2})(?!\d)\s*日?')
_DAY_MONTH_YEAR = re.compile(r'(?P<d>\d{1,2})[-\s](?P<name>[A-Za-z]{3,9})(?:[-\s](?P<y>20\d{2}))?')
_MONTH_DAY_YEAR = re.compile(r'(?P<name>[A-Za-z]{3,9})\s+(?P<d>\d{1,2})(?:,?\s+(?P<y>20\d{2}))?')
_SHORT_DATE = re.compile(r'(?P<m>\d{1,2})[-/.](?P<d>\d{1,2})(?!\d)')
_TRUCK_TYPE = re.compile(r'^(?:[1-9]\d*\s*[*x×]\s*)?[1-9]\d*(?:\.\d+)?\s*(?:T|吨(?:车)?)$', re.IGNORECASE)

TASK_STATUSES = ('waiting', 'review', 'shipment', 'completed', 'cancelled')
TASK_STATUS_LABELS = {
    'waiting': '待通知', 'review': '待复核', 'shipment': '待出货',
    'completed': '已完成', 'cancelled': '已取消',
}
_STATUS_TRANSITIONS = {
    'waiting': ('review', 'cancelled'),
    'review': ('shipment', 'cancelled'),
    'shipment': ('review', 'completed', 'cancelled'),
    'completed': (),
    'cancelled': (),
}


class ShippingRuleError(ValueError):
    """A schedule input that cannot be turned into a valid plan without human review."""


def parse_schedule_date(value, fallback_year: int | None = None) -> date | None:
    """Read the first usable date from free text; returns None instead of guessing.

    The earliest match wins across all formats, so "10 月 26" is not displaced by a
    later "10/28" that belongs to the following line.
    """
    text = str(value or '').strip()
    if not text:
        return None
    year = fallback_year or date.today().year
    best: tuple[tuple[int, int, int], date] | None = None
    for order, pattern in enumerate(
        (_ISO_DATE, _SLASH_DATE, _CN_DATE, _DAY_MONTH_YEAR, _MONTH_DAY_YEAR, _SHORT_DATE)
    ):
        for match in pattern.finditer(text):
            groups = match.groupdict()
            month = _month_of(groups)
            if month is None:
                continue
            parsed = _safe_date(int(groups.get('y') or year), month, int(groups['d']))
            if parsed is None:
                continue
            key = (match.start(), -len(match.group(0)), order)
            if best is None or key < best[0]:
                best = (key, parsed)
    return best[1] if best else None


def resolve_planned_ship_date(
    *,
    ship_date='',
    cutoff_date='',
    si_deadline='',
    received_at='',
) -> date | None:
    """Planned ship date: explicit instruction, else cutoff minus one day, else SI minus one day.

    A message without any usable date, or one that only says 待通知, yields None so the
    task cannot enter 'shipment'.
    """
    year = _received_year(received_at) or date.today().year
    explicit = parse_schedule_date(ship_date, year)
    if explicit is not None:
        return explicit
    for deadline in (cutoff_date, si_deadline):
        parsed = parse_schedule_date(deadline, year)
        if parsed is not None:
            return parsed - timedelta(days=1)
    return None


def can_enter_shipment(planned_ship_date: date | None) -> bool:
    return planned_ship_date is not None


def can_transition(current: str, next_status: str) -> bool:
    return next_status in _STATUS_TRANSITIONS.get(current, ())


def readiness_warnings(*, inventory_confirmed: bool, inspection_confirmed: bool) -> tuple[str, ...]:
    """Readiness is visible but never blocks task creation or worksheet generation."""
    warnings = []
    if not inventory_confirmed:
        warnings.append('库存未确认')
    if not inspection_confirmed:
        warnings.append('验货未确认')
    return tuple(warnings)


@dataclass(frozen=True)
class TruckCargo:
    """One shipment line as it enters 交仓分车. `packing_group` rows must stay together."""

    key: str
    cbm: Decimal
    packing_group: str = ''


@dataclass(frozen=True)
class TruckPlan:
    key: str
    warehouse: str
    cargo_keys: tuple[str, ...]
    cbm: Decimal
    vehicle_type: str = ''


@dataclass(frozen=True)
class ContainerCargo:
    key: str
    boxes: int
    product_code: str = ''


@dataclass(frozen=True)
class ContainerSlot:
    key: str
    so_number: str
    container_type: str = ''
    capacity_boxes: int = 0


@dataclass(frozen=True)
class ContainerLoad:
    container_key: str
    cargo_key: str
    boxes: int


def plan_warehouse_trips(
    cargo: Sequence[TruckCargo],
    *,
    max_cbm: Decimal = DEFAULT_TRUCK_CAP_CBM,
    warehouse: str = '',
) -> tuple[TruckPlan, ...]:
    """Greedy 35 CBM proposal that never splits a packing group."""
    _check_unique_keys(cargo, '货物')
    if not cargo:
        raise ShippingRuleError('没有可分车的货物')
    limits = Decimal(max_cbm)
    blocks = _packing_blocks(cargo)
    plans: list[TruckPlan] = []
    current: list[TruckCargo] = []
    current_cbm = Decimal('0')
    for block, block_cbm in blocks:
        if block_cbm > limits:
            label = block[0].packing_group or block[0].key
            raise ShippingRuleError(f'混装组或单行 {label} 体积 {block_cbm} CBM 超过 {limits} CBM 上限，不能自动分车')
        if current and current_cbm + block_cbm > limits:
            plans.append(_truck_plan(len(plans) + 1, warehouse, current, current_cbm))
            current = []
            current_cbm = Decimal('0')
        current.extend(block)
        current_cbm += block_cbm
    if current:
        plans.append(_truck_plan(len(plans) + 1, warehouse, current, current_cbm))
    return tuple(plans)


def validate_warehouse_trips(
    cargo: Sequence[TruckCargo],
    plans: Sequence[TruckPlan],
    *,
    max_cbm: Decimal | None = DEFAULT_TRUCK_CAP_CBM,
    manual_truck_cbm: Decimal = MANUAL_TRUCK_CBM,
) -> None:
    """Reject an unusable 交仓分车 arrangement instead of repairing it silently.

    ``max_cbm`` is the per-truck ceiling for the capped warehouse (35 CBM in current
    use). Pass None for an uncapped warehouse: only an oversized truck then requires an
    explicit vehicle type.
    """
    _check_unique_keys(cargo, '货物')
    by_key = {item.key: item for item in cargo}
    if not plans:
        raise ShippingRuleError('分车安排不能为空')
    _check_unique_keys(plans, '车次')
    limits = None if max_cbm is None else Decimal(max_cbm)
    assigned: dict[str, str] = {}
    for index, plan in enumerate(plans):
        label = f'第{index + 1}车'
        warehouse = (plan.warehouse or '').strip()
        if not warehouse or '待确认' in warehouse:
            raise ShippingRuleError(f'{label}请确认交仓仓库')
        if not plan.cargo_keys:
            raise ShippingRuleError(f'{label}没有货物，请删除空车')
        total = Decimal('0')
        for key in plan.cargo_keys:
            item = by_key.get(key)
            if item is None:
                raise ShippingRuleError(f'{label}引用了不存在的货物 {key}')
            if key in assigned:
                raise ShippingRuleError(f'货物 {key} 被重复分到{assigned[key]}和{label}')
            assigned[key] = label
            if item.cbm < 0:
                raise ShippingRuleError(f'货物 {key} 体积不能为负数')
            total += item.cbm
        if abs(total - Decimal(plan.cbm)) > CBM_TOLERANCE:
            raise ShippingRuleError(f'{label}体积合计 {plan.cbm} 与货物明细 {total} 不一致')
        if limits is not None and total > limits + CBM_TOLERANCE:
            raise ShippingRuleError(f'{label}体积 {total} CBM 超过 {limits} CBM 上限，请调整分车')
        vehicle = (plan.vehicle_type or '').strip()
        if vehicle:
            error = truck_type_format_error(vehicle)
            if error:
                raise ShippingRuleError(f'{label}{error}')
        elif limits is None and total > Decimal(manual_truck_cbm):
            raise ShippingRuleError(f'{label}体积 {total} CBM 超出自动推荐范围，请人工填写吨车')
    missing = [item.key for item in cargo if item.key not in assigned]
    if missing:
        raise ShippingRuleError('货物尚未分车：' + '、'.join(missing))
    for block, _ in _packing_blocks(cargo):
        group = block[0].packing_group
        if not group:
            continue
        places = {assigned[item.key] for item in block if item.key in assigned}
        if len(places) > 1:
            raise ShippingRuleError(f'混装组 {group} 需整组分配到同一车，暂不支持拆行')


def truck_type_format_error(vehicle_type: str) -> str | None:
    value = (vehicle_type or '').strip()
    if not value:
        return '请填写吨车'
    if not _TRUCK_TYPE.match(value):
        return f'吨车格式无效（{value}），例如 1*3T'
    return None


def plan_container_split(
    cargo: Sequence[ContainerCargo],
    slots: Sequence[ContainerSlot],
) -> tuple[ContainerLoad, ...]:
    """Split cartons across cabins: equal by default, proportional when capacities exist."""
    if not 2 <= len(slots) <= 100:
        raise ShippingRuleError('分柜安排需包含 2 至 100 个柜')
    _check_unique_keys(slots, '柜')
    for slot in slots:
        if not str(slot.so_number or '').strip():
            raise ShippingRuleError(f'柜 {slot.key} 缺少 SO 号')
    _check_unique_keys(cargo, '货物')
    if not cargo:
        raise ShippingRuleError('没有可分柜的货物')
    for item in cargo:
        if isinstance(item.boxes, bool) or not isinstance(item.boxes, int) or item.boxes <= 0:
            raise ShippingRuleError(f'货物 {item.key} 的箱数必须是正整数')
    total = sum(item.boxes for item in cargo)
    if total < len(slots):
        raise ShippingRuleError('总箱数少于柜数，请核对分柜安排')
    capacities = [int(slot.capacity_boxes or 0) for slot in slots]
    if any(value < 0 for value in capacities):
        raise ShippingRuleError('柜容量必须为非负整数箱数')
    capped = any(value > 0 for value in capacities)
    if capped and any(value == 0 for value in capacities):
        raise ShippingRuleError('请补齐所有柜容量，或同柜型全部留空按平均分配')
    if capped and sum(capacities) < total:
        raise ShippingRuleError('柜容量不足，请核对总箱数或柜安排')
    targets = _container_targets(total, len(slots), capacities if capped else None)
    remaining = list(targets)
    loads: list[ContainerLoad] = []
    for item in sorted(cargo, key=lambda entry: (entry.product_code, entry.key)):
        left = item.boxes
        while left > 0:
            index = next((i for i, room in enumerate(remaining) if room >= left), None)
            if index is None:
                index = next((i for i, room in enumerate(remaining) if room > 0), None)
            if index is None:
                raise ShippingRuleError('柜容量不足，无法装下全部货物')
            take = min(left, remaining[index])
            loads.append(ContainerLoad(slots[index].key, item.key, take))
            remaining[index] -= take
            left -= take
    for item in cargo:
        loaded = sum(load.boxes for load in loads if load.cargo_key == item.key)
        if loaded != item.boxes:
            raise ShippingRuleError(f'货物 {item.key} 分柜后箱数与原始箱数不一致')
    return tuple(loads)


def _container_targets(total: int, count: int, capacities: list[int] | None) -> list[int]:
    """Equal split with remainder first, or capacity-proportional split rounded up to fit."""
    if capacities is None:
        base, remainder = divmod(total, count)
        return [base + (1 if index < remainder else 0) for index in range(count)]
    weight = sum(capacities)
    targets = [total * capacity // weight for capacity in capacities]
    left = total - sum(targets)
    index = 0
    while left > 0:
        position = index % count
        if targets[position] < capacities[position]:
            targets[position] += 1
            left -= 1
        index += 1
        if index > count * (total + 1):
            raise ShippingRuleError('柜容量不足，无法装下全部货物')
    return targets


def _month_of(groups: dict) -> int | None:
    if groups.get('m'):
        return int(groups['m'])
    name = str(groups.get('name') or '')[:3].upper()
    return _MONTH_NAMES.get(name)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _received_year(received_at) -> int | None:
    match = re.search(r'(20\d{2})', str(received_at or ''))
    return int(match.group(1)) if match else None


def _decimal(value, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ShippingRuleError(f'{label}必须是有效数字') from None
    return parsed


def _check_unique_keys(items: Sequence, label: str) -> None:
    seen = set()
    for item in items:
        if not str(item.key or '').strip():
            raise ShippingRuleError(f'{label}编号不能为空')
        if item.key in seen:
            raise ShippingRuleError(f'{label}编号重复：{item.key}')
        seen.add(item.key)


def _packing_blocks(cargo: Sequence[TruckCargo]) -> list[tuple[list[TruckCargo], Decimal]]:
    blocks: list[tuple[list[TruckCargo], Decimal]] = []
    groups: dict[str, int] = {}
    for item in cargo:
        cbm = _decimal(item.cbm, f'货物 {item.key} 的体积')
        if cbm < 0:
            raise ShippingRuleError(f'货物 {item.key} 体积不能为负数')
        group = (item.packing_group or '').strip()
        if not group:
            blocks.append(([item], cbm))
            continue
        if group not in groups:
            groups[group] = len(blocks)
            blocks.append(([], Decimal('0')))
        index = groups[group]
        blocks[index][0].append(item)
        blocks[index] = (blocks[index][0], blocks[index][1] + cbm)
    return blocks


def _truck_plan(number: int, warehouse: str, cargo: Sequence[TruckCargo], cbm: Decimal) -> TruckPlan:
    return TruckPlan(
        key=str(number),
        warehouse=warehouse,
        cargo_keys=tuple(item.key for item in cargo),
        cbm=cbm,
    )
