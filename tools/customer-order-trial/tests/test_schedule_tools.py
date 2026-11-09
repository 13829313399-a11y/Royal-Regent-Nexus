from datetime import date
from io import BytesIO
import json
import openpyxl
from openpyxl.comments import Comment
from openpyxl.styles import Font
from fastapi.testclient import TestClient
from app.main import create_app
from app.services import customer_order_casdon as casdon,customer_order_unified as unified
from test_api import BASE,HEADERS,fixtures

P='/api/customer-order-ledger/schedule'


def test_casdon_ship_restore_real_worker_source_and_ledger_unchanged(tmp_path):
    source=fixtures('test_customer_order_casdon_workbook.py',{'fixture','content'},service=casdon,unified=unified,Comment=Comment,Font=Font)['content']()
    with TestClient(create_app(tmp_path,factory_id='huadeng'),base_url=BASE) as c:
        files={'schedule_file':('casdon.xlsx',source)}
        r=c.post(P+'/casdon/preview?factory_id=huadeng',headers=HEADERS,files=files)
        assert r.status_code==200,r.text
        parsed=r.json()
        form={'fingerprint':parsed['fingerprint'],'action':'ship','selections':'["4", "5"]','reason':'合成订单归档核对','confirmed':'true'}
        bad=c.post(P+'/casdon/export?factory_id=huadeng',headers=HEADERS,files=files,data={**form,'fingerprint':'stale'})
        assert bad.status_code==409 and c.get('/api/orders/exports').json()['total']==0
        r=c.post(P+'/casdon/export?factory_id=huadeng',headers=HEADERS,files=files,data=form)
        assert r.status_code==200,r.text
        shipped=r.content
        after=c.post(P+'/casdon/preview?factory_id=huadeng',headers=HEADERS,files={'schedule_file':('shipped.xlsx',shipped)}).json()
        selected=[row['id'] for row in after['rows'] if row['section']=='shipped' and row['reference'] in {'A','B'}]
        assert len(selected)==2
        form.update(fingerprint=after['fingerprint'],action='restore',selections=json.dumps(selected),reason='合成订单恢复核对')
        r=c.post(P+'/casdon/export?factory_id=huadeng',headers=HEADERS,files={'schedule_file':('shipped.xlsx',shipped)},data=form)
        assert r.status_code==200,r.text
        final=c.post(P+'/casdon/preview?factory_id=huadeng',headers=HEADERS,files={'schedule_file':('restored.xlsx',r.content)}).json()
        assert {'A','B'}<={row['reference'] for row in final['rows'] if row['section']=='active'}
        assert c.get('/api/customer-order-ledger/lines?factory_id=huadeng').json()['total']==0
        assert c.get('/api/orders/exports').json()['total']==2
        assert files['schedule_file'][1]==source
        assert c.post(P+'/casdon/preview?factory_id=huaxing',headers=HEADERS,files=files).status_code==403


def test_360_inspection_organize_original_numbers_and_ledger_unchanged(tmp_path):
    book=openpyxl.Workbook();book.remove(book.active)
    for name in ('ITEM表','接单表','正单评审表'):
        sheet=book.create_sheet(name)
        for col,header in enumerate(unified.ITEM_HEADERS if name=='ITEM表' else unified.ORDER_HEADERS,1):sheet.cell(3,col,header)
        ref,item,inspection=(5,8,25) if name=='ITEM表' else (4,7,18)
        for row,product,when in [(4,'00123456789',date(2000,1,1)),(5,'76543220069',date(2099,1,1))]:
            sheet.cell(row,ref,f'RL-100-{row}');sheet.cell(row,item,product);sheet.cell(row,inspection,when);sheet.cell(row,2,'备料单')
        sheet['A10']='取消单';sheet['A13']='已走货订单'
    book['ITEM表']['AM3']='出货货号';book['ITEM表']['AM5']='手工例外'
    stream=BytesIO();book.save(stream);source=stream.getvalue();book.close()
    with TestClient(create_app(tmp_path,factory_id='huakang-a'),base_url=BASE) as c:
        r=c.post(P+'/organize-360?factory_id=huakang-a',headers=HEADERS,files={'schedule_file':('360.xlsx',source)})
        assert r.status_code==200,r.text
        assert r.headers['X-Schedule-Organize-Report']
        out=openpyxl.load_workbook(BytesIO(r.content));sheet=out['ITEM表']
        values={cell.value:(sheet.cell(cell.row,8).value,sheet.cell(cell.row,39).value) for cell in list(sheet._cells.values()) if cell.column==5 and str(cell.value).startswith('RL-')}
        assert values=={'RL-100-4':('00123456789','0012345'),'RL-100-5':('76543220069','手工例外')}
        out.close()
        assert c.get('/api/customer-order-ledger/lines?factory_id=huakang-a').json()['total']==0
        assert c.get('/api/orders/exports').json()['total']==1
