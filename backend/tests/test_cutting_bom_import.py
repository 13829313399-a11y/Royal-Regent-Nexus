from io import BytesIO

import openpyxl
import pytest

from app.services import cutting_bom_import as bom
from test_cutting_ops import BASE, client, command, create, state, user


def workbook(source='ENG-V1', change=None):
    book = openpyxl.load_workbook(BytesIO(bom.template()))
    book['产品与版本'].append(['BOM-001', '00012', '蓝色套装', 'A款', '蓝', source])
    book['裁片组成'].append(['P01', '左片', 2])
    book['裁片组成'].append(['P02', '右片', 1])
    book['物料用量'].append(['001', 'P01，P02', '0.125001', '米', '裁剪', '是', '主布'])
    if change:
        change(book)
    result = BytesIO()
    book.save(result)
    book.close()
    return result.getvalue()


def post(client, action, content, **fields):
    return client.post(f'{BASE}/bom-import/{action}', data={'factory_id': 'huakang-c', **fields},
                       files={'bom_file': ('engineering.xlsx', content)})


def preview(client, content):
    response = post(client, 'preview', content)
    assert response.status_code == 200, response.text
    return response.json()


def confirm_fields(result, **overrides):
    return command(expected_version=result['candidate']['expected_version'], fingerprint=result['fingerprint'],
                   file_sha256=result['file_sha256']) | overrides


def test_template_preview_draft_then_separately_authorized_publish(client):
    material = create(client)
    client.cutting_auth['user'] = user('read', 'bom_write', department='engineering')
    template = client.get(f'{BASE}/bom-import/template', params={'factory_id': 'huakang-c'})
    assert template.status_code == 200
    assert openpyxl.load_workbook(BytesIO(template.content)).sheetnames == list(bom.SHEETS)
    content = workbook()
    result = preview(client, content)
    assert result['issues'] == []
    assert result['candidate']['data']['item_no'] == '00012'
    assert result['candidate']['data']['requirements'][0]['material_version'] == material['version']
    assert result['candidate']['data']['requirements'][0]['quantity_per_set'] == '0.125001'
    assert client.get(f'{BASE}/masters', params={'factory_id':'huakang-c','kind':'bom'}).json()['total'] == 0
    fields = confirm_fields(result)
    imported = post(client, 'confirm', content, **fields)
    assert imported.status_code == 200, imported.text
    draft = imported.json()['record']
    assert draft['status'] == 'draft' and draft['version'] == 1
    assert post(client, 'confirm', content, **fields).json() == imported.json()
    assert preview(client, content)['candidate'] is None
    assert state(client, draft, 'published').status_code == 403
    client.cutting_auth['user'] = user('read', 'bom_publish', department='engineering')
    assert post(client, 'preview', content).status_code == 403
    published = state(client, draft, 'published')
    assert published.status_code == 200 and published.json()['status'] == 'published'
    assert published.json()['version'] == 2


@pytest.mark.parametrize('sheet,cell,value,fragment', [
    ('产品与版本', 'B1', '错误表头', '表头'),
    ('裁片组成', 'A3', 'P01', '重复'),
    ('裁片组成', 'C2', '=1+1', '公式'),
    ('物料用量', 'A2', '未知', '有效物料'),
    ('物料用量', 'B2', 'P01,P99', '适用部件'),
    ('物料用量', 'C2', '-1', '每套净用量'),
    ('物料用量', 'D2', '码', '单位'),
    ('物料用量', 'F2', '否', '裁剪必需物料'),
])
def test_preview_blocks_invalid_sheet_rows(client, sheet, cell, value, fragment):
    create(client)
    content = workbook(change=lambda book: setattr(book[sheet][cell], 'value', value))
    result = preview(client, content)
    assert result['candidate'] is result['fingerprint'] is None
    assert any(issue['sheet'] == sheet and fragment in issue['message'] for issue in result['issues'])


def test_extra_sheets_and_cross_factory_are_rejected(client):
    create(client)
    assert post(client, 'preview', workbook(change=lambda book: book.create_sheet('遗漏资料'))).status_code == 422
    assert post(client, 'preview', workbook(), factory_id='huakang-d').status_code == 422


def test_pinned_material_change_requires_preview_and_recovery_fences_request(client):
    material = create(client)
    content = workbook()
    result = preview(client, content)
    fields = confirm_fields(result)
    revision = command(kind='material', code=material['code'], data=material['data'] | {'name': '改版布料'}, expected_version=material['version'])
    assert client.put(f'{BASE}/masters/{material["id"]}', json=revision).status_code == 200
    assert post(client, 'confirm', content, **fields).status_code == 409
    fresh = preview(client, content)
    fields = confirm_fields(fresh)
    receipt = client.post(f'{BASE}/bom-import/recover', json={'command': fields | {'file_name':fresh['file_name']}})
    assert receipt.json() == {'state':'abandoned'}
    assert post(client, 'confirm', content, **fields).status_code == 409
    assert client.get(f'{BASE}/masters', params={'factory_id':'huakang-c','kind':'bom'}).json()['total'] == 0


def test_new_source_revises_published_version_and_preserves_history(client):
    create(client)
    initial = workbook()
    draft = post(client, 'confirm', initial, **confirm_fields(preview(client, initial))).json()['record']
    assert state(client, draft, 'published').status_code == 200
    amended = workbook('ENG-V2')
    result = preview(client, amended)
    assert result['candidate']['existing_id'] == draft['id']
    revised = post(client, 'confirm', amended, **confirm_fields(result)).json()['record']
    assert revised['version'] == 3 and revised['status'] == 'draft'
    assert preview(client, workbook('ENG-V3'))['candidate'] is None
    history = client.get(f'{BASE}/masters/{draft["id"]}/versions', params={'factory_id':'huakang-c'}).json()['data']
    assert [(row['version'], row['status'], row['data']['source_reference']) for row in history] == [
        (3, 'draft', 'ENG-V2'), (2, 'published', 'ENG-V1'), (1, 'draft', 'ENG-V1')]
