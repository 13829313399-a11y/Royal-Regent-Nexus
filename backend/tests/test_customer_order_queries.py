"""Shared native/assistant read facts, using the real ledger migration only."""
from datetime import date
from decimal import Decimal

from sqlalchemy import event

from test_customer_order_ledger import db, engine, client, Line
from app.services import customer_order_queries as queries, customer_order_schedule as schedule


def seed(db):
    facts = [
        ("SYN-A1", "huaxing", "1000", "600", "active", "2026-10-24"),
        ("SYN-A2", "huaxing", "800", "800", "active", "2026-10-22"),
        ("SYN-A3", "huaxing", "500", "0", "active", "2026-10-22"),
        ("SYN-B1", "huakang-b", "9000", "0", "active", "2026-10-20"),
    ]
    for ident, factory, quantity, shipped, status, due in facts:
        db.add(Line(id=ident, factory_id=factory, customer_code="synthetic", customer_name="合成客户",
                    identity_key=ident, reference_no=ident, product_no="PRODUCT-1", quantity=Decimal(quantity),
                    shipped_quantity=Decimal(shipped), status=status, data={"requested_ship_date": due},
                    created_at="2026-10-20 00:00:00", updated_at="2026-10-20 00:00:00"))
    db.commit()


def test_progress_is_exact_whole_filter_and_matches_native_schedule(db, client):
    seed(db)
    statements = []
    def capture(conn, cursor, statement, *args):
        statements.append(statement)
    event.listen(db.bind, "before_cursor_execute", capture)
    try:
        query = queries.statement("huaxing")
        totals = queries.progress(db, query, today=date(2026, 10, 23))
        total, first_page = queries.page(db, query, page_number=1, page_size=1)
        native = client.get("/api/customer-order-ledger/lines", params={"factory_id": "huaxing", "page_size": 1})
        assert native.status_code == 200, native.text
        assert native.json()["total"] == total == 3 and native.json()["items"][0]["id"] == first_page[0].id
        expected = schedule.read_schedule(db, factory="huaxing", customer="synthetic", customer_name="合成客户",
            q="", date_from=None, date_to=None, pages={"unshipped": 1, "shipped": 1, "cancelled": 1}, page_size=50)
        assert totals["unfinished_count"] == 2 and totals["remaining_quantity"] == "900" and totals["overdue_count"] == 1
        assert all(totals[k] == expected["summary"][k] for k in ("order_count", "ordered_quantity", "shipped_quantity", "remaining_quantity"))
        assert expected["sections"]["unshipped"]["total"] == 2 and expected["sections"]["shipped"]["total"] == 2
        assert not any(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) for sql in statements)
    finally:
        event.remove(db.bind, "before_cursor_execute", capture)


def test_null_cancelled_invalid_dates_and_fractional_quantities_are_not_inferred(db):
    seed(db)
    a1, a2, a3 = [db.get(Line, ident) for ident in ("SYN-A1", "SYN-A2", "SYN-A3")]
    a1.quantity = Decimal("600.1001")
    a1.data = {"requested_ship_date": "2026-02-30"}
    a2.status = "cancelled"
    a3.quantity = None
    db.commit()
    total = queries.progress(db, queries.statement("huaxing"), today=date(2026, 10, 23))
    assert total["remaining_quantity"] == "0.1001"
    assert total["remaining_unknown_count"] == 1 and total["unknown_quantity_count"] == 1
    assert total["unfinished_count"] == 2 and total["overdue_count"] == 0 and total["overdue_unknown_count"] == 2
    assert total["cancelled_count"] == 1
    cancelled = queries.progress(db, queries.statement("huaxing", view="cancelled"))
    assert cancelled["remaining_quantity"] == "0" and cancelled["unfinished_count"] == 0


def test_selection_search_and_native_factory_denial(db, client):
    seed(db)
    row = db.get(Line, "SYN-A1")
    row.reference_no = "literal_%_reference"
    db.commit()
    for params, ids in [({"q": "_%_"}, ["SYN-A1"]), ({"view": "unshipped"}, ["SYN-A1", "SYN-A3"]),
                        ({"customer_code": "missing"}, [])]:
        total, rows = queries.page(db, queries.statement("huaxing", **params))
        native = client.get("/api/customer-order-ledger/lines", params={"factory_id": "huaxing", **params}).json()
        assert [r.id for r in rows] == [r["id"] for r in native["items"]] == ids and total == native["total"]
    selected = queries.progress(db, queries.statement("huaxing", resource_id="SYN-A3"), today=date(2026, 10, 23))
    assert selected["order_count"] == 1 and selected["remaining_quantity"] == "500"
    assert queries.page(db, queries.statement("huaxing", resource_id="SYN-B1"))[0] == 0
    denied = client.get("/api/customer-order-ledger/lines", params={"factory_id": "huakang-b"})
    assert denied.status_code == 403 and "SYN-B1" not in denied.text and "9000" not in denied.text


def test_pagination_does_not_repeat_or_hide_exact_total(db):
    seed(db)
    pages = [queries.page(db, queries.statement("huaxing"), page_number=p, page_size=2) for p in (1, 2, 3)]
    assert [total for total, _ in pages] == [3, 3, 3]
    assert [[r.id for r in rows] for _, rows in pages] == [["SYN-A1", "SYN-A2"], ["SYN-A3"], []]


def test_bounded_native_detail_keeps_exact_history_count(db):
    from app.models.customer_order_ledger import OrderLedgerVersion as Version
    from app.services import customer_order_ledger as ledger
    seed(db)
    for version in range(1, 24):
        db.add(Version(id=f"SYN-V{version}", line_id="SYN-A1", version=version, data={"note": str(version)},
            reason="synthetic", actor="test", created_at="2026-10-23 00:00:00"))
    db.commit()
    line = db.get(Line, "SYN-A1")
    full, bounded = ledger.detail(db, line), ledger.detail(db, line, history_limit=20)
    assert len(full["versions"]) == 23 and "history_counts" not in full
    assert bounded["versions"] == full["versions"][:20]
    assert bounded["history_counts"]["versions"] == 23
