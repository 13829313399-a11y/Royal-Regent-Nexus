from decimal import Decimal as D
from types import SimpleNamespace as Obj

from test_carton_inventory_valuation import movement, events_for
from app.services.carton_inventory_valuation import value_movements, cost_key
from app.services.carton_inventory_identity import inventory_key
from app.services import carton_inventory_money as display


def test_unknown_source_cancel_does_not_hide_known_receipt_or_remaining_pool():
    rows = [movement('a', '10', '2'), movement('b', '5', '0'), movement('c', '2', '3'),
            movement('d', '-5', '0', reversal_of_movement_id='b')]
    value = value_movements(rows, events_for(rows))
    assert value.unpriced_movements == {'b', 'd'}
    assert not value.unpriced_pools
    assert not value.missing
    assert value.balances[cost_key(rows[0])].amount == 26


def test_unknown_consumption_and_reversal_propagate_until_clean_depletion():
    rows = [movement('a', '5', '0'), movement('b', '-2', '0'),
            movement('c', '2', '0', reversal_of_movement_id='b'),
            movement('d', '-5', '0'), movement('e', '4', '3')]
    value = value_movements(rows, events_for(rows))
    assert value.unpriced_movements == {'a', 'b', 'c', 'd'}
    assert not value.unpriced_pools
    assert value.balances[cost_key(rows[0])].amount == 12


def annotate(monkeypatch, rows, quantities):
    value = value_movements(rows, events_for(rows))
    monkeypatch.setattr(display, 'projection', lambda *_: (rows, value))
    positions = [Obj(inventory_key=inventory_key(rows[0]), position_key=str(i), balance=D(q), cost_amount=None)
                 for i, q in enumerate(quantities)]
    return display.annotate_balances(None, 'huaxing', positions)


def test_tiny_split_stock_allocates_cents_without_negative_last_bin(monkeypatch):
    positions = annotate(monkeypatch, [movement('a', '4', '0.006')], ['1'] * 4)
    assert [p.cost_amount for p in positions] == [D('0.01'), D('0.01'), 0, 0]
    assert sum(p.cost_amount for p in positions) == D('0.02')
    assert all(p.cost_status == '已计价' for p in positions)


def test_negative_position_and_currency_ambiguity_never_show_normal_amount(monkeypatch):
    for rows, quantities in [([movement('a', '4', '2')], ['5', '-1']),
                             ([movement('a', '2', '2'), movement('b', '2', '3', currency='HKD')], ['4'])]:
        positions = annotate(monkeypatch, rows, quantities)
        assert all(p.cost_status == '待核算' and p.cost_amount is None for p in positions)


def test_unknown_price_does_not_become_zero_money(monkeypatch):
    positions = annotate(monkeypatch, [movement('a', '5', '0')], ['5'])
    assert positions[0].cost_status == '待核价'
    assert positions[0].cost_amount is None


def test_movement_display_reconstructs_legacy_outbound_cost_from_full_history(monkeypatch):
    rows = [movement('a', '10', '2'), movement('b', '10', '4'), movement('c', '-5', '0')]
    monkeypatch.setattr(display, 'projection', lambda *_: (rows, value_movements(rows, events_for(rows))))
    item = Obj(id='c')
    display.annotate_movements(None, 'huaxing', [item])
    assert item.cost_amount == -15
    assert item.cost_unit_price == 3
    assert item.cost_currency == 'CNY'
    assert rows[-1].unit_price == 0
