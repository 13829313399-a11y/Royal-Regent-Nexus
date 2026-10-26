"""Quote connector against real native calculations and isolated SQL/HTTP data."""
import base64
from datetime import datetime, timedelta
from decimal import Decimal as D
import json
import re

import pytest
from sqlalchemy import select
from test_assistant_api import env, session, payload
from test_internal_quote_queries import setup, capture, no_writes, F, STAMP
from test_work_center_api import actor


def query(user, **args):
    from app.services.assistant.quotes import query as read
    return read(user, {'factory_id': F, **args}, 'synthetic-quote-run')


def fill(dbm, user, ident, *, material='8.5', labor='260'):
    """Save synthetic inputs through the native calculator, without mocking results."""
    from app.models.internal_quote import InternalQuote, InternalQuoteSection
    from app.services import internal_quote as native
    with dbm.SessionLocal() as db:
        quote = db.get(InternalQuote, ident)
        quote.product_name = '同一合成产品'
        quote.qty = 100
        quote.formula_version = native.FORMULA_VERSION
        quote.target_customer_price = 'SECRET_TARGET_PRICE'
        quote.remark = 'SECRET_REMARK'
        quote.business_owner_name = 'SECRET_OWNER'
        inputs = {
            'engineering': {'materials': [{'item': 'SECRET_MATERIAL', 'category': 'hardware', 'quantity': '2', 'unit_price_rmb': material}], 'molds': []},
            'assembly': {'labor_base_hkd': labor, 'groups': [{'name': '合成装配', 'category': 'assembly', 'processes': [
                {'name': '组装', 'persons': '2', 'teams': '1', 'production_qty': '1000'}]}]},
            'sales': {'freight_calc': {'enabled': False}, 'shipping': {'markup_x': '1.25', 'misc_ratio': '0.03'}},
        }
        for code, payload in inputs.items():
            section = db.get(InternalQuoteSection, f'{ident}-{code}')
            section.payload_json = native.canonical_json(payload)
            section.filled_at = STAMP
            section.status = 'draft'
            section.revision += 1
            db.flush()
            calculation = native._calculate_and_apply(db, quote, section, user)
            assert calculation['status'] == 'valid', (code, calculation['warnings'])
            db.flush()
        db.commit()


def test_native_logical_documents_filters_pagination_and_bounded_projection(env):
    client, dbm, calls, user = setup(env)
    statements, stop = capture(dbm)
    try:
        for filters in ({}, {'customer': '客户一'}, {'keyword': '第二产品'}, {'keyword': '版本独有关键词'}, {'status': 'archived'}):
            result, source, actions = query(user, limit=10, **filters)
            response = client.get('/api/internal-quotes', params=dict(factory_id=F, page=1, page_size=10, **filters))
            assert response.status_code == 200, response.text
            native = response.json()
            assert result['total_count'] == result['metrics']['document_count']['value'] == native['total']
            assert [r['id'] for r in result['rows']] == [r['id'] for r in native['items']]
            assert len(source['resources']) == native['total']
            assert [a['params']['quoteId'] for a in actions] == [r['id'] for r in result['rows']]
            assert all(a['query'] == {'factory': F} and a['route_name'] == 'internal-quote-collaboration' for a in actions)
            assert len(result['allowed_actions']) == len(result['rows'])
            assert all(r['financial'] is None for r in result['rows'])
            assert all(set(r['readiness']) == {'ready_sections', 'required_sections', 'state'} for r in result['rows'])
            assert result['as_of'].endswith('+08:00')
            if not filters:
                assert result['truncated'] and result['returned_count'] == 10 and result['total_count'] == 12
                second, _, _ = query(user, limit=10, cursor=result['next_cursor'])
                assert second['returned_count'] == 2 and second['next_cursor'] is None
                assert second['metrics'] == result['metrics']
                assert len({r['id'] for r in result['rows'] + second['rows']}) == 12
            if filters.get('status'): assert result['status'] == 'empty'
    finally: stop()
    no_writes(statements)
    assert not calls


