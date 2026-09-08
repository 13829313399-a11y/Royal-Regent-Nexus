from decimal import Decimal as D

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.carton_procurement import CartonInventoryMovement as Movement
from app.models.carton_procurement import CartonOrder as Order, CartonOrderLine as OrderLine
from app.services.carton_inventory_report import inventory_report


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Movement.__table__.create(engine)
    Order.__table__.create(engine)
    OrderLine.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def movement(id, qty, *, at="2026-09-01T09:00:00+08:00", **overrides):
    values = dict(id=id, factory_id="huaxing", order_line_id=None, customer_code="C1",
                  customer_name="Customer", contract_no="CONTRACT", item_no="ITEM",
                  packaging_type="外箱", paper_quality="A33", specification="1x1x1",
                  movement_type="INBOUND" if D(qty) > 0 else "OUTBOUND", quantity=D(qty),
                  unit="个", unit_price=D(0), currency="CNY", location="A01",
                  document_no=id, source_type="MANUAL", source_id=id, source_line_id=id,
                  reversal_of_movement_id=None, reason="", actor_user_id="u", actor_name="User",
                  occurred_at=at)
    values.update(overrides)
    return Movement(**values)


def seed(db, *rows):
    db.add_all(rows)
    db.commit()


def order_line(db, id, *, order_id=None, factory="huaxing", contract="CONTRACT", unit="个",
               packaging="外箱", status="CONFIRMED", order_date="2026-09-01", line_no=1):
    order_id = order_id or f"order-{id}"
    order = db.get(Order, order_id)
    if not order:
        order = Order(id=order_id, factory_id=factory, order_no=order_id,
                      customer_code="C1", customer_name="Customer", supplier_id="s",
                      supplier_name_snapshot="Supplier", contract_no=contract, item_no="ITEM",
                      product_name="消防车", product_order_quantity=D(100), order_date=order_date,
                      due_date="2026-09-30", status=status, created_by="u", updated_by="u",
                      created_at="2026-09-01T00:00:00+08:00", updated_at="2026-09-01T00:00:00+08:00")
        db.add(order)
        db.flush()
    line = OrderLine(id=id, order_id=order_id, factory_id=factory, line_no=line_no,
                     customer_code="C1", contract_no=contract, item_no="ITEM",
                     packaging_type=packaging, paper_quality="A33", specification="1x1x1",
                     usage_quantity=D(1), required_quantity=D(100), unit=unit)
    db.add(line)
    db.commit()
    return line


def test_daily_balances_carry_full_history_without_mixing_units(db):
    seed(db, movement("opening", "10.125", at="2026-08-31T10:00:00+08:00"),
         movement("in", "2.25"), movement("out", "-3.125", at="2026-09-02T09:00:00+08:00"),
         movement("adjust", "-0.25", movement_type="ADJUSTMENT", at="2026-09-02T10:00:00+08:00"),
         movement("sheets", "1000", unit="张", packaging_type="滑板纸"),
         movement("future", "100", at="2026-09-03T09:00:00+08:00"))
    report = inventory_report(db, "huaxing", date_from="2026-09-01", date_to="2026-09-02")
    rows = {(row.business_date, row.unit): row for row in report.rows}
    first, second = rows[("2026-09-01", "个")], rows[("2026-09-02", "个")]
    assert first.opening_quantity == D("10.125")
    assert first.ending_quantity == D("12.375")
    assert second.opening_quantity == first.ending_quantity
    assert second.outbound_quantity == D("3.125")
    assert second.adjustment_quantity == D("-0.25")
    assert second.ending_quantity == 9
    assert rows[("2026-09-01", "张")].ending_quantity == 1000
    assert len(report.movements) == 4
    for row in report.rows:
        assert row.ending_quantity == row.opening_quantity + row.inbound_quantity - row.outbound_quantity + row.adjustment_quantity


def test_reversals_keep_original_receipt_and_signed_categories_on_reversal_day(db):
    seed(db, movement("receipt", "10", source_type="RECEIPT"),
         movement("issue", "-2", at="2026-09-02T09:00:00+08:00"),
         movement("adjust", "3", movement_type="ADJUSTMENT", at="2026-09-02T10:00:00+08:00"),
         movement("undo-issue", "2", movement_type="REVERSAL", reversal_of_movement_id="issue",
                  at="2026-09-03T09:00:00+08:00"),
         movement("undo-receipt", "-10", movement_type="REVERSAL", reversal_of_movement_id="receipt",
                  at="2026-09-03T10:00:00+08:00"),
         movement("undo-adjust", "-3", movement_type="REVERSAL", reversal_of_movement_id="adjust",
                  at="2026-09-03T11:00:00+08:00"))
    report = inventory_report(db, "huaxing")
    assert report.rows[-1].inbound_quantity == 10
    assert report.rows[0].opening_quantity == 11
    assert report.rows[0].inbound_quantity == -10
    assert report.rows[0].outbound_quantity == -2
    assert report.rows[0].adjustment_quantity == -3
    assert report.rows[0].ending_quantity == 0
    details = {row.id: row for row in report.movements}
    assert details["undo-issue"].flow_category == "OUTBOUND"
    assert details["undo-issue"].flow_quantity == -2
    assert details["undo-receipt"].flow_category == "INBOUND"
    assert details["undo-adjust"].flow_category == "ADJUSTMENT"


