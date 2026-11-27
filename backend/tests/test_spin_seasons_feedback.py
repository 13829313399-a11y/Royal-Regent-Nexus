"""Synthetic regressions for page continuations and SEASONS reservation lanes."""
from copy import deepcopy
from openpyxl.comments import Comment
from openpyxl.styles import PatternFill
from openpyxl.worksheet.formula import ArrayFormula
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule, FormulaRule
from io import BytesIO

import openpyxl
import pytest

from app.services import customer_order_seasons_layout as layout
from app.services import customer_order_unified as unified
from app.services.huadeng_order_legacy.spin_po_parser import SpinPOParser
from app.services.huaxing_order_legacy import shixin_schedule as seasons


def test_spin_detail_continues_after_repeated_page_header():
    header = '''PURCHASE ORDER
NUMBER PAGE
4500999999 Page 2 of 3
Some new address never seen by parser
DATE BUYER
No ORDERED DESCRIPTION'''
    source = f'''10 120 PC 1099991
FIRST PRODUCT
{header}
CONTINUED DESCRIPTION
Sales Material: 6079991 2500 USD Per 04/15/2030 300
Material Group: 49991 1000 PC
Ultimate Consignee: SAMPLE CUSTOMER
Final Destination: USA
Sales Order: 3900001 Line Item: 11
Customer PO: 00001234
20 20 PC 1099992
SECOND PRODUCT
Sales Material: 6079992 3000 USD Per 04/16/2030 60
Material Group: 49992 1000 PC
Customer: SECOND CUSTOMER
Customer PO: 00005678
800001
Foil Film 20 Piece
TOTAL NET VALUE 360'''
    rows = SpinPOParser()._parse_lines(source)
    assert len(rows) == 2
    assert rows[0].description_en == 'FIRST PRODUCT\nCONTINUED DESCRIPTION'
    assert (rows[0].customer, rows[0].customer_po, rows[0].sales_order) == ('SAMPLE CUSTOMER', '00001234', '3900001')
    assert rows[0].qty == 120 and rows[0].unit_price_usd == 2.5
    assert rows[1].components == [dict(code='800001', description='Foil Film', qty=20, unit='Piece')]


def test_spin_converted_text_without_column_title_still_parses():
    rows = SpinPOParser()._parse_lines('PURCHASE ORDER\nNUMBER 4500999999\n10 120 PC 1099991\nFIRST PRODUCT\nSales Material: 6079991 2500 USD Per 04/15/2030 300\nMaterial Group: 49991 1000 PC')
    assert len(rows) == 1 and rows[0].description_en == 'FIRST PRODUCT'


@pytest.mark.parametrize('packing,expected', [('正常英文卡', '英文卡'), ('客卡', '客卡'), ('客彩盒', '客彩盒')])
def test_seasons_packaging_comes_from_product_clause(packing, expected):
    quantity, result = seasons._packing_from_block(
        f'1.正常生产\n2.{packing}\n3.0/12装\nPacking: Outer: 12PCS\n客吊牌产品用客人DATE CODE')
    assert (quantity, result) == ('12', expected)


def book():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for i, name in enumerate(layout.SHEETS):
        ws = wb.create_sheet(name)
        for col, header in enumerate(unified.ITEM_HEADERS if name == 'ITEM表' else unified.ORDER_HEADERS, 1):
            ws.cell(3, col, header)
        ws.cell(8 + i, 1, '预备单')
        ws.cell(12 + i, 1, '取消单')
        ws.cell(13 + i, 2, '保留取消单资料')
        ws['P1'] = 7.8
    return wb


def row(qf=False, quantity=100, po='MPO900001'):
    return dict(id=po, product_no='W90001', po_no='QF90000001' if qf else po,
                reference_no='QF90000001' if qf else 'ZE' + po[3:], contract_no='' if qf else 'ZE' + po[3:],
                order_type='QF预备单' if qf else '正式PO', _seasons_qf='QF90000001',
                production_no='QF90000001',
                _seasons_explicit_qf=not qf, quantity=quantity, units_per_carton=10,
                _huaxing_customer='seasons', issues=[], unit_price_hkd='' if qf else '2', packaging='英文卡')


