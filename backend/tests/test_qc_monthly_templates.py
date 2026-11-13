"""Monthly template contract checks use isolated workflow stores only."""
from io import BytesIO
from uuid import uuid4
from copy import deepcopy
import base64,json
import pytest,xlrd,openpyxl
from PIL import Image
from fastapi import HTTPException
from pydantic import SecretStr
from app.services import qc_monthly_templates as monthly, qc_monthly_excel as excel, qc_weekly_templates as weekly, qc_inspection_sheet as sheet
from test_customer_order_ledger import engine,db
from test_qc_approved_statistics import approval,transition,isolated,hashes
from test_qc_workflow import ACTOR
DAY='2026-11-01'

def body(data,field,value,customer=None):
    key=customer or data['customers'][0]['key']
    return dict(date=DAY,customerKey=key,field=field,value=value,baseVersion=data['fields'][key].get(field,{}).get('version',0),sourceRevision=data['sourceRevision'],requestKey=uuid4().hex)

def issue(db,n,customer='彩星',photos=1,result='PASS'):
    entry=approval(db,n,customer=customer,result=result)
    entry=transition(entry,'revoke')
    entry=sheet.save('huaxing',entry['id'],dict(revision=entry['revision'],result=entry['result'],remark=entry['remark'],inspectionProblem='合成问题描述 '+str(n)),ACTOR,review=True)
    img=BytesIO();Image.new('RGB',(50,40),'red').save(img,format='PNG')
    for i in range(photos):
        entry=sheet.add_photo('huaxing',entry['id'],dict(revision=entry['revision'],name=f'合成照片{i}.png',content=base64.b64encode(img.getvalue()).decode(),requestKey=uuid4().hex),ACTOR,review=True)
    return transition(entry)

def test_calendar_population_layout_and_read_only(db):
    approval(db,1,customer='彩星',actual='2026-11-30');approval(db,2,customer='其他',actual='2026-11-01')
    approval(db,3,customer='彩星',actual='2026-10-31');approval(db,4,customer='彩星玩具',actual='2026-11-05')
    issue(db,5,customer='其他',result='PASS')
    before=hashes();data=monthly.query('huaxing',DAY)
    assert data['dateTo']=='2026-11-30' and data['total']==4
    assert len(data['tables']['caixing'])==1 and len(data['tables']['issues'])==1
    assert data['tables']['issues'][0]['values'][8]=='PASS' and len(data['tables']['issues'][0]['photos'])==1
    assert [len(t['headers']) for t in data['templates']]==[15,18,12,18]
    assert data['tables']['summary'][0]['values'][1:]==[1,1,'','']
    assert hashes()==before and not monthly._path().exists()
    with pytest.raises(HTTPException):monthly.query('huadeng',DAY)

def test_saved_blanks_returns_conflicts_month_isolation_and_no_record_mutation(db):
    entry=issue(db,1);data=monthly.query('huaxing',DAY);before=hashes()
    field=f'detail:{entry["id"]}:contractNo';request=body(data,field,'0000123')
    saved=monthly.save('huaxing',ACTOR,request)
    assert monthly.save('huaxing',ACTOR,request)==saved
    changed=monthly.query('huaxing','2026-11-30')
    assert [changed['tables'][k][0]['values'][i] for k,i in [('all',3),('customers',3),('caixing',2),('issues',2)]]==['0000123']*4
    monthly.save('huaxing',ACTOR,body(changed,'returns','2'))
    changed=monthly.query('huaxing',DAY)
    assert changed['tables']['summary'][0]['values'][3:]==['2',2.0]
    assert not weekly._path().exists() and monthly.query('huaxing','2026-12-01')['fields']=={}
    assert all(hashes()[p]==h for p,h in before.items())
    with pytest.raises(HTTPException) as e:monthly.save('huaxing',ACTOR,{**request,'requestKey':uuid4().hex,'value':'different'})
    assert e.value.status_code==409
    with pytest.raises(HTTPException):monthly.save('huaxing',ACTOR,body(changed,f'detail:{entry["id"]}:productName','overwrite'))

