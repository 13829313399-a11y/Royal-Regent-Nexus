"""Handoff fixtures exercise production parsers and real isolated persistence."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import time
from uuid import uuid4
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import select
from test_assistant_api import env, session, payload

FIXTURES = Path(__file__).parent / "fixtures" / "assistant_v2"


def fixture(name):
    return json.loads((FIXTURES / (name + ".json")).read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", fixture("provider-streams")["cases"], ids=lambda c: c["id"])
def test_native_fixture_parser_and_aggregate(case):
    from app.services.assistant.native_search import parse
    from app.services.assistant.evidence import RunContent
    from app.services.assistant.errors import AssistantError
    content = RunContent("test-run", "on")
    content.begin("search-0", "search", "search")
    error = None
    async def chunks():
        for byte in case["raw_sse"].encode():
            yield bytes([byte])
    async def run():
        nonlocal error
        try:
            async for item in parse(chunks()):
                if item["kind"] == "delta": content.append("text", item["text"], "search-0")
                elif item["kind"] == "sources": content.web("search-0", item["items"])
                elif item["kind"] == "usage": content.account("search-0", usage=item["usage"], search_count=item["search_count"])
        except AssistantError as exc:
            error = exc.detail["code"]
    asyncio.run(run())
    content.terminal("completed" if error is None else "interrupted")
    expected = case["expected"]
    assert error == expected["provider_error"]
    assert "".join(p["text"] for p in content.parts) == expected["text"]
    assert [s["provider_ref"] for s in content.evidence["sources"]] == expected["retained_provider_refs"]
    assert content.evidence["search"]["execution"] == expected["search_execution"]
    assert content.evidence["search"]["evidence_level"] == expected["evidence_level"]
    if expected["tokens"]:
        assert content.usage_summary()["tokens"] == expected["tokens"]
    assert content.usage_summary()["search_count"] == expected["search_count"]
    assert sum(p["type"] == "evidence" for p in content.snapshot()) == 1


@pytest.mark.parametrize("case", fixture("requests-and-capabilities")["cases"], ids=lambda c: c["id"])
def test_canonical_contract(case):
    from app.schemas.assistant import SendMessage, canonical_request
    from pydantic import ValidationError
    incoming = case.get("incoming_raw", case.get("request"))
    if case["expected"]["disposition"] == "reject_before_admit":
        with pytest.raises(ValidationError): SendMessage.model_validate(incoming)
        return
    actual = json.dumps(canonical_request(SendMessage.model_validate(incoming)), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    assert actual == case["expected"]["canonical_json"]
    assert hashlib.sha256(actual.encode()).hexdigest() == case["expected"]["sha256"]


def test_public_context_never_accepts_private_history(monkeypatch):
    from app.services.assistant.public_context import build_public_search_context, wants_search
    from app.services.assistant.native_search import request_body
    from app.schemas.assistant import SendMessage
    from app.core.config import settings
    monkeypatch.setattr(settings, "assistant_model", "qwen3.7-plus")
    monkeypatch.setattr(settings, "assistant_max_output_tokens", None)
    for case in fixture("public-context")["cases"]:
        request = SendMessage.model_validate(case["input"]["request"])
        if request.web_search == "off":
            assert not wants_search(request)
            continue
        body = request_body(build_public_search_context(case["input"]["explicit_public_query"]), request)
        assert body == case["expected_native_request"]
        serialized = json.dumps(body)
        assert all(secret not in serialized for secret in case["forbidden_native_literals"])


def test_citation_code_and_scope():
    from app.services.assistant.evidence import RunContent
    c = RunContent("r", "on")
    c.append("text", "说明[ref_", "one")
    c.append("text", "1]，`[ref_2]`\n```js\n[ref_3]\n```\n", "one")
    c.append("text", "另一段[ref_1]", "two")
    c.web("one", [dict(index=1, url="https://example.test/one", title="One")])
    c.web("two", [dict(index=1, url="https://example.test/two", title="Two")])
    c.terminal("completed")
    assert len(c.evidence["citations"]) == 2
    assert c.evidence["citations"][0]["source_ids"] != c.evidence["citations"][1]["source_ids"]
    c.account("one", usage=dict(prompt_tokens=10, completion_tokens=2, total_tokens=12), search_count=1)
    c.account("two")
    assert c.usage_summary()["tokens"]["total_tokens"] is None
    assert c.usage_summary()["search_count"] is None


def test_native_capability_profiles_and_option_matrix(tmp_path, monkeypatch):
    from pydantic import SecretStr
    from app.services.assistant import search_capabilities as cap
    from app.services.assistant.errors import AssistantError
    from app.schemas.assistant import SendMessage
    endpoint='https://native.example.test/api/v1/services/aigc/multimodal-generation/generation'
    path=tmp_path/'search.json'
    for key,value in dict(assistant_qwen_api_key=SecretStr('synthetic-only'),assistant_model='qwen3.7-plus',assistant_search_endpoint=endpoint,assistant_search_region='cn-beijing',assistant_search_capabilities_file=str(path)).items():
        monkeypatch.setattr(cap.settings,key,value)
    data=fixture('requests-and-capabilities')
    profiles={case['id']:case['response']['search'] for case in data['capability_cases']}
    for ident, expected in profiles.items():
        profile=dict(model='qwen3.7-plus',endpoint=endpoint,region='cn-beijing',verified_combinations=expected['verified_combinations'],last_result=expected['last_result'])
        if ident=='endpoint-changed-invalidates-search':
            profile['endpoint']=endpoint.replace('native.','old.')
            profile['verified_combinations']=profiles['native-text-verified']['verified_combinations']
        path.write_text(json.dumps(profile),encoding='utf-8')
        assert cap.capability()==expected
    for case in data['option_matrix']:
        profile=profiles[case['capability_case_id']]
        path.write_text(json.dumps(dict(model='qwen3.7-plus',endpoint=endpoint,region='cn-beijing',verified_combinations=profile['verified_combinations'])),encoding='utf-8')
        selection=case['selection']
        request=SendMessage.model_validate(payload(protocol_version=2,web_search=selection['web_search'],thinking=selection['thinking'],attachment_ids=['synthetic'] if selection['input']=='text_image' else []))
        if case['expected_allowed']: cap.validate(request)
        else:
            with pytest.raises(AssistantError): cap.validate(request)
    for key,value in [('assistant_model','changed-model'),('assistant_search_region','changed-region'),('assistant_search_endpoint',endpoint.replace('native.','changed.'))]:
        old=getattr(cap.settings,key);monkeypatch.setattr(cap.settings,key,value)
        assert cap.capability()['verification']=='unverified'
        monkeypatch.setattr(cap.settings,key,old)


def migrate(dbm):
    spec = importlib.util.spec_from_file_location("assistant_v2_migration", Path(__file__).parents[1] / "alembic/versions/20261012_0158_assistant_v2_materials.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            module.upgrade()


def ready(client, ident):
    for _ in range(100):
        r = client.get(f"/api/assistant/files/{ident}")
        if r.json().get("parse_status") in ("ready", "failed"): return r.json()
        time.sleep(.02)
    pytest.fail("bounded parser failed to finish")


def test_document_artifact_revision_export_deletion_and_private_ownership(env):
    client, dbm, calls, _ = env
    migrate(dbm)
    sid = session(client)
    response = client.post(f"/api/assistant/sessions/{sid}/files", files={"file": ("验收.csv", '项目,说明\nA,"第一行\n第二行"\nB,=danger\n'.encode(), "text/csv")})
    assert response.status_code == 200, response.text
    ident = response.json()["id"]
    doc = ready(client, ident)
    assert doc["parse_status"] == "ready"
    assert doc["parse_index"][1] == dict(kind="lines", start=2, end=3)
    client.cookies.set("rr_session", "bob")
    assert client.get(f"/api/assistant/files/{ident}").status_code == 404
    client.cookies.set("rr_session", "alice")
    r = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(protocol_version=2, document_ids=[ident], intent="analyze_files"))
    assert "event: run.completed" in r.text, r.text
    history = client.get(f"/api/assistant/sessions/{sid}/messages").json()
    answer = history["items"][-1]
    assert any(p["type"] == "document_ref" for p in history["items"][0]["content_parts"])
    ev = next(p for p in answer["content_parts"] if p["type"] == "evidence")
    assert ev["sources"][1]["locator"] == dict(kind="lines", start=2, end=3)
    saved = client.post(f"/api/assistant/sessions/{sid}/artifacts", json=dict(source_run_id=answer["run_id"], title="文件清单", kind="checklist", content="- [ ] =danger\n- [x] 检查来源"))
    assert saved.status_code == 200, saved.text
    aid = saved.json()["id"]
    export = client.get(f"/api/assistant/artifacts/{aid}/export?format=csv")
    assert "'=danger" in export.text and "第2–3行" in export.text
    assert client.post(f"/api/assistant/artifacts/{aid}/versions", json=dict(base_revision=1, content="- [x] 新版本")).status_code == 200
    assert client.post(f"/api/assistant/artifacts/{aid}/versions", json=dict(base_revision=1, content="冲突")).status_code == 409
    assert "=danger" in client.get(f"/api/assistant/artifacts/{aid}?revision=1").json()["content"]
    assert client.patch(f"/api/assistant/sessions/{sid}/favorite", json={"favorite":True}).status_code == 200
    assert client.get("/api/assistant/sessions?favorites=true").json()["items"][0]["favorite"]
    assert client.delete(f"/api/assistant/files/{ident}").status_code == 204
    assert client.get(f"/api/assistant/files/{ident}/content").status_code == 410
    assert client.get(f"/api/assistant/artifacts/{aid}").status_code == 410
    assert client.get(f"/api/assistant/artifacts/{aid}/export").status_code == 410
    assert client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]["unavailable"]
    assert client.get("/api/assistant/sessions?q=自由回答").json()["items"] == []


def test_native_runtime_persists_same_evidence_through_recovery_and_export(env):
    client, dbm, calls, monkeypatch = env
    from app.services.assistant import native_search, search_capabilities
    monkeypatch.setattr(search_capabilities, "validate", lambda p: None)
    sample = fixture("provider-streams")["cases"][0]
    @asynccontextmanager
    async def stream(body):
        assert "messages" in body["input"]
        async def chunks():
            yield sample["raw_sse"].encode()
        yield chunks()
    monkeypatch.setattr(native_search, "open_stream", stream)
    sid = session(client)
    body = payload(protocol_version=2, web_search="on")
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=body)
    assert "event: run.completed" in response.text, response.text
    messages = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"]
    rid = messages[-1]["run_id"]
    recovered = client.get(f"/api/assistant/runs/{rid}").json()
    assert recovered["items"][-1]["content_parts"] == messages[-1]["content_parts"]
    assert "https://sources.example.test/material/a" in client.get(f"/api/assistant/runs/{rid}/export").text
    assert len(calls) == 0
    assert client.post(f"/api/assistant/sessions/{sid}/messages", json=body).json()["reused"]


def test_file_failures_and_restart(env):
    client, dbm, _, _ = env
    migrate(dbm)
    sid = session(client)
    for name, raw, error in [("empty.txt", b' ', "file_empty"), ("bad.pdf", b'broken', "pdf_invalid"), ("bad.csv", b'"unterminated', "csv_invalid"), ("bad.txt", b'\xff', "file_encoding")]:
        r = client.post(f"/api/assistant/sessions/{sid}/files", files={"file":(name,raw)})
        ident = r.json()["id"]
        assert ready(client, ident)["error_code"] == error
    from app.models.assistant import AssistantFile
    with dbm.SessionLocal() as db:
        row=db.get(AssistantFile,ident); row.parse_status="parsing"; row.parse_owner="previous-process"; db.commit()
    assert client.get(f"/api/assistant/files/{ident}").json()["error_code"] == "parse_interrupted"
    assert client.post(f"/api/assistant/sessions/{sid}/files", files={"file":("fake.xlsx",b'fake')}).status_code == 422


def test_legacy_followup_retains_document_revocation(env):
    client, dbm, calls, _ = env
    migrate(dbm)
    sid = session(client)
    fid = client.post(f"/api/assistant/sessions/{sid}/files", files={"file":("private.txt",b'private-material-unique')}).json()["id"]
    assert ready(client, fid)["parse_status"] == "ready"
    for version, ids in [(2, [fid]), (1, [])]:
        response = client.post(f"/api/assistant/sessions/{sid}/messages", json=payload(protocol_version=version, document_ids=ids))
        assert "run.completed" in response.text, response.text
    last = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]
    saved = client.post(f"/api/assistant/sessions/{sid}/artifacts", json=dict(source_run_id=last["run_id"],title="derived",kind="markdown",content="derived-private-copy")).json()
    client.delete(f"/api/assistant/files/{fid}")
    assert client.get(f"/api/assistant/runs/{last['run_id']}/export").status_code == 410
    assert client.get(f"/api/assistant/artifacts/{saved['id']}").status_code == 410
    assert all(m["unavailable"] for m in client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"])
    client.post(f"/api/assistant/sessions/{sid}/messages", json=payload())
    assert "private-material-unique" not in json.dumps(calls[-1])


def test_image_followup_revocation(env, tmp_path):
    from test_assistant_api import verified_profile
    from test_auth_api import make_avatar_png
    client, dbm, calls, _ = env
    verified_profile(tmp_path)
    sid=session(client)
    image=client.post(f"/api/assistant/sessions/{sid}/attachments",files={"file":("a.png",make_avatar_png(),"image/png")}).json()["id"]
    assert "run.completed" in client.post(f"/api/assistant/sessions/{sid}/messages",json=payload(attachment_ids=[image])).text
    assert "run.completed" in client.post(f"/api/assistant/sessions/{sid}/messages",json=payload()).text
    # Legacy contract protects an in-use image from draft deletion. Expiry must
    # still revoke every derived answer, including a v1 follow-up.
    assert client.delete(f"/api/assistant/attachments/{image}").status_code == 409
    from app.models.assistant import AssistantAttachment
    with dbm.SessionLocal() as db:
        db.get(AssistantAttachment,image).expires_at=1;db.commit()
    assert all(m["unavailable"] for m in client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"])


def test_search_then_synthesis_keeps_both_citation_namespaces_and_count():
    from app.services.assistant.evidence import RunContent
    c=RunContent("mixed","on")
    c.begin("search-0","search","search")
    c.web("search-0",[dict(index=2,title="website",url="https://example.test/doc")])
    c.append("text","public [ref_2]","search-0")
    c.account("search-0",search_count=1)
    context=c.citation_context("synthesis-0")
    assert context[0]["citation_ref"] == "1"
    c.begin("synthesis-0","synthesize","synthesis")
    c.append("text","derived [ref_1]","synthesis-0")
    c.account("synthesis-0",search_count=0)
    c.terminal("completed")
    assert c.evidence["search"]["search_count"] == 1
    assert len(c.evidence["citations"]) == 2
    assert all(b["resolution"]=="resolved" for b in c.evidence["citations"])


def test_readonly_business_adapter_real_scope_and_fixture_math(env, monkeypatch):
    from test_work_center_api import actor
    from app.services.assistant import business
    from app.models.auth import AuthRegistrationRequest
    from app.models.injection_scheduling import Demand
    from app.services.work_center import service as work
    from app.services.injection_scheduling import queries
    from app.schemas.injection_scheduling import Query
    from app.services.assistant.errors import AssistantError
    client, dbm, _, _ = env
    user=actor('alice',permissions=('system:user_manage',))
    with dbm.SessionLocal() as db:
        db.add(AuthRegistrationRequest(id="a-request",user_id="alice",username="applicant",factory_id="huakang-a",department="engineering",submitted_at="2026-01-01 00:00:00"))
        # These fixture rows are calculations, never real business records.
        case=fixture("business-contracts")["cases"][1]
        for row in case["seed_rows"]:
            db.add(Demand(mold_code="synthetic",**{k:v for k,v in row.items() if k != "forecast_unknown"}))
        db.commit()
        native=work.snapshot(db,user,factory_scope="huakang-a")
        native_injection=queries.summary(db,Query(factory_id="huaxing"))
    result, source, actions=business.query(user,"get_my_work",{"factory_id":"huakang-a"},"r")
    _, later, _=business.query(user,"get_my_work",{"factory_id":"huakang-a","q":"not-matching"},"r")
    assert source["source_id"] != later["source_id"] and not later["resources"]
    assert result["authorized_summary"]["values"] == native["summary"]
    assert result["filtered_total"] == native["query"]["filtered_total"] == 1
    assert actions[-1]["query"]["entry"] == native["items"][0]["id"]
    selected, _, _ = business.query(user,"get_my_work",{"factory_id":"huakang-a","resource_id":native["items"][0]["id"]},"r")
    assert selected["items"][0]["id"] == native["items"][0]["id"]
    with pytest.raises(AssistantError):
        business.query(user,"get_my_work",{"factory_id":"huaxing","resource_id":native["items"][0]["id"]},"r")
    with dbm.SessionLocal() as db:
        assert not business.visible(db,actor('alice'),source)
    user=actor('alice',factory="huaxing",department="production",permissions=("injection_scheduling:read",))
    result, _, _=business.query(user,"get_injection_overview",{"factory_id":"huaxing"},"r")
    assert result["reference_summary"]["values"] == native_injection
    summary=result["summary"]
    assert summary["wait_material_count"]==2 and summary["held_count"]==4
    assert summary["remaining_material_kg"]==19 and summary["warehouse_shortage_kg"] is None
    assert summary["remaining_material_unknown_count"]==1 and summary["forecast_unknown_count"]==2
    with pytest.raises(Exception): business.query(user,"get_injection_overview",{"factory_id":"huakang-c"},"r")
    with pytest.raises(Exception): business.query(actor('alice'),"get_injection_overview",{"factory_id":"huaxing"},"r")


def test_v2_downgrade_refuses_private_rows(env):
    client, dbm, _, _=env
    migrate(dbm)
    sid=session(client)
    client.patch(f"/api/assistant/sessions/{sid}/favorite",json={"favorite":True})
    spec=importlib.util.spec_from_file_location("v2_migration",Path(__file__).parents[1]/"alembic/versions/20261012_0158_assistant_v2_materials.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with dbm.engine.begin() as conn:
        with Operations.context(MigrationContext.configure(conn)):
            with pytest.raises(RuntimeError,match="private data"): module.downgrade()
        assert conn.exec_driver_sql("SELECT count(*) FROM nexus_assistant_favorites").scalar()==1


def test_revocation_between_history_read_and_provider_cannot_drop_dependencies(env):
    client, dbm, calls, monkeypatch=env
    migrate(dbm)
    from app.services.assistant import runtime, files
    sid=session(client)
    ident=client.post(f"/api/assistant/sessions/{sid}/files",files={"file":("private.txt",b'concurrent-private-material')}).json()["id"]
    assert ready(client,ident)["parse_status"]=="ready"
    assert "run.completed" in client.post(f"/api/assistant/sessions/{sid}/messages",json=payload(protocol_version=2,document_ids=[ident])).text
    original=runtime.history
    def revoke_after_read(user,*args,**kwargs):
        result=original(user,*args,**kwargs)
        files.remove(user,ident)
        return result
    monkeypatch.setattr(runtime,"history",revoke_after_read)
    response=client.post(f"/api/assistant/sessions/{sid}/messages",json=payload())
    assert "run.interrupted" in response.text and "context_changed" in response.text
    assert len(calls)==1, "revoked history must never be sent in a second upstream call"
    assert client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]["unavailable"]


def test_printer_adapter_uses_readonly_freshness_and_factory_policy(env, monkeypatch):
    from datetime import datetime, timezone, timedelta
    from test_work_center_api import actor
    from app.models.three_d_printing import ThreeDPrintingPrinter
    from app.services import three_d_printing as printers
    from app.services.assistant import business
    _, dbm, _, _=env
    user=actor('alice',department='production',permissions=('three_d_printing:read',))
    stamp=lambda t:t.strftime('%Y-%m-%d %H:%M:%S')
    now=datetime.now(timezone.utc)
    with dbm.SessionLocal() as db:
        for i,age in [(1,0),(2,120)]:
            db.add(ThreeDPrintingPrinter(id=f'qa-{i}',factory_id='huakang-a',machine_no=90+i,name=f'Synthetic {i}',state='RUNNING',connected=True,last_seen_at=stamp(now-timedelta(seconds=age)),created_at=stamp(now),updated_at=stamp(now)))
        db.commit()
        expected=[printers.printer_out(db.get(ThreeDPrintingPrinter,f'qa-{i}')) for i in [1,2]]
    def forbidden(*a,**k): raise AssertionError('read-only tool cannot create settings or call dashboard')
    monkeypatch.setattr(printers,'ensure_settings',forbidden)
    result, source, _=business.query(user,'get_printer_status',{'factory_id':'huakang-a'},'r')
    assert [(p['id'],p['status_stale']) for p in result['items'] if p['id'].startswith('qa-')]==[(p['id'],p['status_stale']) for p in expected]
    assert 'physical_state' in source['unknown_fields']
    with pytest.raises(Exception): business.query(user,'get_printer_status',{'factory_id':'huaxing'},'r')


def test_text_pdf_real_parser_page_locations_and_explicit_resource_limits(env, monkeypatch):
    from io import BytesIO
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
    from app.services.assistant import files
    from app.services.assistant.errors import AssistantError
    writer=PdfWriter()
    for text in ['First synthetic page', 'Second synthetic page']:
        page=writer.add_blank_page(width=300,height=300)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(f'BT /F1 12 Tf 30 200 Td ({text}) Tj ET'.encode())
        page[NameObject('/Contents')]=writer._add_object(stream)
    data=BytesIO();writer.write(data)
    segments=files.extract(data.getvalue(),'.pdf')
    assert [s['locator']['page'] for s in segments]==[1,2]
    assert 'Second synthetic page' in segments[1]['text']
    monkeypatch.setattr(files.settings,'assistant_max_document_pages',1)
    with pytest.raises(AssistantError) as exc: files.extract(data.getvalue(),'.pdf')
    assert exc.value.detail['code']=='file_page_limit'
    monkeypatch.setattr(files.settings,'assistant_max_document_pages',100)
    monkeypatch.setattr(files.settings,'assistant_max_document_characters',5)
    with pytest.raises(AssistantError) as exc: files.extract(data.getvalue(),'.pdf')
    assert exc.value.detail['code']=='file_text_limit'
    monkeypatch.setattr(files.settings,'assistant_max_document_characters',200000)
    writer=PdfWriter();writer.add_blank_page(width=300,height=300)
    blank=BytesIO();writer.write(blank)
    with pytest.raises(AssistantError) as exc: files.extract(blank.getvalue(),'.pdf')
    assert exc.value.detail['code']=='pdf_ocr_required'
    writer.encrypt('synthetic-password');encrypted=BytesIO();writer.write(encrypted)
    with pytest.raises(AssistantError) as exc: files.extract(encrypted.getvalue(),'.pdf')
    assert exc.value.detail['code']=='pdf_encrypted'


@pytest.mark.parametrize('reader_name',['sessions','messages','snapshot'])
def test_read_visibility_validation_does_not_hold_writer_lock(env, monkeypatch, reader_name):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from test_work_center_api import actor
    from app.services.assistant import service
    client, _, _, _=env
    sid=session(client)
    assert 'run.completed' in client.post(f'/api/assistant/sessions/{sid}/messages',json=payload()).text
    rid=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['run_id']
    checking,release=Event(),Event()
    original=service.message_out
    def slow_authorization(*args,**kwargs):
        checking.set()
        assert release.wait(5)
        return original(*args,**kwargs)
    monkeypatch.setattr(service,'message_out',slow_authorization)
    user=actor('alice')
    args=() if reader_name=='sessions' else (sid,) if reader_name=='messages' else (rid,)
    with ThreadPoolExecutor(max_workers=2) as pool:
        reader=pool.submit(getattr(service,reader_name),user,*args)
        try:
            assert checking.wait(3)
            writer=pool.submit(service.create,user,uuid4().hex)
            assert writer.result(timeout=1)['id'], 'slow read must not block admission/cancel writes'
        finally:
            release.set()
            reader.result(timeout=5)


@pytest.mark.parametrize('name,factory,permission',[
    ('get_injection_overview','huaxing','injection_scheduling:read'),
    ('get_printer_status','huakang-a','three_d_printing:read'),
])
def test_revoked_business_artifact_save_cannot_nest_audit_writes(env, monkeypatch, name, factory, permission):
    from test_work_center_api import actor
    from app.services.assistant import business
    from app.models.assistant import AssistantMessage
    from app.services import auth, business_authz
    from app.services.assistant.evidence import RunContent
    client, dbm, _, _=env
    migrate(dbm)
    sid=session(client)
    assert 'run.completed' in client.post(f'/api/assistant/sessions/{sid}/messages',json=payload()).text
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    _,source,_=business.query(actor('alice',factory=factory,department='production',permissions=(permission,)),name,{'factory_id':factory},answer['run_id'])
    content=RunContent(answer['run_id'],'off');content.append('text','private business answer','chat-0');content.add_source(source);content.terminal('completed')
    with dbm.SessionLocal() as db:
        db.get(AssistantMessage,answer['id']).content_parts=content.snapshot();db.commit()
    def forbidden(*a,**k): raise AssertionError('visibility must not commit audit writes inside assistant transaction')
    monkeypatch.setattr(auth,'add_auth_audit',forbidden)
    monkeypatch.setattr(business_authz,'add_auth_audit',forbidden)
    result=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=answer['run_id'],title='revoked',kind='research',content='private business answer'))
    assert result.status_code==410,result.text
    assert client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]['unavailable']