def roundtrip(wb):
    out = BytesIO()
    wb.save(out)
    return openpyxl.load_workbook(BytesIO(out.getvalue()))


def test_qf_then_split_formal_moves_all_three_sheets_and_deducts_once():
    wb = book()
    layout.export_rows(wb, [row(True)])
    wb = roundtrip(wb)
    # A clerk's price and follow-up notes survive reservation conversion.
    order_qf = layout.entries(wb['接单表'])[0]['cell'].row
    wb['接单表'].cell(order_qf, 14, 9.5)
    wb['ITEM表'].cell(layout.entries(wb['ITEM表'])[0]['cell'].row, 30, '人工备注')
    layout.export_rows(wb, [row(False, 40)])
    wb = roundtrip(wb)
    for name in layout.SHEETS:
        entries = layout.entries(wb[name])
        assert [e['po'] for e in entries] == ['QF90000001', 'MPO900001']
        assert entries[0]['cell'].row + 1 == entries[1]['cell'].row
        assert entries[1]['cell'].row < layout.markers(wb[name])['预备单']
        assert any(c.value == '保留取消单资料' for c in wb[name]._cells.values())
    assert wb['ITEM表']['K4'].value == '=(100)-K5'
    assert wb['ITEM表']['AD4'].value == '人工备注'
    assert wb['接单表']['N4'].value == 9.5
    assert wb['接单表']['H4'].value == '=IF(LEN(\'ITEM表\'!I4)=0,"",\'ITEM表\'!I4)'
    assert wb['正单评审表']['N4'].value == '=IF(LEN(\'接单表\'!N4)=0,"",\'接单表\'!N4)'
    layout.export_rows(wb, [row(False, 40)])
    assert wb['ITEM表']['K4'].value == '=(100)-K5'
    assert len(layout.entries(wb['ITEM表'])) == 2
    layout.export_rows(wb, [row(False, 60, 'MPO900002')])
    assert wb['ITEM表']['K4'].value == '=((100)-K6)-K5'
    assert len(layout.entries(wb['ITEM表'])) == 3
    assert wb['接单表']['N4'].value == 9.5


def test_qf_reimport_repairs_wrong_reference_without_resetting_balance_or_price():
    wb = book()
    layout.export_rows(wb, [row(True)])
    for name in layout.SHEETS:
        e = layout.entries(wb[name])[0]
        wb[name].cell(e['cell'].row, layout.columns(wb[name])[0], 'QF90009999')
    item = layout.entries(wb['ITEM表'])[0]
    item['quantity'].value = '=100-40'
    layout.export_rows(wb, [row(True)])
    assert len(layout.entries(wb['ITEM表'])) == 1
    assert item['quantity'].value == '=100-40'
    for name in layout.SHEETS:
        assert layout.entries(wb[name])[0]['ref'] == 'QF90000001'


def test_no_explicit_qf_does_not_deduct_or_move_reservation():
    wb = book()
    layout.export_rows(wb, [row(True)])
    formal = row(False, 40)
    formal['_seasons_explicit_qf'] = False
    layout.export_rows(wb, [formal])
    qf = next(e for e in layout.entries(wb['ITEM表']) if e['qf'])
    assert qf['quantity'].value == 100
    assert qf['cell'].row > layout.markers(wb['ITEM表'])['预备单']
    assert any('不扣' in i['message'] for i in formal['issues'])


