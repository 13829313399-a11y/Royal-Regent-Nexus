"""Business regressions for the carton chain audit, using isolated databases."""
import json
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal as D
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from test_carton_inventory_valuation import db, movement, seed, closing, advance, USER, events_for
from test_carton_closing_workflow import clock
from app.models.carton_procurement import (
    CartonOrder, CartonOrderLine, CartonReceipt, CartonReceiptLine, CartonSupplier,
    CartonAuditEvent, CartonException, CartonInventoryMovement,
)
from app.schemas.carton_procurement import (
    CartonOrderUpdate, CartonOrderCancelRequest, CartonOrderBulkCancelRequest,
    CartonOrderAppendRequest, CartonInventoryMovementCreate,
)
from app.services import carton_procurement as ledger, carton_positions as pos
from app.services.carton_inventory_valuation import cost_key, load_valuation
from app.services.carton_inventory_identity import inventory_key, legacy_key


def test_backdated_real_excel_import_cannot_change_a_later_locked_closing(db, monkeypatch):
    from test_carton_procurement_api import _history_inventory_workbook_bytes
    from app.services import carton_procurement_history_inventory as history
    clock(monkeypatch, "2026-09-07")
    seed(db, [movement("a", "10", "2", at="2026-08-01T09:00:00+08:00")])
    locked = advance(db, advance(db, advance(db, closing(db, "2026-08"), "PENDING"), "CONFIRMED"), "LOCKED")
    monkeypatch.setattr(history, "get_active_customer_by_name", lambda *args: SimpleNamespace(customer_code="TEST", customer_name="Test"))
    content = _history_inventory_workbook_bytes([
        ["old", "Test", "", "C", "I", "外箱", "A33", "1x1x1", "个", 5, 2, "CNY", "A", "2026-07-31", "OLD", "期初盘点", None]])
    with pytest.raises(HTTPException, match="2026-08 已锁账"):
        history.import_history_inventory(db, "huaxing", "opening.xlsx", content, USER)
    db.rollback()
    assert len(list(db.scalars(select(CartonInventoryMovement)))) == 1
    assert locked.ending_quantity == 10 and locked.ending_amount == 20
    assert not ledger.closing_out(db, locked).snapshot_stale
    ledger._ensure_period_open(db, "huaxing", "OTHER", "2026-07-31")
    ledger._ensure_period_open(db, "huaxing", "TEST", "2026-09-01")


def test_units_are_frozen_and_equal_total_cross_unit_changes_require_review(db, monkeypatch):
    clock(monkeypatch, "2026-10-01")
    seed(db, [movement("boxes", "10", "2"), movement("sheets", "100", "2", unit="张")])
    row = advance(db, advance(db, closing(db), "PENDING"), "CONFIRMED")
    original = ledger.closing_out(db, row)
    assert {x.unit: x.ending_quantity for x in original.quantities_by_unit} == {"个": 10, "张": 100}
    assert original.ending_amount == 220
    changed = [movement("box-out", "-1", "2", at="2026-09-02", movement_type="ADJUSTMENT"),
               movement("sheet-in", "1", "2", at="2026-09-02", unit="张", movement_type="ADJUSTMENT")]
    ev = events_for(changed)
    for e in ev: e.sequence = None
    db.add_all(changed + ev); db.commit()
    current = ledger.closing_out(db, row)
    assert current.ending_quantity == original.ending_quantity and current.ending_amount == original.ending_amount
    assert current.quantities_by_unit == original.quantities_by_unit and current.snapshot_stale
    with pytest.raises(HTTPException, match="数量或金额已变化"):
        advance(db, row, "LOCKED")
    db.rollback()
    regenerated = closing(db)
    assert {x.unit: x.ending_quantity for x in ledger.closing_out(db, regenerated).quantities_by_unit} == {"个": 9, "张": 101}
    assert ledger.closing_outputs(db, [regenerated]) == [ledger.closing_out(db, regenerated)]


