from datetime import date
from decimal import Decimal

import pytest

from app.services.shipping_schedule import (
    ContainerCargo,
    ContainerSlot,
    ShippingRuleError,
    TruckCargo,
    TruckPlan,
    can_enter_shipment,
    can_transition,
    parse_schedule_date,
    plan_container_split,
    plan_warehouse_trips,
    readiness_warnings,
    resolve_planned_ship_date,
    truck_type_format_error,
    validate_warehouse_trips,
)

D = Decimal


@pytest.mark.parametrize(
    ('text', 'expected'),
    [
        ('2026-03-05', date(2026, 3, 5)),
        ('2026-03-05T17:00', date(2026, 3, 5)),
        ('2026/3/5 17:00', date(2026, 3, 5)),
        ('3/5/2026', date(2026, 3, 5)),
        ('2026年3月5日', date(2026, 3, 5)),
        ('5-Mar-2026', date(2026, 3, 5)),
        ('Mar 5, 2026', date(2026, 3, 5)),
        ('', None),
        (None, None),
        ('时间待定', None),
        ('13/45/2026', None),
    ],
)
def test_parse_schedule_date(text, expected):
    assert parse_schedule_date(text) == expected


def test_parse_schedule_date_uses_fallback_year_for_short_forms():
    assert parse_schedule_date('3/5', fallback_year=2025) == date(2025, 3, 5)
    assert parse_schedule_date('3月5日', fallback_year=2024) == date(2024, 3, 5)


def test_parse_schedule_date_does_not_take_year_from_next_token():
    # 2026-03-05 已带年，短日期规则不能把它解析成别的年份。
    assert parse_schedule_date('2026-03-05', fallback_year=2020) == date(2026, 3, 5)


def test_resolve_prefers_explicit_ship_date():
    assert resolve_planned_ship_date(
        ship_date='2026-03-08', cutoff_date='2026-03-06', si_deadline='2026-03-04',
    ) == date(2026, 3, 8)


def test_resolve_falls_back_to_cutoff_minus_one_day():
    assert resolve_planned_ship_date(cutoff_date='2026-03-06', si_deadline='2026-03-04') == date(2026, 3, 5)


def test_resolve_falls_back_to_si_minus_one_day():
    assert resolve_planned_ship_date(si_deadline='2026-03-04') == date(2026, 3, 3)


def test_resolve_returns_none_when_waiting_for_notification():
    assert resolve_planned_ship_date() is None


def test_resolve_uses_received_year_for_short_dates():
    assert resolve_planned_ship_date(ship_date='3/5', received_at='2025-12-30T10:00:00+08:00') == date(2025, 3, 5)


def test_resolve_without_received_at_uses_current_year():
    resolved = resolve_planned_ship_date(ship_date='3/5')
    assert resolved is not None and resolved.month == 3 and resolved.day == 5


@pytest.mark.parametrize(
    ('current', 'next_status', 'allowed'),
    [
        ('waiting', 'review', True),
        ('waiting', 'cancelled', True),
        ('waiting', 'shipment', False),
        ('review', 'shipment', True),
        ('review', 'cancelled', True),
        ('shipment', 'review', True),
        ('shipment', 'completed', True),
        ('shipment', 'cancelled', True),
        ('completed', 'shipment', False),
        ('cancelled', 'review', False),
        ('unknown', 'review', False),
    ],
)
def test_can_transition(current, next_status, allowed):
    assert can_transition(current, next_status) is allowed


def test_shipment_needs_a_planned_date():
    assert can_enter_shipment(date(2026, 3, 5)) is True
    assert can_enter_shipment(None) is False


@pytest.mark.parametrize(
    ('inventory', 'inspection', 'expected'),
    [
        (True, True, ()),
        (False, True, ('库存未确认',)),
        (True, False, ('验货未确认',)),
        (False, False, ('库存未确认', '验货未确认')),
    ],
)
def test_readiness_warnings_only_advise(inventory, inspection, expected):
    assert readiness_warnings(inventory_confirmed=inventory, inspection_confirmed=inspection) == expected


def test_plan_warehouse_trips_splits_on_cap():
    plans = plan_warehouse_trips(
        [TruckCargo('a', D('20')), TruckCargo('b', D('20'))], warehouse='裕泰仓',
    )
    assert [(plan.key, plan.cargo_keys, plan.cbm) for plan in plans] == [
        ('1', ('a',), D('20')),
        ('2', ('b',), D('20')),
    ]


