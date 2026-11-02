"""Isolated service transactions: never open configured data or use HTTP sockets."""
import json
from decimal import Decimal as D
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session

from app.db import Base
from app.models.carton_procurement import CartonSupplier, CartonReceipt, CartonReceiptLine, CartonInventoryMovement as Movement, CartonAuditEvent as Audit, CartonClosing
from app.models.carton_positions import CartonPositionEntry
from app.models.carton_price_review import CartonPriceReview
from app.models.carton_special_requests import SpecialRequest, SpecialLine, SpecialShipment, SpecialShipmentLine, SpecialReceiptLink, SpecialVersion
from app.schemas import carton_special_requests as schema
from app.schemas.carton_procurement import CartonReceiptReverseRequest, CartonInventoryReversalRequest
from app.services import carton_special_requests as special, carton_special_stock as stock, carton_procurement as core, carton_positions as positions

FACTORY = "huaxing"
NOW = "2026-10-21T12:00:00+08:00"
USER = SimpleNamespace(id="operator", display_name="测试操作员", scopes={"read", "order_write", "inventory_write", "receipt_write", "order_adjust", "closing_manage"})
REAL_DETAIL = special.detail


@pytest.fixture
def db(monkeypatch):
    engine = create_engine("sqlite://")
    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")
    Base.metadata.create_all(engine)
    def locked_actor(db, user, factory):
        core._lock_receipt_factory(db, factory)
        return user  # IAM identity is synthetic; factory serialization/refresh is real.
    monkeypatch.setattr(special, "locked_actor", locked_actor)
    monkeypatch.setattr(special, "allowed", lambda user, factory, key: factory == FACTORY and key in user.scopes)
    monkeypatch.setattr(special, "notify", lambda *args, **kwargs: None)
    monkeypatch.setattr(core, "now_text", lambda: NOW)
    monkeypatch.setattr(core, "ensure_receipt_operation", lambda *args: None)
    monkeypatch.setattr(special.portal, "supplier_access", lambda db, user, factory: db.get(CartonSupplier, "supplier"))
    monkeypatch.setattr(special.portal, "supplier_permission", lambda user, permission, factory: factory in {FACTORY, "*"})
    from app.services import auth
    monkeypatch.setattr(auth, "authorization_decision", lambda *args: (True, "test-fixture"))
    from app.services import carton_customer_assignment
    monkeypatch.setattr(carton_customer_assignment, "allowed", lambda user, factory, key: factory == FACTORY and key in user.scopes)
    monkeypatch.setattr(special, "detail", lambda db, user, factory, identifier, **kwargs: stock.summary(db.get(SpecialRequest, identifier)))
    with Session(engine, autoflush=False, expire_on_commit=False) as session:
        session.add(CartonSupplier(id="supplier", factory_id=FACTORY, supplier_code="HEYUAN-DONGKANG",
            supplier_name="测试供应商", status="ACTIVE", created_at=NOW, updated_at=NOW))
        session.commit()
        yield session
    engine.dispose()


def paper_input(**extra):
    return {"item_no": "TEST", "packaging_type": "外箱", "paper_quality": "A33", "specification": "20*10*8",
        "dimension_unit": "cm", "quantity": "100", "unit": "个", "mark_mode": "NONE", **extra}


def command(row=None, **extra):
    return {"factory_id": FACTORY, "request_id": uuid4().hex, "expected_revision": row.revision if row else 0, **extra}


