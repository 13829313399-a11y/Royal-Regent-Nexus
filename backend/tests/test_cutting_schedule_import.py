"""Schedule-only intake retains a ledger origin; isolated SQLite, no production DB."""
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import openpyxl
import pytest
from sqlalchemy import select,func,text
from sqlalchemy.orm import Session
from test_cutting_ops import client,user,command,create,bom_body,state,BASE
from test_cutting_orders import flow
from test_cutting_planning import planned
from test_cutting_materials import bridge,actor,warehouse_view,warehouse_post
from app.models.customer_order_ledger import OrderLedgerLine as Line,OrderLedgerSource as Source,OrderLedgerVersion,OrderLedgerDispatch
from app.models.cutting_ops import CuttingOrder
from app.services.cutting_schedule_import import parse,SCHEMA

URL=BASE+'/schedule-import'
HEAD=['客户','订单号','货号','货名','数量','交期','单位']
ROW=['合成洋行','SCHEDULE-TEST-01','00012','测试产品',100,'2026-11-03','PCS']
def workbook(rows=None):
    b=openpyxl.Workbook();w=b.active;w.title='业务排期';w.append(HEAD)
    for row in (rows if rows is not None else [ROW]):w.append(row)
    result=BytesIO();b.save(result);b.close();return result.getvalue()
def preview(p,content,factory='huakang-c'):
    return p.post(URL+'/preview',data={'factory_id':factory},files={'schedule_file':('排期.xlsx',content)})
def confirm(p,content,v,**changes):
    data=dict(factory_id='huakang-c',operation_id=uuid4().hex,reason='合成排期来源核对',fingerprint=v['fingerprint'],file_sha256=v['file_sha256'],confirmed='true')|changes
    response=p.post(URL+'/confirm',data=data,files={'schedule_file':('排期.xlsx',content)})
    return response,data
def count(p,table):
    with Session(p.engine) as db:return db.scalar(select(func.count()).select_from(table))

def test_archive_dispatch_receipt_bom_and_duplicates(flow):
    p=flow;content=workbook();v=preview(p,content).json()
    with p.engine.begin() as db:
        db.execute(text("CREATE TRIGGER schedule_test_dispatch_immutable BEFORE UPDATE OF snapshot ON order_ledger_dispatches BEGIN SELECT RAISE(ABORT,'Dispatch evidence is immutable'); END"))
    assert v['can_confirm'] and v['rows'][0]['row']==2 and count(p,Source)==0
    response,data=confirm(p,content,v);assert response.status_code==200,response.text
    result=response.json();assert result['created']==1 and result['skipped']==0
    repeated,_=confirm(p,content,v,**data);assert repeated.json()==result
    v2=preview(p,content).json();assert v2['duplicate_count']==1
    r,_=confirm(p,content,v2);assert r.json()['created']==0 and r.json()['skipped']==1
    assert count(p,Source)==1 and count(p,OrderLedgerVersion)==1
    line=result['rows'][0]['line_id']
    order=p.get(BASE+'/orders/'+line,params={'factory_id':'huakang-c'}).json()
    assert not order['needs_receipt'] and order['snapshot']['intake_row']==2 and order['snapshot']['order_unit']=='PCS'
    assert order['current']['version']==1
    assert order['current']['data']['receipt']==dict(mode='automatic',source_version=1,received_at=order['received_at'])
    assert order['current']['data']['requisition'] is None
    material=create(p);bom=state(p,create(p,bom_body(material)),'published').json()
    bound=p.post(BASE+'/orders/'+line+'/bom',json=command(expected_version=1,bom_id=bom['id'],bom_version=bom['version'],target_sets=50,quantity_basis='工程核对100件组成50套'))
    assert bound.status_code==200,bound.text
    assert bound.json()['current']['data']['order']['intake_batch']==data['operation_id']
    with Session(p.engine) as db:
        assert db.scalar(select(Source)).content==content
        assert db.get(Line,line).data['source_import']['sheet']=='业务排期'
        assert db.get(Line,line).data['source_kind']==SCHEMA
        assert db.scalar(select(func.count()).select_from(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id==line))==1

@pytest.mark.parametrize('field,value',[('quantity',0),('quantity','NaN'),('quantity','=50+50'),('requested_ship_date','bad-date'),('unit',''),('customer_name','未知客户')])
def test_invalid_input_never_writes(flow,field,value):
    row=ROW.copy();row[['customer_name','reference_no','product_no','product_name_zh','quantity','requested_ship_date','unit'].index(field)]=value
    content=workbook([row]);v=preview(flow,content).json()
    assert not v['can_confirm'] and v['rows'][0]['status']=='invalid'
    r,_=confirm(flow,content,v);assert r.status_code==409,r.text
    assert count(flow,Source)==0 and count(flow,Line)==1

