"""Real session permissions, one-use pairing, and existing inspection mutations."""
import base64
import importlib
import io
import json
import time
from urllib.parse import urlsplit

import pytest
from PIL import Image
from test_molding_sample_api import make_client, login_as
from test_qc_department_gateway import install_upstream


def pair(client):
    response=client.post('/api/qc-mobile/pairings',json={'factory':'huaxing'})
    assert response.status_code==200,response.text
    return response.json()['url'].split('#pair=')[1]


def test_mobile_scoped_lifecycle_and_real_save_photo_submit(monkeypatch,tmp_path):
    monkeypatch.setenv('QC_DOSSIER_EMERGENCY_DISABLED','true')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'companies'))
    monkeypatch.setenv('QC_MOBILE_PUBLIC_ORIGIN','http://testserver')
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    with make_client(monkeypatch) as client:
        install_upstream(monkeypatch)
        mobile=importlib.import_module('app.api.qc_mobile')
        service=importlib.import_module('app.services.qc_inspection_sheet')
        assert client.get('/api/qc-mobile/context').status_code==401
        assert client.post('/api/qc-mobile/pairings',json={'factory':'huaxing'}).status_code==401
        login_as(client,'qc_inspector')
        assert client.post('/api/qc-mobile/pairings',json={'factory':'huakang-a'}).status_code==403
        assert client.post('/api/qc-mobile/pairings',json={'factory':'huaxing'},headers={'Origin':'http://evil.example'}).status_code==403
        old=pair(client);ticket=pair(client)
        assert client.post('/api/qc-mobile/exchange',json={'ticket':old}).status_code==401
        assert client.post('/api/qc-mobile/exchange',json={'ticket':ticket}).status_code==200
        assert client.post('/api/qc-mobile/exchange',json={'ticket':ticket}).status_code==401
        context=client.get('/api/qc-mobile/context').json()
        assert context['factory']=='huaxing'
        assert client.post('/api/qc-mobile/sheet/review/confirm',json={}).status_code==404
        assert client.post('/api/qc-mobile/sheet/entries/a/delete',json={}).status_code==404
        source={'id':'a','customer':'客户甲','poNo':'0001','productNo':'001','dateFrom':'2026-11-17','sourceStatus':'active'}
        tasks=[{'id':'task-a','sourceId':'a','source':source,'batch':'首验','execution':{},'attachments':[]}]
        row=service.sync('huaxing',service.candidates('huaxing',[],tasks,[source]))['items'][0]
        endpoint='/api/qc-mobile/sheet/entries/'+row['id']
        saved=client.post(endpoint+'/save',json={'revision':row['revision'],'result':'FAIL','remark':'备注','inspectionProblem':'压痕','improvement':'可选措施'})
        assert saved.status_code==200,saved.text
        row=saved.json();assert row['improvement']=='可选措施'
        named=client.post(endpoint+'/save',json={'revision':row['revision'],'result':'FAIL','remark':'备注','inspectionExecution':{'inspector':'手填验货员'}})
        assert named.status_code==200,named.text
        row=named.json();assert row['inspectionExecution']['inspector']=='手填验货员'
        assert not row['inspectionExecution'].get('inspectorId')
        assert client.post(endpoint+'/save',json={'revision':0,'result':'PASS','remark':''}).status_code==409
        cleared=client.post(endpoint+'/save',json={'revision':row['revision'],'result':'PASS','remark':'','inspectionProblem':'','improvement':''})
        assert cleared.status_code==200;row=cleared.json();assert row['inspectionProblem']==row['remark']==row['improvement']==''
        png=io.BytesIO();Image.new('RGB',(40,40),'red').save(png,format='PNG')
        payload={'revision':row['revision'],'requestKey':'1234567890abcdef','name':'验货.png','content':base64.b64encode(png.getvalue()).decode()}
        uploaded=client.post(endpoint+'/photos',json=payload);assert uploaded.status_code==200,uploaded.text
        again=client.post(endpoint+'/photos',json=payload);assert again.status_code==200
        row=again.json();photo=row['uploadedPhotoId'];assert len(row['photos'])==1
        assert client.get(endpoint+'/photos/'+photo).status_code==200
        arrow={'type':'arrow','x1':.1,'y1':.2,'x2':.7,'y2':.8}
        annotation={'photoId':photo,'annotationVersion':0,'annotations':[arrow]}
        marked=client.post(endpoint+'/photo-annotations',json=annotation)
        assert marked.status_code==200,marked.text
        assert marked.json()['photo']['annotationVersion']==1
        assert client.get(endpoint).json()['photos'][0]['annotations']==[arrow]
        assert service.photo_info('huaxing',row['id'])['items'][0]['annotations']==[arrow]
        assert client.post(endpoint+'/photo-annotations',json={**annotation,'annotations':[]}).status_code==409
        assert client.post(endpoint+'/photo-annotations',json=annotation,headers={'Origin':'http://evil.example'}).status_code==403
        row=marked.json()['entry']
        removed=client.post(endpoint+'/remove-photo',json={'revision':row['revision'],'photoId':photo});assert removed.status_code==200
        row=removed.json();assert not row['photos']
        submitted=client.post(endpoint+'/submit',json={'revision':row['revision']});assert submitted.status_code==200,submitted.text
        assert submitted.json()['reviewState']=='pending'
        assert client.post(endpoint+'/photo-annotations',json={**annotation,'annotationVersion':1}).status_code==409
        assert client.post(endpoint+'/save',json={'revision':submitted.json()['revision'],'result':'PASS','remark':'late'}).status_code==409
        # Logout of the issuing desktop revokes the phone's authority too.
        client.post('/api/auth/logout')
        assert client.get('/api/qc-mobile/context').status_code==401