def source(db, *, kind="SAMPLE", allocations=True, quantity="100", price="2"):
    row = SpecialRequest(id="parent", factory_id=FACTORY, supplier_id="supplier", request_no="SP-PARENT",
        kind=kind, title="测试需求", requester_name="测试人", purpose="", required_date="2026-10-20", status="COMPLETED",
        revision=1, current_version_id="", quote_version_id="", pricing_kind="CHARGEABLE", promised_date="2026-10-20",
        created_by=USER.id, created_at=NOW, updated_at=NOW, origin="INTERNAL")
    db.add(row); db.flush()
    paper = SpecialLine(id="paper", factory_id=FACTORY, request_id=row.id, line_no=1,
        **{key: value for key, value in paper_input(quantity=D(quantity)).items() if key != "mark_mode"}, unit_price=D(price), mark_mode="NONE")
    db.add(paper); db.flush()
    special.version(db, USER, row, "SEND", execution=True)
    shipment = SpecialShipment(id="shipment", factory_id=FACTORY, supplier_id="supplier", request_id=row.id,
        version_id=row.current_version_id, delivery_note_no="NOTE", delivery_date="2026-10-20", created_by=USER.id, created_at=NOW)
    db.add(shipment); db.flush()
    shipped = SpecialShipmentLine(id="shipped", factory_id=FACTORY, shipment_id=shipment.id, request_line_id=paper.id,
        quantity=D(quantity), snapshot_json=special.pack(special.line_out(paper) | {"kind": kind, "pricing_kind": "CHARGEABLE",
            "customer_code": "", "customer_name": "", "request_no": row.request_no}))
    db.add(shipped); db.flush()
    receipt = CartonReceipt(id="receipt", factory_id=FACTORY, receipt_no="R1", delivery_note_no="NOTE#SP", delivery_date="2026-10-20",
        acceptance_date="2026-10-20", supplier_id="supplier", supplier_name_snapshot="测试供应商", status="POSTED", revision=2,
        created_by=USER.id, created_by_name=USER.display_name, confirmed_by=USER.id, confirmed_by_name=USER.display_name,
        created_at=NOW, updated_at=NOW, confirmed_at=NOW)
    db.add(receipt); db.flush()
    loc = positions.create_location(db, FACTORY, "测试仓", "A")
    marker = "__SAMPLE__" if kind == "SAMPLE" else "__WORKSHOP_MISC__"
    receipt_paper = CartonReceiptLine(id="receipt-paper", factory_id=FACTORY, receipt_id=receipt.id, line_no=1, source_type="AD_HOC", order_line_id=None,
        customer_code=marker, customer_name="测试需求", contract_no="", item_no=paper.item_no, packaging_type=paper.packaging_type,
        paper_quality=paper.paper_quality, specification=core._unordered_specification(paper.specification, "cm"),
        delivered_quantity=D(quantity), received_quantity=D(quantity), damaged_quantity=0, rejected_quantity=0, unusable_quantity=0,
        effective_quantity=D(quantity), unit="个", unit_price=D(price), currency="CNY", location="",
        location_allocations_json=special.pack([{"location_id": loc.id, "quantity": quantity}]) if allocations else "[]")
    db.add(receipt_paper); db.flush()
    db.add(SpecialReceiptLink(id="link", factory_id=FACTORY, shipment_line_id=shipped.id, receipt_line_id=receipt_paper.id)); db.flush()
    movement = Movement(id="incoming", **{key: getattr(receipt_paper, key) for key in ("factory_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency")},
        movement_type="INBOUND", quantity=D(quantity), location="", document_no="NOTE", source_type="RECEIPT", source_id=receipt.id,
        source_line_id=receipt_paper.id, actor_user_id=USER.id, actor_name=USER.display_name, occurred_at=NOW)
    positions.post(db, movement, allocations=[{"location_id": loc.id, "quantity": quantity}] if allocations else None)
    core._audit(db, USER, FACTORY, "RECEIPT_CONFIRMED", "carton_receipt", receipt.id)
    db.commit()
    db.expire_all()  # A browser GET reads persisted Numeric scales, as production does.
    return row, paper, receipt, receipt_paper, movement, loc


def submit(db, row, *, action="REPLENISH", quantity="20", responsibility="SUPPLIER", **extra):
    view = stock.preview(db, USER, FACTORY, row.id)
    option = next(item for item in view["lines"] if D(item["safe_quantity"]) > 0)
    fields = {"return_date": "2026-10-21"} if action == "RETURN" else {"required_date": "2026-10-25", "responsibility": responsibility}
    payload = schema.StockAction(**command(row, source_fingerprint=view["source_fingerprint"], action=action, reason="测试质量问题换补",
        lines=[{key: option[key] for key in ("receipt_line_id", "movement_id", "location_id")} | {"quantity": quantity}], **fields, **extra))
    return stock.submit(db, USER, row.id, payload, refresh_actor=lambda: USER), payload


def test_internal_misc_workshop_is_optional_but_provided_invalid_id_rejected(db):
    body = schema.Create(**command(kind="WORKSHOP_MISC", requester_name="测试人", required_date="2026-10-25", lines=[paper_input()]))
    saved = special.create(db, USER, body)
    assert db.get(SpecialRequest, saved["id"]).workshop_id == ""
    invalid = body.model_copy(update={"request_id": uuid4().hex, "workshop_id": "wrong-factory-workshop"})
    with pytest.raises(HTTPException) as err:
        special.create(db, USER, invalid)
    assert err.value.status_code == 422


@pytest.mark.parametrize("kind", ["SAMPLE", "WORKSHOP_MISC"])
def test_completed_append_keeps_receipt_and_versions_and_replays(db, kind):
    row, paper, receipt, *_ = source(db, kind=kind)
    old_version = row.current_version_id
    body = schema.Adjust(**command(row, kind=kind, requester_name=row.requester_name, required_date="2026-10-25", reason="追加实际纸品需求",
        lines=[paper_input(id=paper.id, quantity="110"), paper_input(quantity="2", item_no="NEW")]))
    saved = special.update(db, USER, row.id, body, adjusting=True)
    assert row.status == "PARTIALLY_RECEIVED" and row.current_version_id != old_version
    assert special.state_counts(db, row)[3][paper.id] == 100 and receipt.status == "POSTED"
    assert special.update(db, USER, row.id, body, adjusting=True) == saved
    assert db.scalar(select(func.count()).select_from(SpecialVersion).where(SpecialVersion.action == "ADJUSTED")) == 1


