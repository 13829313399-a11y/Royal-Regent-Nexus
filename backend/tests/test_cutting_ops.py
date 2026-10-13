"""P1b acceptance: temporary databases only, no business data or default grants."""
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from uuid import uuid4
os.environ.setdefault('DATABASE_URL', 'sqlite://')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, func
from sqlalchemy.orm import Session
from app.api import cutting_operations as api
from app.models.cutting_ops import CuttingMaster, CuttingRevision, CuttingCommand
from app.services import cutting_ops as c
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.permission_codes import CUTTING_OPS_PERMISSION_CODES


def user(*actions, department='*', factory='huakang-c'):
    codes = frozenset('cutting_ops:' + a for a in actions)
    grant = AuthGrantContext(role_id='synthetic', role_name='Test', factory_id=factory, department=department, permissions=codes)
    return AuthContext(id='test-user', username='synthetic', display_name='合成测试', roles=('test',), role_codes=('test',),
                       permissions=codes, factory_scopes=(factory,), department_scopes=(department,), grants=(grant,),
                       active_permission_codes=frozenset(CUTTING_OPS_PERMISSION_CODES))


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + (tmp_path / 'cutting.db').as_posix(), connect_args={'check_same_thread': False, 'timeout': 20})
    @event.listens_for(engine, 'connect')
    def enable_fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    CuttingMaster.metadata.create_all(engine, tables=list(c.TABLES))
    auth = {'user': user('read', 'master_write', 'bom_write', 'bom_publish')}
    def get_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.get_db] = get_db
    app.dependency_overrides[get_current_user] = lambda: auth['user']
    monkeypatch.setattr(api.settings, 'cutting_ops_enabled', True)
    with TestClient(app) as test:
        test.engine, test.cutting_auth = engine, auth
        yield test
    engine.dispose()


BASE = '/api/cutting-operations'
def command(**kwargs):
    return dict(factory_id='huakang-c', operation_id=uuid4().hex, expected_version=0, reason='合成测试依据') | kwargs


def material_body(code='001'):
    return command(kind='material', code=code, data=dict(name='蓝布', category='fabric', unit='米', color='蓝', specification='规格A', source_reference='工程物料原始编码M01'))


def create(client, body=None):
    response = client.post(BASE + '/masters', json=body or material_body())
    assert response.status_code == 200, response.text
    return response.json()


def bom_body(material):
    return command(kind='bom', code='B001', data=dict(name='测试套装', item_no='00012', style='款式A', color='蓝', source_reference='工程生产BOM-1',
        parts=[dict(code='P01', name='左片', pieces_per_set=2), dict(code='P02', name='右片', pieces_per_set=1)],
        requirements=[dict(material_id=material['id'], material_version=material['version'], part_codes=['P01', 'P02'],
                           quantity_per_set='0.125000', unit='米', required_for_cutting=True, stage='裁剪', note='布料先到')]))


def state(client, row, status, **kwargs):
    return client.post(f"{BASE}/masters/{row['id']}/state", json=command(expected_version=row['version'], status=status, **kwargs))


def test_versioned_bom_preserves_published_data_and_partial_material_policy(client):
    material = create(client)
    body = bom_body(material)
    body['data']['requirements'].append(dict(body['data']['requirements'][0], required_for_cutting=False, stage='包装', note='后到辅料'))
    draft = create(client, body)
    assert draft['data']['item_no'] == '00012'
    published_response = state(client, draft, 'published')
    assert published_response.status_code == 200, published_response.text
    published = published_response.json()
    revised = material_body(); revised['expected_version'] = material['version']; revised['data']['name'] = '新名称'
    assert client.put(f"{BASE}/masters/{material['id']}", json=revised).status_code == 200
    body.update(operation_id=uuid4().hex, expected_version=published['version'])
    body['data']['parts'][0]['pieces_per_set'] = 3
    new = client.put(f"{BASE}/masters/{draft['id']}", json=body)
    assert new.status_code == 200 and new.json()['status'] == 'draft'
    history = client.get(f"{BASE}/masters/{draft['id']}/versions?factory_id=huakang-c").json()['data']
    assert [r['version'] for r in history] == [3, 2, 1]
    assert history[1]['data'] == published['data'] and history[1]['status'] == 'published'
    assert history[1]['data']['requirements'][0]['material_version'] == 1
    assert history[1]['material_references'][material['id'] + ':1']['name'] == '蓝布'
    assert history[1]['data']['requirements'][1]['required_for_cutting'] is False


def test_retry_conflicts_and_audit_are_atomic(client):
    body = material_body()
    original = create(client, body)
    assert client.post(BASE + '/masters', json=body).json() == original
    changed = dict(body, reason='重用编号但内容变化')
    assert client.post(BASE + '/masters', json=changed).status_code == 409
    assert client.post(BASE + '/masters', json=material_body()).status_code == 409
    bad = material_body('002'); bad['data']['unit'] = ''
    assert client.post(BASE + '/masters', json=bad).status_code == 422
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(CuttingMaster)) == 1
        assert db.scalar(select(func.count()).select_from(CuttingRevision)) == 1
        assert db.scalar(select(func.count()).select_from(CuttingCommand)) == 1


def test_concurrent_same_version_only_one_revision_wins(client):
    item = create(client)
    bodies = [material_body(), material_body()]
    for i, body in enumerate(bodies):
        body.update(expected_version=1); body['data']['name'] = '修订' + str(i)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda body: client.put(f"{BASE}/masters/{item['id']}", json=body), bodies))
    assert sorted(r.status_code for r in responses) == [200, 409]
    with Session(client.engine) as db:
        assert db.get(CuttingMaster, item['id']).version == 2
        assert db.scalar(select(func.count()).select_from(CuttingCommand)) == 2


