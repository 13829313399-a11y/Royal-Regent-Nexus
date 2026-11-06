"""T05a isolated trial acceptance; no real orders or stock."""
from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import hashlib
import json
from copy import deepcopy
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_engineering_bom import client as engineering_client, command, material, bom, post, user as engineer
from app.api import material_plan as api
from app.services import material_plan as service
from app.models.material_plan import MaterialPlan, MaterialPlanEvent
from app.schemas.material_plan import TrialRequest
from app.models.engineering_bom import EngineeringEvent
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext
from app.services.permission_codes import MATERIAL_PLAN_PERMISSION_CODES

BASE = '/api/material-planning'


def sales(identity='sales-1', actions=('read', 'draft_write'), department='sales-business', factory='huakang-c'):
    codes = frozenset('material_plan:' + a for a in actions)
    grant = AuthGrantContext(role_id='synthetic', role_name='Test', factory_id=factory, department=department, permissions=codes)
    return AuthContext(id=identity, username='synthetic', display_name='测试业务', roles=('test',), role_codes=('test',),
        permissions=codes, factory_scopes=(factory,), department_scopes=(department,), grants=(grant,), active_permission_codes=frozenset(MATERIAL_PLAN_PERMISSION_CODES))


def migration():
    spec = spec_from_file_location('material_migration', Path(__file__).parents[1] / 'alembic/versions/20261104_0191_material_plan.py')
    module = module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def engineering_material_attribute(request):
    return getattr(request, 'param', '外购')


@pytest.fixture
def client(engineering_client, monkeypatch, engineering_material_attribute):
    c = engineering_client
    c.app.include_router(api.router)
    with c.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()
    monkeypatch.setattr(api.settings, 'material_plan_enabled', True)
    m = material(c, attribute=engineering_material_attribute); payload = bom(m)
    root = payload['data']['nodes'][0]
    payload['data']['nodes'].extend([dict(root, key='sew', parent='root', process='车缝'),
        dict(root, key='fabric', parent='sew', numerator='0.2', process='裁床')])
    draft = post(c, '/boms', payload)
    published = post(c, f"/boms/{draft['id']}/approve", command(expected_version=1))
    c.published, c.bom_payload = published, payload
    c.engineering_auth['user'] = sales()
    return c


def payload(client, **changes):
    return command(data=dict(title='新单试算', bom_id=client.published['id'], bom_version=2,
        quantity='100', loss_percent='5', loss_exemptions={}) | changes)


def request(client, path, body):
    response = client.post(BASE + path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def exact(amount):
    return Fraction(int(amount['numerator']), int(amount['denominator']))


def test_gross_loss_is_once_per_occurrence_and_unknown_supply_is_not_zero(client):
    result = request(client, '/preview', payload(client))
    assert [line['gross']['value'] for line in result['lines']] == ['105', '21']
    assert result['finished_quantity']['value'] == '100'
    assert result['totals'][0]['gross']['value'] == '126'  # same synthetic material, two processes
    assert result['totals'][0]['processes'] == ['裁床', '车缝']
    assert result['net_purchase_quantity'] is None and result['supply_status'] == 'PENDING_VERIFICATION'
    assert len(result['pending']) == 4
    exempt = request(client, '/preview', payload(client, loss_exemptions={'sew': True}))
    assert [line['gross']['value'] for line in exempt['lines']] == ['100', '21']
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(MaterialPlanEvent)) == 0


def test_fraction_totals_do_not_accumulate_display_rounding_or_mix_versions_units():
    root = dict(key='root', parent='', numerator='1', denominator='1')
    nodes = [root] + [dict(key=str(i), parent='root', numerator='1', denominator='3', material_id='m', material_version=1,
        unit='码', process='车缝' if i == 0 else '手工', exempt_loss=False) for i in range(3)]
    material = dict(id='m', version=1, code='02-20-001', name='同色线', data={'engineering': {'attribute': '外购'}})
    frozen = {'data': {'nodes': nodes}, 'materials': {'m:1': material}}
    root['unit'] = '套'
    result = service.calculate(frozen, dict(quantity='1', loss_percent='0', loss_exemptions={}))
    assert result['lines'][0]['gross']['approximate'] is True
    assert exact(result['totals'][0]['gross']) == 1 and result['totals'][0]['gross']['value'] == '1'
    nodes[1]['unit'] = '米'
    assert len(service.calculate(frozen, dict(quantity='1', loss_percent='0', loss_exemptions={}))['totals']) == 2
    nodes[2]['material_version'] = 2
    frozen['materials']['m:2'] = dict(material, version=2)
    assert len(service.calculate(frozen, dict(quantity='1', loss_percent='0', loss_exemptions={}))['totals']) == 3


