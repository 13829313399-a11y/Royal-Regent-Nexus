from uuid import uuid4
from decimal import Decimal as D
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select

from test_carton_inventory_valuation import db, events_for, movement, Movement, Audit
from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from app.schemas.carton_stocktake import StocktakeCreate, StocktakeAction
from app.schemas.carton_procurement import CartonInventoryMovementCreate, CartonInventoryRelocateRequest
from app.services.carton_procurement import create_inventory_movement, relocate_inventory, inventory_balances
from app.services.carton_stocktake import create_stocktake, act_stocktake, stocktake_detail
from app.services.carton_inventory_valuation import load_valuation

CREATOR = SimpleNamespace(id="counter", display_name="盘点员")
REVIEWER = SimpleNamespace(id="supervisor", display_name="主管")


@pytest.fixture
def stockdb(db):
    CartonStocktake.__table__.create(db.get_bind())
    CartonStocktakeLine.__table__.create(db.get_bind())
    seed(db, [movement("a", "100", "2")])
    return db


def seed(db, rows):
    events = events_for(rows)
    for event in events: event.sequence = None
    db.add_all(rows + events)
    db.commit()


def create(db, refs=None):
    return create_stocktake(db, StocktakeCreate(factory_id="huaxing", reference_movement_ids=refs or ["a"]), CREATOR)


def action(db, doc, name, actual="98", user=CREATOR, **kwargs):
    values = dict(factory_id="huaxing", expected_revision=doc["revision"], action=name,
                  ledger_token=doc["ledger_token"], cutoff_acknowledged=True,
                  lines=[dict(id=line["id"], actual_quantity=actual, reason="实物盘点差异") for line in doc["lines"]])
    values.update(kwargs)
    return act_stocktake(db, doc["id"], StocktakeAction(**values), user)


def change(db, qty):
    return create_inventory_movement(db, CartonInventoryMovementCreate(request_id=uuid4().hex, factory_id="huaxing",
        reference_movement_id="a", movement_type="ADJUSTMENT", quantity=qty, document_no="CHANGE", reason="盘点期间正常交易"), CREATOR)


@pytest.mark.parametrize("intervening,expected", [("-10", "88"), ("20", "118")])
def test_fixed_difference_preserves_post_submission_movements(stockdb, intervening, expected):
    doc = action(stockdb, create(stockdb), "SUBMIT")
    change(stockdb, intervening)
    posted = action(stockdb, doc, "APPROVE", user=REVIEWER)
    assert posted["status"] == "POSTED"
    assert posted["lines"][0]["difference"] == -2
    assert inventory_balances(stockdb, "huaxing")[0].balance == D(expected)
    row = stockdb.get(Movement, posted["lines"][0]["movement_id"])
    assert row.source_type == "STOCKTAKE" and row.quantity == -2 and row.unit_price == 2
    assert load_valuation(stockdb, "huaxing").balances.popitem()[1].amount == D(expected) * 2
    with pytest.raises(HTTPException): action(stockdb, posted, "APPROVE", user=REVIEWER)
    stockdb.rollback()
    assert len(list(stockdb.scalars(select(Movement).where(Movement.source_type == "STOCKTAKE")))) == 1


def test_draft_blank_zero_and_zero_difference_evidence(stockdb):
    doc = create(stockdb)
    saved = action(stockdb, doc, "SAVE", actual=None)
    assert saved["lines"][0]["actual_quantity"] is None
    with pytest.raises(HTTPException): action(stockdb, saved, "SUBMIT", actual=None)
    stockdb.rollback()
    with pytest.raises(HTTPException): action(stockdb, saved, "SUBMIT", cutoff_acknowledged=False)
    stockdb.rollback()
    submitted = action(stockdb, saved, "SUBMIT", actual="100")
    posted = action(stockdb, submitted, "APPROVE", user=REVIEWER)
    assert posted["lines"][0]["difference"] == 0
    assert posted["lines"][0]["movement_id"] == ""
    assert len(list(stockdb.scalars(select(Movement)))) == 1
    nextdoc = create(stockdb)
    submitted = action(stockdb, nextdoc, "SUBMIT", actual="0")
    action(stockdb, submitted, "APPROVE", user=REVIEWER)
    assert inventory_balances(stockdb, "huaxing")[0].balance == 0


