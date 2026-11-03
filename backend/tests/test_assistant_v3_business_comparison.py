"""Actual authorized native results remain comparable when old prose is omitted."""
from copy import deepcopy
import json
import pytest
from sqlalchemy import select
from test_assistant_api import env,session,payload
from test_assistant_v2 import migrate
from test_assistant_v3_orders import setup


def result():
    return dict(contract_version=3,tool_name='list_customer_orders',tool_version='orders-v3.1',run_id='old',source_refs=['native'],
        as_of='2026-10-26T19:09:38+08:00',scope=dict(factory_ids=['huakang-a'],module_id='customer-orders',filters={'view':'all'},resource_refs=['order:A1'],coverage='selected_resources',label='华康A / 选中订单'),
        metrics=dict(remaining_quantity=dict(value='120.500000000000000001',unit='原订单数量单位',currency=None,status='known',definition_id='quantity'),
            unknown=dict(value=None,unit='kg',currency=None,status='unknown',definition_id='unknown')),
        definitions={'quantity':'同范围数量，不换算。','unknown':'未读取库存。'},rows=[{'private_extra':'DO-NOT-RETAIN-ROW'}])


def test_explicit_previous_query_comparisons_only():
    from app.services.assistant.business_comparison import requested
    for text in ['和上次查询比有什么变化？','比上回少了多少？','与先前查询比较','What changed compared with the previous query?','Compare with last time']:
        assert requested(text)
    for text in ['刷新订单','比较今年和去年','上次怎么打开页面','查一下库存']:
        assert not requested(text)


def test_projection_keeps_exact_values_unknowns_and_separate_clocks_without_rows_or_mutation():
    from app.services.assistant.business_comparison import build
    old=result();new=deepcopy(old);new.update(run_id='new',as_of='2026-10-26T19:10:23+08:00')
    source=dict(source_id='owned-wrapper',kind='business')
    original=deepcopy(old)
    basis=build(new,dict(result=old,sources=[source]))
    assert basis['status']=='comparable'
    assert basis['previous_metrics']['remaining_quantity']['value']=='120.500000000000000001'
    assert basis['previous_metrics']['unknown']['value'] is None
    assert basis['previous_as_of']!=basis['current_as_of'] and old==original
    assert basis['previous_source_ids']==['owned-wrapper']
    assert 'DO-NOT-RETAIN-ROW' not in json.dumps(basis)


@pytest.mark.parametrize('field,value',[('factory_ids',['huakang-b']),('filters',{'view':'shipped'}),('resource_refs',['order:A2']),('coverage','authorized_scope')])
def test_different_denominators_never_supply_old_values_for_arithmetic(field,value):
    from app.services.assistant.business_comparison import build
    old=result();new=deepcopy(old);new['scope'][field]=value
    basis=build(new,dict(result=old,sources=[]))
    assert basis['status']=='scope_changed' and 'previous_metrics' not in basis


@pytest.mark.parametrize('dimension,value',[('unit','箱'),('currency','USD'),('definition_id','other')])
def test_unit_currency_or_definition_changes_exclude_that_metric(dimension,value):
    from app.services.assistant.business_comparison import build
    old=result();new=deepcopy(old);new['metrics']['remaining_quantity'][dimension]=value
    basis=build(new,dict(result=old,sources=[]))
    assert 'remaining_quantity' not in basis.get('previous_metrics',{})
    assert 'unknown' in basis['previous_metrics']


def test_ancestor_sources_or_ineligible_sources_cannot_become_native_baselines():
    from app.services.assistant.business_comparison import capture
    old=result()
    source=dict(kind='business',source_id='wrapped',run_id='current',tool_name=old['tool_name'],origin=dict(run_id='old',source_id='native'))
    assert capture(old,[source])
    for changed in [{**source,'citation_eligible':False},{**source,'origin':dict(run_id='ancestor',source_id='native')},{**source,'tool_name':'get_my_work'}]:
        assert capture(old,[changed]) is None


