"""Real domain/API comparisons; provider transport is offline, not live acceptance."""
from datetime import date
from decimal import Decimal
import json

import pytest
from sqlalchemy import event
from test_assistant_api import env, session, payload
from test_work_center_api import actor


def setup(env):
    from app.models.customer_order_ledger import OrderLedgerLine as Line
    from app.services import auth, customer_order_queries as reader
    from app.core.config import settings
    client, dbm, calls, patch = env
    patch.setattr(settings, "authz_mode", "enforce")
    patch.setattr(reader, "shanghai_today", lambda: date(2026, 10, 23))
    from app.services.assistant import orders
    patch.setattr(orders, "now_iso", lambda: "2026-10-23T02:00:00+00:00")
    user = actor("alice", department="sales-business", permissions=("customer_order:read",))
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    with dbm.SessionLocal() as db:
        for ident, factory, qty, shipped, due in [("SYN-O-A001", "huakang-a", 1000, 600, "2026-10-24"),
            ("SYN-O-A002", "huakang-a", 800, 800, "2026-10-22"), ("SYN-O-A003", "huakang-a", 500, 0, "2026-10-22"),
            ("SYN-O-B001", "huakang-b", 9000, 0, "2026-10-20")]:
            db.add(Line(id=ident, factory_id=factory, customer_code="synthetic", customer_name="合成客户",
                identity_key=ident, reference_no=ident, product_no="SYN-PRODUCT", quantity=Decimal(qty), shipped_quantity=Decimal(shipped),
                status="active", data={"requested_ship_date": due, "unit_price_hkd": "999.99", "private_extension": "HIDDEN-EXTENSION"},
                created_at="2026-10-20 00:00:00", updated_at="2026-10-20 00:00:00"))
        db.commit()
    return client, dbm, calls, patch, user


def query(user, **args):
    from app.services.assistant import business
    return business.query(user, "list_customer_orders", {"factory_id": "huakang-a", **args}, "synthetic-order-run")


