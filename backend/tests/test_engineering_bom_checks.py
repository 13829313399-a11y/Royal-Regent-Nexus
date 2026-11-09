"""Read-only approval preparation, using isolated engineering databases."""
from copy import deepcopy
from decimal import Decimal
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.engineering_bom import EngineeringEvent, EngineeringBom
from app.models.fabric_master import FabricMasterRecord
from app.models.fabric_procurement import FabricProcurementState
from test_engineering_bom import client, material, bom, post, command, user, BASE
from app.services import engineering_bom as service


def check(c, draft, **params):
    return c.get(BASE + f"/boms/{draft['id']}/approval-check", params={
        'factory_id': 'huakang-c', 'expected_version': draft['version'], **params})


def state(c):
    with Session(c.engine) as db:
        return (list(db.scalars(select(EngineeringEvent.result_json).order_by(EngineeringEvent.id))),
                [(r.id, r.version, r.effective_version) for r in db.scalars(select(EngineeringBom))],
                [(r.id, r.revision, r.status, r.data_json) for r in db.scalars(select(FabricMasterRecord))],
                [(r.factory_id, r.revision) for r in db.scalars(select(FabricProcurementState))])


def test_customer_loss_blocks_save_and_legacy_approval_without_rewriting_history(client, monkeypatch):
    m = material(client, attribute='客供'); payload = bom(m)
    payload['data']['nodes'].append(dict(payload['data']['nodes'][0], key='supplied', parent='root',
        exempt_loss=True, source={'物料属性': '外购'}))  # Source text cannot override pinned identity.
    before = state(client)
    response = client.post(BASE + '/boms', json=payload)
    assert response.status_code == 422 and '客供' in response.text
    assert state(client) == before
    # Model an existing pre-rule draft without altering immutable database events.
    with monkeypatch.context() as legacy:
        legacy.setattr(service, 'validate_material_loss', lambda *args: None)
        draft = post(client, '/boms', payload)
    old = client.get(BASE + f"/history/{draft['id']}?factory_id=huakang-c").json()['items'][0]
    before = state(client)
    report = check(client, draft).json()
    assert not report['ready_for_approval'] and not report['can_release']
    assert report['issues'][0]['key'] == 'supplied' and '客供' in report['issues'][0]['message']
    assert client.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 422
    assert state(client) == before
    # Even changing the current catalog to 外购 must not erase the pinned 客供 rule.
    newer = post(client, '/materials', command(id=m['id'], code=m['code'], group='01-01', name=m['name'],
        unit='码', department='裁床', attribute='外购', expected_version=m['version']))
    post(client, f"/materials/{m['id']}/approve", command(expected_version=newer['version']))
    assert not check(client, draft).json()['ready_for_approval']
    fixed = deepcopy(draft['data']); fixed['nodes'][1]['exempt_loss'] = False
    saved = post(client, f"/boms/{draft['id']}", command(expected_version=1, data=fixed))
    assert check(client, saved).json()['ready_for_approval']
    post(client, f"/boms/{draft['id']}/approve", command(expected_version=2))
    history = client.get(BASE + f"/history/{draft['id']}?factory_id=huakang-c").json()['items']
    assert history[-1] == old


@pytest.mark.parametrize('handwork', [False, True])
def test_both_finished_structures_approve_and_expand_without_duplicate_sewing_inputs(client, handwork):
    m = material(client); payload = bom(m); root = payload['data']['nodes'][0]
    root['process'] = '手工' if handwork else '车缝'
    nodes = payload['data']['nodes']; sewing = 'sewing' if handwork else 'root'
    if handwork:
        nodes.append(dict(root, key=sewing, parent='root', process='车缝'))
        nodes.append(dict(root, key='manual-thread', parent='root', process='手工', numerator='0.2'))
    nodes.extend([dict(root, key='cut', parent=sewing, process='裁床', numerator='2'),
        dict(root, key='fabric', parent='cut', process='裁床', numerator='0.0297', denominator='2'),
        dict(root, key='sewing-thread', parent=sewing, process='车缝', numerator='0.8')])
    saved = post(client, '/boms', payload)
    assert check(client, saved).json()['ready_for_approval']
    approved = post(client, f"/boms/{saved['id']}/approve", command(expected_version=1))
    expanded = {row['key']: row['quantity'] for row in service.expansion(approved['data'])}
    assert Decimal(expanded['fabric']) == Decimal('0.0297')
    assert Decimal(expanded['sewing-thread']) == Decimal('0.8')
    assert len(approved['data']['nodes']) == (6 if handwork else 4)
    if not handwork:
        assert all(n['process'] != '手工' for n in approved['data']['nodes'])


def test_check_is_read_only_and_does_not_authorize_approval(client):
    c = client; draft = post(c, '/boms', bom(material(c)))
    c.engineering_auth['user'] = user(('read',))
    before = state(c)
    response = check(c, draft); assert response.status_code == 200, response.text
    report = response.json()
    assert report['ready_for_approval'] and not report['can_release']
    assert report['version'] == 1 and report['checked_rows'] == 1 and report['checked_at']
    assert report['issues'] == [] and state(c) == before
    assert c.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 403


