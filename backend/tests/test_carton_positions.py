from decimal import Decimal as D
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_carton_inventory_valuation import db, movement, events_for
from app.models.carton_positions import CartonPositionEntry
from app.models.carton_procurement import CartonInventoryMovement
from app.schemas.carton_positions import PositionTransfer
from app.schemas.carton_procurement import CartonInventoryMovementCreate, CartonInventoryBulkCreate, CartonInventoryReversalRequest
from app.services import carton_positions as pos, carton_procurement as ledger
from app.services.carton_inventory_valuation import load_valuation
from app.services.carton_usage import usage_by_key

USER = SimpleNamespace(id="warehouse", display_name="仓管")


def setup(db):
    a = pos.create_location(db, "huaxing", "一仓", "A-01")
    b = pos.create_location(db, "huaxing", "二仓", "B-01")
    row = movement("receipt", "100", "2", source_type="RECEIPT")
    pos.post(db, row, allocations=[{"location_id": a.id, "quantity": "70"}, {"location_id": b.id, "quantity": "30"}])
    db.add_all(events_for([row])); db.commit()
    return row, a, b


def assert_balance(db, expected):
    rows = pos.position_balances(db, "huaxing")
    assert {r.latest_location: r.balance for r in rows} == {k: D(v) for k, v in expected.items()}
    movements = list(db.scalars(select(CartonInventoryMovement)))
    parts = list(db.scalars(select(CartonPositionEntry)))
    assert all(r.balance >= 0 for r in rows)
    assert sum(r.balance for r in rows) == sum(r.quantity for r in movements)
    for row in movements:
        assert sum(p.quantity for p in parts if p.movement_id == row.id) == row.quantity


def out(db, loc, qty, kind="USAGE", request=None):
    return ledger.create_inventory_movement(db, CartonInventoryMovementCreate(
        factory_id="huaxing", request_id=request or uuid4().hex, reference_movement_id="receipt",
        location_id=loc.id, movement_type="OUTBOUND", quantity=qty, document_no="OUT-1", reason="实际出库", issue_kind=kind), USER)


def test_split_receipt_position_limits_transfer_retry_and_cost(db):
    row, a, b = setup(db)
    assert_balance(db, {"一仓／A-01": "70", "二仓／B-01": "30"})
    with pytest.raises(HTTPException, match="库存不足"):
        out(db, b, "31")
    db.rollback()
    source = next(r for r in pos.position_balances(db, "huaxing") if r.location_id == a.id)
    payload = PositionTransfer(factory_id="huaxing", request_id=uuid4().hex, position_key=source.position_key,
        expected_position_revision=source.position_revision, location_id=b.id, quantity="20")
    result = pos.transfer(db, payload, USER)
    assert pos.transfer(db, payload.model_copy(update={"quantity": D("20.0000")}), USER) == result
    assert_balance(db, {"一仓／A-01": "50", "二仓／B-01": "50"})
    assert sum(v.amount for v in load_valuation(db, "huaxing").balances.values()) == 200
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["status"] == "UNUSED"
    with pytest.raises(HTTPException, match="不同内容"):
        pos.transfer(db, payload.model_copy(update={"quantity": D(1)}), USER)


def test_two_positions_same_material_bulk_atomic_and_usage(db):
    row, a, b = setup(db)
    request = dict(factory_id="huaxing", request_id=uuid4().hex, document_no="BULK", issue_kind="USAGE",
                   items=[dict(reference_movement_id=row.id, location_id=a.id, quantity="20"),
                          dict(reference_movement_id=row.id, location_id=b.id, quantity="31")])
    with pytest.raises(HTTPException):
        ledger.create_inventory_movements_bulk(db, CartonInventoryBulkCreate(**request), USER)
    db.rollback()
    assert_balance(db, {"一仓／A-01": "70", "二仓／B-01": "30"})
    request["items"][1]["quantity"] = "10"
    result = ledger.create_inventory_movements_bulk(db, CartonInventoryBulkCreate(**request), USER)
    assert len(result) == 2
    assert len(ledger.create_inventory_movements_bulk(db, CartonInventoryBulkCreate(**request), USER)) == 2
    assert_balance(db, {"一仓／A-01": "50", "二仓／B-01": "20"})
    usage = usage_by_key(db, "huaxing")[pos.inventory_key(row)]
    assert usage["usage"] == 30 and usage["status"] == "PARTIAL"
    ledger.reverse_inventory_movement(db, result[0].id, CartonInventoryReversalRequest(factory_id="huaxing", reason="纠正出库"), USER)
    assert_balance(db, {"一仓／A-01": "70", "二仓／B-01": "20"})
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["usage"] == 10


def test_exhaustion_new_receipt_and_non_usage_clear(db):
    row, a, b = setup(db)
    out(db, a, "70"); out(db, b, "30")
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["status"] == "EXHAUSTED"
    later = movement("later", "10", "2", at="2026-09-08T09:00:00+08:00", source_type="RECEIPT")
    pos.post(db, later, location_id=b.id)
    ev = events_for([later])[0]; ev.sequence = None; db.add(ev); db.commit()
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["status"] == "PARTIAL"
    # Move clock forward so the loss is after this receipt in weighted valuation.
    from unittest.mock import patch
    with patch.object(ledger, "now_text", return_value="2026-09-08T10:00:00+08:00"):
        out(db, b, "10", kind="LOSS")
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["status"] == "CLEARED"


