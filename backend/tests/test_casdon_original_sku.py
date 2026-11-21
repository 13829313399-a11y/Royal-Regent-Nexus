"""Casdon season notes must not change the source SKU."""
from io import BytesIO
import openpyxl
from openpyxl.styles import Font
from app.services import customer_order_unified as service
from test_customer_order_goliath import _pdf_document
from test_customer_order_casdon_workbook import fixture, content


def casdon_po():
    lines = ['Purchase Order No: 0000099991', 'Order Date 18/11/2026',
        'Shipment Date 23/03/2027', 'Your Reference UK', 'All Items are AW26 version',
        '1 30050 Test Kitchen 95030000 100 PCS 3.715 371.50',
        '2 30050.TAR001 Test Variant 95030000 20 PCS 2.00 40.00']
    commands = []
    for i, line in enumerate(lines):
        escaped = line.replace('\\','\\\\').replace('(','\\(').replace(')','\\)')
        commands.append(f'BT /F1 9 Tf 35 {800-i*18} Td ({escaped}) Tj ET')
    return _pdf_document(commands)


def test_original_sku_keeps_customer_suffix_season_separate_and_grouped():
    old = fixture()
    for name in old.sheetnames:
        col = 8 if name == "ITEM表" else 7
        for row in (4, 5): old[name].cell(row,col).font = Font(name="Arial",size=11,color="123456")
    params = dict(factory_id='huadeng', customer_code='casdon', received_date='2026-11-19',
        po_files=[('demo.pdf',casdon_po())], schedule_file_name='schedule.xlsx', schedule_content=content(old))
    preview = service.create_unified_customer_preview(**params)
    assert [r['product_no'] for r in preview['rows']] == ['30050','30050.TAR001']
    assert all(r['remarks'] == '原单版本：AW26' for r in preview['rows'])
    output, _, _ = service.export_unified_customer_schedule(**params)
    book = openpyxl.load_workbook(BytesIO(output))
    for name in book.sheetnames:
        s = book[name]; rc,pc = (5,8) if name=='ITEM表' else (4,7)
        found = [r for r in range(4,s.max_row+1) if s.cell(r,rc).value=='0000099991']
        assert s.cell(found[0],pc).value=='30050' and found[0]==6
        assert s.cell(found[1],pc).value=='30050.TAR001'
        assert s.cell(4,pc)._style==old[name].cell(4,pc)._style
        assert s.cell(6,pc)._style==old[name].cell(5,pc)._style
        assert any(s.cell(r,pc).value=='30050(AW26)' for r in range(4,s.max_row+1))
    assert book['ITEM表']['AD4'].value=='原始备注'
    assert book['ITEM表']['AD4'].comment.text=='业务人工填写'
    assert book['ITEM表']['K7'].value=='=SUM(K4:K6)'
    assert book['接单表']['P6'].value==3.715
    assert book['ITEM表']['AD6'].value == '原单版本：AW26'


def test_original_bracketed_sku_never_inherits_another_customer_article(monkeypatch):
    from app.services.huadeng_order_legacy.casdon_po_parser import CasdonPOParser
    old=fixture();old['ITEM表']['H4']='30050.TAR001(AW26)';old['ITEM表']['G4']='CASDON UK'
    monkeypatch.setattr(CasdonPOParser,'parse',lambda *a,**k:dict(po_number='99992',customer='CASDON UK',
        version='AW26',ship_date='2027-03-23',lines=[dict(item_code='30050(AW26)',qty=20,unit_price=2,total_usd=40)]))
    params=dict(factory_id='huadeng',customer_code='casdon',received_date='2026-11-19',
        po_files=[('source.xlsx',b'fixture')],schedule_file_name='old.xlsx',schedule_content=content(old))
    assert service.create_unified_customer_preview(**params)['rows'][0]['product_no']=='30050(AW26)'
