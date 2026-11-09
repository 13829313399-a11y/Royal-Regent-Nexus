from copy import deepcopy
from io import BytesIO
import struct
import xlrd
from xlrd.compdoc import CompDoc
import pytest
from fastapi import HTTPException
from app.services import qc_weekly_templates as weekly, qc_weekly_excel as excel

def fixture(count=120):
    data = dict(date='2026-11-05', dateFrom='2026-11-02', dateTo='2026-11-08', customer='',
                customers=[], fields={}, sourceRevision='a'*64, total=count, scheduleCount=0,
                templates=deepcopy(weekly.TEMPLATES), tables=dict(detail=[],group=[],internal=[],footer=[]),totals={})
    for n in range(count):
        key=f'{n:064x}'; name=f'验收客户{n:04}'
        data['customers'].append(dict(key=key,label=name,name=name,code=str(n)))
        data['fields'][key]={f:dict(value='',version=0) for f in weekly.FIELDS}
        detail=[n+1,'2026-11-05',name,f'CONTRACT-{n:04}','英国',f'ITEM-{n:04}','中文产品名称与完整字段验收',100,'10','10','PASS','有','生产部门','验货机构','长文本问题：包装压痕，需要复检。'*12,'第一责任人','第二责任人',f'DETAIL-END-{n:04}']
        data['tables']['detail'].append(dict(id=str(n),values=detail))
        common=['华兴',name,1,'0','0.0%','退货原因长文本，按客户核对。'*8,'香港跟客']
        data['tables']['group'].append(dict(id=key,values=common+[f'GROUP-END-{n:04}']))
        data['tables']['footer'].append(dict(id=key,values=common+['返工&A0D原样保留',f'FOOTER-END-{n:04}']))
        data['tables']['internal'].append(dict(id=key,values=[name,1,'0','100.0%',common[5],'第一/二责任人','处理明细：已安排复检。'*8,f'INTERNAL-END-{n:04}']))
    for kind in ['group','internal']:
        spec=next(t for t in data['templates'] if t['id']==kind)
        data['totals'][kind]=weekly._totals(spec['headers'],data['tables'][kind])
    return data



def records(content):
    data=CompDoc(content).get_named_stream('Workbook'); offset=0; result=[]
    while offset+4<=len(data):
        opcode,size=struct.unpack_from('<HH',data,offset)
        result.append((opcode,data[offset+4:offset+4+size]));offset+=4+size
    return result


@pytest.mark.parametrize('kind',['detail','group','internal'])
@pytest.mark.parametrize('count',[1,220])
def test_original_template_fields_styles_dynamic_rows_formulas_and_totals(kind,count):
    data=fixture(count)
    data['tables']['detail'][0]['values'][3]='0000123'
    data['tables']['detail'][0]['values'][-1]='=HYPERLINK("https://example.invalid")'
    content=excel.render(data,kind)
    book=xlrd.open_workbook(file_contents=content,formatting_info=True);assert book.nsheets==1
    sheet=book.sheet_by_index(0)
    source=xlrd.open_workbook(excel.TEMPLATE_DIR/(kind+'.xls'),formatting_info=True);base=source.sheet_by_index(0)
    assert sheet.row_values(1)==base.row_values(1)
    for col in range(base.ncols):
        assert sheet.colinfo_map[col].width==base.colinfo_map[col].width
        actual=book.xf_list[sheet.cell_xf_index(1,col)];expected=source.xf_list[base.cell_xf_index(1,col)]
        assert actual.border.__dict__==expected.border.__dict__
        a=book.font_list[actual.font_index];b=source.font_list[expected.font_index]
        assert (a.name,a.height,a.bold)==(b.name,b.height,b.bold)
        assert book.xf_list[sheet.cell_xf_index(2,col)].alignment.text_wrapped
    assert sheet.nrows==count*2+7 if kind=='detail' else sheet.nrows==count+3
    values=[cell.value for row in sheet.get_rows() for cell in row]
    for n in range(count):
        mark=f'{kind.upper()}-END-{n:04}'
        if kind=='detail' and n==0:continue
        assert mark in values
    assert '合计' in values
    assert sheet.cell_value(sheet.nrows-1,3 if kind=='detail' else 2 if kind=='group' else 1)==count
    assert sheet.cell_value(sheet.nrows-1,7 if kind=='detail' else 4 if kind=='group' else 3)==(1.0 if kind=='internal' else 0.0)
    formulas=[r for op,r in records(content) if op==0x06]
    assert len(formulas)==count+3
    assert all(struct.unpack_from('<H',r,14)[0]&3==3 for r in formulas)
    if kind=='detail':
        assert sheet.cell(2,3).ctype==xlrd.XL_CELL_TEXT and sheet.cell_value(2,3)=='0000123'
        assert sheet.cell(2,17).ctype==xlrd.XL_CELL_TEXT
        assert sheet.cell(2,1).ctype==xlrd.XL_CELL_DATE
        assert book.format_map[book.xf_list[sheet.cell_xf_index(2,1)].format_key].format_str=='m.d'
        assert book.xf_list[sheet.cell_xf_index(2,17)].border.bottom_line_style
        assert [sheet.cell_value(count+5,c) for c in excel.FOOTER_COLUMNS]==weekly.TEMPLATES[0]['summaryHeaders']
    assert not any(cell.ctype==xlrd.XL_CELL_ERROR for row in sheet.get_rows() for cell in row)


