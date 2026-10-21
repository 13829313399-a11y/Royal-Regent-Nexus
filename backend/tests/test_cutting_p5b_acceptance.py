"""Joined P5b acceptance with real cookie sessions and least-privilege roles.

Only the source sales dispatch, reference warehouse catalog and IAM accounts are
fixture data. All cutting business transitions below use the real HTTP API.
Temporary SQLite is not evidence of production PostgreSQL or employee acceptance.
"""
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo
import json
import runpy

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from openpyxl import load_workbook
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api import auth as auth_api, warehouse_operations as warehouse_api
from app.core.config import settings
from app.models.auth import (AuthUser, AuthRole, AuthPermission, AuthRolePermission,
    AuthUserRole, EmployeeProfile, AuthIamState, AuthRoleBindingMetadata)
from app.models.identity import IamOrgUnit, IamOrgDepartment, EmployeeAssignment
from app.services.identity_sources import snapshot_role
from app.models.fabric_master import FabricMasterRecord
from app.services.auth import get_current_user, hash_password
from app.services import warehouse_operations as wh, cutting_planning as planning, cutting_exports
from test_cutting_ops import client, BASE, command, create, bom_body, state
from test_cutting_orders import flow, receive, post, batch, read as order_read
from app.services.cutting_planning_schemas import PlanTask
from test_cutting_planning import resource, task, save as plan_save, publish
from test_cutting_materials import (request_body, send as material_send,
    decision as material_decision, issue, warehouse_post, warehouse_view)
from test_cutting_reporting import send as report, read as reports, ok, doc
from test_cutting_usage import write, consume, read as usage_read
from test_cutting_cost_allocation import allocate
from test_cutting_periods import draft, act, get as period_read
from test_cutting_settlement import price, save as fee_save, decision as fee_decision, record
from test_cutting_payments import save as payment_save, body as payment_body, decision as payment_decision, read as payments


# Proposed acceptance roles only. No production role or employee is modified.
ROLE_ACTIONS = {
    'clerk': ('production', 'read order_receive material_request material_receive report_write return_write handover_write usage_write'),
    'supervisor': ('production', 'read master_write plan_write plan_publish report_review acceptance_write usage_review cost_read allocation_confirm period_prepare settlement_read settlement_price settlement_prepare'),
    'engineering': ('engineering', 'read bom_write bom_publish requisition_submit'),
    'procurement': ('pmc-warehouse', 'read eta_write requisition_reconcile cost_read cost_write'),
    'warehouse': ('pmc-warehouse', 'read'),
    'registrar': ('accounting', 'read cost_read settlement_read payment_read payment_prepare'),
    'reviewer': ('accounting', 'read cost_read period_lock period_reopen settlement_read settlement_confirm settlement_reopen payment_read payment_confirm payment_reverse'),
    'foreign': ('production', 'read order_receive'),
}


def role_codes(name):
    codes = {'cutting_ops:' + a for a in ROLE_ACTIONS[name][1].split()}
    if name == 'warehouse':
        codes |= {'fabric_operations:read', 'fabric_operations:operate', 'fabric_operations:correct'}
    return codes


