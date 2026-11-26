from io import BytesIO
import pytest
import openpyxl
from fastapi.testclient import TestClient
from app.main import create_app
from app.services.customer_order_zuru_native import unpack_references
from test_api import fixtures, BASE, HEADERS


@pytest.mark.parametrize('factory', ['huakang-a','huaxing'])
def test_multi_reference_export_ledger_retry_and_scope(factory,tmp_path):
    f=fixtures('test_customer_order_zuru_unified.py',{'po_book','data'})
    g=fixtures('test_zuru_original_summary.py',{'original_book'})
    refs=[('first.xlsx',f['data'](g['original_book']())),('second.xlsx',f['data'](g['original_book'](role='item')))]
    files=[('po_files',('po.xlsx',f['data'](f['po_book']()))),('schedule_file',refs[0]),('schedule_files',refs[1])]
    fields=dict(factory_id=factory,customer_code='zuru',received_date='2026-11-20')
    with TestClient(create_app(tmp_path,factory_id=factory,customer_codes=['zuru']),base_url=BASE) as c:
        r=c.post('/api/orders/preview',data=fields,files=files,headers=HEADERS)
        assert r.status_code==200,r.text
        p=r.json();fields.update(confirmed='true',preview_fingerprint=p['preview_fingerprint'])
        r=c.post('/api/orders/export',data=fields,files=files,headers=HEADERS)
        assert r.status_code==200,r.text
        w=openpyxl.load_workbook(BytesIO(r.content));assert {'新单数据','9560接单表_新单','Iteam表_新单'} <= set(w.sheetnames)
        r=c.post('/api/customer-order-ledger/imports/zuru',data=fields,files=files,headers=HEADERS)
        assert r.status_code==200,r.text
        saved=r.json();assert saved['created_count']==2
        again=c.post('/api/customer-order-ledger/imports/zuru',data=fields,files=files,headers=HEADERS)
        assert again.status_code==200 and again.json()['created_count']==0
        detail=c.get('/api/customer-order-ledger/lines/'+saved['items'][0]['id'],params={'factory_id':factory}).json()
        source=next(s for s in detail['sources'] if s['file_name'].endswith('.zip'))
        content=c.get('/api/customer-order-ledger/sources/'+source['id'],params={'factory_id':factory}).content
        assert unpack_references(source['file_name'],content)==refs
        stale=c.post('/api/orders/export',data=fields,files=files[:-1],headers=HEADERS)
        assert stale.status_code==409
        wrong=c.post('/api/orders/preview',data=dict(fields,factory_id='huadeng'),files=files,headers=HEADERS)
        assert wrong.status_code==403