def test_financial_permission_scope_and_argument_failures_never_read_sensitive_summary(env):
    from app.services.assistant import quotes
    from app.services.assistant.errors import AssistantError
    _, dbm, calls, _ = setup(env)
    user = actor('quote-reader', factory=F, department='sales-business', permissions=('internal_quote:read',))
    def prohibited(*args, **kwargs): pytest.fail('Operational reader reached financial service')
    env[3].setattr(quotes.reader, 'summary', prohibited)
    env[3].setattr(quotes.reader, 'comparison', prohibited)
    statements, stop = capture(dbm)
    try:
        result, source, _ = query(user, resource_id='Q0')
        assert result['rows'][0]['financial']['state'] == 'forbidden'
        assert result['rows'][0]['financial']['quote_hkd'] is None and not source['financial_access']
        for args, status in [({'view': 'compare', 'resource_id': 'ALT', 'base_resource_id': 'Q0'}, 403),
                ({'factory_id': 'huakang-b'}, 403), ({'factory_id': 'all'}, 422),
                ({'resource_id': 'FOREIGN'}, 404), ({'resource_id': 'missing'}, 404),
                ({'resource_id': ' Q0'}, 422), ({'resource_id': 'Q0', 'keyword': 'x'}, 422),
                ({'view': 'compare', 'resource_id': 'Q0'}, 422), ({'base_resource_id': 'Q0'}, 422),
                ({'view': 'compare', 'resource_id': 'Q0', 'base_resource_id': 'Q0'}, 422),
                ({'limit': True}, 422), ({'limit': 51}, 422), ({'unknown': 'x'}, 422)]:
            with pytest.raises(AssistantError) as error: query(user, **args)
            assert error.value.status_code == status, (args, error.value.detail)
    finally: stop()
    no_writes(statements)
    assert not calls


def test_incomplete_and_missing_reference_amounts_are_unknown_without_lazy_writes(env):
    client, dbm, calls, user = setup(env)
    statements, stop = capture(dbm)
    try:
        incomplete, _, _ = query(user, resource_id='Q0')
        missing, _, _ = query(user, resource_id='Q1')
        native = client.get('/api/internal-quotes/Q0/summary').json()
    finally: stop()
    no_writes(statements)
    money = incomplete['rows'][0]['financial']
    assert not native['pricing_complete'] and native['authoritative_factory_quote_hkd'] is None
    assert money['state'] == 'incomplete' and money['quote_hkd'] is None
    assert money['base_cost_hkd'] is None and all(r['hkd'] is None for r in money['section_amounts'])
    assert missing['rows'][0]['financial']['state'] == 'reference_unavailable'
    assert not calls


def test_complete_prices_costs_tax_and_comparison_match_native_http_without_private_fields(env):
    client, dbm, calls, user = setup(env)
    fill(dbm, user, 'Q0')
    fill(dbm, user, 'ALT', material='10.2')
    statements, stop = capture(dbm)
    try:
        result, _, _ = query(user, view='compare', resource_id='ALT', base_resource_id='Q0')
        summaries = [client.get(f'/api/internal-quotes/{ident}/summary').json() for ident in ('Q0', 'ALT')]
        native_compare = client.get('/api/internal-quotes/ALT/compare/Q0').json()
    finally: stop()
    no_writes(statements)
    for row, native in zip(result['rows'], summaries):
        financial = row['financial']
        assert native['pricing_complete'] and financial['complete']
        assert financial['state'] == 'draft_calculated' and row['workflow'] == 'direct_output'
        assert financial['quote_hkd'] == native['authoritative_factory_quote_hkd']
        assert financial['base_cost_hkd'] == native['factory_price_hkd']
        assert financial['pricing_mode'] == 'standard' and financial['currency'] == 'HKD'
        t3 = {r['key']: r['value'] for r in native['rr2_cost_summary']['t3']}
        assert financial['profit_hkd'] == t3['profit'] and financial['cost_hkd'] == t3['total_cost']
        assert financial['tax_deduction_hkd'] == native['rr2_cost_summary']['totals']['total_deduction_hkd']
        assert financial['invoice_tax'] is financial['invoice_net'] is financial['invoice_gross'] is None
        assert '未明确件/套' in financial['unit']
    compare = result['rows'][-1]['comparison']
    assert compare['comparable'], compare['reasons']
    assert compare['base_cost_delta_hkd'] == native_compare['total_delta_hkd']
    assert D(compare['quote_delta_hkd']) == D(summaries[1]['authoritative_factory_quote_hkd']) - D(summaries[0]['authoritative_factory_quote_hkd'])
    encoded = json.dumps(result, ensure_ascii=False)
    assert 'SECRET_' not in encoded and 'payload_changes' not in encoded and 'line_breakdown' not in encoded
    assert not calls


