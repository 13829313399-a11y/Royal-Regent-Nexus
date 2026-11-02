"""Do not confuse help coverage with authorized business reading."""
from dataclasses import replace
import pytest
from test_assistant_api import env, session, payload


def test_only_bound_connectors_are_callable_and_planned_states_are_honest():
    from app.services.assistant import registry, business
    assert len(registry.coverage()) == 8
    assert {c.tool_name for c in registry.CALLABLE} == business.NAMES
    assert all(c["coverage_state"] != "connected" for c in registry.coverage())
    assert all(not c["tools"] and c["reason"] for c in registry.coverage() if c["coverage_state"] == "planned")
    with pytest.raises(ValueError, match="incomplete bindings"):
        registry.validate([replace(registry.CONNECTORS[0], authorize_symbol=None)])
    with pytest.raises(ValueError, match="duplicate"):
        registry.validate([registry.CONNECTORS[0], registry.CONNECTORS[0]])


@pytest.mark.parametrize("module", ["unregistered"])
def test_missing_module_does_not_fall_back_to_personal_work(module):
    from app.services.assistant import registry
    from app.services.assistant.errors import AssistantError
    with pytest.raises(AssistantError) as failure:
        registry.resolve(module)
    assert failure.value.detail["code"] == "module_not_connected"
    assert registry.resolve("portal") == "get_my_work"


def test_record_type_is_bound_to_module():
    from app.services.assistant import registry
    from app.services.assistant.errors import AssistantError
    assert registry.resolve("injection-scheduling", "demand") == "get_injection_overview"
    assert registry.resolve('carton-procurement', 'order') == 'get_carton_overview'
    assert registry.resolve('carton-procurement', 'inventory') == 'get_carton_overview'
    assert registry.resolve('internal-quote', 'quote') == 'get_internal_quote_overview'
    assert registry.resolve('uv-operations', 'task') == 'get_uv_operations_snapshot'
    assert registry.resolve('spray-production', 'demand') == 'get_spray_operations_snapshot'
    assert registry.resolve('spray-production', 'task') == 'get_spray_operations_snapshot'
    with pytest.raises(AssistantError):
        registry.resolve("injection-scheduling", "printer")


def test_unbound_spray_page_stops_before_business_or_model(env):
    from app.services.assistant import business
    client, _, calls, patch = env
    def forbidden(*args, **kwargs):
        pytest.fail("unbound native scope must not query business data")
    patch.setattr(business, "query", forbidden)
    sid = session(client)
    request = payload(protocol_version=2, intent="my_work", web_search="off",
        page_context=dict(module_id="spray-production", route_name="spray-overview", factory_id="huakang-a"))
    response = client.post(f"/api/assistant/sessions/{sid}/messages", json=request)
    assert "event: run.failed" in response.text and "context_unavailable" in response.text, response.text
    assert not calls
    answer = client.get(f"/api/assistant/sessions/{sid}/messages").json()["items"][-1]
    evidence = next(p for p in answer["content_parts"] if p["type"] == "evidence")
    assert not any(s["kind"] == "business" for s in evidence["sources"])


def test_supplier_cannot_reach_any_internal_connector_via_registered_selection_or_batch(env,tmp_path):
    from app.services import auth
    from app.services.assistant import business,registry,runtime,help_registry
    from app.services.assistant.errors import AssistantError
    from test_work_center_api import actor
    client,dbm,calls,patch=env
    supplier=actor('alice',factory='huakang-a',department='pmc-warehouse',permissions=('carton_supplier:read',))
    assert help_registry.supplier_only(supplier)
    assert all(article.audience in ('all','supplier') for article in help_registry.visible(supplier))
    resources=[('injection-scheduling','demand'),('internal-quote','quote')]
    assert business.permitted_tools(supplier,'huakang-a')==[]
    with dbm.SessionLocal() as db:
        for name in business.NAMES:
            with pytest.raises(AssistantError) as failure:business.authorize(db,supplier,name,'huakang-a')
            assert failure.value.status_code==403
        for module,kind in resources:
            name=registry.resolve(module,kind)
            with pytest.raises(AssistantError) as failure:business.query(supplier,name,dict(factory_id='huakang-a',resource_id='PRIVATE-INTERNAL-RECORD'),'supplier-denial')
            assert failure.value.status_code==403
    client.app.dependency_overrides[auth.get_current_user]=lambda:supplier
    patch.setattr(runtime,'authenticate',lambda request:supplier)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,web_search='off',
        context_selection=dict(selection_id='supplier-internal-combination',filters=dict(factory_id='huakang-a'),resources=[
            dict(module_id=module,resource_type=kind,resource_id='PRIVATE-INTERNAL-RECORD') for module,kind in resources])))
    assert 'business_queries_unavailable' in response.text and not calls
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    failures=[p['result'] for p in answer['content_parts'] if p['type']=='business_failure']
    assert len(failures)==len(resources)
    assert all(f['status']=='forbidden' and not f['source_refs'] and not f['rows'] and not f['allowed_actions'] for f in failures)
    assert 'PRIVATE-INTERNAL-RECORD' not in str(answer)
    evidence=next(p for p in answer['content_parts'] if p['type']=='evidence')
    assert not evidence['sources']
    from test_assistant_api import verified_profile
    verified_profile(tmp_path)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(protocol_version=2,web_search='off'))
    assert 'event: run.completed' in response.text and len(calls)==1
    names={tool['function']['name'] for tool in calls[0]['tools']}
    assert names and not names.intersection(business.NAMES)
