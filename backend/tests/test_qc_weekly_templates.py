"""Isolated approved records; never write the user's inspection database."""
from uuid import uuid4
import sqlite3
import pytest
from fastapi import HTTPException
from app.services import qc_weekly_templates as weekly, qc_daily_report as daily
from test_customer_order_ledger import engine, db
from test_qc_approved_statistics import approval, transition, hashes, isolated
from test_qc_workflow import ACTOR

DAY = '2026-11-05'


def payload(data, field='returns', value='1', customer=None):
    customer = customer or data['customers'][0]['key']
    return dict(date=DAY, customerKey=customer, field=field, value=value,
                baseVersion=data['fields'][customer][field]['version'],
                sourceRevision=data['sourceRevision'], requestKey=uuid4().hex)


def test_empty_read_does_not_initialize_database():
    before = hashes()
    data = weekly.query('huaxing', DAY)
    assert data['total'] == 0 and data['totals']['group'][1:4] == ['合计', 0, 0]
    assert hashes() == before and not weekly._path().exists()


def test_population_mapping_dates_and_distinct_customer_identity(db):
    approval(db, 1, code='A', actual='2026-11-04')
    approval(db, 2, result='FAIL', code='A')
    approval(db, 3, result='LG', code='B')
    approval(db, 4, code='A', actual='2026-10-30')
    approval(db, 5, flag='testData')
    approval(db, 6, factory='huadeng')
    before = hashes()
    data = weekly.query('huaxing', DAY)
    assert data['total'] == daily.report('huaxing', DAY, 'weekly')['total'] == 3
    assert data['scheduleCount'] == 2
    assert len({r['id'] for r in data['tables']['detail']}) == 3
    assert len(data['customers']) == 2  # same name, distinct customer code
    assert [r['values'][2] for r in data['tables']['group']] == [2, 1]
    assert all(r['values'][3:5] == ['', ''] for r in data['tables']['group'])
    assert data['totals']['group'][2:5] == [3, '待补全', '']
    row = data['tables']['detail'][0]['values']
    assert len(row) == 18 and row[3] == '' and row[7:10] == [100, '10', '10']
    key = data['customers'][0]['key']
    assert weekly.query('huaxing', DAY, key)['total'] == 2
    assert hashes() == before


def test_shared_supplements_totals_idempotency_and_record_immutability(db):
    approval(db, 1); approval(db, 2, result='FAIL')
    data = weekly.query('huaxing', DAY); before = hashes()
    body = payload(data)
    first = weekly.save('huaxing', ACTOR, body)
    assert weekly.save('huaxing', ACTOR, body) == first
    data = weekly.query('huaxing', DAY)
    assert data['tables']['group'][0]['values'][3:5] == ['1', '50.0%']
    assert 'internal' not in data['tables']
    assert data['tables']['footer'][0]['values'][3:5] == ['1', '50.0%']
    assert data['totals']['group'][2:5] == [2, 1, '50.0%']
    assert 'internal' not in data['totals']
    weekly.save('huaxing', ACTOR, payload(data, 'weeklyRemark', '人工备注\n完整保留'))
    again = weekly.query('huaxing', DAY)
    assert all(again['tables'][name][0]['values'][-1] == '人工备注\n完整保留' for name in ('group','footer'))
    assert weekly.query('huaxing', '2026-11-12')['total'] == 0
    after = hashes()
    assert all(after[path] == digest for path, digest in before.items())
    with sqlite3.connect(weekly._path()) as conn:
        assert conn.execute('SELECT COUNT(*) FROM changes').fetchone()[0] == 2
        assert conn.execute('SELECT COUNT(*) FROM writes').fetchone()[0] == 2


def test_compare_and_swap_source_change_and_reappearance_preserve_manual_values(db):
    entry = approval(db, 1)
    old = weekly.query('huaxing', DAY)
    weekly.save('huaxing', ACTOR, payload(old, 'weeklyRemark', '原备注'))
    with pytest.raises(HTTPException) as exc:
        weekly.save('huaxing', ACTOR, payload(old, 'weeklyRemark', '另一个人'))
    assert exc.value.status_code == 409 and exc.value.detail['current']['value'] == '原备注'
    entry = transition(entry, 'revoke')
    assert weekly.query('huaxing', DAY)['total'] == 0
    with pytest.raises(HTTPException) as exc:
        weekly.save('huaxing', ACTOR, payload(old))
    assert exc.value.detail['code'] == 'source_changed'
    transition(entry)
    fresh = weekly.query('huaxing', DAY)
    assert fresh['tables']['group'][0]['values'][-1] == '原备注'
    approval(db, 2)
    assert weekly.query('huaxing', DAY)['tables']['group'][0]['values'][2] == 2
    assert weekly.query('huaxing', DAY)['tables']['group'][0]['values'][-1] == '原备注'


@pytest.mark.parametrize('change', [dict(field='contractNo'), dict(field=[]), dict(value='-1'),
    dict(value='1.5'), dict(value=1), dict(baseVersion=True), dict(date=[]), dict(factory='huadeng')])
def test_invalid_or_record_level_mutations_rejected(db, change):
    approval(db, 1)
    body = {**payload(weekly.query('huaxing', DAY)), **change}
    with pytest.raises(HTTPException) as exc: weekly.save('huaxing', ACTOR, body)
    assert exc.value.status_code == 422
    assert not weekly._path().exists()