def test_special_adjustment_can_join_a_transaction_and_rollback(db):
    row, paper, *_ = source(db)
    identifier, revision, version_id, paper_id = row.id, row.revision, row.current_version_id, paper.id
    body = schema.Adjust(**command(row, kind=row.kind, required_date="2026-10-25", reason="追加实际纸品需求",
        lines=[paper_input(id=paper.id, quantity="110")]))
    special.update(db, USER, identifier, body, adjusting=True, commit=False)
    assert row.current_version_id != version_id
    db.rollback()
    assert db.get(SpecialRequest, identifier).revision == revision
    assert db.get(SpecialRequest, identifier).current_version_id == version_id
    assert special.lines(db, db.get(SpecialRequest, identifier))[0].id == paper_id


@pytest.mark.parametrize("changes", [{"quantity": "99"}, {"specification": "99*99*99"}, {"quantity": "100"}])
def test_completed_append_rejects_reduction_material_rewrite_or_noop(db, changes):
    row, paper, *_ = source(db)
    body = schema.Adjust(**command(row, kind=row.kind, required_date="2026-10-25", reason="测试调整实际需求", lines=[paper_input(id=paper.id, **changes)]))
    with pytest.raises(HTTPException) as err: special.update(db, USER, row.id, body, adjusting=True)
    assert err.value.status_code == 409


@pytest.mark.parametrize("kind", ["SAMPLE", "WORKSHOP_MISC"])
def test_completed_flags_only_append_and_stock_actions(db, kind):
    row, *_ = source(db, kind=kind)
    flags = special.flags(db, USER, row, False)
    assert flags["can_append"] and flags["can_return_stock"] and flags["can_replenish"]
    assert not flags["can_adjust"] and not flags["can_cancel"]


def test_replenish_real_child_debit_immutable_parent_demand_and_replay(db):
    row, paper, _, _, incoming, _ = source(db)
    result, payload = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    debit = db.get(Movement, result["movement_ids"][0])
    assert child.origin == stock.ORIGIN and child.current_version_id and child.status == "SENT"
    assert debit.quantity == -20 and debit.source_type == "SPECIAL_REPLENISHMENT" and debit.order_line_id is None
    assert paper.quantity == 100 and special.state_counts(db, row)[3][paper.id] == 100
    assert special.lines(db, child)[0].specification == paper.specification
    assert stock.submit(db, USER, row.id, payload, refresh_actor=lambda: USER) == result
    flags = special.flags(db, USER, child, False)
    assert flags["can_undo_replenish"] and not any(flags[key] for key in ("can_adjust", "can_append", "can_cancel", "can_delete"))
    assert stock.preview(db, USER, FACTORY, child.id)["replacement"]["parent_request_no"] == row.request_no


def test_return_real_stock_and_exact_supplier_evidence_without_cancelling_demand(db):
    from app.services.carton_supplier_settlement import return_supplier, sources
    from app.services.carton_return_dates import dates
    row, paper, *_ = source(db)
    result, _ = submit(db, row, action="RETURN")
    movement = db.get(Movement, result["movement_ids"][0])
    assert movement.source_type == "SPECIAL_RETURN" and movement.issue_kind == "RETURN"
    assert return_supplier(db, movement) == "supplier" and dates(db, FACTORY)[movement.id] == "2026-10-21"
    assert row.status == "COMPLETED" and paper.quantity == 100
    assert db.scalar(select(Audit.id).where(Audit.event_type == "RETURN_COLLABORATION_OPENED", Audit.entity_id == movement.id))


def test_unallocated_historical_receipt_has_no_fake_source_stock(db):
    row, *_ = source(db, allocations=False)
    view = stock.preview(db, USER, FACTORY, row.id)
    assert not view["can_replenish"] and not view["lines"] and view["blockers"]


def extra_movement(db, incoming, location, qty, *, allocated=True, transfer=False):
    movement = Movement(**{key: getattr(incoming, key) for key in ("factory_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit", "unit_price", "currency")},
        id=uuid4().hex, quantity=D(qty), movement_type="OUTBOUND" if D(qty) < 0 else "INBOUND", document_no="OTHER", location="",
        source_type="MANUAL", source_id=uuid4().hex, source_line_id=uuid4().hex, actor_user_id=USER.id, actor_name=USER.display_name,
        occurred_at=NOW)
    if allocated: positions.post(db, movement, location_id=location.id)
    else: db.add(movement)
    core._audit(db, USER, FACTORY, "INVENTORY_MOVEMENT_CREATED", "carton_inventory_movement", movement.id)
    db.commit()
    return movement


def test_proof_uses_position_posting_order_and_never_credits_unrelated_inbound(db):
    row, _, _, _, incoming, loc = source(db)
    movement = extra_movement(db, incoming, loc, "-30")
    # Position posting sequence remains decisive even if an evidence timestamp is historical.
    db.scalar(select(CartonPositionEntry).where(CartonPositionEntry.movement_id == movement.id)).occurred_at = "2026-10-01T12:00:00+08:00"
    db.commit()
    extra_movement(db, incoming, loc, "90")
    assert D(stock.preview(db, USER, FACTORY, row.id)["lines"][0]["safe_quantity"]) == 70


def test_missing_historical_debit_location_blocks_source_proof(db):
    row, _, _, _, incoming, loc = source(db)
    extra_movement(db, incoming, loc, "-30", allocated=False)
    assert not stock.preview(db, USER, FACTORY, row.id)["can_return"]


