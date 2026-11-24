"""Synthetic original weekly layouts; private customer documents stay outside Git."""
from io import BytesIO
from copy import deepcopy
import pytest
import openpyxl
from app.services import customer_order_unified as service
from app.services import customer_order_zuru_native as native
from app.schemas.customer_order import CustomerOrderImportPreviewOut
from test_customer_order_zuru_unified import po_book, data


def original_book(item='9560-S001', role='orders'):
    w=openpyxl.Workbook(); s=w.active; s.title='Iteam表' if role=='item' else '9560接单表'
    s.append(['ZURU 原排期'])
    s.append(['第三方客户名称','来单日期','正单合同号','第三方客户 PO NO#','SKU','产品货号','产品名称','PO数量','外箱装箱数','总箱数','CRD','验货结果','单价HKD','金额HKD','备注'])
    s.append(['Example Retail','2026-01-01','4500000001','000001','4500000001-10',item,'玩具',40,4,'=H3/I3','2026-03-01','PASS',20,'=H3*M3','历史备注不继承'])
    return w


def arguments(factory='huakang-a', books=None):
    name,content=native.pack_references(books or [('原排期.xlsx', data(original_book()))])
    return dict(customer_code='zuru',factory_id=factory,received_date='2026-11-20',po_files=[('PO.xlsx',data(po_book()))],schedule_file_name=name,schedule_content=content)


@pytest.mark.parametrize('factory',['huakang-a','huaxing'])
def test_original_layout_and_copy_ready_values(factory):
    args=arguments(factory); source=args['schedule_content']
    p=service.create_unified_customer_preview(**args)
    CustomerOrderImportPreviewOut.model_validate(dict(p,preview_fingerprint='fixture'))
    assert p['target_template']=='ZURU_ORIGINAL_NEW_ORDER_SUMMARY_V1'
    output,_,resolved=service.export_unified_customer_schedule(**args)
    w=openpyxl.load_workbook(BytesIO(output))
    assert w['新单数据'].max_column==18 and w['新单数据'].max_row==3
    assert w['新单数据']['E2'].value=='000100'
    assert w['新单数据']['R2'].value==250
    s=w['9560接单表_新单']
    assert s['F2'].value=='9560-S001' and s['J2'].value==25
    assert s['L2'].value is s['M2'].value is s['N2'].value is None
    assert not any(c.data_type=='f' for sheet in w for row in sheet for c in row)
    assert args['schedule_content']==source


def test_multi_reference_bundle_deterministic_and_tracks_every_file():
    books=[('一.xlsx',data(original_book())),('二.xlsx',data(original_book(role='item')))]
    args=arguments(books=books)
    assert native.pack_references(books)==native.pack_references(books)
    assert native.unpack_references(args['schedule_file_name'],args['schedule_content'])==books
    output,_,p=service.export_unified_customer_schedule(**args)
    w=openpyxl.load_workbook(BytesIO(output));assert {'9560接单表_新单','Iteam表_新单'}<=set(w.sheetnames)
    changed=original_book(role='item');changed.active['O3']='新备注'
    p2=service.create_unified_customer_preview(**arguments(books=[books[0],('二.xlsx',data(changed))]))
    assert p['source_schedule_sha256'] != p2['source_schedule_sha256']


def test_ambiguity_and_unknown_family_remain_in_summary_without_guessing():
    b=original_book(); b.active['P2']='另一版额外列'
    args=arguments(books=[('1.xlsx',data(original_book())),('2.xlsx',data(b))])
    out,_,p=service.export_unified_customer_schedule(**args)
    w=openpyxl.load_workbook(BytesIO(out));assert w.sheetnames==['新单数据','复制说明']
    assert p['summary']['blocked']==0 and len(p['rows'])==2


def test_archive_is_only_history_and_duplicates_never_become_new_orders():
    b=original_book();s=b.copy_worksheet(b.active);s.title='已走货订单';s['C3']='4500999001';s['D3']='000100';s['E3']='4500999001-10';s['H3']=100
    out,_,p=service.export_unified_customer_schedule(**arguments(books=[('旧表.xlsx',data(b))]))
    w=openpyxl.load_workbook(BytesIO(out));assert w['新单数据'].max_row==2
    assert w['已有订单参考']['F2'].value=='4500999001-10'
    assert not any('已走货' in n for n in w.sheetnames)