def test_other_factory_never_reads_huaxing_data():
    with pytest.raises(HTTPException) as exc: weekly.query('huadeng', DAY)
    assert exc.value.status_code == 404


def test_http_mapping_permission_factory_and_persistence(monkeypatch, tmp_path):
    import test_molding_sample_api
    from test_molding_sample_api import make_client, login_as
    from test_qc_daily_report import isolated_upstream, seed
    from test_qc_department_gateway import grant_permission_override
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path / 'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR', str(tmp_path / 'http-companies'))
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    with make_client(monkeypatch) as client:
        isolated_upstream(monkeypatch)
        health = '/api/qc-department/huaxing/api/health'
        assert client.get(health).status_code == 401
        login_as(client, 'qc_inspector')
        base = client.get(health).json()['frame_url']; seed(client, base)
        url = base + 'api/weekly-templates'
        response = client.get(url, params={'date':DAY}); assert response.status_code == 200, response.text
        data = response.json(); assert data['canEdit'] is True and data['total'] == 6
        assert data['tables']['detail'][0]['values'][3] == '0001'
        assert client.get(url, params={'date':DAY,'company':'hy-huadeng'}).status_code == 403
        assert client.get(url, params=[('date',DAY),('date',DAY)]).status_code == 422
        assert client.post(url+'/save', json=payload(data), headers={'sec-fetch-site':'cross-site'}).status_code == 403
        body = payload(data,'handling','测试处理')
        assert client.post(url+'/save', json=body).status_code == 200
        assert client.post(url+'/save', json=body).json()['version'] == 1
        assert client.get(url, params={'date':DAY}).json()['fields'][body['customerKey']]['handling']['value'] == '测试处理'
        assert client.get(base+'qc-weekly-templates.js').status_code == 200
        from app.services import qc_weekly_excel as active_excel
        from pydantic import SecretStr
        monkeypatch.setattr(active_excel.settings,'qc_department_gateway_token',SecretStr('isolated-weekly-export-token'*2))
        data=client.get(url,params={'date':DAY}).json()
        for kind in ['detail','group']:
            export=dict(date=DAY,customer='',template=kind,sourceRevision=data['sourceRevision'],versions=active_excel.versions(data))
            assert client.post(url+'/excel',json=export,headers={'sec-fetch-site':'cross-site'}).status_code==403
            prepared=client.post(url+'/excel',json=export)
            assert prepared.status_code==200,prepared.text
            download=client.get(base+prepared.json()['url'])
            assert download.status_code==200 and download.content.startswith(bytes.fromhex('d0cf11e0a1b11ae1'))
            assert download.headers['content-type']==active_excel.MIME
            assert '2026-11-02_2026-11-08' in download.headers['content-disposition']
            assert client.post(url+'/excel',json={**export,'sourceRevision':'f'*64}).status_code==409
        grant_permission_override('qc_inspector','qc_inspection:result_write',effect='deny',factory_id='huaxing',department='qc')
        newbase=client.get(health).json()['frame_url']
        assert client.get(newbase+'api/weekly-templates', params={'date':DAY}).json()['canEdit'] is False
        assert client.post(newbase+'api/weekly-templates/save', json=body).status_code == 403
        assert client.post(newbase+'api/weekly-templates/excel',json=export).status_code==200
        grant_permission_override('qc_inspector','qc_inspection:report_export',effect='deny',factory_id='huaxing',department='qc')
        newbase=client.get(health).json()['frame_url']
        assert client.get(newbase+'api/weekly-templates',params={'date':DAY}).json()['canExport'] is False
        assert client.post(newbase+'api/weekly-templates/excel',json=export).status_code==403
        assert client.get(newbase+prepared.json()['url']).status_code==403


def test_blank_report_fields_save_per_entry_and_export_without_rewriting_approvals(db):
    import xlrd
    from app.services import qc_weekly_excel as excel

    approval(db, 1, code='A')
    approval(db, 2, code='A')
    approval(db, 3, code='B')
    before = hashes()
    data = weekly.query('huaxing', DAY)
    first, second, other = data['tables']['detail']
    contract = first['editableFields'][3]
    assert second['editableFields'][3] != contract
    assert 0 not in first['editableFields'] and 5 not in first['editableFields']

    weekly.save('huaxing', ACTOR, payload(data, contract, '000123'))
    weekly.save('huaxing', ACTOR, payload(data, 'responsible', '周报跟进人'))
    locked = f"detail:{first['id']}:productNo"
    for change in ({'field': locked}, {'customerKey': other['customerKey']}):
        with pytest.raises(HTTPException) as exc:
            weekly.save('huaxing', ACTOR, {**payload(data, contract, '覆盖'), **change})
        assert exc.value.status_code == 422

    fresh = weekly.query('huaxing', DAY)
    assert fresh['tables']['detail'][0]['values'][3] == '000123'
    assert fresh['tables']['detail'][1]['values'][3] == ''
    assert fresh['fields'][fresh['customers'][0]['key']]['responsible']['value']=='周报跟进人' # retained archival supplement
    assert all(hashes()[path] == digest for path, digest in before.items())
    output = xlrd.open_workbook(file_contents=excel.render(fresh, 'detail'))
    assert output.sheet_by_index(0).cell_value(2, 3) == '000123'