def test_scope_and_document_search_preserve_complete_exact_inventory_history(db):
    seed(db, movement("hit", "10", document_no="DN-UNIQUE", at="2026-08-01T09:00:00+08:00"),
         movement("issue", "-2"),
         movement("other-contract", "100", contract_no="OTHER"),
         movement("other-unit", "1000", unit="张"),
         movement("other-customer", "200", customer_code="C2"),
         movement("other-factory", "300", factory_id="huadeng"))
    report = inventory_report(db, "huaxing", date_from="2026-09-01", search="dn-unique")
    assert len(report.rows) == 1
    assert report.rows[0].opening_quantity == 10
    assert report.rows[0].ending_quantity == 8
    assert [r.id for r in report.movements] == ["issue"]
    assert not inventory_report(db, "huaxing", customer_code="C2", search="dn-unique").rows
    assert inventory_report(db, "huadeng").rows[0].ending_quantity == 300
    assert inventory_report(db, "huaxing", customer_code="C2").rows[0].ending_quantity == 200


def test_same_printed_document_numbers_do_not_collapse_distinct_source_documents(db):
    seed(db, movement("one", "1", document_no="DN", source_id="receipt-1", source_type="RECEIPT"),
         movement("two", "2", document_no="DN", source_id="receipt-1", source_type="RECEIPT"),
         movement("three", "3", document_no="DN", source_id="receipt-2", source_type="RECEIPT"))
    row = inventory_report(db, "huaxing").rows[0]
    assert row.document_count == 2
    assert row.line_count == 3
    assert row.inbound_quantity == 6


def test_business_timezone_inclusive_dates_and_name_snapshot_changes(db):
    seed(db, movement("before", "2", at="2026-08-31T15:59:59.999999Z"),
         movement("start", "3", at="2026-08-31T16:00:00Z"),
         movement("end", "4", at="2026-09-01T23:59:59.999999+08:00", customer_name="Renamed"),
         movement("after", "5", at="2026-09-01T16:00:00Z"))
    report = inventory_report(db, "huaxing", date_from="2026-09-01", date_to="2026-09-01")
    assert len(report.rows) == 1
    row = report.rows[0]
    assert (row.opening_quantity, row.inbound_quantity, row.ending_quantity) == (2, 7, 9)
    assert row.customer_name == "Renamed"
    assert len(report.movements) == 2
    assert all(row.occurred_at.startswith("2026-09-01T") and row.occurred_at.endswith("+08:00")
               for row in report.movements)


def test_manual_batch_lines_share_document_number_with_type_boundary(db):
    seed(db, movement("one", "-1", document_no="OUT-BATCH"),
         movement("two", "-2", document_no="OUT-BATCH", contract_no="OTHER"),
         movement("adjust", "3", document_no="OUT-BATCH", movement_type="ADJUSTMENT"))
    row = inventory_report(db, "huaxing").rows[0]
    assert row.document_count == 2
    assert row.line_count == 3


@pytest.mark.parametrize("start,end", [("2026-02-30", ""), ("2026-09-02", "2026-09-01")])
def test_invalid_ranges_are_rejected(db, start, end):
    with pytest.raises(HTTPException) as exc:
        inventory_report(db, "huaxing", date_from=start, date_to=end)
    assert exc.value.status_code == 422


def test_missing_reversal_origin_is_explicit_not_misclassified(db):
    seed(db, movement("bad", "-2", movement_type="REVERSAL", reversal_of_movement_id="absent"))
    with pytest.raises(HTTPException) as exc:
        inventory_report(db, "huaxing")
    assert exc.value.status_code == 409


def test_empty_range_does_not_fabricate_activity_rows(db):
    seed(db, movement("before", "2", at="2026-08-01T09:00:00+08:00"))
    report = inventory_report(db, "huaxing", date_from="2026-09-01")
    assert not report.rows
    assert not report.movements
    assert report.order_rows[0].opening_quantity == 2
    assert report.order_rows[0].ending_quantity == 2
    assert report.order_rows[0].line_count == 0