def test_stale_formula_reference_or_pending_calculation_does_not_expose_partial_zero(env):
    from app.models.internal_quote import InternalQuoteSection
    _, dbm, _, user = setup(env)
    fill(dbm, user, 'Q0')
    for key, value in [('calculation_formula_version', 'old'), ('calculation_reference_snapshot_id', 'old'),
                       ('dependency_status', 'stale'), ('calculation_status', 'pending')]:
        with dbm.SessionLocal() as db:
            section = db.get(InternalQuoteSection, 'Q0-engineering')
            previous = getattr(section, key)
            setattr(section, key, value)
            db.commit()
        result, _, _ = query(user, resource_id='Q0')
        money = result['rows'][0]['financial']
        assert money['state'] == 'incomplete' and money['quote_hkd'] is money['base_cost_hkd'] is None
        assert all(r['hkd'] is None for r in money['section_amounts'])
        with dbm.SessionLocal() as db:
            setattr(db.get(InternalQuoteSection, 'Q0-engineering'), key, previous)
            db.commit()


def test_incompatible_versions_preserve_facts_but_decline_arithmetic_and_unrelated_versions(env):
    from app.models.internal_quote import InternalQuote, InternalQuoteReferenceSet
    from app.services.assistant.errors import AssistantError
    _, dbm, _, user = setup(env)
    fill(dbm, user, 'Q0')
    fill(dbm, user, 'ALT', material='10.2')
    for field, value in [('qty', 101), ('product_name', '另一产品'), ('formula_version', 'old')]:
        with dbm.SessionLocal() as db:
            row = db.get(InternalQuote, 'ALT'); previous = getattr(row, field); setattr(row, field, value); db.commit()
        result, _, _ = query(user, view='compare', resource_id='ALT', base_resource_id='Q0')
        comparison = result['rows'][-1]['comparison']
        assert not comparison['comparable'] and comparison['reasons']
        assert comparison['quote_delta_hkd'] is comparison['base_cost_delta_hkd'] is None
        with dbm.SessionLocal() as db:
            setattr(db.get(InternalQuote, 'ALT'), field, previous); db.commit()
    with dbm.SessionLocal() as db:
        ref = db.get(InternalQuoteReferenceSet, db.get(InternalQuote, 'ALT').reference_snapshot_id)
        snapshot = json.loads(ref.snapshot_json); snapshot['fx']['hkd_usd'] = '8.123'
        ref.snapshot_json = json.dumps(snapshot); db.commit()
    result, _, _ = query(user, view='compare', resource_id='ALT', base_resource_id='Q0')
    assert not result['rows'][-1]['comparison']['comparable']
    assert '冻结汇率不同或缺失' in result['rows'][-1]['comparison']['reasons']
    with pytest.raises(AssistantError) as unrelated: query(user, view='compare', resource_id='Q1', base_resource_id='Q0')
    assert unrelated.value.status_code == 400


def test_issued_frozen_summary_survives_current_formula_change_without_using_live_section_amounts(env):
    from app.models.internal_quote import InternalQuote, InternalQuoteSection
    from app.services import internal_quote as native
    client, dbm, _, user = setup(env)
    fill(dbm, user, 'Q0')
    before = client.get('/api/internal-quotes/Q0/summary').json()
    with dbm.SessionLocal() as db:
        quote = db.get(InternalQuote, 'Q0')
        costs = native._cost_context(db, quote)
        quote.final_submission_manifest_json = native.canonical_json({'cost_context': {k:str(v) for k,v in costs.items()}, 'rr2_cost_summary': before['rr2_cost_summary']})
        quote.final_release_status = 'issued'; quote.status = 'exported'
        quote.formula_version = 'historic-formula'
        for section in db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == 'Q0')):
            section.calculation_status = 'stale'; section.calculation_json = '{}'
        db.commit()
    statements, stop = capture(dbm)
    try:
        result, _, _ = query(user, resource_id='Q0')
        summary = client.get('/api/internal-quotes/Q0/summary').json()
    finally: stop()
    no_writes(statements)
    financial = result['rows'][0]['financial']
    assert financial['state'] == 'issued_snapshot' and financial['frozen']
    assert financial['quote_hkd'] == summary['authoritative_factory_quote_hkd'] == before['authoritative_factory_quote_hkd']
    assert financial['base_cost_hkd'] == before['factory_price_hkd']
    assert all(r['hkd'] is None for r in financial['section_amounts'])
    assert result['rows'][0]['readiness']['state'] == 'issued'


