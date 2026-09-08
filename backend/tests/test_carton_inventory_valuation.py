from uuid import uuid4
import json
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models.carton_procurement import (
    CartonAuditEvent as Audit, CartonClosing, CartonInventoryMovement as Movement, CartonSupplier,
)
from app.schemas.carton_procurement import (
    CartonClosingGenerateRequest, CartonClosingStatusRequest,
    CartonInventoryMovementCreate, CartonInventoryPriceConfirmRequest, CartonInventoryReversalRequest,
)
from app.services.carton_inventory_valuation import cost_key, value_movements
from app.services.carton_procurement import (
    closing_out, confirm_inventory_price, create_inventory_movement, generate_closings,
    reverse_inventory_movement, update_closing_status,
)

USER = SimpleNamespace(id="reviewer", display_name="核价员")


def movement(id, qty, price, *, at="2026-09-01T09:00:00+08:00", **kwargs):
    values = dict(id=id, factory_id="huaxing", order_line_id=None, customer_code="TEST",
                  customer_name="Test", contract_no="C", item_no="I", packaging_type="外箱",
                  paper_quality="A33", specification="1x1x1", unit="个", currency="CNY",
                  movement_type="INBOUND" if D(qty) > 0 else "OUTBOUND", quantity=D(qty),
                  unit_price=D(price), location="A", document_no=id, source_type="MANUAL",
                  source_id=id, source_line_id=id, actor_user_id="u", actor_name="User",
                  occurred_at=at, reversal_of_movement_id=None)
    values.update(kwargs)
    return Movement(**values)


def events_for(rows):
    return [Audit(id=f"audit-{r.id}", sequence=i + 1, factory_id=r.factory_id,
                  event_type="INVENTORY_MOVEMENT_REVERSED" if r.reversal_of_movement_id else "INVENTORY_MOVEMENT_CREATED",
                  entity_id=r.reversal_of_movement_id or r.id, entity_type="carton_inventory_movement",
                  detail_json=json.dumps({"reversal_id": r.id} if r.reversal_of_movement_id else {}),
                  actor_user_id="u", actor_name="User", created_at=r.occurred_at)
            for i, r in enumerate(rows)]


def test_full_depletion_and_original_prices_are_not_rewritten():
    rows = [movement("z", "100", "2"), movement("y", "100", "4"), movement("a", "-200", "4")]
    result = value_movements(rows, events_for(rows))
    assert not result.errors
    assert result.amounts["a"] == -600
    assert result.balances[cost_key(rows[0])].amount == 0
    assert rows[-1].unit_price == 4  # immutable original evidence


def test_interleaved_same_second_uses_audit_sequence_not_uuid_or_month_average():
    rows = [movement("z", "100", "2"), movement("a", "-50", "2"),
            movement("y", "100", "5"), movement("b", "-50", "5")]
    result = value_movements(list(reversed(rows)), events_for(rows))
    assert result.amounts["a"] == -100
    assert result.amounts["b"] == -200
    assert result.balances[cost_key(rows[0])].amount == 400


def test_outbound_reversal_restores_original_projected_cost():
    rows = [movement("a", "100", "2"), movement("b", "-50", "999"),
            movement("c", "100", "5"),
            movement("d", "50", "999", movement_type="REVERSAL", reversal_of_movement_id="b")]
    result = value_movements(rows, events_for(rows))
    assert result.amounts["d"] == 100
    assert result.balances[cost_key(rows[0])].amount == 700


def test_adjustment_reversal_with_residual_value_is_explicit_error():
    rows = [movement("a", "100", "2"), movement("b", "100", "4", movement_type="ADJUSTMENT"),
            movement("c", "-100", "3"),
            movement("d", "-100", "4", movement_type="REVERSAL", reversal_of_movement_id="b")]
    result = value_movements(rows, events_for(rows))
    assert any(r.id == "d" for r, _ in result.errors)


def test_precision_partial_then_full_outbound_has_no_residual():
    rows = [movement("a", "3", "0.123456"), movement("b", "7", "0.654321"),
            movement("c", "-3.1234", "0.1"), movement("d", "-6.8766", "0.1")]
    result = value_movements(rows, events_for(rows))
    assert result.balances[cost_key(rows[0])].amount == 0
    assert sum(result.amounts.values()) == 0