def test_old_locked_discrepancy_is_visible_without_rewriting_snapshot(db, monkeypatch):
    clock(monkeypatch, "2026-10-01")
    seed(db, [movement("a", "10", "2")])
    row = advance(db, advance(db, advance(db, closing(db), "PENDING"), "CONFIRMED"), "LOCKED")
    # Simulate an already-existing legacy discrepancy, not a newly allowed write.
    db.add(movement("legacy", "5", "2", at="2026-08-01")); db.commit()
    out = ledger.closing_out(db, row)
    assert out.snapshot_stale and out.ending_quantity == 10 and out.ending_amount == 20
    assert out.quantities_by_unit[0].ending_quantity == 10


@pytest.mark.parametrize('batch', [False, True])
def test_closing_response_refreshes_header_before_reading_new_generation_evidence(db, monkeypatch, batch):
    seed(db, [movement('a', '10', '2')])
    row = closing(db)
    identifier, old_revision = row.id, row.revision
    # Simulate a regeneration committed after a list query loaded this header.
    db.rollback()
    _ = row.revision
    with Session(db.get_bind()) as writer:
        writer.add(movement('b', '100', '2', unit='张'))
        writer.commit()
        refreshed = closing(writer)
        new_revision = refreshed.revision
    assert row.revision == old_revision
    result = ledger.closing_outputs(db, [row])[0] if batch else ledger.closing_out(db, row)
    assert result.id == identifier and result.revision == new_revision
    assert result.ending_quantity == 110 and not result.snapshot_stale
    assert {x.unit: x.ending_quantity for x in result.quantities_by_unit} == {'个': 10, '张': 100}


def test_mixed_offsets_agree_on_month_order_and_cost(db):
    rows = [movement("old", "100", "2", at="2026-08-01T00:00:00+08:00"),
            movement("issue", "-50", "2", at="2026-09-01T00:30:00+08:00"),
            movement("later", "100", "6", at="2026-08-31T17:00:00Z")]
    seed(db, rows)
    assert load_valuation(db, "huaxing").amounts["issue"] == -100
    august = closing(db, "2026-08")
    september = closing(db)
    assert august.ending_quantity == 100 and august.ending_amount == 200
    assert september.ending_quantity == 150 and september.ending_amount == 700
    _, listed = ledger.list_movements(db, "huaxing")
    assert [r.id for r in listed] == ["later", "issue", "old"]
    assert listed[1].balance == 50
    CartonReceipt.__table__.create(db.get_bind())
    summary = ledger.list_inventory_flow_summary(db, "huaxing", date_from="2026-09-01", date_to="2026-09-01")
    assert sum(r.quantity for r in summary if r.movement_type == "INBOUND") == 100
    assert all(r.business_date == "2026-09-01" for r in summary)


def test_delimiter_materials_cannot_issue_from_each_others_position(db):
    a = pos.create_location(db, "huaxing", "A", "1")
    b = pos.create_location(db, "huaxing", "B", "1")
    one = movement("one", "10", "2", contract_no="C|X", item_no="I")
    two = movement("two", "10", "2", contract_no="C", item_no="X|I")
    assert legacy_key(one) == legacy_key(two) and inventory_key(one) != inventory_key(two)
    pos.post(db, one, location_id=a.id); pos.post(db, two, location_id=b.id)
    db.add_all(events_for([one, two])); db.commit()
    with pytest.raises(HTTPException, match="库存不足"):
        ledger.create_inventory_movement(db, CartonInventoryMovementCreate(factory_id="huaxing", request_id=uuid4().hex,
            reference_movement_id=one.id, location_id=b.id, movement_type="OUTBOUND", quantity=10,
            document_no="OUT", reason="正常出库"), USER)
    db.rollback()
    assert {r.location_id: r.balance for r in pos.position_balances(db, "huaxing")} == {a.id: 10, b.id: 10}
    assert load_valuation(db, "huaxing").balances[cost_key(one)].quantity == 10


