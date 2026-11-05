from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

from openpyxl import load_workbook

from test_molding_sample_api import login_as, make_client
from test_qc_department_gateway import install_upstream


DAY = '2026-11-05'
EXAMPLES = [
    ('示例洋行 A', 'DM-101', '回力车', '美国', '2400', 'PASS', '', '', ''),
    ('示例洋行 B', 'DM-102', '积木套装', '英国', '1800', 'FAIL', '外盒压痕', '返工后复验', '责任人 A'),
    ('示例洋行 A', 'DM-103', '模型车', '加拿大', '3600', 'PASS', '', '', ''),
    ('示例洋行 C', 'DM-104', '拼装玩具', '澳大利亚', '1200', 'PENDING', '检测报告待补', '补齐检测报告后确认结论', '责任人 C'),
    ('示例洋行 D', 'DM-105', '磁力拼图', '德国', '1600', 'PASS', '', '', ''),
    ('示例洋行 B', 'DM-106', '动物公仔', '英国', '2800', 'PASS', '', '', ''),
]

def isolated_upstream(patch):
    from app.api import qc_department
    install_upstream(patch)
    patch.setattr(qc_department, 'schedule_example', lambda factory: {'items': []})


def seed(client, base):
    def post(path, body):
        response = client.post(base + 'api/' + path, json=body)
        assert response.status_code == 200, response.text
        return response.json()

    for i, (customer, product, name, country, qty, result, problem, improvement, owner) in enumerate(EXAMPLES, 1):
        source = post('workflow/schedules', {'requestKey': uuid4().hex, 'row': dict(
            dateFrom=DAY, dateTo='', customer=customer, poNo=f'DEMO-PO-{i:03}', country=country,
            productNo=product, productName=name, quantity=qty, unitsPerCarton='10',
            cartonCount=str(int(qty)//10), production='隔离验收', agency='行验', customerPo='', remark='')})
        post('workflow/tasks', {'requestKey': uuid4().hex, 'items': [dict(
            sourceId=source['id'], sourceRevision=1, method='internal', batch='首验',
            plannedDate=DAY, plannedQuantity=qty)]})
        listing = client.get(base + 'api/inspection-sheet/entries')
        assert listing.status_code == 200, listing.text
        entries = listing.json()['items']
        entry = next(x for x in entries if x['sourceId'] == source['id'])
        path = 'inspection-sheet/entries/' + entry['id']
        entry = post(path + '/save', dict(revision=entry['revision'], result=result, remark='',
            inspectionProblem=problem, improvement=improvement, inspectionExecution={'actualDate': DAY}))
        entry = post(path + '/submit', dict(revision=entry['revision']))
        entry = post('inspection-sheet/review/entries/' + entry['id'] + '/save', dict(
            revision=entry['revision'], result=result, remark='', contractNo=f'000{i}', firstResponsible=owner,
            secondResponsible='责任人 B' if i == 2 else '', otherRemark='待复验' if i == 2 else ''))
        outcome = post('inspection-sheet/review/confirm', dict(requestKey=uuid4().hex,
            entries=[dict(id=entry['id'], revision=entry['revision'])]))
        assert outcome['succeeded'] == 1, outcome


def test_report_and_template_download(monkeypatch, tmp_path):
    import test_molding_sample_api
    from test_qc_department_gateway import grant_permission_override

    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path / 'main')
    monkeypatch.setenv('QC_DEPARTMENT_DATA_DIR', str(tmp_path / 'companies'))
    monkeypatch.setenv('AUTHZ_MODE', 'enforce')
    with make_client(monkeypatch) as client:
        isolated_upstream(monkeypatch)
        health = '/api/qc-department/huaxing/api/health'
        assert client.get(health).status_code == 401
        login_as(client, 'qc_inspector')
        base = client.get(health).json()['frame_url']
        seed(client, base)
        endpoint = base + 'api/daily-report'
        report = client.get(endpoint, params={'date': DAY}).json()
        assert (report['total'], report['passed'], report['failed'], report['other'], report['rate']) == (6,4,1,1,66.7)
        assert client.get(endpoint, params={'date': '2026-11-06'}).json()['total'] == 0
        assert client.get(endpoint, params={'date': '2026-11-99'}).status_code == 422
        assert client.get(endpoint, params={'date': DAY, 'company': 'hy-huadeng'}).status_code == 403
        export_url = endpoint + '/export'
        assert client.get(export_url, params={'date': DAY, 'revision': 'stale'}).status_code == 409
        params = {'date': DAY, 'revision': report['revision']}
        response = client.get(export_url, params=params)
        assert response.status_code == 200, response.text
        wb = load_workbook(BytesIO(response.content))
        assert wb.sheetnames == ['11.5']
        sheet = wb.active
        assert [cell.value for cell in sheet[3][:13]] == report['headers']
        assert {str(r) for r in sheet.merged_cells.ranges} == {'A1:M1','A2:M2'}
        for row, item in enumerate(report['rows'], 4):
            assert [sheet.cell(row,col).value for col in range(1,14)] == [
                None if value == '' else value for value in item['values']]
            assert sheet.cell(row,2).data_type == 's'
        from app.services.qc_daily_report import TEMPLATE, workbook
        with ZipFile(TEMPLATE) as original, ZipFile(BytesIO(response.content)) as output:
            assert original.namelist() == output.namelist()
        more = workbook({**report, 'rows': report['rows'] * 9})
        large = load_workbook(BytesIO(more)).active
        assert large['D57'].value == report['rows'][-1]['values'][3]
        grant_permission_override('qc_inspector', 'qc_inspection:report_export', effect='deny', factory_id='huaxing', department='qc')
        newbase = client.get(health).json()['frame_url']
        assert client.get(newbase+'api/daily-report/export', params=params).status_code == 403
