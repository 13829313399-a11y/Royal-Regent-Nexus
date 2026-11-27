from openpyxl import Workbook
import pytest
from app.services import qc_report_empty_cols as policy

@pytest.mark.parametrize('value,expected',[(None,True),('',True),('   ',True),(0,False),(0.,False),('0',False)])
def test_blank(value,expected):
    assert policy.blank(value) is expected
    row={'values':[value]*13}
    assert policy.hidden('daily',[row]) == (list(policy.ALLOWED['daily']) if expected else [])

def test_photo_formula_and_core_whitelist():
    row={'values':['']*19,'photos':[]}
    assert 13 in policy.hidden('tracking',[row])
    assert 12 not in policy.hidden('tracking',[row])
    row['photos']=[{'id':'img'}]
    assert 13 not in policy.hidden('tracking',[row])
    for qty,pack,expected in [(600,12,False),(0,12,False),('',12,True),(600,0,True),('无',12,True)]:
        row['values'][6:9]=[qty,pack,'']
        assert (9 in policy.hidden('quality-detail',[row])) == expected
    row['values'][6:9] = [600, 12, '   ']
    assert not policy.formula_boxes(row['values'])
    assert 9 in policy.hidden('quality-detail', [row])
    assert not policy.hidden('annual-stats',[row])

def test_group_header_relocated_with_style():
    s=Workbook().active;s.merge_cells('R5:U5');s['R5']='验货问题与责任'
    s['R5'].style='Headline 1';style=s['R5'].style_id
    row={'values':['']*21};row['values'][18]='已补';row['values'][20]='备注'
    policy.hide_sheet(s,'orders',[row])
    assert 'S5:U5' in map(str,s.merged_cells.ranges)
    assert s['S5'].value=='验货问题与责任' and s['S5'].style_id==style
