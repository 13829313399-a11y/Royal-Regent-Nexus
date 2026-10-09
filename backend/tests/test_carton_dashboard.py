"""Dashboard semantics and bounded responses using synthetic data only."""
import importlib
import json
import pkgutil
import time
from datetime import date

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from app.services.carton_dashboard import Context, SourceIndex, alert_page, build_alerts, reminder


def row(index=0, **changes):
    return dict(contract_no=f"SC{index}", item_no=f"ITEM{index}", customer_code="TEST", customer_name="TEST", schedule_customer_code="TEST", schedule_customer_name="TEST",
                quantity=100, source_sheet="ITEM", source_row=index+2, source_reference=f"SO{index}", schedule_identity=f"KEY{index}",
                schedule_section="PENDING", customer_due_date="2026-10-10", match_status="MISSING_ORDER", **changes)


def batch(rows, identifier="B", **changes):
    return dict(id=identifier, factory_id="huakang-b", status="REQUIRES_REVIEW", original_filename="synthetic.xlsx", imported_by_name="TEST", created_at="2026-10-01", parse_summary={"rows": rows}, **changes)


def exception(r, identifier="E", category="MISSING_ORDER", batch_id="B", **changes):
    return dict(id=identifier, factory_id="huakang-b", source_type="WEEKLY_SCHEDULE", source_id=batch_id, exception_no=identifier,
        category=category, contract_no=r["contract_no"], item_no=r["item_no"], customer_name="TEST", customer_code="TEST", description="Review",
        status="OPEN", created_at="2026-10-01", **changes)


def context(orders=(), marks=None, rules=None, today=date(2026, 10, 2)):
    return Context("huakang-b", orders, [dict(factory_id="huakang-b", customer_code="TEST", customer_name="TEST", status="ACTIVE")], marks or {}, rules or {}, today)


def order(r, **changes):
    result = dict(id="O", factory_id="huakang-b", order_no="CT1", customer_code="TEST", customer_name="TEST", contract_no=r["contract_no"], item_no=r["item_no"], customer_po=r["source_reference"], status="CONFIRMED", product_order_quantity=100, product_name="TEST", split_records=[])
    result.update(changes)
    return result


def test_resolved_exception_is_not_placed_order_and_latest_identity_wins():
    r = row()
    e = exception(r); e["status"] = "RESOLVED"
    old = {**r, "quantity": 900}
    alerts = build_alerts(context(), [batch([r]), batch([old], "OLD")], [e])
    assert len(alerts) == 1 and alerts[0]["status"] == "OPEN" and alerts[0]["scheduleQuantity"] == 100
    assert alerts[0]["reminder"]["state"] == "OVERDUE"
    assert not build_alerts(context(marks={r["schedule_identity"]: {"marked": True}}), [batch([r])], [e])
    withdrawn = batch([r]); withdrawn["status"] = "REJECTED"
    assert not build_alerts(context(), [withdrawn], [e])
    other = batch([r]); other["factory_id"] = "huaxing"
    assert not build_alerts(context(), [other], [e])


def test_ambiguity_and_cancelled_source_coordinates_remain_authoritative():
    r = row(); second = {**r, "source_row": 3, "source_reference": "SO2", "schedule_section": "CANCELLED"}
    lookup = SourceIndex([r, second])
    assert lookup.find(exception(r)) is None
    assert lookup.find(exception(r, category="SCHEDULE_CANCELLED")) is second
    e = exception(r); e["description"] = "review\n来源：ITEM · 第 2 行 · SO：SO0"
    assert lookup.find(e) is r
    e["description"] = "review\n来源：ITEM · 第 2 行 · SO：wrong"
    assert lookup.find(e) is None
    duplicate = {**r, "schedule_identity_duplicate": True}
    assert not build_alerts(context(), [batch([duplicate])], [])
    assert not build_alerts(context([order(r), order(r, id="O2")]), [batch([r])], [])