def test_cursor_changes_off_page_filters_actor_ttl_and_source_visibility_fail_closed(env):
    from app.models.internal_quote import InternalQuote
    from app.services.assistant import quotes
    from app.services.assistant.errors import AssistantError
    _, dbm, _, user = setup(env)
    result, source, _ = query(user, limit=1)
    changed_user = actor('quote-reader', factory=F, department='sales-business', permissions=('internal_quote:read',))
    with dbm.SessionLocal() as db:
        assert quotes.visible(db, user, source)
        assert not quotes.visible(db, changed_user, source)
    for args in ({'customer': '客户一'}, {'cursor': 'not-a-cursor'}, {'cursor': base64.urlsafe_b64encode(b'[]').decode()}):
        with pytest.raises(AssistantError) as invalid:
            query(user, **({'limit': 1, 'cursor': result['next_cursor']} | args))
        assert invalid.value.detail['code'] == 'cursor_invalid'
    with pytest.raises(AssistantError): query(changed_user, limit=1, cursor=result['next_cursor'])
    original_clock = quotes.business_now
    env[3].setattr(quotes, 'business_now', lambda: datetime.fromisoformat(result['as_of']) + timedelta(seconds=301))
    with pytest.raises(AssistantError): query(user, limit=1, cursor=result['next_cursor'])
    env[3].setattr(quotes, 'business_now', original_clock)
    # An off-page contributing record participates in both snapshot and history checks.
    ident = next(r['resource_id'] for r in source['resources'] if r['resource_id'] != result['rows'][0]['id'])
    with dbm.SessionLocal() as db:
        db.get(InternalQuote, ident).product_name = '变更的原产品'; db.commit()
    with pytest.raises(AssistantError): query(user, limit=1, cursor=result['next_cursor'])
    with dbm.SessionLocal() as db:
        db.delete(db.get(InternalQuote, ident)); db.commit()
        assert not quotes.visible(db, user, source)


def test_calculated_zero_is_known_but_missing_issued_manifest_is_not_reconstructed(env):
    from app.models.internal_quote import InternalQuote
    from app.services.assistant import quotes
    client, dbm, _, user = setup(env)
    fill(dbm, user, 'Q0', material='0', labor='0')
    result, source, _ = query(user, resource_id='Q0')
    native = client.get('/api/internal-quotes/Q0/summary').json()
    money = result['rows'][0]['financial']
    assert native['pricing_complete'] and money['complete']
    assert D(native['authoritative_factory_quote_hkd']) == D(money['quote_hkd']) == 0
    assert source['financial_access']
    with dbm.SessionLocal() as db:
        quote = db.get(InternalQuote, 'Q0')
        quote.final_release_status = 'issued'; quote.final_submission_manifest_json = '{}'
        db.commit()
    def prohibited(*args, **kwargs): pytest.fail('Missing immutable output must not be reconstructed')
    env[3].setattr(quotes.reader, 'summary', prohibited)
    statements, stop = capture(dbm)
    try: result, _, _ = query(user, resource_id='Q0')
    finally: stop()
    no_writes(statements)
    assert result['rows'][0]['financial']['state'] == 'issued_snapshot_unavailable'
    assert result['rows'][0]['financial']['quote_hkd'] is None


