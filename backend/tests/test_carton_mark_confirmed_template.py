import io
import json

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from pypdf import PdfReader

from app.services import carton_mark_confirmed_template as template
from app.services import carton_mark_flexible as flow
from app.services import carton_mark_workbench as workbench
from app.services import carton_mark_ai_pilot as pilot


def grid(product='TEST NEW PRODUCT', item='TEST-NEW-001', quantity=36, france=True, changes=None):
    book=Workbook();sheet=book.active;sheet.title='本单箱唛'
    values={'C2':'四个面都要印刷，ZURU LOGO + 箱唛内容按实际情况调整。'+('侧唛加法国地址' if france else ''),
        'C5':'Item:', 'E5':item, 'G10':'ZURU', 'C11':'Vendor name: ZURU INC',
        'C12':'Product name:', 'F12':product, 'C13':'Content:', 'F13':f'{quantity} PCS', 'G13':'/CTN',
        'C14':'GTIN:', 'C15':'10193052021172', 'I14':'Vendor product number:', 'I15':item,
        'C16':'Width/Length/Height:', 'I16':'Gross weight:', 'D17':'x', 'F17':'x', 'H17':'CM', 'J17':'KG',
        'M16':'尺寸和重量请根据实际填写 “宽*长*高”', 'M18':'条码印刷在外箱上，必须清晰可扫'}
    values.update(changes or {})
    for cell,value in values.items():sheet[cell]=value
    data=io.BytesIO();book.save(data);book.close()
    return dict(excel_file_name='unseen-customer.xlsx',excel_bytes=data.getvalue())


def read(original):
    return workbench.read(original,'test-owner',False)


def render(original,result,edits=None,**kwargs):
    return workbench.render(original,'test-owner',result['payload'],result['signature'],edits or {},[],
        'A4','landscape',include_sources=kwargs.pop('include_sources',False),**kwargs)


def test_unseen_native_grid_renders_new_values_in_confirmed_table_without_provider_or_old_data(monkeypatch):
    monkeypatch.setattr(pilot,'request_plan',lambda *a,**k:pytest.fail('No provider call for confirmed layout'))
    original=grid();inspection=workbench.inspect(original)
    assert inspection['confirmed_template']['id']=='zuru-vendor-grid-v1'
    result=read(original)
    assert result['mode']=='confirmed_template' and result['paper']=='A4'
    assert [p['face'] for p in result['records'][0]['panels']]==['front','side']
    data,pages,warnings=render(original,result)
    page=PdfReader(io.BytesIO(data)).pages[0];text=page.extract_text()
    assert pages==1 and page.mediabox.width>page.mediabox.height
    assert text.count('TEST NEW PRODUCT')==2 and text.count('36 PCS /CTN')==2
    assert 'TEST-NEW-001' in text and '100369TQ1-2024' not in text and '6946441304533' not in text
    assert 'care@zuru.com' in text and text.count('10193052021172')==4
    assert any('认证章未沿用' in x for x in warnings)


def test_actual_measurement_edit_is_validated_and_synchronized_to_both_faces_and_recorded():
    original=grid();result=read(original)
    data,pages,warnings=render(original,result,{'r0p0f5':'35 x 40 x 25 CM','r0p0f6':'5.5 KG'})
    text=PdfReader(io.BytesIO(data)).pages[0].extract_text()
    assert text.count('35 x 40 x 25 CM')==2 and text.count('5.5 KG')==2
    assert any('18cm' in w for w in warnings)
    full,count,_=render(original,result,{'r0p0f5':'35 x 40 x 25 CM'},include_sources=True)
    full_text='\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(full)).pages)
    assert count>1 and '本次明确补充' in full_text and '模型未明确落实' not in full_text
    for edits in [{'r0p0f5':'35 x 40 x 25'}, {'r0p0f6':'-2 KG'}, {'r0p0f5':'35 x 40 x 25 CM','r0p1f5':'36 x 40 x 25 CM'}]:
        with pytest.raises(HTTPException):render(original,result,edits)


