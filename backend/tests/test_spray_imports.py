from io import BytesIO
from pathlib import Path
import sys
from zipfile import ZipFile
import pytest
from fastapi import HTTPException
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.services.spray_imports import parse_source


def test_sparse_xfd_shared_formulas_dates_errors_and_empty_sheets():
    buffer=BytesIO()
    ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    with ZipFile(buffer,'w') as z:
        z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="历史明细" sheetId="1" r:id="r1"/><sheet name="空白证据" sheetId="2" state="hidden" r:id="r2"/></sheets></workbook>')
        z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Target="worksheets/sheet2.xml"/></Relationships>')
        z.writestr('xl/styles.xml',f'<styleSheet xmlns="{ns}"><cellXfs><xf numFmtId="0"/><xf numFmtId="14"/></cellXfs></styleSheet>')
        z.writestr('xl/worksheets/sheet1.xml',f'<worksheet xmlns="{ns}"><dimension ref="A1:XFD1048576"/><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>000935373-1</t></is></c><c r="B1" s="1"><v>46231</v></c><c r="C1"><f t="shared" si="0">B1*2</f><v>92462</v></c><c r="XFD1" t="e"><v>#REF!</v></c></row><row r="2"><c r="C2"><f t="shared" si="0"/><v>12</v></c><c r="D2"><f>C2+1</f></c></row></sheetData><mergeCells><mergeCell ref="A3:D3"/></mergeCells></worksheet>')
        z.writestr('xl/worksheets/sheet2.xml',f'<worksheet xmlns="{ns}"><sheetData/></worksheet>')
    kind,rows=parse_source(buffer.getvalue())
    assert kind=='OOXML' and len(rows)==4
    first=next(r for r in rows if r['row_number']==1)['cells']
    assert first['A1']['raw_value']=='000935373-1'
    assert first['B1']['normalized_value'].startswith('2026-07-28')
    assert first['XFD1']['validation_status']=='cached_error'
    second=next(r for r in rows if r['row_number']==2)['cells']
    assert second['C2']['raw_formula']=='B2*2'
    assert second['D2']['validation_status']=='missing_cache'
    assert rows[-1]['sheet']=='空白证据' and rows[-1]['cells']['表页说明']['raw_value']=='隐藏'


@pytest.mark.parametrize('content',[b'not a workbook',b'PKbroken'])
def test_invalid_source_is_actionable_validation_error(content):
    with pytest.raises(HTTPException) as error: parse_source(content)
    assert error.value.status_code==422
