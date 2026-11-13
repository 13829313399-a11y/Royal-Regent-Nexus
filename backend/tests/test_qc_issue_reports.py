from io import BytesIO
from uuid import uuid4
import pytest, openpyxl
from fastapi import HTTPException
from pydantic import SecretStr
from app.services import qc_issue_reports as reports, qc_monthly_excel as excel, qc_monthly_templates as monthly
from test_customer_order_ledger import engine, db
from test_qc_approved_statistics import isolated, transition
from test_qc_monthly_templates import issue
from test_qc_workflow import ACTOR


def request(data, **changes):
    return dict(date=data['date'],period=data['period'],customer=data['customer'],sourceRevision=data['sourceRevision'],
                photoQuality='preview',allowPreviewFallback=False,**changes)


@pytest.mark.parametrize('day,period,expected',[
    ('2026-11-08','weekly',('2026-11-08','2026-11-14')),
    ('2026-11-14','weekly',('2026-11-08','2026-11-14')),
    ('2026-11-15','weekly',('2026-11-15','2026-11-21')),
    ('2026-01-01','weekly',('2025-12-28','2026-01-03')),
    ('2024-02-11','monthly',('2024-02-01','2024-02-29')),
    ('2026-11-13','yearly',('2026-01-01','2026-12-31')),
])
def test_period_bounds(day,period,expected):assert reports.bounds(day,period)==expected


def test_customer_query_supplement_scope_and_revoked_exclusion(db,monkeypatch):
    one=issue(db,1,'彩星',2);two=issue(db,2,'其他客户',1)
    data=reports.query('huaxing','2026-11-03','weekly')
    assert data['total']==2 and len(data['customers'])==2
    key=next(c['key'] for c in data['customers'] if c['name']=='彩星')
    scoped=reports.query('huaxing','2026-11-03','weekly',key)
    assert scoped['total']==1 and scoped['tables']['issues'][0]['id']==one['id']
    month=monthly.query('huaxing','2026-11-01');field='detail:'+one['id']+':contractNo'
    monthly.save('huaxing',ACTOR,dict(date='2026-11-01',customerKey=key,field=field,value='0009',baseVersion=0,sourceRevision=month['sourceRevision'],requestKey=uuid4().hex))
    assert reports.query('huaxing','2026-11-03','weekly',key)['tables']['issues'][0]['values'][2]=='0009'
    assert reports.query('huaxing','2026-11-03','yearly',key)['tables']['issues'][0]['values'][2]=='0009'
    transition(two,'revoke');assert reports.query('huaxing','2026-11-03','weekly')['total']==1
    assert reports.query('huaxing','2027-01-01','yearly')['total']==0
    with pytest.raises(HTTPException):reports.query('huadeng','2026-11-03','weekly')
    with pytest.raises(HTTPException):reports.query('huaxing','2026-11-03','weekly','invented')


@pytest.mark.parametrize('period',['weekly','monthly','yearly'])
def test_actual_excel_preview_original_missing_fallback_and_owner(db,monkeypatch,period):
    issue(db,1,photos=2)
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('isolated-issue-token'))
    data=reports.query('huaxing','2026-11-03',period)
    body=request(data);out=reports.prepare('huaxing','owner',body)
    raw,name=excel.download('owner',out['url'].split('/')[-1]);sheet=openpyxl.load_workbook(BytesIO(raw)).active
    assert len(sheet._images)==2 and sheet.max_row==3 and sheet['M2'].value=='照片'
    assert sheet['L2'].value=='照片备注' and out['filename']==name
    assert sheet['B3'].value=='彩星' and data['title'] in ''.join(str(c.value or '') for c in sheet[1])
    with pytest.raises(HTTPException):excel.download('other-owner',out['url'].split('/')[-1])
    body['photoQuality']='original'
    with pytest.raises(HTTPException) as err:reports.prepare('huaxing','owner',body)
    assert err.value.detail['code']=='original_missing'
    body['allowPreviewFallback']=True;out=reports.prepare('huaxing','owner',body)
    assert out['fallbackCount']==2 and '预览替代' in out['filename']
    body['sourceRevision']='0'*64
    with pytest.raises(HTTPException) as err:reports.prepare('huaxing','owner',body)
    assert err.value.status_code==409