def test_expiry_and_public_assets(monkeypatch,tmp_path):
    monkeypatch.setenv('QC_DOSSIER_EMERGENCY_DISABLED','true')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'companies'))
    monkeypatch.setenv('QC_MOBILE_PUBLIC_ORIGIN','http://testserver')
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    with make_client(monkeypatch) as client:
        module=importlib.import_module('app.api.qc_mobile')
        assert client.get('/api/qc-mobile/app/').status_code==200
        assert client.get('/api/qc-mobile/ready').status_code==404
        assert client.get('/api/qc-mobile/app/remote.js').status_code==200
        assert client.get('/api/qc-mobile/app/qc-photo-shapes.js').status_code==200
        assert client.get('/api/qc-mobile/app/../../.isolation/main.sqlite3').status_code==404
        assert client.get('/api/qc-mobile/app/source-manifest.json').status_code==404
        login_as(client,'qc_inspector');ticket=pair(client)
        with module.store() as conn:conn.execute('UPDATE grants SET ticket_expires=0')
        assert client.post('/api/qc-mobile/exchange',json={'ticket':ticket}).status_code==401


def test_lan_listener_reuses_managed_private_gateway_without_starting_workers(monkeypatch,tmp_path):
    import asyncio
    from types import SimpleNamespace
    from pydantic import SecretStr
    module=importlib.import_module('app.qc_mobile_app')
    token='a'*64
    (tmp_path/'gateway-token').write_text(token)
    settings=SimpleNamespace(qc_department_data_dir=str(tmp_path/'companies'),qc_department_gateway_token=SecretStr(''))
    monkeypatch.setattr(module,'settings',settings)
    async def verify():
        async with module.lifespan(module.app):
            assert settings.qc_department_gateway_token.get_secret_value()==token
    asyncio.run(verify())
    from fastapi.testclient import TestClient
    with TestClient(module.app) as client:
        assert client.get('/api/qc-mobile/app/').status_code==200
        assert client.get('/api/qc-mobile/ready').json()=={'service':'qc-mobile','ready':True}
        assert client.get('/api/auth/me').status_code==404
        assert client.get('/api/qc-department/huaxing/api/health').status_code==404
        resolve_asset=module.mobile_asset_path
        monkeypatch.setattr(module,'mobile_asset_path',lambda name: tmp_path/'missing.js' if name=='app.js' else resolve_asset(name))
        assert client.get('/api/qc-mobile/ready').status_code==503


@pytest.mark.parametrize('state', ['old-address', 'no-listener', 'wrong-service', 'ready'])
def test_lan_pairing_checks_assigned_address_and_dedicated_service(monkeypatch, state):
    import asyncio
    import socket
    from types import SimpleNamespace
    from fastapi import HTTPException
    import httpx
    module=importlib.import_module('app.api.qc_mobile')
    requested=[]
    class Bound:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def bind(self,address):
            assert address==('192.168.5.13',0)
            if state=='old-address': raise OSError('address is not assigned')
    class Client:
        def __init__(self,**options):
            assert options=={'timeout':1.5,'trust_env':False,'follow_redirects':False}
        async def __aenter__(self): return self
        async def __aexit__(self, *_): pass
        async def get(self,url):
            requested.append(url)
            if state=='no-listener': raise httpx.ConnectError('connection refused')
            return httpx.Response(200,json=module.MOBILE_READY if state=='ready' else {'ready':True},
                                  request=httpx.Request('GET',url))
    monkeypatch.setattr(module,'socket',SimpleNamespace(AF_INET=socket.AF_INET,AF_INET6=socket.AF_INET6,socket=lambda _:Bound()))
    monkeypatch.setattr(module,'httpx',SimpleNamespace(AsyncClient=Client,HTTPError=httpx.HTTPError))
    origin=urlsplit('http://192.168.5.13:5298')
    if state=='ready':
        asyncio.run(module.check_lan_entry(origin,origin.port))
    else:
        with pytest.raises(HTTPException) as failure:
            asyncio.run(module.check_lan_entry(origin,origin.port))
        assert failure.value.status_code==503
        assert ('地址已不在' if state=='old-address' else '手机专用服务未就绪') in failure.value.detail
    assert requested==([] if state=='old-address' else ['http://192.168.5.13:5298/api/qc-mobile/ready'])


