from copy import copy
from io import BytesIO
from types import SimpleNamespace

import openpyxl
import pytest
from openpyxl.comments import Comment
from openpyxl.styles import Font

from app.services import customer_order_casdon as service
from app.services import customer_order_unified as unified
from app.services.huadeng_order_legacy.casdon_po_parser import CasdonPOParser
from test_customer_order_ledger import engine, db, client, user
from app.services.auth import get_current_user


def fixture():
    w = openpyxl.Workbook(); w.remove(w.active)
    for name in service.SHEETS:
        s = w.create_sheet(name)
        headers = unified.ITEM_HEADERS if name == 'ITEM表' else unified.ORDER_HEADERS
        for c, v in enumerate(headers, 1): s.cell(3, c, v)
        for r, ref, product, qty in [(4,'A','30050',1000),(5,'B','30050',500),
                                     (7,'C','30050(AW26)',20),(11,'X','30050',100),(14,'D','30050',200)]:
            cols = (4,5,6,7,8,11) if name == 'ITEM表' else (3,4,5,6,7,10)
            for c,v in zip(cols,(ref,ref,ref,'NTI',product,qty)): s.cell(r,c,v)
        s['A10']='取消单';s['A12']='已走货订单'
        if name != 'ITEM表':
            s['P1']=7.75
            for r in (4,5,7,11,14):
                s.cell(r,14,4.3555); s.cell(r,15,f'=ROUND(J{r}*N{r},2)')
                s.cell(r,16,f'=IF(LEN(N{r})=0,"",ROUND($N{r}/$P$1,2))')
                s.cell(r,17,f'=ROUND(J{r}*P{r},2)')
            s['H4']='=INDEX(ITEM表!I4:I100,SUMPRODUCT((ITEM表!E4:E100=D4)*(ITEM表!H4:H100=G4)*(ROW(ITEM表!E4:E100)-MIN(ROW(ITEM表!E4:E100))+1)))'
        else:
            s['K6']='=SUM(K4:K5)';s['AD3']='备注';s['AD4']='原始备注'
            s['AD4'].comment=Comment('业务人工填写','业务员');s['AD4'].font=Font(color='123456')
            s['AD4'].hyperlink='https://example.com/order/A'
            s['AF3']='客PO';s['AF4']='0015286'
    return w


def content(w=None):
    w = w or fixture(); b=BytesIO(); w.save(b); return b.getvalue()


@pytest.mark.parametrize('reference,expected', [
    ('DEM [NTI] 15286 20FT','15286'), ('DEM [NTI] 00152 40FTHC','00152'),
    ('DAM [TARGET] 10001769117','10001769117'), ('DUK [AMAZON] 7CU324UE','7CU324UE'),
    ('DEM [NTI] 20FT 40FTHC',''), ('UK P1453','P1453'),
])
def test_customer_po_reference(reference,expected):
    assert CasdonPOParser._parse_reference(reference)[1] == expected


def test_money_precision_zero_and_manual_values():
    w=fixture(); s=w['ITEM表'];s['AE3']='单价HK';s['AE4']=0
    w['接单表']['P5']=0.77
    report=service.prepare_money(w)
    assert s['AE4'].value==0
    assert 'ROUND' not in w['接单表']['P4'].value
    assert w['接单表']['P5'].value==0.77
    assert len(report['money_columns'])==4
    assert len({c.value for c in s._cells.values() if c.row==3 and c.value in service.MONEY})==4
    assert service.prepare_money(w)['precision_formulas_fixed']==0
    assert s.cell(5,report['money_columns'][2]).value=='=IF(LEN(\'接单表\'!P5)=0,"",\'接单表\'!P5)'
    # Amount rounds at the end, not before multiplication.
    assert round(4.3555/7.75*1000,2)==562


def test_ambiguous_money_stays_blank():
    w=fixture();w['接单表']['D5']='A';w['接单表']['G5']='30050'
    report=service.prepare_money(w)
    assert any('第4行' in v for v in report['warnings'])
    assert all(w['ITEM表'].cell(4,c).value is None for c in report['money_columns'])


