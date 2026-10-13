"""Business-flow regressions using isolated synthetic records only."""
import os
os.environ.setdefault('DATABASE_URL', 'sqlite://')

import base64
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal
from io import BytesIO
from uuid import uuid4
from zipfile import ZipFile

import openpyxl
import pytest
from PIL import Image
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from lxml import etree as ET
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api import indonesia_materials as api
from app.db import get_db
from app.models.indonesia_materials import IndonesiaMaterialRecord as Record, IndonesiaMaterialCommand as Receipt, IndonesiaMaterialAsset as Asset
from app.models.auth import AuthIamState
from app.services import indonesia_materials as service
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext, get_current_user
from app.services.indonesia_material_calculations import packaging_totals, production_plan
from app.services.indonesia_material_excel import TEMPLATE, NS, DRAWING_PART, SHEET_PART
from app.services.permission_codes import INDONESIA_MATERIAL_PERMISSION_CODES

BASE = '/api/indonesia-materials'


def actor(*actions, factory='huaxing', department='sales-business'):
    codes = frozenset('indonesia_material:' + a for a in actions)
    grant = AuthGrantContext(role_id='synthetic', role_name='测试角色', factory_id=factory, department=department, permissions=codes)
    return AuthContext(id='synthetic-user', username='synthetic', display_name='合成测试', roles=('test',), role_codes=('test',),
                       permissions=codes, factory_scopes=(factory,), department_scopes=(department,), grants=(grant,),
                       active_permission_codes=frozenset(INDONESIA_MATERIAL_PERMISSION_CODES))


@pytest.fixture
def client(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + (tmp_path / 'materials.db').as_posix(),
                           connect_args={'check_same_thread': False, 'timeout': 20})
    Record.metadata.create_all(engine, tables=list(service.TABLES))
    AuthIamState.__table__.create(engine)
    with Session(engine) as db:
        db.add(AuthIamState(key='identity_mutation_lock', value_json='{}'))
        db.commit()
    auth = {'user': actor('read', 'write', 'receipt_confirm', 'export')}
    def session():
        with Session(engine, expire_on_commit=False) as db:
            yield db
    # Parse behavior is separately covered; API tests do not launch subprocesses.
    async def run_job(function, *args, db=None, **kwargs):
        if db:
            db.rollback()
        return function(*args, **kwargs)
    monkeypatch.setattr(api, 'run_order_job', run_job)
    monkeypatch.setattr(api, 'refresh_user', lambda request, db: auth['user'])
    app = FastAPI(); app.include_router(api.router)
    app.dependency_overrides[get_db] = session
    app.dependency_overrides[get_current_user] = lambda: auth['user']
    with TestClient(app) as test:
        test.engine, test.materials_auth = engine, auth
        yield test
    engine.dispose()


def command(client, action, data, row=None, *, factory='huaxing', status=200, operation_id=None):
    body = dict(factory_id=factory, operation_id=operation_id or uuid4().hex, action=action, data=data,
                entity_id=row['id'] if row else None, expected_version=row['version'] if row else 0)
    response = client.post(BASE + '/commands', json=body)
    assert response.status_code == status, response.text
    return response.json()['record'] if status == 200 else response


def material(client, code='00001', **changes):
    image = BytesIO(); Image.new('RGB', (4, 4), 'green').save(image, 'PNG')
    data = dict(code=code, name='合成螺丝', english_name='Synthetic screw', specification='TEST', category='辅助材料',
                unit='PCS', customs_unit='KGM', net_weight_kg='.001', billing_weight_kg='.002',
                price='.10', billing_unit='PCS', currency='USD', procurement_days=18,
                supplier='合成供应商', usage='合成测试装配', department='合成装配部门', export_company='合成出口公司',
                image_data='data:image/png;base64,' + base64.b64encode(image.getvalue()).decode())
    return command(client, 'material_save', data | changes)


def product(client, m, code='ITEM01', **changes):
    return command(client, 'product_save', dict(code=code, customer='合成客户', daily_capacity='10',
                    materials=[dict(material_id=m['id'], usage='1')]) | changes)


def order(client, m=None, contract='TEST-A', quantity='100', **changes):
    return command(client, 'order_save', dict(customer='合成客户', recipient='RRI', contract_no=contract,
                    item_no='ITEM01', batch='1', quantity=quantity, delivery_date='2026-11-30') | changes)


def supply(client, m, normal='90', spare='10', **changes):
    return command(client, 'supply_save', dict(material_id=m['id'], purchase_no='PO-TEST', purchase_line='0001',
                    purchase_date='2026-10-01', supplier='合成供应商', purchase_quantity='100', normal_quantity=normal,
                    spare_quantity=spare, batch='SUPPLY-1', price='.10', currency='USD', promised_date='2026-10-21') | changes)


