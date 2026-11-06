"""Isolated engineering foundation acceptance; never touches business databases."""
import os
from io import BytesIO
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
os.environ.setdefault('DATABASE_URL', 'sqlite://')

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text, select, func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from openpyxl import Workbook
from app.api import engineering_bom as api
from app.models.fabric_master import FabricMasterRecord
from app.models.engineering_bom import EngineeringEvent
from app.services import engineering_bom as service
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.permission_codes import ENGINEERING_BOM_PERMISSION_CODES
from app.services import fabric_master
from app.schemas.fabric_master import SaveMasterRequest

BASE = '/api/engineering-bom'


def user(actions=service.ACTIONS, factory='huakang-c', department='engineering'):
    codes = frozenset('engineering_bom:' + a for a in actions)
    grant = AuthGrantContext(role_id='synthetic', role_name='Test', factory_id=factory, department=department, permissions=codes)
    return AuthContext(id='test-user', username='synthetic', display_name='合成测试', roles=('test',), role_codes=('test',),
        permissions=codes, factory_scopes=(factory,), department_scopes=(department,), grants=(grant,),
        active_permission_codes=frozenset(ENGINEERING_BOM_PERMISSION_CODES))


def migration():
    path = Path(__file__).parents[1] / 'alembic/versions/20261104_0190_engineering_bom.py'
    spec = spec_from_file_location('engineering_migration', path)
    module = module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + (tmp_path / 'engineering.db').as_posix(), connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def fk(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    tables = [t for t in FabricMasterRecord.metadata.sorted_tables if t.name.startswith(('fabric_master_', 'fabric_procurement_', 'fabric_chase_'))]
    FabricMasterRecord.metadata.create_all(engine, tables=tables)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()
    auth = {'user': user()}
    def get_db():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[api.get_db] = get_db
    app.dependency_overrides[get_current_user] = lambda: auth['user']
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', True)
    with TestClient(app) as test:
        test.engine, test.engineering_auth = engine, auth
        yield test
    engine.dispose()


def command(**kw):
    return dict(factory_id='huakang-c', operation_id=uuid4().hex, expected_version=0, reason='合成验收') | kw


def post(client, path, body):
    response = client.post(BASE + path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def material(client, **kw):
    body = command(code='01-01-00001', group='01-01', name='测试布', unit='码', department='裁床', **kw)
    draft = post(client, '/materials', body)
    return post(client, f"/materials/{draft['id']}/approve", command(expected_version=draft['version']))


def bom(m=None):
    root = dict(key='root', material_id=m['id'] if m else '', material_version=m['version'] if m else 0,
                unit='码', numerator='1', denominator='1', process='手工')
    return command(data=dict(item_no='001', name='测试成品', nodes=[root]))


def test_shared_material_identity_department_revision_and_retry(client):
    m = material(client)
    change = command(id=m['id'], code=m['code'], group='01-01', name=m['name'], unit='码', department='车缝', expected_version=m['version'])
    revised = post(client, '/materials', change)
    assert revised['id'] == m['id'] and revised['code'] == m['code'] and revised['data']['engineering']['department'] == '车缝'
    assert post(client, '/materials', change) == revised
    assert client.post(BASE + '/materials', json=change | {'reason': '另一次'}).status_code == 409
    assert client.post(BASE + '/materials', json=change | {'operation_id': uuid4().hex}).status_code == 409
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(FabricMasterRecord)) == 1
        assert db.scalar(select(func.count()).select_from(EngineeringEvent)) == 3


def test_bom_self_approval_effective_version_copy_and_immutable_history(client):
    m = material(client); payload = bom(m)
    draft = post(client, '/boms', payload)
    published = post(client, f"/boms/{draft['id']}/approve", command(expected_version=1))
    payload['expected_version'] = 2; payload['operation_id'] = uuid4().hex
    payload['data']['nodes'].append(dict(payload['data']['nodes'][0], key='child', parent='root', numerator='0.0297', denominator='2', process='裁床'))
    revised = post(client, f"/boms/{draft['id']}", payload)
    assert revised['version'] == 3 and revised['effective_version'] == 2
    history = client.get(BASE + f"/history/{draft['id']}?factory_id=huakang-c").json()['items']
    assert history[1]['data'] == published['data'] and history[1]['actor_id'] == 'test-user'
    copy = bom(m) | dict(copy_from=draft['id'], copy_version=2)
    assert client.post(BASE + '/boms', json=copy).status_code == 422
    copy['data']['item_no'] = '002'
    copied = post(client, '/boms', copy)
    assert copied['id'] != draft['id'] and copied['copy_version'] == 2
    with client.engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(text("UPDATE engineering_bom_events SET reason='changed'"))
        with pytest.raises(IntegrityError):
            connection.execute(text('DELETE FROM engineering_bom_events'))
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError):
            migration().downgrade()