@pytest.fixture
def role_flow(flow, monkeypatch):
    p = flow
    for filename in (
        '20261010_0155_cutting_production_events.py',
        '20261014_0156_cutting_material_usage.py',
        '20261015_0163_cutting_internal_periods.py',
        '20261016_0165_cutting_subcontract_settlement.py',
        '20261016_0166_cutting_subcontract_payments.py',
    ):
        migration = runpy.run_path(str(Path(__file__).parents[1] / 'alembic/versions' / filename))
        with p.engine.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration['upgrade']()
    AuthUser.metadata.create_all(p.engine, tables=[t for t in AuthUser.metadata.sorted_tables
                                                  if not t.name.startswith('cutting_ops_')])
    p.app.include_router(auth_api.router)
    p.app.include_router(warehouse_api.router)
    p.app.dependency_overrides.pop(get_current_user)
    monkeypatch.setattr(settings, 'session_cookie_secure', False)
    monkeypatch.setattr(settings, 'authz_mode', 'enforce')
    monkeypatch.setattr(settings, 'cutting_period_admin_acceptance', False)
    monkeypatch.setattr(wh, 'business_now', lambda: datetime(2026, 12, 15, 12, tzinfo=ZoneInfo('Asia/Shanghai')))
    monkeypatch.setattr(cutting_exports, 'business_now', wh.business_now)
    monkeypatch.setattr(planning, 'business_today', lambda: date(2026, 12, 15))
    with Session(p.engine) as db:
        db.add(AuthIamState(key='identity_mutation_lock', value_json='{}'))
        for factory in ('huakang-c', 'huakang-d'):
            db.add(IamOrgUnit(id=factory, name=factory, kind='factory', legacy_factory_id=factory))
        db.flush()
        for factory in ('huakang-c', 'huakang-d'):
            for dept in {v[0] for v in ROLE_ACTIONS.values()}:
                db.add(IamOrgDepartment(org_unit_id=factory, department_code=dept))
        for code in sorted(set().union(*(role_codes(n) for n in ROLE_ACTIONS))):
            db.add(AuthPermission(id=code, code=code, name=code))
        for name in ROLE_ACTIONS:
            db.add(AuthUser(id=name, username='p5b-'+name, display_name=name,
                password_salt='synthetic-p5b', password_hash=hash_password('SyntheticPass123!', 'synthetic-p5b'), status='active'))
            db.add(AuthRole(id=name, code='p5b-'+name, name=name))
        db.flush()
        for name, (dept, _) in ROLE_ACTIONS.items():
            factory = 'huakang-d' if name == 'foreign' else 'huakang-c'
            db.add(EmployeeProfile(user_id=name, primary_factory_id=factory, primary_department=dept,
                identity_mode='v2', identity_version=1, confirmation_status='confirmed'))
            db.add(AuthUserRole(id=name, user_id=name, role_id=name, factory_id=factory, department=dept))
            for code in sorted(role_codes(name)):
                db.add(AuthRolePermission(id=name+':'+code, role_id=name, permission_id=code))
        db.flush()
        for name, (dept, _) in ROLE_ACTIONS.items():
            factory = 'huakang-d' if name == 'foreign' else 'huakang-c'
            assignment = EmployeeAssignment(id='assignment-'+name, user_id=name, org_unit_id=factory,
                department_code=dept, official_position_title=name, is_primary=True,
                valid_from='2020-01-01T00:00:00Z', created_by='fixture', confirmed_by='fixture',
                created_at='2020-01-01T00:00:00Z', updated_at='2020-01-01T00:00:00Z')
            db.add(assignment)
            db.flush()
            profile = db.get(EmployeeProfile, name)
            profile.primary_assignment_id = assignment.id
            profile.primary_org_unit_id = factory
            version = snapshot_role(db, name, 'fixture')
            db.add(AuthRoleBindingMetadata(user_role_id=name, assignment_id=assignment.id,
                role_version_id=version.id, employment_epoch=1, source_type='assignment',
                source_id=assignment.id, reason='隔离验收任职确认'))
        for key, kind, code, data in (
            ('fabric-mat', 'MATERIAL', 'FAB-01', dict(category='FABRIC', unit='米', spec='规格A', color='蓝')),
            ('bin', 'LOCATION', 'A01', dict(warehouse='布料一仓', category='FABRIC')),
        ):
            db.add(FabricMasterRecord(id=key, factory_id='huakang-c', kind=kind, code=code,
                name='蓝布' if kind == 'MATERIAL' else code, status='ACTIVE', revision=1, data_json=json.dumps(data), updated_at='2026-10-10'))
        db.commit()
    return p


def login(p, role):
    p.cookies.clear()
    response = p.post('/api/auth/login', json={'username': 'p5b-'+role, 'password': 'SyntheticPass123!'})
    ok(response)
    assert response.json()['identity']['identity_mode'] == 'v2'
    assert 'HttpOnly' in response.headers['set-cookie']
    assert get_current_user not in p.app.dependency_overrides


def export(p, kind, **kwargs):
    body = dict(factory_id='huakang-c', month='2026-10', kind=kind) | kwargs
    preview = ok(p.post(BASE+'/exports/preview', json=body))
    response = p.post(BASE+'/exports/download', json=body | {'token': preview['token']})
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    workbook = load_workbook(BytesIO(response.content))
    evidence = Path(p.engine.url.database).parent / 'exports'
    evidence.mkdir(exist_ok=True)
    sequence = len(list(evidence.glob('*.xlsx'))) + 1
    (evidence / f'{sequence:02d}-{kind}.xlsx').write_bytes(response.content)
    return workbook, preview


def sheet_records(book, name):
    values = list(book[name].values)
    return [dict(zip(values[1], row)) for row in values[2:]]


