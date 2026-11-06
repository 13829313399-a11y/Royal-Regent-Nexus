"""Immutable engineering version comparison; isolated databases only."""
from copy import deepcopy
from fastapi import HTTPException
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_engineering_bom import client, material, bom, post, command, user, BASE
from app.models.engineering_bom import EngineeringEvent


def tree(c):
    m = material(c, attribute='自制', specification='旧规格', color='白')
    body = bom(m); root = body['data']['nodes'][0]
    body['data']['nodes'] += [dict(root, key='a', parent='root', numerator='2', process='裁床'),
                             dict(root, key='b', parent='root', numerator='3', process='车缝'),
                             dict(root, key='leaf', parent='a', numerator='0.0297', denominator='2', process='手工')]
    first = post(c, '/boms', body)
    approved = post(c, f"/boms/{first['id']}/approve", command(expected_version=1))
    return m, first, approved


def request(c, identity, old, new):
    return c.get(BASE + f'/boms/{identity}/comparison', params={'factory_id': 'huakang-c', 'from_version': old, 'to_version': new})


def test_hierarchy_and_inherited_usage_use_frozen_versions_without_writes(client):
    c = client; _, _, old = tree(c)
    data = deepcopy(old['data']); data['name'] = '新版成品'; data['nodes'][2]['numerator'] = '4'; data['nodes'][3]['parent'] = 'b'
    newer = post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    c.engineering_auth['user'] = user(('read',))
    with Session(c.engine) as db: history = list(db.scalars(select(EngineeringEvent.result_json)))
    response = request(c, old['id'], 2, 3); assert response.status_code == 200, response.text
    result = response.json(); rows = {r['key']: r for r in result['rows']}
    assert result['from_status'] == 'APPROVED' and result['to_status'] == 'DRAFT'
    assert result['header'] == [dict(field='name', label='BOM 名称', before='测试成品', after='新版成品')]
    assert {c['field'] for c in rows['leaf']['changes']} >= {'parent', 'path', 'cumulative'}
    assert rows['leaf']['before']['path_keys'] == ['root', 'a', 'leaf']
    assert rows['leaf']['after']['path_keys'] == ['root', 'b', 'leaf']
    assert rows['leaf']['before']['cumulative'] == '297/10000' and rows['leaf']['after']['cumulative'] == '297/5000'
    assert result['unchanged_count'] == 2
    with Session(c.engine) as db: assert list(db.scalars(select(EngineeringEvent.result_json))) == history
    c.engineering_auth['user'] = user()
    # A still newer version must not silently replace either selected historical version.
    data['nodes'][2]['numerator'] = '5'
    post(c, f"/boms/{old['id']}", command(expected_version=newer['version'], data=data))
    assert request(c, old['id'], 2, 3).json() == result


def test_material_snapshot_attribute_changes_never_merge_same_code_occurrences(client):
    c = client; m, _, old = tree(c)
    revised = post(c, '/materials', command(id=m['id'], code=m['code'], group='01-01', name=m['name'], unit='码',
        department='车缝', attribute='委外', specification='新规格', color='蓝', expected_version=m['version']))
    current = post(c, f"/materials/{m['id']}/approve", command(expected_version=revised['version']))
    data = deepcopy(old['data']); data['nodes'][3]['material_version'] = current['version']
    post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    result = request(c, old['id'], 2, 3).json()
    assert len(result['rows']) == 1 and result['unchanged_count'] == 3
    leaf = result['rows'][0]
    assert leaf['key'] == 'leaf' and leaf['before']['code'] == leaf['after']['code']
    assert (leaf['before']['attribute'], leaf['after']['attribute']) == ('自制', '委外')
    assert (leaf['before']['color'], leaf['after']['color']) == ('白', '蓝')
    assert (leaf['before']['specification'], leaf['after']['specification']) == ('旧规格', '新规格')
    assert request(c, old['id'], 1, 2).json()['rows'] == []


def test_removed_added_keys_and_ancestor_only_quantity_change_are_explicit(client):
    c = client; _, _, old = tree(c)
    data = deepcopy(old['data']); data['nodes'][1]['numerator'] = '4'; data['nodes'][2]['key'] = 'new-b'
    post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    rows = {r['key']: r for r in request(c, old['id'], 2, 3).json()['rows']}
    assert rows['b']['kind'] == 'REMOVED' and rows['new-b']['kind'] == 'ADDED'
    assert [c['field'] for c in rows['leaf']['changes']] == ['cumulative']


@pytest.mark.parametrize('old,new,status', [(0, 2, 422), (2, 1, 422), (1, 1, 422), (1, 99, 404)])
def test_comparison_requires_existing_ordered_versions(client, old, new, status):
    _, first, _ = tree(client)
    assert request(client, first['id'], old, new).status_code == status


def test_comparison_enforces_engineering_read_scope_factory_and_bom_identity(client, monkeypatch):
    c = client; m, first, _ = tree(c)
    for account in (user(('bom_write',)), user(factory='huakang-a'), user(department='pmc-warehouse')):
        c.engineering_auth['user'] = account
        assert request(c, first['id'], 1, 2).status_code == 403
    c.engineering_auth['user'] = user()
    assert request(c, m['id'], 1, 2).status_code == 404
    assert request(c, 'missing', 1, 2).status_code == 404
    assert c.get(BASE + f"/boms/{first['id']}/comparison", params={'factory_id': 'huakang-a', 'from_version': 1, 'to_version': 2}).status_code == 422
    from app.api import engineering_bom as api
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', False)
    assert request(c, first['id'], 1, 2).status_code == 503


def test_equivalent_decimal_format_is_not_a_quantity_change(client):
    c = client; _, _, old = tree(c)
    data = deepcopy(old['data']); data['nodes'][1]['numerator'] = '2.000'
    post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    result = request(c, old['id'], 2, 3).json()
    assert result['rows'] == [] and result['unchanged_count'] == 4


def test_numerator_and_denominator_changes_are_visible_even_when_ratio_is_equal(client):
    c = client; _, _, old = tree(c)
    data = deepcopy(old['data']); data['nodes'][1].update(numerator='4', denominator='2')
    post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    rows = request(c, old['id'], 2, 3).json()['rows']
    assert len(rows) == 1 and rows[0]['key'] == 'a'
    assert {change['field'] for change in rows[0]['changes']} == {'numerator', 'denominator'}


def test_table_reordering_does_not_claim_changed_path_or_consumption(client):
    c = client; _, _, old = tree(c)
    data = deepcopy(old['data']); data['nodes'][1], data['nodes'][2] = data['nodes'][2], data['nodes'][1]
    post(c, f"/boms/{old['id']}", command(expected_version=old['version'], data=data))
    rows = request(c, old['id'], 2, 3).json()['rows']
    assert {r['key'] for r in rows} == {'a', 'b'}
    assert all(r['changes'] == [dict(field='position', label='表内行序')] for r in rows)


def test_missing_frozen_material_is_not_reconstructed_from_current_master(client):
    from app.services.engineering_bom_comparison import compare
    _, _, old = tree(client)
    incomplete = deepcopy(old); incomplete['materials'] = {}
    with pytest.raises(HTTPException) as error:
        compare(incomplete, old)
    assert error.value.status_code == 409
