"""Exercise the engineering-to-cutting handoff through the existing order and warehouse APIs."""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session

from app.api import engineering_bom, warehouse_operations
from app.models.fabric_master import FabricMasterRecord
from app.models.warehouse_operations import WarehouseOperation
from test_cutting_materials import actor, decision, issue, ledger, request_body, send, warehouse_post, warehouse_view
from test_cutting_ops import client, command, create, material_body
from test_cutting_orders import batch, flow, post, read
from test_cutting_planning import publish, resource, save, task
from test_engineering_bom import BASE, migration, post as engineering_post, user as engineer


@pytest.fixture
def handoff(flow, monkeypatch):
    flow.app.include_router(engineering_bom.router)
    flow.app.include_router(warehouse_operations.router)
    monkeypatch.setattr(engineering_bom.settings, 'engineering_bom_enabled', True)
    tables = [t for t in WarehouseOperation.metadata.sorted_tables
              if t.name.startswith('fabric_') or t.name == 'warehouse_operations_documents']
    WarehouseOperation.metadata.create_all(flow.engine, tables=tables)
    with flow.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()
    cutting_role = actor('bom_write', 'bom_publish', 'master_write', 'plan_write', 'plan_publish',
                         'requisition_submit', 'eta_write', 'material_request', 'material_receive')
    engineering_role = engineer()
    flow.cutting_auth['user'] = replace(cutting_role, grants=cutting_role.grants + engineering_role.grants,
        permissions=cutting_role.permissions | engineering_role.permissions,
        active_permission_codes=cutting_role.active_permission_codes | engineering_role.active_permission_codes)
    return flow


def setup_bom(p, ratio='0.25'):
    materials = []
    for code, name, group, unit, category in [
        ('04-01', '成品', '04', '套', ''), ('04-02', '前片', '04', '片', ''), ('01-01', '蓝布', '01', '米', 'FABRIC'),
    ]:
        data = dict(code=code, name=name, group=group, unit=unit, department='裁床', warehouse_category=category)
        if category:
            data.update(specification='规格A', color='蓝')
        draft = engineering_post(p, '/materials', command(**data))
        materials.append(engineering_post(p, f"/materials/{draft['id']}/approve", command(expected_version=draft['version'])))
    create(p, material_body('01-01'))
    nodes = [dict(key=key, parent=parent, material_id=m['id'], material_version=m['version'], unit=m['data']['unit'],
                  process='裁床', numerator=quantity)
             for m, key, parent, quantity in zip(materials, ('root', 'part', 'fabric'), ('', 'root', 'part'), ('1', '2', ratio))]
    draft = engineering_post(p, '/boms', command(data=dict(item_no='00012', name='联动验收成品', nodes=nodes)))
    approved = engineering_post(p, f"/boms/{draft['id']}/approve", command(expected_version=draft['version']))
    return approved, materials[-1]


def selection(source):
    return dict(source_version=source['version'], style='款式A', color='蓝', part_keys=['part'],
                materials=[dict(key='fabric', part_keys=['part'], required_for_cutting=True)])


def endpoint(source, action=''):
    return f"{BASE}/boms/{source['id']}/cutting{action}"


def preview(p, source):
    response = p.post(endpoint(source, '/preview'), params={'factory_id': 'huakang-c'}, json=selection(source))
    assert response.status_code == 200, response.text
    return response.json()


def publish_body(p, source):
    before = preview(p, source)
    return command(expected_version=before['expected_version'], token=before['token'], selection=selection(source))


def revise(p, source, ratio):
    data = source['data']
    data['nodes'][-1]['numerator'] = ratio
    draft = engineering_post(p, f"/boms/{source['id']}", command(expected_version=source['version'], data=data))
    return engineering_post(p, f"/boms/{source['id']}/approve", command(expected_version=draft['version']))


