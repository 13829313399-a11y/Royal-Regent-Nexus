import asyncio
import importlib
import time
from starlette.requests import Request
from test_assistant_api import env, session, payload, viewer_for


def test_server_rechecks_revocation_and_closes_upstream(env):
    client, dbm, _, monkeypatch = env
    svc=importlib.import_module('app.services.assistant.service')
    runtime=importlib.import_module('app.services.assistant.runtime')
    provider=importlib.import_module('app.services.assistant.provider')
    schema=importlib.import_module('app.schemas.assistant')
    auth=importlib.import_module('app.models.auth')
    user=viewer_for(dbm); sid=session(client); data=schema.SendMessage(**payload())
    admitted=svc.admit(user,sid,data); admitted['session_id']=sid
    request=Request({'type':'http','method':'POST','path':'/api/assistant/sessions/test/messages','headers':[(b'cookie',b'rr_session=alice')]})
    closed=[]
    async def waiting(*args):
        try:
            yield {'kind':'delta','channel':'answer','text':'partial-before-revocation'}
            with dbm.SessionLocal() as db:
                db.get(auth.AuthSession,'alice').status='revoked';db.commit()
            await asyncio.sleep(30)
        finally:
            closed.append(time.monotonic())
    monkeypatch.setattr(provider,'stream',waiting)
    # Production default is <=10s; accelerate only the next check for this test.
    assert runtime.check_delay(user)<=10
    monkeypatch.setattr(runtime,'check_delay',lambda _: .1)
    async def collect(): return [item async for item in runtime.events(request,user,data,admitted)]
    started=time.monotonic(); frames=asyncio.run(collect())
    assert closed and closed[0]-started<3
    assert any('run.interrupted' in f for f in frames)
    snapshot=svc.snapshot(user,rid=admitted['run_id'])
    assert snapshot['state']=='interrupted'
    assert snapshot['items'][-1]['content_parts'][0]['text']=='partial-before-revocation'


def test_disconnect_and_disabled_close_upstream_and_release_slot(env):
    client,dbm,_,monkeypatch=env
    svc=importlib.import_module('app.services.assistant.service')
    runtime=importlib.import_module('app.services.assistant.runtime')
    provider=importlib.import_module('app.services.assistant.provider')
    schema=importlib.import_module('app.schemas.assistant')
    settings=importlib.import_module('app.core.config').settings
    user=viewer_for(dbm);sid=session(client);data=schema.SendMessage(**payload())
    request=Request({'type':'http','method':'POST','path':'/api/assistant/sessions/test/messages','headers':[(b'cookie',b'rr_session=alice')]})
    closed=[]
    async def waiting(*args):
        try:
            yield {'kind':'delta','channel':'answer','text':'kept'}
            await asyncio.sleep(30)
        finally: closed.append(True)
    monkeypatch.setattr(provider,'stream',waiting)
    for disabled in [False,True]:
        admitted=svc.admit(user,sid,data.model_copy(update={'client_request_id':str(disabled)+'-request'}));admitted['session_id']=sid
        async def consume():
            stream=runtime.events(request,user,data,admitted)
            async for frame in stream:
                if 'response.delta' in frame:
                    if disabled: settings.assistant_enabled=False
                    else: await stream.aclose();break
        asyncio.run(consume())
        settings.assistant_enabled=True
        assert svc.snapshot(user,rid=admitted['run_id'])['state']=='interrupted'
    assert len(closed)==2


def test_failed_lease_renewal_closes_the_upstream(env):
    client,dbm,_,monkeypatch=env
    svc=importlib.import_module('app.services.assistant.service')
    runtime=importlib.import_module('app.services.assistant.runtime')
    provider=importlib.import_module('app.services.assistant.provider')
    schema=importlib.import_module('app.schemas.assistant')
    from app.services.assistant.errors import AssistantError
    user=viewer_for(dbm);sid=session(client);data=schema.SendMessage(**payload())
    admitted=svc.admit(user,sid,data);admitted['session_id']=sid
    request=Request({'type':'http','method':'POST','path':'/api/assistant/sessions/test/messages','headers':[(b'cookie',b'rr_session=alice')]})
    real_control=svc.control;count=0;closed=[]
    def lost(*args,**kwargs):
        nonlocal count
        count+=1
        if count>1:raise AssistantError('lease_lost','synthetic lease loss',409)
        return real_control(*args,**kwargs)
    async def waiting(*args):
        try:
            yield {'kind':'delta','channel':'answer','text':'partial'}
            await asyncio.sleep(30)
        finally:closed.append(True)
    monkeypatch.setattr(provider,'stream',waiting);monkeypatch.setattr(svc,'control',lost)
    async def collect():return [frame async for frame in runtime.events(request,user,data,admitted)]
    start=time.monotonic();frames=asyncio.run(collect())
    assert closed and time.monotonic()-start<4 and any('run.interrupted' in f for f in frames)
    monkeypatch.setattr(svc,'control',real_control)
    model=importlib.import_module('app.models.assistant')
    with svc.transaction() as db:db.get(model.AssistantRun,admitted['run_id']).lease_expires_at=time.time()-1
    assert svc.snapshot(user,rid=admitted['run_id'])['state']=='interrupted'