def test_unknown_cost_or_changed_parent_material_is_blocked(db):
    row, paper, *_ = source(db)
    paper.specification = "99*99*99"; db.commit()
    assert not stock.preview(db, USER, FACTORY, row.id)["can_return"]


def test_stale_fingerprint_atomic_no_debit_and_live_actor_before_replay(db):
    row, _, _, _, incoming, loc = source(db)
    result, payload = submit(db, row)
    denied = SimpleNamespace(id=USER.id, display_name=USER.display_name, scopes={"read", "order_write"})
    with pytest.raises(HTTPException) as err:
        stock.submit(db, USER, row.id, payload, refresh_actor=lambda: denied)
    assert err.value.status_code == 403
    stale = payload.model_copy(update={"request_id": uuid4().hex, "expected_revision": row.revision})
    with pytest.raises(HTTPException) as err: stock.submit(db, USER, row.id, stale, refresh_actor=lambda: USER)
    assert err.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Movement).where(Movement.source_type == "SPECIAL_REPLENISHMENT")) == 1


def test_parent_receipt_and_generic_replacement_debit_reversals_protected(db):
    row, _, receipt, *_ = source(db)
    result, _ = submit(db, row)
    with pytest.raises(HTTPException) as err:
        core.reverse_receipt(db, receipt.id, CartonReceiptReverseRequest(factory_id=FACTORY, expected_revision=receipt.revision, reason="核实原单收料冲销"), USER)
    assert err.value.status_code == 409
    with pytest.raises(HTTPException) as err:
        core.reverse_inventory_movement(db, result["movement_ids"][0], CartonInventoryReversalRequest(factory_id=FACTORY, reason="核实原单库存冲销"), USER)
    assert err.value.status_code == 409


def test_undo_child_restores_exact_debit_and_is_idempotent(db):
    row, *_ = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    payload = schema.Delete(**command(child, reason="尚未发货取消补单"))
    saved = stock.undo(db, USER, child.id, payload, refresh_actor=lambda: USER)
    assert child.status == "CANCELLED" and db.get(Movement, saved["movement_ids"][0]).quantity == 20
    assert stock.undo(db, USER, child.id, payload, refresh_actor=lambda: USER) == saved
    assert D(stock.preview(db, USER, FACTORY, row.id)["lines"][0]["safe_quantity"]) == 80  # reversal is not ownership proof


@pytest.mark.parametrize("responsibility,price", [("SUPPLIER", None), ("OWN", "3")])
def test_real_child_receiving_restores_cost_or_payable_with_exact_link(db, responsibility, price):
    from app.services.carton_special_manual_receiving import receive
    from app.services.carton_inventory_valuation import load_valuation
    from app.services.carton_supplier_settlement import sources
    row, _, _, _, _, loc = source(db)
    result, _ = submit(db, row, responsibility=responsibility)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    line = special.lines(db, child)[0]
    payload = schema.ManualReceive(**command(child, delivery_note_no="CHILD-NOTE", delivery_date="2026-10-21", acceptance_date="2026-10-21",
        lines=[{"line_id": line.id, "received_quantity": "20", "unit_price": price,
            "location_allocations": [{"location_id": loc.id, "quantity": "20"}]}]))
    receive(db, USER, child.id, payload)
    event = db.scalar(select(Audit).where(Audit.event_type == stock.LINK_EVENT))
    assert event and json.loads(event.detail_json)["child_request_id"] == child.id
    linked_line = db.get(CartonReceiptLine, event.entity_id)
    rendered = core.receipt_out(db, db.get(CartonReceipt, linked_line.receipt_id)).model_dump(mode="json")
    displayed = next(item for item in rendered["lines"] if item["id"] == linked_line.id)
    assert displayed["child_request_id"] == child.id and displayed["parent_request_id"] == row.id
    assert displayed["replenishment_issue_id"] is None  # Never fabricate a formal issue.
    assert D(displayed["settlement_unit_price"]) == (0 if responsibility == "SUPPLIER" else 3)
    valuation = load_valuation(db, FACTORY)
    inbound = db.scalar(select(Movement).where(Movement.source_line_id == linked_line.id))
    assert not valuation.errors and valuation.amounts[inbound.id] == (40 if responsibility == "SUPPLIER" else 60)
    review = db.scalar(select(CartonPriceReview).where(CartonPriceReview.receipt_line_id == linked_line.id))
    payable, *_ = sources(db, FACTORY, "supplier", "2026-10", "CNY")
    child_payable = [item for item in payable if item.get("source_key") == "RECEIPT:" + linked_line.id]
    assert (not review and not child_payable) if responsibility == "SUPPLIER" else (review and len(child_payable) == 1)
    if responsibility == "SUPPLIER":
        from app.services.carton_price_correction import source as correction_source
        correction = correction_source(db, FACTORY, linked_line.id)
        assert correction["payable"] == 0 and correction["original_supplier_price"] is None
        assert correction["invalid"]
        from app.services.carton_settlement_collaboration import build
        projection = build(db, FACTORY, "supplier", "2026-10", "CNY", payable, "test")
        entry = next(item for item in projection["unsettled_shipments"] if item["document_no"] == "CHILD-NOTE")
        assert entry["reason"] == "供应商责任补单，恢复库存成本，不计应结"
        assert entry["original_unit_price"] is None
    with pytest.raises(HTTPException):
        stock.undo(db, USER, child.id, schema.Delete(**command(child, reason="已收货不可撤销补单")), refresh_actor=lambda: USER)


