"""Workbook coordinates, permissions and save/export consistency on synthetic records."""
from io import BytesIO

from lxml import html
from openpyxl import load_workbook
import pytest
import xlrd
from app.services import qc_report_workbook as workbooks
from app.services import qc_annual_excel, qc_daily_report, qc_monthly_templates as monthly, qc_monthly_excel
from app.services import qc_weekly_excel, qc_weekly_templates as weekly
from test_qc_approved_statistics import approval
from test_qc_monthly_templates import issue, db, engine, isolated, ACTOR, DAY


def test_visible_catalog_and_versioned_edit(db):
    issue(db, 1)
    assert workbooks.KINDS == {'daily','detail','issues','orders','tracking','quality','annual-stats','annual-issues'}
    for kind in workbooks.KINDS:
        data = workbooks.projection('huaxing', kind, '2026-11-03', '')
        cells = workbooks.writable_cells(kind, data)
        if kind in ('daily', 'issues', 'annual-stats', 'annual-issues'):
            assert not cells
        elif kind == 'detail':
            assert cells['0:E8']['field'] == 'returns'
        elif kind == 'quality':
            cell = cells['0:F7']
            assert cell['field'] == 'returns'
            monthly.save('huaxing', ACTOR, dict(customerKey=cell['customerKey'], field=cell['field'], value='1',
                date=DAY, sourceRevision=data['sourceRevision'], baseVersion=cell['version'],
                requestKey='workbook-preview-edit', template='overview', customer=''))
            fresh = workbooks.projection('huaxing', kind, DAY, '')
            assert workbooks.writable_cells(kind, fresh)['0:F7']['value'] == '1'
            assert qc_weekly_excel.versions(fresh)[cell['customerKey']]['returns'] == 1


def test_native_preview_and_readonly_cache(db):
    issue(db, 1)
    if not workbooks.office_executable():
        pytest.skip('Native Calc unavailable')
    for kind in sorted(workbooks.KINDS):
        book = workbooks.preview('huaxing', kind, '2026-11-03', '', True)
        assert book['sheets']
        shown = set()
        for i, sheet in enumerate(book['sheets']):
            table = html.fromstring(sheet['html'])
            shown.update(f'{i}:{addr}' for addr in table.xpath('.//td/@data-addr'))
            assert not table.xpath('.//script|.//a|.//*[@onclick]')
            if kind in ('tracking','issues','quality','annual-issues','annual-stats') and i == 0:
                assert table.xpath('.//img[starts-with(@src,"data:image/")]')
        assert set(book['cells']) <= shown
        assert not workbooks.preview('huaxing', kind, '2026-11-03', '', False)['cells']


def test_report_catalog_and_workbook_headings_follow_factory(db):
    day, factory = '2026-11-03', 'huadeng'
    issue(db, 1, customer='共用客户', result='FAIL')
    approval(db, 2, 'FAIL', factory=factory, customer='共用客户')
    for kind in workbooks.KINDS:
        east = workbooks.projection(factory, kind, day, '')
        west = workbooks.projection('huaxing', kind, day, '')
        assert (east.get('sourceRevision') or east['revision']) != (west.get('sourceRevision') or west['revision'])
        # An empty factory stays empty even with approved rows in two other factories.
        empty = workbooks.projection('huakang-d', kind, day, '')
        assert (empty['totals']['total'] if kind == 'annual-stats' else empty['total']) == 0

    daily = workbooks.projection(factory, 'daily', day, '')
    assert [row['values'][3] for row in daily['rows']] == ['ITEM-2']
    assert load_workbook(BytesIO(qc_daily_report.workbook(daily))).active['A1'].value == '华登'
    detail = weekly.query(factory, day)
    assert detail['tables']['footer'][0]['values'][0] == '华登'
    sheet = xlrd.open_workbook(file_contents=qc_weekly_excel.render(detail, 'detail')).sheet_by_index(0)
    assert any(str(sheet.cell_value(row, 0)).startswith('华登客户周验货汇总') for row in range(sheet.nrows))
    key = detail['customers'][0]['key']
    weekly.save(factory, ACTOR, dict(date=day, customerKey=key, field='weeklyRemark', value='仅华登',
        baseVersion=0, sourceRevision=detail['sourceRevision'], requestKey='factory-specific-weekly'))
    assert weekly.query(factory, day)['fields'][key]['weeklyRemark']['value'] == '仅华登'
    assert weekly.query('huaxing', day)['fields'][key]['weeklyRemark']['value'] == ''

    quality = workbooks.projection(factory, 'quality', day, '')
    assert load_workbook(BytesIO(qc_monthly_excel.render(quality, 'quality', factory))).active['A1'].value == '华登'
    annual = workbooks.projection(factory, 'annual-stats', day, '')
    assert load_workbook(BytesIO(qc_annual_excel.workbook(annual))).active['A1'].value == '华登 2026 年度验货统计表'
    if workbooks.office_executable():
        for kind in ('daily', 'detail', 'quality', 'annual-stats'):
            preview = workbooks.preview(factory, kind, day, '', False)
            headings = html.fromstring(preview['sheets'][0]['html']).text_content()
            assert '华登' in headings and '华兴' not in headings