def test_tree_decimal_math_and_invalid_ancestry(client):
    payload = bom(); nodes = payload['data']['nodes']
    nodes.extend([dict(key='ears', parent='root', numerator='2', denominator='1'),
                  dict(key='fabric', parent='ears', numerator='0.0297', denominator='2')])
    result = post(client, '/preview', payload)
    assert result['items'][2]['quantity'] == '0.0297'
    nodes[1]['parent'] = 'missing'
    nodes[:] = [nodes[0], nodes[2], nodes[1]]
    assert client.post(BASE + '/preview', json=payload).status_code == 422
    nodes[2]['parent'] = 'fabric'
    assert client.post(BASE + '/boms', json=payload).status_code == 422
    nodes[2]['parent'] = 'root'; nodes[1]['denominator'] = '0'
    assert client.post(BASE + '/boms', json=payload).status_code == 422


def test_unresolved_drafts_cannot_be_approved(client):
    draft = post(client, '/boms', bom())
    assert client.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 422
    m = material(client); payload = bom(m)
    payload['data']['nodes'][0].update(review_required=True)
    draft = post(client, '/boms', payload)
    assert client.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 422


@pytest.mark.parametrize('account', [user(factory='huakang-a'), user(department='pmc-warehouse'), user(actions=())])
def test_scope_and_permissions_fail_closed(client, account):
    client.engineering_auth['user'] = account
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 403
    assert client.post(BASE + '/boms', json=bom()).status_code == 403


def test_read_only_and_disabled_and_schema_drift(client, monkeypatch):
    client.engineering_auth['user'] = user(actions=('read',))
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 200
    assert client.post(BASE + '/boms', json=bom()).status_code == 403
    assert client.get(BASE + '/workspace?factory_id=huakang-a').status_code == 422
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', False)
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 503
    monkeypatch.setattr(api.settings, 'engineering_bom_enabled', True)
    with client.engine.begin() as connection:
        connection.execute(text('DROP TRIGGER engineering_events_no_delete'))
    assert client.get(BASE + '/access?factory_id=huakang-c').json()['schema_ready'] is False
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 503


HEADERS = ['BOM层级', '子项物料编码', '物料名称', '物料属性', 'BOM版本', '数据状态', '单位', '用量：分子', '用量：分母', '标准用量', '子项类型', '实际数量', '备注']


def workbook(formula=False):
    book = Workbook(); sheet = book.active
    sheet.append(HEADERS)
    sheet.append([0, '04-08-001', '成品', '自制', '旧版本', '已审核', '套', 0, 0, 1, '', 1, ''])
    sheet.append([1, '03-01-001', '尾巴', '外购', '', '已审核', '件', '=1+1' if formula else 23, 24, 1, '', 1, ''])
    stream = BytesIO(); book.save(stream); return stream.getvalue()


def test_import_preserves_source_flags_ratios_and_never_writes(client):
    response = client.post(BASE + '/import-preview', data={'factory_id': 'huakang-c'}, files={'file': ('sample.xlsx', workbook())})
    assert response.status_code == 200, response.text
    preview = response.json()
    assert preview['row_count'] == 2 and preview['can_save']
    root, child = preview['data']['nodes']
    assert root['source']['用量：分子'] == '0' and root['numerator'] == '1'
    assert child['numerator'] == '23' and child['denominator'] == '24' and child['review_required']
    assert any('口径' in issue['message'] for issue in preview['issues'])
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(EngineeringEvent)) == 0
    response = client.post(BASE + '/import-preview', data={'factory_id': 'huakang-c'}, files={'file': ('formula.xlsx', workbook(True))})
    assert response.status_code == 200 and not response.json()['can_save']


@pytest.mark.parametrize('filename', ['bad.xls', 'bad.xlsx', 'bad.csv'])
def test_malformed_files_return_validation_errors(client, filename):
    response = client.post(BASE + '/import-preview', data={'factory_id': 'huakang-c'}, files={'file': (filename, b'not excel')})
    assert response.status_code == 422