def test_grouped_export_scoped_full_product_independent_slots(monkeypatch):
    w=fixture();w['ITEM表']['K16384']=None
    rows=[dict(id=f'n{i}',reference_no=f'NEW{i}',contract_no=f'NEW{i}',product_no=p,
               customer_name='NTI',quantity='1000',unit_price_hkd='4.3555',issues=[],_regional_customer='casdon')
          for i,p in enumerate(['30050(AW26)','30050','NEWPRODUCT'])]
    monkeypatch.setattr(unified,'_create_customer_rows',lambda *a:(rows,[],'TEST'))
    out,_,_=unified.export_unified_customer_schedule(factory_id='huadeng',customer_code='casdon',
        received_date='2026-10-29',po_files=[('new.pdf',b'fake')],schedule_file_name='casdon.xlsx',schedule_content=content(w))
    result=openpyxl.load_workbook(BytesIO(out)); s=result['ITEM表']
    found={c.value:c.row for c in s._cells.values() if c.column==5 and str(c.value).startswith('NEW')}
    assert found['NEW1']==6
    assert s.cell(found['NEW0']-1,8).value=='30050(AW26)'
    assert found['NEW2'] < service.active_end(s)
    assert s['K7'].value=='=SUM(K4:K6)'
    for name in service.SHEETS[1:]:
        order=result[name];row=next(c.row for c in order._cells.values() if c.column==4 and c.value=='NEW1')
        assert order.cell(row,14).value == (4.3555 if name=='接单表' else f'=IF(LEN(\'接单表\'!N{row})=0,"",\'接单表\'!N{row})')
        assert 'ROUND' not in order.cell(row,16).value
        assert order.cell(row,10).value=="=IF(LEN('ITEM表'!K6)=0,\"\",'ITEM表'!K6)"
    assert all('NEW' not in str(c.value) for c in s._cells.values() if c.row>=service.active_end(s) and c.column==5)


def test_ship_restore_preserves_detail_and_reference():
    b=content(); v=service._casdon_preview('casdon.xlsx',b)
    assert '11' not in {r['id'] for r in v['rows']}
    out,n,rep,h=service._casdon_export('casdon.xlsx',b,v['fingerprint'],'ship',['4','5'])
    shipped=openpyxl.load_workbook(BytesIO(out));s=shipped['ITEM表']
    destinations=[r['to_row'] for r in rep['moves']]
    assert s.cell(destinations[0],30).value=='原始备注'
    assert s.cell(destinations[0],30).comment.text=='业务人工填写'
    assert s.cell(destinations[0],30).font.color.rgb=='00123456'
    assert s.cell(destinations[0],30).hyperlink.ref==f'AD{destinations[0]}'
    assert s['K6'].value==f'=SUM(K{destinations[0]},K{destinations[1]})'
    p=service._casdon_preview(n,out)
    restored,_,rep2,_=service._casdon_export(n,out,p['fingerprint'],'restore',list(map(str,destinations)))
    final=openpyxl.load_workbook(BytesIO(restored));fs=final['ITEM表']
    active={service.value(fs,r,5) for r,state in service.order_rows(fs) if state=='active'}
    assert {'A','B','C'} <= active
    assert len([r for r,state in service.order_rows(fs) if service.value(fs,r,5)=='A'])==1
    assert len(rep2['moves'])==2


@pytest.mark.parametrize('action,ids', [('ship',['11']),('restore',['4']),('ship',['4','4']),('ship',[]),('prepare',['4']),('ship',[4])])
def test_invalid_moves_rejected(action,ids):
    b=content()
    with pytest.raises(ValueError):service._casdon_export('casdon.xlsx',b,service.fingerprint(b),action,ids)


def test_stale_source_rejected():
    b=content()
    with pytest.raises(ValueError,match='已变化'):service._casdon_export('casdon.xlsx',b,'old','ship',['4'])


def test_reservation_type_with_product_is_not_a_section_marker():
    w=fixture();s=w['ITEM表'];s['B4']='备料单';s['E4']=None
    assert service.sections(s)==[(10,'cancelled'),(12,'shipped')]
    assert (5,'active') in service.order_rows(s)


def test_print_range_covers_money_and_new_archive_rows():
    w=fixture();w['ITEM表'].print_area='A1:AF14';b=content(w)
    out,_,report,_=service._casdon_export('casdon.xlsx',b,service.fingerprint(b),'ship',['4'])
    s=openpyxl.load_workbook(BytesIO(out))['ITEM表'];a=next(iter(s._print_area.ranges))
    assert a.max_row>=report['moves'][0]['to_row']
    assert a.max_col>=max(report['money_columns'])


