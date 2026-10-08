"""Synthetic users and explicitly migrated disposable SQLite only."""
import asyncio
from contextlib import asynccontextmanager
import importlib
import importlib.util
import json
from pathlib import Path
import time
from uuid import uuid4
import pytest
from sqlalchemy import select, inspect, text
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_auth_api import make_client


@pytest.fixture
def env(monkeypatch, tmp_path):
    client = make_client(monkeypatch, SEED_DEFAULT_ACCOUNTS="false", ASSISTANT_ENABLED="true",
        ASSISTANT_QWEN_API_KEY="synthetic-never-sent", ASSISTANT_QWEN_BASE_URL="https://provider.example.test/v1",
        ASSISTANT_MODEL="synthetic-model", ASSISTANT_MODEL_CAPABILITIES_FILE="", THREE_D_CONNECTOR_ENABLED="false",
        ASSISTANT_STORAGE_DIR=str(tmp_path / "images"))
    with client:
        dbm = importlib.import_module("app.db")
        assert not any(n.startswith("nexus_assistant_") for n in inspect(dbm.engine).get_table_names())
        migration = importlib.import_module("alembic")
        spec = importlib.util.spec_from_file_location("assistant_migration", Path(__file__).parents[1] / "alembic/versions/20260929_0131_nexus_assistant.py")
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        with dbm.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
        auth = importlib.import_module("app.models.auth")
        authsvc = importlib.import_module("app.services.auth")
        with dbm.SessionLocal() as db:
            for name in ("alice", "bob"):
                db.add(auth.AuthUser(id=name, username=name, display_name="合成测试", password_salt="unused", password_hash="unused", status="active"))
                db.flush()
                db.add(auth.AuthSession(id=name, user_id=name, token_hash=authsvc.hash_session_token(name), expires_at="2099-01-01 00:00:00", status="active"))
            db.commit()
        client.cookies.set("rr_session", "alice")
        provider = importlib.import_module("app.services.assistant.provider")
        calls = []
        @asynccontextmanager
        async def simulated(body):
            calls.append(body)
            async def chunks():
                values = [dict(id="synthetic", choices=[dict(index=0, delta={"reasoning_content": "核对资料"}, finish_reason=None)]),
                    dict(choices=[dict(delta={"content": "曜灵：自由回答\n\n```js\nconst n = 1;\n```"}, finish_reason=None)]),
                    dict(choices=[dict(delta={}, finish_reason="stop")]), dict(choices=[], usage={"total_tokens": 12})]
                raw = "".join("data: " + json.dumps(v, ensure_ascii=False) + "\r\n\r\n" for v in values) + "data: [DONE]\r\n\r\n"
                for byte in raw.encode(): yield bytes([byte])
            yield chunks()
        monkeypatch.setattr(provider, "open_stream", simulated)
        yield client, dbm, calls, monkeypatch


def session(client, key=None):
    r = client.post("/api/assistant/sessions", json={"client_request_id": key or uuid4().hex})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def payload(**values):
    return dict(client_request_id=uuid4().hex, text="解释 JavaScript 闭包，给两个例子", **values)


def test_stream_idempotency_history_export_and_ownership(env):
    client, dbm, calls, _ = env
    sid = session(client)
    importlib.import_module("app.core.config").settings.document_tools_ai_mode = "off"
    body = payload()
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=body)
    assert response.status_code == 200, response.text
    assert "event: run.completed" in response.text, response.text
    assert "曜灵" in response.text and "reasoning" in response.text
    assert len(calls) == 1 and calls[0]["messages"][-1]["content"][0]["text"] == body["text"]
    assert "enable_thinking" not in calls[0] and "max_tokens" not in calls[0] and "tools" not in calls[0]
    retry = client.post(f"/api/assistant/sessions/{sid}/messages", json=body)
    assert retry.json()["reused"] is True and len(calls) == 1
    run_id = retry.json()["run_id"]
    assert client.post(f"/api/assistant/sessions/{sid}/messages", json=body | {"text": "different"}).status_code == 409
    snapshot = client.get(f"/api/assistant/runs/{run_id}").json()
    assert snapshot["state"] == "completed" and snapshot["usage"]["total_tokens"] == 12
    assert client.get(f"/api/assistant/sessions/{sid}/runs/lookup", params={"client_request_id":body["client_request_id"]}).json()["run_id"] == run_id
    assert "自由回答" in client.get(f"/api/assistant/sessions/{sid}/export").text
    client.cookies.set("rr_session", "bob")
    for path in (f"sessions/{sid}/messages", f"sessions/{sid}/export", f"runs/{run_id}"):
        assert client.get("/api/assistant/"+path).status_code == 404
    assert client.post(f"/api/assistant/runs/{run_id}/cancel").status_code == 404
    assert client.delete(f"/api/assistant/sessions/{sid}").status_code == 404
    assert client.get("/api/assistant/sessions").json()["items"] == []


