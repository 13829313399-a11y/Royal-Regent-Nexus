"""Workbook coordinates, permissions and save/export consistency on synthetic records."""
from collections import OrderedDict
from io import BytesIO
from uuid import uuid4

from fastapi import HTTPException
from lxml import html
from openpyxl import load_workbook
import pytest
import xlrd
from app.services import qc_report_workbook as workbooks
from app.services import qc_annual_excel, qc_daily_report, qc_monthly_templates as monthly, qc_monthly_excel
from app.services import qc_weekly_excel, qc_weekly_templates as weekly
from test_qc_approved_statistics import approval, transition, hashes
from test_qc_monthly_templates import issue, db, engine, isolated, ACTOR, DAY


def test_preview_wire_encoding_preserves_workbook_and_cache_headers():
    import gzip
    import json
    payload = {'sheets': [{'html': '<td>验货问题</td>' * 500}], 'cells': {'0:A1': {'version': 2}}}
    for accepted, compressed in [('br, gzip', True), ('gzip;q=0.2', True), ('gzip;q=0', False), ('', False)]:
        response = workbooks.preview_response(payload, accepted, {'Cache-Control':'no-store'})
        assert ('content-encoding' in response.headers) == compressed
        assert response.headers['vary'] == 'Accept-Encoding' and response.headers['cache-control'] == 'no-store'
        assert int(response.headers['content-length']) == len(response.body)
        assert json.loads(gzip.decompress(response.body) if compressed else response.body) == payload


def test_idle_visit_starts_one_engine_and_does_not_block_summary(monkeypatch):
    from threading import Event, Lock
    started, release = Event(), Event()
    calls = []
    def start(exe):
        calls.append(exe)
        started.set()
        assert release.wait(3)
    lock = Lock()
    monkeypatch.setattr(workbooks, '_render_lock', lock)
    monkeypatch.setattr(workbooks, '_warm_attempted', False)
    monkeypatch.setattr(workbooks, 'office_executable', lambda:'calc')
    monkeypatch.setattr(workbooks, 'start_worker', start)
    try:
        workbooks.warm_on_report_visit()
        assert started.wait(2)
        workbooks.warm_on_report_visit()
    finally:
        release.set()
    assert lock.acquire(timeout=2)
    lock.release()
    assert calls == ['calc']


def test_hot_preview_does_not_queue_behind_an_unrelated_conversion(db):
    from concurrent.futures import ThreadPoolExecutor
    issue(db, 1)
    first = workbooks.preview('huaxing', 'quality', DAY, '', True)
    assert first['sheets'] and first['cells']
    with ThreadPoolExecutor(max_workers=1) as pool:
        # A separate template is using Calc. A viewer can read the finished
        # preview immediately, with the current request's read-only cell map.
        with workbooks._render_lock:
            future = pool.submit(workbooks.preview, 'huaxing', 'quality', DAY, '', False)
            result = future.result(timeout=2)
        assert result['sheets'] == first['sheets'] and not result['cells']


def test_visible_catalog_and_versioned_edit(db):
    issue(db, 1)
    assert workbooks.KINDS == {'daily','detail','issues','orders','tracking','quality','annual-stats','annual-issues'}
    for kind in workbooks.KINDS:
        data = workbooks.projection('huaxing', kind, '2026-11-03', '')
        cells = workbooks.writable_cells(kind, data)
        if kind == 'daily':
            assert cells['0:G4']['field'].endswith(':traderQDate') and '0:I4' not in cells
        elif kind in ('issues', 'annual-issues'):
            assert cells['0:O7']['field'].endswith(':analysisReason') and '0:M7' not in cells
        elif kind == 'annual-stats':
            assert not cells  # This fixture has no FAIL rows in the selected view.
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
            if kind in ('quality','annual-stats') and i == 0:
                assert table.xpath('.//img[starts-with(@src,"data:image/")]')
            if kind in ('tracking','issues','annual-issues'):
                assert table.xpath('.//td[@data-addr="M7"]//img[@loading="lazy"][starts-with(@src,"api/report-workbook/photo?")]')
                assert 'data:image/' not in sheet['html']
        assert set(book['cells']) <= shown
        assert not workbooks.preview('huaxing', kind, '2026-11-03', '', False)['cells']