def allocation(client, sup, ord, normal='90', spare='10', **changes):
    return command(client, 'allocate', dict(supply_id=sup['id'], order_id=ord['id'], demand_id=ord['data']['demands'][0]['id'],
                    normal_quantity=normal, spare_quantity=spare) | changes)


def received_flow(client, quantity='100'):
    m = material(client); p = product(client, m); o = order(client, quantity=quantity)
    sup = supply(client, m)
    sup = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    return m, p, o, sup


def shipment(client, alloc, normal='9', spare='1', **changes):
    item = dict(allocation_id=alloc['id'], normal_quantity=normal, spare_quantity=spare)
    package = dict(label='合成测试箱', cartons=1, length_cm='27', width_cm='14.5', height_cm='27.3',
                   carton_weight_kg='.020', items=[item])
    return command(client, 'shipment_save', dict(customer='合成客户', recipient='RRI', shipment_date='2026-10-23',
                                                lines=[item], packages=[package]) | changes)


def workspace(client):
    response = client.get(BASE + '/workspace', params={'factory_id': 'huaxing'})
    assert response.status_code == 200, response.text
    return response.json()


def test_production_workdays_and_natural_days():
    plan = production_plan('100', '10', '2026-11-30', 25)
    assert plan == dict(production_days=10, start_date='2026-11-16', dispatch_date='2026-10-22',
                        required_date='2026-10-22', transport_days=25, preparation_days=0)
    assert production_plan('101', '10', '2026-11-30', 25)['production_days'] == 11
    assert production_plan('100', None, '2026-11-30', 25) is None


def test_empty_real_workspace_and_factory_scope(client):
    assert workspace(client)['records'] == []
    assert client.get(BASE + '/workspace?factory_id=group').status_code == 422
    assert client.get(BASE + '/workspace?factory_id=huakang-a').status_code == 403
    assert client.get(BASE + '/workspace?factory_id=huaxing&factory_id=huakang-a').status_code == 422
    m = material(client)
    client.materials_auth['user'] = actor('read', 'write', factory='huakang-a')
    assert command(client, 'material_save', m['data'], m, factory='huakang-a', status=404).status_code == 404


def test_manual_demand_and_pinned_master_recalculation(client):
    m = material(client); p = product(client, m)
    o = order(client, quantity='100')
    d = o['data']['demands'][0]
    assert d['computed_quantity'] == '100'
    assert d['purchase_start'] == '2026-10-04'
    o = command(client, 'demand_adjust', dict(demand_id=d['id'], quantity='120.12345678', reason='合成调整'), o)
    p = command(client, 'product_save', p['data'] | {'materials': [{'material_id': m['id'], 'usage': '2'}]}, p)
    assert workspace(client)['board'][0]['demands'][0]['computed_quantity'] == '100'
    o = command(client, 'order_recalculate', {'reason': '合成显式重算'}, o)
    assert o['data']['demands'][0]['computed_quantity'] == '200'
    assert o['data']['demands'][0]['quantity'] == '120.12345678'
    assert o['data']['demands'][0]['id'] == d['id']


def test_missing_capacity_does_not_hide_actual_complete(client):
    m = material(client, procurement_days=None); product(client, m, daily_capacity=None)
    o = order(client); sup = supply(client, m)
    allocation(client, sup, o)
    assert workspace(client)['board'][0]['status'] == 'missing_parameters'
    command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    board = workspace(client)['board'][0]
    assert board['status'] == 'complete' and board['planning_status'] == 'missing_parameters'


def test_reply_does_not_receive_or_hide_late_risk(client):
    m = material(client); product(client, m); o = order(client); sup = supply(client, m)
    allocation(client, sup, o)
    sup = command(client, 'supply_reply', {'promised_date': '2026-10-25', 'reason': '来料仓合成回复'}, sup)
    row = workspace(client)['board'][0]
    assert row['status'] == 'shortage' and row['demands'][0]['coverage'] == '0'
    assert row['demands'][0]['risk'] == 'late' and row['plan']['required_date'] == '2026-10-22'
    assert sup['data']['status'] == 'expected' and sup['data']['actual_date'] is None