def test_schema_pending_and_disabled_do_not_break_business(env):
    client, dbm, _, _ = env
    settings = importlib.import_module("app.core.config").settings
    assert client.get("/api/assistant/capabilities").json()["connection_status"] == "unverified"
    settings.assistant_enabled = False
    assert client.post("/api/assistant/sessions", json={"client_request_id":"12345678"}).status_code == 503
    assert client.get("/health").status_code == 200
    settings.assistant_enabled = True
    with dbm.engine.begin() as db: db.execute(text("DROP TABLE nexus_assistant_attachments"))
    assert client.get("/api/assistant/capabilities").json()["schema_status"] == "schema_pending"
    assert client.get("/api/assistant/sessions").status_code == 503
    assert client.get("/health").status_code == 200


def test_create_rename_delete_and_origin(env):
    client, _, _, _ = env
    sid = session(client, "create-once")
    assert session(client, "create-once") == sid
    path = f"/api/assistant/sessions/{sid}"
    assert client.patch(path, json={"title":"我的测试", "revision":1}).json()["revision"] == 2
    assert client.patch(path, json={"title":"冲突", "revision":1}).status_code == 409
    assert client.patch(path, json={"title":"恶意", "revision":2}, headers={"Origin":"https://evil.test"}).status_code == 403
    invalid = client.post(path+"/messages", json=payload() | {"owner_user_id":"bob"})
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "invalid_request"
    assert invalid.json()["detail"]["request_id"] == invalid.headers["x-request-id"]
    assert client.delete(path).json()["deletion_state"] == "deleted"
    assert client.get(path+"/messages").status_code == 404
    assert client.post("/api/assistant/sessions",json={"client_request_id":"create-once"}).status_code == 409


def test_provider_errors_are_not_user_auth_errors(env):
    client, _, calls, monkeypatch = env
    provider = importlib.import_module("app.services.assistant.provider")
    errors = importlib.import_module("app.services.assistant.errors")
    @asynccontextmanager
    async def denied(body):
        raise errors.AssistantError("provider_auth", "模型连接认证失败", 502)
        yield
    monkeypatch.setattr(provider, "open_stream", denied)
    r = client.post(f"/api/assistant/sessions/{session(client)}/messages", json=payload())
    assert r.status_code == 200 and "event: run.failed" in r.text and "provider_auth" in r.text
    assert client.get("/api/auth/me").status_code == 200


def test_interrupted_and_usage_unknown(env):
    client, _, _, monkeypatch = env
    provider = importlib.import_module("app.services.assistant.provider")
    @asynccontextmanager
    async def incomplete(body):
        async def chunks():
            yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        yield chunks()
    monkeypatch.setattr(provider, "open_stream", incomplete)
    sid = session(client)
    r = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload())
    assert "run.interrupted" in r.text
    saved = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]
    assert saved["content_parts"] == [{"type":"text","text":"partial"}]
    assert client.get(f'/api/assistant/runs/{saved["run_id"]}').json()["usage"] is None


def test_parallel_admission_lease_and_cancel(env):
    from concurrent.futures import ThreadPoolExecutor
    import threading
    client, dbm, _, _ = env
    svc = importlib.import_module("app.services.assistant.service")
    authsvc = importlib.import_module("app.services.auth")
    auth = importlib.import_module("app.models.auth")
    schema = importlib.import_module("app.schemas.assistant")
    settings = importlib.import_module("app.core.config").settings
    with dbm.SessionLocal() as db: user = authsvc.build_auth_context(db, db.get(auth.AuthUser,"alice"))
    settings.assistant_global_concurrency = 1
    ids = [session(client) for _ in range(2)]
    barrier = threading.Barrier(2)
    def start(sid):
        barrier.wait()
        try: return svc.admit(user, sid, schema.SendMessage(**payload()))
        except Exception as e: return e.status_code
    with ThreadPoolExecutor(2) as pool: results = list(pool.map(start,ids))
    assert len([r for r in results if isinstance(r,dict)]) == 1
    assert 429 in results
    admitted = next(r for r in results if isinstance(r,dict))
    with ThreadPoolExecutor(1) as pool: pool.submit(svc.cancel,user,admitted["run_id"]).result()
    assert svc.control(admitted["run_id"],admitted["lease"]) == "cancelled"
    with pytest.raises(Exception): svc.control(admitted["run_id"],admitted["lease"],terminal="completed")
    run = svc.admit(user,ids[1],schema.SendMessage(**payload()))
    model = importlib.import_module("app.models.assistant")
    with svc.transaction() as db: db.get(model.AssistantRun,run["run_id"]).lease_expires_at = time.time()-1
    assert svc.snapshot(user,rid=run["run_id"])["state"] == "interrupted"


