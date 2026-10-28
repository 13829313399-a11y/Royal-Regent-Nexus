from pathlib import Path
from io import BytesIO
from types import SimpleNamespace
import json
import sys

import pytest
from openpyxl import load_workbook
from cutting_print_cases import print_cases, LONG_EVIDENCE
from app.services import cutting_export_workbook as workbooks
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_cutting_print_boundaries as runner


@pytest.mark.parametrize('label', list(print_cases()))
def test_boundary_workbooks_preserve_exact_source_and_units(label):
    report=print_cases()[label]
    before=json.dumps(report,ensure_ascii=False,sort_keys=True)
    payload, extension=workbooks.package(report,SimpleNamespace(id='test',display_name='合成验证'),
        lambda value,user:workbooks.render_workbook(value,user,'合成打印验收'))
    assert extension=='xlsx' and json.dumps(report,ensure_ascii=False,sort_keys=True)==before
    book=load_workbook(BytesIO(payload))
    try:
        for table in report['sheets']:
            assert [list(row) for row in list(book[table['name']].values)[2:]]==table['rows']
        cover=list(book['打印摘要'].values)[2:]
        if label=='settlement-zero':
            assert dict((r[0],r[1:]) for r in cover)['含税应付金额']==('HKD','0.00')
            assert book['结算汇总']['G3'].value==LONG_EVIDENCE
        else:
            assert {r[1] for r in cover}=={'CNY','HKD','USD'}
        if label=='period-currencies':assert book['同源版本差异']['E3'].value=='-5.00'
        if label=='wide-history':
            sheet=book['冻结来源索引']
            assert sheet['K3'].value==LONG_EVIDENCE and sheet['K4'].value=='=literal-evidence'
            assert sheet['K4'].data_type=='s'
            assert sheet.page_setup.scale==100 and sheet.print_title_cols=='$A:$A'
            assert sheet.col_breaks.count>0
        assert book['打印摘要'].page_setup.fitToWidth==1
        assert all(str(sheet.page_setup.paperSize)==sheet.PAPERSIZE_A3 and sheet.page_setup.orientation=='landscape'
                   for sheet in book)
    finally:book.close()


def test_generator_rejects_outside_output_without_creating_it(tmp_path,monkeypatch):
    monkeypatch.setattr(runner,'ROOT',tmp_path/'project')
    with pytest.raises(ValueError):runner.generate(tmp_path/'not-repo-evidence')
    assert not (tmp_path/'not-repo-evidence').exists()


def test_generator_never_overwrites_existing_output(tmp_path, monkeypatch):
    monkeypatch.setattr(runner,'ROOT',tmp_path)
    existing=tmp_path/'.tmp/retained';existing.mkdir(parents=True)
    (existing/'keep.txt').write_text('retained')
    with pytest.raises(FileExistsError):runner.generate(existing)
    assert (existing/'keep.txt').read_text()=='retained'


def test_generator_completes_all_cases_without_database():
    from uuid import uuid4
    output=runner.ROOT/'.tmp/cutting-print-boundaries-tests'/uuid4().hex
    result=runner.generate(output)
    assert result['status']=='passed_xlsx_readback'
    assert result['database_used'] is False and len(result['cases'])==4
    assert {row['case'] for row in result['cases']}==set(print_cases())