def test_engine_missing_and_timeout_use_same_editable_grid(db, monkeypatch):
    from subprocess import TimeoutExpired
    issue(db,1)
    monkeypatch.setattr(workbooks, '_cache', OrderedDict())
    monkeypatch.setattr(workbooks, '_try_native_at', 0)
    monkeypatch.setattr(workbooks, 'office_executable', lambda: 'engine')
    attempts=[]
    def timed_out(*args):
        attempts.append(1)
        raise TimeoutExpired('engine',8)
    monkeypatch.setattr(workbooks, 'render_native', timed_out)
    for kind in sorted(workbooks.KINDS):
        book = workbooks.preview('huaxing',kind,'2026-11-03','',True)
        assert book['previewMode']=='grid'
        shown=set()
        for i, sheet in enumerate(book['sheets']):
            table=html.fromstring(sheet['html'])
            shown.update(f'{i}:{c}' for c in table.xpath('.//td/@data-addr'))
            if kind in ('tracking','issues','annual-issues'):
                assert table.xpath('.//td[@data-addr="M7"]//img[@loading="lazy"][starts-with(@src,"api/report-workbook/photo?")]')
                assert 'data:image/' not in sheet['html']
        assert set(book['cells'])<=shown
        assert not workbooks.preview('huaxing',kind,'2026-11-03','',False)['cells']
    assert len(attempts)==1  # The failed engine does not block every template.
    monkeypatch.setattr(workbooks,'_try_native_at',0)
    monkeypatch.setattr(workbooks,'office_executable',lambda:None)
    assert workbooks.preview('huaxing','daily','2026-11-03','',True)['previewMode']=='grid'


def test_deferred_previews_use_approved_revision_and_export_keeps_photos(db, monkeypatch):
    from urllib.parse import urlsplit, parse_qs
    entry = issue(db, 1, photos=3)
    data = workbooks.projection('huaxing', 'tracking', DAY, '')
    with monkeypatch.context() as patch:
        patch.setattr(qc_monthly_excel, '_photo', lambda *a: pytest.fail('read image bytes before opening table'))
        sheets, _ = workbooks.render('huaxing', 'tracking', data)
    images = html.fromstring(sheets[0]['html']).xpath('.//td[@data-addr="M7"]//img')
    ids = []
    for image in images:
        params = parse_qs(urlsplit(image.get('src')).query)
        photo = params['photo'][0]
        ids.append(photo)
        assert params['entry'] == [entry['id']] and params['revision'] == [str(entry['revision'])]
        content, mime = qc_monthly_excel.approved_photo('huaxing', entry['id'], entry['revision'], photo)
        assert content and mime.startswith('image/')
    assert ids == [p['id'] for p in data['tables']['tracking'][0]['photos']]
    assert len(load_workbook(BytesIO(qc_monthly_excel.render(data,'tracking'))).active._images) == 3
    for factory, rev in [('huadeng', entry['revision']), ('huaxing', entry['revision'] - 1)]:
        with pytest.raises(HTTPException, match='409'):
            qc_monthly_excel.approved_photo(factory, entry['id'], rev, ids[0])
    transition(entry, 'revoke')
    with pytest.raises(HTTPException, match='409'):
        qc_monthly_excel.approved_photo('huaxing', entry['id'], entry['revision'], ids[0])


def save_request(cell, value, **changes):
    return {**{k:cell[k] for k in ('customerKey', 'field', 'writeRevision')},
            'value':value,'baseVersion':cell['version'],'requestKey':uuid4().hex,**changes}