def test_forced_password_epoch_and_revocation(env):
    client, dbm, _, _ = env
    auth = importlib.import_module("app.models.auth")
    runtime = importlib.import_module("app.services.assistant.runtime")
    schema = importlib.import_module("app.schemas.assistant")
    from starlette.requests import Request
    req = Request({"type":"http","method":"POST","path":"/api/assistant/sessions/test/messages","headers":[(b"cookie",b"rr_session=alice")]})
    original = runtime.authenticate(req)
    sid = session(client)
    with dbm.SessionLocal() as db:
        profile = db.get(auth.EmployeeProfile,"alice")
        if profile is None:
            profile = auth.EmployeeProfile(user_id="alice", employment_epoch=2)
            db.add(profile)
        else: profile.employment_epoch += 1
        db.commit()
    assert client.get(f"/api/assistant/sessions/{sid}/messages").status_code == 404
    with pytest.raises(Exception): runtime.revalidate(req,original,schema.SendMessage(**payload()))
    with dbm.SessionLocal() as db: db.get(auth.AuthUser,"alice").force_password_change=1; db.commit()
    assert client.get("/api/assistant/capabilities").status_code == 403
    with dbm.SessionLocal() as db: db.get(auth.AuthUser,"alice").force_password_change=0; db.get(auth.AuthSession,"alice").status="revoked"; db.commit()
    assert client.get("/api/assistant/capabilities").status_code == 401


def viewer_for(dbm, name="alice"):
    auth = importlib.import_module("app.models.auth")
    svc = importlib.import_module("app.services.auth")
    with dbm.SessionLocal() as db:
        return svc.build_auth_context(db, db.get(auth.AuthUser, name))


def verified_profile(tmp_path, **values):
    settings = importlib.import_module("app.core.config").settings
    path = tmp_path / "synthetic-profile.json"
    path.write_text(json.dumps(dict(model=settings.assistant_model, base_url=settings.assistant_qwen_base_url,
        region="synthetic", documentation=["synthetic protocol fixture only"], verified_at="synthetic-test",
        verified_combinations=["text", "tools", "vision"], function_calling=True, vision=True, **values)), encoding="utf-8")
    settings.assistant_model_capabilities_file = str(path)
    return settings


def test_tools_roundtrip_citations_audience_and_unknown_usage(env, tmp_path):
    client, dbm, _, monkeypatch = env
    verified_profile(tmp_path)
    provider = importlib.import_module("app.services.assistant.provider")
    svc = importlib.import_module("app.services.assistant.service")
    model = importlib.import_module("app.models.assistant")
    bodies = []
    @asynccontextmanager
    async def upstream(body):
        bodies.append(body)
        async def chunks():
            if len(bodies) == 1:
                values = [
                    {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"tool-one","function":{"name":"help_describe_element","arguments":'{"help_id":"injection.'}}]}}]},
                    {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":"remaining_shots\"}"}}]},"finish_reason":"tool_calls"}]},
                ]
            else:
                values = [{"choices":[{"delta":{"content":"根据经过核对的注塑说明。"},"finish_reason":"stop"}]}, {"choices":[],"usage":{"total_tokens":20}}]
            for value in values: yield ("data: "+json.dumps(value)+"\n\n").encode()
            yield b'data: [DONE]\n\n'
        yield chunks()
    monkeypatch.setattr(provider,"open_stream",upstream)
    sid = session(client)
    result = client.post(f"/api/assistant/sessions/{sid}/messages",json=payload())
    assert "run.completed" in result.text, result.text
    assert len(bodies)==2 and bodies[1]["messages"][-1]["role"]=="tool"
    message = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]
    assert message["help_citations"][0]["id"]=="injection.remaining_shots"
    assert client.get(f'/api/assistant/runs/{message["run_id"]}').json()["usage"] is None
    from types import SimpleNamespace
    with dbm.SessionLocal() as db:
        filtered=svc.message_out(db.get(model.AssistantMessage,message["id"]),SimpleNamespace(permissions=["carton_supplier:read"]))
        assert filtered["help_citations"]==[] and "不再适用" in filtered["content_parts"][0]["text"]
    assert "工具记录" in client.get(f"/api/assistant/sessions/{sid}/export").text


