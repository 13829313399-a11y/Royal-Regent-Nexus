"""Exercise packaged engines through real child workers and an isolated export store."""
import ast
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import time

from fastapi.testclient import TestClient
import openpyxl
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
import pytest

from app.main import create_app
from app.services import customer_order_unified as service
from app.services import customer_order_huaxing_unified as hx_mapping
from app.services.huakang_a_order_legacy import unified_schedule as a_mapping

ROOT=Path(__file__).resolve().parents[3]
BASE='http://127.0.0.1:8765'
HEADERS={'X-Order-Trial':'1','Origin':BASE}


def fixtures(filename,names,**values):
    source=ROOT/'backend/tests'/filename
    tree=ast.parse(source.read_text());nodes=[]
    for node in tree.body:
        if isinstance(node,ast.FunctionDef) and node.name in names:
            node.decorator_list=[];nodes.append(node)
        elif isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id in names for t in node.targets):nodes.append(node)
    namespace={'BytesIO':BytesIO,'openpyxl':openpyxl,'service':service,'PdfWriter':PdfWriter,
        'DictionaryObject':DictionaryObject,'NameObject':NameObject,'DecodedStreamObject':DecodedStreamObject,**values}
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(source),'exec'),namespace)
    return namespace


def sample(factory):
    if factory=='huakang-a':
        f=fixtures('test_green_toys_po_integrity.py',{'LINES','html_po','recovery_template'},mapping=a_mapping)
        return 'green-toys',[('synthetic.html',f['html_po']())],f['recovery_template'](),8
    if factory=='huadeng':
        f=fixtures('test_customer_order_goliath.py',{'po','_pdf_document','template'})
        return 'goliath',[('synthetic.pdf',f['po']())],f['template'](),1
    template=fixtures('test_customer_order_huaxing_unified.py',{'template','data'},mapping=hx_mapping)
    f=fixtures('test_customer_order_disney_factory.py',{'disney_po','arguments'},template=template['template'],data=template['data'])
    args=f['arguments'](factory,f['disney_po']())
    return 'disney',args['po_files'],args['schedule_content'],1


def uploads(pos,content):
    return [('po_files',(name,value)) for name,value in pos]+[('schedule_file',('synthetic.xlsx',content))]


def preview(client,factory):
    code,pos,content,count=sample(factory)
    fields={'customer_code':code,'factory_id':factory,'received_date':'2026-11-09'}
    files=uploads(pos,content)
    response=client.post('/api/orders/preview',data=fields,files=files,headers=HEADERS)
    assert response.status_code==200,response.text
    result=response.json()
    assert result['factory_id']==factory and len(result['rows'])==count
    keys=[issue['skip_key'] for row in result['rows'] for issue in row['issues'] if issue.get('can_skip') and issue.get('skip_key')]
    fields.update(confirmed='true',preview_fingerprint=result['preview_fingerprint'],skipped_issue_keys=json.dumps(keys),
        manual_overrides='[]',confirmation_reason='本地合成资料核对')
    return fields,files,result


@pytest.mark.parametrize('factory',['huakang-a','huakang-d','huaxing','huadeng'])
def test_real_factory_preview_export_history_restart(factory,tmp_path):
    app=create_app(tmp_path,factory_id=factory)
    with TestClient(app,base_url=BASE) as client:
        config=client.get('/api/config').json()
        assert config['factory_id']==factory
        fields,files,parsed=preview(client,factory)
        original=deepcopy(files)
        response=client.post('/api/orders/export',data=fields,files=files,headers=HEADERS)
        assert response.status_code==200,response.text
        workbook=openpyxl.load_workbook(BytesIO(response.content),data_only=False)
        assert {'ITEM表','接单表','正单评审表'}<=set(workbook.sheetnames)
        workbook.close()
        assert files==original
        history=client.get('/api/orders/exports').json()
        assert history['total']==1 and history['items'][0]['row_count']==len(parsed['rows'])
        ident=history['items'][0]['id']
        assert client.get(f'/api/orders/exports/{ident}/download').content==response.content
        repeated=client.post('/api/orders/export',data=fields,files=files,headers=HEADERS)
        assert repeated.status_code==200 and repeated.content==response.content
        assert client.get('/api/orders/exports').json()['total']==1
    with TestClient(create_app(tmp_path,factory_id=factory),base_url=BASE) as second:
        assert second.get('/api/orders/exports').json()['total']==1
        assert second.get(f'/api/orders/exports/{ident}/download').content==response.content
    with sqlite3.connect(tmp_path/'order_trial.sqlite3') as database:
        with pytest.raises(sqlite3.IntegrityError,match='append-only'):
            database.execute('DELETE FROM exports')


@pytest.mark.parametrize('tamper',['fingerprint','unknown-confirmation','unknown-manual-row','not-confirmed'])
def test_invalid_controls_never_persist_export(tamper,tmp_path):
    with TestClient(create_app(tmp_path,factory_id='huaxing'),base_url=BASE) as client:
        fields,files,result=preview(client,'huaxing')
        if tamper=='fingerprint':fields['preview_fingerprint']='incorrect'
        elif tamper=='unknown-confirmation':fields['skipped_issue_keys']='["unknown|quantity|999"]'
        elif tamper=='not-confirmed':fields['confirmed']='false'
        else:fields['manual_overrides']=json.dumps([{'row_id':'unknown','issue_key':'unknown','field':'quantity','value':'100'}])
        response=client.post('/api/orders/export',data=fields,files=files,headers=HEADERS)
        assert response.status_code in {400,409},response.text
        assert client.get('/api/orders/exports').json()['total']==0


def test_factory_host_origin_and_missing_header_are_rejected(tmp_path):
    with TestClient(create_app(tmp_path,factory_id='huaxing'),base_url=BASE) as client:
        assert client.get('/api/config',headers={'Host':'evil.invalid'}).status_code==403
        assert client.get('/api/config',headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.options('/api/orders/export',headers={'Origin':'https://evil.invalid'}).status_code==403
        assert client.post('/api/orders/export').status_code==403
        code,pos,content,_=sample('huaxing')
        for customer,factory in [('disney','huakang-d'),('headstart','huaxing'),('jp','huaxing')]:
            r=client.post('/api/orders/preview',data={'customer_code':customer,'factory_id':factory,'received_date':'2026-11-09'},
                files=uploads(pos,content),headers=HEADERS)
            assert r.status_code in {400,403},r.text
    with pytest.raises(RuntimeError,match='厂区'):create_app(tmp_path,factory_id='huadeng')
    with pytest.raises(ValueError,match='未开放'):create_app(tmp_path/'c',factory_id='huakang-c')
    with pytest.raises(ValueError,match='127'):create_app(tmp_path/'remote',host='0.0.0.0')
