"""Current/effective engineering reference queries; isolated fixtures only."""
from copy import deepcopy
from types import SimpleNamespace
import json
import pytest
from sqlalchemy.orm import Session
from app.models.engineering_bom import EngineeringBom
from test_engineering_bom import client, material, bom, post, command, user, BASE
from test_engineering_bom_checks import state


def query(c, m, **params):
    return c.get(BASE + f"/materials/{m['id']}/bom-usage", params={
        'factory_id': 'huakang-c', 'expected_version': m['version'], **params})


def test_effective_latest_same_version_is_once_and_query_is_read_only(client):
    c = client; m = material(c); draft = post(c, '/boms', bom(m))
    post(c, f"/boms/{draft['id']}/approve", command(expected_version=1))
    c.engineering_auth['user'] = user(('read',)); before = state(c)
    response = query(c, m); assert response.status_code == 200, response.text
    report = response.json(); assert report['bom_count'] == 1 and report['checked_at']
    assert len(report['items']) == 1
    assert report['items'][0]['roles'] == ['LATEST', 'EFFECTIVE'] and report['items'][0]['bom_version'] == 2
    assert state(c) == before


def test_latest_removal_keeps_effective_reference_until_new_approval(client):
    c = client; m = material(c); old = post(c, '/boms', bom(m))
    approved = post(c, f"/boms/{old['id']}/approve", command(expected_version=1))
    other = post(c, '/materials', command(code='02-01-00001', group='02-01', name='另一物料', unit='码', department='手工'))
    other = post(c, f"/materials/{other['id']}/approve", command(expected_version=other['version']))
    data = deepcopy(approved['data']); data['nodes'][0].update(material_id=other['id'], material_version=other['version'])
    post(c, f"/boms/{old['id']}", command(expected_version=2, data=data))
    items = query(c, m).json()['items']
    assert len(items) == 1 and items[0]['bom_version'] == 2 and items[0]['roles'] == ['EFFECTIVE']
    assert query(c, other).json()['items'][0]['roles'] == ['LATEST']
    post(c, f"/boms/{old['id']}/approve", command(expected_version=3))
    assert query(c, m).json()['items'] == []  # Old v1/v2 still exist, but are no longer current references.


def test_each_bom_version_occurrence_and_pinned_attribute_remains_separate(client):
    c = client; m = material(c, attribute='自制'); payload = bom(m)
    root = payload['data']['nodes'][0]
    payload['data']['nodes'].append(dict(root, key='cut', parent='root', process='裁床', numerator='0.0297', denominator='2'))
    draft = post(c, '/boms', payload)
    approved = post(c, f"/boms/{draft['id']}/approve", command(expected_version=1))
    newer = post(c, '/materials', command(id=m['id'], code=m['code'], group='01-01', name='新物料名', unit='码', department='裁床', attribute='委外', expected_version=m['version']))
    newer = post(c, f"/materials/{m['id']}/approve", command(expected_version=newer['version']))
    data = deepcopy(approved['data']); data['nodes'].append(dict(data['nodes'][1], key='subcontract', material_version=newer['version'], process='车缝'))
    post(c, f"/boms/{draft['id']}", command(expected_version=2, data=data))
    report = query(c, newer).json(); items = report['items']
    assert report['bom_count'] == 1 and len(items) == 5
    assert [i['attribute'] for i in items] == ['自制', '自制', '委外', '自制', '自制']
    assert [i['name'] for i in items] == ['测试布', '测试布', '新物料名', '测试布', '测试布']
    assert items[1]['numerator'] == '0.0297' and items[1]['denominator'] == '2'
    assert [i['roles'] for i in items] == [['LATEST']] * 3 + [['EFFECTIVE']] * 2


def test_matches_stable_material_identity_not_unresolved_source_code(client):
    c = client; m = material(c); payload = bom()
    payload['data']['nodes'][0].update(source_code=m['code'], source_name=m['name'])
    post(c, '/boms', payload)
    result = query(c, m).json()
    assert result['items'] == [] and result['bom_count'] == 0


def test_multiple_boms_and_latest_unapproved_revision_only(client):
    c = client; m = material(c); draft = post(c, '/boms', bom(m))
    data = deepcopy(draft['data']); data['name'] = '新草稿'
    post(c, f"/boms/{draft['id']}", command(expected_version=1, data=data))
    data['item_no'] = '002'
    post(c, '/boms', command(data=data, copy_from=draft['id'], copy_version=2))
    result = query(c, m).json()
    assert result['bom_count'] == 2 and len(result['items']) == 2
    assert all(i['roles'] == ['LATEST'] and i['status'] == 'DRAFT' for i in result['items'])


def test_stale_material_rejected_and_inactive_material_still_has_references(client):
    c = client; m = material(c); post(c, '/boms', bom(m))
    inactive = post(c, f"/materials/{m['id']}/deactivate", command(expected_version=m['version']))
    assert query(c, m).status_code == 409
    assert len(query(c, inactive).json()['items']) == 1


def test_missing_current_bom_event_is_not_reported_as_zero_usage(client):
    c = client; m = material(c); draft = post(c, '/boms', bom(m))
    with Session(c.engine) as db:
        db.get(EngineeringBom, draft['id']).effective_version = 999
        db.commit()
    response = query(c, m)
    assert response.status_code == 409 and '无法完整查询' in response.json()['detail']


def test_missing_pinned_material_does_not_fall_back_to_current_master(client, monkeypatch):
    from app.services import engineering_material_usage as service
    c = client; m = material(c); post(c, '/boms', bom(m))
    def incomplete(raw):
        result = json.loads(raw)
        result['materials'] = {}
        return result
    monkeypatch.setattr(service, 'json', SimpleNamespace(loads=incomplete))
    assert query(c, m).status_code == 409


@pytest.mark.parametrize('account', [user(('material_write',)), user(factory='huakang-a'), user(department='pmc-warehouse')])
def test_read_scope_required(client, account):
    m = material(client); client.engineering_auth['user'] = account
    assert query(client, m).status_code == 403


def test_factory_identity_version_and_feature_gates(client, monkeypatch):
    from app.api import engineering_bom as api
    c = client; m = material(c)
    assert query(c, m, factory_id='huakang-a').status_code == 422
    assert query(c, m, expected_version=0).status_code == 422
    assert query(c, {'id': 'missing', 'version': 1}).status_code == 404
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', False)
    assert query(c, m).status_code == 503
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', True)
    monkeypatch.setattr(api.service, 'ready', lambda db: False)
    assert query(c, m).status_code == 503