def actual_plan(p, receipts):
    login(p, 'supervisor')
    order = order_read(p)
    baseline = order['current']['data']['planning']['baseline']
    tasks = [{k: v for k, v in t.items() if k in PlanTask.model_fields} | dict(
        date_basis='actual', actual_issue_date='2026-10-10', actual_issue_reference='隔离样本实际分批签收',
        material_receipt_ids=receipts[t['task_id']])
        for t in order['current']['data']['planning']['published']['tasks']]
    ok(plan_save(p, tasks, reason='实际签收后核定本厂和外发计划'))
    ok(publish(p, reason='实际签收后核定本厂和外发计划'))
    current = order_read(p)
    assert current['current']['data']['planning']['baseline'] == baseline
    assert not current['planning_summary']['receipt_review_required']
    for t in current['current']['data']['planning']['published']['tasks']:
        assert not t['actual_review_pending']
        assert {r['id'] for r in t['material_receipts']} == set(receipts[t['task_id']])


def prepare_order(p):
    login(p, 'clerk')
    row = receive(p)
    login(p, 'supervisor')
    material = create(p)
    a, b = resource(p), resource(p, 'R02', 'outsourced')
    login(p, 'engineering')
    body = bom_body(material)
    body['data']['requirements'].append(dict(body['data']['requirements'][0], stage='后续', required_for_cutting=False))
    bom = ok(state(p, create(p, body), 'published'))
    row = ok(post(p, 'bom', expected_version=row['current']['version'], bom_id=bom['id'],
        bom_version=bom['version'], target_sets=50, quantity_basis='100件，每套2件，50套'))
    row = ok(post(p, 'requisition', expected_version=row['current']['version'],
        lines=[dict(row=0, quantity='7'), dict(row=1, quantity='8')]))
    login(p, 'procurement')
    row = ok(post(p, 'eta', expected_version=row['current']['version'],
        requisition_version=row['current']['data']['requisition']['version'],
        batches=[dict(batch(quantity='7'), expected_date='2026-10-12')]))
    assert row['current']['data']['requisition']['lines'][1]['awaiting_reply_quantity'] == '8'
    login(p, 'supervisor')
    ok(plan_save(p, [task(a, target_sets=25, days=[dict(day='2026-10-15', sets=25)]),
                     task(b, task_id='external', target_sets=25, days=[dict(day='2026-10-15', sets=25)])]))
    published = ok(publish(p))['current']['data']['planning']['published']
    assert published['allocated_sets'] == 50
    assert published['tasks'][0]['earliest_supply_date'] == '2026-10-15'