def test_daily_annual_and_tracking_supplements_save_reload_and_export(db):
    from app.services import qc_inspection_sheet as sheet, qc_approved_statistics as stats
    problem=issue(db,1,result='FAIL')
    blank=transition(approval(db,2,result='FAIL'),'revoke')
    blank=sheet.save('huaxing',blank['id'],dict(revision=blank['revision'],result='FAIL',remark=''),ACTOR,review=True)
    blank=transition(blank)
    source=hashes()
    day='2026-11-03'
    def grid(kind, customer='', result='ALL'):
        return workbooks.writable_cells(kind,workbooks.projection('huaxing',kind,day,customer,result))
    def scoped(kind, value):
        return next(cell for cell in grid(kind).values() if cell['field'].endswith(value))
    def put(kind, body, customer=''):
        return workbooks.save_record('huaxing',ACTOR,kind,day,customer,'ALL',body)
    qdate=scoped('daily',f'{blank["id"]}:traderQDate')
    note=scoped('annual-stats',f'{blank["id"]}:remark')
    action=scoped('issues',f'{problem["id"]}:improvement')
    request=save_request(qdate,'2026-11-27')
    assert put('daily',request)==put('daily',request)
    assert scoped('daily',f'{blank["id"]}:traderQDate')['value']=='2026-11-27'
    current=qc_daily_report.report('huaxing',day)
    assert '2026-11-27' in [r['values'][6] for r in current['rows']]
    daily_excel=load_workbook(BytesIO(qc_daily_report.workbook(current))).active
    assert any(c.value=='2026-11-27' for c in daily_excel['G'])
    assert put('annual-stats',save_request(note,'年度补录'))['version']==1
    report=stats.report('huaxing',{'year':'2026','result':'ALL'},all_detail_rows=True)
    assert report['totals']['FAIL']==2
    assert any(c.value=='年度补录' for c in load_workbook(BytesIO(qc_annual_excel.workbook(report))).active['H'])
    assert scoped('daily',f'{blank["id"]}:remark')['value']=='年度补录'
    assert put('issues',save_request(action,'整改后复查'))['version']==1
    assert scoped('annual-issues',f'{problem["id"]}:improvement')['value']=='整改后复查'
    assert scoped('tracking',f'{problem["id"]}:improvement')['value']=='整改后复查'
    from app.services import qc_issue_reports
    tracked=qc_issue_reports.query('huaxing',day,'yearly')
    assert any(c.value=='整改后复查' for c in load_workbook(BytesIO(qc_monthly_excel.render(tracked,'issues','huaxing'))).active['P'])
    for bad,code in [
        (save_request(qdate,'不是日期'),422),
        (save_request(qdate,'2026-11-30'),409),  # Stale CAS.
        (save_request(note,'不得覆盖',field=f'detail:{problem["id"]}:remark'),409),
        (save_request(note,'跨范围',customerKey='f'*64),409),
    ]:
        with pytest.raises(HTTPException) as exc:
            put('daily',bad)
        assert exc.value.status_code==code
    assert all(hashes()[p]==h for p,h in source.items())
    transition(blank,'revoke')
    with pytest.raises(HTTPException) as exc:
        put('annual-stats', save_request(note,'不能写已反审核'))
    assert exc.value.status_code==409


def test_save_route_respects_current_session_and_factory_permission(monkeypatch, tmp_path):
    import test_molding_sample_api
    from test_molding_sample_api import make_client, login_as
    from test_qc_daily_report import DAY as report_day, EXAMPLES, isolated_upstream, seed
    from test_qc_department_gateway import grant_permission_override
    monkeypatch.setattr(test_molding_sample_api,'TEST_TMP_DIR',tmp_path/'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR',str(tmp_path/'companies'))
    monkeypatch.setenv('AUTHZ_MODE','enforce')
    with make_client(monkeypatch) as client:
        from app.services import qc_report_workbook as live_workbooks
        monkeypatch.setattr(live_workbooks,'office_executable',lambda:None)
        isolated_upstream(monkeypatch)
        login_as(client,'qc_inspector')
        health='/api/qc-department/huaxing/api/health'
        frame=client.get(health).json()['frame_url']
        seed(client,frame,EXAMPLES[:1])
        scope=dict(kind='daily',day=report_day,customer='')
        book=client.get(frame+'api/report-workbook',params=scope).json()
        assert book['previewMode']=='grid'
        body=save_request(book['cells']['0:G4'],'2026-11-19')
        endpoint='api/report-workbook/save'
        assert client.post(frame+endpoint,params=scope,json=body,headers={'sec-fetch-site':'cross-site'}).status_code==403
        saved=client.post(frame+endpoint,params=scope,json=body)
        assert saved.status_code==200, saved.text
        assert saved.json()['version']==1
        assert client.get(frame+'api/report-workbook',params=scope).json()['cells']['0:G4']['value']=='2026-11-19'
        records=client.get(frame+'api/inspection-summary/records').json()['items']
        assert len(records)==1
        dossier=client.get(frame+'api/inspection-dossier/records/'+records[0]['id']).json()
        supplements=dossier['reportSupplements']
        assert [row['value'] for row in supplements['items']]==['2026-11-19']
        actor=supplements['changes'][0]['actor']
        assert actor['id'] and actor['name'] and supplements['changes'][0]['before']==''
        grant_permission_override('qc_inspector','qc_inspection:result_write',effect='deny',factory_id='huaxing',department='qc')
        newframe=client.get(health).json()['frame_url']
        assert not client.get(newframe+'api/report-workbook',params=scope).json()['cells']
        assert client.post(newframe+endpoint,params=scope,json=body).status_code==403
        assert client.get(newframe+'api/inspection-dossier/records/'+records[0]['id']).status_code==200


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
