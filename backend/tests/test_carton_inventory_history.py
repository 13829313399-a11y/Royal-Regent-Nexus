from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.carton_procurement import CartonAuditEvent, CartonCustomer, CartonInventoryMovement
from app.services.carton_inventory_history import inventory_movement_history


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool)
    CartonInventoryMovement.__table__.create(engine)
    CartonAuditEvent.__table__.create(engine)
    CartonCustomer.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def movement(identifier, quantity="1", *, at="2026-10-01T09:00:00+08:00", **overrides):
    values = dict(
        id=identifier, factory_id="huaxing", order_line_id=None,
        customer_code="C1", customer_name="客户甲", contract_no="CONTRACT", item_no="ITEM",
        packaging_type="外箱", paper_quality="A33", specification="1x1x1",
        movement_type="INBOUND", quantity=Decimal(quantity), unit="个", unit_price=Decimal("2"),
        currency="CNY", location="A01", document_no=identifier,
        source_type="MANUAL", source_id=identifier, source_line_id=identifier,
        reversal_of_movement_id=None, reason="", actor_user_id="u", actor_name="仓管",
        occurred_at=at,
    )
    values.update(overrides)
    return CartonInventoryMovement(**values)


def seed(db, *rows):
    db.add_all(rows)
    db.commit()


def test_pages_search_the_complete_ledger_and_keep_full_running_balance_and_cost(db):
    start = datetime(2026, 10, 1, 9)
    seed(db, *(movement(f"DOC-{number:04d}", at=(start + timedelta(minutes=number)).isoformat())
               for number in range(507)))
    page = inventory_movement_history(db, "huaxing", limit=500)
    assert page.total == 507
    assert len(page.items) == 500
    assert page.items[0].id == "DOC-0506"
    assert page.items[0].balance == Decimal(507)
    older = inventory_movement_history(db, "huaxing", limit=500, offset=500)
    assert older.total == 507
    assert [item.id for item in older.items] == [f"DOC-{number:04d}" for number in range(6, -1, -1)]
    match = inventory_movement_history(db, "huaxing", search="doc-0003", limit=1)
    assert match.total == 1
    assert match.items[0].balance == Decimal(4)
    assert match.items[0].cost_amount == Decimal("2.00")
    assert match.items[0].cost_status == "已计价"


def test_shanghai_date_filters_include_both_boundaries_and_legacy_offsets(db):
    seed(db,
         movement("before", at="2026-09-30T15:59:59Z"),
         movement("start", at="2026-09-30T16:00:00Z"),
         movement("legacy", at="2026-10-01T12:00:00"),
         movement("offset", at="2026-10-01T07:00:00-04:00"),
         movement("end", at="2026-10-01T15:59:59Z"),
         movement("after", at="2026-10-01T16:00:00Z"))
    page = inventory_movement_history(db, "huaxing", date_from="2026-10-01", date_to="2026-10-01")
    assert [item.id for item in page.items] == ["end", "offset", "legacy", "start"]
    assert page.items[0].balance == Decimal(5)
    assert page.items[-1].balance == Decimal(2)
    searched = inventory_movement_history(db, "huaxing", search="2026-10-01 00:00")
    assert [item.id for item in searched.items] == ["start"]


def test_page_and_filtered_reversal_metadata_uses_the_complete_scoped_ledger(db):
    seed(db,
         movement("opening", "10", at="2026-09-01T09:00:00+08:00"),
         movement("issue", "-2", at="2026-09-02T09:00:00+08:00", movement_type="OUTBOUND"),
         movement("reverse", "2", at="2026-10-01T09:00:00+08:00", movement_type="REVERSAL",
                  source_type="REVERSAL", reversal_of_movement_id="issue"),
         movement("other-factory", "100", factory_id="huakang-a"))
    page = inventory_movement_history(db, "huaxing", movement_type="OUTBOUND", date_to="2026-09-30")
    assert page.total == 1
    assert page.items[0].id == "issue"
    assert page.items[0].is_reversed is True
    assert page.items[0].balance == Decimal(8)
    assert page.items[0].cost_amount == Decimal("-4.00")
    assert inventory_movement_history(db, "huakang-a").total == 1
    assert inventory_movement_history(db, "huaxing", search="other-factory").total == 0


def test_customer_type_and_literal_search_filter_before_count_and_paging(db):
    seed(db,
         movement("opening", "10", at="2026-09-01T09:00:00+08:00"),
         movement("special%_", "-2", at="2026-09-02T09:00:00+08:00", movement_type="OUTBOUND"),
         movement("other-customer", customer_code="C2", customer_name="客户乙"))
    assert inventory_movement_history(db, "huaxing", customer_code="C1", movement_type="OUTBOUND").total == 1
    assert inventory_movement_history(db, "huaxing", search="%_").items[0].id == "special%_"
    assert inventory_movement_history(db, "huaxing", search="客户乙").total == 1
    assert inventory_movement_history(db, "huaxing", search="仓管").total == 3
    assert inventory_movement_history(db, "huaxing", search="special", offset=1).items == []


def test_legacy_customer_name_filter_keeps_all_same_name_customer_codes_separate(db):
    seed(db, movement("C1-history", "10", customer_code="C1", customer_name="同名客户"),
         movement("C2-history", "20", customer_code="C2", customer_name="同名客户"),
         movement("other", "30", customer_code="C3", customer_name="不同客户"))
    page = inventory_movement_history(db, "huaxing", customer_name="同名客户")
    assert page.total == 2
    assert {(item.customer_code, item.balance) for item in page.items} == {
        ("C1", Decimal(10)), ("C2", Decimal(20)),
    }
    code_page = inventory_movement_history(db, "huaxing", customer_name="同名客户", customer_code="C2")
    assert code_page.total == 1 and code_page.items[0].id == "C2-history"
    assert inventory_movement_history(db, "huaxing", customer_name="不同客户", customer_code="C2").total == 0


def test_current_customer_name_finds_prior_name_snapshots_without_cross_factory_aliases(db):
    db.add_all([CartonCustomer(id="renamed", factory_id="huaxing", customer_code="C1",
                              customer_name="新名称", created_by="u", updated_by="u",
                              created_at="2026-10-01", updated_at="2026-10-01"),
                CartonCustomer(id="foreign-name", factory_id="huadeng", customer_code="C2",
                              customer_name="新名称", created_by="u", updated_by="u",
                              created_at="2026-10-01", updated_at="2026-10-01")])
    seed(db, movement("old-name", customer_code="C1", customer_name="旧名称"),
         movement("recorded-name", customer_code="C3", customer_name="新名称"),
         movement("other-identity", customer_code="C2", customer_name="别的客户"))
    page = inventory_movement_history(db, "huaxing", customer_name="新名称")
    assert page.total == 2
    assert {item.id for item in page.items} == {"old-name", "recorded-name"}
    assert inventory_movement_history(db, "huaxing", customer_name="新名称", customer_code="C1").total == 1


@pytest.mark.parametrize("filters", [
    {"date_from": "2026-10-02", "date_to": "2026-10-01"},
    {"date_from": "2026-02-30"}, {"movement_type": "INVALID"},
    {"limit": 501}, {"offset": -1},
])
def test_invalid_queries_report_errors_instead_of_a_false_empty_result(db, filters):
    with pytest.raises(HTTPException) as error:
        inventory_movement_history(db, "huaxing", **filters)
    assert error.value.status_code == 422
