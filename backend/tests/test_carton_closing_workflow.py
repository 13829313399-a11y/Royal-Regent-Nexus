import json
from datetime import datetime
from decimal import Decimal as D
from zoneinfo import ZoneInfo
import pytest
from fastapi import HTTPException
from sqlalchemy import select

from test_carton_inventory_valuation import db, movement, seed, closing, advance, USER, Audit, events_for
from app.models.carton_procurement import CartonClosing
from app.schemas.carton_procurement import CartonClosingUnlockRequest
from app.services.carton_procurement import closing_out, unlock_closing


def clock(monkeypatch, text):
    value = datetime.fromisoformat(text).replace(tzinfo=ZoneInfo("Asia/Shanghai"))
    monkeypatch.setattr("app.services.carton_procurement.business_now", lambda: value)
    monkeypatch.setattr("app.services.carton_procurement.now_text", lambda: value.isoformat())


@pytest.mark.parametrize("today,period,allowed", [
    ("2026-09-07", "2026-09", False), ("2026-09-30T23:59:59", "2026-09", False),
    ("2026-10-01", "2026-09", True), ("2026-09-07", "2026-10", False),
    ("2027-01-01", "2026-12", True),
])
def test_final_lock_only_after_business_month_ends(db, monkeypatch, today, period, allowed):
    clock(monkeypatch, today)
    seed(db, [movement("a", "10", "2", at=f"{period}-01T09:00:00+08:00")])
    row = advance(db, advance(db, closing(db, period), "PENDING"), "CONFIRMED")
    if allowed:
        assert advance(db, row, "LOCKED").status == "LOCKED"
    else:
        with pytest.raises(HTTPException, match="月份尚未结束"):
            advance(db, row, "LOCKED")
        db.rollback()
        assert row.status == "CONFIRMED"


def test_zero_net_change_requires_review_of_gross_quantities(db, monkeypatch):
    clock(monkeypatch, "2026-10-01")
    seed(db, [movement("a", "100", "2")])
    row = advance(db, advance(db, closing(db), "PENDING"), "CONFIRMED")
    later = [movement("b", "10", "2"), movement("c", "-10", "2")]
    events = events_for(later)
    for event in events: event.sequence = None
    db.add_all(later + events); db.commit()
    assert closing_out(db, row).snapshot_stale
    assert row.ending_quantity == 100 and row.ending_amount == 200
    with pytest.raises(HTTPException, match="数量或金额已变化"):
        advance(db, row, "LOCKED")
    db.rollback()
    revised = closing(db)
    assert revised.status == "DRAFT" and revised.inbound_quantity == 110 and revised.outbound_quantity == 10
    assert not closing_out(db, revised).snapshot_stale
    assert advance(db, advance(db, advance(db, revised, "PENDING"), "CONFIRMED"), "LOCKED").status == "LOCKED"


def test_unlock_audits_frozen_snapshot_and_requires_latest_locked_month_first(db, monkeypatch):
    clock(monkeypatch, "2026-11-01")
    seed(db, [movement("a", "10", "2")])
    earlier = advance(db, advance(db, advance(db, closing(db), "PENDING"), "CONFIRMED"), "LOCKED")
    later = advance(db, advance(db, advance(db, closing(db, "2026-10"), "PENDING"), "CONFIRMED"), "LOCKED")
    def unlock(row, revision=None):
        return unlock_closing(db, row.id, CartonClosingUnlockRequest(factory_id="huaxing",
            expected_revision=revision or row.revision, reason="误操作锁账，需重新核对"), USER)
    with pytest.raises(HTTPException, match="最新月份"):
        unlock(earlier)
    db.rollback()
    old_revision = later.revision
    result = unlock(later)
    assert result.status == "DRAFT" and result.revision == old_revision + 1
    assert result.confirmed_by == result.locked_by == result.locked_at == ""
    audit = db.scalar(select(Audit).where(Audit.event_type == "CLOSING_UNLOCKED"))
    detail = json.loads(audit.detail_json)
    assert detail["before"]["status"] == "LOCKED" and D(detail["before"]["ending_amount"]) == 20
    assert detail["before"]["locked_by"] == USER.id
    assert detail["reason"] == "误操作锁账，需重新核对"
    with pytest.raises(HTTPException): unlock(result, old_revision)
    db.rollback()
    assert unlock(earlier).status == "DRAFT"


def test_generation_preserves_locked_customer_while_refreshing_unlocked(db, monkeypatch):
    clock(monkeypatch, "2026-10-01")
    seed(db, [movement("a", "10", "2")])
    row = advance(db, advance(db, advance(db, closing(db), "PENDING"), "CONFIRMED"), "LOCKED")
    revision = row.revision
    db.add(movement("other", "5", "3", customer_code="OTHER")); db.commit()
    from app.services.carton_procurement import generate_closings
    from app.schemas.carton_procurement import CartonClosingGenerateRequest
    generated = generate_closings(db, CartonClosingGenerateRequest(factory_id="huaxing", period="2026-09"), USER)
    assert {item.customer_code: item.status for item in generated} == {"TEST": "LOCKED", "OTHER": "DRAFT"}
    assert row.revision == revision and row.ending_amount == 20