def test_images_normalization_ownership_context_export_and_cleanup(env, tmp_path):
    from PIL import Image
    from io import BytesIO
    client, dbm, calls, monkeypatch = env
    verified_profile(tmp_path)
    storage = importlib.import_module("app.services.assistant.storage")
    model = importlib.import_module("app.models.assistant")
    sid = session(client)
    raw = BytesIO(); Image.new("RGB",(300,300),(50,130,100)).save(raw,"PNG")
    upload = client.post(f"/api/assistant/sessions/{sid}/attachments",files={"file":("x.png",raw.getvalue(),"image/png")})
    assert upload.status_code==200,upload.text
    ident=upload.json()["id"]
    client.cookies.set("rr_session","bob")
    assert client.get(f"/api/assistant/attachments/{ident}/content").status_code==404
    client.cookies.set("rr_session","alice")
    r=client.post(f"/api/assistant/sessions/{sid}/messages",json=payload(attachment_ids=[ident]))
    assert "run.completed" in r.text,r.text
    assert calls[-1]["messages"][-1]["content"][-1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "data:image/png;base64," in client.get(f"/api/assistant/sessions/{sid}/export").text
    assert client.delete(f"/api/assistant/attachments/{ident}").status_code==409
    assert client.post(f"/api/assistant/sessions/{sid}/attachments",files={"file":("fake.png",b"not-image","image/png")}).status_code==422
    original = Path.unlink
    def locked(path, *args, **kwargs):
        if path.name==ident+".png": raise PermissionError("synthetic file lock")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,"unlink",locked)
    assert client.delete(f"/api/assistant/sessions/{sid}").status_code==202
    assert client.get(f"/api/assistant/attachments/{ident}/content").status_code==404
    monkeypatch.setattr(Path,"unlink",original)
    client.get("/api/assistant/sessions")
    assert not storage.path_for(ident+".png").exists()
    with dbm.SessionLocal() as db: assert db.get(model.AssistantAttachment,ident) is None


def test_complete_export_pagination_and_context_window(env):
    client, dbm, _, _=env
    model=importlib.import_module("app.models.assistant")
    svc=importlib.import_module("app.services.assistant.service")
    schema=importlib.import_module("app.schemas.assistant")
    settings=importlib.import_module("app.core.config").settings
    user=viewer_for(dbm); sid=session(client)
    run=svc.admit(user,sid,schema.SendMessage(**payload()))
    svc.control(run["run_id"],run["lease"],terminal="completed",usage={"total_tokens":1})
    with dbm.SessionLocal() as db:
        for i in range(3,125):
            db.add(model.AssistantMessage(id=uuid4().hex,session_id=sid,run_id=run["run_id"],seq=i,
                role="user" if i%2 else "assistant",content_parts=[{"type":"text","text":f"history-{i}:"+"字"*100}],
                status="completed",help_citations=[],context_descriptor=None,created_at=time.time()))
        db.commit()
    latest=client.get(f"/api/assistant/sessions/{sid}/messages").json()
    assert len(latest["items"])==50 and latest["next_cursor"]
    output=client.get(f"/api/assistant/sessions/{sid}/export")
    assert "history-3:" in output.text and "history-124:" in output.text
    assert output.headers["cache-control"]=="private, no-store"
    settings.assistant_context_character_budget=2500
    r=client.post(f"/api/assistant/sessions/{sid}/messages",json=payload())
    assert "context.window" in r.text and "run.completed" in r.text


def test_budget_unknown_is_not_zero_and_retention_is_opt_in(env, tmp_path):
    client,dbm,_,_=env
    settings=verified_profile(tmp_path)
    settings.assistant_max_output_tokens=100
    settings.assistant_context_character_budget=1000
    settings.assistant_max_tool_rounds=1
    settings.assistant_daily_token_budget=8200
    svc=importlib.import_module("app.services.assistant.service")
    schema=importlib.import_module("app.schemas.assistant")
    model=importlib.import_module("app.models.assistant")
    user=viewer_for(dbm); sid=session(client)
    first=svc.admit(user,sid,schema.SendMessage(**payload()))
    svc.control(first["run_id"],first["lease"],terminal="interrupted",usage=None)
    assert client.delete(f"/api/assistant/sessions/{sid}").status_code==200
    denied=client.post(f"/api/assistant/sessions/{session(client)}/messages",json=payload())
    assert denied.status_code==429 and denied.json()["detail"]["code"]=="daily_budget_exhausted"
    settings.assistant_daily_token_budget=None
    old=session(client)
    with dbm.SessionLocal() as db: db.get(model.AssistantSession,old).updated_at=time.time()-3*86400; db.commit()
    assert client.get(f"/api/assistant/sessions/{old}/messages").status_code==200
    settings.assistant_retention_days=1
    assert client.get(f"/api/assistant/sessions/{old}/messages").status_code==404
    client.get("/api/assistant/sessions")
    with dbm.SessionLocal() as db: assert db.get(model.AssistantSession,old).deletion_state=="deleted"


