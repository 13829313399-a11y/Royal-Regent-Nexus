"""P0: production authorization/HTTP flow on disposable synthetic SQLite."""
import importlib
import json
from contextlib import asynccontextmanager
from pathlib import Path
import pytest
from test_assistant_api import env, session, payload


def test_cap_001_002_diagnostic_reasons_and_chat_independence(env, tmp_path):
    client, _, calls, patch = env
    from app.core.config import settings
    from app.services.assistant.search_capabilities import capability, validate
    from app.services.assistant.errors import AssistantError
    from app.schemas.assistant import SendMessage
    patch.setattr(settings, "assistant_search_endpoint", "")
    assert capability()["reason_code"] == "search_unconfigured"
    endpoint = "https://synthetic.example.test/api/v1/services/aigc/multimodal-generation/generation"
    patch.setattr(settings, "assistant_search_endpoint", endpoint)
    patch.setattr(settings, "assistant_search_capabilities_file", "")
    assert capability()["reason_code"] == "search_profile_missing"
    path = tmp_path / "search.json"
    patch.setattr(settings, "assistant_search_capabilities_file", str(path))
    assert capability()["reason_code"] == "search_profile_invalid"
    data = dict(model=settings.assistant_model, endpoint=endpoint, region=settings.assistant_search_region,
                last_result={"status": "success", "at": "2020-01-01"}, verified_combinations=[])
    path.write_text(json.dumps(data), encoding="utf-8")
    assert capability()["reason_code"] == "search_combination_unverified"
    data["verified_combinations"] = [dict(model=settings.assistant_model, input="text", thinking="off",
        forced_search=True, source_return=True, inline_citations=True, verified_at="2020-01-01T00:00:00Z")]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert capability()["verification"] == "verified"
    assert capability()["last_result"] is None  # no shared-profile result attributed to this user
    request = SendMessage.model_validate(payload(protocol_version=2, web_search="on", thinking="on"))
    with pytest.raises(AssistantError) as failure:
        validate(request)
    assert failure.value.detail["code"] == "unsupported_combination"
    assert request.thinking == "on"
    data["region"] = "other-region"
    path.write_text(json.dumps(data), encoding="utf-8")
    assert capability()["reason_code"] == "search_profile_mismatch"
    # Search configuration cannot prevent an unrelated ordinary chat.
    response = client.post(f"/api/assistant/sessions/{session(client)}/messages", json=payload())
    assert "event: run.completed" in response.text and len(calls) == 1
    cap = client.get("/api/assistant/capabilities").json()
    assert cap["execution_status"]["last_success"] is not None
    assert cap["search"]["last_success"] is None
    assert "synthetic-never-sent" not in json.dumps(cap)


@pytest.mark.parametrize("code,status", [("provider_auth",401),("provider_access",403),
    ("provider_rate_limit",429),("provider_budget_exhausted",429),("provider_timeout",504)])
def test_cap_003_errors_have_trace_and_never_retry_paid_step(env, code, status):
    client, _, _, patch = env
    from app.services.assistant import provider
    from app.services.assistant.errors import AssistantError
    attempts = []
    @asynccontextmanager
    async def failed(body):
        attempts.append(body)
        raise AssistantError(code, "合成供应商故障", status, True)
        yield  # pragma: no cover
    patch.setattr(provider, "open_stream", failed)
    sid = session(client)
    request = payload()
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=request)
    frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1]["code"] == code and frames[-1]["request_id"]
    assert frames[-1]["run_id"] and len(attempts) == 1
    again = client.post(f"/api/assistant/sessions/{sid}/messages", json=request)
    assert again.json()["reused"] and len(attempts) == 1
    assert client.get("/api/assistant/capabilities").json()["execution_status"]["last_failure"]["code"] == code
    client.cookies.set("rr_session", "bob")
    assert client.get("/api/assistant/capabilities").json()["execution_status"]["last_failure"] is None