def prepare_closed_order(p):
    """Reusable synthetic scenario; all business transitions use the APIs."""
    prepare_order(p)
    login(p, 'warehouse')
    stock = warehouse_post(p, 'RECEIPT', quantity='20', source_no='P5B-SYNTHETIC', source_line='1',
        item_code='FAB-01', item_name='蓝布', unit='米', location_id='bin', lot='LOT-1', counterparty='合成供方')
    p.stock_id = stock['id']
    login(p, 'clerk')
    request = material_send(p, 'request', request_body(p))
    assert p.get('/api/warehouse-operations/fabric', params={'factory_id':'huakang-c'}).status_code == 403
    login(p, 'warehouse')
    issued = issue(p, request)
    p.issue_id = issued['id']
    assert warehouse_view(p)['stock'][0]['quantity'] == '16'
    login(p, 'clerk')
    # A valid expected plan alone must not qualify as actual readiness.
    assert report(p, sets=10, exception_reason='').status_code == 422
    receipt_ids = []
    for quantity in ('2.5', '1.5'):
        receipt_ids.append(material_send(p, 'receive', material_decision(p, issued, quantity=quantity))['id'])
    external_request = material_send(p, 'request', request_body(p) | {'task_id':'external', 'quantity':'2'})
    login(p, 'warehouse')
    external_issue = warehouse_post(p, 'ISSUE', original_id=external_request['id'],
        batch_id=p.stock_id, quantity='2', counterparty='R02')
    login(p, 'clerk')
    external_receipt = material_send(p, 'receive', material_decision(p, external_issue, quantity='2'))
    actual_plan(p, {'task-1':receipt_ids, 'external':[external_receipt['id']]})
    login(p, 'clerk')
    ok(report(p, sets=10, exception_reason=''))
    ok(report(p, kind='handover', sets=8))
    ok(report(p, task_id='external', sets=20, exception_reason=''))
    assert reports(p)['summary']['completed'] == 10
    assert report(p, task_id='external', kind='accept', sets=15).status_code == 403
    returned=ok(report(p, task_id='external', kind='return', sets=18))
    assert returned['documents'][-1]['posted']['actor_id'] == 'clerk'
    login(p, 'supervisor')
    assert report(p, task_id='external', kind='return', sets=1).status_code == 403
    p.acceptance = doc(ok(report(p, task_id='external', kind='accept', sets=15, rejected=2)))
    login(p, 'clerk')
    ok(report(p, task_id='external', kind='handover', sets=14))
    totals = reports(p)['summary']
    assert (totals['completed'], totals['actual_delivery'], totals['remaining']) == (25, 22, 25)
    consume(p)
    assert 'price' not in usage_read(p)['issues'][0]
    login(p, 'procurement')
    assert usage_read(p, True)['pending_pricing'] == 1
    write(p, 'price', issue_id=p.issue_id, unit_cost='3.125', currency='HKD', price_reference='合成原批次成本凭据')
    login(p, 'supervisor')
    allocate(p)
    month_basis = period_read(p, suffix='/basis')
    draft(p, allocations=[dict(issue_id=r['issue_id'], opening_completed_quantity='0',
        completed_quantity='1.2' if r['issue_id']==p.issue_id else '0') for r in month_basis['rows']])
    act(p, 'submit')
    act(p, 'lock', status=403)
    login(p, 'reviewer')
    frozen, _ = act(p, 'lock')
    costs = period_read(p)['data']['snapshot']['costs']['HKD']
    assert (costs['ending_completed'], costs['ending_wip'], costs['period_loss']) == ('3.75', '2.50', '1.56')
    book, _ = export(p, 'period', event_id=frozen['id'])
    old_period_book = book
    totals = sheet_records(book, '费用汇总')[0]
    assert {k: totals[k] for k in ('币种','本期正常费用','期末累计完工费用','期末在制费用','本期损耗费用')} == {
        '币种':'HKD','本期正常费用':'6.25','期末累计完工费用':'3.75','期末在制费用':'2.50','本期损耗费用':'1.56'}
    inventory = {r['原实发ID']:r for r in sheet_records(book, '物料收发耗存')}
    assert set(inventory) == {p.issue_id, external_issue['id']}
    assert tuple(Decimal(inventory[p.issue_id][k]) for k in ('本期实发','本期签收','本期正常耗用','本期损耗','期末结存')) == tuple(map(Decimal,('4','4','2','0.5','1.5')))
    assert inventory[external_issue['id']]['期末结存'] == '2'
    sources = sheet_records(book, '冻结来源索引')
    assert p.issue_id in {r['单据ID'] for r in sources}
    assert all(r['事件ID'] and r['业务日期'] for r in sources)
    login(p, 'procurement')
    write(p, 'price', status=409, issue_id=p.issue_id, unit_cost='4', currency='HKD', price_reference='锁月后不可改价')
    login(p, 'supervisor')
    price(p, value='2')
    p.one = fee_save(p, sets=10)
    ok(fee_decision(p, p.one, 'submit'))
    assert fee_decision(p, p.one, 'confirm').status_code == 403
    login(p, 'reviewer')
    ok(fee_decision(p, p.one, 'confirm'))
    statement = record(p, p.one)
    assert statement['data']['snapshot']['total'] == '20.00'
    old_fee_book, _ = export(p, 'settlement', document_id=p.one, event_id=statement['event_id'])
    fee_total = sheet_records(old_fee_book, '结算汇总')[0]
    assert (fee_total['币种'],fee_total['验收结算套数'],fee_total['含税应付金额']) == ('CNY',10,'20.00')
    fee_line = sheet_records(old_fee_book, '验收计费明细')[0]
    assert (fee_line['订单明细ID'],fee_line['任务ID'],fee_line['验收单ID'],fee_line['本次结算套数'],fee_line['冻结金额']) == ('line-1','external',p.acceptance,10,'20.00')
    assert fee_line['报价版本ID'] and fee_line['验收事件ID']
    login(p, 'registrar')
    saved_command = payment_body(p, day='2026-11-01')
    saved = ok(p.post(BASE+'/payments/save', json=saved_command))
    assert ok(p.post(BASE+'/payments/save', json=saved_command)) == saved
    recovery = ok(p.post(BASE+'/payment-operations/recover', json=dict(action='save', command=saved_command)))
    assert recovery['state'] == 'committed'
    payment = saved_command['document_id']
    ok(payment_decision(p, payment, 'submit'))
    assert payment_decision(p, payment, 'confirm').status_code == 403
    # Even an accidental extra grant cannot bypass independent review.
    with Session(p.engine) as db:
        db.add(AuthRolePermission(id='temporary-dual-duty', role_id='registrar', permission_id='cutting_ops:payment_confirm'))
        db.flush()
        db.get(AuthRoleBindingMetadata, 'registrar').role_version_id = snapshot_role(db, 'registrar', 'fixture').id
        db.commit()
    assert payment_decision(p, payment, 'confirm').status_code == 409
    login(p, 'reviewer')
    ok(payment_decision(p, payment, 'confirm'))
    assert p.post(BASE+'/payments/save', json=saved_command).status_code == 403
    balance = payments(p)['totals'][0]
    assert (balance['paid'], balance['unpaid'], balance['pending']) == ('5.00', '15.00', '0.00')
    confirmed_payment = payments(p, payment, month='2026-11')
    assert confirmed_payment['data']['local_admin_acceptance'] is False
    assert confirmed_payment['data']['prepared_by'] == 'registrar'
    assert confirmed_payment['history'][-1]['actor'] == 'reviewer'
    assert fee_decision(p, p.one, 'reopen').status_code == 409
    book, _ = export(p, 'payments', month='2026-11')
    assert list(book['当前全期余额汇总'].values)[2:] == [('CNY', '20.00', '5.00', '15.00', '0.00', '15.00')]
    allocation = sheet_records(book, '所选月核销明细')[0]
    assert (allocation['结算单ID'], allocation['原冻结结算版本ID'], allocation['分配金额']) == (p.one, statement['event_id'], '5.00')
    internal = ok(p.post(BASE+'/cutover/preview', json=dict(factory_id='huakang-c', scope='internal', month='2026-11')))
    assert not internal['can_post']
    assert next(r['value'] for r in internal['rows'] if r['key'].startswith('wip_cost:')) == '2.50'
    payment_event = payments(p, payment, month='2026-11')['event_id']
    ok(payment_decision(p, payment, 'reverse'))
    assert payments(p)['totals'][0]['paid'] == '0.00'
    history = payments(p, payment, month='2026-11', event_id=payment_event)
    assert history['selected_state'] == 'confirmed' and history['state'] == 'reversed'
    login(p, 'registrar')
    replacement = payment_save(p, day='2026-11-02', replaces_document_id=payment)
    ok(payment_decision(p, replacement, 'submit'))
    login(p, 'reviewer')
    ok(payment_decision(p, replacement, 'confirm'))
    assert payments(p)['totals'][0]['paid'] == '5.00'
    assert payments(p, payment, month='2026-11')['replacements'][0]['document_id'] == replacement
    # Controlled reopen/reclose must change current totals, never old amounts.
    ok(payment_decision(p, replacement, 'reverse'))
    ok(fee_decision(p, p.one, 'reopen'))
    login(p, 'supervisor')
    price(p, value='3')
    fee_save(p, sets=10, document_id=p.one)
    ok(fee_decision(p, p.one, 'submit'))
    login(p, 'reviewer')
    ok(fee_decision(p, p.one, 'confirm'))
    historical_fee, fee_info = export(p, 'settlement', document_id=p.one, event_id=statement['event_id'])
    assert '历史失效' in dict(fee_info['metadata'])['使用状态']
    for name in ('结算汇总','验收计费明细'):
        assert sheet_records(historical_fee,name) == sheet_records(old_fee_book,name)
    current_fee = record(p,p.one)
    new_fee,_ = export(p,'settlement',document_id=p.one,event_id=current_fee['event_id'])
    assert sheet_records(new_fee,'结算汇总')[0]['含税应付金额'] == '30.00'
    act(p,'reopen')
    login(p,'procurement')
    write(p,'price',issue_id=p.issue_id,unit_cost='4',currency='HKD',price_reference='反结后重新核价')
    login(p,'supervisor')
    draft(p,allocations=[dict(issue_id=r['issue_id'],opening_completed_quantity='0',
        completed_quantity='1.2' if r['issue_id']==p.issue_id else '0') for r in month_basis['rows']])
    act(p,'submit')
    login(p,'reviewer')
    relocked,_ = act(p,'lock')
    historical_period, period_info = export(p,'period',event_id=frozen['id'])
    assert '历史失效' in dict(period_info['metadata'])['使用状态']
    for name in ('费用汇总','生产汇总','物料收发耗存','完工及在制归集','冻结来源索引'):
        assert sheet_records(historical_period,name) == sheet_records(old_period_book,name)
    new_period,_ = export(p,'period',event_id=relocked['id'])
    new_cost = sheet_records(new_period,'费用汇总')[0]
    assert (new_cost['本期正常费用'],new_cost['期末累计完工费用'],new_cost['期末在制费用'],new_cost['本期损耗费用']) == ('8.00','4.80','3.20','2.00')
    login(p, 'warehouse')
    assert warehouse_view(p)['stock'][0]['quantity'] == '14'