def test_france_address_is_conditional_and_fixed_template_rejects_unimplemented_structure_edits():
    original=grid(france=False);result=read(original)
    pdf,_,_=render(original,result)
    assert 'care@zuru.com' not in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    for kwargs in [{'omissions':['r0p0f1']},{'additions':[{'record':0,'face':'front','value':'EXTRA'}]},
                   {'graphics':[{'record':0,'face':'front','logo':False,'symbols':[]}]}]:
        with pytest.raises(HTTPException,match='箱面结构固定'):render(original,result,**kwargs)
    for key in ['r0p0f3','r0p0f4','r0p0f7']:
        with pytest.raises(HTTPException):render(original,result,{key:'FORGED'})


def test_explicit_no_france_address_overrides_a_positive_keyword_match():
    original=grid(changes={'C2':'四个面都要印刷，ZURU LOGO。侧唛不要添加法国地址'})
    result=read(original);pdf,_,_=render(original,result)
    assert 'care@zuru.com' not in PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


@pytest.mark.parametrize('changes',[
    {'C15':'10193052021173'}, {'M18':'条码至少80mm宽60mm高'},
    {'M18':'barcode Code128'}, {'C2':'正唛两面，侧唛只有地址'},
    {'C20':'Net weight: 2 KG'}, {'F13':'0 PCS'}, {'I15':'OTHER-ITEM'},
    {'C20':'Battery count: 3'}, {'I16':'Gross weight: -2 KG'},
])
def test_different_or_ambiguous_layout_never_silently_reuses_profile_without_consent(monkeypatch,changes):
    monkeypatch.setattr(pilot,'request_plan',lambda *a,**k:pytest.fail('No consent'))
    original=grid(changes=changes)
    assert 'confirmed_template' not in workbench.inspect(original)
    with pytest.raises(HTTPException,match='明确同意'):read(original)


@pytest.mark.parametrize('value,expected',[
    ('30 x 40 x 23 CM','18cm'), ('40 x 40 x 23 CM','18cm'),
    ('40.1 x 40 x 33 CM','25cm'), ('50 x 40 x 33 CM','25cm'),
    ('50.1 x 40 x 42 CM','32cm'), ('29 x 40 x 23 CM','按比例'),
    ('40.1 x 40 x 32 CM','箱高低于'),
])
def test_logo_size_rule_uses_width_then_length_then_height_and_explicit_boundaries(value,expected):
    assert expected in template.logo_rule(value)


def test_template_token_keeps_owner_scope_source_integrity_and_profile_revision():
    original=grid();result=read(original)
    with pytest.raises(HTTPException):
        workbench.render(original,'another-owner',result['payload'],result['signature'],{},[],'A4','landscape')
    with pytest.raises(HTTPException):render(grid(product='DIFFERENT'),result)
    data=json.loads(result['payload']);data['confirmed_bindings'][0]['france_address']=False
    with pytest.raises(HTTPException):render(original,{**result,'payload':json.dumps(data)})


def test_http_page_inspect_read_render_does_not_require_ai_or_persist_business_records(monkeypatch):
    from test_molding_sample_api import make_client
    from test_carton_supplier_mark_check import prepare
    with make_client(monkeypatch) as client:
        prepare(client)
        original=grid()
        monkeypatch.setattr(pilot,'request_plan',lambda *a,**k:pytest.fail('No external call'))
        files={'excel':(original['excel_file_name'],original['excel_bytes'])}
        base='/api/carton-supplier/carton-mark/'
        inspected=client.post(base+'inspect-pdf-draft',files=files)
        assert inspected.status_code==200 and inspected.json()['confirmed_template']['id']=='zuru-vendor-grid-v1'
        response=client.post(base+'read-pdf-draft',files=files,data={'ai_consent':'false'})
        assert response.status_code==200,response.text
        result=response.json()
        pdf=client.post(base+'render-reviewed-draft',files=files,data={
            'review_payload':result['payload'],'review_signature':result['signature'],
            'paper':'A4','orientation':'landscape','include_sources':'false',
            'edits_json':json.dumps({'r0p0f5':'35 x 40 x 25 CM','r0p0f6':'5.5 KG'})})
        assert pdf.status_code==200,pdf.text
        assert pdf.headers['cache-control']=='private, no-store'
        assert 'TEST NEW PRODUCT' in PdfReader(io.BytesIO(pdf.content)).pages[0].extract_text()
        from app.db import SessionLocal
        from app.models.carton_mark import CartonMarkAsset,CartonMarkTemplate
        from sqlalchemy import select,func
        with SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(CartonMarkAsset))==1
            assert db.scalar(select(func.count()).select_from(CartonMarkTemplate))==0