def test_file_duplicates_conflicts_and_preview_tampering(flow):
    p=flow;content=workbook([ROW,ROW]);v=preview(p,content).json();assert not v['can_confirm']
    assert '重复订单' in v['rows'][1]['errors'][0]
    good=workbook();v=preview(p,good).json();assert confirm(p,good,v)[0].status_code==200
    changed=ROW.copy();changed[4]=101
    content=workbook([changed]);v=preview(p,content).json()
    assert v['rows'][0]['status']=='conflict' and confirm(p,content,v)[0].status_code==409
    v=preview(p,good).json();assert confirm(p,content,v)[0].status_code==409
    assert count(p,Source)==1 and count(p,OrderLedgerVersion)==1

def test_scope_permissions_and_recovery_fence(flow):
    p=flow;content=workbook();assert preview(p,content,factory='huakang-d').status_code==422
    p.cutting_auth['user']=user('read');assert preview(p,content).status_code==403
    p.cutting_auth['user']=user('read','order_receive');v=preview(p,content).json()
    _,data=confirm(p,content,v,confirmed='false');assert count(p,Source)==0
    body=command(operation_id=uuid4().hex,reason='合成排期来源核对')|dict(fingerprint=v['fingerprint'],file_sha256=v['file_sha256'],file_name='排期.xlsx',confirmed=True)
    p.cutting_auth['user']=user('read')
    assert p.post(URL+'/recover',json={'command':body}).json()=={'state':'abandoned'}
    p.cutting_auth['user']=user('read','order_receive')
    r,_=confirm(p,content,v,operation_id=body['operation_id']);assert r.status_code==409
    assert count(p,Source)==0

def test_competing_imports_create_one_origin(flow):
    content=workbook();v=preview(flow,content).json()
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(lambda _:confirm(flow,content,v)[0],range(2)))
    assert all(r.status_code==200 for r in results),[r.text for r in results]
    assert sum(r.json()['created'] for r in results)==1
    assert count(flow,Source)==1 and count(flow,OrderLedgerVersion)==1


def test_database_identity_conflict_rolls_back_archive_and_returns_repreview(flow):
    content=workbook();v=preview(flow,content).json()
    # A conflict may arise after the last existence check (e.g. another intake
    # writer); enforce that boundary in the database, after the source INSERT.
    with flow.engine.begin() as db:
        db.execute(text("CREATE TRIGGER schedule_test_identity_conflict BEFORE INSERT ON order_ledger_lines BEGIN SELECT RAISE(ABORT,'concurrent order identity conflict'); END"))
    r,_=confirm(flow,content,v)
    assert r.status_code==409,r.text
    assert '重新预览' in r.json()['detail']
    assert count(flow,Source)==0 and count(flow,Line)==1 and count(flow,OrderLedgerVersion)==0

def test_parser_limits_template_and_leading_zeroes(flow):
    b=openpyxl.Workbook();w=b.active;w.append(HEAD);w.append(ROW);w['C2']=12;w['C2'].number_format='00000'
    stream=BytesIO();b.save(stream);b.close()
    assert parse(stream.getvalue(),'排期.xlsx')['rows'][0]['data']['product_no']=='00012'
    assert flow.get(URL+'/template',params={'factory_id':'huakang-c'}).status_code==200
    assert preview(flow,workbook([ROW]*501)).status_code==422
    assert preview(flow,b'not an xlsx').status_code==422


def multiple_sheets(second_headers, second_rows, hidden=False):
    book = openpyxl.Workbook()
    first = book.active
    first.title = '标准排期'
    first.append(HEAD)
    first.append(ROW)
    second = book.create_sheet('待核对排期')
    if second_headers:
        second.append(second_headers)
    for row in second_rows:
        second.append(row)
    if hidden:
        second.sheet_state = 'hidden'
    output = BytesIO()
    book.save(output)
    book.close()
    return output.getvalue()


@pytest.mark.parametrize('hidden', [False, True])
def test_populated_incomplete_sheet_blocks_whole_import(flow, hidden):
    content = multiple_sheets(HEAD[:-1], [ROW[:-1]], hidden=hidden)
    response = preview(flow, content)
    assert response.status_code == 200, response.text
    data = response.json()
    assert not data['can_confirm']
    assert len(data['rows']) == 1
    sheets = {sheet['sheet']: sheet for sheet in data['sheets']}
    assert sheets['标准排期']['status'] == 'ready'
    assert sheets['标准排期']['row_count'] == 1
    assert sheets['待核对排期']['status'] == 'blocked'
    assert '单位' in sheets['待核对排期']['message']
    result, _ = confirm(flow, content, data)
    assert result.status_code == 409
    assert '工作表' in result.json()['detail']
    assert count(flow, Source) == 0 and count(flow, Line) == 1
    assert count(flow, OrderLedgerVersion) == 0