def test_joined_roles_order_to_frozen_cost_payment_and_cutover(role_flow):
    prepare_closed_order(role_flow)

@pytest.mark.parametrize('role', [name for name in ROLE_ACTIONS if name != 'foreign'])
def test_capabilities_match_explicit_role_only(role_flow, role):
    login(role_flow, role)
    result = ok(role_flow.get(BASE+'/access', params={'factory_id':'huakang-c'}))
    assert set(result['permissions']) == set(ROLE_ACTIONS[role][1].split())
    assert all(result[k] for k in ('schema_ready', 'orders_schema_ready', 'reporting_schema_ready',
                                  'usage_schema_ready', 'periods_schema_ready', 'settlements_schema_ready', 'payments_schema_ready'))


def test_roles_denied_live_revocation_and_logout(role_flow):
    p = role_flow
    login(p, 'foreign')
    assert p.get(BASE+'/orders', params={'factory_id':'huakang-c'}).status_code == 403
    login(p, 'clerk')
    assert p.get(BASE+'/payments/2026-10', params={'factory_id':'huakang-c'}).status_code == 403
    assert p.post(BASE+'/cutover/preview', json=dict(factory_id='huakang-c', month='2026-11', scope='internal')).status_code == 403
    with Session(p.engine) as db:
        db.get(AuthRoleBindingMetadata, 'clerk').state = 'revoked'
        db.commit()
    assert p.get(BASE+'/orders', params={'factory_id':'huakang-c'}).status_code == 403
    assert p.post('/api/auth/logout').status_code == 204
    assert p.get(BASE+'/orders', params={'factory_id':'huakang-c'}).status_code == 401


