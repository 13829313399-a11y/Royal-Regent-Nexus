import json
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_carton_inventory_valuation import db, movement, Movement, Audit, closing
from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from app.models.carton_positions import CartonPositionEntry
from app.services import carton_opening_batches as batches, carton_positions as positions, carton_procurement as ledger
from app.services.carton_inventory_valuation import load_valuation
from app.services.carton_inventory_identity import inventory_key
from app.services.carton_ledger_time import ledger_rows

USER = SimpleNamespace(id="reviewer", display_name="核对员")
BATCH = "CHI2-test-batch"


@pytest.fixture
def opening_db(db):
    CartonStocktake.__table__.create(db.get_bind())
    CartonStocktakeLine.__table__.create(db.get_bind())
    location = positions.create_location(db, "huaxing", "A", "A1")
    rows = [movement("open-a", "10", "2", at="2026-07-31T09:00:00+08:00"),
            movement("open-b", "20", "3", at="2026-08-01T09:00:00+08:00")]
    for row in rows:
        row.movement_type = "ADJUSTMENT"; row.source_type = "HISTORY_INVENTORY"; row.source_id = BATCH
        positions.post(db, row, location_id=location.id)
    ledger._audit(db, USER, "huaxing", "HISTORY_INVENTORY_IMPORTED", "carton_inventory_import", BATCH,
                  {"filename": "期初原表.xlsx", "row_count": 2, "rows": [{"movement_id": row.id} for row in rows]})
    db.commit()
    return db


def request(preview, **changes):
    values = dict(factory_id="huaxing", request_id=str(uuid4()), expected_fingerprint=preview["source_fingerprint"], reason="期初导错，整批撤销")
    values.update(changes)
    return batches.OpeningBatchReversal(**values)


def test_preview_whole_batch_atomic_reversal_and_actor_bound_replay(opening_db):
    db = opening_db
    listed = batches.list_batches(db, "huaxing")
    assert listed["total"] == 1 and listed["items"][0]["filename"] == "期初原表.xlsx"
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    assert checked["errors"] == [] and checked["row_count"] == 2, checked
    assert checked["totals"] == [{"unit": "个", "quantity": "30.0000"}]
    assert len(list(db.scalars(select(Movement)))) == 2
    payload = request(checked)
    result = batches.reverse_batch(db, BATCH, payload, USER)
    assert result["reversed_count"] == 2 and not result["duplicate"]
    assert all(row.balance == 0 for row in positions.position_balances(db, "huaxing"))
    originals = {row.id: row for row in db.scalars(select(Movement)) if row.source_type == "HISTORY_INVENTORY"}
    reversals = [row for row in db.scalars(select(Movement)) if row.movement_type == "REVERSAL"]
    assert len(reversals) == 2
    assert all(row.occurred_at == originals[row.reversal_of_movement_id].occurred_at for row in reversals)
    assert all(row.quantity == -originals[row.reversal_of_movement_id].quantity for row in reversals)
    assert all(row.quantity in (10, 20) for row in originals.values())
    assert all(balance.quantity == 0 and balance.amount == 0 for balance in load_valuation(db, "huaxing").balances.values())
    assert sum(row.quantity for row in ledger_rows(db, "huaxing", before="2026-08-01T")) == 0
    assert batches.reverse_batch(db, BATCH, payload, USER)["duplicate"]
    assert len(list(db.scalars(select(Movement)))) == 4
    changed = payload.model_copy(update={"reason": "不同内容"})
    with pytest.raises(HTTPException, match="提交标识"):
        batches.reverse_batch(db, BATCH, changed, USER)
    assert batches.list_batches(db, "huaxing")["items"][0]["status"] == "REVERSED"
    assert batches.preview_batch_reversal(db, "huaxing", BATCH)["errors"]
    with pytest.raises(HTTPException):
        batches.preview_batch_reversal(db, "huakang-b", BATCH)


