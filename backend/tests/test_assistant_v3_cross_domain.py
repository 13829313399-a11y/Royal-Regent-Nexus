"""Independent native readers and real persistence; provider replay is offline."""
from dataclasses import replace
from decimal import Decimal
import json

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from test_assistant_api import env, session, payload, verified_profile


def setup(env):
    from app.services import auth
    from app.services.assistant import runtime
    from test_assistant_v2 import migrate
    from test_assistant_v3_orders import setup as orders_setup
    client, dbm, calls, patch, user = orders_setup(env)
    migrate(dbm)
    patch.setattr(runtime, "authenticate", lambda request: user)
    return client, dbm, calls, patch, user


def selected(*modules):
    refs = {
        "order": dict(module_id="customer-orders", resource_type="order", resource_id="SYN-O-A001"),
        "uv": dict(module_id="uv-operations", resource_type="task", resource_id="PRIVATE-UNREADABLE-UV"),
        "spray": dict(module_id="spray-production", resource_type="demand", resource_id="PRIVATE-UNREADABLE-SPRAY"),
    }
    return dict(selection_id="independent-domains", resources=[refs[m] for m in modules], filters={"factory_id": "huakang-a"})


def answer(client, sid):
    return client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]


def assert_unavailable(result):
    from app.services.assistant.tool_result import validate_result
    validate_result(result, registered_sources=[], registered_resources=[], row_fields=[])
    assert result["status"] in {"failed", "forbidden"}
    assert result["total_count"] is None and result["as_of"] is None
    assert result["rows"] == [] and result["metrics"] == {}
    assert result["source_refs"] == [] and result["allowed_actions"] == []
    assert "PRIVATE-" not in json.dumps(result)


@pytest.mark.parametrize("modules", [("uv", "order", "spray"), ("order", "uv", "spray")])
def test_selected_partial_failure_preserves_native_order_and_history_export(env, modules):
    from app.services.assistant import runtime
    from app.services import auth
    client, dbm, calls, patch, user = setup(env)
    sid = session(client)
    request = payload(protocol_version=2, context_selection=selected(*modules), web_search="off")
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=request)
    assert "event: run.completed" in response.text, response.text[-2000:]
    value = answer(client, sid)
    failures = [p["result"] for p in value["content_parts"] if p["type"] == "business_failure"]
    assert len(failures) == 2
    for result in failures:
        assert_unavailable(result)
        assert result["status"] == "forbidden"
    snapshot = next(p["result"] for p in value["content_parts"] if p["type"] == "business_snapshot")
    native = client.get("/api/customer-order-ledger/lines/SYN-O-A001?factory_id=huakang-a").json()["line"]
    assert snapshot["rows"][0]["remaining_quantity"] == native["remaining_quantity"] == "400"
    evidence = next(p for p in value["content_parts"] if p["type"] == "evidence")
    assert [s["kind"] for s in evidence["sources"]] == ["business"]
    assert [a["status"] for a in evidence["activities"] if a["kind"] == "query_business"].count("failed") == 2
    actions = next(p["items"] for p in value["content_parts"] if p["type"] == "actions")
    assert len(actions) == 1 and actions[0]["resource"]["resource_id"] == "SYN-O-A001"
    assert client.post("/api/assistant/actions/resolve", json=dict(run_id=value["run_id"], index=0)).status_code == 200
    assert len(calls) == 1
    assert "PRIVATE-" not in json.dumps(calls) and "原子一致" in calls[0]["messages"][0]["content"]
    history, _ = runtime.history(user, sid, "future-run", [])
    assert sum("历史查询未取得数据" in m.get("content", "") for m in history if isinstance(m.get("content"), str)) == 2
    assert snapshot["as_of"] in json.dumps(history)
    exported = client.get(f"/api/assistant/sessions/{sid}/export")
    assert exported.status_code == 200 and '"type": "business_failure"' in exported.text
    assert "数量与风险仍未知" in client.get(f"/api/assistant/runs/{value['run_id']}/export").text
    # Successful dependencies still fail closed after permission revocation.
    revoked = replace(user, permissions=frozenset(), grants=())
    client.app.dependency_overrides[auth.get_current_user] = lambda: revoked
    patch.setattr(runtime, "authenticate", lambda request: revoked)
    assert answer(client, sid)["unavailable"]
    assert client.get(f"/api/assistant/runs/{value['run_id']}/export").status_code == 410


def test_all_selected_failures_keep_reasons_without_provider_attempt(env):
    client, _, calls, _, _ = setup(env)
    sid = session(client)
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(
        protocol_version=2, context_selection=selected("uv", "spray"), web_search="off"))
    assert "event: run.failed" in response.text and "business_queries_unavailable" in response.text
    assert not calls
    value = answer(client, sid)
    for p in value["content_parts"]:
        if p["type"] == "business_failure": assert_unavailable(p["result"])
    evidence = next(p for p in value["content_parts"] if p["type"] == "evidence")
    assert evidence["sources"] == [] and all(a["status"] == "failed" for a in evidence["activities"])
    assert "UV 生产未取得数据" in response.text and "喷油生产未取得数据" in response.text