def test_small_usage_and_loss_exemptions_are_exact(client):
    frozen = client.published
    frozen['data']['nodes'][1].update(numerator='2', denominator='1')
    frozen['data']['nodes'][2].update(numerator='0.0297', denominator='2', exempt_loss=True)
    result = service.calculate(frozen, dict(quantity='1', loss_percent='5', loss_exemptions={}))
    assert exact(result['lines'][1]['gross']) == Fraction('0.0297')
    result = service.calculate(frozen, dict(quantity='1', loss_percent='5', loss_exemptions={'fabric': False}))
    assert exact(result['lines'][1]['gross']) == Fraction('0.031185')
    tiny = service.amount(Fraction(1, 10 ** 30))
    assert Fraction(tiny['value']) > 0 and exact(tiny) == Fraction(1, 10 ** 30)


@pytest.mark.parametrize('engineering_material_attribute', ['自制', '委外'], indirect=True)
def test_same_material_different_business_attributes_stay_separate_and_history_is_fixed(client):
    body = payload(client, material_attributes={'sew': '自制', 'fabric': '委外'})
    first = request(client, '/drafts', body)
    totals = first['result']['totals']
    assert len({(t['material_id'], t['material_version'], t['unit']) for t in totals}) == 1
    assert {(t['attribute'], t['gross']['value']) for t in totals} == {('自制', '105'), ('委外', '21')}
    assert first['inputs']['material_attributes'] == {'sew': '自制', 'fabric': '委外'}
    # Attribute grouping is independent of process, and never rewrites engineering defaults.
    frozen = deepcopy(client.published)
    frozen['data']['nodes'][1]['process'] = frozen['data']['nodes'][2]['process']
    calculated = service.calculate(frozen, body['data'])
    assert len(calculated['totals']) == 2
    changed = payload(client, material_attributes={'sew': '自制', 'fabric': '自制'}) | {'expected_version': 1}
    second = request(client, f"/drafts/{first['id']}", changed)
    assert [(t['attribute'], t['gross']['value']) for t in second['result']['totals']] == [('自制', '126')]
    history = client.get(BASE + f"/drafts/{first['id']}/history?factory_id=huakang-c").json()['items']
    assert history == [second, first]
    assert request(client, '/drafts', body) == first
    assert all(m['data']['engineering']['attribute'] == client.published['materials'][key]['data']['engineering']['attribute']
               for key, m in first['bom']['materials'].items())


def test_pre_attribute_receipt_replays_without_rewriting_historical_result(client):
    old = deepcopy(request(client, '/drafts', payload(client)))
    old['id'] = uuid4().hex
    old['inputs'].pop('material_attributes')
    old['result']['algorithm'] = 'gross-fraction-v1'
    for line in old['result']['lines']:
        line.pop('engineering_attribute')
    body = payload(client)
    legacy = TrialRequest.model_validate(body).model_dump(mode='json')
    legacy['data'].pop('material_attributes')
    legacy['data'].pop('order')
    digest = hashlib.sha256(service.bom.dump([sales().id, '', legacy]).encode()).hexdigest()
    with Session(client.engine) as db:
        db.add(MaterialPlan(id=old['id'], factory_id='huakang-c', owner_id=sales().id, version=1))
        db.add(MaterialPlanEvent(id=uuid4().hex, factory_id='huakang-c', operation_id=body['operation_id'], request_hash=digest,
            entity_id=old['id'], version=1, result_json=json.dumps(old), actor_id=sales().id, occurred_at=old['occurred_at'], reason=old['reason']))
        db.commit()
    assert request(client, '/drafts', body) == old
    body['data']['material_attributes'] = {'sew': '外购'}
    assert client.post(BASE + '/drafts', json=body).status_code == 409


def test_saved_versions_are_immutable_and_original_request_replays(client):
    body = payload(client); first = request(client, '/drafts', body)
    assert first['inputs']['loss_exemptions'] == {'sew': False, 'fabric': False}
    assert request(client, '/drafts', body) == first
    assert client.post(BASE + '/drafts', json=body | {'reason': 'changed'}).status_code == 409
    revised = payload(client, quantity='200') | {'expected_version': 1}
    second = request(client, f"/drafts/{first['id']}", revised)
    assert second['result']['lines'][0]['gross']['value'] == '210'
    history = client.get(BASE + f"/drafts/{first['id']}/history?factory_id=huakang-c").json()['items']
    assert history == [second, first]
    assert client.post(BASE + f"/drafts/{first['id']}", json=revised | {'operation_id': uuid4().hex}).status_code == 409
    with client.engine.begin() as connection:
        for sql in ['DELETE FROM material_plan_events', "UPDATE material_plan_events SET reason='overwrite'"]:
            with pytest.raises(IntegrityError):
                connection.execute(text(sql))
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError):
            migration().downgrade()


def test_save_materializes_engineering_default_exemptions(client):
    client.engineering_auth['user'] = engineer()
    changed = client.bom_payload | {'expected_version': 2, 'operation_id': uuid4().hex}
    changed['data']['nodes'][2]['exempt_loss'] = True
    post(client, f"/boms/{client.published['id']}", changed)
    post(client, f"/boms/{client.published['id']}/approve", command(expected_version=3))
    client.engineering_auth['user'] = sales()
    saved = request(client, '/drafts', payload(client, bom_version=4))
    assert saved['inputs']['loss_exemptions'] == {'sew': False, 'fabric': True}
    assert saved['result']['lines'][1]['gross']['value'] == '20'