def test_pairing_does_not_issue_ticket_for_unavailable_lan_entry(monkeypatch,tmp_path):
    monkeypatch.setenv('QC_DOSSIER_EMERGENCY_DISABLED','true')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'companies'))
    monkeypatch.setenv('QC_MOBILE_PUBLIC_ORIGIN','http://127.0.0.1:5298')
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    with make_client(monkeypatch) as client:
        login_as(client,'qc_inspector')
        response=client.post('/api/qc-mobile/pairings',json={'factory':'huaxing'})
        assert response.status_code==503 and '本机地址' in response.json()['detail']
        assert not (tmp_path/'companies/_mobile/pairings.sqlite3').exists()


@pytest.mark.parametrize(('entry_host', 'app_env', 'mobile_tls'), [
    ('qc.company.example', 'production', False),
    ('1.1.1.1', 'production', False),
    ('1.1.1.1', 'development', True),
])
def test_production_mobile_behind_tls_proxy(monkeypatch, tmp_path, entry_host, app_env, mobile_tls):
    import httpx
    import test_molding_sample_api
    monkeypatch.setenv('QC_DOSSIER_EMERGENCY_DISABLED', 'true')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR', str(tmp_path/'companies'))
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path/'main')
    with make_client(monkeypatch) as client:
        mobile=importlib.import_module('app.api.qc_mobile')
        origin=f'https://{entry_host}'
        # Model TLS termination upstream: the application's connection is HTTP
        # but the browser has the canonical HTTPS Origin and public Host.
        client.base_url=f'http://{entry_host}'
        login_as(client, 'qc_inspector')
        monkeypatch.setattr(mobile.settings, 'app_env', app_env)
        monkeypatch.setattr(mobile.settings, 'qc_mobile_require_https', mobile_tls)
        monkeypatch.setattr(mobile.settings, 'session_cookie_secure', False)
        monkeypatch.setattr(mobile.settings, 'qc_mobile_public_origin', origin)
        ready=False

        async def upstream(method, path, params, content):
            assert (method, path, params, content)==('GET', 'api/companies', [], b'')
            return httpx.Response(200 if ready else 403, json={'companies':[{'id':id_} for id_ in mobile.COMPANIES.values()]})

        monkeypatch.setattr(mobile, 'upstream', upstream)
        health='/api/qc-mobile/health'
        pairs='/api/qc-mobile/pairings'
        exchange='/api/qc-mobile/exchange'
        assert client.get(health).status_code==503
        assert client.get(health).headers['cache-control']=='no-store'
        result=client.post(pairs, json={'factory':'huaxing'}, headers={'Origin':origin})
        assert result.status_code==503 and 'QC 验货服务暂时不可用' in result.json()['detail']
        assert not (tmp_path/'companies/_mobile/pairings.sqlite3').exists()
        ready=True
        assert client.get(health).json()=={'service':'qc-mobile','ready':True}
        assert client.get(health, headers={'Host':'wrong.company.example','X-Forwarded-Host':entry_host}).status_code==503
        assert client.post(pairs, json={'factory':'huaxing'}, headers={'Origin':'https://other.example'}).status_code==403
        assert client.post(exchange, json={'ticket':''}, headers={'Origin':origin,'Sec-Fetch-Site':'cross-site'}).status_code==403
        assert client.post(exchange, json={'ticket':''}, headers={'Origin':origin}).status_code==422
        result=client.post(pairs, json={'factory':'huaxing'}, headers={'Origin':origin})
        assert result.status_code==200, result.text
        url=result.json()['url']
        assert url.startswith(origin+'/api/qc-mobile/app/#pair=')
        ticket=url.split('#pair=')[1]
        result=client.post(exchange, json={'ticket':ticket}, headers={'Origin':origin})
        assert result.status_code==200, result.text
        assert 'secure' in result.headers['set-cookie'].lower()
        assert client.post(exchange, json={'ticket':ticket}, headers={'Origin':origin}).status_code==401
        assert client.get(origin+'/api/qc-mobile/context').json()['factory']=='huaxing'


@pytest.mark.parametrize('origin', [
    '', 'http://qc.company.example', 'https://192.168.10.110',
    'http://1.1.1.1', 'https://127.0.0.1', 'https://224.0.0.1', 'https://100.64.0.1',
    'https://localhost', 'https://macbook.local', 'https://qc.company.example:5298',
    'https://qc.company.example/api', 'https://qc.company.example#', 'https://qc.company.example:bad',
])
def test_production_qr_origin_rejects_unusable_values(monkeypatch, origin):
    from fastapi import HTTPException
    mobile=importlib.import_module('app.api.qc_mobile')
    monkeypatch.setattr(mobile.settings, 'app_env', 'Production')
    monkeypatch.setattr(mobile.settings, 'qc_mobile_public_origin', origin)
    with pytest.raises(HTTPException) as error:
        mobile.configured_origin()
    assert error.value.status_code==503