def test_receipt_independent_permission_and_explicit_deny(client):
    m = material(client); sup = supply(client, m)
    client.materials_auth['user'] = actor('read', 'write')
    command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup, status=403)
    client.materials_auth['user'] = actor('read', 'receipt_confirm', department='pmc-warehouse')
    command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    command(client, 'material_save', m['data'], m, status=403)
    deny = AuthOverrideContext(id='test-deny', permission_code='indonesia_material:read', factory_id='huaxing', department='*', effect='deny')
    client.materials_auth['user'] = replace(actor('read', 'write'), overrides=(deny,))
    assert client.get(BASE + '/workspace?factory_id=huaxing').status_code == 403


def test_purchase_cap_includes_free_spares_and_all_batches(client):
    m = material(client); supply(client, m)
    command(client, 'supply_save', dict(material_id=m['id'], purchase_no='PO-TEST', purchase_line='0001', purchase_date='2026-10-01',
                    supplier='合成供应商', purchase_quantity='100', normal_quantity='1', spare_quantity='0', batch='SUPPLY-2', price='.1'), status=409)
    assert len([r for r in workspace(client)['records'] if r['kind'] == 'supply']) == 1


def test_allocations_do_not_double_reserve_and_failed_reallocate_rolls_back(client):
    m, _, a, sup = received_flow(client, quantity='50')
    b = order(client, contract='TEST-B', quantity='50')
    alloc_a = allocation(client, sup, a, normal='50', spare='0')
    allocation(client, sup, b, normal='40', spare='10')
    command(client, 'allocate', dict(supply_id=sup['id'], order_id=a['id'], demand_id=a['data']['demands'][0]['id'],
                                    normal_quantity='1', spare_quantity='0'), status=409)
    command(client, 'reallocate', dict(order_id=b['id'], demand_id=b['data']['demands'][0]['id'], normal_quantity='10', spare_quantity='0', reason='测试超配'), alloc_a, status=409)
    original = next(r for r in workspace(client)['records'] if r['id'] == alloc_a['id'])
    assert original['version'] == 1 and original['data']['normal_quantity'] == '50'


def test_reallocate_unshipped_reopens_original_shortage(client):
    m, _, a, sup = received_flow(client, quantity='50')
    b = order(client, contract='TEST-B', quantity='50')
    alloc = allocation(client, sup, a, normal='50', spare='0')
    command(client, 'reallocate', dict(order_id=b['id'], demand_id=b['data']['demands'][0]['id'], normal_quantity='10', spare_quantity='0', reason='测试调整'), alloc)
    board = {r['contract_no']: r for r in workspace(client)['board']}
    assert board['TEST-A']['demands'][0]['shortage'] == '10'
    assert board['TEST-B']['demands'][0]['coverage'] == '10'


def test_version_conflicts_and_exact_request_replay(client):
    m = material(client)
    updated = command(client, 'material_save', m['data'] | {'name': '合成新版'}, m)
    command(client, 'material_save', m['data'], m, status=409)
    op = uuid4().hex
    first = command(client, 'material_save', updated['data'] | {'name': '合成再次修订'}, updated, operation_id=op)
    replay = command(client, 'material_save', updated['data'] | {'name': '合成再次修订'}, updated, operation_id=op)
    assert replay == first
    command(client, 'material_save', updated['data'] | {'name': '错误复用'}, updated, operation_id=op, status=409)