def test_order_summary_keeps_formal_orders_paper_lines_and_standalone_stock_separate(db):
    order_line(db, "box-1")
    order_line(db, "sheet-1", order_id="order-box-1", unit="张", packaging="滑板纸", line_no=2)
    order_line(db, "box-2", contract="OTHER")
    order_line(db, "same-contract-different-order")
    seed(db, movement("a", "10", order_line_id="box-1"),
         movement("b", "-3", order_line_id="box-1", at="2026-09-02T09:00:00+08:00"),
         movement("c", "1000", order_line_id="sheet-1", unit="张", packaging_type="滑板纸"),
         movement("d", "20", order_line_id="box-2", contract_no="OTHER"),
         movement("e", "40", order_line_id="same-contract-different-order"),
         movement("standalone", "5"))
    report = inventory_report(db, "huaxing")
    rows = {row.order_line_id: row for row in report.order_rows}
    assert len(rows) == 5
    assert len({row.key for row in rows.values()}) == 5
    assert (rows["box-1"].inbound_quantity, rows["box-1"].outbound_quantity,
            rows["box-1"].ending_quantity, rows["box-1"].line_count) == (10, 3, 7, 2)
    assert rows["box-1"].order_id == rows["sheet-1"].order_id
    assert rows["sheet-1"].unit == "张"
    assert rows["same-contract-different-order"].ending_quantity == 40
    assert rows[None].order_id is None and rows[None].ending_quantity == 5
    assert rows["box-1"].product_name == "消防车"
    assert rows["box-1"].last_movement_at.startswith("2026-09-02")


def test_order_summary_range_retains_opening_and_signed_reversal_categories(db):
    order_line(db, "line", order_date="2026-08-01")
    seed(db, movement("in", "10", order_line_id="line", at="2026-08-01T09:00:00+08:00"),
         movement("out", "-4", order_line_id="line", at="2026-08-02T09:00:00+08:00"),
         movement("return", "2", order_line_id="line"),
         movement("undo-out", "4", order_line_id="line", movement_type="REVERSAL",
                  reversal_of_movement_id="out"),
         movement("gain", "1", order_line_id="line", movement_type="ADJUSTMENT"))
    row = inventory_report(db, "huaxing", date_from="2026-09-01", date_to="2026-09-01").order_rows[0]
    assert (row.opening_quantity, row.inbound_quantity, row.outbound_quantity,
            row.adjustment_quantity, row.ending_quantity) == (6, 2, -4, 1, 13)
    assert row.line_count == row.document_count == 3
    row = inventory_report(db, "huaxing", date_from="2026-10-01").order_rows[0]
    assert (row.opening_quantity, row.ending_quantity, row.line_count) == (13, 13, 0)


def test_zero_posting_orders_filter_by_placement_date_search_and_factory(db):
    order_line(db, "new", order_date="2026-09-02")
    order_line(db, "old", order_date="2026-08-01")
    order_line(db, "cancelled", status="CANCELLED")
    order_line(db, "cancelled-history", status="CANCELLED")
    order_line(db, "foreign", factory="huadeng")
    seed(db, movement("kept", "2", order_line_id="cancelled-history"))
    report = inventory_report(db, "huaxing")
    assert {row.order_line_id for row in report.order_rows} == {"new", "old", "cancelled-history"}
    rows = inventory_report(db, "huaxing", date_from="2026-09-02", date_to="2026-09-02").order_rows
    assert {row.order_line_id for row in rows} == {"new", "cancelled-history"}
    assert next(row for row in rows if row.order_line_id == "new").ending_quantity == 0
    assert {row.order_line_id for row in inventory_report(db, "huaxing", search="消防车").order_rows} == {
        "new", "old", "cancelled-history"}
    assert not inventory_report(db, "huaxing", search="missing").order_rows
    assert not inventory_report(db, "huaxing", customer_code="C2").order_rows
    assert {row.order_line_id for row in inventory_report(db, "huadeng").order_rows} == {"foreign"}


def test_report_route_requires_scoped_read_and_preserves_decimal_wire_values(db, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import carton_procurement as api

    seed(db, movement("allowed", "0.125"), movement("foreign", "500", factory_id="huadeng"))
    checks = []

    def has_scope(user, permission, factory, department):
        checks.append((permission, factory))
        return permission == "carton_procurement:read" and factory == "huaxing"

    def deny(*args):
        raise HTTPException(status_code=403, detail="当前用户没有该工厂读取权限")

    monkeypatch.setattr(api, "has_permission_in_scope", has_scope)
    monkeypatch.setattr(api, "ensure_permission_in_scope", deny)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = lambda: db
    app.dependency_overrides[api.get_current_user] = lambda: object()
    with TestClient(app) as client:
        response = client.get("/api/carton-procurement/inventory/report", params={"factory_id": "huaxing"})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["rows"][0]["inbound_quantity"] == "0.1250"
        assert body["movements"][0]["flow_quantity"] == "0.1250"
        assert body["order_rows"][0]["inbound_quantity"] == "0.1250"
        assert body["order_rows"][0]["order_id"] is None
        assert [row["id"] for row in body["movements"]] == ["allowed"]
        assert client.get("/api/carton-procurement/inventory/report", params={"factory_id": "huadeng"}).status_code == 403
        assert client.get("/api/carton-procurement/inventory/report", params={"factory_id": "huaxing", "date_from": "2026-02-30"}).status_code == 422
    assert ("carton_procurement:read", "huaxing") in checks
    assert ("carton_procurement:read", "huadeng") in checks