def request_for(ident,text):
    value=payload(protocol_version=2,intent='my_work',web_search='off',thinking='auto',
        page_context=dict(module_id='customer-orders',route_name='customer-order-center',factory_id='huakang-a'),
        context_selection=dict(selection_id='synthetic-compare',resources=[dict(module_id='customer-orders',resource_type='order',resource_id=ident)],filters={}))
    value['text']=text
    return value


@pytest.mark.parametrize('scope_change',[False,True])
def test_real_runtime_pins_only_native_basis_when_full_prior_turn_is_dropped(env,scope_change):
    from app.services.assistant import runtime,business_comparison
    from app.models.assistant import AssistantMessage
    from app.models.customer_order_ledger import OrderLedgerLine
    client,dbm,calls,patch,user=setup(env);migrate(dbm)
    patch.setattr(runtime,'authenticate',lambda request:user)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request_for('SYN-O-A001','查询选中订单'))
    assert 'event: run.completed' in response.text,response.text
    with dbm.SessionLocal() as db:
        original=db.scalar(select(AssistantMessage).where(AssistantMessage.session_id==sid,AssistantMessage.role=='assistant'))
        original_id,original_parts=original.id,deepcopy(original.content_parts)
        row=db.get(OrderLedgerLine,'SYN-O-A001');row.shipped_quantity+=50;row.revision+=1;db.commit()
    real_fit=runtime.fit_context
    def force_drop(packing,supplements,content,window):
        if len(packing['groups'])>1:
            marker='合成的长历史解释'
            packing['groups'][0][1].append(dict(role='assistant',content=marker*(window['character_budget']//len(marker)+1)))
        return real_fit(packing,supplements,content,window)
    patch.setattr(runtime,'fit_context',force_drop)
    ident='SYN-O-A002' if scope_change else 'SYN-O-A001'
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request_for(ident,'和上次查询比有什么变化？'))
    assert 'event: run.completed' in response.text,response.text
    encoded=next(m['content'][len(business_comparison.INSTRUCTION):] for m in calls[-1]['messages'] if m['role']=='system' and isinstance(m['content'],str) and m['content'].startswith(business_comparison.INSTRUCTION))
    basis=json.loads(encoded)
    assert basis['status']==('scope_changed' if scope_change else 'comparable')
    if scope_change: assert 'previous_metrics' not in basis
    else: assert basis['previous_metrics']['remaining_quantity']['value']=='400'
    with dbm.SessionLocal() as db:
        assert db.get(AssistantMessage,original_id).content_parts==original_parts
    messages=client.get(f'/api/assistant/sessions/{sid}/messages').json()['items']
    current=next(m for m in reversed(messages) if m['role']=='assistant')
    evidence=next(p for p in current['content_parts'] if p['type']=='evidence')
    assert all(any(s['source_id']==source and s.get('origin',{}).get('run_id')==basis['previous_run_id'] for s in evidence['sources']) for source in basis['previous_source_ids'])
    assert not any('合成的长历史解释' in str(m['content']) for m in calls[-1]['messages'])


def test_deleted_prior_resource_never_enters_comparison_projection(env):
    from app.services.assistant import runtime,business_comparison
    from app.models.customer_order_ledger import OrderLedgerLine
    client,dbm,calls,patch,user=setup(env);migrate(dbm)
    patch.setattr(runtime,'authenticate',lambda request:user)
    sid=session(client)
    # An earlier still-visible success must not replace the latest deleted one.
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request_for('SYN-O-A002','查询选中订单'))
    assert 'event: run.completed' in response.text
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request_for('SYN-O-A001','查询选中订单'))
    assert 'event: run.completed' in response.text
    with dbm.SessionLocal() as db:db.delete(db.get(OrderLedgerLine,'SYN-O-A001'));db.commit()
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=request_for('SYN-O-A002','和上次查询比有什么变化？'))
    assert 'event: run.completed' in response.text,response.text
    encoded=next(m['content'][len(business_comparison.INSTRUCTION):] for m in calls[-1]['messages'] if m['role']=='system' and isinstance(m['content'],str) and m['content'].startswith(business_comparison.INSTRUCTION))
    basis=json.loads(encoded)
    assert basis['status']=='unavailable' and 'previous_metrics' not in basis
    assert 'SYN-O-A001' not in encoded