def test_confirm_export_is_immutable_and_normal_shipment_preserves_fulfilment(client):
    _, _, o, sup = received_flow(client)
    alloc = allocation(client, sup, o)
    draft = shipment(client, alloc)
    op = uuid4().hex
    confirmed = command(client, 'shipment_confirm', {}, draft, operation_id=op)
    assert command(client, 'shipment_confirm', {}, draft, operation_id=op) == confirmed
    assert workspace(client)['board'][0]['status'] == 'complete'
    assert confirmed['data']['packing_totals']['lines'][alloc['id']]['gross_weight_kg'] == '.030' or Decimal(confirmed['data']['packing_totals']['lines'][alloc['id']]['gross_weight_kg']) == Decimal('.030')
    file_a = client.get(BASE + f'/shipments/{confirmed["id"]}/export?factory_id=huaxing')
    file_b = client.get(BASE + f'/shipments/{confirmed["id"]}/export?factory_id=huaxing')
    assert file_a.content == file_b.content and file_a.status_code == 200
    record = next(r for r in workspace(client)['records'] if r['id'] == alloc['id'])
    assert record['data']['shipped_normal'] == '9' and record['data']['shipped_spare'] == '1'
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 1
    wb = openpyxl.load_workbook(BytesIO(file_a.content), data_only=True)
    sheet = wb[SHEET_NAME := '5.21出货明细']
    assert sheet['L4'].value == 9 and sheet['K4'].value == .01
    assert sheet['AP4'].value == .9 and sheet['P4'].value == .03
    summary = confirmed['data']['supplier_summary']
    assert len(summary) == 1 and summary[0]['materials'] == 1
    assert summary[0]['amount'] == '0.90'
    assert next(r for r in workspace(client)['records'] if r['id'] == confirmed['id'])['data']['supplier_summary'] == summary
    assert all(sheet[f'{col}4'].value is None for col in ('B', 'C', 'E', 'N', 'O', 'V', 'Z', 'AA', 'AG'))
    assert sheet['AS4'].value == '華登製品實業有限公司'
    assert '备品 1 PCS，免费' in sheet['BE4'].value
    assert all(wb[name].sheet_state == 'hidden' for name in wb.sheetnames if name != SHEET_NAME)
    # The latest request removes tutorial images; only this shipment's actual photo survives.
    with ZipFile(BytesIO(file_a.content)) as exported, ZipFile(TEMPLATE) as template:
        assert exported.read('xl/styles.xml') == template.read('xl/styles.xml')
        drawing = ET.fromstring(exported.read(DRAWING_PART))
        assert len(drawing.findall('.//xdr:pic', NS)) == 1
        assert len([n for n in exported.namelist() if n.startswith('xl/media/')]) == 1
        assert not any(n in exported.namelist() for n in ('xl/worksheets/sheet1.xml', 'xl/worksheets/sheet3.xml'))
    client.materials_auth['user'] = actor('read')
    assert client.get(BASE + f'/shipments/{confirmed["id"]}/export?factory_id=huaxing').status_code == 403
    assert client.get(BASE + f'/assets/{confirmed["data"]["export_asset_id"]}?factory_id=huaxing').status_code == 403


def test_draft_packages_require_separate_normal_and_spare_reconciliation(client):
    _, _, o, sup = received_flow(client); alloc = allocation(client, sup, o)
    draft = shipment(client, alloc)
    changed = deepcopy(draft['data']); changed.pop('status'); changed['packages'][0]['items'][0].update(normal_quantity='10', spare_quantity='0')
    draft = command(client, 'shipment_save', changed, draft)
    command(client, 'shipment_confirm', {}, draft, status=422)
    assert next(r for r in workspace(client)['records'] if r['id'] == draft['id'])['data']['status'] == 'draft'


def test_mixed_carton_can_confirm_once_with_frozen_material_rows(client):
    m = material(client); other = material(client, code='00002')
    product(client, m, materials=[dict(material_id=x['id'], usage='1') for x in (m, other)])
    o = order(client)
    selected = []
    for i, entry in enumerate((m, other)):
        sup = supply(client, entry, purchase_line=str(i+1))
        sup = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
        a = allocation(client, sup, o, demand_id=o['data']['demands'][i]['id'])
        selected.append(dict(allocation_id=a['id'], normal_quantity='3', spare_quantity='1'))
    draft = command(client, 'shipment_save', dict(customer='合成客户', recipient='RRI', shipment_date='2026-10-23',
                    lines=selected, packages=[dict(label='真实混箱', cartons=1, length_cm='27', width_cm='14.5',
                    height_cm='27.3', carton_weight_kg='.02', items=selected)]))
    confirmed = command(client, 'shipment_confirm', {}, draft)
    assert confirmed['data']['export_material_count'] == 2 and confirmed['data']['export_layout_version'] == 'material_row_v2'
    content = client.get(BASE + f'/shipments/{draft["id"]}/export?factory_id=huaxing').content
    sheet = openpyxl.load_workbook(BytesIO(content), data_only=True)['5.21出货明细']
    assert {str(r) for r in sheet.merged_cells.ranges} >= {'AT4:AT5', 'S4:S5'}
    assert sheet['AT4'].value == 1 and sheet['AT5'].value is None
    assert sheet['P4'].value == pytest.approx(.014) and sheet['P5'].value == pytest.approx(.014)