def test_placed_order_keeps_quantity_and_cancellation_but_draft_keeps_deadline():
    r = row()
    draft = build_alerts(context([order(r)]), [batch([r])], [])
    assert draft[0]["reminder"]["label"].endswith("待确认下单")
    placed = order(r, status="PENDING_SUPPLIER")
    assert not build_alerts(context([placed]), [batch([r])], [])
    increased = {**r, "quantity": 160}
    alerts = build_alerts(context([placed]), [batch([increased])], [exception(increased, category="QUANTITY_MISMATCH")])
    assert len(alerts) == 1 and alerts[0]["differenceQuantity"] == 60
    cancelled = {**r, "schedule_section": "CANCELLED"}
    alerts = build_alerts(context([placed], marks={r["schedule_identity"]: {"marked": True}}), [batch([cancelled])], [exception(cancelled, category="SCHEDULE_CANCELLED_AFTER_ORDER")])
    assert len(alerts) == 1 and alerts[0]["kind"] == "CANCELLED_AFTER_ORDER"


def test_deadline_zero_override_incomplete_date_and_business_midnight():
    r = row(); r["inspection_window"] = "2026-10-03"
    ctx = context(rules={"": {"lead_days": 3, "production_days": 7}, "TEST": {"lead_days": 0, "production_days": 0}})
    assert ctx.reminder(r)["deadline"] == "2026-10-03"
    assert ctx.reminder(r)["state"] == "DUE_SOON"
    assert context(rules=ctx.rules, today=date(2026, 10, 3)).reminder(r)["state"] == "DUE_TODAY"
    assert context(rules=ctx.rules, today=date(2026, 10, 4)).reminder(r)["state"] == "OVERDUE"
    assert ctx.reminder({**r, "customer_due_date": "2026-09-31"})["state"] == "DATE_REVIEW"


def test_split_target_stops_timing_and_does_not_cross_customer_or_factory():
    r = row(); parent = order(r, contract_no="PARENT", status="PENDING_SUPPLIER", split_records=[dict(status="ACTIVE", item_no=r["item_no"], targets=[dict(contract_no=r["contract_no"], customer_po=r["source_reference"])])])
    assert context([parent]).matching(r) == [parent]
    assert not build_alerts(context([parent]), [batch([r])], [])
    assert not context([{**parent, "factory_id": "huaxing"}]).matching(r)
    assert not context([{**parent, "customer_code": "OTHER"}]).matching(r)


def test_5000_rows_keep_counts_and_paging_without_cubic_matching():
    rows = [row(i) for i in range(5000)]
    start = time.monotonic()
    alerts = build_alerts(context(), [batch(rows)], [exception(r, f"E{i}") for i, r in enumerate(rows)])
    assert len(alerts) == 5000
    page = alert_page(alerts, offset=8, limit=8)
    assert page["total"] == page["summary"]["total"] == 5000
    assert len(page["items"]) == 8 and len(page["reminders"]) == 3
    assert page["items"][0]["contractNo"] == "SC8"
    assert alert_page(alerts, search="SC4999")["total"] == 1
    assert alert_page(alerts, customer="OTHER")["total"] == 0
    assert time.monotonic() - start < 8  # A generous guard against restoring the 62-million-scan path.