def test_bounded_text_and_financial_history_authority(env):
    from app.models.internal_quote import InternalQuote
    from app.services.assistant import quotes
    _, dbm, _, user = setup(env)
    with dbm.SessionLocal() as db:
        db.get(InternalQuote, 'Q0').product_name = '长' * 1000
        db.commit()
    result, source, _ = query(user, resource_id='Q0')
    row = result['rows'][0]
    assert row['product_name'] == '长' * 300 and 'product_name' in row['truncated_fields']
    assert any(u['field'] == 'rows' for u in result['unknown_fields'])
    reader = actor('quote-reader', factory=F, department='sales-business', permissions=('internal_quote:read',))
    with dbm.SessionLocal() as db:
        assert quotes.visible(db, user, source)
        # Even a re-signed snapshot cannot turn historical finance into read-only access.
        source['authorization_fingerprint'] = quotes.fingerprint(db, reader)
        assert not quotes.visible(db, reader, source)
        source['authorization_fingerprint'] = quotes.fingerprint(db, user)
        source['resources'][0]['resource_type'] = 'unrecognized'
        assert not quotes.visible(db, user, source)


def runtime_setup(env):
    from test_assistant_v2 import migrate
    from app.models.auth import AuthUser
    from app.services.assistant import runtime
    client, dbm, calls, user = setup(env)
    with dbm.SessionLocal() as db:
        db.add(AuthUser(id=user.id, username='synthetic-quote-reader', display_name='合成报价读取',
            password_salt='unused', password_hash='unused', status='active'))
        db.commit()
    migrate(dbm)
    env[3].setattr(runtime, 'authenticate', lambda request: user)
    return client, dbm, calls, user


def test_runtime_filters_and_compare_persist_snapshot_citations_and_authorized_source_actions(env):
    from app.services.assistant import runtime
    client, dbm, calls, user = runtime_setup(env)
    fill(dbm, user, 'Q0'); fill(dbm, user, 'ALT', material='10.2')
    sid = session(client)
    page = dict(module_id='internal-quote', route_name='internal-quote-desk-home', factory_id=F)
    selection = dict(selection_id='quote-filter', resources=[], filters=dict(factory_id=F, keyword='第二产品'))
    request = payload(protocol_version=2, intent='my_work', web_search='off', page_context=page, context_selection=selection)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=request)
    assert 'event: run.completed' in response.text, response.text[-2500:]
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    result = next(p['result'] for p in answer['content_parts'] if p['type']=='business_snapshot')
    assert result['scope']['filters']['keyword']=='第二产品' and result['total_count']==1
    assert result['rows'][0]['id']=='Q0' and result['rows'][0]['financial'] is None
    compare = dict(selection_id='quote-compare', resources=[dict(module_id='internal-quote', resource_type='quote', resource_id=i) for i in ('Q0','ALT')],
        filters=dict(factory_id=F, view='compare', base_resource_id='FOREIGN'))
    request = payload(protocol_version=2, intent='my_work', web_search='off', page_context=page, context_selection=compare)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=request)
    assert 'event: run.completed' in response.text, response.text[-2500:]
    answer = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    snapshots = [p['result'] for p in answer['content_parts'] if p['type']=='business_snapshot']
    assert len(snapshots)==1 and snapshots[0]['tool_call_id']=='prequery-0'
    assert [r['id'] for r in snapshots[0]['rows']]==['Q0','ALT']
    assert snapshots[0]['rows'][-1]['comparison']['comparable']
    actions = next(p['items'] for p in answer['content_parts'] if p['type']=='actions')
    native_actions = [(index, action) for index, action in enumerate(actions) if action['type']=='open_record']
    assert len(native_actions)==2
    for (index, action), ident in zip(native_actions, ('Q0','ALT')):
        response = client.post('/api/assistant/actions/resolve',json=dict(run_id=answer['run_id'],index=index))
        assert response.status_code==200,response.text
        assert response.json()==action
        assert response.json()['params']=={'quoteId':ident} and response.json()['query']=={'factory':F}
    assert len(calls)==2
    sent = json.dumps(calls, ensure_ascii=False)
    assert 'SECRET_' not in sent
    def assert_public_metadata(value):
        if isinstance(value, dict):
            assert not {'financial_access', 'authorization_fingerprint'}.intersection(value)
            for item in value.values(): assert_public_metadata(item)
        elif isinstance(value, list):
            for item in value: assert_public_metadata(item)
        elif isinstance(value, str):
            # Definition IDs describe the boundary; internal source keys must not be sent.
            assert not re.search(r'"(?:financial_access|authorization_fingerprint)"\s*:', value)
    assert_public_metadata(calls)
    history, _ = runtime.history(user,sid,'future-run',[])
    assert any(m['role']=='system' and '历史业务快照' in m['content'] for m in history)
    assert client.get(f"/api/assistant/runs/{answer['run_id']}/export").status_code==200