@pytest.mark.parametrize('conflict', ['dimensions', 'currency'])
def test_export_conflicts_leave_draft_and_allocation_unshipped(client, conflict):
    m, _, o, sup = received_flow(client); a = allocation(client, sup, o)
    selected = [dict(allocation_id=a['id'], normal_quantity='9', spare_quantity='1')]
    packages = [dict(label='整箱', cartons=1, length_cm='27', width_cm='14.5', height_cm='27.3',
                     carton_weight_kg='.02', items=deepcopy(selected))]
    if conflict == 'dimensions':
        packages[0]['items'] = [dict(allocation_id=a['id'], normal_quantity='5', spare_quantity='0')]
        packages.append(dict(label='尾箱', cartons=1, length_cm='28', width_cm='14.5', height_cm='27.3',
                             carton_weight_kg='.02', items=[dict(allocation_id=a['id'], normal_quantity='4', spare_quantity='1')]))
    else:
        other = material(client, code='00002'); product(client, other, code='ITEM02')
        other_order = order(client, contract='TEST-B', item_no='ITEM02')
        source = supply(client, other, purchase_line='2', currency='CNY')
        source = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, source)
        other_a = allocation(client, source, other_order)
        selected.append(dict(allocation_id=other_a['id'], normal_quantity='9', spare_quantity='1'))
        packages.append(dict(label='第二物料', cartons=1, length_cm='27', width_cm='14.5', height_cm='27.3',
                             carton_weight_kg='.02', items=[selected[-1]]))
    draft = command(client, 'shipment_save', dict(customer='合成客户', recipient='RRI', shipment_date='2026-10-23',
                                                lines=selected, packages=packages))
    failure = command(client, 'shipment_confirm', {}, draft, status=422)
    assert ('尺寸' in failure.text or '长宽高' in failure.text) if conflict == 'dimensions' else '采购币种不一致' in failure.text
    records = {r['id']: r for r in workspace(client)['records']}
    assert records[draft['id']]['data']['status'] == 'draft'
    assert records[a['id']]['data']['shipped_normal'] == '0' and records[a['id']]['data']['shipped_spare'] == '0'
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 0


def test_weight_billing_uses_billable_weight_not_net_and_never_charges_spares(client):
    m = material(client); product(client, m); o = order(client)
    sup = supply(client, m, billing_basis='weight', billing_factor='1', price='100')
    sup = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    alloc = allocation(client, sup, o)
    confirmed = command(client, 'shipment_confirm', {}, shipment(client, alloc))
    line = confirmed['data']['snapshot_lines'][0]
    assert Decimal(line['amount']) == Decimal('1.8')  # 9 * .002 * 100, spare is free.
    assert Decimal(confirmed['data']['packing_totals']['lines'][alloc['id']]['net_weight_kg']) == Decimal('.01')


def test_mixed_carton_weight_ratio_and_cbm_precision():
    lines = {'a': dict(normal_quantity='6', spare_quantity='0', material={'net_weight_kg': '1'}),
             'b': dict(normal_quantity='4', spare_quantity='0', material={'net_weight_kg': '1'})}
    package = dict(label='混箱', cartons=1, length_cm='27', width_cm='14.5', height_cm='27.3', carton_weight_kg='1', pallet='999',
                   items=[dict(allocation_id=k, normal_quantity=q, spare_quantity='0') for k, q in [('a','6'),('b','4')]])
    calculated = packaging_totals([package], lines)
    assert Decimal(calculated['lines']['a']['gross_weight_kg']) == Decimal('6.6')
    assert Decimal(calculated['lines']['b']['gross_weight_kg']) == Decimal('4.4')
    package.update(cartons=53, carton_weight_kg='0')
    assert packaging_totals([package], lines)['cbm'] == '0.57'


def schedule_bytes(*, duplicate=False):
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = 'ITEM表'
    ws.append([]); ws.append([])
    ws.append(['CONTRACT NO.', 'SO#/REFERENCE', 'P/O#:', '产品编号', '数量', '客要求走货期', '客名'])
    ws.append(['TEST-I', 'SO-TEST', 'PO-TEST', '00001', 100, '2026-11-30', '合成客户'])
    if duplicate:
        ws.append(['TEST-I', 'SO-TEST', 'PO-TEST', '00001', 50, '2026-12-15', '合成客户'])
    stream = BytesIO(); wb.save(stream); return stream.getvalue()


def test_import_selected_rows_repeated_files_and_original_lineage(client):
    original = schedule_bytes()
    data = dict(factory_id='huaxing', customer='合成客户', recipient='RRI')
    result = client.post(BASE + '/imports/preview', data=data, files={'file': ('schedule.xlsx', original)})
    assert result.status_code == 200, result.text
    preview = result.json()['record']
    confirmed = command(client, 'import_confirm', {'indexes': [0]}, preview)
    repeated = client.post(BASE + '/imports/preview', data=data, files={'file': ('schedule.xlsx', original)})
    assert repeated.json()['record']['id'] == confirmed['id'] and repeated.json()['record']['data']['status'] == 'confirmed'
    rows = workspace(client)['records']; orders = [r for r in rows if r['kind'] == 'order']
    assert len(orders) == 1 and orders[0]['data']['item_no'] == '00001'
    assert orders[0]['data']['source']['sheet'] == 'ITEM表' and orders[0]['data']['source']['row'] == 4
    saved = client.get(BASE + f'/assets/{preview["data"]["asset_id"]}?factory_id=huaxing')
    assert saved.content == original