@pytest.fixture
def db():
    import app.models
    from app.db import Base
    for module in pkgutil.iter_modules(app.models.__path__):
        importlib.import_module("app.models." + module.name)
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_workspace_reads_all_effective_batches_excludes_deleted_and_limits_payload(db):
    from app.models.carton_procurement import CartonCustomer, CartonOrder, CartonImportBatch
    from app.services.carton_dashboard import workspace, alert_context
    audit = dict(created_by="TEST", updated_by="TEST", created_at="2026-10-01", updated_at="2026-10-01")
    db.add(CartonCustomer(id="C", factory_id="huakang-b", customer_code="TEST", customer_name="TEST", status="ACTIVE", **audit))
    for i in range(55):
        db.add(CartonImportBatch(id=f"B{i}", factory_id="huakang-b", import_type="WEEKLY_SCHEDULE", original_filename="test.xlsx", source_sha256=str(i), import_profile="", content_type="application/xlsx", source_size_bytes=1,
            status="REQUIRES_REVIEW", imported_by="TEST", imported_by_name="TEST", created_at=f"2026-09-{(i % 28)+1:02d}", parse_summary_json=json.dumps({"rows": [row(i)]})))
    for i, deleted in enumerate([None, "2026-10-01"]):
        db.add(CartonOrder(id=f"O{i}", factory_id="huakang-b", order_no=f"CT{i}", customer_code="TEST", customer_name="TEST", supplier_id="S", supplier_name_snapshot="S",
            contract_no="OTHER", item_no="OTHER", order_date="2026-10-01", due_date="2026-10-12", product_order_quantity=100, status="CONFIRMED", deleted_at=deleted, **audit))
    db.commit()
    result = workspace(db, "huakang-b", limit=8)
    assert result["total"] == 55 and result["pending_order_count"] == 1
    assert len(result["items"]) == 8 and "parse_summary" not in json.dumps(result, default=str)
    assert len(result["recent_orders"]) == 1 and not db.dirty
    detail = alert_context(db, "huakang-b", result["items"][0]["id"])
    assert len(detail["batch"]["parse_summary"]["rows"]) == 1
    with pytest.raises(HTTPException):
        alert_context(db, "huaxing", result["items"][0]["id"])


def test_dashboard_routes_require_factory_permission(monkeypatch):
    from test_molding_sample_api import make_client, login_as
    with make_client(monkeypatch) as client:
        assert client.get('/api/carton-procurement/dashboard/workspace', params={'factory_id': 'huaxing'}).status_code == 401
        assert client.get('/api/carton-procurement/dashboard/alert-context', params={'factory_id': 'huaxing', 'alert_id': 'SYNTHETIC'}).status_code == 401
        login_as(client, 'warehouse_keeper')
        for endpoint in ('workspace', 'alert-context'):
            assert client.get(f'/api/carton-procurement/dashboard/{endpoint}', params={'factory_id': 'huakang-b', 'alert_id': 'SYNTHETIC'}).status_code == 403
        response = client.get('/api/carton-procurement/dashboard/workspace', params={'factory_id': 'huaxing'})
        assert response.status_code == 200, response.text
        assert client.get('/api/carton-procurement/dashboard/workspace', params={'factory_id': 'group'}).status_code in (400, 403, 422)
        assert client.get('/api/carton-procurement/dashboard/workspace', params={'factory_id': 'huaxing', 'limit': 5000}).status_code == 422


def test_search_keeps_contiguous_case_insensitive_text():
    from app.services.carton_dashboard import text_matches
    assert text_matches(["SO-123", "Customer name"], "  customer NAME ")
    assert not text_matches(["SO-123", "Customer name"], "SO name")
    assert not text_matches(["SO-123", "Customer name"], "name Customer")


def test_workspace_inventory_keeps_units_precision_and_filters(db, monkeypatch):
    from decimal import Decimal
    from types import SimpleNamespace
    from app.services.carton_dashboard import workspace
    def balance(customer, unit, quantity):
        return SimpleNamespace(customer_name=customer, unit=unit, balance=Decimal(quantity), latest_movement_at="2026-10-01T12:00:00",
            latest_document_no="IN-1", contract_no="SC-1", item_no="ITEM", packaging_type="外箱", paper_quality="A", specification="", latest_location="")
    seen = []
    def balances(session, factory):
        seen.append(factory)
        return [balance("TEST", "个", "100.0001"), balance("TEST", "张", "90"), balance("OTHER", "个", "165"), balance("TEST", "个", "-2")]
    monkeypatch.setattr("app.services.carton_positions.position_balances", balances)
    result = workspace(db, "huakang-b")
    assert {i["unit"]: i["quantity"] for i in result["inventory_by_unit"]} == {"个": "265.0001", "张": "90"}
    result = workspace(db, "huakang-b", customer="TEST", search="外箱 A")
    assert {i["unit"]: i["quantity"] for i in result["inventory_by_unit"]} == {"个": "100.0001", "张": "90"}
    assert workspace(db, "huakang-b", search="not present")["inventory_by_unit"] == []
    assert seen == ["huakang-b"] * 3