@pytest.mark.parametrize('value',['-1','1.5','abc'])
def test_return_validation(db,value):
    approval(db,1,customer='彩星');data=monthly.query('huaxing',DAY)
    with pytest.raises(HTTPException):monthly.save('huaxing',ACTOR,body(data,'returns',value))

def test_four_exports_headers_all_photos_and_no_history(db):
    entry=issue(db,1,photos=5);approval(db,2,customer='Other/A');approval(db,3,customer='Other:A')
    data=monthly.query('huaxing',DAY)
    monthly.save('huaxing',ACTOR,body(data,f'detail:{entry["id"]}:contractNo','=2+3',next(c['key'] for c in data['customers'] if c['name']=='彩星')))
    data=monthly.query('huaxing',DAY)
    for kind in ('caixing','all','customers'):
        raw=excel.render(data,kind)
        import os
        from pathlib import Path
        if os.environ.get('QC_MONTHLY_EVIDENCE_DIR'):
            out=Path(os.environ['QC_MONTHLY_EVIDENCE_DIR']);out.mkdir(parents=True,exist_ok=True);(out/('合成验收样本_'+kind+'.xls')).write_bytes(raw)
        book=xlrd.open_workbook(file_contents=raw,formatting_info=True)
        spec=next(t for t in monthly.TEMPLATES if t['id']==kind);hr=0 if kind=='caixing' else 1
        for s in book.sheets():
            assert s.row_values(hr)==spec['headers']
            assert (bool(s.merged_cells) if kind=='caixing' else not s.merged_cells)
            assert all(book.xf_list[s.cell_xf_index(hr,c)].alignment.hor_align==2 for c in range(len(spec['headers'])))
            if kind!='caixing':
                title_col=next(c for c in range(s.ncols) if s.cell_value(0,c))
                assert title_col>0 and book.xf_list[s.cell_xf_index(0,title_col)].alignment.hor_align==2
            assert '每周' not in str(s.row_values(0))
        if kind=='customers':assert len(book.sheets())==3 and len(set(book.sheet_names()))==3
        if kind=='caixing':
            assert book.sheet_by_index(0).cell_value(1,2)=='=2+3'
            assert book.sheet_by_index(0).row_values(book.sheet_by_index(0).nrows-1)[5]==''
    data['tables']['issues'][0]['values'][11]='第一张：外观\n第二张：标识'
    raw=excel.render(data,'issues')
    if os.environ.get('QC_MONTHLY_EVIDENCE_DIR'):(out/'合成验收样本_issues.xlsx').write_bytes(raw)
    book=openpyxl.load_workbook(BytesIO(raw));s=book.active
    assert [v.value for v in s[2]]==[*monthly.TEMPLATES[2]['headers'][:11],'照片备注','照片']
    assert s['L3'].value=='第一张：外观\n第二张：标识'
    assert len(s._images)==5
    for image in s._images:
        assert (image.anchor._from.col,image.anchor._from.row)==(12,2)
        assert (image.anchor._from.rowOff+image.anchor.ext.cy)/excel.EMU_PER_PIXEL <= s.row_dimensions[3].height/0.75
    assert s['C3'].value=='=2+3' and s['C3'].data_type=='s'
    assert not s.merged_cells.ranges and s.max_row==3
    title_cell=next(c for c in s[1] if c.value)
    assert title_cell.column>1 and title_cell.alignment.horizontal=='center'
    assert all(c.alignment.horizontal=='center' for c in s[2])
    assert len(excel._asset('issues')[0])<100000

def test_exports_many_rows_preserve_footer_and_all_records(db):
    approval(db,1,customer='彩星');data=monthly.query('huaxing',DAY)
    for k in ('all','caixing','customers'):
        row=data['tables'][k][0];data['tables'][k]=[deepcopy(row) for _ in range(300)]
    for kind in ('all','caixing','customers'):
        book=xlrd.open_workbook(file_contents=excel.render(data,kind));s=book.sheet_by_index(0)
        assert s.nrows>=301 and s.cell_value(300,0)!=''
        if kind=='caixing': assert s.cell_value(s.nrows-2,4)=='不合格(退货)单数'