@pytest.mark.parametrize('factory', ['', 'group', '*', 'huakang-d', 'huaxing'])
def test_factory_scope_cannot_fallback(client, factory):
    assert client.get(BASE + '/masters', params={'factory_id': factory}).status_code == 422
    body = material_body(); body['factory_id'] = factory
    assert client.post(BASE + '/masters', json=body).status_code == 422


def test_repeated_factory_parameter_rejected(client):
    assert client.get(BASE + '/masters?factory_id=huakang-d&factory_id=huakang-c').status_code == 422


@pytest.mark.parametrize('department,actions,expected', [('production', ('read', 'master_write'), 200), ('engineering', ('read', 'master_write'), 403), ('production', ('read',), 403), ('sales-business', ('read', 'master_write'), 403)])
def test_master_write_department_and_action(client, department, actions, expected):
    client.cutting_auth['user'] = user(*actions, department=department)
    assert client.post(BASE + '/masters', json=material_body()).status_code == expected


def test_bom_engineering_publish_and_explicit_deny(client):
    material = create(client)
    draft = create(client, bom_body(material))
    client.cutting_auth['user'] = user('read', 'bom_write', 'bom_publish', department='production')
    assert state(client, draft, 'published').status_code == 403
    client.cutting_auth['user'] = user('read', 'bom_write', 'bom_publish', department='engineering')
    client.cutting_auth['user'] = replace(client.cutting_auth['user'], overrides=(AuthOverrideContext(id='deny', permission_code='cutting_ops:bom_publish', effect='deny', factory_id='huakang-c', department='engineering'),))
    assert state(client, draft, 'published').status_code == 403
    client.cutting_auth['user'] = user('read', 'bom_publish', department='engineering')
    assert state(client, draft, 'published').status_code == 200


def test_unrestricted_position_still_requires_engineering_department(client):
    material = create(client); draft = create(client, bom_body(material))
    account = user('read', 'bom_publish', department='production')
    account = replace(account, grants=(replace(account.grants[0], unrestricted_department=True),))
    client.cutting_auth['user'] = account
    assert state(client, draft, 'published').status_code == 403
    client.cutting_auth['user'] = replace(account, grants=(replace(account.grants[0], department='engineering'),))
    assert state(client, draft, 'published').status_code == 200


def test_read_and_replay_recheck_current_access(client):
    body = material_body(); row = create(client, body)
    client.cutting_auth['user'] = user('read', 'master_write', factory='huakang-d')
    assert client.get(BASE + '/masters?factory_id=huakang-c').status_code == 403
    assert client.get(f"{BASE}/masters/{row['id']}/versions?factory_id=huakang-c").status_code == 403
    assert client.post(BASE + '/masters', json=body).status_code == 403
    client.cutting_auth['user'] = replace(user('read', 'master_write'), account_available=False)
    assert client.post(BASE + '/masters', json=body).status_code == 403


@pytest.mark.parametrize('invalid', ['0', '-1', 'NaN', 'Infinity', '0.0000001', '1000000000000'])
def test_invalid_bom_quantity_never_persists(client, invalid):
    body = bom_body(create(client)); body['data']['requirements'][0]['quantity_per_set'] = invalid
    assert client.post(BASE + '/masters', json=body).status_code == 422
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(CuttingMaster)) == 1


def test_invalid_reference_unit_and_piece_composition(client):
    body = bom_body(create(client))
    body['data']['requirements'][0]['unit'] = '公斤'
    assert client.post(BASE + '/masters', json=body).status_code == 422
    body['data']['requirements'][0]['unit'] = '米'
    body['data']['requirements'][0]['material_version'] = 99
    assert client.post(BASE + '/masters', json=body).status_code == 404
    body['data']['requirements'][0]['material_version'] = 1
    body['data']['parts'][1]['code'] = 'P01'
    assert client.post(BASE + '/masters', json=body).status_code == 422


def test_publish_checks_required_material_and_current_disabled_state(client):
    material = create(client); body = bom_body(material)
    body['data']['requirements'][0]['required_for_cutting'] = False
    draft = create(client, body)
    assert state(client, draft, 'published').status_code == 422
    assert state(client, material, 'inactive').status_code == 200
    body['data']['requirements'][0]['required_for_cutting'] = True; body['code'] = 'B002'; body['operation_id'] = uuid4().hex
    next_draft = create(client, body)
    assert state(client, next_draft, 'published').status_code == 409


def test_disabled_and_missing_schema_fail_closed(client, monkeypatch):
    monkeypatch.setattr(api.settings, 'cutting_ops_enabled', False)
    assert client.get(BASE + '/access?factory_id=huakang-c').json()['enabled'] is False
    assert client.post(BASE + '/masters', json=material_body()).status_code == 503
    monkeypatch.setattr(api.settings, 'cutting_ops_enabled', True)
    CuttingMaster.metadata.drop_all(client.engine, tables=list(reversed(c.TABLES)))
    assert client.get(BASE + '/access?factory_id=huakang-c').json()['schema_ready'] is False
    assert client.get(BASE + '/masters?factory_id=huakang-c').status_code == 503


def test_outsourcing_only_accepts_cutting_and_code_search_is_literal(client):
    body = command(kind='resource', code='F01', data=dict(name='外发厂', execution='outsourced', process='sewing', source_reference='合同'))
    assert client.post(BASE + '/masters', json=body).status_code == 422
    create(client, material_body('M%01')); create(client, material_body('M201'))
    result = client.get(BASE + '/masters', params=dict(factory_id='huakang-c', kind='material', q='%')).json()
    assert result['total'] == 1 and result['data'][0]['code'] == 'M%01'