def test_plan_warehouse_trips_keeps_exact_cap_in_one_truck():
    plans = plan_warehouse_trips([TruckCargo('a', D('20')), TruckCargo('b', D('15'))])
    assert len(plans) == 1 and plans[0].cbm == D('35')


def test_plan_warehouse_trips_refuses_single_line_over_cap():
    with pytest.raises(ShippingRuleError, match='超过 35 CBM 上限'):
        plan_warehouse_trips([TruckCargo('a', D('36'))])


def test_plan_warehouse_trips_keeps_packing_group_together():
    plans = plan_warehouse_trips([
        TruckCargo('a', D('10'), packing_group='g1'),
        TruckCargo('b', D('10'), packing_group='g1'),
        TruckCargo('c', D('20')),
    ])
    assert [plan.cargo_keys for plan in plans] == [('a', 'b'), ('c',)]


def test_plan_warehouse_trips_refuses_packing_group_over_cap():
    with pytest.raises(ShippingRuleError, match='g1'):
        plan_warehouse_trips([
            TruckCargo('a', D('20'), packing_group='g1'),
            TruckCargo('b', D('20'), packing_group='g1'),
        ])


def test_plan_warehouse_trips_refuses_empty_cargo():
    with pytest.raises(ShippingRuleError, match='没有可分车的货物'):
        plan_warehouse_trips([])


def _valid_plan() -> tuple[list[TruckCargo], list[TruckPlan]]:
    cargo = [TruckCargo('a', D('20')), TruckCargo('b', D('10'))]
    plan = [TruckPlan('1', '裕泰仓', ('a', 'b'), D('30'), '1*3T')]
    return cargo, plan


def test_validate_accepts_a_balanced_plan():
    cargo, plan = _valid_plan()
    validate_warehouse_trips(cargo, plan)


def test_validate_refuses_unallocated_cargo():
    cargo, plan = _valid_plan()
    with pytest.raises(ShippingRuleError, match='尚未分车'):
        validate_warehouse_trips(cargo, [TruckPlan('1', '裕泰仓', ('a',), D('20'), '1*3T')])


def test_validate_refuses_duplicate_assignment():
    cargo, _ = _valid_plan()
    plans = [
        TruckPlan('1', '裕泰仓', ('a',), D('20'), '1*3T'),
        TruckPlan('2', '裕泰仓', ('a', 'b'), D('30'), '1*3T'),
    ]
    with pytest.raises(ShippingRuleError, match='重复分到'):
        validate_warehouse_trips(cargo, plans)


def test_validate_refuses_cbm_mismatch():
    cargo, _ = _valid_plan()
    plans = [TruckPlan('1', '裕泰仓', ('a', 'b'), D('31'), '1*3T')]
    with pytest.raises(ShippingRuleError, match='不一致'):
        validate_warehouse_trips(cargo, plans)


def test_validate_refuses_over_cap():
    cargo = [TruckCargo('a', D('40'))]
    plans = [TruckPlan('1', '裕泰仓', ('a',), D('40'), '1*3T')]
    with pytest.raises(ShippingRuleError, match='超过 35 CBM 上限'):
        validate_warehouse_trips(cargo, plans)


def test_validate_refuses_blank_or_unconfirmed_warehouse():
    cargo, plan = _valid_plan()
    with pytest.raises(ShippingRuleError, match='交仓仓库'):
        validate_warehouse_trips(cargo, [TruckPlan('1', '', ('a', 'b'), D('30'), '1*3T')])
    with pytest.raises(ShippingRuleError, match='交仓仓库'):
        validate_warehouse_trips(cargo, [TruckPlan('1', '待确认仓库', ('a', 'b'), D('30'), '1*3T')])


def test_validate_refuses_split_packing_group():
    cargo = [
        TruckCargo('a', D('10'), packing_group='g1'),
        TruckCargo('b', D('10'), packing_group='g1'),
    ]
    plans = [
        TruckPlan('1', '裕泰仓', ('a',), D('10'), '1*3T'),
        TruckPlan('2', '裕泰仓', ('b',), D('10'), '1*3T'),
    ]
    with pytest.raises(ShippingRuleError, match='混装组 g1'):
        validate_warehouse_trips(cargo, plans)


def test_validate_refuses_large_truck_without_vehicle():
    cargo = [TruckCargo('a', D('55'))]
    plans = [TruckPlan('1', '外仓', ('a',), D('55'))]
    with pytest.raises(ShippingRuleError, match='人工填写吨车'):
        validate_warehouse_trips(cargo, plans, max_cbm=None)