def test_token_catches_net_zero_and_location_roundtrip(stockdb):
    doc = create(stockdb)
    change(stockdb, "-10"); change(stockdb, "10")
    with pytest.raises(HTTPException) as error: action(stockdb, doc, "SUBMIT")
    assert "重新核对" in error.value.detail
    stockdb.rollback()
    doc = stocktake_detail(stockdb, "huaxing", doc["id"])
    for location in ("B", "A"):
        balance = inventory_balances(stockdb, "huaxing")[0]
        relocate_inventory(stockdb, CartonInventoryRelocateRequest(factory_id="huaxing", reference_movement_id=balance.latest_movement_id,
            expected_location_revision=balance.location_revision, location=location), CREATOR)
    with pytest.raises(HTTPException): action(stockdb, doc, "SUBMIT")


def test_location_change_after_submit_requires_return(stockdb):
    doc = action(stockdb, create(stockdb), "SUBMIT")
    relocate_inventory(stockdb, CartonInventoryRelocateRequest(factory_id="huaxing", reference_movement_id="a", expected_location_revision=0, location="B"), CREATOR)
    with pytest.raises(HTTPException): action(stockdb, doc, "APPROVE", user=REVIEWER)
    stockdb.rollback()
    returned = action(stockdb, doc, "RETURN", user=REVIEWER, reason="仓位变化重新盘点")
    submitted = action(stockdb, returned, "SUBMIT")
    assert submitted["lines"][0]["latest_location"] == "B"
    assert action(stockdb, submitted, "APPROVE", user=REVIEWER)["status"] == "POSTED"


def test_overlap_factory_revision_and_self_review(stockdb):
    doc = create(stockdb)
    with pytest.raises(HTTPException): create(stockdb)
    stockdb.rollback()
    with pytest.raises(HTTPException) as e: stocktake_detail(stockdb, "huadeng", doc["id"])
    assert e.value.status_code == 404
    with pytest.raises(HTTPException): action(stockdb, doc, "SUBMIT", expected_revision=22)
    stockdb.rollback()
    with pytest.raises(HTTPException): action(stockdb, doc, "SAVE", user=REVIEWER)
    stockdb.rollback()
    submitted = action(stockdb, doc, "SUBMIT")
    with pytest.raises(HTTPException) as e: action(stockdb, submitted, "APPROVE")
    assert e.value.status_code == 403
    stockdb.rollback()
    cancelled = action(stockdb, submitted, "CANCEL", reason="取消重盘")
    assert cancelled["status"] == "CANCELLED"
    assert create(stockdb)["status"] == "DRAFT"


def test_invalid_inputs_and_line_injection(stockdb):
    for value in ("-1", "1.00001", "NaN", "Infinity"):
        with pytest.raises(ValidationError):
            StocktakeAction(factory_id="huaxing", expected_revision=1, action="SAVE", lines=[{"id": "x", "actual_quantity": value}])
    doc = create(stockdb)
    for lines in ([], [{"id": "other", "actual_quantity": 0}], [{"id": doc["lines"][0]["id"], "actual_quantity": 98, "reason": ""}]):
        with pytest.raises(HTTPException): action(stockdb, doc, "SUBMIT", lines=lines)
        stockdb.rollback()


def test_atomic_negative_balance_rollback(stockdb):
    seed(stockdb, [movement("b", "10", "3", item_no="OTHER", at="2026-09-02T09:00:00+08:00")])
    doc = create(stockdb, ["a", "b"])
    submitted = action(stockdb, doc, "SUBMIT", actual="0")
    change(stockdb, "-1")
    with pytest.raises(HTTPException): action(stockdb, submitted, "APPROVE", user=REVIEWER)
    stockdb.rollback()
    assert stocktake_detail(stockdb, "huaxing", doc["id"])["status"] == "SUBMITTED"
    assert not list(stockdb.scalars(select(Movement).where(Movement.source_type == "STOCKTAKE")))


