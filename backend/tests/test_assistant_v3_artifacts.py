"""Canonical native data, immutable notes, real file formats and live authorization."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree

import pytest
from openpyxl import load_workbook
from pypdf import PdfReader
from test_assistant_api import env, session, payload
from test_assistant_v2 import migrate


def sample():
    return json.loads((Path(__file__).parent / 'fixtures/assistant_v3/tool-result-example.json').read_text(encoding='utf-8'))


def test_one_immutable_dataset_drives_table_chart_and_export_without_unknown_zero():
    from app.services.assistant import artifact_data, artifacts
    value = sample()
    value['metrics']['unknown'] = dict(value=None, unit='piece', definition_id='open_quantity', status='unknown')
    value['rows'][0].update(reference_no='=HYPERLINK("https://evil.example")', open_quantity='123456789012345678.123')
    parts = [dict(type='business_snapshot', result=value)]
    first = artifact_data.datasets(parts)[0]
    assert 'resource_ref' not in first['rows'][0]
    assert first['metrics'][-1]['value'] is None
    assert all('unknown' not in chart['metric_keys'] for chart in first['charts'])
    assert all(chart['dataset_id'] == first['dataset_id'] for chart in first['charts'])
    assert len(first['charts']) == 2, 'Different units never share an axis'
    assert artifact_data.datasets(deepcopy(parts))[0] == first
    for kind in ('research', 'table', 'chart', 'checklist'):
        raw, _ = artifacts.render('人工说明不替换原值', kind, '中文核对成果', [], 'xlsx', [first])
        book = load_workbook(BytesIO(raw), data_only=False)
        cells = [cell for sheet in book for row in sheet for cell in row]
        assert any(cell.value == '123456789012345678.123' for cell in cells)
        attack = next(cell for cell in cells if str(cell.value).startswith('=HYPERLINK'))
        assert attack.data_type == 's'
        assert not any(cell.data_type == 'f' for cell in cells)
        assert not book._external_links
        assert '未知' in [cell.value for cell in cells]
        book.close()
        with ZipFile(BytesIO(raw)) as archive:
            charts = [name for name in archive.namelist() if name.startswith('xl/charts/chart') and name.endswith('.xml')]
            assert charts
            chart = ElementTree.fromstring(archive.read(charts[0]))
            assert chart.find('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}plotVisOnly').get('val') == '0'
    csv, _ = artifacts.render('人工说明', 'table', '中文核对成果', [], 'csv', [first])
    assert "'=HYPERLINK" in csv and '123456789012345678.123' in csv
    checklist, _ = artifacts.render('- [ ] 核对原记录', 'checklist', '中文核对成果', [], 'csv', [first])
    assert '核对原记录' in checklist and '900' in checklist and first['dataset_id'] in checklist


def tool_result_parts():
    value=sample()
    value.update(tool_name='list_customer_orders',run_id='cached-run')
    value['scope']['module_id']='customer-orders'
    value['freshness'].update(cache_hit=True,cache_created_at=value['retrieved_at'])
    sources=[dict(source_id=ref,kind='business',run_id='cached-run',tool_name='list_customer_orders',title='原订单快照') for ref in value['source_refs']]
    return [dict(type='evidence',run_id='cached-run',sources=sources),dict(type='tool_result',name='list_customer_orders',result=value)]


def test_registered_business_tool_result_keeps_immutable_dataset_and_deduplicates_prequery_copy():
    from app.services.assistant import artifact_data
    parts=tool_result_parts();before=deepcopy(parts)
    first=artifact_data.datasets(parts)
    assert len(first)==1 and first[0]['source_ids']==parts[1]['result']['source_refs']
    assert first[0]['as_of']==parts[1]['result']['as_of'] and parts==before
    parts.append(dict(type='business_snapshot',result=deepcopy(parts[1]['result'])))
    assert artifact_data.datasets(parts)==first


@pytest.mark.parametrize('boundary',['missing','other-run','other-tool','wrong-call','ineligible','unknown-module','help','foreign-pair','missing-evidence-run','bad-payload'])
def test_unregistered_or_mismatched_tool_payload_cannot_become_business_dataset(boundary):
    from app.services.assistant import artifact_data
    parts=tool_result_parts();source=parts[0]['sources'][0]
    if boundary=='missing':parts[0]['sources']=[]
    if boundary=='other-run':source['run_id']='foreign-run'
    if boundary=='other-tool':source['tool_name']='get_my_work'
    if boundary=='wrong-call':parts[1]['name']='get_my_work'
    if boundary=='ineligible':source['citation_eligible']=False
    if boundary=='unknown-module':parts[1]['result']['scope']['module_id']='unregistered'
    if boundary=='help':source['kind']='help'
    if boundary=='foreign-pair':
        source['run_id']='foreign-run';parts[1]['result']['run_id']='foreign-run'
    if boundary=='missing-evidence-run':parts[0].pop('run_id')
    if boundary=='bad-payload':parts[1]['result']=[]
    assert artifact_data.datasets(parts)==[]


def test_pdf_chinese_pagination_and_escaped_model_markup_are_real_pdf():
    from app.services.assistant import artifact_data, artifacts
    value = sample()
    value['rows'] = [dict(reference_no=f'合成订单{i:03d}', open_quantity=i, note='中文长条款，核对数量和单位。' * 12) for i in range(65)]
    value.update(total_count=65, returned_count=65)
    dataset = artifact_data.datasets([dict(type='business_snapshot', result=value)])[0]
    raw, media = artifacts.render('# 📊交付报告\n\n<script>alert(1)</script>\n\n| 核对 | 数量 |\n| --- | --- |\n| **样品** | 900 |',
        'chart', '曜灵合成订单核对', [], 'pdf', [dataset])
    assert media == 'application/pdf' and raw.startswith(b'%PDF-')
    reader = PdfReader(BytesIO(raw))
    assert len(reader.pages) > 2
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert all(value in text for value in ('曜灵合成订单核对', '合成订单064', '数量', '样品', '900', dataset['dataset_id']))
    assert '**' not in text and '📊' not in text
    assert reader.trailer['/Root'].get('/OpenAction') is None
    assert '/JavaScript' not in reader.trailer['/Root'].get('/Names', {})


def test_native_order_artifacts_keep_dataset_across_versions_and_recheck_every_format(env):
    from test_assistant_v3_orders import setup
    from test_work_center_api import actor
    from app.services.assistant import runtime
    from app.services import auth
    client, dbm, calls, patch, user = setup(env)
    migrate(dbm)
    patch.setattr(runtime, 'authenticate', lambda request: user)
    sid = session(client)
    request = payload(protocol_version=2, intent='my_work', web_search='off',
        page_context=dict(module_id='customer-orders', route_name='customer-order-center', factory_id='huakang-a'))
    request['text'] = '仅查询合成订单。'
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=request)
    assert 'event: run.completed' in response.text, response.text[-1500:]
    message = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    ids = []
    for kind in ('research', 'table', 'chart', 'checklist'):
        response = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(source_run_id=message['run_id'],
            title='授权订单成果', kind=kind, content='人工说明：不改变业务数据。'))
        assert response.status_code == 200, response.text
        saved = response.json()
        dataset = saved['datasets'][0]
        ids.append(saved['id'])
        assert dataset['total_count'] == 3
        assert next(m['value'] for m in dataset['metrics'] if m['key'] == 'remaining_quantity') == '900'
        assert all('SYN-O-B001' not in str(row) for row in dataset['rows'])
        assert 'HIDDEN-EXTENSION' not in json.dumps(saved)
        if kind == 'research':
            first = saved
        else:
            assert dataset == first['datasets'][0]
    aid = ids[0]
    path = '/api/assistant/artifacts/' + aid
    changed = client.post(path + '/versions', json=dict(base_revision=1, content='人工编辑成9999，并不改变原数据900。'))
    assert changed.status_code == 200 and changed.json()['edit_origin'] == 'manual_edit'
    assert changed.json()['datasets'] == first['datasets']
    assert client.post(path + '/versions', json=dict(base_revision=1, content='过时草稿')).status_code == 409
    assert client.get(path + '?revision=1').json()['content'] == first['content']
    for format in ('md', 'pdf', 'xlsx'):
        exported = client.get(path + '/export', params=dict(format=format, revision=2))
        assert exported.status_code == 200, exported.text[:200]
        if format == 'xlsx':
            book = load_workbook(BytesIO(exported.content))
            assert '900' in [cell.value for row in book['数据1'] for cell in row]
            book.close()
    assert len(calls) == 1, 'Saving, viewing and exporting never invoke a provider'
    denied = actor('alice', department='sales-business', permissions=())
    client.app.dependency_overrides[auth.get_current_user] = lambda: denied
    patch.setattr(runtime, 'authenticate', lambda request: denied)
    for ident in ids:
        for revision in (1, 2) if ident == aid else (1,):
            assert client.get('/api/assistant/artifacts/' + ident, params=dict(revision=revision)).status_code == 410
            for format in ('md', 'pdf', 'xlsx', 'csv'):
                response = client.get('/api/assistant/artifacts/' + ident + '/export', params=dict(revision=revision, format=format))
                assert response.status_code == 410
                assert set(response.json()) == {'detail'}
                assert response.json()['detail']['code'] == 'source_unavailable'
                assert 'SYN-O-A001' not in response.text


def test_export_rechecks_source_deletion_after_rendering_before_returning_private_bytes(env):
    from app.services.assistant import artifact_exports
    from app.models.assistant import AssistantSession
    client, dbm, calls, patch = env
    migrate(dbm)
    sid = session(client)
    response = client.post(f'/api/assistant/sessions/{sid}/messages', json=payload(protocol_version=2))
    assert 'event: run.completed' in response.text
    message = client.get(f'/api/assistant/sessions/{sid}/messages').json()['items'][-1]
    saved = client.post(f'/api/assistant/sessions/{sid}/artifacts', json=dict(source_run_id=message['run_id'],
        title='删除竞态', kind='markdown', content='PRIVATE-EXPORT-CONTENT')).json()
    original = artifact_exports.render
    def revoked_during_render(*args, **kwargs):
        value = original(*args, **kwargs)
        with dbm.SessionLocal() as db:
            db.get(AssistantSession, sid).deletion_state = 'deleted'
            db.commit()
        return value
    patch.setattr(artifact_exports, 'render', revoked_during_render)
    response = client.get('/api/assistant/artifacts/' + saved['id'] + '/export?format=pdf')
    assert response.status_code == 410
    assert 'PRIVATE-EXPORT-CONTENT' not in response.text and not response.content.startswith(b'%PDF-')
