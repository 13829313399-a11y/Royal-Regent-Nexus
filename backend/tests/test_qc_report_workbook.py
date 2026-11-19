"""Workbook coordinates, permissions and save/export consistency on synthetic records."""
from lxml import html
import pytest
from app.services import qc_report_workbook as workbooks
from app.services import qc_monthly_templates as monthly, qc_weekly_excel
from test_qc_monthly_templates import issue, db, engine, isolated, ACTOR, DAY


def test_visible_catalog_and_versioned_edit(db):
    issue(db, 1)
    assert workbooks.KINDS == {'daily','detail','issues','orders','tracking','quality'}
    for kind in workbooks.KINDS:
        data = workbooks.projection('huaxing', kind, '2026-11-03', '')
        cells = workbooks.writable_cells(kind, data)
        if kind in ('daily', 'issues'):
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
            if kind in ('tracking','issues','quality') and i == 0:
                assert table.xpath('.//img[starts-with(@src,"data:image/")]')
        assert set(book['cells']) <= shown
        assert not workbooks.preview('huaxing', kind, '2026-11-03', '', False)['cells']
