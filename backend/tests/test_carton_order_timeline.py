import json
from decimal import Decimal as D

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.carton_procurement import (
    CartonAuditEvent as Audit, CartonInventoryMovement as Movement, CartonOrder as Order,
    CartonOrderLine as Line, CartonPurchaseOrderIssue as Issue,
    CartonReceipt as Receipt, CartonReceiptLine as ReceiptLine,
)
from app.services.carton_order_timeline import order_timeline
from test_carton_inventory_report import movement, order_line, seed


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for model in (Order, Line, Movement, Audit, Receipt, ReceiptLine, Issue):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def audit(id, kind, entity, detail=None, *, at="2026-09-01T09:00:00+08:00", factory="huaxing", entity_type="carton_order"):
    return Audit(id=id, factory_id=factory, event_type=kind, entity_type=entity_type, entity_id=entity,
                 detail_json=json.dumps(detail or {}), actor_user_id="u", actor_name="User", created_at=at)


def test_order_snapshots_not_current_totals_and_cancelled_orders_remain(db):
    order_line(db, "l", status="CANCELLED")
    seed(db, audit("created", "ORDER_CREATED", "order-l"),
         audit("append", "ORDER_APPENDED", "order-l", {"before_quantity": "100", "after_quantity": "150"}),
         audit("reduce", "ORDER_REDUCED", "order-l", {"before_quantity": "150", "after_quantity": "120", "reason": "客人减单"}),
         audit("cancel", "ORDER_CANCELLED", "order-l"))
    db.get(Order, "order-l").product_order_quantity = D(999)
    db.commit()
    rows = order_timeline(db, "huaxing").events
    assert [row.event_type for row in rows] == ["ORDER_CREATED", "ORDER_APPENDED", "ORDER_REDUCED", "ORDER_CANCELLED"]
    assert rows[0].quantity_change is None
    assert "未保存" in rows[0].description
    assert (rows[1].quantity_before, rows[1].quantity_change, rows[1].quantity_after) == ("100", "50", "150")
    assert rows[2].quantity_change == "-30"
    assert rows[2].quantity_basis == "ORDER_PRODUCT"
    assert rows[2].unit == "件"


def test_creation_and_modification_use_captured_snapshots(db):
    order_line(db, "l")
    seed(db, audit("create", "ORDER_CREATED", "order-l", {"product_order_quantity": "80", "item_no": "OLD-ITEM"}),
         audit("edit", "ORDER_UPDATED", "order-l", {
             "before": {"product_order_quantity": "80", "due_date": "2026-09-10", "contract_no": "OLD"},
             "after": {"product_order_quantity": "100", "due_date": "2026-09-12", "contract_no": "NEW"}}))
    rows = order_timeline(db, "huaxing").events
    assert rows[0].quantity_change == "80"
    assert rows[0].quantity_after == "80"
    assert rows[0].item_no == "OLD-ITEM"
    assert rows[1].quantity_change == "20"
    assert rows[1].description == "合同：OLD → NEW；计划交期：2026-09-10 → 2026-09-12"


def test_exact_order_all_lines_search_and_factory_customer_isolation(db):
    order_line(db, "box", order_id="first")
    order_line(db, "sheet", order_id="first", line_no=2, packaging="滑板纸", unit="张")
    order_line(db, "duplicate", order_id="second")
    order_line(db, "foreign", factory="huadeng")
    seed(db, audit("a", "ORDER_CREATED", "first"), audit("b", "ORDER_CREATED", "second"),
         audit("foreign-a", "ORDER_CREATED", "order-foreign", factory="huadeng"),
         movement("box-in", "10", order_line_id="box", document_no="UNIQUE-DN"),
         movement("sheet-in", "100", order_line_id="sheet", packaging_type="滑板纸", unit="张"),
         movement("wrong", "500", order_line_id="duplicate"),
         movement("foreign", "900", order_line_id="foreign", factory_id="huadeng"))
    rows = order_timeline(db, "huaxing", search="unique-dn").events
    assert {row.id for row in rows} == {"audit:a", "movement:box-in", "movement:sheet-in"}
    assert {row.order_id for row in rows} == {"first"}
    assert len(order_timeline(db, "huaxing", order_id="first").events) == 3
    assert not order_timeline(db, "huaxing", order_id="order-foreign").events
    assert not order_timeline(db, "huaxing", customer_code="C2").events