def test_help_scope_forgery_stale_sources_and_optional_flags(env):
    client,dbm,_,monkeypatch=env
    registry=importlib.import_module("app.services.assistant.help_registry")
    from types import SimpleNamespace
    supplier=SimpleNamespace(permissions=["carton_supplier:read"])
    assert all(a.audience in ("all","supplier") for a in registry.visible(supplier))
    with pytest.raises(Exception): registry.get(supplier,"injection.remaining_shots")
    with pytest.raises(Exception): registry.tool(supplier,"business_write",{"query":"x"})
    assert client.get("/api/assistant/help/context",params={"module_id":"injection-scheduling","route_name":"carton-supplier"}).status_code==422
    sid=session(client)
    assert client.post(f"/api/assistant/sessions/{sid}/messages",json=payload(web_search="on")).status_code==422
    assert client.post(f"/api/assistant/sessions/{sid}/messages",json=payload(thinking="on")).status_code==422
    cfg=importlib.import_module("app.core.config")
    parsed=cfg.Settings(_env_file=None,assistant_daily_token_budget="",assistant_retention_days="",assistant_max_output_tokens="")
    assert parsed.assistant_daily_token_budget is None and parsed.assistant_retention_days is None and parsed.assistant_max_output_tokens is None
    assert client.get("/api/assistant/capabilities").headers["cache-control"]=="private, no-store"


def test_provider_http_classification_options_and_unconfigured_help(env, tmp_path):
    client,dbm,_,monkeypatch=env
    provider=importlib.import_module("app.services.assistant.provider")
    capabilities=importlib.import_module("app.services.assistant.capabilities")
    schema=importlib.import_module("app.schemas.assistant")
    settings=verified_profile(tmp_path,thinking="toggle")
    for mode in ("auto","on","off"):
        body=provider.request_body([{"role":"user","content":"original"}],schema.SendMessage(**payload(thinking=mode)))
        if mode=="auto":assert "enable_thinking" not in body
        else:assert body["enable_thinking"] is (mode=="on")
    import httpx2
    real_client=httpx2.AsyncClient
    from app.services.assistant.errors import AssistantError
    # Restore the actual transport wrapper replaced by the general fixture.
    source=importlib.reload(provider)
    for status,upstream_code,code,retry in [(401,'invalid_api_key','provider_auth',False),(403,'forbidden','provider_access',False),(404,'unknown_model','provider_model',False),(429,'insufficient_quota','provider_budget_exhausted',False),(429,'rate_limit','provider_rate_limit',True)]:
        transport=httpx2.MockTransport(lambda request:httpx2.Response(status,json={'error':{'code':upstream_code,'message':'private-upstream-detail'}},headers={'Retry-After':'3'}))
        monkeypatch.setattr(httpx2,'AsyncClient',lambda **kwargs:real_client(transport=transport,**kwargs))
        async def request():
            async with source.open_stream({}) as chunks:
                return [c async for c in chunks]
        with pytest.raises(AssistantError) as err:asyncio.run(request())
        assert err.value.status_code==502 and err.value.detail['code']==code and err.value.detail['retryable']==retry
        assert 'private-upstream-detail' not in str(err.value.detail)
    from pydantic import SecretStr
    settings.assistant_qwen_api_key=SecretStr('')
    assert client.get('/api/assistant/capabilities').json()['configuration_status']=='unconfigured'
    assert client.get('/api/assistant/help/context',params={'module_id':'portal','route_name':'dashboard'}).status_code==200
    settings.assistant_qwen_api_key=SecretStr('synthetic');settings.assistant_model='qwen-ocr'
    assert capabilities.configuration_status()=='invalid'
    client.cookies.clear()
    for path in ('capabilities','sessions','help/articles/portal.overview','attachments/any/content'):
        assert client.get('/api/assistant/'+path).status_code==401