def test_export_tickets_versions_and_owner(db,monkeypatch):
    issue(db,1,customer='彩星');data=monthly.query('huaxing',DAY)
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('monthly-test-secret'))
    req=dict(date=DAY,customer='',template='all',sourceRevision=data['sourceRevision'],versions=excel.versions(data))
    prepared=excel.prepare('huaxing','owner',req);token=prepared['url'].split('/')[-1]
    raw,name=excel.download('owner',token);assert raw and name==prepared['filename']=='全客明细_月度验货_2026-11-01_2026-11-30.xls'
    for kind,prefix in [('caixing','彩星汇总'),('all','全客明细'),('issues','问题图文'),('customers','分客明细')]:
        assert excel.filename(kind,DAY,'2026-11-30').startswith(prefix+'_')
    issue_request={**req,'template':'issues'}
    photo_export=excel.prepare('huaxing','owner',issue_request)
    raw,name=excel.download('owner',photo_export['url'].split('/')[-1])
    assert raw.startswith(b'PK')
    assert name==photo_export['filename']=='问题图文_月度验货_2026-11-01_2026-11-30_预览图.xlsx'
    with pytest.raises(HTTPException,match='仅支持导出预览图'):
        excel.prepare('huaxing','owner',{**issue_request,'photoQuality':'original'})
    with pytest.raises(HTTPException):excel.download('other',token)
    monthly.save('huaxing',ACTOR,body(data,'returns','0'))
    with pytest.raises(HTTPException) as e:excel.prepare('huaxing','owner',req)
    assert e.value.status_code==409


def test_gateway_permissions_export_and_monthly_route(monkeypatch,tmp_path):
    import test_molding_sample_api
    from test_molding_sample_api import make_client,login_as
    from test_qc_daily_report import isolated_upstream,seed
    from test_qc_department_gateway import grant_permission_override
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'companies'))
    monkeypatch.setenv('AUTHZ_MODE','enforce')
    with make_client(monkeypatch) as client:
        isolated_upstream(monkeypatch);health='/api/qc-department/huaxing/api/health'
        assert client.get(health).status_code==401
        login_as(client,'qc_inspector');base=client.get(health).json()['frame_url'];seed(client,base)
        url=base+'api/monthly-templates';response=client.get(url,params={'date':DAY})
        assert response.status_code==200,response.text
        data=response.json();assert data['total']==6 and data['canEdit']
        assert client.get(base+'qc-monthly-templates.js').status_code==200
        assert client.get(url,params=[('date',DAY),('date',DAY)]).status_code==422
        assert client.get(url,params={'date':DAY,'company':'hy-huadeng'}).status_code==403
        field=next(f for cells in data['fields'].values() for f in cells if f.startswith('detail:'))
        key=next(k for k,cells in data['fields'].items() if field in cells)
        req=body(data,field,'合成补录',key)
        assert client.post(url+'/save',json=req,headers={'sec-fetch-site':'cross-site'}).status_code==403
        assert client.post(url+'/save',json=req).status_code==200
        data=client.get(url,params={'date':DAY}).json();assert data['fields'][key][field]['value']=='合成补录'
        from app.services import qc_monthly_excel as active_excel
        monkeypatch.setattr(active_excel.settings,'qc_department_gateway_token',SecretStr('isolated-monthly-export-token'))
        req=dict(date=DAY,customer='',template='all',sourceRevision=data['sourceRevision'],versions=excel.versions(data))
        result=client.post(url+'/excel',json=req);assert result.status_code==200,result.text
        assert client.get(base+result.json()['url']).status_code==200
        grant_permission_override('qc_inspector','qc_inspection:report_export',effect='deny',factory_id='huaxing',department='qc')
        newbase=client.get(health).json()['frame_url']
        assert client.post(newbase+'api/monthly-templates/excel',json=req).status_code==403
        assert client.get(newbase+result.json()['url']).status_code==403