def test_financial_history_export_artifacts_and_tampered_actions_fail_closed(env):
    from copy import deepcopy
    from app.models.assistant import AssistantMessage
    from app.models.internal_quote import InternalQuote
    from app.services import auth
    from app.services.assistant import runtime
    client,dbm,_,user=runtime_setup(env)
    fill(dbm,user,'Q0')
    sid=session(client)
    body=payload(protocol_version=2,web_search='off',page_context=dict(module_id='internal-quote',route_name='internal-quote-collaboration',factory_id=F),
        context_selection=dict(selection_id='selected-quote',resources=[dict(module_id='internal-quote',resource_type='quote',resource_id='Q0')],filters=dict(factory_id=F)))
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=body)
    assert 'event: run.completed' in response.text,response.text[-2000:]
    answer=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    actions=next(p['items'] for p in answer['content_parts'] if p['type']=='actions')
    action_index=next(i for i,a in enumerate(actions) if a['type']=='open_record')
    rid=answer['run_id']; action_request=dict(run_id=rid,index=action_index)
    artifact=client.post(f'/api/assistant/sessions/{sid}/artifacts',json=dict(source_run_id=rid,title='报价证据',kind='markdown',content='合成报价记录'))
    assert artifact.status_code==200,artifact.text
    artifact_id=artifact.json()['id']
    original=deepcopy(answer['content_parts'])
    for patch,expected in [(dict(params={'quoteId':'Q0','extra':'x'}),422),
        (dict(params={'quoteId':'FOREIGN'},resource=dict(module_id='internal-quote',resource_type='quote',resource_id='FOREIGN')),410)]:
        with dbm.SessionLocal() as db:
            message=db.get(AssistantMessage,answer['id']); parts=deepcopy(original)
            next(p['items'] for p in parts if p['type']=='actions')[action_index].update(patch)
            message.content_parts=parts;db.commit()
        assert client.post('/api/assistant/actions/resolve',json=action_request).status_code==expected
    with dbm.SessionLocal() as db: db.get(AssistantMessage,answer['id']).content_parts=original;db.commit()
    reader=actor(user.id,factory=F,department='sales-business',permissions=('internal_quote:read',))
    client.app.dependency_overrides[auth.get_current_user]=lambda:reader
    env[3].setattr(runtime,'authenticate',lambda request:reader)
    hidden=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    assert hidden['unavailable'] and 'Q0' not in json.dumps(hidden['content_parts'])
    assert client.get(f'/api/assistant/runs/{rid}/export').status_code==410
    assert client.get(f'/api/assistant/artifacts/{artifact_id}/export').status_code==410
    assert client.post('/api/assistant/actions/resolve',json=action_request).status_code==410
    client.app.dependency_overrides[auth.get_current_user]=lambda:user
    env[3].setattr(runtime,'authenticate',lambda request:user)
    with dbm.SessionLocal() as db: db.get(InternalQuote,'Q0').factory_id='huakang-b';db.commit()
    assert client.post('/api/assistant/actions/resolve',json=action_request).status_code==410


def test_quote_scope_failure_and_invalid_compare_stop_before_provider(env):
    client,_,calls,_=runtime_setup(env)
    sid=session(client)
    for filters in (dict(factory_id=F,scope_error='读取尚未完成'),dict(factory_id=F,view='compare')):
        body=payload(protocol_version=2,intent='my_work',web_search='off',page_context=dict(module_id='internal-quote',route_name='internal-quote-desk-home',factory_id=F),
            context_selection=dict(selection_id='invalid-quote-context',resources=[],filters=filters))
        response=client.post(f'/api/assistant/sessions/{sid}/messages',json=body)
        assert 'event: run.failed' in response.text and 'context_unavailable' in response.text,response.text[-2000:]
    assert not calls