def test_currency_factory_unit_and_contract_do_not_share_cost():
    rows = [movement("a", "10", "2"), movement("b", "10", "9", currency="HKD"),
            movement("c", "10", "8", factory_id="huadeng"), movement("d", "10", "7", unit="张"),
            movement("e", "10", "6", contract_no="OTHER"), movement("f", "-5", "99")]
    result = value_movements(rows, events_for(rows))
    assert result.amounts["f"] == -10
    assert len(result.balances) == 5


def test_unsequenced_legacy_interleaving_is_reported_instead_of_guessed():
    rows = [movement("a", "100", "2"), movement("b", "-50", "2"), movement("c", "100", "4")]
    assert value_movements(rows, []).errors


def test_unsequenced_single_new_price_also_needs_transaction_order():
    rows = [movement("a", "100", "2", at="2026-08-01T09:00:00+08:00"),
            movement("b", "-100", "2"), movement("c", "100", "4")]
    assert value_movements(rows, []).errors


def test_reversing_consumed_missing_price_does_not_erase_unknown_cost():
    rows = [movement("a", "10", "0", movement_type="ADJUSTMENT"), movement("b", "10", "2"),
            movement("c", "-5", "1"),
            movement("d", "-10", "0", movement_type="REVERSAL", reversal_of_movement_id="a")]
    assert [r.id for r in value_movements(rows, events_for(rows)).missing] == ["a"]


def test_repricing_refreshes_amount_and_quantity_together(db):
    seed(db, [movement("a", "10", "0")])
    current = closing(db)
    db.add(movement("new", "5", "3", at="2026-09-02T09:00:00+08:00")); db.commit()
    confirm_inventory_price(db, "a", CartonInventoryPriceConfirmRequest(
        factory_id="huaxing", unit_price=2, reason="供应商报价核实"), USER)
    assert current.ending_quantity == 15
    assert current.inbound_quantity == 15
    assert current.ending_amount == 35


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    for cls in (Movement, CartonClosing, Audit, CartonSupplier):
        cls.__table__.create(engine)
    monkeypatch.setattr("app.services.carton_procurement.now_text", lambda: "2026-09-07T09:00:00+08:00")
    with Session(engine) as session:
        session.add(CartonSupplier(id="s", factory_id="huaxing", supplier_code="S", supplier_name="Supplier",
                                   status="ACTIVE", created_at="2026-01-01", updated_at="2026-01-01"))
        session.commit()
        yield session
    engine.dispose()


def seed(db, rows):
    db.add_all(rows + events_for(rows))
    db.commit()


def closing(db, period="2026-09"):
    return generate_closings(db, CartonClosingGenerateRequest(factory_id="huaxing", period=period), USER)[0]


def advance(db, row, status):
    return update_closing_status(db, row.id, CartonClosingStatusRequest(
        factory_id="huaxing", expected_revision=row.revision, status=status), USER)


def test_service_outbound_uses_weighted_price_and_cross_month_carry(db):
    rows = [movement("a", "100", "2", at="2026-08-01T09:00:00+08:00"),
            movement("b", "-50", "2", at="2026-08-02T09:00:00+08:00"),
            movement("c", "100", "5", at="2026-09-01T09:00:00+08:00")]
    seed(db, rows)
    assert closing(db, "2026-08").ending_amount == 100
    out = create_inventory_movement(db, CartonInventoryMovementCreate(request_id=uuid4().hex,
        factory_id="huaxing", reference_movement_id="c", movement_type="OUTBOUND",
        quantity=50, document_no="OUT", reason="客户要货"), USER)
    assert out.unit_price == 4
    current = closing(db)
    assert current.opening_quantity == 50
    assert current.ending_quantity == 100
    assert current.ending_amount == 400


