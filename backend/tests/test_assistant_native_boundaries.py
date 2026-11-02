"""Remaining P3 contracts through native authentication on disposable data."""
from datetime import date
from decimal import Decimal
from uuid import uuid4
import json
import logging

import httpx
import pytest
from sqlalchemy import select,func
from test_assistant_api import env,session,payload,verified_profile


@pytest.fixture
def native_boundary(env,tmp_path):
    from app.core.config import settings
    from app.models.auth import AuthRole,AuthRolePermission,AuthUserRole,AuthPermission,EmployeeProfile
    from app.models.customer_order_ledger import OrderLedgerLine
    from app.services import customer_order_queries
    from app.services.assistant import orders
    client,dbm,calls,patch=env
    patch.setattr(settings,'authz_mode','enforce')
    patch.setattr(settings,'assistant_daily_token_budget',None)
    patch.setattr(settings,'assistant_max_tool_rounds',0)
    patch.setattr(customer_order_queries,'shanghai_today',lambda:date(2026,10,23))
    patch.setattr(orders,'now_iso',lambda:'2026-10-23T01:00:00+00:00')
    verified_profile(tmp_path)
    def deny_network(*args,**kwargs):raise AssertionError('No external network in native-boundary tests')
    async def deny_async_network(*args,**kwargs):deny_network()
    patch.setattr(httpx.HTTPTransport,'handle_request',deny_network)
    patch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',deny_async_network)
    with dbm.SessionLocal() as db:
        permission=db.scalar(select(AuthPermission).where(AuthPermission.code=='customer_order:read'))
        assert permission is not None
        db.add(AuthRole(id='closure-order',code='closure-order',name='订单阅读员'))
        db.flush()
        db.add(AuthRolePermission(id='closure-order-read',role_id='closure-order',permission_id=permission.id))
        db.add(AuthUserRole(id='closure-order-assignment',user_id='alice',role_id='closure-order',factory_id='huakang-a',department='sales-business'))
        db.add(EmployeeProfile(user_id='alice',primary_factory_id='huakang-a',primary_department='sales-business',position='订单阅读员',identity_mode='legacy'))
        rows=[('SYN-O-A001','huakang-a','FILTER-A',1000,600,'2026-10-24'),
              ('SYN-O-A002','huakang-a','FILTER-OTHER',800,800,'2026-10-22'),
              ('SYN-O-A003','huakang-a','FILTER-A',500,0,'2026-10-22'),
              ('SYN-O-B001','huakang-b','FILTER-A',9000,0,'2026-10-20')]
        for ident,factory,customer,quantity,shipped,due in rows:
            db.add(OrderLedgerLine(id=ident,factory_id=factory,customer_code=customer,
                customer_name='PRIVATE-B-TITLE-CANARY' if factory=='huakang-b' else '合成客户',
                identity_key=ident,reference_no=ident,product_no='SYN-PRODUCT',quantity=Decimal(quantity),
                shipped_quantity=Decimal(shipped),status='active',
                data={'requested_ship_date':due,'private_extension':'PRIVATE-EXTENSION-CANARY'},
                created_at='2026-10-20 00:00:00',updated_at='2026-10-20 00:00:00'))
        db.commit()
    # Neither the route dependency nor the streaming reauthentication is mocked.
    from app.services.assistant import runtime
    assert runtime.authenticate.__module__=='app.services.assistant.runtime'
    from app.services import auth
    assert auth.get_current_user not in client.app.dependency_overrides
    return env


def send_query(client,*,factory='huakang-a',filters=None,resources=None):
    sid=session(client)
    body=payload(protocol_version=2,intent='my_work',web_search='off',
        page_context=dict(module_id='customer-orders',route_name='customer-order-center',factory_id=factory),
        context_selection=dict(selection_id=uuid4().hex,filters={'factory_id':factory,**(filters or {})},resources=resources or []))
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=body)
    assert response.status_code==200,response.text
    messages=client.get(f'/api/assistant/sessions/{sid}/messages')
    assert messages.status_code==200,messages.text
    return response,messages.json()['items'][-1]


def result_of(message):
    return next(part['result'] for part in message['content_parts'] if part['type']=='business_snapshot')


