"""Exercise the engineering-to-cutting handoff through the existing order and warehouse APIs."""
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from openpyxl import Workbook
from sqlalchemy.orm import Session

from app.api import engineering_bom, fabric_procurement, warehouse_operations
from app.models.cutting_ops import CuttingOrderRevision
from app.models.fabric_master import FabricMasterRecord
from app.models.warehouse_operations import WarehouseOperation
from app.services.auth import AuthGrantContext
from app.services.cutting_purchase_links import display_batches
from test_cutting_materials import actor, decision, issue, ledger, request_body, send, warehouse_post, warehouse_view
from test_cutting_ops import client, command, create, material_body
from test_cutting_orders import batch, flow, post, read
from test_cutting_planning import publish, resource, save, task
from test_engineering_bom import BASE, migration, post as engineering_post, user as engineer
from test_fabric_procurement import FIELDS as PURCHASE_FIELDS, row as purchase_row, stored
from test_fabric_procurement_tracking import save as import_purchases
from test_fabric_receiving import receive as receive_purchase, request as purchase_receipt
from warehouse_location_fixtures import seed_fabric_locations


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


def test_split_purchase_arrivals_issues_and_cutting_signatures(handoff):
    """Use original purchase receipt batches rather than seeding available stock."""
    p = handoff
    p.app.include_router(fabric_procurement.router)
    cutting_actor = actor('material_request', 'material_receive', 'plan_write', 'plan_publish',
                          warehouse=False, department='production')
    warehouse_permissions = frozenset({
        'fabric_warehouse:read', 'fabric_warehouse:import', 'fabric_warehouse:receive',
        'fabric_operations:read', 'fabric_operations:operate',
    })
    warehouse_actor = replace(
        actor(warehouse=False, department='pmc-warehouse'),
        id='receiving-clerk',
        permissions=warehouse_permissions,
        active_permission_codes=warehouse_permissions,
        grants=(AuthGrantContext(role_id='fabric', role_name='布料仓', factory_id='huakang-c',
                                 department='pmc-warehouse', permissions=warehouse_permissions),),
    )
    source, stock_material = setup_bom(p, ratio='0.065')
    execution = engineering_post(p, f"/boms/{source['id']}/cutting/publish", publish_body(p, source))
    order = post(p, 'bom', expected_version=read(p)['current']['version'], bom_id=execution['id'],
                 bom_version=execution['version'], target_sets=50, quantity_basis='合成订单核定50套')
    assert order.status_code == 200, order.text
    demand = post(p, 'requisition', expected_version=order.json()['current']['version'], lines=[dict(row=0, quantity='6.5')])
    assert demand.status_code == 200, demand.text
    current = demand.json()['current']
    eta = post(p, 'eta', expected_version=current['version'], requisition_version=current['data']['requisition']['version'],
               batches=[batch(quantity=q) | dict(purchase_reference='PO-001', expected_date=day)
                        for q, day in [('3', '2026-10-10'), ('3.5', '2026-10-12')]])
    assert eta.status_code == 200, eta.text
    executor = resource(p)
    draft = save(p, [task(executor)])
    assert draft.status_code == 200, draft.text
    initial_plan = publish(p)
    assert initial_plan.status_code == 200, initial_plan.text
    baseline = initial_plan.json()['current']['data']['planning']['baseline']
    original_promises = eta.json()['current']['data']['batches']

    with Session(p.engine) as db:
        seed_fabric_locations(db)
    tracking_file = Workbook()
    worksheet = tracking_file.active
    worksheet.title = '未回物料'
    headers = [*PURCHASE_FIELDS, '供应商复期']
    worksheet.append(headers)
    purchase_data = purchase_row(
        订单号='PO-001', 采购明细ID='SPLIT-1', 供应商='合成供应商', 物料编码='01-01',
        物料名称='蓝布', 基本单位='米', 订单数量=6.5, 入库数量=0, 交货明细='', 供应商复期='2026-10-12',
    )
    worksheet.append([purchase_data.get(field) for field in headers])
    content = BytesIO()
    tracking_file.save(content)
    tracking_file.close()
    p.cutting_auth['user'] = warehouse_actor
    import_purchases(p, content.getvalue())
    purchase = stored(p)['items'][0]
    assert purchase['promise_date'] == '2026-10-12'
    assert Decimal(purchase['warehouse_outstanding_quantity']) == Decimal('6.5')
    assert warehouse_view(p)['stock'] == []

    params = dict(factory_id='huakang-c', row=0, reference='PO-001', supplier='合成供应商')
    lookup = '/api/cutting-operations/orders/line-1/purchase-candidates'
    progress = '/api/cutting-operations/orders/line-1/purchase-progress?factory_id=huakang-c'
    # Source lookup needs both procurement-side grants; a cutting reader only
    # sees whitelisted quantities for a saved association.
    assert p.get(lookup, params=params).status_code == 403
    eta_permissions = warehouse_permissions | {'cutting_ops:read', 'cutting_ops:eta_write'}
    eta_actor = replace(warehouse_actor, permissions=eta_permissions, active_permission_codes=eta_permissions,
                        grants=(replace(warehouse_actor.grants[0], permissions=eta_permissions),))
    p.cutting_auth['user'] = eta_actor
    assert p.get(lookup, params=params | {'factory_id': 'huaxing'}).status_code == 422
    assert p.get(lookup, params=params | {'reference': 'UNKNOWN'}).json() == {'items': []}
    matched = p.get(lookup, params=params).json()['items']
    assert matched == [dict(id=purchase['id'], revision=purchase['revision'], detail_no='SPLIT-1',
                            production_no='P001', quantity='6.5', unit='米')]
    link = {k: matched[0][k] for k in ('id', 'revision')}
    promises = [dict(b, purchase_source=link) for b in original_promises]
    eta_command = command(expected_version=read(p)['current']['version'], requisition_version=current['data']['requisition']['version'],
                          batches=promises)
    eta_url = '/api/cutting-operations/orders/line-1/eta'
    assert p.post(eta_url, json=eta_command | {'batches': [dict(promises[0], purchase_reference='WRONG')]}).status_code == 422
    assert p.post(eta_url, json=eta_command | {'batches': [dict(promises[0], purchase_source=link | {'revision': 99})]}).status_code == 409
    linked_reply = p.post(eta_url, json=eta_command)
    assert linked_reply.status_code == 200, linked_reply.text
    assert linked_reply.json()['current']['data']['batches'] == promises
    assert not linked_reply.json()['planning_summary']['published_stale']
    assert p.post(eta_url, json=eta_command).json() == linked_reply.json()
    linked_version = linked_reply.json()['current']['version']
    history = p.get('/api/cutting-operations/orders/line-1/versions', params={'factory_id': 'huakang-c'})
    assert history.json()['data'][0]['data']['batches'] == promises
    with Session(p.engine) as db:
        stored_revision = db.get(CuttingOrderRevision, ('line-1', linked_version)).data
        assert stored_revision['batches'] == original_promises
        legacy_edit = dict(stored_revision, batches=[dict(original_promises[0], expected_date='2026-10-13')])
        assert display_batches(legacy_edit) == legacy_edit['batches']

    p.cutting_auth['user'] = cutting_actor
    assert p.get(lookup, params=params).status_code == 403
    requisition = send(p, 'request', request_body(p) | {
        'material_id': stock_material['id'], 'material_revision': stock_material['version'],
    })
    signatures = []
    for index, (quantity, day, outstanding, signed_total) in enumerate([
        ('3', '2026-10-10', '3.5', '3'), ('3.5', '2026-10-12', '0', '6.5'),
    ], start=1):
        p.cutting_auth['user'] = warehouse_actor
        body = purchase_receipt(purchase, receipt_date=day, delivery_reference=f'DN-SPLIT-{index}',
                                delivery_quantity=quantity,
                                batches=[dict(quantity=quantity, location='A01', dye_lot=f'LOT-{index}')])
        response = receive_purchase(p, purchase, body)
        assert response.status_code == 200, response.text
        inbound = response.json()
        assert receive_purchase(p, purchase, body).json() == inbound
        purchase = stored(p)['items'][0]
        assert Decimal(purchase['warehouse_outstanding_quantity']) == Decimal(outstanding)
        warehouse_batch = next(b for b in warehouse_view(p)['stock'] if b['id'] == inbound['batches'][0]['id'])
        assert warehouse_batch['receipt_origin']['source_line_id'] == purchase['id'] == inbound['source_line_id']
        assert warehouse_batch['receipt_origin']['id'] == inbound['id']

        issued = warehouse_post(p, 'ISSUE', original_id=requisition['id'], batch_id=warehouse_batch['id'],
                                quantity=quantity, counterparty='R01', business_date=day)
        movement = next(d for d in warehouse_view(p)['documents'] if d['id'] == issued['id'])
        assert movement['batch_snapshot']['receipt_origin']['id'] == inbound['id']
        p.cutting_auth['user'] = cutting_actor
        before = ledger(p)['totals'][0]
        assert Decimal(before['received_quantity']) == Decimal(signed_total) - Decimal(quantity)
        assert Decimal(before['issued_quantity']) == Decimal(signed_total)
        metrics = p.get(progress).json()
        assert len(metrics['sources']) == 1
        source_metrics = metrics['sources'][0]
        assert source_metrics['status'] == 'active'
        assert source_metrics['detail_no'] == 'SPLIT-1'
        assert Decimal(source_metrics['received_quantity']) == Decimal(signed_total)
        assert Decimal(source_metrics['outstanding_quantity']) == Decimal(outstanding)
        assert set(source_metrics) == {'id', 'row', 'order_no', 'detail_no', 'unit', 'status', 'linked_revision', 'current_revision',
                                       'received_quantity', 'outstanding_quantity'}
        assert Decimal(metrics['cutting'][0]['signed_quantity']) == Decimal(signed_total) - Decimal(quantity)
        signature = send(p, 'receive', decision(p, issued, quantity=quantity) | {'business_date': day})
        signatures.append(signature['id'])
        totals = ledger(p)['totals'][0]
        assert Decimal(totals['theoretical_quantity']) == Decimal('6.5')
        assert Decimal(totals['issued_quantity']) == Decimal(totals['received_quantity']) == Decimal(signed_total)
        assert Decimal(totals['outstanding_quantity']) == Decimal(outstanding)
        facts = read(p)['current']['data']
        assert facts['batches'] == promises
        assert facts['planning']['published']['tasks'][0]['date_basis'] == 'estimated'

    actual = task(executor, date_basis='actual', actual_issue_date='2026-10-12', material_receipt_ids=signatures,
                  actual_issue_reference='核对两次裁床签收')
    rejected = save(p, [actual | {'actual_issue_date': '2026-10-10'}], reason='排期核定')
    assert rejected.status_code == 422 and '最晚日期' in rejected.json()['detail']
    result = save(p, [actual], reason='核对两次裁床签收后修订')
    assert result.status_code == 200, result.text
    result = publish(p, reason='核对两次裁床签收后修订')
    assert result.status_code == 200, result.text
    plan = result.json()['current']['data']['planning']
    assert plan['baseline'] == baseline
    assert [item['id'] for item in plan['published']['tasks'][0]['material_receipts']] == signatures
    assert p.get(progress).json()['cutting'] == [dict(row=0, unit='米', signed_quantity='6.5', returned_quantity='0')]


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