def test_ambiguous_delivery_rows_and_caches_are_blocked(client):
    result = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                         files={'file': ('schedule.xlsx', schedule_bytes(duplicate=True))})
    assert result.status_code == 200, result.text
    record = result.json()['record']
    assert all(r['blocked'] for r in record['data']['rows'])
    command(client, 'import_confirm', {'indexes': [0]}, record, status=422)
    assert not any(r['kind'] == 'order' for r in workspace(client)['records'])


def test_referenced_material_specification_and_units_are_identity(client):
    m = material(client, specification='M2'); product(client, m); order(client)
    command(client, 'material_save', m['data'] | {'specification': 'M3'}, m, status=422)
    command(client, 'material_save', m['data'] | {'unit': 'KGM'}, m, status=422)
    updated = command(client, 'material_save', m['data'] | {'english_name': 'Corrected description'}, m)
    assert updated['data']['specification'] == 'M2'


def test_explicit_output_refresh_fills_missing_data_but_preserves_known_weights(client):
    m = material(client, english_name='', image_data='', net_weight_kg=None, billing_weight_kg=None)
    product(client, m); o = order(client); sup = supply(client, m, billing_basis='weight', price='100')
    sup = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, sup)
    alloc = allocation(client, sup, o); draft = shipment(client, alloc)
    command(client, 'shipment_confirm', {}, draft, status=422)
    image = BytesIO(); Image.new('RGB', (4, 4), 'blue').save(image, 'PNG')
    m = command(client, 'material_save', m['data'] | dict(english_name='Completed description', net_weight_kg='.001',
        billing_weight_kg='.002', image_data='data:image/png;base64,' + base64.b64encode(image.getvalue()).decode()), m)
    sup = command(client, 'output_material_refresh', {'reason': '补齐缺失资料'}, sup)
    first = command(client, 'shipment_confirm', {}, draft)
    assert Decimal(first['data']['snapshot_lines'][0]['amount']) == Decimal('1.8')
    # Subsequent master corrections do not change known source measurements or an existing file.
    m = command(client, 'material_save', m['data'] | {'net_weight_kg': '.5', 'billing_weight_kg': '.7'}, m)
    sup = command(client, 'output_material_refresh', {'reason': '更新文字和图片版本'}, sup)
    second = command(client, 'shipment_confirm', {}, shipment(client, alloc, normal='1', spare='0'))
    # First explicit missing-measurement completion becomes this batch's fixed basis.
    assert Decimal(second['data']['snapshot_lines'][0]['material']['net_weight_kg']) == Decimal('.001')


def test_received_board_preserves_promised_and_actual_dates(client):
    m = material(client); product(client, m); o = order(client); sup = supply(client, m, promised_date='2026-10-25')
    allocation(client, sup, o)
    command(client, 'receipt_confirm', {'actual_date': '2026-10-26'}, sup)
    demand = workspace(client)['board'][0]['demands'][0]
    assert demand['promised_date'] == '2026-10-25' and demand['actual_date'] == '2026-10-26'
    assert demand['risk'] == 'late_received'


def test_reimport_previews_changes_and_allows_new_rows_independently(client):
    order(client, contract='TEST-I', item_no='00001', po_no='PO-TEST')
    wb = openpyxl.load_workbook(BytesIO(schedule_bytes())); sheet = wb['ITEM表']
    sheet['F4'] = '2026-12-15'
    sheet.append(['TEST-NEW', 'SO-NEW', 'PO-NEW', '00002', 50, '2026-12-15', '合成客户'])
    content = BytesIO(); wb.save(content)
    response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                           files={'file': ('changed.xlsx', content.getvalue())})
    record = response.json()['record']
    assert record['data']['rows'][0]['match_status'] == 'changed' and record['data']['rows'][0]['blocked']
    assert record['data']['rows'][0]['changes'][0]['field'] == 'delivery_date'
    assert record['data']['rows'][1]['match_status'] == 'new'
    command(client, 'import_confirm', {'indexes': [1]}, record)
    assert len(workspace(client)['board']) == 2