def test_native_coverage_uses_registry_and_unavailable_uv_never_substitutes_my_work(native_boundary):
    from app.services.assistant import registry,business
    client,_,calls,patch=native_boundary
    response=client.get('/api/assistant/coverage',params={'factory_id':'huakang-a'})
    assert response.status_code==200 and response.headers['cache-control']=='private, no-store'
    rows={row['module_id']:row for row in response.json()['items']}
    assert rows['customer-orders']['state']=='business_read'
    assert any(row['state']=='guide_only' and row['verification']=='not_registered' for row in rows.values())
    for connector in registry.CONNECTORS:
        assert rows[connector.module_id]['verification']==connector.coverage_state
    assert {c.tool_name for c in registry.CALLABLE}=={t['function']['name'] for t in business.TOOLS}
    unavailable=client.get('/api/assistant/coverage',params={'factory_id':'huaxing','module_id':'not-registered'})
    other={row['module_id']:row for row in unavailable.json()['items']}
    assert other['uv-operations']['state']==other['not-registered']['state']=='not_connected'
    names=[];original=business.query
    def observed(user,name,*args,**kwargs):
        names.append(name)
        return original(user,name,*args,**kwargs)
    patch.setattr(business,'query',observed)
    sid=session(client)
    response=client.post(f'/api/assistant/sessions/{sid}/messages',json=payload(
        protocol_version=2,intent='my_work',web_search='off',
        page_context=dict(module_id='uv-operations',route_name='uv-planning',factory_id='huaxing'),
        context_selection=dict(selection_id=uuid4().hex,filters={'factory_id':'huaxing','view':'tasks'})))
    assert response.status_code==422 and response.json()['detail']['code']=='factory_unavailable'
    assert set(names)<={'get_uv_operations_snapshot'} and 'get_my_work' not in names
    assert not calls


def test_native_authorized_order_positive_precedes_cross_factory_and_id_denials_ordinary_chat_survives(native_boundary):
    client,_,calls,_=native_boundary
    native=client.get('/api/customer-order-ledger/lines',params={'factory_id':'huakang-a'})
    assert native.status_code==200 and native.json()['total']==3
    accepted,answer=send_query(client)
    assert 'event: run.completed' in accepted.text
    result=result_of(answer)
    assert result['total_count']==3 and result['metrics']['remaining_quantity']['value']=='900'
    assert len(calls)==1
    denied=client.get('/api/customer-order-ledger/lines',params={'factory_id':'huakang-b'})
    assert denied.status_code==403
    response,answer=send_query(client,factory='huakang-b')
    assert 'event: run.interrupted' in response.text and 'business_forbidden' in response.text
    assert len(calls)==1
    for data in (denied.text,response.text,json.dumps(answer)):
        assert not any(x in data for x in ('PRIVATE-B-TITLE-CANARY','SYN-O-B001','9000','PRIVATE-EXTENSION-CANARY'))
    wrong_id=client.get('/api/customer-order-ledger/lines/SYN-O-B001',params={'factory_id':'huakang-a'})
    unknown=client.get('/api/customer-order-ledger/lines/not-known',params={'factory_id':'huakang-a'})
    assert wrong_id.status_code==unknown.status_code==404 and wrong_id.json()==unknown.json()
    sid=session(client)
    ordinary=client.post(f'/api/assistant/sessions/{sid}/messages',json={**payload(protocol_version=2,web_search='off'),'text':'解释闭包'})
    assert 'event: run.completed' in ordinary.text and len(calls)==2
    assert 'PRIVATE-B-TITLE-CANARY' not in json.dumps(calls)