def seed_order(engine, status="CONFIRMED"):
    for cls in (CartonSupplier, CartonOrder, CartonOrderLine, CartonReceipt, CartonReceiptLine, CartonAuditEvent, CartonException, CartonInventoryMovement):
        cls.__table__.create(engine)
    payload = dict(factory_id="huaxing", expected_revision=1, reason="核对订单内容", customer_code="C", customer_name="Customer",
        contract_no="SC1", item_no="I1", product_name="P", product_order_quantity=95, order_date="2026-09-01", due_date="2026-09-10",
        lines=[dict(packaging_type="BOX", paper_quality="A33", specification="1x1x1", dimension_unit="cm",
                    usage_quantity=10, unit="个", unit_price=2, currency="CNY")])
    with Session(engine) as db:
        db.add(CartonSupplier(id="s", factory_id="huaxing", supplier_code="S", supplier_name="Supplier", created_at="2026-09-01", updated_at="2026-09-01"))
        db.add(CartonOrder(id="o", order_no="O", supplier_id="s", supplier_name_snapshot="Supplier", status=status,
            revision=1, created_by="u", updated_by="u", created_at="2026-09-01", updated_at="2026-09-01",
            **{key: value for key, value in payload.items() if key not in {"expected_revision", "reason", "lines"}}))
        db.add(CartonOrderLine(id="l", factory_id="huaxing", order_id="o", line_no=1, customer_code="C", contract_no="SC1", item_no="I1",
            required_quantity=10, **payload["lines"][0]))
        db.commit()
    return payload


@pytest.mark.parametrize("second_action", ["edit", "cancel", "bulk_cancel"])
def test_concurrent_draft_changes_accept_only_one_revision(tmp_path, monkeypatch, second_action):
    engine = create_engine(f"sqlite:///{tmp_path / 'orders.db'}")
    payload = seed_order(engine)
    barrier = Barrier(2)
    original_lock = ledger._lock_receipt_factory
    def synchronized_lock(db, factory):
        barrier.wait(timeout=10)
        original_lock(db, factory)
    monkeypatch.setattr(ledger, "_lock_receipt_factory", synchronized_lock)
    def run(action, note):
        with Session(engine) as db:
            try:
                if action == "edit": result = ledger.update_order(db, "O", CartonOrderUpdate(**payload, note=note), USER)
                elif action == "cancel": result = ledger.cancel_order(db, "O", CartonOrderCancelRequest(factory_id="huaxing", expected_revision=1, reason="取消错误订单"), USER)
                else: result = ledger.bulk_cancel_orders(db, CartonOrderBulkCancelRequest(factory_id="huaxing", reason="取消错误订单", items=[dict(order_no="O", expected_revision=1)]), USER)[0]
                return result.revision
            except HTTPException as error:
                db.rollback()
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, "edit", "FIRST")
        second = pool.submit(run, second_action, "SECOND")
        assert sorted([first.result(), second.result()]) == [2, 409]
    with Session(engine) as db:
        assert db.get(CartonOrder, "o").revision == 2
        assert len(list(db.scalars(select(CartonAuditEvent)))) == 1
    engine.dispose()


def test_append_inside_rounding_slack_stays_completed_then_reopens_for_new_carton():
    engine = create_engine("sqlite:///:memory:")
    seed_order(engine, "COMPLETED")
    with Session(engine) as db:
        db.add(CartonReceipt(id="r", factory_id="huaxing", receipt_no="R", delivery_note_no="DN", delivery_date="2026-09-01",
            supplier_id="s", supplier_name_snapshot="Supplier", status="POSTED", created_by="u", created_at="2026-09-01", updated_at="2026-09-01"))
        db.add(CartonReceiptLine(id="rl", factory_id="huaxing", receipt_id="r", line_no=1, order_line_id="l",
            customer_code="C", customer_name="Customer", contract_no="SC1", item_no="I1", packaging_type="BOX", paper_quality="A33",
            specification="1x1x1", unit="个", delivered_quantity=10, received_quantity=10, effective_quantity=10))
        db.commit()
        row = ledger.append_order(db, "O", CartonOrderAppendRequest(factory_id="huaxing", expected_revision=1, additional_quantity=1), USER)
        assert row.status == "COMPLETED" and db.get(CartonOrderLine, "l").required_quantity == 10
        row = ledger.append_order(db, "O", CartonOrderAppendRequest(factory_id="huaxing", expected_revision=2, additional_quantity=5), USER)
        assert row.status == "PARTIALLY_RECEIVED" and db.get(CartonOrderLine, "l").required_quantity == 11
    engine.dispose()
