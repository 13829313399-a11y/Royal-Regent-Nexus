"""Pure projections: SPECIAL replacement costs never become new purchase prices."""
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest

from app.services.carton_inventory_valuation import cost_key, value_movements


def movement(identifier, qty, price, **values):
    data = dict(id=identifier, factory_id="huaxing", order_line_id=None, customer_code="__SAMPLE__",
                contract_no="", item_no="SAMPLE-1", packaging_type="外箱", paper_quality="A33",
                specification="1x1x1 cm", unit="个", currency="CNY", quantity=D(qty), unit_price=D(price),
                source_type="RECEIPT", source_id="receipt-" + identifier, source_line_id="line-" + identifier,
                movement_type="INBOUND" if D(qty) > 0 else "OUTBOUND", reversal_of_movement_id=None,
                occurred_at="2026-10-21T09:00:00+08:00")
    data.update(values)
    return SimpleNamespace(**data)


def event(sequence, kind, identifier, data=None):
    return SimpleNamespace(sequence=sequence, event_type=kind, entity_id=identifier, factory_id="huaxing",
                           detail_json=json.dumps(data or {}))


def posted(sequence, row):
    return event(sequence, "INVENTORY_MOVEMENT_CREATED", row.id)


def link(sequence, row, source, *, amount="20", quantity="10", **values):
    data = dict(responsibility="SUPPLIER", child_request_id=source.source_id, parent_request_id="parent",
                source_movement_ids=[source.id], source_quantity=quantity, inventory_amount=amount,
                inventory_unit_price=str(row.unit_price), settlement_unit_price="0", quantity=str(row.quantity),
                receipt_id=row.source_id)
    data.update(values)
    return event(sequence, "SPECIAL_RECEIPT_REPLENISHMENT_LINKED", row.source_line_id, data)


def baseline(*, quantity="10", price="2", replacement_quantity=None, replacement_price=None):
    original = movement("original", quantity, price)
    debit = movement("debit", str(-D(quantity)), price, source_type="SPECIAL_REPLENISHMENT", source_id="child")
    replacement = movement("replacement", replacement_quantity or quantity, replacement_price or price)
    rows = [original, debit, replacement]
    events = [posted(1, original), posted(2, debit), link(3, replacement, debit,
              amount=str(D(quantity) * D(price)), quantity=quantity), posted(4, replacement)]
    return rows, events


def test_restores_exact_amount_instead_of_rounded_display_price():
    first = movement("first", "1", "1")
    second = movement("second", "2", "2")
    debit = movement("debit", "-3", "1.666667", source_type="SPECIAL_REPLENISHMENT", source_id="child")
    replacement = movement("replacement", "3", "1.666667")
    rows = [first, second, debit, replacement]
    evidence = [posted(1, first), posted(2, second), posted(3, debit),
                link(4, replacement, debit, amount="5", quantity="3"), posted(5, replacement)]
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[debit.id] == -5
    assert result.amounts[replacement.id] == 5
    assert result.balances[cost_key(first)].amount == 5
    assert replacement.unit_price == D("1.666667")
    assert json.loads(evidence[3].detail_json)["inventory_amount"] == "5"