def test_all_valid_and_empty_sheets_are_explicitly_accounted_for(flow):
    other = ROW.copy()
    other[1] = 'SCHEDULE-TEST-02'
    content = multiple_sheets(HEAD, [other])
    data = preview(flow, content).json()
    assert data['can_confirm'] and data['new_count'] == 2
    assert [sheet['row_count'] for sheet in data['sheets']] == [1, 1]
    assert all(sheet['status'] == 'ready' for sheet in data['sheets'])
    assert confirm(flow, content, data)[0].json()['created'] == 2


def test_empty_sheet_is_reported_but_does_not_block(flow):
    content = multiple_sheets(None, [])
    data = preview(flow, content).json()
    assert data['can_confirm'] and len(data['sheets']) == 2
    assert data['sheets'][1]['status'] == 'empty'
    assert data['sheets'][1]['row_count'] == 0
    assert confirm(flow, content, data)[0].status_code == 200


def test_nonstandard_data_after_header_scan_limit_is_not_treated_as_empty(flow):
    content = multiple_sheets(None, [[None]] * 25 + [['不能静默漏读的排期记录']])
    data = preview(flow, content).json()
    assert not data['can_confirm']
    assert data['sheets'][1]['status'] == 'blocked'
    assert '七列' in data['sheets'][1]['message']
    assert confirm(flow, content, data)[0].status_code == 409
    assert count(flow, Source) == 0


def test_schedule_only_task_request_partial_issues_and_signatures_without_procurement(bridge):
    p=bridge;p.cutting_auth['user']=actor('order_receive','bom_write','plan_write','plan_publish','material_request','material_receive')
    v=preview(p,workbook()).json();r,_=confirm(p,workbook(),v)
    assert r.status_code==200,r.text
    identifier=r.json()['rows'][0]['line_id'];base=BASE+'/orders/'+identifier
    def read():return p.get(base,params={'factory_id':'huakang-c'}).json()
    o=read();r=p.post(base+'/receive',json=command(dispatch_id=o['dispatch_id']));assert r.status_code==200,r.text
    old=p.get(BASE+'/orders/line-1',params={'factory_id':'huakang-c'}).json()['current']['data']
    b=old['bom'];r=p.post(base+'/bom',json=command(expected_version=read()['current']['version'],bom_id=b['id'],bom_version=b['version'],target_sets=50,quantity_basis='合成100件按BOM核定50套'))
    assert r.status_code==200,r.text
    task=old['planning']['published']['tasks'][0]
    raw={k:v for k,v in task.items() if k in {'task_id','name','resource_id','resource_version','target_sets','date_basis','preparation_workdays','materials'}}|dict(days=[])
    r=p.post(base+'/plan',json=command(expected_version=read()['current']['version'],tasks=[raw]));assert r.status_code==200,r.text
    draft=read()['current']['data']['planning']['draft']['version']
    r=p.post(base+'/plan-publish',json=command(expected_version=read()['current']['version'],draft_version=draft));assert r.status_code==200,r.text
    assert read()['current']['data']['requisition'] is None
    published=read()['current']['data']['planning']['published']
    assert published['publication_kind']=='task_only' and not any(t['days'] for t in published['tasks'])
    assert not read()['current']['data']['planning'].get('baseline')
    before=warehouse_view(p);version=read()['current']['version']
    r=p.post(base+'/materials/request',json=command(expected_version=version,task_id=raw['task_id'],plan_version=published['version'],row=0,material_id='fabric-mat',material_revision=1,quantity='4',business_date='2026-10-10',mapping_basis='原物料规格颜色单位一致'))
    assert r.status_code==200,r.text
    request=r.json();assert warehouse_view(p)['stock']==before['stock']
    for _ in range(2):
        issued=warehouse_post(p,'ISSUE',original_id=request['id'],batch_id=p.stock_id,quantity='2',counterparty='R01')
        ledger=p.get(base+'/materials',params={'factory_id':'huakang-c'}).json()
        r=p.post(base+'/materials/receive',json=command(expected_version=ledger['revision'],original_id=issued['id'],quantity='2',business_date='2026-10-10'))
        assert r.status_code==200,r.text
    assert sum(float(s['quantity']) for s in warehouse_view(p)['stock'])==16
    final=p.get(base+'/materials',params={'factory_id':'huakang-c'}).json()['requests'][0]
    assert final['issued_quantity']=='4' and len(final['issues'])==2