def test_legacy_usage_unknown_and_position_not_inferred(db):
    row = movement("legacy", "100", "2")
    db.add(row); db.commit()
    pos.seed_unallocated(db, "huaxing"); db.commit()
    assert_balance(db, {"待核仓位": "100"})
    unknown = pos.get_location(db, "huaxing", pos.unknown_id("huaxing"))
    # Keep actual fixture source identifier when creating a new request.
    ledger.create_inventory_movement(db, CartonInventoryMovementCreate(factory_id="huaxing", request_id=uuid4().hex,
        reference_movement_id="legacy", location_id=unknown.id, movement_type="OUTBOUND", quantity=100,
        document_no="OLD", reason="无法辨别旧用途"), USER)
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["status"] == "UNKNOWN"


def test_allocation_validation_and_cross_factory(db):
    row, a, b = setup(db)
    with pytest.raises(HTTPException):
        pos.validate_allocations(db, "huaxing", [{"location_id": a.id, "quantity": "10"}], D(11))
    with pytest.raises(HTTPException):
        pos.validate_allocations(db, "other", [{"location_id": a.id, "quantity": "10"}], D(10))
    with pytest.raises(HTTPException):
        pos.validate_allocations(db, "huaxing", [{"location_id": a.id, "quantity": "5"}] * 2, D(10))


def test_count_is_scoped_to_one_position_and_other_positions_can_count(db):
    from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
    from app.schemas.carton_stocktake import StocktakeCreate
    from app.services.carton_stocktake import create_stocktake
    from test_carton_stocktake import action, REVIEWER
    CartonStocktake.__table__.create(db.get_bind())
    CartonStocktakeLine.__table__.create(db.get_bind())
    row, a, b = setup(db)
    balances = {r.location_id: r for r in pos.position_balances(db, "huaxing")}
    def create(loc):
        return create_stocktake(db, StocktakeCreate(factory_id="huaxing", position_keys=[balances[loc.id].position_key]), USER)
    first, second = create(a), create(b)
    assert first["lines"][0]["initial_quantity"] == 70
    assert second["lines"][0]["initial_quantity"] == 30
    with pytest.raises(HTTPException, match="进行中的盘点"):
        create(a)
    db.rollback()
    submitted = action(db, first, "SUBMIT", actual="68", user=USER)
    out(db, a, 5)
    posted = action(db, submitted, "APPROVE", user=REVIEWER)
    assert posted["status"] == "POSTED"
    assert_balance(db, {"一仓／A-01": "63", "二仓／B-01": "30"})
    assert usage_by_key(db, "huaxing")[pos.inventory_key(row)]["usage"] == 5


def test_long_names_are_preserved_in_catalog_but_main_ledger_stays_bounded(db):
    loc = pos.create_location(db, "huaxing", "仓" * 64, "位" * 64)
    row = movement("long", "5", "2", contract_no="C" * 96, item_no="I" * 96)
    pos.post(db, row, location_id=loc.id)
    db.add_all(events_for([row])); db.commit()
    assert len(row.location) <= 128 and len(pos.label(loc)) == 129
    source = pos.position_balances(db, "huaxing")[0]
    target = pos.create_location(db, "huaxing", "目的仓", "B")
    pos.transfer(db, PositionTransfer(factory_id="huaxing", request_id=uuid4().hex,
        position_key=source.position_key, expected_position_revision=source.position_revision,
        location_id=target.id, quantity=2), USER)
    from app.models.carton_procurement import CartonAuditEvent
    transfer = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == "INVENTORY_LOCATION_CHANGED"))
    assert len(transfer.entity_id) <= 96


def test_multi_paper_usage_aggregation_does_not_confuse_losses_with_issues():
    from app.services.carton_usage import aggregate_status
    assert aggregate_status(["CLEARED", "UNUSED"], D(0)) == "UNUSED"
    assert aggregate_status(["CLEARED", "UNUSED"], D(10)) == "PARTIAL"
    assert aggregate_status(["EXHAUSTED", "NOT_RECEIVED"], D(10)) == "EXHAUSTED"
    assert aggregate_status(["UNKNOWN", "UNUSED"], D(0)) == "UNKNOWN"


def test_position_read_uses_one_snapshot_for_balance_metadata_and_revision(db):
    from sqlalchemy import event
    row, a, b = setup(db)
    statements = []
    def capture(_conn, _cursor, statement, _params, _context, _many):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)
    event.listen(db.get_bind(), "before_cursor_execute", capture)
    try:
        positions = pos.position_balances(db, "huaxing")
        assert sum(r.balance for r in positions) == 100
        # A single joined read cannot observe a movement and its allocation from different commits.
        assert len(statements) == 1
        assert all(r.latest_movement_id == row.id and r.position_revision > 0 for r in positions)
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture)