def test_validate_accepts_large_truck_with_vehicle():
    cargo = [TruckCargo('a', D('55'))]
    plans = [TruckPlan('1', '外仓', ('a',), D('55'), '1*12T')]
    validate_warehouse_trips(cargo, plans, max_cbm=None)


def test_validate_refuses_empty_plan_or_empty_truck():
    cargo, _ = _valid_plan()
    with pytest.raises(ShippingRuleError, match='不能为空'):
        validate_warehouse_trips(cargo, [])
    with pytest.raises(ShippingRuleError, match='没有货物'):
        validate_warehouse_trips(cargo, [TruckPlan('1', '裕泰仓', (), D('0'), '1*3T')])


@pytest.mark.parametrize(
    ('vehicle', 'valid'),
    [('3T', True), ('1*3T', True), ('3吨', True), ('3吨车', True), ('1*12.5T', True),
     ('0T', False), ('三吨', False), ('3', False), ('', False)],
)
def test_truck_type_format(vehicle, valid):
    assert (truck_type_format_error(vehicle) is None) is valid


def _slots(count: int, capacity: int = 0) -> list[ContainerSlot]:
    return [ContainerSlot(f'c{index}', f'SO{index}', '40HQ', capacity) for index in range(1, count + 1)]


def _totals(loads) -> dict:
    totals: dict[str, int] = {}
    for load in loads:
        totals[load.container_key] = totals.get(load.container_key, 0) + load.boxes
    return totals


def test_container_split_evenly():
    loads = plan_container_split([ContainerCargo('a', 10)], _slots(2))
    assert _totals(loads) == {'c1': 5, 'c2': 5}


def test_container_split_remainder_goes_to_first_cabins():
    loads = plan_container_split([ContainerCargo('a', 11)], _slots(3))
    assert _totals(loads) == {'c1': 4, 'c2': 4, 'c3': 3}


def test_container_split_is_proportional_to_capacity():
    slots = [ContainerSlot('c1', 'SO1', '40HQ', 100), ContainerSlot('c2', 'SO2', '20GP', 50)]
    loads = plan_container_split([ContainerCargo('a', 90)], slots)
    assert _totals(loads) == {'c1': 60, 'c2': 30}


def test_container_split_keeps_same_sku_consecutive():
    loads = plan_container_split(
        [ContainerCargo('b', 10, 'B-001'), ContainerCargo('a', 30, 'A-001')], _slots(2),
    )
    assert [(load.cargo_key, load.container_key, load.boxes) for load in loads] == [
        ('a', 'c1', 20), ('a', 'c2', 10), ('b', 'c2', 10),
    ]


def test_container_split_refuses_insufficient_capacity():
    slots = [ContainerSlot('c1', 'SO1', '40HQ', 10), ContainerSlot('c2', 'SO2', '40HQ', 10)]
    with pytest.raises(ShippingRuleError, match='柜容量不足'):
        plan_container_split([ContainerCargo('a', 30)], slots)


def test_container_split_refuses_partial_capacity_input():
    slots = [ContainerSlot('c1', 'SO1', '40HQ', 100), ContainerSlot('c2', 'SO2', '40HQ', 0)]
    with pytest.raises(ShippingRuleError, match='补齐所有柜容量'):
        plan_container_split([ContainerCargo('a', 50)], slots)


def test_container_split_refuses_invalid_slot_count():
    with pytest.raises(ShippingRuleError, match='2 至 100'):
        plan_container_split([ContainerCargo('a', 10)], _slots(1))


def test_container_split_refuses_missing_so():
    slots = _slots(2)
    slots[1] = ContainerSlot('c2', '  ', '40HQ')
    with pytest.raises(ShippingRuleError, match='缺少 SO'):
        plan_container_split([ContainerCargo('a', 10)], slots)


@pytest.mark.parametrize('boxes', [0, -1, 1.5, True])
def test_container_split_refuses_invalid_boxes(boxes):
    with pytest.raises(ShippingRuleError, match='正整数'):
        plan_container_split([ContainerCargo('a', boxes)], _slots(2))


def test_container_split_refuses_fewer_boxes_than_cabins():
    with pytest.raises(ShippingRuleError, match='总箱数少于柜数'):
        plan_container_split([ContainerCargo('a', 1)], _slots(2))