@pytest.mark.parametrize("kind", ["outbound", "transfer", "count", "locked", "partial"])
def test_affected_downstream_state_blocks_entire_batch(opening_db, kind):
    db = opening_db
    original = db.get(Movement, "open-a")
    if kind == "outbound":
        row = movement("later", "-1", "2")
        positions.post(db, row, location_id=db.scalar(select(CartonPositionEntry.location_id)))
    elif kind == "transfer":
        location = positions.create_location(db, "huaxing", "A", "A2")
        first = db.scalar(select(CartonPositionEntry.location_id))
        for target, quantity in ((first, -1), (location.id, 1)):
            db.add(CartonPositionEntry(factory_id="huaxing", inventory_key=inventory_key(original),
                location_id=target, movement_id=None, transfer_id="transfer-test", quantity=quantity,
                occurred_at="2026-09-01T09:00:00+08:00"))
    elif kind == "count":
        db.add(CartonStocktake(id="count", factory_id="huaxing", created_by="u", created_by_name="User", created_at="2026-09-01"))
        db.flush()
        db.add(CartonStocktakeLine(id="count-line", stocktake_id="count", factory_id="huaxing",
            inventory_key=inventory_key(original), reference_movement_id=original.id, snapshot_json="{}",
            initial_quantity=30, count_book_quantity=30))
    elif kind == "locked":
        doc = closing(db, "2026-08")
        doc.status = "LOCKED"
    else:
        from app.schemas.carton_procurement import CartonInventoryReversalRequest
        ledger.reverse_inventory_movement(db, original.id, CartonInventoryReversalRequest(factory_id="huaxing", reason="单独冲销"), USER)
    db.commit()
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    assert checked["errors"], checked
    before = len(list(db.scalars(select(Movement))))
    with pytest.raises(HTTPException):
        batches.reverse_batch(db, BATCH, request(checked), USER)
    assert len(list(db.scalars(select(Movement)))) == before
    assert not db.scalar(select(Audit).where(Audit.event_type == batches.REVERSED_EVENT))


def test_stale_preview_and_failure_mid_batch_leave_every_original_unchanged(opening_db, monkeypatch):
    db = opening_db
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    ledger._audit(db, USER, "huaxing", "TEST_SOURCE_CHANGED", "test", "test", {})
    db.commit()
    with pytest.raises(HTTPException, match="已变化"):
        batches.reverse_batch(db, BATCH, request(checked), USER)
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    real_post = positions.post
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise HTTPException(409, "simulated second-row failure")
        return real_post(*args, **kwargs)
    monkeypatch.setattr(positions, "post", fail_second)
    with pytest.raises(HTTPException, match="second-row"):
        batches.reverse_batch(db, BATCH, request(checked), USER)
    assert len(list(db.scalars(select(Movement)))) == 2
    assert sum(row.balance for row in positions.position_balances(db, "huaxing")) == 30
    assert not db.scalar(select(Audit).where(Audit.event_type == "INVENTORY_MOVEMENT_REVERSED"))


@pytest.mark.parametrize("price", ["0", "2.5"])
def test_missing_and_known_prices_remain_balanced_on_reversal(opening_db, price):
    db = opening_db
    db.get(Movement, "open-a").unit_price = Decimal(price)
    db.commit()
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    assert checked["errors"] == [], checked
    batches.reverse_batch(db, BATCH, request(checked), USER)
    valuation = load_valuation(db, "huaxing")
    assert not valuation.errors
    assert not valuation.unpriced_pools


def test_legacy_batch_without_complete_row_evidence_remains_readable_but_cannot_reverse(opening_db):
    db = opening_db
    event = db.scalar(select(Audit).where(Audit.event_type == "HISTORY_INVENTORY_IMPORTED"))
    evidence = json.loads(event.detail_json); evidence.pop("rows")
    event.detail_json = json.dumps(evidence)
    db.commit()
    assert batches.list_batches(db, "huaxing")["total"] == 1
    checked = batches.preview_batch_reversal(db, "huaxing", BATCH)
    assert any("逐行入账依据" in error for error in checked["errors"])
    with pytest.raises(HTTPException):
        batches.reverse_batch(db, BATCH, request(checked), USER)