def replay_tools(env, tmp_path, calls):
    from app.services.assistant import provider
    from assistant_v3_support import ReplayTransport
    verified_profile(tmp_path)
    values = [dict(index=i, id=f"query-{i}", type="function", function=dict(name=name, arguments=json.dumps(args)))
              for i, (name, args) in enumerate(calls)]
    raw = "data: " + json.dumps(dict(choices=[dict(delta=dict(tool_calls=values), finish_reason="tool_calls")])) + "\n\ndata: [DONE]\n\n"
    final = 'data: {"choices":[{"delta":{"content":"离线传输回放结束；不代表真实模型验收。"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
    replay = ReplayTransport([raw, final])
    env[3].setattr(provider, "open_stream", replay.open)
    return replay


def test_model_tool_batch_keeps_real_orders_after_domain_sql_failure(env, tmp_path):
    from app.services.assistant import business
    client, dbm, _, patch, user = setup(env)
    from test_work_center_api import actor
    # Grant native injection read; inject a database outage at its actual SELECT.
    grant = actor("alice", department="production", permissions=("injection_scheduling:read",)).grants[0]
    user = replace(user, grants=(*user.grants, grant), permissions=user.permissions | {"injection_scheduling:read"})
    from app.services.assistant import runtime
    from app.services import auth
    patch.setattr(runtime, "authenticate", lambda request: user)
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    replay = replay_tools(env, tmp_path, [
        ("get_injection_overview", {"factory_id": "huakang-a"}),
        ("list_customer_orders", {"factory_id": "huakang-a", "resource_id": "SYN-O-A001"}),
    ])
    statements = []
    def outage(conn, cursor, statement, *args):
        statements.append(statement)
        if statement.lstrip().upper().startswith("SELECT") and "injection_v3_demand" in statement:
            raise OperationalError(statement, {}, Exception("PRIVATE-SQL-CREDENTIAL"))
    event.listen(dbm.engine, "before_cursor_execute", outage)
    try:
        sid = session(client)
        response = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(protocol_version=2, web_search="off"))
    finally:
        event.remove(dbm.engine, "before_cursor_execute", outage)
    assert "event: run.completed" in response.text, response.text[-3000:]
    assert len(replay.calls) == 2
    results = [p["result"] for p in answer(client, sid)["content_parts"] if p["type"] == "tool_result"]
    assert len(results) == 2
    assert_unavailable(results[0])
    assert results[0]["diagnostic_code"] == "business_query_failed"
    assert results[1]["rows"][0]["remaining_quantity"] == "400"
    assert "PRIVATE-SQL" not in json.dumps(replay.calls) and "PRIVATE-SQL" not in response.text
    assert not any(s.lstrip().upper().startswith(("UPDATE INJECTION", "DELETE FROM INJECTION", "INSERT INTO INJECTION")) for s in statements)


@pytest.mark.parametrize("code", ["identity_changed", "context_changed", "cancelled", "run_timeout"])
def test_control_failures_are_never_downgraded_to_domain_results(code):
    from app.services.assistant.business_failures import unavailable
    from app.services.assistant.errors import AssistantError
    exc = AssistantError(code, "control failure", 403)
    with pytest.raises(AssistantError) as caught:
        unavailable(exc, "list_customer_orders", {}, "r", tool_call_id="c", step_id="s", requested_at="2026-10-25T00:00:00Z")
    assert caught.value is exc


def test_identity_change_between_queries_stops_before_second_reader(env):
    from app.services.assistant import business, runtime
    client, _, calls, patch, user = setup(env)
    state, observed = {"user": user}, []
    original = business.query
    def query(*args, **kwargs):
        observed.append(args[1])
        result = original(*args, **kwargs)
        state["user"] = replace(user, identity={**user.identity, "employment_epoch": 2})
        return result
    patch.setattr(business, "query", query)
    patch.setattr(runtime, "authenticate", lambda request: state["user"])
    response = client.post(f"/api/assistant/sessions/{session(client)}/messages", json=payload(
        protocol_version=2, context_selection=selected("order", "uv"), web_search="off"))
    assert "event: run.interrupted" in response.text and "identity_changed" in response.text
    assert observed == ["list_customer_orders"] and not calls


