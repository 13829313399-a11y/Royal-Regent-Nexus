import asyncio
from contextlib import asynccontextmanager
import json
from threading import RLock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import httpx
import pytest
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect

from test_online_documents import api, BASE, SCOPE, new, open_editor, put_grants
from app.api import online_document_connections as gateway
from app.models.auth import AuthSession
from app.models.online_documents import OnlineDocument as Document


def scope(who):
    return {'type': 'http', 'method': 'GET', 'path': '/office/doc/key/c', 'query_string': b'',
            'headers': [(b'cookie', f'rr_session={who}'.encode()), (b'host', b'testserver')], 'scheme': 'http', 'server': ('testserver', 80)}


def setup(api):
    client, engine, users, current, monkey = api
    monkey.setattr(gateway, 'SessionLocal', lambda: Session(engine))
    doc = new(client)
    put_grants(client, f'{BASE}/{doc}/grants{SCOPE}', json={'grants': [{'user_id': 'editor', 'access': 'edit'}, {'user_id': 'viewer', 'access': 'view'}]})
    owner = open_editor(client, doc)
    current['user'] = 'editor'; client.cookies.set('rr_session', 'editor')
    editor = open_editor(client, doc)
    current['user'] = 'viewer'; client.cookies.set('rr_session', 'viewer')
    viewer = open_editor(client, doc)
    current['user'] = 'owner'; client.cookies.set('rr_session', 'owner')
    return doc, owner, editor, viewer


def auth_frame(config):
    packet = {'type': 'auth', 'docid': config['document']['key'], 'user': config['editorConfig']['user'], 'jwtOpen': config['token']}
    return '40' + json.dumps({'token': config['token'], 'data': packet})


def test_cookie_policy_rejects_revoked_cached_edit_and_view_keys(api):
    client, engine, users, current, monkey = api
    doc, owner, editor, viewer = setup(api)
    for who, config in [('owner', owner), ('editor', editor), ('viewer', viewer)]:
        assert gateway.connection_policy(scope(who), config['document']['key'])[0] == who + '_1'
    with Session(engine) as db:
        record = db.get(Document, doc)
        record.grants = [g for g in record.grants if g['user_id'] not in {'editor', 'viewer'}]; db.commit()
    for who, config in [('editor', editor), ('viewer', viewer)]:
        with pytest.raises(HTTPException): gateway.connection_policy(scope(who), config['document']['key'])
    assert gateway.connection_policy(scope('owner'), owner['document']['key']) == ('owner_1', True)
    with Session(engine) as db:
        db.get(AuthSession, 'owner').status = 'revoked'; db.commit()
    with pytest.raises(HTTPException): gateway.connection_policy(scope('owner'), owner['document']['key'])


def test_token_identity_key_and_all_reauthentication_are_bound(api):
    doc, owner, editor, viewer = setup(api)
    key = owner['document']['key']
    assert gateway.inspect_frame(auth_frame(editor), key, 'editor_1', True, False)
    with pytest.raises(HTTPException): gateway.inspect_frame(auth_frame(owner), key, 'editor_1', True, False)
    with pytest.raises(HTTPException): gateway.inspect_frame(auth_frame(editor), 'different-key', 'editor_1', True, False)
    with pytest.raises(HTTPException): gateway.inspect_frame(auth_frame(editor), key, 'editor_1', False, False)
    packet = {'type': 'auth', 'docid': key, 'user': {'id': 'owner_1'}, 'jwtOpen': owner['token']}
    with pytest.raises(HTTPException): gateway.inspect_frame('42' + json.dumps(['message', packet]), key, 'editor_1', True, True)
    with pytest.raises(HTTPException): gateway.inspect_frame('451-' + json.dumps(['message', {**packet, 'unused': {'_placeholder': True, 'num': 0}}]), key, 'editor_1', True, True)
    with pytest.raises(HTTPException): gateway.inspect_frame('451-' + json.dumps(['message', {'_placeholder': True, 'num': 0}]), key, 'editor_1', True, True)
    assert gateway.inspect_frame('451-' + json.dumps(['message', {'type': 'saveChanges', 'changes': {'_placeholder': True, 'num': 0}}]), key, 'editor_1', True, True)
    with pytest.raises(HTTPException): gateway.inspect_frame(b'binary', key, 'editor_1', True, False)
    assert gateway.inspect_frame(b'x' * 1_572_864, key, 'editor_1', True, True)
    assert gateway.FRAME_LIMIT >= 1_572_864