def test_cap_005_cross_valid_factory_denied_by_real_authorizer(env):
    _, dbm, _, _ = env
    from test_work_center_api import actor
    from app.services.assistant import business
    from app.services.assistant.errors import AssistantError
    from app.models.injection_scheduling import Demand
    from app.services.injection_scheduling import queries
    from app.schemas.injection_scheduling import Query
    facts = json.loads((Path(__file__).parent / "fixtures/assistant_v3/facts.json").read_text(encoding="utf-8"))
    with dbm.SessionLocal() as db:
        for ident, state, kg, slack in [("A1","READY",100,24),("A2","WAIT_MATERIAL",20.5,-1),("A3","HELD",0,None)]:
            db.add(Demand(id=ident,factory_id="huakang-a",mold_code="synthetic",dispatch_state=state,
                          remaining_material_kg=kg,delivery_slack_hours=slack))
        db.add(Demand(id="B1",factory_id="huakang-b",mold_code="synthetic",remaining_material_kg=9000))
        db.commit()
        original = queries.summary(db, Query(factory_id="huakang-a"))
    user = actor("alice",factory="huakang-a",department="production",permissions=("injection_scheduling:read",))
    result, _, _ = business.query(user,"get_injection_overview",{"factory_id":"huakang-a"},"synthetic-run")
    assert result["reference_summary"]["values"] == original
    for key in ("held_count","wait_material_count","forecast_late_count","warehouse_shortage_kg"):
        assert result["summary"][key] == facts["injection"][key]
    assert result["summary"]["remaining_material_kg"] == float(facts["injection"]["remaining_material_kg"])
    with pytest.raises(AssistantError) as denied:
        business.query(user,"get_injection_overview",{"factory_id":"huakang-b"},"synthetic-run")
    assert denied.value.status_code == 403 and denied.value.detail["code"] == "business_forbidden"


def test_admin_diagnostics_require_existing_global_system_permission(env):
    client, _, _, _ = env
    from app.services.assistant import diagnostics
    from test_work_center_api import actor
    from app.services.assistant.errors import AssistantError
    assert client.get("/api/assistant/diagnostics").status_code == 403
    for user in [actor(), actor(permissions=("system:access_manage",)), actor(permissions=("internal_quote:read",))]:
        with pytest.raises(AssistantError):
            diagnostics.details(user)
    permitted = actor(factory="group",department="system",permissions=("system:access_manage",))
    output = diagnostics.details(permitted)
    assert output["paid_retry"] == "explicit_only"
    assert not any(key in json.dumps(output) for key in ("synthetic-never-sent", "provider.example.test", ".env", "password"))


def test_offline_native_replay_uses_production_parser_and_rejects_unplanned_calls():
    import asyncio
    from assistant_v3_support import ReplayTransport
    from app.services.assistant.native_search import parse
    raw = 'data: {"request_id":"synthetic-P0","output":{"choices":[{"finish_reason":"stop","message":{"content":[{"text":"合成来源[ref_1]"}]}}],"search_info":{"search_results":[{"index":1,"url":"https://example.test/official","title":"合成"}]}}}\n\n'
    replay = ReplayTransport([raw])
    async def scenario():
        async with replay.open({"input":{"messages":[{"role":"user","content":"公开合成问题"}]}}) as chunks:
            events = [item async for item in parse(chunks)]
        assert any(item["kind"] == "sources" for item in events)
        assert any(item["kind"] == "request_id" and item["value"] == "synthetic-P0" for item in events)
        with pytest.raises(AssertionError, match="No provider replay"):
            async with replay.open({}):
                pass
    asyncio.run(scenario())
    replay.assert_private_absent(["SYN-O-A001", "合成内部客户甲"])


def test_expired_execution_metadata_is_not_disclosed(env):
    client, dbm, _, patch = env
    from app.core.config import settings
    from app.models.assistant import AssistantSession
    sid = session(client)
    client.post(f"/api/assistant/sessions/{sid}/messages", json=payload())
    with dbm.SessionLocal() as db:
        db.get(AssistantSession, sid).updated_at = 1
        db.commit()
    patch.setattr(settings, "assistant_retention_days", 1)
    assert client.get("/api/assistant/capabilities").json()["execution_status"]["last_success"] is None