def test_repeated_partial_returns_keep_distinct_debit_identity(db):
    row, *_ = source(db)
    first, _ = submit(db, row, action="RETURN", quantity="10")
    second, _ = submit(db, row, action="RETURN", quantity="15")
    assert set(first["movement_ids"]).isdisjoint(second["movement_ids"])
    assert D(stock.preview(db, USER, FACTORY, row.id)["lines"][0]["safe_quantity"]) == 75


def test_one_return_can_debit_two_original_bins_without_source_collision(db):
    row, _, _, paper, incoming, first = source(db)
    second = positions.create_location(db, FACTORY, "测试仓", "B")
    entry = db.scalar(select(CartonPositionEntry).where(CartonPositionEntry.movement_id == incoming.id))
    entry.quantity = 50
    db.add(CartonPositionEntry(factory_id=FACTORY, inventory_key=entry.inventory_key, location_id=second.id,
        movement_id=incoming.id, quantity=50, transfer_id="", occurred_at=NOW))
    paper.location_allocations_json = special.pack([{"location_id": first.id, "quantity": "50"}, {"location_id": second.id, "quantity": "50"}])
    db.commit()
    view = stock.preview(db, USER, FACTORY, row.id)
    payload = schema.StockAction(**command(row, action="RETURN", return_date="2026-10-21", reason="两仓实际退货核实",
        source_fingerprint=view["source_fingerprint"], lines=[{key: item[key] for key in ("receipt_line_id", "movement_id", "location_id")} | {"quantity": "10"} for item in view["lines"]]))
    result = stock.submit(db, USER, row.id, payload, refresh_actor=lambda: USER)
    assert len(result["movement_ids"]) == 2
    assert all(D(item["safe_quantity"]) == 40 for item in stock.preview(db, USER, FACTORY, row.id)["lines"])


def test_seeded_unknown_debit_never_becomes_exact_bin_ownership(db):
    row, _, _, _, incoming, _ = source(db)
    other = positions.create_location(db, FACTORY, "测试仓", "OTHER")
    extra_movement(db, incoming, other, "100")
    extra_movement(db, incoming, other, "-80", allocated=False)
    positions.seed_unallocated(db, FACTORY); db.commit()
    view = stock.preview(db, USER, FACTORY, row.id)
    assert not view["can_return"] and not view["can_replenish"]
    assert any("分仓" in text for text in view["lines"][0]["blockers"])


def test_replay_payload_mismatch_and_revoked_session_do_not_post(db):
    row, *_ = source(db)
    _, payload = submit(db, row)
    with pytest.raises(HTTPException) as error:
        stock.submit(db, USER, row.id, payload.model_copy(update={"reason": "相同标识不同操作原因"}), refresh_actor=lambda: USER)
    assert error.value.status_code == 409
    def revoked(): raise HTTPException(401, "session revoked")
    with pytest.raises(HTTPException) as error:
        stock.submit(db, USER, row.id, payload, refresh_actor=revoked)
    assert error.value.status_code == 401
    assert db.scalar(select(func.count()).select_from(Movement).where(Movement.source_type == "SPECIAL_REPLENISHMENT")) == 1


def test_live_customer_scope_is_rechecked_before_successful_replay(db, monkeypatch):
    row, *_ = source(db)
    _, payload = submit(db, row)
    def denied(*args): raise HTTPException(403, "客户已转交其他负责人")
    monkeypatch.setattr(special, "customer_access", denied)
    with pytest.raises(HTTPException) as error:
        stock.submit(db, USER, row.id, payload, refresh_actor=lambda: USER)
    assert error.value.status_code == 403


@pytest.mark.parametrize("factory", ["huakang-a", "invalid-factory"])
def test_cross_factory_sources_are_rejected_without_stock_preview(db, factory):
    row, *_ = source(db)
    with pytest.raises(HTTPException) as error: stock.preview(db, USER, factory, row.id)
    assert error.value.status_code in {403, 404, 422}


def lock_inventory(db, customer="__SAMPLE__"):
    db.add(CartonClosing(id="closing", factory_id=FACTORY, period="2026-10", customer_code=customer, customer_name="测试需求",
        opening_quantity=0, inbound_quantity=100, outbound_quantity=0, adjustment_quantity=0, ending_quantity=100,
        ending_amount=200, currency="CNY", status="LOCKED", revision=1, generated_by=USER.id,
        generated_by_name=USER.display_name, generated_at=NOW))
    db.commit()


def confirm_supplier_month(db):
    from app.models.carton_supplier_settlement import CartonSupplierSettlement
    db.add(CartonSupplierSettlement(id="settlement", factory_id=FACTORY, supplier_id="supplier", period="2026-10", currency="CNY",
        version=1, revision=1, status="CONFIRMED", source_fingerprint="test", created_at=NOW, updated_at=NOW, created_by=USER.id))
    db.commit()