def test_blank_zero_rates_safe_literal_and_tamper(monkeypatch,tmp_path):
    data=fixture(2);data['tables']['internal'][0]['values'][2]=''
    sheet=xlrd.open_workbook(file_contents=excel.render(data,'internal')).sheet_by_index(0)
    assert sheet.cell_value(2,3)=='' and sheet.cell_value(3,3)==1
    assert sheet.cell_value(4,2)=='待补全' and sheet.cell_value(4,3)==''
    with pytest.raises(HTTPException) as exc:excel.render(fixture(0),'group')
    assert exc.value.status_code==409
    (tmp_path/'group.xls').write_bytes(b'wrong file')
    monkeypatch.setattr(excel,'TEMPLATE_DIR',tmp_path)
    with pytest.raises(HTTPException) as exc:excel.render(data,'group')
    assert exc.value.status_code==503


def test_versions_scope_expiry_no_business_writes(monkeypatch,tmp_path):
    data=fixture(2)
    monkeypatch.setattr(excel.settings,'qc_department_data_dir',str(tmp_path))
    from pydantic import SecretStr
    monkeypatch.setattr(excel.settings,'qc_department_gateway_token',SecretStr('weekly-excel-test-token'*3))
    monkeypatch.setattr(weekly,'query',lambda factory,day,customer:deepcopy(data))
    body=dict(date=data['date'],customer='',template='group',sourceRevision=data['sourceRevision'],versions=excel.versions(data))
    out=excel.prepare('huaxing','huaxing:actor-a',body);token=out['url'].split('/')[-1]
    content,filename=excel.download('huaxing:actor-a',token)
    assert xlrd.open_workbook(file_contents=content).nsheets==1 and filename==out['filename']
    with pytest.raises(HTTPException) as exc:excel.download('huaxing:actor-b',token)
    assert exc.value.status_code==404
    data['fields'][data['customers'][0]['key']]['returns']['version']=1
    with pytest.raises(HTTPException) as exc:excel.prepare('huaxing','huaxing:actor-a',body)
    assert exc.value.status_code==409
    assert {p.suffix for p in tmp_path.rglob('*') if p.is_file()}=={'.xls'}
    monkeypatch.setattr(excel.time,'time',lambda:9999999999)
    with pytest.raises(HTTPException) as exc:excel.download('huaxing:actor-a',token)
    assert exc.value.status_code==410


def test_sanitized_templates_contain_only_structure():
    for spec in weekly.TEMPLATES:
        book=xlrd.open_workbook(excel.TEMPLATE_DIR/(spec['id']+'.xls'))
        assert book.nsheets==1
        allowed=set(spec['headers']+spec.get('summaryHeaders',[])+[spec['title'],'华兴客户周验货汇总','合计',''])
        assert all(cell.value in allowed for row in book.sheet_by_index(0).get_rows() for cell in row)