@pytest.mark.parametrize("interruption", ["cancel", "revoke"])
def test_control_guard_keeps_partial_failure_from_bypassing_cancel_or_revocation(env, interruption):
    from app.services.assistant import business, runtime, service
    client, _, calls, patch, user = setup(env)
    state, observed = {"user": user}, []
    original = business.query
    def query(*args, **kwargs):
        observed.append(args[1])
        result = original(*args, **kwargs)
        if interruption == "cancel":
            service.cancel(user, args[3])
        else:
            state["user"] = replace(user, permissions=frozenset(), grants=())
        return result
    patch.setattr(business, "query", query)
    patch.setattr(runtime, "authenticate", lambda request: state["user"])
    sid = session(client)
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(
        protocol_version=2, context_selection=selected("order", "uv"), web_search="off"))
    assert not calls
    if interruption == "cancel":
        assert "event: run.cancelled" in response.text and observed == ["list_customer_orders"]
    else:
        assert "event: run.interrupted" in response.text and "context_changed" in response.text
        value = answer(client, sid)
        assert value["unavailable"] and "SYN-O-A001" not in json.dumps(value)
        assert client.get(f"/api/assistant/runs/{value['run_id']}/export").status_code == 410


@pytest.mark.parametrize("uv_allowed", [True, False])
def test_three_native_domains_keep_independent_facts_times_and_authority(env, tmp_path, uv_allowed):
    from app.services import auth
    from app.services.assistant import runtime
    from test_assistant_v3_uv import setup as uv_setup
    from test_uv_ops import setup_task, user_with as uv_user
    from test_assistant_v3_spray import setup as spray_setup, fixture_order
    from test_spray_ops import user_with as spray_user
    client, dbm, _, patch, user = setup(env)
    uv_setup(env)
    task = setup_task(client, quantity=71)["task"]
    spray_setup(env)
    demand = fixture_order(client, quantity="83", factory="huakang-a")["demand"]
    production = [spray_user("read", factory="huakang-a")]
    if uv_allowed: production.append(uv_user("read"))
    user = replace(user, permissions=user.permissions.union(*(u.permissions for u in production)),
                   grants=(*user.grants, *(g for u in production for g in u.grants)),
                   department_scopes=("sales-business", "production"))
    patch.setattr(runtime, "authenticate", lambda request: user)
    client.app.dependency_overrides[auth.get_current_user] = lambda: user
    replay = replay_tools(env, tmp_path, [
        ("list_customer_orders", dict(factory_id="huakang-a", resource_id="SYN-O-A001")),
        ("get_uv_operations_snapshot", dict(factory_id="huakang-a", resource_id=task["id"])),
        ("get_spray_operations_snapshot", dict(factory_id="huakang-a", view="demands", resource_id=demand["id"])),
    ])
    sid = session(client)
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(
        protocol_version=2, web_search="off") | {"text": "比较订单、UV和喷油的风险"})
    assert "event: run.completed" in response.text, response.text[-4000:]
    parts = answer(client, sid)["content_parts"]
    order_result, uv_result, spray_result = [p["result"] for p in parts if p["type"] == "tool_result"]
    order_native = client.get("/api/customer-order-ledger/lines/SYN-O-A001", params=dict(factory_id="huakang-a"))
    uv_native = client.get("/api/uv-operations/tasks/" + task["id"], params=dict(factory_id="huakang-a"))
    spray_native = client.get("/api/spray-operations/demands/" + demand["id"], params=dict(factory_id="huakang-a"))
    assert order_native.status_code == spray_native.status_code == 200
    assert order_result["rows"][0]["remaining_quantity"] == order_native.json()["line"]["remaining_quantity"] == "400"
    assert spray_result["rows"][0]["lines"][0]["quantity"] == spray_native.json()["data"]["lines"][0]["quantity"]
    assert Decimal(spray_result["rows"][0]["lines"][0]["quantity"]) == 83
    if uv_allowed:
        assert uv_native.status_code == 200
        assert uv_result["rows"][0]["quantity"] == uv_native.json()["data"]["quantity"] == 71
    else:
        assert uv_native.status_code == 403
        assert_unavailable(uv_result)
    successful = [order_result, spray_result] + ([uv_result] if uv_allowed else [])
    sources = next(p["sources"] for p in parts if p["type"] == "evidence")
    assert len(sources) == len(successful)
    for result in successful:
        source = next(s for s in sources if s["source_id"] in result["source_refs"])
        assert result["as_of"] == source["as_of"] and result["scope"]["factory_ids"] == ["huakang-a"]
    assert order_result["as_of"] != spray_result["as_of"]
    assert len({r["scope"]["module_id"] for r in successful}) == len(successful)
    assert len(replay.calls) == 2
    tool_messages = [m for m in replay.calls[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 3
    assert "PRIVATE-PRICE" not in json.dumps(replay.calls) and "commercial_price" not in json.dumps(replay.calls)
    instruction = replay.calls[1]["messages"][0]["content"]
    assert "不能声称原子一致" in instruction and "没有权威映射" in instruction