def test_lists_each_occurrence_first_blocker_without_merging_same_material(client):
    c = client; m = material(c); payload = bom(m); root = payload['data']['nodes'][0]
    payload['data']['nodes'] += [dict(root, key='sewing', parent='root', process=''),
        dict(root, key='manual', parent='root', review_required=True, review_note=''),
        dict(key='unknown', parent='root', source_code='02-unknown', source_name='未匹配线')]
    draft = post(c, '/boms', payload)
    result = check(c, draft).json()
    assert not result['ready_for_approval'] and result['checked_rows'] == 4
    assert [i['key'] for i in result['issues']] == ['sewing', 'manual', 'unknown']
    assert [i['row'] for i in result['issues']] == [2, 3, 4]
    assert result['issues'][0]['code'] == result['issues'][1]['code'] == m['code']
    assert '工序' in result['issues'][0]['message']
    assert '核对说明' in result['issues'][1]['message']
    assert '未匹配物料' in result['issues'][2]['message']
    assert c.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 422
    data = deepcopy(draft['data']); data['nodes'][1]['process'] = '车缝'; data['nodes'][2]['review_note'] = '已核对'
    data['nodes'].pop()
    fixed = post(c, f"/boms/{draft['id']}", command(expected_version=1, data=data))
    assert check(c, fixed).json()['ready_for_approval']
    post(c, f"/boms/{draft['id']}/approve", command(expected_version=2))


def test_material_change_after_pass_blocks_real_approval_and_recheck(client):
    c = client; m = material(c); draft = post(c, '/boms', bom(m))
    assert check(c, draft).json()['ready_for_approval']
    post(c, f"/materials/{m['id']}/deactivate", command(expected_version=m['version']))
    response = c.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1))
    assert response.status_code == 422
    report = check(c, draft).json()
    assert not report['ready_for_approval'] and '停用或待审' in report['issues'][0]['message']
    assert report['version'] == 1


def test_same_code_historical_attributes_stay_separate(client):
    c = client; m = material(c, attribute='自制'); payload = bom(m)
    draft = post(c, '/boms', payload)
    updated = post(c, '/materials', command(id=m['id'], code=m['code'], group='01-01', name=m['name'],
        unit='码', department='裁床', attribute='委外', expected_version=m['version']))
    updated = post(c, f"/materials/{m['id']}/approve", command(expected_version=updated['version']))
    data = deepcopy(draft['data']); data['nodes'][0]['process'] = ''
    data['nodes'].append(dict(data['nodes'][0], key='subcontract', parent='root', material_version=updated['version']))
    draft = post(c, f"/boms/{draft['id']}", command(expected_version=1, data=data))
    issues = check(c, draft).json()['issues']
    assert len(issues) == 2 and issues[0]['code'] == issues[1]['code']
    assert [i['attribute'] for i in issues] == ['自制', '委外']


def test_newer_material_keeps_pinned_units_and_attributes(client):
    c = client; m = material(c, attribute='自制'); draft = post(c, '/boms', bom(m))
    newer = post(c, '/materials', command(id=m['id'], code=m['code'], group='01-01', name='新规格',
        unit='卷', department='裁床', attribute='委外', expected_version=m['version']))
    assert not check(c, draft).json()['ready_for_approval']  # Current master is pending approval.
    post(c, f"/materials/{m['id']}/approve", command(expected_version=newer['version']))
    assert check(c, draft).json()['ready_for_approval']  # Saved BOM still uses its approved 码 snapshot.
    approved = post(c, f"/boms/{draft['id']}/approve", command(expected_version=1))
    assert approved['materials'][f"{m['id']}:{m['version']}"]['data']['unit'] == '码'


def test_stale_version_and_non_draft_are_not_reported_as_ready(client):
    c = client; draft = post(c, '/boms', bom(material(c)))
    approved = post(c, f"/boms/{draft['id']}/approve", command(expected_version=1))
    assert check(c, draft).status_code == 409
    result = check(c, approved).json()
    assert not result['ready_for_approval'] and result['issues'][0]['row'] is None
    assert result['effective_version'] == 2 and result['status'] == 'APPROVED'


@pytest.mark.parametrize('account', [user(('bom_write',)), user(factory='huakang-a'), user(department='pmc-warehouse')])
def test_check_requires_engineering_read_scope(client, account):
    draft = post(client, '/boms', bom(material(client)))
    client.engineering_auth['user'] = account
    assert check(client, draft).status_code == 403


def test_invalid_identity_version_factory_flag_and_schema_fail_closed(client, monkeypatch):
    from app.api import engineering_bom as api
    c = client; m = material(c); draft = post(c, '/boms', bom(m))
    assert check(c, draft, expected_version=0).status_code == 422
    assert check(c, draft, factory_id='huakang-a').status_code == 422
    assert check(c, {'id': m['id'], 'version': 1}).status_code == 404
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', False)
    assert check(c, draft).status_code == 503
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', True)
    monkeypatch.setattr(api.service, 'ready', lambda db: False)
    assert check(c, draft).status_code == 503
