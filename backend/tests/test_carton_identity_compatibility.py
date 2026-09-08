import json
from decimal import Decimal as D
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_carton_stocktake import stockdb, db, create, action, REVIEWER, CREATOR, seed
from test_carton_inventory_valuation import movement
from app.models.carton_positions import CartonPositionEntry
from app.models.carton_procurement import CartonInventoryMovement
from app.models.carton_stocktake import CartonStocktake, CartonStocktakeLine
from app.schemas.carton_positions import PositionTransfer
from app.schemas.carton_stocktake import StocktakeCreate
from app.services import carton_positions as pos, carton_stocktake as count
from app.services.carton_inventory_identity import inventory_key, legacy_key


def legacy_entries(db):
    rows = list(db.scalars(select(CartonInventoryMovement)))
    old = {inventory_key(row): legacy_key(row) for row in rows}
    for part in db.scalars(select(CartonPositionEntry)):
        part.inventory_key = old[part.inventory_key]
    db.commit()


def test_unambiguous_old_transfers_mix_with_new_entries_and_keep_retry_evidence(stockdb):
    source = pos.position_balances(stockdb, "huaxing")
    if not source:
        pos.seed_unallocated(stockdb, "huaxing")
        source = pos.position_balances(stockdb, "huaxing")
    target = pos.create_location(stockdb, "huaxing", "新仓", "B")
    payload = PositionTransfer(factory_id="huaxing", request_id=uuid4().hex, position_key=source[0].position_key,
        expected_position_revision=source[0].position_revision, location_id=target.id, quantity=20)
    result = pos.transfer(stockdb, payload, CREATOR)
    legacy_entries(stockdb)
    legacy_snapshot = [(p.id, p.inventory_key, p.quantity) for p in pos.entries(stockdb, "huaxing")]
    assert pos.transfer(stockdb, payload, CREATOR) == result
    rows = pos.position_balances(stockdb, "huaxing")
    assert sorted(r.balance for r in rows) == [20, 80]
    original = next(r for r in rows if r.balance == 80)
    pos.transfer(stockdb, PositionTransfer(factory_id="huaxing", request_id=uuid4().hex,
        position_key=original.position_key, expected_position_revision=original.position_revision,
        location_id=target.id, quantity=10), CREATOR)
    assert sorted(r.balance for r in pos.position_balances(stockdb, "huaxing")) == [30, 70]
    assert [(p.id, p.inventory_key, p.quantity) for p in pos.entries(stockdb, "huaxing")][:len(legacy_snapshot)] == legacy_snapshot


@pytest.mark.parametrize("submitted", [False, True])
def test_old_position_count_keeps_cutoff_and_prevents_duplicate_count(stockdb, submitted):
    doc = create(stockdb)
    line = stockdb.scalar(select(CartonStocktakeLine))
    header = stockdb.get(CartonStocktake, doc['id'])
    source = stockdb.get(CartonInventoryMovement, line.reference_movement_id)
    _, loc = json.loads(line.inventory_key)
    line.inventory_key = pos.position_key(legacy_key(source), loc)
    legacy_entries(stockdb)
    header.basis_token = count._state(stockdb, header, [line])[4]
    stockdb.commit()
    doc = count.stocktake_detail(stockdb, 'huaxing', doc['id'])
    assert not doc['basis_changed'] and doc['lines'][0]['current_quantity'] == 100
    if submitted:
        doc = action(stockdb, doc, 'SUBMIT', actual='98')
    key = pos.position_balances(stockdb, 'huaxing')[0].position_key
    with pytest.raises(HTTPException, match='进行中的盘点'):
        count.create_stocktake(stockdb, StocktakeCreate(factory_id='huaxing', position_keys=[key]), CREATOR)
    stockdb.rollback()
    if not submitted:
        doc = action(stockdb, doc, 'SUBMIT', actual='98')
    old_key = stockdb.get(CartonStocktakeLine, line.id).inventory_key
    posted = action(stockdb, doc, 'APPROVE', user=REVIEWER)
    assert posted['status'] == 'POSTED'
    assert sum(r.balance for r in pos.position_balances(stockdb, 'huaxing')) == 98
    assert stockdb.get(CartonStocktakeLine, line.id).inventory_key == old_key


def test_ambiguous_old_count_cannot_post_but_can_be_cancelled(stockdb):
    original = stockdb.get(CartonInventoryMovement, 'a')
    original.contract_no, original.item_no = 'C|X', 'I'
    stockdb.commit()
    doc = create(stockdb)
    line = stockdb.scalar(select(CartonStocktakeLine))
    _, loc = json.loads(line.inventory_key)
    line.inventory_key = pos.position_key(legacy_key(original), loc)
    legacy_entries(stockdb)
    seed(stockdb, [movement('second', '10', '2', contract_no='C', item_no='X|I')])
    doc = count.stocktake_detail(stockdb, 'huaxing', doc['id'])
    assert doc['reconciliation_error'] and doc['lines'][0]['current_quantity'] is None
    with pytest.raises(HTTPException, match='旧库存身份'):
        action(stockdb, doc, 'SUBMIT')
    stockdb.rollback()
    cancelled = action(stockdb, doc, 'CANCEL', reason='旧合并库存需重新核对')
    assert cancelled['status'] == 'CANCELLED'


def test_ambiguous_legacy_transfer_never_guesses_material_ownership(db):
    a = pos.create_location(db, 'huaxing', 'A', '1')
    b = pos.create_location(db, 'huaxing', 'B', '1')
    one = movement('one', '10', '2', contract_no='C|X', item_no='I')
    two = movement('two', '10', '2', contract_no='C', item_no='X|I')
    pos.post(db, one, location_id=a.id); pos.post(db, two, location_id=b.id)
    db.add_all([CartonPositionEntry(factory_id='huaxing', inventory_key=legacy_key(one), location_id=loc,
        transfer_id='OLD-TRANSFER', quantity=qty, occurred_at='2026-09-01') for loc,qty in [(a.id,D(-1)),(b.id,D(1))]])
    db.commit()
    with pytest.raises(HTTPException, match='旧库存身份'):
        pos.position_balances(db, 'huaxing')
    with pytest.raises(HTTPException, match='旧库存身份'):
        pos.state(db, 'huaxing')


def test_new_collision_cannot_break_a_previously_readable_legacy_transfer(db):
    a = pos.create_location(db, 'huaxing', 'A', '1')
    b = pos.create_location(db, 'huaxing', 'B', '1')
    one = movement('one', '10', '2', contract_no='C|X', item_no='I')
    pos.post(db, one, location_id=a.id)
    db.add_all([CartonPositionEntry(factory_id='huaxing', inventory_key=legacy_key(one), location_id=loc,
        transfer_id='OLD', quantity=qty, occurred_at='2026-09-01') for loc, qty in [(a.id,D(-1)),(b.id,D(1))]])
    db.commit()
    before = [(r.position_key, r.balance) for r in pos.position_balances(db, 'huaxing')]
    two = movement('two', '10', '2', contract_no='C', item_no='X|I')
    with pytest.raises(HTTPException, match='旧库存身份'):
        pos.post(db, two, location_id=b.id)
    db.rollback()
    assert db.get(CartonInventoryMovement, 'two') is None
    assert [(r.position_key, r.balance) for r in pos.position_balances(db, 'huaxing')] == before