@pytest.mark.parametrize('field',['actor','user_id','factory_id','authorization_fingerprint'])
def test_native_position_name_and_forged_body_cannot_grant_authority_and_trace_is_redacted(native_boundary,caplog,field):
    from app.models.auth import EmployeeProfile,AuthRole,AuthUser
    from app.services.auth import build_auth_context
    from app.models.assistant import AssistantRun
    client,dbm,calls,_=native_boundary
    with dbm.SessionLocal() as db:
        db.get(EmployeeProfile,'alice').position='管理员'
        db.get(AuthRole,'closure-order').name='超级管理员'
        db.commit()
    me=client.get('/api/auth/me')
    assert me.status_code==200 and me.json()['id']=='alice' and me.json()['profile']['position']=='管理员'
    with dbm.SessionLocal() as db:
        native_context=build_auth_context(db,db.get(AuthUser,'alice'))
        assert native_context.role_codes==('closure-order',)
    assert 'system:access_manage' not in me.json()['permissions']
    assert client.get('/api/customer-order-ledger/lines',params={'factory_id':'huakang-a'}).status_code==200
    assert client.get('/api/customer-order-ledger/lines',params={'factory_id':'huakang-b'}).status_code==403
    sid=session(client)
    with dbm.SessionLocal() as db:before=db.scalar(select(func.count()).select_from(AssistantRun))
    trace='native-'+uuid4().hex
    secret='FORGED-PRIVATE-INPUT-NOT-TO-LOG'
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    forged=client.post(f'/api/assistant/sessions/{sid}/messages',json={**payload(),field:secret},headers={'X-Request-ID':trace})
    assert forged.status_code==422 and forged.json()['detail']['code']=='invalid_request'
    assert forged.headers['x-request-id']==forged.json()['detail']['request_id']==trace
    with dbm.SessionLocal() as db:assert db.scalar(select(func.count()).select_from(AssistantRun))==before
    records=[r.getMessage() for r in caplog.records if r.name=='uvicorn.error' and trace in r.getMessage()]
    assert len(records)==1 and 'status=422' in records[0] and 'path=/api/assistant/sessions/{sid}/messages' in records[0]
    assert all(x not in forged.text+records[0] for x in (secret,'rr_session','PRIVATE-B-TITLE-CANARY','PRIVATE-EXTENSION-CANARY'))
    assert not calls


def test_native_filtered_second_page_detail_saved_action_and_revocation_keep_scope(native_boundary):
    from app.models.auth import AuthRolePermission
    client,dbm,calls,_=native_boundary
    common={'factory_id':'huakang-a','customer_code':'FILTER-A','page_size':1}
    native1=client.get('/api/customer-order-ledger/lines',params={**common,'page':1}).json()
    native2=client.get('/api/customer-order-ledger/lines',params={**common,'page':2}).json()
    assert native1['total']==native2['total']==2
    first_response,first_message=send_query(client,filters={'customer_code':'FILTER-A','limit':1})
    first=result_of(first_message)
    assert 'event: run.completed' in first_response.text and first['truncated'] and first['next_cursor']
    second_response,second_message=send_query(client,filters={'customer_code':'FILTER-A','limit':1,'cursor':first['next_cursor']})
    second=result_of(second_message)
    assert 'event: run.completed' in second_response.text
    for item,native in ((first,native1),(second,native2)):
        assert item['total_count']==2 and item['returned_count']==1
        assert item['metrics']['remaining_quantity']['value']=='900'
        assert item['scope']['factory_ids']==['huakang-a'] and item['scope']['filters']['customer_code']=='FILTER-A'
        assert item['rows'][0]['id']==native['items'][0]['id']
        assert item['rows'][0]['customer_code']=='FILTER-A'
    assert second['next_cursor'] is None
    selected=second['rows'][0]['id']
    _,detail_message=send_query(client,resources=[dict(module_id='customer-orders',resource_type='order',resource_id=selected)])
    detail=result_of(detail_message)
    native_detail=client.get('/api/customer-order-ledger/lines/'+selected,params={'factory_id':'huakang-a'})
    assert native_detail.status_code==200 and detail['rows'][0]['remaining_quantity']==native_detail.json()['line']['remaining_quantity']
    actions=next(p['items'] for p in detail_message['content_parts'] if p['type']=='actions')
    index=next(i for i,a in enumerate(actions) if a.get('query',{}).get('order')==selected)
    body={'run_id':detail_message['run_id'],'index':index}
    resolved=client.post('/api/assistant/actions/resolve',json=body)
    assert resolved.status_code==200 and resolved.json()['route_name']=='customer-order-center'
    assert resolved.json()['query']=={'factory':'huakang-a','order':selected}
    with dbm.SessionLocal() as db:
        db.delete(db.get(AuthRolePermission,'closure-order-read'));db.commit()
    revoked=client.post('/api/assistant/actions/resolve',json=body)
    assert revoked.status_code in (403,410) and selected not in revoked.text
    assert client.post('/api/assistant/actions/resolve',json={**body,'index':100}).status_code in (403,404,410)
    assert len(calls)==3 and 'PRIVATE-B-TITLE-CANARY' not in json.dumps(calls)