def test_gain_uses_average_not_latest_price_and_rejects_mixed_currency(stockdb):
    seed(stockdb, [movement("b", "100", "4", at="2026-09-02T09:00:00+08:00")])
    doc = action(stockdb, create(stockdb, ["b"]), "SUBMIT", actual="210")
    posted = action(stockdb, doc, "APPROVE", user=REVIEWER)
    assert stockdb.get(Movement, posted["lines"][0]["movement_id"]).unit_price == 3
    seed(stockdb, [movement("c", "1", "1", currency="USD", at="2026-09-03T09:00:00+08:00")])
    reference = inventory_balances(stockdb, "huaxing")[0].latest_movement_id
    with pytest.raises(HTTPException): create(stockdb, [reference])


def test_unreviewed_save_keeps_stale_basis_even_for_net_zero(stockdb):
    doc = action(stockdb, create(stockdb), "SAVE")
    change(stockdb, "-10"); change(stockdb, "10")
    reopened = stocktake_detail(stockdb, "huaxing", doc["id"])
    assert reopened["basis_changed"] is True
    saved = action(stockdb, reopened, "SAVE", cutoff_acknowledged=False)
    assert saved["basis_changed"] is True
    assert saved["lines"][0]["count_book_quantity"] == 100
    verified = action(stockdb, saved, "SUBMIT")
    assert verified["basis_changed"] is False


def test_raw_receipt_location_change_also_blocks_approval(stockdb):
    doc = action(stockdb, create(stockdb), "SUBMIT")
    seed(stockdb, [movement("b", "5", "2", location="B", at="2026-09-02T09:00:00+08:00")])
    assert stocktake_detail(stockdb, "huaxing", doc["id"])["lines"][0]["location_changed"] is True
    with pytest.raises(HTTPException): action(stockdb, doc, "APPROVE", user=REVIEWER)
    stockdb.rollback()
    assert not list(stockdb.scalars(select(Movement).where(Movement.source_type == "STOCKTAKE")))


def test_return_and_recount_preserves_original_submission_evidence(stockdb):
    first = action(stockdb, create(stockdb), "SUBMIT")
    returned = action(stockdb, first, "RETURN", user=REVIEWER, reason="请重新点数")
    second = action(stockdb, returned, "SUBMIT", actual="99")
    evidence = [event["detail"] for event in second["events"] if event["action"] == "STOCKTAKE_SUBMIT"]
    assert [D(event["lines"][0]["actual_quantity"]) for event in evidence] == [98, 99]
    assert [D(event["lines"][0]["difference"]) for event in evidence] == [-2, -1]


def test_locked_month_blocks_entire_stocktake(stockdb, monkeypatch):
    from test_carton_inventory_valuation import closing, advance
    from datetime import datetime
    from zoneinfo import ZoneInfo
    # Final locking is only available after the month has ended.
    monkeypatch.setattr("app.services.carton_procurement.business_now",
                        lambda: datetime(2026, 10, 1, tzinfo=ZoneInfo("Asia/Shanghai")))
    doc = action(stockdb, create(stockdb), "SUBMIT")
    month = closing(stockdb)
    for status in ("PENDING", "CONFIRMED", "LOCKED"):
        month = advance(stockdb, month, status)
    with pytest.raises(HTTPException): action(stockdb, doc, "APPROVE", user=REVIEWER)
    stockdb.rollback()
    assert stocktake_detail(stockdb, "huaxing", doc["id"])["status"] == "SUBMITTED"


def test_gain_without_carrying_cost_stays_unpriced(stockdb):
    change(stockdb, "-100")
    ref = inventory_balances(stockdb, "huaxing")[0].latest_movement_id
    doc = action(stockdb, create(stockdb, [ref]), "SUBMIT", actual="3")
    posted = action(stockdb, doc, "APPROVE", user=REVIEWER)
    identifier = posted["lines"][0]["movement_id"]
    assert stockdb.get(Movement, identifier).unit_price == 0
    assert identifier in {row.id for row in load_valuation(stockdb, "huaxing").missing}