@pytest.mark.parametrize("lock", [lock_inventory, confirm_supplier_month])
def test_inventory_or_supplier_month_blocks_new_stock_action_atomically(db, lock):
    row, *_ = source(db)
    lock(db)
    with pytest.raises(HTTPException) as error: submit(db, row)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(Movement).where(Movement.source_type == "SPECIAL_REPLENISHMENT")) == 0
    assert db.scalar(select(func.count()).select_from(SpecialRequest)) == 1


@pytest.mark.parametrize("lock", [lock_inventory, confirm_supplier_month])
def test_month_lock_is_visible_and_blocks_dedicated_undo(db, lock):
    row, *_ = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    lock(db)
    preview = stock.preview(db, USER, FACTORY, child.id)
    assert preview["replacement"]["blockers"] and not preview["replacement"]["can_undo"]
    with pytest.raises(HTTPException) as error:
        stock.undo(db, USER, child.id, schema.Delete(**command(child, reason="月份锁定不能撤销")), refresh_actor=lambda: USER)
    assert error.value.status_code == 409 and child.status == "SENT"


def receive_child(db, row, loc, *, quantity="20", note="CHILD-COST"):
    from app.services.carton_special_manual_receiving import receive
    line = special.lines(db, row)[0]
    receive(db, USER, row.id, schema.ManualReceive(**command(row, delivery_note_no=note,
        delivery_date="2026-10-21", acceptance_date="2026-10-21", lines=[{"line_id": line.id,
            "received_quantity": quantity, "location_allocations": [{"location_id": loc.id, "quantity": quantity}]}])))
    source_line = db.scalar(select(SpecialShipmentLine).join(SpecialShipment, SpecialShipment.id == SpecialShipmentLine.shipment_id)
        .where(SpecialShipment.request_id == row.id, SpecialShipment.delivery_note_no == note))
    receipt_line = db.scalar(select(CartonReceiptLine).join(SpecialReceiptLink, SpecialReceiptLink.receipt_line_id == CartonReceiptLine.id)
        .where(SpecialReceiptLink.shipment_line_id == source_line.id))
    return db.scalar(select(Movement).where(Movement.source_type == "RECEIPT", Movement.source_line_id == receipt_line.id))


def correct_original_price(db, line_id, price):
    """Use the actual propose → supplier agree → supervisor impact confirmation flow."""
    from app.schemas.carton_price_correction import Action
    from app.services import carton_price_correction as correction
    for action in ("PROPOSE", "SUPPLIER_CONFIRM", "FINAL_CONFIRM"):
        current = correction.source(db, FACTORY, line_id)
        assert not current["invalid"], (action, current["invalid"])
        if action != "PROPOSE":
            assert current["source_fingerprint"] == current["state"]["proposal"]["source_fingerprint"], action
        kwargs = dict(factory_id=FACTORY, request_id=uuid4().hex, expected_revision=current["state"]["revision"],
            source_fingerprint=current["source_fingerprint"], action=action, reason="按原凭证双边核实价格")
        if action == "PROPOSE":
            kwargs.update(proposed_unit_price=price, document_no="PRICE-" + uuid4().hex[:8], document_date="2026-10-21")
        if action == "FINAL_CONFIRM":
            preview = correction.impact(db, current, D(price))
            assert preview["can_apply"], preview["blockers"]
            kwargs["impact_fingerprint"] = preview["impact_fingerprint"]
        correction.act(db, USER, line_id, Action(**kwargs), external=action == "SUPPLIER_CONFIRM")


@pytest.mark.parametrize("correction_before_receipt", [False, True])
def test_real_receipt_links_propagate_later_exact_cost_correction_once(db, correction_before_receipt):
    from app.services.carton_inventory_valuation import load_valuation
    row, _, _, original_line, incoming, loc = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    if correction_before_receipt:
        correct_original_price(db, original_line.id, "3")
    replacement_inbound = receive_child(db, child, loc)
    valuation = load_valuation(db, FACTORY)
    assert not valuation.errors
    assert valuation.amounts[replacement_inbound.id] == (60 if correction_before_receipt else 40)
    correct_original_price(db, original_line.id, "4")
    valuation = load_valuation(db, FACTORY)
    assert not valuation.errors and valuation.amounts[replacement_inbound.id] == 80
    assert db.scalar(select(func.count()).select_from(CartonPriceReview).where(CartonPriceReview.receipt_line_id == replacement_inbound.source_line_id)) == 0
    from app.services.carton_supplier_settlement import sources
    assert all(item.get("source_key") != "RECEIPT:" + replacement_inbound.source_line_id for item in sources(db, FACTORY, "supplier", "2026-10", "CNY")[0])