def test_engineering_projection_order_supply_and_historical_version(handoff):
    p = handoff
    source, stock_material = setup_bom(p)
    choices = p.get(endpoint(source), params={'factory_id': 'huakang-c', 'version': source['version']}).json()
    assert choices['source']['version'] == 2 and [(r['key'], r['quantity']) for r in choices['rows']] == [('part', '2'), ('fabric', '1/2')]
    body = publish_body(p, source)
    path = endpoint(source, '/publish')
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: p.post(path, json=body), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    execution = responses[0].json()
    assert execution == responses[1].json()
    assert execution['data']['engineering_source']['version'] == source['version']
    assert execution['data']['engineering_source']['materials'][0]['path_keys'] == ['root', 'part', 'fabric']
    assert execution['data']['parts'][0]['pieces_per_set'] == 2
    assert execution['data']['requirements'][0]['quantity_per_set'] == '0.500000'
    assert p.post(path, json=body | {'operation_id': command()['operation_id']}).status_code == 409
    edited = dict(execution['data'])
    edited.pop('engineering_source')
    assert p.put(f"/api/cutting-operations/masters/{execution['id']}", json=command(
        expected_version=execution['version'], code=execution['code'], kind='bom', data=edited)).status_code == 409

    row = read(p)
    bound = post(p, 'bom', expected_version=row['current']['version'], bom_id=execution['id'],
                 bom_version=execution['version'], target_sets=50, quantity_basis='合成订单每套按两件核定')
    assert bound.status_code == 200, bound.text
    row = post(p, 'requisition', expected_version=bound.json()['current']['version'], lines=[dict(row=0, quantity='25')]).json()
    reply = post(p, 'eta', expected_version=row['current']['version'], requisition_version=row['current']['data']['requisition']['version'],
                 batches=[batch(quantity='25') | {'expected_date': '2026-10-12'}])
    assert reply.status_code == 200, reply.text
    scheduled = save(p, [task(resource(p))])
    assert scheduled.status_code == 200, scheduled.text
    published = publish(p)
    assert published.status_code == 200, published.text

    with Session(p.engine) as db:
        db.add(FabricMasterRecord(id='bin', factory_id='huakang-c', kind='LOCATION', code='A01', name='A01',
                                 status='ACTIVE', revision=1, data_json=json.dumps(dict(warehouse='一仓', category='FABRIC')),
                                 updated_at='2026-10-10'))
        db.commit()
    p.stock_id = warehouse_post(p, 'RECEIPT', quantity='30', source_no='engineering-stock', source_line='1',
                               item_code='01-01', item_name='蓝布', unit='米', location_id='bin', lot='LOT-ENG',
                               counterparty='合成供应商')['id']
    request = send(p, 'request', request_body(p) | {'material_id': stock_material['id'], 'material_revision': stock_material['version']})
    issued = issue(p, request)
    send(p, 'receive', decision(p, issued, quantity='2.5'))
    assert ledger(p)['requests'][0]['issues'][0]['received_quantity'] == '2.5'
    assert warehouse_view(p)['stock'][0]['quantity'] == '26'

    newer = revise(p, source, '0.5')
    replacement = p.post(path, json=publish_body(p, newer))
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()['id'] == execution['id'] and replacement.json()['version'] == execution['version'] + 1
    assert replacement.json()['data']['requirements'][0]['quantity_per_set'] == '1.000000'
    old = read(p)['current']['data']
    assert old['bom'] == execution and old['planning']['published'] == published.json()['current']['data']['planning']['published']
    assert p.get(endpoint(source), params={'factory_id': 'huakang-c', 'version': source['version']}).status_code == 409
    assert p.post(path, json=body).json() == execution


def test_preview_fences_source_changes_and_requires_combined_permissions(handoff):
    p = handoff
    source, _ = setup_bom(p)
    body = publish_body(p, source)
    path = endpoint(source, '/publish')
    authorized = p.cutting_auth['user']
    p.cutting_auth['user'] = engineer()
    assert p.post(path, json=body).status_code == 403
    p.cutting_auth['user'] = actor('bom_write', 'bom_publish')
    assert p.post(path, json=body).status_code == 403
    p.cutting_auth['user'] = authorized
    assert p.get(endpoint(source), params={'factory_id': 'huakang-a', 'version': 2}).status_code == 422
    newer = revise(p, source, '0.0000001')
    assert p.post(path, json=body).status_code == 409
    assert p.post(endpoint(newer, '/preview'), params={'factory_id': 'huakang-c'}, json=selection(newer)).status_code == 422


def test_projection_checks_current_cutting_material_at_confirmation(handoff):
    p = handoff
    source, _ = setup_bom(p)
    body = publish_body(p, source)
    path = endpoint(source, '/publish')
    material = p.get('/api/cutting-operations/masters', params={
        'factory_id': 'huakang-c', 'kind': 'material', 'q': '01-01',
    }).json()['data'][0]
    update = material_body('01-01')
    update['expected_version'] = material['version']
    update['data']['unit'] = '码'
    revised = p.put(f"/api/cutting-operations/masters/{material['id']}", json=update)
    assert revised.status_code == 200, revised.text
    stale = p.post(path, json=body)
    assert stale.status_code == 422 and '单位' in stale.json()['detail']
    choices = p.get(endpoint(source), params={'factory_id': 'huakang-c', 'version': source['version']}).json()
    assert choices['existing'] is None
