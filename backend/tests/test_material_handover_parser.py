import importlib
from io import BytesIO
from decimal import Decimal
import pytest
from test_material_handover import workbook


def test_merged_material_and_dye_lots_keep_independent_rows_and_numbered_rolls():
    from openpyxl import Workbook
    parser = importlib.import_module('app.services.material_handover_parser')
    book = Workbook(); sheet = book.active
    sheet.append(['物料编码', '物料名称', '缸号', '1', '2', '合计数量'])
    sheet.append(['000123', '同种布料', '1#', 200, 200, '400Y'])
    sheet.append([None, None, None, 152, None, '152Y'])
    sheet.append([None, None, '2#', 200, 30, '230Y'])
    sheet.merge_cells('A2:A4'); sheet.merge_cells('B2:B4'); sheet.merge_cells('C2:C3')
    output = BytesIO(); book.save(output)
    result = parser.parse('合并多缸.xlsx', output.getvalue())
    lines = result['data']['lines']
    assert [(r['item_code'], r['lot'], r['quantity'], r['unit']) for r in lines] == [
        ('000123', '1#', '400', '码'), ('000123', '1#', '152', '码'), ('000123', '2#', '230', '码')]
    assert [r['roll_quantities'] for r in lines] == ['200 / 200', '152', '200 / 30']
    assert not any('逐卷数量' in warning for warning in result['warnings'])


def test_ocr_total_spanning_into_roll_header_is_not_counted_as_an_extra_roll():
    from app.services.document_tools.document_ir import DocumentIR, Table, Cell
    parser = importlib.import_module('app.services.material_handover_parser')
    table = Table(id='grid', row_count=2, column_count=6, cells=[
        Cell(id='h0',row=0,column=0,raw_text='物料编码'), Cell(id='h1',row=0,column=1,raw_text='物料名称'),
        Cell(id='h2',row=0,column=2,raw_text='1'), Cell(id='h3',row=0,column=3,raw_text='2'),
        Cell(id='h4',row=0,column=4,raw_text='3'), Cell(id='h5',row=0,column=5,raw_text='合计数量'),
        Cell(id='code',row=1,column=0,raw_text='000123'),Cell(id='name',row=1,column=1,raw_text='布料'),
        Cell(id='r1',row=1,column=2,raw_text='200'),Cell(id='r2',row=1,column=3,raw_text='30'),
        Cell(id='total',row=1,column=4,colspan=2,raw_text='230Y')])
    result = parser.map_ir(DocumentIR(source_type='image',tables=[table]))
    assert result['data']['lines'][0]['roll_quantities'] == '200 / 30'
    assert result['data']['lines'][0]['quantity'] == '230'


def test_mixed_units_first_row_and_planned_quantity_are_preserved():
    parser = importlib.import_module('app.services.material_handover_parser')
    result = parser.parse('budget.xlsx', workbook(headers=['产品名称','单位','物料编码','物料名称','单位','计划用量','总数量'],
        rows=[['产品','套','00012','胶水','支','40','40'], ['产品','套','00013','辅料','Pcs','73','73']], title='制单预算用料'))
    assert [(v['item_code'],v['unit'],v['quantity']) for v in result['data']['lines']] == [('00012','支','40'),('00013','Pcs','73')]
    assert any('预算' in warning for warning in result['warnings'])


def test_merged_ocr_headers_roll_quantities_and_mismatch_require_review():
    parser = importlib.import_module('app.services.material_handover_parser')
    ir = importlib.import_module('app.services.document_tools.document_ir')
    cells = [ir.Cell(id='head',row=0,column=0,rowspan=2,colspan=2,raw_text='订单号/货号\n布料名称-色号'),
        ir.Cell(id='rolls',row=0,column=2,colspan=2,raw_text='明细数量'),
        ir.Cell(id='total',row=0,column=4,rowspan=2,raw_text='合计\n数量'),
        ir.Cell(id='rh',row=1,column=2,colspan=2,raw_text='1\n2')]
    for column,value in enumerate(['订单1 缸号：2#','01-01-10-00002 黑布','200','201','400Y']):
        cells.append(ir.Cell(id=f'd{column}',row=2,column=column,raw_text=value))
    result = parser.map_ir(ir.DocumentIR(source_type='image', tables=[ir.Table(id='photo',row_count=3,column_count=5,cells=cells)]))
    assert len(result['data']['lines']) == 1
    row = result['data']['lines'][0]
    assert row['quantity'] == '400' and row['unit'] == '码' and row['lot'] == '2#'
    assert row['roll_quantities'] == '200 / 201'
    assert any('合计' in warning for warning in result['warnings'])