def test_new_bom_effective_version_blocks_old_selection_but_keeps_draft_evidence(client):
    body = payload(client); first = request(client, '/drafts', body)
    client.engineering_auth['user'] = engineer()
    changed = client.bom_payload | {'expected_version': 2, 'operation_id': uuid4().hex}
    post(client, f"/boms/{client.published['id']}", changed)
    client.engineering_auth['user'] = sales()
    assert request(client, '/preview', body)['lines'][0]['gross']['value'] == '105'
    client.engineering_auth['user'] = engineer()
    post(client, f"/boms/{client.published['id']}/approve", command(expected_version=3))
    client.engineering_auth['user'] = sales()
    assert client.post(BASE + '/preview', json=body).status_code == 409
    assert client.post(BASE + f"/drafts/{first['id']}", json=body | {'operation_id': uuid4().hex, 'expected_version': 1}).status_code == 409
    assert request(client, '/drafts', body) == first
    w = client.get(BASE + '/workspace?factory_id=huakang-c').json()
    assert w['boms'][0]['version'] == 4 and w['drafts'][0]['bom']['version'] == 2


def test_creator_isolation_and_current_permissions_always_apply(client):
    body = payload(client); first = request(client, '/drafts', body)
    client.engineering_auth['user'] = sales('another')
    assert client.get(BASE + '/workspace?factory_id=huakang-c').json()['drafts'] == []
    assert client.get(BASE + f"/drafts/{first['id']}/history?factory_id=huakang-c").status_code == 404
    assert client.post(BASE + f"/drafts/{first['id']}", json=payload(client) | {'expected_version': 1}).status_code == 404
    assert client.post(BASE + '/drafts', json=body).status_code == 409
    client.engineering_auth['user'] = sales(actions=('read',))
    assert client.post(BASE + '/drafts', json=body).status_code == 403
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 200


@pytest.mark.parametrize('actor', [sales(department='engineering'), sales(department='pmc-warehouse'), sales(factory='huakang-a'), sales(actions=())])
def test_scope_boundaries(client, actor):
    client.engineering_auth['user'] = actor
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 403
    assert client.post(BASE + '/preview', json=payload(client)).status_code == 403


def test_position_scope_explicit_deny_and_disabled_schema(client, monkeypatch):
    actor = sales(department='pmc-warehouse')
    client.engineering_auth['user'] = replace(actor, grants=(replace(actor.grants[0], unrestricted_department=True),))
    assert client.post(BASE + '/drafts', json=payload(client)).status_code == 403
    client.engineering_auth['user'] = replace(sales(), overrides=(AuthOverrideContext(id='deny', permission_code='material_plan:draft_write',
        effect='deny', factory_id='huakang-c', department='sales-business'),))
    assert client.post(BASE + '/drafts', json=payload(client)).status_code == 403
    client.engineering_auth['user'] = sales()
    monkeypatch.setattr(api.settings, 'material_plan_enabled', False)
    assert client.post(BASE + '/drafts', json=payload(client)).status_code == 503
    monkeypatch.setattr(api.settings, 'material_plan_enabled', True)
    with client.engine.begin() as connection:
        connection.execute(text('DROP TRIGGER material_plan_no_update'))
    assert client.get(BASE + '/access?factory_id=huakang-c').json()['schema_ready'] is False
    assert client.post(BASE + '/drafts', json=payload(client)).status_code == 503


@pytest.mark.parametrize('changes', [{'quantity': '0'}, {'quantity': '-1'}, {'quantity': 'NaN'}, {'loss_percent': '101'},
    {'loss_percent': '-1'}, {'loss_exemptions': {'unknown': True}}, {'loss_exemptions': {'root': True}}, {'bom_version': 1},
    {'material_attributes': {'unknown': '自制'}}, {'material_attributes': {'root': '自制'}},
    {'material_attributes': {'sew': '未知'}}, {'material_attributes': {'sew': '委外'}}])
def test_invalid_trials_never_persist(client, changes):
    response = client.post(BASE + '/drafts', json=payload(client, **changes))
    assert response.status_code in (409, 422)
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(MaterialPlanEvent)) == 0


def test_concurrent_retry_and_save_conflict(client):
    body = payload(client)
    with ThreadPoolExecutor(2) as pool:
        saved = list(pool.map(lambda _: request(client, '/drafts', body), range(2)))
    assert saved[0] == saved[1]
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(lambda _: client.post(BASE + f"/drafts/{saved[0]['id']}", json=payload(client) | {'expected_version': 1}).status_code, range(2)))
    assert sorted(statuses) == [200, 409]


def test_empty_migration_reversible_and_read_only_work_does_not_change_engineering(client):
    with Session(client.engine) as db:
        before = db.scalar(select(func.count()).select_from(EngineeringEvent))
    request(client, '/preview', payload(client))
    with client.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().downgrade(); migration().upgrade()
    with Session(client.engine) as db:
        assert service.ready(db)
        assert db.scalar(select(func.count()).select_from(EngineeringEvent)) == before