def test_manual_change_recalculates_and_remaps_but_preserves_source_amount_without_edit():
    args=arguments();p=service.create_unified_customer_preview(**args);rid=p['rows'][0]['id']
    overrides=[dict(row_id=rid,issue_key='x',field='quantity',value='120'),dict(row_id=rid,issue_key='y',field='product_no',value='77903-S002')]
    out,_,p=service.export_unified_customer_schedule(**args,manual_overrides=overrides)
    w=openpyxl.load_workbook(BytesIO(out));assert w['新单数据']['L2'].value==30 and w['新单数据']['R2'].value==300
    assert w['9560接单表_新单'].max_row==2
    assert w['新单数据']['H2'].value is None


def test_formula_like_source_text_is_literal():
    b=po_book();b.active['E7']='@SUM(1)';b.active['AE15']='=1+1';b.active['AE15'].data_type='s'
    args=arguments();args['po_files']=[('PO.xlsx',data(b))]
    out,_,_=service.export_unified_customer_schedule(**args)
    w=openpyxl.load_workbook(BytesIO(out));assert w['新单数据']['E2'].data_type=='s'
    assert w['新单数据']['E2'].value=='=1+1'


def test_limits_and_factory_rejection():
    with pytest.raises(ValueError,match='最多10份'): native.pack_references([('x.xlsx',b'x')]*11)
    with pytest.raises(service.CustomerOrderUnifiedError): service.create_unified_customer_preview(**arguments(factory='huadeng'))


# Real API test runs isolated worker and export audit, without warehouse posting.
from test_customer_order_zuru_api import client, actor

def test_http_extra_reference_fingerprint_and_non_zuru_rejection(client):
    import importlib
    auth=importlib.import_module('app.services.auth')
    client.test_app.dependency_overrides[auth.get_current_user]=lambda: actor(factory='huaxing')
    fields=dict(factory_id='huaxing',received_date='2026-11-20')
    files=[('po_files',('PO.xlsx',data(po_book()))),('schedule_file',('one.xlsx',data(original_book()))),('schedule_files',('two.xlsx',data(original_book(role='item'))))]
    r=client.post('/api/customer-orders/zuru/preview-batch',data=fields,files=files)
    assert r.status_code==200,r.text
    p=r.json();assert p['warehouse_sync'] is None
    controls=dict(fields,confirmed='true',preview_fingerprint=p['preview_fingerprint'])
    r=client.post('/api/customer-orders/zuru/export-batch',data=controls,files=files)
    assert r.status_code==200,r.text
    r=client.post('/api/customer-orders/zuru/export-batch',data=controls,files=files[:-1])
    assert r.status_code==409,r.text


def test_unidentified_history_never_suppresses_new_line_and_archives_not_targets():
    book=original_book();book.active.title='9560 SMASHERS 接单表'
    book.active['C3']='4500999001';book.active['D3']=None;book.active['E3']=None
    archived=book.copy_worksheet(book.active);archived.title='已出货订单';archived['P2']='归档栏'
    out,_,p=service.export_unified_customer_schedule(**arguments(books=[('参考.xlsx',data(book))]))
    w=openpyxl.load_workbook(BytesIO(out));assert w['新单数据'].max_row==3
    assert '9560 SMASHERS 接单表_新单' in w.sheetnames
    assert not any('已出货' in name for name in w.sheetnames)


def test_real_http_manual_missing_name_and_date_remain_authorized(client):
    import json, importlib
    auth=importlib.import_module('app.services.auth')
    client.test_app.dependency_overrides[auth.get_current_user]=lambda: actor(factory='huaxing')
    po=po_book();po.active['U15']=None;po.active['X5']=None
    files=[('po_files',('PO.xlsx',data(po))),('schedule_file',('参考.xlsx',data(original_book())))]
    fields=dict(factory_id='huaxing',received_date='2026-11-20')
    response=client.post('/api/customer-orders/zuru/preview-batch',data=fields,files=files)
    assert response.status_code==200,response.text
    p=response.json();edits=[]
    for row in p['rows']:
        for issue in row['issues']:
            if issue.get('can_edit') and issue['field'] in {'product_name_zh','requested_ship_date'}:
                edits.append(dict(row_id=row['id'],issue_key=issue['skip_key'],field=issue['edit_field'],
                    value='补录品名' if issue['field']=='product_name_zh' else '2027-01-05'))
    assert len(edits)==2
    fields.update(confirmed='true',preview_fingerprint=p['preview_fingerprint'],manual_overrides=json.dumps(edits))
    response=client.post('/api/customer-orders/zuru/export-batch',data=fields,files=files)
    assert response.status_code==200,response.text
    w=openpyxl.load_workbook(BytesIO(response.content))
    assert w['新单数据']['H3'].value=='补录品名'
    assert str(w['新单数据']['M2'].value).startswith('2027-01-05')
