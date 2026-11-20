"""Monthly overview calculations, supplement boundaries and native Excel checks."""
from io import BytesIO
from uuid import uuid4
import openpyxl
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from test_customer_order_ledger import engine,db
from test_qc_approved_statistics import approval,transition,isolated,hashes
from test_qc_workflow import ACTOR
from app.services import qc_monthly_templates as monthly,qc_monthly_excel as excel,qc_monthly_overview as overview
DAY='2026-11-01'

def report(customer=''):
    return monthly.query('huaxing',DAY,customer,True)

def save(data,key,field,value):
    req=dict(date=DAY,customerKey=key,field=field,value=value,baseVersion=data['fields'].get(key,{}).get(field,{}).get('version',0),sourceRevision=data['sourceRevision'],requestKey=uuid4().hex,template='overview',customer=data.get('customer',''))
    result=monthly.save('huaxing',ACTOR,req)
    assert monthly.save('huaxing',ACTOR,req)==result
    return req

def test_original_denominator_unknown_returns_and_separate_field_meanings(db):
    entries=[approval(db,i,result=x,customer='客户A') for i,x in enumerate(['PASS','FAIL','PENDING','LG'])]
    approval(db,9,customer='客户A',actual='2026-10-05')
    before=hashes();data=report();r=data['overview']
    assert r['rows'][0]['values'][1:6]==[4,1,'',.25,'']
    assert r['months'][9]['rate']==1 and r['months'][10]['rate']==.25 and r['months'][11]['rate']==''
    assert len(r['details'])==4 and r['detailHeaders'][11]=='机构'
    assert all(row['values'][4]=='' and row['values'][11]=='行验' and row['values'][12]=='' for row in r['details'])
    failure=next(row for row in r['issues'] if row['id']==entries[1]['id'])
    assert failure['values'][4]=='' # inspection completion is not corrective closure
    assert hashes()==before
    key=r['rows'][0]['customerKey'];save(data,key,'returns','1');data=report()
    assert data['overview']['rows'][0]['values'][5]==.25

def test_manual_fields_are_versioned_shared_and_exported_without_overwriting_approval(db,monkeypatch,tmp_path):
    entry=approval(db,1,customer='客户A');approval(db,2,customer='客户B')
    data=report();key=next(c['key'] for c in data['customers'] if c['name']=='客户A');meta=data['overview']['metadataKey'];before=hashes()
    for field,value,target in [(f'detail:{entry["id"]}:customerName','=2+3',key),(f'detail:{entry["id"]}:returnReason','已核实退货原因',key),('returns','0',key),('overview:preparer','验货员',meta),('overview:reportDate','2026-11-30',meta),('overview:distribution:1:count','2',meta),('overview:distribution:1:rate','50%',meta),('overview:distribution:1:name','表面',meta),('overview:issue:1:problem','外观问题',meta),('overview:issue:1:completion','待复核',meta)]:
        save(data,target,field,value);data=report()
    assert all(hashes()[path]==digest for path,digest in before.items())
    filtered=report(key);assert filtered['sourceRevision']==data['sourceRevision']
    assert filtered['overview']['metadataKey']!=meta and filtered['overview']['signatures']['values']==['','','']
    assert all(v=='' for r in filtered['overview']['distribution'] for v in r['values'])
    for field,value in [('overview:preparer','验货员'),('overview:issue:1:completion','待复核')]:
        save(filtered,filtered['overview']['metadataKey'],field,value);filtered=report(key)
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('monthly-overview-test-key'))
    req=dict(date=DAY,customer=key,template='overview',sourceRevision=filtered['sourceRevision'],versions=excel.versions(filtered))
    result=excel.prepare('huaxing','owner',req);raw,name=excel.download('owner',result['url'].split('/')[-1])
    assert name=='客户月度验货总结_2026-11-01_2026-11-30.xlsx'
    book=openpyxl.load_workbook(BytesIO(raw));cached=openpyxl.load_workbook(BytesIO(raw),data_only=True)
    assert book.sheetnames==['月度汇总','验货明细'] and len(book.active._charts)==1
    detail=book['验货明细'];assert detail['L3'].value=='机构' and detail['E4'].value=='=2+3' and detail['E4'].data_type=='s'
    assert detail['M4'].value=='已核实退货原因' and detail['L4'].value=='行验'
    assert book.active['G4'].value=='=IF(C4=0,"",E4/C4)' and cached.active['G4'].value==1
    assert cached.active['I4'].value==0
    assert any(c.value=='制表：验货员' for row in book.active for c in row)
    assert any(c.value=='待复核' for row in book.active for c in row)
    for s in book:
        for row in s:
            for c in row:
                if c.value is not None:assert (c.alignment.horizontal,c.alignment.vertical)==('center','center')
    with pytest.raises(HTTPException):excel.download('other',result['url'].split('/')[-1])
    import os
    if os.getenv('QC_MONTHLY_EVIDENCE_DIR'):
        from pathlib import Path
        p=Path(os.environ['QC_MONTHLY_EVIDENCE_DIR']);p.mkdir(parents=True,exist_ok=True);(p/'月度总结_合成验收.xlsx').write_bytes(raw)

def test_conflicts_scope_invalid_rates_and_year_history_invalidate_export(db,monkeypatch):
    entry=approval(db,1,customer='彩星');data=report();key=data['customers'][0]['key'];meta=data['overview']['metadataKey']
    req=save(data,key,'returns','1')
    with pytest.raises(HTTPException) as exc:monthly.save('huaxing',ACTOR,{**req,'requestKey':uuid4().hex,'value':'2'})
    assert exc.value.status_code==409
    data=report()
    for target,field,value in [(key,'overview:reviewer','张'),(meta,'overview:distribution:1:rate','10'),(meta,'overview:distribution:1:count','-1'),(meta,'overview:reportDate','2026-13-01'),(key,f'detail:{entry["id"]}:productName','覆盖')]:
        with pytest.raises(HTTPException):save(data,target,field,value)
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('monthly-overview-test-key'))
    req=dict(date=DAY,customer='',template='overview',sourceRevision=data['sourceRevision'],versions=excel.versions(data))
    approval(db,2,customer='彩星',actual='2026-10-01')
    with pytest.raises(HTTPException) as exc:excel.prepare('huaxing','owner',req)
    assert exc.value.status_code==409
    other = monthly.query('huadeng', DAY, include_overview=True)
    assert other['total'] == 0 and not other['overview']['rows']
    assert key not in other['fields']