def test_native_comparison_full_totals_paging_and_projection(env):
    client, dbm, _, _, user = setup(env)
    statements = []
    def capture(conn, cursor, statement, *args): statements.append(statement)
    event.listen(dbm.engine, "before_cursor_execute", capture)
    try:
        result, source, actions = query(user, limit=1)
        native = client.get("/api/customer-order-ledger/lines", params={"factory_id": "huakang-a", "page_size": 1}).json()
    finally:
        event.remove(dbm.engine, "before_cursor_execute", capture)
    assert not any(s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")) for s in statements)
    assert result["total_count"] == native["total"] == 3 and result["returned_count"] == 1 and result["truncated"]
    assert result["metrics"]["unfinished_count"]["value"] == 2
    assert result["metrics"]["remaining_quantity"]["value"] == "900"
    assert result["metrics"]["overdue_count"]["value"] == 1
    assert result["rows"][0]["id"] == native["items"][0]["id"]
    assert result["source_refs"] == [source["source_id"]] and result["scope"]["factory_ids"] == ["huakang-a"]
    assert "9000" not in json.dumps(result) and "HIDDEN-EXTENSION" not in json.dumps(result) and "unit_price" not in json.dumps(result)
    next_page, _, _ = query(user, limit=2, cursor=result["next_cursor"])
    assert [r["id"] for r in next_page["rows"]] == ["SYN-O-A002", "SYN-O-A003"]
    assert next_page["next_cursor"] is None and next_page["metrics"] == result["metrics"]
    detail, _, _ = query(user, resource_id="SYN-O-A001")
    original = client.get("/api/customer-order-ledger/lines/SYN-O-A001?factory_id=huakang-a").json()
    assert detail["scope"]["coverage"] == "selected_resources" and detail["total_count"] == 1
    assert detail["rows"][0]["remaining_quantity"] == original["line"]["remaining_quantity"] == "400"
    assert "detail" in detail["rows"][0] and actions[0]["query"] == {"factory": "huakang-a", "order": "SYN-O-A001"}


@pytest.mark.parametrize("args,code", [({"factory_id": "huakang-b"}, "business_forbidden"),
    ({"resource_id": "SYN-O-B001"}, "source_unavailable"), ({"factory_id": "authorized"}, "factory_unavailable"),
    ({"sql": "SELECT *"}, "tool_invalid"), ({"limit": True}, "tool_invalid"), ({"date_from": "2026-02-30"}, "tool_invalid"),
    ({"date_from": "2026-10-24", "date_to": "2026-10-01"}, "tool_invalid"),
    ({"resource_id": "SYN-O-A001", "view": "cancelled"}, "tool_invalid")])
def test_negative_scope_and_strict_parameters_do_not_leak_facts(env, args, code):
    from app.services.assistant.errors import AssistantError
    _, _, _, _, user = setup(env)
    with pytest.raises(AssistantError) as exc: query(user, **args)
    assert exc.value.detail["code"] == code
    assert not any(s in json.dumps(exc.value.detail) for s in ("9000", "SYN-O-B001", "HIDDEN-EXTENSION"))


def test_cursor_scope_and_unknowns(env):
    from app.models.customer_order_ledger import OrderLedgerLine as Line
    from app.services.assistant.errors import AssistantError
    _, dbm, _, _, user = setup(env)
    first, _, _ = query(user, limit=1)
    with pytest.raises(AssistantError): query(user, q="other", cursor=first["next_cursor"])
    with dbm.SessionLocal() as db:
        db.get(Line, "SYN-O-A003").quantity = None
        db.get(Line, "SYN-O-A001").data = {"requested_ship_date": "2026-02-30"}
        db.commit()
    result, _, _ = query(user)
    assert result["status"] == "partial"
    assert result["metrics"]["remaining_quantity"]["value"] is None
    assert result["metrics"]["overdue_count"]["value"] is None
    assert result["metrics"]["overdue_unknown_count"]["value"] == 2
    empty, _, actions = query(user, q="not-present")
    assert empty["status"] == "empty" and empty["total_count"] == 0 and not actions


def test_snapshot_uses_explicit_shanghai_date_across_utc_midnight(env):
    from app.services.assistant import orders
    from app.models.customer_order_ledger import OrderLedgerLine as Line
    _, dbm, _, patch, user = setup(env)
    patch.setattr(orders, "now_iso", lambda: "2026-10-23T17:37:21+00:00")
    with dbm.SessionLocal() as db:
        db.get(Line, "SYN-O-A001").data = {"requested_ship_date": "2026-10-23"}
        db.commit()
    result, source, _ = query(user)
    assert result["as_of"] == source["as_of"] == "2026-10-24T01:37:21+08:00"
    assert result["business_date"] == "2026-10-24"
    assert result["metrics"]["overdue_count"]["value"] == 2


def test_runtime_persists_structured_snapshot_and_reauthorizes_record_action(env):
    from app.services.assistant import runtime, business
    from app.services import auth
    from app.models.customer_order_ledger import OrderLedgerLine as Line
    client, dbm, calls, patch, user = setup(env)
    patch.setattr(runtime, "authenticate", lambda request: user)
    sid = session(client)
    body = payload(protocol_version=2, intent="my_work", web_search="off",
        page_context=dict(module_id="customer-orders", route_name="customer-order-center", factory_id="huakang-a"))
    body["text"] = "华康A还有多少订单未发完？"
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=body)
    assert "event: run.completed" in response.text, response.text[-2000:]
    message = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]
    result = next(p["result"] for p in message["content_parts"] if p["type"] == "business_snapshot")
    assert result["metrics"]["remaining_quantity"]["value"] == "900" and result["tool_call_id"] == "prequery-0"
    actions = next(p["items"] for p in message["content_parts"] if p["type"] == "actions")
    index = next(i for i, action in enumerate(actions) if action.get("query", {}).get("order") == "SYN-O-A001")
    action_payload = {"run_id": message["run_id"], "index": index}
    action = client.post("/api/assistant/actions/resolve", json=action_payload)
    assert action.status_code == 200 and action.json()["query"]["order"] == "SYN-O-A001", action.text
    assert len(calls) == 1
    supplied = next(m["content"] for m in calls[0]["messages"] if m["role"] == "system" and m["content"].startswith("已受权业务快照"))
    supplied_result = json.loads(supplied.split("：", 1)[1])
    assert supplied_result["metrics"]["remaining_quantity"]["value"] == "900"
    assert supplied_result["step_id"] == "business-0" and "SYN-O-B001" not in supplied
    # A subsequent historical turn cannot fabricate an orphan provider tool result.
    history, _ = runtime.history(user, sid, "future-run", [])
    assert any(r["role"] == "system" and "历史业务快照" in r["content"] for r in history)
    assert not any(r["role"] == "tool" for r in history)
    denied = actor("alice", department="sales-business", permissions=())
    client.app.dependency_overrides[auth.get_current_user] = lambda: denied
    patch.setattr(runtime, "authenticate", lambda request: denied)
    action = client.post("/api/assistant/actions/resolve", json=action_payload)
    assert action.status_code in (403, 410) and "SYN-O-A001" not in action.text
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    patch.setattr(runtime, "authenticate", lambda request: user)
    with dbm.SessionLocal() as db:
        db.delete(db.get(Line, "SYN-O-A001")); db.commit()
    assert client.post("/api/assistant/actions/resolve", json=action_payload).status_code == 410