@pytest.mark.parametrize('quantities', [(40, 50), (50, 40)])
def test_conflicting_batch_versions_never_choose_a_deduction_by_file_order(quantities):
    wb = book()
    layout.export_rows(wb, [row(True)])
    layout.export_rows(wb, [row(False, quantity) for quantity in quantities])
    entries = layout.entries(wb['ITEM表'])
    assert len(entries) == 1 and entries[0]['quantity'].value == 100
    assert 'ITEM待补资料' in wb.sheetnames
    assert all(len(layout.entries(wb[name])) == 1 for name in layout.SHEETS)


def test_array_early_cross_sheet_reference_survives_move():
 w=book();layout.export_rows(w,[row(True)])
 reserve=layout.entries(w['正单评审表'])[0]['cell'].row
 w['正单评审表'].cell(reserve,27,ArrayFormula(ref=f'AA{reserve}',text="='ITEM表'!K4"))
 layout.export_rows(w,[row(False,40)])
 value=w['正单评审表']['AA4'].value
 assert isinstance(value,ArrayFormula)
 assert value.text=="='ITEM表'!K6" # inserting formal destination + formal row shifts original row4
 assert value.ref=='AA4'

def test_manual_style_comments_and_reference_structures_survive_move():
 w=book();layout.export_rows(w,[row(True)])
 q=layout.entries(w['ITEM表'])[0]['cell'].row
 w['ITEM表'].cell(q,30,f'=SUM(K{q}:L{q})')
 cell=w['ITEM表'].cell(q,31,'manual')
 cell.comment=Comment('manual note','clerk');cell.fill=PatternFill('solid',fgColor='AABBCC')
 cell.hyperlink='https://example.com/order'
 w.defined_names.add(DefinedName('ReserveQty',attr_text=f"'ITEM表'!$K${q}"))
 dv=DataValidation(type='decimal',operator='lessThan',formula1=f"='ITEM表'!$K${q}")
 w['接单表'].add_data_validation(dv);dv.add('V4')
 layout.export_rows(w,[row(False,40)])
 assert w['ITEM表']['AD4'].value=='=SUM(K4:L4)'
 assert w['ITEM表']['AE4'].value=='manual'
 assert w['ITEM表']['AE4'].comment.text=='manual note'
 assert w['ITEM表']['AE4'].fill.fgColor.rgb=='00AABBCC'
 assert w.defined_names['ReserveQty'].attr_text=="'ITEM表'!$K$4"
 assert dv.formula1=="='ITEM表'!$K$4"
 assert roundtrip(w)['ITEM表']['AE4'].hyperlink.target=='https://example.com/order'

def test_same_po_duplicate_exact_rows_and_reload_do_not_consume_twice():
 w=book();layout.export_rows(w,[row(True)])
 x=row(False,40)
 layout.export_rows(w,[x,deepcopy(x)])
 assert len(layout.entries(w['ITEM表']))==2
 assert w['ITEM表']['K4'].value=='=(100)-K5'
 w=roundtrip(w);layout.export_rows(w,[row(True),row(False,40)])
 assert len(layout.entries(w['ITEM表']))==2
 assert w['ITEM表']['K4'].value=='=(100)-K5'

def test_different_explicit_qf_versions_do_not_select_one():
 w=book();layout.export_rows(w,[row(True)])
 a,b=row(False,40),row(False,40);b['_seasons_qf']='QF99999999'
 layout.export_rows(w,[a,b])
 assert len(layout.entries(w['ITEM表']))==1
 assert layout.entries(w['ITEM表'])[0]['quantity'].value==100
 assert w['ITEM待补资料'].max_row==5

def test_cancelled_duplicate_is_never_added_or_consumed():
 w=book();layout.export_rows(w,[row(True)])
 for name in layout.SHEETS:
  s=w[name];r=layout.boundary(s)+1;ref,po,product,quantity=layout.columns(s)
  s.cell(r,ref,'ZE900001');s.cell(r,po,'MPO900001');s.cell(r,product,'W90001');s.cell(r,quantity,40)
 layout.export_rows(w,[row(False,40)])
 assert len(layout.entries(w['ITEM表']))==1
 assert layout.entries(w['ITEM表'])[0]['quantity'].value==100
 assert len(layout.entries(w['ITEM表'],active=False))==2


