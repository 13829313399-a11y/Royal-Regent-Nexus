import json
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.models.carton_procurement import CartonAuditEvent, CartonImportBatch
from app.services.carton_order_split_trace import schedule_split_sources


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:")
    for table in (CartonAuditEvent.__table__, CartonImportBatch.__table__):
        table.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def evidence(db, *, suffix="1", factory="huadeng", customer="GOLIATH", legacy=False):
    order = SimpleNamespace(id="order" + suffix, factory_id=factory, order_no="CT" + suffix,
        customer_code=customer, contract_no="CHILD", item_no="934811.929", customer_po="SO1")
    row = dict(source_sheet="ITEM", source_row=7, contract_no="CHILD", item_no="934811.929",
        source_reference="SO1", split_source="PARENT", source_customer_name="Original raw buyer")
    if not legacy:
        row["schedule_customer_code"] = customer
    from app.services.carton_schedule_tracking import customer_key
    detail = dict(batch_id="batch" + suffix, source_sheet="ITEM", source_row=7, order_id=order.id,
        order_no=order.order_no, customer_code=customer, customer=customer_key(row), contract_no="CHILD", item_no=order.item_no)
    batch = CartonImportBatch(id=detail["batch_id"], factory_id=factory, import_type="WEEKLY_SCHEDULE",
        original_filename="TEST.xlsx", source_sha256=suffix, imported_by="test", created_at="2026-10-30",
        parse_summary_json=json.dumps({"rows": [row]}))
    audit = CartonAuditEvent(id="event" + suffix, factory_id=factory, event_type="SCHEDULE_ORDER_LINKED",
        entity_type="schedule_order_link", entity_id="identity" + suffix, detail_json=json.dumps(detail),
        actor_user_id="test", created_at="2026-10-30")
    db.add_all([batch, audit])
    db.commit()
    return order, batch, audit


def test_exact_creation_source_survives_customer_display_name_changes(db):
    order, batch, audit = evidence(db, legacy=True)
    order.customer_name = "Renamed customer"
    assert schedule_split_sources(db, [order])[order.id] == dict(source_contract_no="PARENT",
        current_contract_no="CHILD", batch_id=batch.id, source_sheet="ITEM", source_row=7)
    detail = json.loads(audit.detail_json)
    detail.pop("customer_code")
    audit.detail_json = json.dumps(detail)
    db.commit()
    assert schedule_split_sources(db, [order]) == {}


@pytest.mark.parametrize("change", ["factory", "customer", "coordinate", "duplicate", "po", "raw_buyer", "batch_customer", "batch_factory"])
def test_untrusted_or_ambiguous_source_is_never_exposed(db, change):
    order, batch, audit = evidence(db)
    summary = json.loads(batch.parse_summary_json)
    detail = json.loads(audit.detail_json)
    if change == "factory": audit.factory_id = "huaxing"
    if change == "customer": detail["customer_code"] = "OTHER"
    if change == "coordinate": detail["source_row"] = 8
    if change == "duplicate": summary["rows"].append(dict(summary["rows"][0]))
    if change == "po": order.customer_po = "OTHER-SO"
    if change == "raw_buyer": detail["customer"] = "other buyer"
    if change == "batch_customer": summary["schedule_customer"] = {"customer_code": "OTHER"}
    if change == "batch_factory": batch.factory_id = "huaxing"
    batch.parse_summary_json = json.dumps(summary)
    audit.detail_json = json.dumps(detail)
    db.commit()
    assert schedule_split_sources(db, [order]) == {}


def test_same_contract_in_other_customer_does_not_create_source_link(db):
    order, _, _ = evidence(db)
    other = SimpleNamespace(**vars(order))
    other.id = "unlinked"
    other.customer_code = "OTHER"
    assert schedule_split_sources(db, [other]) == {}


def test_blank_source_po_allows_manually_supplied_order_po(db):
    order, batch, _ = evidence(db)
    summary = json.loads(batch.parse_summary_json)
    summary["rows"][0]["source_reference"] = ""
    batch.parse_summary_json = json.dumps(summary)
    db.commit()
    assert schedule_split_sources(db, [order])[order.id]["source_contract_no"] == "PARENT"


def test_page_uses_two_queries_regardless_of_order_count(db):
    orders = [evidence(db, suffix=str(index))[0] for index in range(12)]
    statements = []
    def record(*args): statements.append(args[2])
    event.listen(db.bind, "before_cursor_execute", record)
    try:
        assert len(schedule_split_sources(db, orders)) == 12
    finally:
        event.remove(db.bind, "before_cursor_execute", record)
    assert len(statements) == 2
    assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


def test_postgresql_projection_uses_supported_json_cast_and_page_order_ids():
    from sqlalchemy.dialects.postgresql import dialect
    statements = []
    def scalars(statement):
        statements.append(statement.compile(dialect=dialect(), compile_kwargs={"literal_binds": True}))
        return []
    connection = SimpleNamespace(bind=SimpleNamespace(dialect=dialect()), scalars=scalars)
    order = SimpleNamespace(id="authorized-order", factory_id="huadeng")
    assert schedule_split_sources(connection, [order]) == {}
    sql = str(statements[0])
    assert "json_valid" not in sql.lower()
    assert "CAST(carton_audit_events.detail_json AS JSON)" in sql
    assert "authorized-order" in sql and "huadeng" in sql