def test_docx_native_table_without_supplier_template():
    from docx import Document
    parser = importlib.import_module('app.services.material_handover_parser')
    doc = Document(); doc.add_paragraph('领料单 单号：REQ-002 2026-07-18')
    table = doc.add_table(rows=2,cols=4)
    for i,value in enumerate(['物料名称','单位','数量','物料编码']): table.cell(0,i).text=value
    for i,value in enumerate(['黑布','码','12.5','00012']): table.cell(1,i).text=value
    out=BytesIO(); doc.save(out)
    result=parser.parse('车间自由格式.docx',out.getvalue())
    assert result['data']['kind'] == 'ISSUE' and result['data']['lines'][0]['quantity'] == '12.5'


def test_disposable_worker_extracts_office_without_business_database():
    files = importlib.import_module('app.services.material_handover_files')
    result=files.extract('任意.xlsx', workbook())
    assert result['engine'] == 'xlsx' and result['data']['lines'][0]['quantity'] == '40'


def test_file_and_numeric_boundaries():
    parser=importlib.import_module('app.services.material_handover_parser')
    error=importlib.import_module('app.services.document_tools.document_ir').ToolError
    for name,content in [('danger.xlsm',b'x'),('fake.xlsx',b'invalid'),('empty.pdf',b'')]:
        with pytest.raises(error): parser.validate_file(name,content)
    assert parser.numeric('1,000.125Y') == ('1000.125','码')
    assert parser.numeric('-12')[0] == '' and parser.numeric('1e10')[0] == ''


def test_native_pdf_table_extracts_without_fixed_template():
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    from reportlab.lib import colors
    parser=importlib.import_module('app.services.material_handover_parser')
    buffer=BytesIO(); document=SimpleDocTemplate(buffer)
    table=Table([['item code','description','qty','unit'],['00012','Black fabric','17.5','Y']],colWidths=[90,160,80,80])
    table.setStyle(TableStyle([('GRID',(0,0),(-1,-1),1,colors.black)]));document.build([table])
    result=parser.parse('different.pdf',buffer.getvalue())
    assert len(result['data']['lines']) == 1
    assert result['data']['lines'][0]['quantity']=='17.5' and result['data']['lines'][0]['unit']=='码'


def test_uncached_formula_stays_unknown_and_displayed_code_keeps_zeroes():
    from openpyxl import Workbook
    parser=importlib.import_module('app.services.material_handover_parser')
    book=Workbook();sheet=book.active
    sheet.append(['物料编码','物料名称','数量','单位'])
    sheet.append([12,'布料','=10+20','码']);sheet['A2'].number_format='00000'
    buffer=BytesIO();book.save(buffer)
    result=parser.parse('formulas.xlsx',buffer.getvalue())
    assert result['data']['lines'][0]['item_code']=='00012'
    assert result['data']['lines'][0]['quantity']=='' and result['warnings']


def test_optional_price_columns_preserve_zero_currency_and_price_unit():
    parser=importlib.import_module('app.services.material_handover_parser')
    result=parser.parse('价格不同布局.xlsx',workbook(headers=['物料名称','单价','数量','币种','物料编码','单位','计价单位','单价依据'],
        rows=[['赠送辅料','0','15','人民币','00012','Pcs','件','免费补货'],['另种辅料','2.30','20','港币','00013','码','米','原单报价']]))
    first,second=result['data']['lines']
    assert first['unit_price']=='0' and first['currency']=='CNY' and first['price_unit']=='件'
    assert second['unit_price']=='2.30' and second['currency']=='HKD' and second['price_unit']=='米'
    assert second['quantity']=='20' and second['unit']=='码'  # no price-unit conversion