def test_missing_price_blocks_confirmation_even_when_consumed_and_can_be_resolved(db, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("app.services.carton_procurement.business_now", lambda: datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
    rows = [movement("a", "10", "0", at="2026-08-01T09:00:00+08:00"), movement("b", "-10", "0")]
    seed(db, rows)
    current = advance(db, closing(db), "PENDING")
    assert closing_out(db, current).pricing_issues[0].movement_id == "a"
    with pytest.raises(HTTPException, match="计价问题"):
        advance(db, current, "CONFIRMED")
    confirm_inventory_price(db, "a", CartonInventoryPriceConfirmRequest(
        factory_id="huaxing", unit_price="2.5", reason="供应商报价单核对"), USER)
    assert current.status == "DRAFT"
    assert current.ending_amount == 0
    assert db.get(Movement, "a").unit_price == 0
    assert not closing_out(db, current).pricing_issues
    for status in ("PENDING", "CONFIRMED", "LOCKED"):
        current = advance(db, current, status)


def test_lock_rechecks_missing_price_added_after_confirmation(db, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    monkeypatch.setattr("app.services.carton_procurement.business_now", lambda: datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
    seed(db, [movement("a", "10", "2")])
    current = closing(db)
    for status in ("PENDING", "CONFIRMED"):
        current = advance(db, current, status)
    db.add(movement("new-missing", "5", "0", item_no="NEW")); db.commit()
    with pytest.raises(HTTPException, match="new-missing"):
        advance(db, current, "LOCKED")
    assert current.status == "CONFIRMED"


def test_explicit_free_price_requires_acknowledgement_and_audited_reason(db):
    seed(db, [movement("a", "10", "0")])
    current = closing(db)
    with pytest.raises(ValueError, match="免费"):
        CartonInventoryPriceConfirmRequest(factory_id="huaxing", unit_price=0, reason="免费供料确认")
    confirm_inventory_price(db, "a", CartonInventoryPriceConfirmRequest(
        factory_id="huaxing", unit_price=0, zero_price_confirmed=True, reason="免费供料确认"), USER)
    assert not closing_out(db, current).pricing_issues
    record = db.scalar(select(Audit).where(Audit.event_type == "INVENTORY_PRICE_CONFIRMED"))
    assert json.loads(record.detail_json)["zero_price_confirmed"] is True
    with pytest.raises(HTTPException, match="已核实"):
        confirm_inventory_price(db, "a", CartonInventoryPriceConfirmRequest(
            factory_id="huaxing", unit_price=3, reason="重复核实价格"), USER)


def test_price_cannot_revalue_any_later_locked_snapshot(db):
    seed(db, [movement("a", "10", "0")])
    current = closing(db)
    current.status = "LOCKED"; db.commit()
    with pytest.raises(HTTPException, match="已锁账"):
        confirm_inventory_price(db, "a", CartonInventoryPriceConfirmRequest(
            factory_id="huaxing", unit_price=2, reason="供应商报价核实"), USER)
    assert current.ending_amount == 0


def test_previous_locked_amount_is_never_silently_rebased(db):
    seed(db, [movement("a", "100", "2", at="2026-08-01T09:00:00+08:00"),
              movement("b", "100", "4", at="2026-08-02T09:00:00+08:00"),
              movement("c", "-100", "4", at="2026-08-03T09:00:00+08:00")])
    previous = closing(db, "2026-08")
    previous.status = "LOCKED"
    previous.ending_amount = D(200)  # preserved old costing snapshot; new valuation is 300
    db.commit()
    current = advance(db, closing(db), "PENDING")
    assert any("历史锁账金额" in issue.message for issue in closing_out(db, current).pricing_issues)
    with pytest.raises(HTTPException, match="历史锁账金额"):
        advance(db, current, "CONFIRMED")
    assert previous.ending_amount == 200


def test_confirmed_legacy_wrong_cost_can_be_regenerated_without_unlocking(db):
    seed(db, [movement("a", "100", "2"), movement("b", "100", "4"), movement("c", "-100", "4")])
    current = closing(db)
    current.status = "CONFIRMED"
    current.ending_amount = D(200)
    current.confirmed_by = "old"
    db.commit()
    refreshed = closing(db)
    assert refreshed.status == "DRAFT"
    assert refreshed.ending_amount == 300
    assert refreshed.confirmed_by == ""


def test_canceled_unpriced_opening_is_not_permanent_missing_price(db):
    rows = [movement("a", "10", "0", movement_type="ADJUSTMENT"),
            movement("b", "-10", "0", movement_type="REVERSAL", reversal_of_movement_id="a")]
    seed(db, rows)
    assert not closing_out(db, closing(db)).pricing_issues


def test_service_reversal_rejects_quantity_zero_value_residual(db):
    rows = [movement("a", "100", "2"), movement("b", "100", "4", movement_type="ADJUSTMENT"),
            movement("c", "-100", "3")]
    seed(db, rows)
    with pytest.raises(HTTPException, match="金额无法对平"):
        reverse_inventory_movement(db, "b", CartonInventoryReversalRequest(
            factory_id="huaxing", reason="盘点数据错误"), USER)
    db.rollback()
    assert len(list(db.scalars(select(Movement)).all())) == 3