def receipt(db, id="receipt", effective="10"):
    seed(db, Receipt(id=id, factory_id="huaxing", receipt_no="RC", delivery_note_no="DN",
                     delivery_date="2026-08-01", supplier_id="s", supplier_name_snapshot="Supplier",
                     status="POSTED", created_by="u", created_at="2026-09-01T09:00:00+08:00",
                     updated_at="2026-09-01T09:00:00+08:00"),
         ReceiptLine(id="rl", factory_id="huaxing", receipt_id=id, line_no=1, order_line_id="l",
                     source_type="FORMAL_ORDER", customer_code="C1", customer_name="Customer",
                     contract_no="CONTRACT", item_no="ITEM", packaging_type="外箱", paper_quality="A33",
                     specification="1x1x1", delivered_quantity=D(effective), received_quantity=D(effective),
                     effective_quantity=D(effective), unit="个"))


def test_receipt_save_confirmation_reversal_are_not_double_counted_and_dates_use_posting(db):
    order_line(db, "l")
    receipt(db)
    seed(db, audit("save", "RECEIPT_DRAFT_CREATED", "receipt", entity_type="carton_receipt", at="2026-08-31T16:00:00Z"),
         audit("confirm", "RECEIPT_CONFIRMED", "receipt", entity_type="carton_receipt"),
         audit("undo", "INVENTORY_MOVEMENT_REVERSED", "in", {"reversal_id": "reverse"},
               entity_type="carton_inventory_movement", at="2026-09-02T09:00:00+08:00"),
         audit("undo-receipt", "RECEIPT_REVERSED", "receipt", {"previous_status": "POSTED"},
               entity_type="carton_receipt", at="2026-09-02T09:00:00+08:00"),
         movement("in", "10", order_line_id="l", source_type="RECEIPT", source_id="receipt"),
         movement("reverse", "-10", order_line_id="l", movement_type="REVERSAL", reversal_of_movement_id="in",
                  at="2026-09-02T09:00:00+08:00"))
    rows = order_timeline(db, "huaxing").events
    assert [row.event_label for row in rows] == ["保存收料单", "确认入库", "入库冲销"]
    assert rows[0].quantity_change is None
    assert sum(D(row.quantity_change or "0") for row in rows) == 0
    assert rows[-1].quantity_before == "10.0000" and rows[-1].quantity_after == "0.0000"
    filtered = order_timeline(db, "huaxing", date_from="2026-09-01", date_to="2026-09-01")
    assert len(filtered.events) == 2
    assert filtered.events[0].occurred_at.startswith("2026-09-01T00:00:00")


def test_same_second_sequence_preserves_balances_and_product_vs_paper_units(db):
    order_line(db, "l")
    seed(db, audit("append", "ORDER_APPENDED", "order-l", {"before_quantity": 100, "after_quantity": 120}),
         audit("in", "INVENTORY_MOVEMENT_CREATED", "z-in", entity_type="carton_inventory_movement"),
         audit("out", "INVENTORY_MOVEMENT_CREATED", "a-out", entity_type="carton_inventory_movement"),
         movement("z-in", "12", order_line_id="l"), movement("a-out", "-6", order_line_id="l"))
    rows = order_timeline(db, "huaxing").events
    assert [row.id for row in rows] == ["audit:append", "movement:z-in", "movement:a-out"]
    assert [(row.quantity_change, row.quantity_basis) for row in rows] == [
        ("20", "ORDER_PRODUCT"), ("12.0000", "INVENTORY"), ("-6.0000", "INVENTORY")]
    assert (rows[-1].quantity_before, rows[-1].quantity_after) == ("12.0000", "6.0000")


def test_standalone_identity_relocation_and_price_confirmation_do_not_change_stock(db):
    seed(db, movement("standalone", "2"), movement("other", "8", unit="张"),
         audit("relocate", "INVENTORY_LOCATION_CHANGED", "location", {
             "reference_movement_id": "standalone", "from_location": "A", "to_location": "B"},
               entity_type="carton_inventory_location"),
         audit("price", "INVENTORY_PRICE_CONFIRMED", "standalone", {"unit_price": "2.8", "currency": "CNY"},
               entity_type="carton_inventory_movement"))
    all_rows = order_timeline(db, "huaxing").events
    key = next(row.inventory_key for row in all_rows if row.id == "movement:standalone")
    rows = order_timeline(db, "huaxing", inventory_key=key).events
    assert len(rows) == 3
    assert all(row.order_id is None for row in rows)
    assert sum(D(row.quantity_change or "0") for row in rows) == 2
    assert next(row for row in rows if row.event_label == "调仓").description == "仓位：A → B；数量不变。"
    with pytest.raises(HTTPException) as error:
        order_timeline(db, "huaxing", order_id="o", inventory_key=key)
    assert error.value.status_code == 422