def test_partial_selected_import_can_be_completed_later(client):
    wb = openpyxl.load_workbook(BytesIO(schedule_bytes())); wb['ITEM表'].append(['TEST-B', 'SO-B', 'PO-B', '00002', 50, '2026-12-15', '合成客户'])
    content = BytesIO(); wb.save(content)
    response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                           files={'file': ('partial.xlsx', content.getvalue())})
    record = response.json()['record']
    partial = command(client, 'import_confirm', {'indexes': [0]}, record)
    assert partial['data']['status'] == 'partial'
    assert partial['data']['rows'][0]['imported_order_id']
    confirmed = command(client, 'import_confirm', {'indexes': [1]}, partial)
    assert confirmed['data']['status'] == 'confirmed' and len(confirmed['data']['order_ids']) == 2


def test_file_job_return_rechecks_current_authorization(client, monkeypatch):
    async def revoke_during_parse(function, *args, db=None, **kwargs):
        if db:
            db.rollback()
        result = function(*args, **kwargs)
        client.materials_auth['user'] = actor('read')
        return result
    monkeypatch.setattr(api, 'run_order_job', revoke_during_parse)
    response = client.post(BASE + '/imports/preview', data=dict(factory_id='huaxing', customer='合成客户', recipient='RRI'),
                           files={'file': ('revoked.xlsx', schedule_bytes())})
    assert response.status_code == 403
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 0
        assert db.scalar(select(func.count()).select_from(Record)) == 0


def test_concurrent_confirmations_never_over_ship(client):
    from concurrent.futures import ThreadPoolExecutor
    _, _, o, sup = received_flow(client); alloc = allocation(client, sup, o)
    drafts = [shipment(client, alloc, normal='60', spare='0') for _ in range(2)]
    bodies = [dict(factory_id='huaxing', operation_id=uuid4().hex, action='shipment_confirm', entity_id=d['id'],
                   expected_version=d['version'], data={}) for d in drafts]
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda body: client.post(BASE + '/commands', json=body), bodies))
    assert sorted(r.status_code for r in responses) == [200, 409]
    record = next(r for r in workspace(client)['records'] if r['id'] == alloc['id'])
    assert record['data']['shipped_normal'] == '60'
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == 1


def test_template_three_rows_keeps_guide_and_actual_photo_locations(client):
    _, _, o, sup = received_flow(client); alloc = allocation(client, sup, o)
    draft = shipment(client, alloc)
    data = deepcopy(draft['data']); data.pop('status')
    original_group = data['packages'][0]
    allocations = [alloc]
    for i in (2, 3):
        m = material(client, code=f'0000{i}')
        product(client, m, code=f'ITEM0{i}')
        other_order = order(client, contract=f'TEST-{i}', item_no=f'ITEM0{i}')
        source = supply(client, m, purchase_line=str(i))
        source = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, source)
        allocations.append(allocation(client, source, other_order))
    data['lines'] = [dict(allocation_id=a['id'], normal_quantity='3', spare_quantity='0') for a in allocations]
    data['packages'] = []
    for i, a in enumerate(allocations):
        group = deepcopy(original_group); group['label'] = f'分组 {i+1}'
        group['items'] = [dict(allocation_id=a['id'], normal_quantity='3', spare_quantity='0')]
        data['packages'].append(group)
    draft = command(client, 'shipment_save', data, draft)
    confirmed = command(client, 'shipment_confirm', {}, draft)
    response = client.get(BASE + f'/shipments/{confirmed["id"]}/export?factory_id=huaxing')
    formulas = openpyxl.load_workbook(BytesIO(response.content), data_only=False)
    sheet = formulas['5.21出货明细']
    assert sheet['R6'].value == '=AW6*AX6*AY6/28316.75*0.0283'
    assert sheet['AQ4'].value.startswith("=SUM('出货计算'!J")
    cached = openpyxl.load_workbook(BytesIO(response.content), data_only=True)['5.21出货明细']
    assert cached['AQ4'].value == pytest.approx(.9)
    with ZipFile(BytesIO(response.content)) as output, ZipFile(TEMPLATE) as template:
        source = ET.fromstring(template.read(SHEET_PART)); result = ET.fromstring(output.read(SHEET_PART))
        source_guide = source.find("s:sheetData/s:row[@r='7']/s:c[@r='L7']", NS)
        result_guide = result.find("s:sheetData/s:row[@r='8']/s:c[@r='L8']", NS)
        assert source_guide.get('s') == result_guide.get('s')
        assert source_guide.findtext('s:v',namespaces=NS) == result_guide.findtext('s:v',namespaces=NS)
        picture = ET.fromstring(output.read(DRAWING_PART)).findall('.//xdr:oneCellAnchor',NS)
        assert [p.findtext('xdr:from/xdr:row',namespaces=NS) for p in picture] == ['3','4','5']
        assert all(p.findtext('xdr:from/xdr:col',namespaces=NS) == '19' for p in picture)