def test_broken_xml_returns_validation_error(client):
    out = BytesIO()
    with ZipFile(BytesIO(workbook())) as source, ZipFile(out, 'w') as dest:
        for entry in source.infolist():
            dest.writestr(entry, b'<bad' if entry.filename == 'xl/workbook.xml' else source.read(entry))
    response = client.post(BASE + '/import-preview', data={'factory_id': 'huakang-c'}, files={'file': ('broken.xlsx', out.getvalue())})
    assert response.status_code == 422


def test_import_duplicate_file_cannot_create_a_second_document(client):
    content = workbook()
    def preview():
        return client.post(BASE + '/import-preview', data={'factory_id': 'huakang-c'}, files={'file': ('sample.xlsx', content)}).json()
    data = preview()['data']; data['item_no'] = '001'
    body = command(data=data); original = post(client, '/boms', body)
    # Exact command replay is safe, even after the source becomes known.
    assert post(client, '/boms', body)['id'] == original['id']
    assert client.post(BASE + '/boms', json=body | {'operation_id': uuid4().hex}).status_code == 409
    duplicate = preview()
    assert not duplicate['can_save'] and duplicate['duplicates'][0]['id'] == original['id']


def test_legacy_material_editor_cannot_erase_engineering_but_suppliers_still_work(client):
    m = material(client)
    with Session(client.engine) as db:
        request = SaveMasterRequest(factory_id='huakang-c', request_id=uuid4(), id=m['id'], expected_revision=m['version'],
            kind='MATERIAL', code=m['code'], name='覆盖名称', status='ACTIVE', data={'unit': '码'})
        with pytest.raises(HTTPException) as error:
            fabric_master.save(db, user(), request)
        assert error.value.status_code == 409
        db.rollback()
        supplier = SaveMasterRequest(factory_id='huakang-c', request_id=uuid4(), kind='SUPPLIER', code='TEST-S1', name='合成供应商', data={})
        assert fabric_master.save(db, user(), supplier)['kind'] == 'SUPPLIER'
        assert service.material(db, m['id']).name == m['name']


def test_parallel_auto_number_and_same_command_retry(client):
    body = command(group='02-20-16', name='共用线', unit='码', department='车缝')
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: post(client, '/materials', body), range(2)))
    assert results[0] == results[1]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: post(client, '/materials', body | {'operation_id': uuid4().hex}), range(2)))
    assert {r['code'] for r in results} == {'02-20-16-00002', '02-20-16-00003'}


def test_empty_migration_can_be_reversed_and_reapplied(client):
    with client.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().downgrade()
        migration().upgrade()
    assert client.get(BASE + '/access?factory_id=huakang-c').json()['schema_ready']


def test_legacy_layout_keeps_blank_row_offsets_and_requires_cache_review(client, monkeypatch):
    from app.services import engineering_bom_import as parser
    values = [[''] * 14, ['', 0.0, '04-08-001', '成品', '自制', 'B001_v2', '已审核', '套', 0.0, 0.0, 1.0, '', 1.0, ''],
              ['', 1.0, '01-01-001', '蓝布', '外购', '', '已审核', '码', 0.0297, 2.0, 0.01485, '', 0.01485, '']]
    monkeypatch.setattr(parser, 'rows', lambda *_: [('Sheet1', values)])
    with Session(client.engine) as db:
        result = parser.preview(db, b'legacy-fixture', 'historical.xls')
    assert result['can_save'] and result['row_count'] == 2
    root, child = result['data']['nodes']
    assert root['source']['row'] == '2' and child['source']['row'] == '3'
    assert child['parent'] == root['key'] and child['source']['BOM版本'] == ''
    assert all(n['review_required'] for n in result['data']['nodes'])
    assert any('缓存值' in i['message'] for i in result['issues'])


def test_position_department_and_explicit_deny_remain_authoritative(client):
    account = user(department='pmc-warehouse')
    client.engineering_auth['user'] = replace(account, grants=(replace(account.grants[0], unrestricted_department=True),))
    assert client.get(BASE + '/workspace?factory_id=huakang-c').status_code == 403
    client.engineering_auth['user'] = user()
    draft = post(client, '/boms', bom(material(client)))
    client.engineering_auth['user'] = replace(user(), overrides=(AuthOverrideContext(id='deny', permission_code='engineering_bom:bom_approve',
        effect='deny', factory_id='huakang-c', department='engineering'),))
    assert client.post(BASE + f"/boms/{draft['id']}/approve", json=command(expected_version=1)).status_code == 403
