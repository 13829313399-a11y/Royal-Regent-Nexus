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
        removed=client.post(endpoint+'/remove-photo',json={'revision':row['revision'],'photoId':photo});assert removed.status_code==200
        row=removed.json();assert not row['photos']
        submitted=client.post(endpoint+'/submit',json={'revision':row['revision']});assert submitted.status_code==200,submitted.text
        assert submitted.json()['reviewState']=='pending'
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
        assert client.get('/api/qc-mobile/app/remote.js').status_code==200
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
        assert client.get('/api/auth/me').status_code==404
        assert client.get('/api/qc-department/huaxing/api/health').status_code==404