def test_only_target_websocket_closes_and_other_connection_keeps_frames(api):
    client, engine, users, current, monkey = api
    doc, owner, editor, viewer = setup(api)
    original_policy, original_inspect = gateway.connection_policy, gateway.inspect_frame
    policy_lock = RLock()  # The shared test fixture uses one in-memory SQLite connection.
    failures = []
    def checked_policy(*args):
        try:
            with policy_lock: return original_policy(*args)
        except HTTPException as error:
            failures.append(('policy', [v.decode() for k, v in args[0]['headers'] if k == b'cookie'], args[2:] if len(args) > 2 else [], str(error.detail))); raise
    def checked_frame(*args):
        try: return original_inspect(*args)
        except HTTPException as error:
            failures.append(('frame', str(error.detail))); raise
    monkey.setattr(gateway, 'connection_policy', checked_policy)
    monkey.setattr(gateway, 'inspect_frame', checked_frame)
    streams = []
    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue(); self.queue.put_nowait('0{}'); self.sent = []
        def __aiter__(self): return self
        async def __anext__(self): return await self.queue.get()
        async def send(self, value): self.sent.append(value)
    @asynccontextmanager
    async def connect(*args, **kwargs):
        assert not any(k.lower() in {'cookie', 'authorization'} for k in kwargs['additional_headers'])
        assert kwargs['max_size'] == gateway.FRAME_LIMIT
        stream = Upstream(); streams.append(stream); yield stream
    monkey.setattr(gateway, 'connect', connect)
    app = FastAPI(); app.include_router(gateway.router)
    url = f'/office/doc/{owner["document"]["key"]}/c/?EIO=4&transport=websocket'
    with TestClient(app) as proxy:
        with proxy.websocket_connect(url, headers={'cookie': 'rr_session=owner'}) as keep:
            assert keep.receive_text() == '0{}'; keep.send_text(auth_frame(owner))
            with proxy.websocket_connect(url, headers={'cookie': 'rr_session=editor'}) as target:
                assert target.receive_text() == '0{}'; target.send_text(auth_frame(editor))
                with policy_lock, Session(engine) as db:
                    record = db.get(Document, doc); record.grants = [g for g in record.grants if g['user_id'] != 'editor']; db.commit()
                target.send_text('3')
                with pytest.raises(WebSocketDisconnect): target.receive_text()
                keep.send_bytes(b'x' * 1_572_864)
                proxy.portal.call(streams[0].queue.put, '2')
                try: assert keep.receive_text() == '2'
                except WebSocketDisconnect: pytest.fail(str(failures))
            # Reusing the original valid JWT cannot pass the new cookie/ACL check.
            with pytest.raises(WebSocketDisconnect):
                with proxy.websocket_connect(url, headers={'cookie': 'rr_session=editor'}): pass


def test_http_exports_and_cache_recheck_current_access_and_strip_cookie(api):
    client, engine, users, current, monkey = api
    doc, owner, editor, viewer = setup(api)
    calls = []
    def upstream(request):
        calls.append(request)
        assert 'cookie' not in request.headers and 'authorization' not in request.headers
        return httpx.Response(200, stream=httpx.ByteStream(b'document-bytes'), headers={'content-type': 'application/octet-stream'})
    original = httpx.AsyncClient
    monkey.setattr(gateway.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(upstream), **kw))
    app = FastAPI(); app.include_router(gateway.router)
    key = editor['document']['key']
    with TestClient(app) as proxy:
        proxy.cookies.set('rr_session', 'editor')
        assert proxy.get(f'/office/cache/files/{key}_changes/output.xlsx').content == b'document-bytes'
        assert proxy.post(f'/office/downloadas/{key}', json={'token': owner['token']}).status_code == 403
        assert proxy.post(f'/office/downloadas/{key}', params={'cmd': json.dumps({'id': 'another-key', 'tokenSession': editor['token']})}).status_code == 403
        assert proxy.post(f'/office/downloadas/{key}', params={'cmd': json.dumps({'id': key, 'tokenSession': owner['token']})}).status_code == 403
        assert proxy.get(f'/office/downloadfile/{key}', params={'id': key, 'tokenSession': owner['token']}).status_code == 403
        assert proxy.post(f'/office/downloadfile/{key}', content=json.dumps({'id': 'another-key', 'tokenSession': editor['token']}), headers={'content-type': 'application/octet-stream'}).status_code == 403
        assert proxy.get(f'/office/downloadfile/{key}', params=[('cmd', '{}'), ('cmd', '{}')]).status_code == 400
        assert proxy.post(f'/office/savefile/{key}', params={'cmd': json.dumps({'id': key, 'tokenSession': editor['token']})}, content=b'bytes').status_code == 200
        with Session(engine) as db:
            record = db.get(Document, doc); record.grants = [g for g in record.grants if g['user_id'] != 'editor']; db.commit()
        for path in (f'cache/files/{key}/output.xlsx', f'downloadas/{key}', f'printfile/{key}/print.pdf'):
            assert proxy.get('/office/' + path).status_code in {403, 404}
        proxy.cookies.set('rr_session', 'viewer')
        assert proxy.get(f'/office/cache/files/{viewer["document"]["key"]}/output.xlsx').status_code == 200
        assert proxy.get(f'/office/doc/{key}/c/?EIO=4&transport=polling').status_code == 403
    assert len(calls) == 3


@pytest.mark.parametrize('path', ['doc/key/c/extra', 'doc/key/../c', '10.0.0/doc/key/c/extra'])
def test_noncanonical_connection_paths_cannot_reach_upstream(api, path):
    app = FastAPI(); app.include_router(gateway.router)
    with TestClient(app) as proxy:
        with pytest.raises(WebSocketDisconnect):
            with proxy.websocket_connect('/office/' + path + '?EIO=4&transport=websocket'): pass