def test_migration_is_explicit_and_evidence_is_immutable(tmp_path):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    path = Path(__file__).parents[1] / 'alembic/versions/20261013_0160_indonesia_materials.py'
    spec = importlib.util.spec_from_file_location('materials_migration', path)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine('sqlite:///' + (tmp_path/'migration.db').as_posix())
    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert service.ready(Session(bind=connection)) is None
        connection.execute(text("INSERT INTO indonesia_material_assets VALUES ('a','huaxing','synthetic.xlsx','test','digest',X'01','2026-10-13')"))
        with pytest.raises(IntegrityError, match='immutable'):
            connection.execute(text("DELETE FROM indonesia_material_assets WHERE id='a'"))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match='拒绝'):
                migration.downgrade()
    engine.dispose()


def test_permission_catalog_does_not_expand_existing_positions():
    from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS, GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
    from app.services.iam_scope import READ_PERMISSION_CODES
    assert 'indonesia_material:read' in READ_PERMISSION_CODES
    assert set(INDONESIA_MATERIAL_PERMISSION_CODES) <= GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
    assert all(not (set(p.permission_codes) & set(INDONESIA_MATERIAL_PERMISSION_CODES)) for p in SYSTEM_POSITION_DEFINITIONS)


@pytest.mark.parametrize('change,status', [('revoke', 403), ('identity', 401), ('session', 401)])
def test_command_rechecks_identity_after_waiting_for_locks(client, monkeypatch, change, status):
    saved = material(client)
    original_lock = service.lock_transaction
    def changed_while_waiting(db, namespace, factory):
        original_lock(db, namespace, factory)
        if change == 'revoke':
            client.materials_auth['user'] = actor('read')
        elif change == 'identity':
            client.materials_auth['user'] = replace(client.materials_auth['user'], id='other-user')
        else:
            def expired(request, db):
                raise HTTPException(401, '登录已失效')
            monkeypatch.setattr(api, 'refresh_user', expired)
    monkeypatch.setattr(service, 'lock_transaction', changed_while_waiting)
    data = {key: value for key, value in saved['data'].items() if key in api.service.s.Material.model_fields}
    data['name'] = '不得保存的变更'
    command(client, 'material_save', data, saved, status=status)
    with Session(client.engine) as db:
        assert db.get(Record, saved['id']).data['name'] == saved['data']['name']
        assert db.scalar(select(func.count()).select_from(Receipt)) == 1


def test_receipt_rechecks_revocation_and_replay_never_bypasses_it(client, monkeypatch):
    saved = material(client)
    batch = supply(client, saved)
    operation = uuid4().hex
    body = dict(factory_id='huaxing', operation_id=operation, action='receipt_confirm',
                entity_id=batch['id'], expected_version=batch['version'], data={'actual_date':'2026-10-22'})
    assert client.post(BASE+'/commands', json=body).status_code == 200
    original_lock = service.lock_transaction
    def revoke_after_lock(db, namespace, factory):
        original_lock(db, namespace, factory)
        client.materials_auth['user'] = actor('read', 'write')
    monkeypatch.setattr(service, 'lock_transaction', revoke_after_lock)
    assert client.post(BASE+'/commands', json=body).status_code == 403
    with Session(client.engine) as db:
        assert db.scalar(select(func.count()).select_from(Receipt)) == 3


def test_fully_reallocated_old_supply_does_not_pollute_current_dates(client):
    m = material(client); product(client, m)
    a = order(client, contract='TEST-A', quantity='50'); b = order(client, contract='TEST-B', quantity='50')
    old = supply(client, m, normal='50', spare='0', promised_date='2026-10-25')
    old = command(client, 'receipt_confirm', {'actual_date': '2026-10-26'}, old)
    alloc = allocation(client, old, a, normal='50', spare='0')
    command(client, 'reallocate', dict(order_id=b['id'], demand_id=b['data']['demands'][0]['id'], normal_quantity='50', spare_quantity='0', reason='全部改绑'), alloc)
    new = supply(client, m, normal='50', spare='0', batch='SUPPLY-2', promised_date='2026-10-21')
    new = command(client, 'receipt_confirm', {'actual_date': '2026-10-22'}, new)
    allocation(client, new, a, normal='50', spare='0')
    current = next(r for r in workspace(client)['board'] if r['id'] == a['id'])['demands'][0]
    assert current['risk'] == 'received' and current['promised_date'] == '2026-10-21' and current['actual_date'] == '2026-10-22'