def test_issued_document_links_by_order_id_and_does_not_repeat_quantity_change(db):
    order_line(db, "l", order_id="first")
    order_line(db, "same", order_id="second")
    seed(db, Issue(id="issue", factory_id="huaxing", order_id="first", order_no="first", document_no="PO-P00",
                   document_type="INITIAL", issue_sequence=1, source_order_revision=1,
                   before_product_quantity=0, after_product_quantity=100, product_quantity_delta=100,
                   snapshot_json="{}", generated_by="u", generated_at="2026-09-01T09:00:00+08:00"),
         audit("issue-event", "PURCHASE_ORDER_ISSUED", "issue", entity_type="carton_purchase_order_issue"))
    rows = order_timeline(db, "huaxing", search="PO-P00").events
    assert len(rows) == 1 and rows[0].order_id == "first"
    assert rows[0].quantity_change is None
    assert not order_timeline(db, "huaxing", order_id="second").events


def test_zero_effective_receipt_keeps_confirmation_without_inventing_movement(db):
    order_line(db, "l")
    receipt(db, effective="0")
    seed(db, audit("confirm", "RECEIPT_CONFIRMED", "receipt", entity_type="carton_receipt"))
    rows = order_timeline(db, "huaxing").events
    assert len(rows) == 1
    assert rows[0].event_label == "确认收料（无有效入库）"
    assert rows[0].quantity_basis == "NONE"


def test_legacy_same_second_balance_order_is_not_fabricated(db):
    seed(db, movement("z-in", "10"), movement("a-out", "-4"),
         movement("later", "1", at="2026-09-02T09:00:00+08:00"))
    rows = order_timeline(db, "huaxing").events
    assert all(row.quantity_before is None and row.quantity_after is None for row in rows[:2])
    assert rows[2].quantity_before == "6.0000" and rows[2].quantity_after == "7.0000"


def test_route_requires_scoped_read_and_rejects_invalid_dates(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import carton_procurement as api

    seed(db, movement("m", "0.125"))
    monkeypatch.setattr(api, "has_permission_in_scope", lambda user, permission, factory, department:
                        permission == "carton_procurement:read" and factory == "huaxing")
    def deny(*args):
        raise HTTPException(403, "无此工厂权限")
    monkeypatch.setattr(api, "ensure_permission_in_scope", deny)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = lambda: db
    app.dependency_overrides[api.get_current_user] = lambda: object()
    with TestClient(app) as client:
        url = "/api/carton-procurement/inventory/order-timeline"
        response = client.get(url, params={"factory_id": "huaxing"})
        assert response.status_code == 200, response.text
        assert response.json()["events"][0]["quantity_change"] == "0.1250"
        assert response.json()["total"] == 1
        assert client.get(url, params={"factory_id": "huadeng"}).status_code == 403
        assert client.get(url, params={"factory_id": "huaxing", "date_to": "2026-02-30"}).status_code == 422


def test_explicit_adjustments_show_immutable_paper_targets_without_product_totals(db):
    order_line(db, "box", order_id="explicit")
    order_line(db, "sheet", order_id="explicit", line_no=2, packaging="滑板纸", unit="张")
    order = db.get(Order, "explicit")
    order.quantity_basis = "EXPLICIT"
    order.product_order_quantity = None
    seed(db, audit("reduce-explicit", "ORDER_REDUCED", "explicit", {
        "quantity_basis": "EXPLICIT", "before_quantity": None, "after_quantity": None,
        "before_required": {"box": "100", "sheet": "20"}, "after_required": {"box":"40", "sheet":"0"},
        "line_labels": {"box": {"packaging_type":"外箱", "unit":"个"}, "sheet":{"packaging_type":"滑板纸", "unit":"张"}}}))
    db.get(Line, "box").required_quantity = D(999)
    db.commit()
    event = order_timeline(db, "huaxing").events[0]
    assert event.quantity_change is None
    assert "外箱：100 → 40 个" in event.description
    assert "滑板纸：20 → 0 张" in event.description
    assert "999" not in event.description


def test_explicit_creation_preserves_initial_paper_snapshot_without_guessing_product_quantity(db):
    order_line(db, "box", order_id="explicit-create")
    seed(db, audit("create-explicit", "HISTORY_ORDER_IMPORTED", "explicit-create", {
        "quantity_basis": "EXPLICIT", "product_order_quantity": None,
        "paper_demand": [{"packaging_type":"外箱", "paper_quality":"K3K", "specification":"30*20*15", "unit":"个", "required_quantity":"100"}]}))
    db.get(Line, "box").required_quantity = D(999)
    db.commit()
    event = order_timeline(db, "huaxing").events[0]
    assert event.quantity_change is None
    assert event.description == "纸品需求：外箱 / K3K / 30*20*15 100 个"