def test_correction_before_link_is_already_frozen_and_not_applied_twice():
    rows, evidence = baseline(replacement_price="3")
    evidence[2] = link(4, rows[2], rows[1], amount="30")
    evidence[3] = posted(5, rows[2])
    evidence.append(event(3, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"}))
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 30
    assert rows[0].unit_price == 2


def test_later_correction_propagates_only_delta_after_link():
    rows, evidence = baseline()
    frozen = evidence[2].detail_json
    evidence.append(event(5, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"}))
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 30
    assert rows[2].unit_price == 2
    assert evidence[2].detail_json == frozen


def test_corrections_before_and_after_link_do_not_double_count():
    rows, evidence = baseline(replacement_price="3")
    evidence[2] = link(4, rows[2], rows[1], amount="30")
    evidence[3] = posted(5, rows[2])
    evidence += [event(3, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"}),
                 event(6, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "4"})]
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 40


def test_partial_receipts_freeze_independently_across_a_correction():
    rows, evidence = baseline(replacement_quantity="3")
    later = movement("later", "7", "3")
    rows.append(later)
    evidence += [event(5, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"}),
                 link(6, later, rows[1], amount="30"), posted(7, later)]
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 9
    assert result.amounts[later.id] == 21
    assert result.balances[cost_key(later)].amount == 30


def test_later_correction_propagates_through_multiple_replacement_generations():
    rows, evidence = baseline()
    second_debit = movement("second-debit", "-10", "2", source_type="SPECIAL_REPLENISHMENT", source_id="second-child")
    second_receipt = movement("second-receipt", "10", "2")
    rows += [second_debit, second_receipt]
    evidence += [posted(5, second_debit), link(6, second_receipt, second_debit), posted(7, second_receipt),
                 event(8, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"})]
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 30
    assert result.amounts[second_debit.id] == -30
    assert result.amounts[second_receipt.id] == 30
    assert result.balances[cost_key(rows[0])].amount == 30


def test_own_responsibility_keeps_actual_receipt_cost():
    rows, evidence = baseline(replacement_price="5")
    evidence[2] = link(3, rows[2], rows[1], responsibility="OWN", settlement_unit_price="5")
    evidence.append(event(5, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "3"}))
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.amounts[rows[2].id] == 50


@pytest.mark.parametrize("changes", [
    {"source_movement_ids": []}, {"source_movement_ids": ["missing"]},
    {"source_movement_ids": ["debit", "debit"]}, {"child_request_id": "different"},
    {"source_quantity": "9"}, {"source_quantity": "NaN"}, {"inventory_amount": "NaN"},
    {"inventory_amount": "-1"}, {"inventory_amount": "21"}, {"quantity": "9"},
    {"receipt_id": "other"}, {"settlement_unit_price": "1"}, {"responsibility": "UNKNOWN"},
])
def test_inconsistent_evidence_blocks_instead_of_inventing_cost(changes):
    rows, evidence = baseline()
    evidence[2] = link(3, rows[2], rows[1], **changes)
    assert any(row.id == rows[2].id for row, _ in value_movements(rows, evidence).errors)


@pytest.mark.parametrize("changes", [
    {"factory_id": "huadeng"}, {"currency": "HKD"}, {"unit": "张"},
    {"paper_quality": "OTHER"}, {"source_type": "MANUAL"}, {"movement_type": "ADJUSTMENT"},
])
def test_source_identity_or_domain_mismatch_is_a_blocker(changes):
    rows, evidence = baseline()
    for key, value in changes.items():
        setattr(rows[1], key, value)
    assert value_movements(rows, evidence).errors


def test_duplicate_link_and_malformed_json_are_blockers():
    rows, evidence = baseline()
    duplicate = link(5, rows[2], rows[1])
    assert value_movements(rows, evidence + [duplicate]).errors
    duplicate.detail_json = "{broken"
    assert value_movements(rows, evidence[:2] + [duplicate] + evidence[3:]).errors


def test_missing_source_cost_stays_unpriced_even_after_later_confirmation():
    rows, evidence = baseline(price="0")
    assert value_movements(rows, evidence).errors
    evidence.append(event(5, "INVENTORY_PRICE_CORRECTED", rows[0].id, {"unit_price": "2"}))
    assert value_movements(rows, evidence).errors


def test_confirmed_zero_cost_can_be_restored_without_inventing_missing_price():
    rows, evidence = baseline(price="0")
    evidence.append(event(1, "INVENTORY_PRICE_CONFIRMED", rows[0].id, {"unit_price": "0"}))
    result = value_movements(rows, evidence)
    assert not result.errors
    assert not result.unpriced_pools
    assert not result.missing
    assert result.amounts[rows[2].id] == 0


def test_active_receipts_cannot_use_the_same_debit_quota_twice():
    rows, evidence = baseline()
    another = movement("another", "1", "2")
    rows.append(another)
    evidence += [link(5, another, rows[1]), posted(6, another)]
    assert value_movements(rows, evidence).errors


def test_reversed_receipt_does_not_consume_active_quota_twice_on_reentry():
    rows, evidence = baseline()
    reversal = movement("reverse", "-10", "2", movement_type="REVERSAL", source_type="REVERSAL",
                        reversal_of_movement_id=rows[2].id)
    another = movement("another", "10", "2")
    rows += [reversal, another]
    evidence += [event(5, "INVENTORY_MOVEMENT_REVERSED", rows[2].id, {"reversal_id": reversal.id}),
                 link(6, another, rows[1]), posted(7, another)]
    result = value_movements(rows, evidence)
    assert not result.errors
    assert result.balances[cost_key(another)].amount == 20


def test_source_posted_after_link_cannot_restore_cost():
    rows, evidence = baseline()
    evidence[1] = posted(5, rows[1])
    assert value_movements(rows, evidence).errors


def test_child_before_its_original_debit_is_blocked_even_with_a_link():
    rows, evidence = baseline()
    rows[1].occurred_at = "2026-10-22T09:00:00+08:00"
    assert value_movements(rows, evidence).errors