def test_charge_amount_is_not_lost_without_quantity():
    w=fixture();service.write_prices(w,{'quantity':'','unit_price_hkd':'3875','amount_hkd':'3875'},4,4,4)
    assert w['接单表']['O4'].value==3875
    assert 'O4/$P$1' in w['接单表']['Q4'].value


def test_zero_price_does_not_become_missing():
    from app.services.huadeng_order_legacy import casdon_schedule as legacy
    values=legacy._compose_row({'po_number':'FREE','customer':'NTI'},
        {'item_code':'30050','qty':100,'unit_price':0,'total_usd':0},legacy.MasterIndex())
    assert values[legacy.COL['unit_hkd']]==0
    assert values[legacy.COL['total_hkd']]==0


def test_real_worker_preview_and_export(monkeypatch,tmp_path):
    import asyncio
    from app.services import customer_order_jobs as jobs
    monkeypatch.setattr(jobs,'LOCK_PATH',tmp_path/'job.lock')
    b=content()
    preview=asyncio.run(jobs.run_order_job(service._casdon_preview,'casdon.xlsx',b))
    assert preview['fingerprint']==service.fingerprint(b)
    out,_,report,_=asyncio.run(jobs.run_order_job(service._casdon_export,'casdon.xlsx',b,preview['fingerprint'],'ship',['4']))
    assert report['moves'][0]['original_row']==4
    assert openpyxl.load_workbook(BytesIO(out))['ITEM表'].cell(report['moves'][0]['to_row'],5).value=='A'


def test_endpoint_scope_confirm_stale_and_audit(client,monkeypatch):
    from app.api import customer_order_ledger as api
    client.test_app.dependency_overrides[get_current_user]=lambda:user(['read','write','export'],factory='huadeng')
    async def inline(func,*args,**kwargs):return func(*args)
    monkeypatch.setattr(api,'run_order_job',inline)
    audits=[]
    monkeypatch.setattr(api.mapping,'_record_export_audit',lambda *a,**kw:(audits.append(kw) or SimpleNamespace(id='audit-casdon')))
    b=content();files={'schedule_file':('casdon.xlsx',b)}
    url='/api/customer-order-ledger/schedule/casdon/'
    assert client.post(url+'preview?factory_id=huakang-a',files=files).status_code==403
    preview=client.post(url+'preview?factory_id=huadeng',files=files)
    assert preview.status_code==200
    data={'fingerprint':preview.json()['fingerprint'],'action':'ship','selections':'["4"]','reason':'已核对走货'}
    assert client.post(url+'export?factory_id=huadeng',files=files,data=data).status_code==400
    data['confirmed']='true'
    assert client.post(url+'export?factory_id=huadeng',files=files,data={**data,'fingerprint':'stale'}).status_code==409
    assert not audits
    result=client.post(url+'export?factory_id=huadeng',files=files,data=data)
    assert result.status_code==200 and result.headers['x-export-audit-id']=='audit-casdon'
    assert 'original_row' in audits[0]['confirmation_reason']
    assert audits[0]['preview']['source_schedule_sha256']
    client.test_app.dependency_overrides[get_current_user]=lambda:user(['read','export'],factory='huadeng')
    assert client.post(url+'export?factory_id=huadeng',files=files,data=data).status_code==403



def test_grouped_rows_do_not_inherit_public_manual_formulas():
    w = fixture()
    for name in service.SHEETS:
        sheet = w[name]
        sheet['AH3'] = '纸箱'
        sheet['AI3'] = '拆单来源'
        sheet['AH5'] = '=IF(1=1,"已确认","")'
        sheet['AI5'] = '=D5'
    slots = service.grouped_slots(w, [dict(contract_no='NEW', reference_no='NEW',
        po_no='NEW', customer_name='NTI', product_no='30050')])
    for name in service.SHEETS:
        sheet = w[name]
        row = slots[name][0]
        assert sheet.cell(row, 34).value is None
        assert sheet.cell(row, 35).value is None
        assert sheet['AH5'].value == '=IF(1=1,"已确认","")'
        assert sheet['AI5'].value == '=D5'


def test_workbook_without_calculation_properties_can_be_prepared():
    w = fixture()
    w.calculation = None
    source = content(w)
    output, _, _, _ = service._casdon_export(
        'casdon.xlsx', source, service.fingerprint(source), 'prepare', [])
    result = openpyxl.load_workbook(BytesIO(output))
    assert result.calculation.calcMode == 'auto'
    assert result.calculation.fullCalcOnLoad