@pytest.mark.parametrize('changes', [dict(_seasons_qf='QF90000002'), dict(reference_no='ZECHANGED'),
                                    dict(unit_price_hkd='3'), dict(requested_ship_date='2030-05-02')])
def test_same_quantity_revision_is_retained_without_rededuction(changes):
    wb = book()
    original = row(False, 40)
    original['requested_ship_date'] = '2030-05-01'
    layout.export_rows(wb, [row(True), original])
    wb = roundtrip(wb)
    revised = deepcopy(original)
    revised.update(changes)
    layout.export_rows(wb, [revised])
    assert wb['ITEM表']['K4'].value == '=(100)-K5'
    assert len(layout.entries(wb['ITEM表'])) == 2
    assert wb['ITEM待补资料']['AD4'].value == float(revised['unit_price_hkd'])
    assert wb['ITEM待补资料']['AG4'].value == revised['_seasons_qf']


def test_identical_dated_po_after_save_is_noop_and_conditional_warning_moves():
    wb = book()
    layout.export_rows(wb, [row(True)])
    r = layout.entries(wb['ITEM表'])[0]['cell'].row
    wb['ITEM表'].conditional_formatting.add(f'K{r}', CellIsRule(operator='lessThan', formula=['0'], fill=PatternFill('solid', fgColor='FF0000')))
    wb['ITEM表'].conditional_formatting.add(f'K{r}', FormulaRule(formula=[f'$K${r}<0'], fill=PatternFill('solid', fgColor='FF0000')))
    formal = row(False, 40)
    formal['requested_ship_date'] = '2030-05-01'
    layout.export_rows(wb, [formal])
    wb = roundtrip(wb)
    layout.export_rows(wb, [formal])
    assert 'ITEM待补资料' not in wb.sheetnames
    assert any('K4' in cf.sqref for cf in wb['ITEM表'].conditional_formatting)
    assert any(rule.formula == ['$K$4<0'] for cf, rules in wb['ITEM表'].conditional_formatting._cf_rules.items() if 'K4' in cf.sqref for rule in rules)


def test_formal_qf_reference_can_touch_chinese_text():
    text = 'W90001 OC: ZE900001 SHIPDATE: 2030/12/18 100 2.00 0 200.00\nSAMPLE TOY\n本订单从QF90000001预备单中扣除\nPacking: Outer: 10PCS'
    records = seasons._parse_document_lines(text, {}, False, 'MPO900001.pdf')
    assert records[0]['_explicit_qf'] and records[0]['oqf_no'] == 'QF90000001'


def test_totals_separate_remaining_qf_from_formal_amounts():
    wb = book()
    ws = wb['正单评审表']
    ws['N7'], ws['N8'], ws['N11'], ws['N12'] = '合计：', '订单总计：', '合计：', '订单+预备单总计：'
    layout.export_rows(wb, [row(True), row(False, 40)])
    entries = layout.entries(ws)
    q, p = next(e for e in entries if e['qf']), next(e for e in entries if not e['qf'])
    values = {c.value: ws.cell(c.row, 15).value for c in ws._cells.values() if c.column == 14 and c.data_type != 'f' and isinstance(c.value, str)}
    assert values['订单总计：'] == f'=SUM(O{p["cell"].row})'
    assert values['订单+预备单总计：'] == f'=SUM(O{q["cell"].row},O{p["cell"].row})'


def test_changed_unconsumed_qf_is_retained_without_resetting_history():
    wb = book()
    layout.export_rows(wb, [row(True)])
    layout.export_rows(wb, [row(True, 120)])
    assert layout.entries(wb['ITEM表'])[0]['quantity'].value == 100
    assert wb['ITEM待补资料']['K4'].value == 120