@pytest.mark.parametrize('change', ['ended', 'revoked', 'wrong_epoch', 'department_closed', 'transferred'])
def test_v2_assignment_boundaries_remove_cutting_access(role_flow, change):
    p = role_flow
    login(p, 'clerk')
    assert p.get(BASE+'/orders', params={'factory_id':'huakang-c'}).status_code == 200
    with Session(p.engine) as db:
        assignment = db.get(EmployeeAssignment, 'assignment-clerk')
        if change == 'ended':
            assignment.valid_until = '2021-01-01T00:00:00Z'
        elif change == 'revoked':
            assignment.lifecycle_state = 'revoked'
        elif change == 'wrong_epoch':
            assignment.employment_epoch = 2
        elif change == 'department_closed':
            db.get(IamOrgDepartment, ('huakang-c', 'production')).status = 'inactive'
        else:
            # The old binding must not silently follow a new formal assignment.
            assignment.valid_until = '2021-01-01T00:00:00Z'
            db.add(EmployeeAssignment(id='transferred-clerk', user_id='clerk', org_unit_id='huakang-d',
                department_code='production', official_position_title='调任', is_primary=True,
                valid_from='2021-01-01T00:00:00Z', created_by='fixture', confirmed_by='fixture',
                created_at='2021-01-01T00:00:00Z', updated_at='2021-01-01T00:00:00Z'))
        db.commit()
    assert p.get(BASE+'/orders', params={'factory_id':'huakang-c'}).status_code == 403
    if change == 'transferred':
        me = ok(p.get('/api/auth/me'))
        assert me['identity']['primary_factory_id'] == 'huakang-d'


def test_v2_package_is_frozen_until_explicit_version_change(role_flow):
    p = role_flow
    login(p, 'clerk')
    def access():
        return ok(p.get(BASE+'/access', params={'factory_id':'huakang-c'}))['permissions']
    with Session(p.engine) as db:
        db.execute(delete(AuthRolePermission).where(AuthRolePermission.id=='clerk:cutting_ops:report_write'))
        db.commit()
    assert 'report_write' in access()
    with Session(p.engine) as db:
        db.get(AuthRoleBindingMetadata, 'clerk').role_version_id = snapshot_role(db, 'clerk', 'fixture').id
        db.commit()
    assert 'report_write' not in access()
    assert 'material_receive' in access()