def test_report_limits_fail_explicitly(db,monkeypatch):
    issue(db,1,photos=2)
    monkeypatch.setattr(reports,'MAX_REPORT_ROWS',0)
    with pytest.raises(HTTPException) as err:reports.query('huaxing','2026-11-03','yearly')
    assert err.value.status_code==422


def test_retained_original_exact_bytes_and_image_budget(db,monkeypatch):
    from unittest.mock import patch
    from app.services import qc_photo_assets as assets, qc_inspection_sheet as sheet
    from test_qc_photo_assets import image
    import base64,zipfile
    entry=issue(db,1,photos=0);entry=transition(entry,'revoke')
    raw=image('JPEG',size=(1600,1200));save=assets.save
    with patch.object(assets,'save',side_effect=lambda conn,pid,content,status,**kw:save(conn,pid,content,'available',**kw)):
        entry=sheet.add_photo('huaxing',entry['id'],dict(revision=entry['revision'],name='historic.jpg',content=base64.b64encode(raw).decode(),requestKey=uuid4().hex),ACTOR,review=True)
    transition(entry)
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('isolated-issue-token'))
    data=reports.query('huaxing','2026-11-03','yearly');body=request(data);body['photoQuality']='original'
    out=reports.prepare('huaxing','owner',body);content,_=excel.download('owner',out['url'].split('/')[-1])
    with zipfile.ZipFile(BytesIO(content)) as z:
        media=[z.read(n) for n in z.namelist() if n.startswith('xl/media/')]
    assert media==[raw] and out['fallbackCount']==0


def test_annual_large_population_and_real_photo_size_limit(db,monkeypatch):
    from copy import deepcopy
    entry=issue(db,1,photos=2)
    real_query=reports.weekly.approved.query
    def many(factory,params,_report_snapshots):
        seed=[];result=real_query(factory,params,_report_snapshots=seed)
        for i in range(5001):
            item,marker=deepcopy(seed[0]);item['id']=f'{i:032x}'
            _report_snapshots.append((item,marker))
        return result
    monkeypatch.setattr(reports.weekly.approved,'query',many)
    with pytest.raises(HTTPException) as err:reports.query('huaxing','2026-11-03','yearly')
    assert err.value.status_code==422 and '5000' in err.value.detail
    monkeypatch.setattr(reports.weekly.approved,'query',real_query)
    data=reports.query('huaxing','2026-11-03','yearly')
    monkeypatch.setattr(excel,'MAX_BYTES',1)
    with pytest.raises(HTTPException) as err:excel.render(data,'issues','huaxing')
    assert err.value.status_code==422 and '照片总量' in err.value.detail


def test_http_scope_permission_and_static_assets(monkeypatch,tmp_path):
    import test_molding_sample_api
    from test_molding_sample_api import make_client,login_as
    from test_qc_daily_report import isolated_upstream,seed
    from test_qc_department_gateway import grant_permission_override
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'http-companies'))
    monkeypatch.setenv('AUTHZ_MODE','enforce')
    with make_client(monkeypatch) as client:
        isolated_upstream(monkeypatch);health='/api/qc-department/huaxing/api/health'
        assert client.get(health).status_code==401
        login_as(client,'qc_inspector');base=client.get(health).json()['frame_url'];seed(client,base)
        url=base+'api/issue-reports';params={'period':'yearly','date':'2026-11-03'}
        response=client.get(url,params=params);assert response.status_code==200,response.text
        data=response.json();assert data['canExport'] is True
        for asset in ['qc-issue-reports.js','qc-issue-reports.css']:assert client.get(base+asset).status_code==200
        assert client.get(base+'qc-issue-reports.test.js').status_code==404
        assert client.get(url,params={**params,'company':'hy-huadeng'}).status_code==403
        assert client.get(url,params=[('date','2026-11-03'),('date','2026-11-03'),('period','yearly')]).status_code==422
        assert client.post(url+'/excel',json=request(data),headers={'sec-fetch-site':'cross-site'}).status_code==403
        grant_permission_override('qc_inspector','qc_inspection:report_export',effect='deny',factory_id='huaxing',department='qc')
        newbase=client.get(health).json()['frame_url'];url=newbase+'api/issue-reports'
        assert client.get(url,params=params).json()['canExport'] is False
        assert client.post(url+'/excel',json=request(data)).status_code==403