def test_real_multi_generation_supplier_replacement_restores_cost_recursively(db):
    from app.services.carton_inventory_valuation import load_valuation
    row, _, _, original_line, incoming, loc = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    receive_child(db, child, loc)
    second, _ = submit(db, child, quantity="10")
    grandchild = db.get(SpecialRequest, second["replenishment_request"]["id"])
    new_inbound = receive_child(db, grandchild, loc, quantity="10", note="GRANDCHILD-COST")
    correct_original_price(db, original_line.id, "3")
    result = load_valuation(db, FACTORY)
    assert not result.errors and result.amounts[new_inbound.id] == 30
    assert stock.replacement(db, grandchild)["parent_request_id"] == child.id


def test_completed_append_preserves_existing_workshop_identity(db):
    from app.models.carton_master import CartonMasterRecord
    row, paper, *_ = source(db, kind="WORKSHOP_MISC")
    db.add(CartonMasterRecord(id="legacy-workshop", factory_id=FACTORY, kind="WORKSHOP", identity="W", code="原车间", status="ACTIVE"))
    row.workshop_id = "legacy-workshop"; db.commit()
    payload = schema.Adjust(**command(row, kind=row.kind, workshop_id=row.workshop_id, required_date="2026-10-25", reason="保留车间历史加单",
        lines=[paper_input(id=paper.id, quantity="110")]))
    special.update(db, USER, row.id, payload, adjusting=True)
    assert row.workshop_id == "legacy-workshop"
    with pytest.raises(HTTPException) as error:
        special.update(db, USER, row.id, payload.model_copy(update={"workshop_id": "", "request_id": uuid4().hex, "expected_revision": row.revision}), adjusting=True)
    assert error.value.status_code == 422


def test_all_selected_stock_sources_validate_before_any_child_or_debit(db):
    row, *_ = source(db)
    view = stock.preview(db, USER, FACTORY, row.id)
    option = view["lines"][0]
    good = {key: option[key] for key in ("receipt_line_id", "movement_id", "location_id")} | {"quantity": "10"}
    payload = schema.StockAction(**command(row, action="REPLENISH", responsibility="OWN", required_date="2026-10-25",
        reason="核实两项实际库存来源", source_fingerprint=view["source_fingerprint"],
        lines=[good, {**good, "location_id": "other-factory-bin"}]))
    with pytest.raises(HTTPException) as error:
        stock.submit(db, USER, row.id, payload, refresh_actor=lambda: USER)
    assert error.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(SpecialRequest)) == 1
    assert db.scalar(select(func.count()).select_from(Movement)) == 1


def test_zero_unknown_inventory_cost_cannot_be_replaced(db):
    row, *_ = source(db, price="0")
    view = stock.preview(db, USER, FACTORY, row.id)
    assert not view["can_replenish"] and view["lines"][0]["inventory_unit_price"] is None


def test_receipt_reversal_and_exact_original_note_reentry_keep_replacement_cost(db):
    from app.services.carton_inventory_valuation import load_valuation
    row, _, _, _, _, loc = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    inbound = receive_child(db, child, loc)
    receipt = db.get(CartonReceipt, inbound.source_id)
    core.reverse_receipt(db, receipt.id, CartonReceiptReverseRequest(factory_id=FACTORY,
        expected_revision=receipt.revision, reason="原收料数量核实更正"), USER)
    shipment = db.scalar(select(SpecialShipment).where(SpecialShipment.request_id == child.id))
    shipped_line = db.scalar(select(SpecialShipmentLine).where(SpecialShipmentLine.shipment_id == shipment.id))
    special.receive(db, USER, child.id, shipment.id, schema.Receive(**command(child, acceptance_date="2026-10-21",
        lines=[{"shipment_line_id": shipped_line.id, "received_quantity": "20",
            "location_allocations": [{"location_id": loc.id, "quantity": "20"}]}])))
    valuation = load_valuation(db, FACTORY)
    assert not valuation.errors and child.status == "COMPLETED"
    assert len(list(db.scalars(select(Audit).where(Audit.event_type == stock.LINK_EVENT)))) == 2
    assert sum(valuation.amounts.values()) == 200


def test_supplier_child_cannot_be_changed_cancelled_deleted_or_quoted_chargeable(db):
    row, *_ = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    line = special.lines(db, child)[0]
    operations = [
        lambda: special.update(db, USER, child.id, schema.Adjust(**command(child, kind=child.kind, required_date=child.required_date,
            reason="尝试改写冻结补单", lines=[paper_input(id=line.id, quantity="30")])), adjusting=True),
        lambda: special.action(db, USER, child.id, schema.Command(**command(child)), "CANCEL"),
        lambda: special.delete_request(db, USER, child.id, schema.Delete(**command(child, reason="尝试删除冻结补单"))),
        lambda: special.action(db, USER, child.id, schema.Quote(**command(child, version_id=child.current_version_id,
            pricing_kind="CHARGEABLE", promised_date=child.required_date, lines=[{"line_id": line.id, "unit_price": "3"}])), "QUOTE", external=True),
    ]
    for operation in operations:
        with pytest.raises(HTTPException) as error: operation()
        assert error.value.status_code in {409, 422}
        db.rollback()
    assert child.status == "SENT" and line.quantity == 20


def test_supplier_child_rejects_chargeable_warehouse_recording(db):
    from app.services.carton_special_manual_receiving import receive
    row, _, _, _, _, loc = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    with pytest.raises(HTTPException) as error:
        receive(db, USER, child.id, schema.ManualReceive(**command(child, delivery_note_no="BAD-PRICE",
            delivery_date="2026-10-21", acceptance_date="2026-10-21", lines=[{"line_id": special.lines(db, child)[0].id,
                "received_quantity": "20", "unit_price": "3", "location_allocations": [{"location_id": loc.id, "quantity": "20"}]}])))
    assert error.value.status_code == 422
    assert not db.scalar(select(SpecialShipment.id).where(SpecialShipment.request_id == child.id))


def test_optional_legacy_own_link_price_remains_unknown_in_public_history():
    from app.services.carton_replenishment_receipts import public_link
    value = public_link({"responsibility": "OWN", "child_request_id": "child"})
    assert value["settlement_unit_price"] is None and value["child_request_id"] == "child"


@pytest.mark.parametrize("manual", [True, False])
def test_external_special_feedback_and_unified_note_show_free_settlement_not_stock_cost(db, monkeypatch, manual):
    from app.services import carton_unified_deliveries
    from app.services.carton_price_correction import source as correction_source
    row, _, _, _, _, loc = source(db)
    result, _ = submit(db, row)
    child = db.get(SpecialRequest, result["replenishment_request"]["id"])
    if manual:
        inbound = receive_child(db, child, loc, note="FREE-MANUAL")
    else:
        # Immutable evidence from an actual supplier-entered free note, without
        # the WAREHOUSE_MANUAL absence of original supplier price evidence.
        line = special.lines(db, child)[0]
        shipment = SpecialShipment(id="supplier-free-note", factory_id=FACTORY, supplier_id=child.supplier_id,
            request_id=child.id, version_id=child.current_version_id, delivery_note_no="FREE-SUPPLIER",
            delivery_date="2026-10-21", created_by=USER.id, created_at=NOW)
        db.add(shipment); db.flush()
        shipped = SpecialShipmentLine(id="supplier-free-paper", factory_id=FACTORY, shipment_id=shipment.id,
            request_line_id=line.id, quantity=20, snapshot_json=special.pack(special.line_out(line) | {
                "pricing_kind": "FREE", "customer_code": child.customer_code, "customer_name": child.customer_name,
                "kind": child.kind, "request_no": child.request_no}))
        db.add(shipped); db.commit()
        special.receive(db, USER, child.id, shipment.id, schema.Receive(**command(child, acceptance_date="2026-10-21",
            lines=[{"shipment_line_id": shipped.id, "received_quantity": "20",
                "location_allocations": [{"location_id": loc.id, "quantity": "20"}]}])))
        receipt_line = db.scalar(select(CartonReceiptLine).join(SpecialReceiptLink, SpecialReceiptLink.receipt_line_id == CartonReceiptLine.id)
            .where(SpecialReceiptLink.shipment_line_id == shipped.id))
        inbound = db.scalar(select(Movement).where(Movement.source_type == "RECEIPT", Movement.source_line_id == receipt_line.id))

    # Run the production special detail and unified note projections, bypassing
    # only unrelated mark-library discovery in this isolated stock fixture.
    def actual_detail(db, user, factory, identifier, **kwargs):
        return REAL_DETAIL(db, user, factory, identifier, mark_assets_by_order={}, **kwargs)
    monkeypatch.setattr(special, "detail", actual_detail)
    external = special.detail(db, USER, FACTORY, child.id, external=True)
    internal = special.detail(db, USER, FACTORY, child.id)
    supplier_paper = external["shipments"][0]["receipts"][0]["lines"][0]
    internal_paper = internal["shipments"][0]["receipts"][0]["lines"][0]
    assert D(supplier_paper["unit_price"]) == 0
    assert D(internal_paper["unit_price"]) == 2 and inbound.unit_price == 2
    projected = carton_unified_deliveries.project(db, USER, FACTORY,
        "SPECIAL:" + external["shipments"][0]["id"], external=True)
    assert D(projected["receipts"][0]["lines"][0]["unit_price"]) == 0
    assert projected["lines"][0]["delivery_unit_price"] is None if manual else D(projected["lines"][0]["delivery_unit_price"]) == 0
    by_line, evidence = special.settlement_evidence(db, FACTORY, child.supplier_id, "2026-10")
    assert by_line[inbound.source_line_id]["unit_price"] == "0"
    assert by_line[inbound.source_line_id]["original_unit_price"] is None if manual else D(by_line[inbound.source_line_id]["original_unit_price"]) == 0
    current = correction_source(db, FACTORY, inbound.source_line_id)
    assert current["payable"] == 0
    assert current["original_supplier_price"] is None if manual else D(current["original_supplier_price"]) == 0
    frozen = db.scalar(select(SpecialShipmentLine).join(SpecialShipment, SpecialShipment.id == SpecialShipmentLine.shipment_id)
        .where(SpecialShipment.request_id == child.id))
    assert D(json.loads(frozen.snapshot_json)["unit_price"]) == 0  # Carrying cost was never copied into vendor evidence.
