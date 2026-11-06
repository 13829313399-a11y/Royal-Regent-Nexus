from dataclasses import replace
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4
import json
import pytest
from sqlalchemy import select, func, text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from alembic.migration import MigrationContext
from alembic.operations import Operations
from test_material_plan_workflow import flow, linked, client, engineering_client, engineering_material_attribute, owner, purchaser, submitted, act
from test_material_plan_orders import body as demand_body
from test_material_plan import request as demand_request
from test_engineering_bom import command
from app.api import material_purchase as api
from app.services import material_purchase as service
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext
from app.services.permission_codes import MATERIAL_PURCHASE_PERMISSION_CODES
from app.models.material_purchase import MaterialPurchase, MaterialPurchaseEvent
from app.models.customer_order_ledger import OrderLedgerLine
from app.services.material_purchase_checks import summarize
from copy import deepcopy
from fractions import Fraction
from app.services.material_purchase_comparison import compare, compare_processes

BASE = '/api/material-purchasing'


def actor(actions=('read', 'write'), factory='huakang-c', department='pmc-warehouse', identity='clerk'):
    codes = frozenset('material_purchase:' + a for a in actions)
    grant = AuthGrantContext(role_id='synthetic', role_name='测试', factory_id=factory, department=department, permissions=codes)
    return AuthContext(id=identity, username=identity, display_name=identity, roles=('test',), role_codes=('test',), permissions=codes,
        factory_scopes=(factory,), department_scopes=(department,), grants=(grant,), active_permission_codes=frozenset(MATERIAL_PURCHASE_PERMISSION_CODES))


def head(): return actor(('read', 'approve', 'release'), identity='head')


def migration():
    spec = spec_from_file_location('purchase_migration', Path(__file__).parents[1] / 'alembic/versions/20261104_0192_material_purchase.py')
    module = module_from_spec(spec); spec.loader.exec_module(module)
    return module


@pytest.fixture
def purchase(flow, monkeypatch):
    flow.app.include_router(api.router)
    with flow.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().upgrade()
    monkeypatch.setattr(api.settings, 'material_purchase_enabled', True)
    changes = {'material_attributes': {'sew': '自制', 'fabric': '委外'}} if flow.published['materials'][next(iter(flow.published['materials']))]['data']['engineering']['attribute'] == '自制' else {}
    draft = demand_request(flow, '/drafts', demand_body(flow, **changes))
    shared = act(flow, draft, 'submit'); flow.engineering_auth['user'] = purchaser()
    dated = act(flow, shared, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    flow.engineering_auth['user'] = owner(); flow.demand = act(flow, dated, 'self-review')
    flow.engineering_auth['user'] = actor()
    return flow


def post(c, path, body):
    response = c.post(BASE + path, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def data(c):
    basis = c.get(BASE + '/workspace?factory_id=huakang-c').json()['sources'][0]
    return dict(demand_id=basis['id'], demand_version=basis['version'], supplier_reference='待核实供应商甲', currency='CNY', tax_rate='13',
        delivery_date='2026-11-20', delivery_location='本厂', payment_terms='按约定结算',
        lines=[dict(source_key=g['source_key'], quantity=22, purchase_unit='码', unit_price='0') for g in basis['groups'] if g['purchasable']])


def action(c, doc, name):
    return post(c, f"/documents/{doc['id']}/actions/{name}", command(expected_version=doc['version']))


def approved(c):
    draft = post(c, '/documents', command(data=data(c)))
    pending = action(c, draft, 'submit'); c.engineering_auth['user'] = head()
    return action(c, pending, 'approve')


def test_approval_quantity_change_rejection_cancellation_history_and_no_release(purchase):
    c = purchase; initial = approved(c)
    assert initial['status'] == service.APPROVED and not initial['effective_on_order'] and initial['released_at'] is None
    assert not initial['release_gate']['can_release']
    before = c.get(BASE + f"/documents/{initial['id']}/history?factory_id=huakang-c").json()['items']
    assert len(before) == 3
    for state in [initial]:
        response = c.post(BASE + f"/documents/{state['id']}/actions/release", json=command(expected_version=state['version']))
        assert response.status_code == 409 and '正式下发未开放' in response.text
    assert c.get(BASE + f"/documents/{initial['id']}/history?factory_id=huakang-c").json()['items'] == before
    c.engineering_auth['user'] = actor()
    key = initial['data']['lines'][0]['source_key']
    change = post(c, f"/documents/{initial['id']}/change", command(expected_version=initial['version'], kind='QUANTITY', quantities={key: 25}))
    assert change['data']['lines'][0]['quantity'] == 22 and change['pending_change']['before'][key] == 22
    c.engineering_auth['user'] = head(); rejected = action(c, change, 'reject-change')
    assert rejected['data']['lines'][0]['quantity'] == 22
    c.engineering_auth['user'] = actor()
    change = post(c, f"/documents/{initial['id']}/change", command(expected_version=rejected['version'], kind='QUANTITY', quantities={key: 25}))
    c.engineering_auth['user'] = head(); changed = action(c, change, 'approve-change')
    assert changed['data']['lines'][0]['quantity'] == 25
    c.engineering_auth['user'] = actor()
    cancel = post(c, f"/documents/{initial['id']}/change", command(expected_version=changed['version'], kind='CANCEL'))
    c.engineering_auth['user'] = head(); cancelled = action(c, cancel, 'approve-change')
    assert cancelled['status'] == service.CANCELLED and not cancelled['effective_on_order']
    with c.engine.begin() as connection:
        for sql in ['DELETE FROM material_purchase_events', "UPDATE material_purchase_events SET reason='overwrite'"]:
            with pytest.raises(IntegrityError): connection.execute(text(sql))
        with Operations.context(MigrationContext.configure(connection)), pytest.raises(RuntimeError): migration().downgrade()


@pytest.mark.parametrize('engineering_material_attribute', ['自制'], indirect=True)
def test_same_code_attributes_do_not_merge_or_become_purchase_by_tampering(purchase):
    c = purchase; basis = c.get(BASE + '/workspace?factory_id=huakang-c').json()['sources'][0]
    assert len({g['code'] for g in basis['groups']}) == 1
    assert {(g['attribute'], g['gross']['value']) for g in basis['groups']} == {('自制', '105'), ('委外', '21')}
    assert len({g['source_key'] for g in basis['groups']}) == 2
    good = data(c); assert len(good['lines']) == 1
    invalid = dict(good, lines=[dict(good['lines'][0], source_key=next(g['source_key'] for g in basis['groups'] if not g['purchasable']))])
    assert c.post(BASE + '/documents', json=command(data=invalid)).status_code == 422
    invalid = dict(good, lines=[dict(good['lines'][0], attribute='自制')])
    assert c.post(BASE + '/documents', json=command(data=invalid)).status_code == 422
    saved = approved(c)
    assert saved['source']['groups'] == basis['groups']
    assert saved['data']['lines'][0]['source_key'] == next(g['source_key'] for g in basis['groups'] if g['attribute'] == '委外')
    assert 'customer_name' not in json.dumps(saved) and 'PO-100' not in json.dumps(saved)


def test_incomplete_drafts_and_numeric_validation(purchase):
    c = purchase; fields = data(c); fields['supplier_reference'] = ''
    draft = post(c, '/documents', command(data=fields))
    assert c.post(BASE + f"/documents/{draft['id']}/actions/submit", json=command(expected_version=1)).status_code == 422
    for value in [0, -1, 1.2, True, '22']:
        fields = data(c); fields['lines'][0]['quantity'] = value
        assert c.post(BASE + '/documents', json=command(data=fields)).status_code == 422
    fields = data(c); fields['lines'] *= 2
    assert c.post(BASE + '/documents', json=command(data=fields)).status_code == 422


def test_source_changes_block_approval_but_allow_rejection_and_cancel(purchase):
    c = purchase; draft = post(c, '/documents', command(data=data(c))); pending = action(c, draft, 'submit')
    with Session(c.engine) as db:
        row = db.get(OrderLedgerLine, 'order-1'); row.revision += 1; db.commit()
    c.engineering_auth['user'] = head()
    assert c.post(BASE + f"/documents/{draft['id']}/actions/approve", json=command(expected_version=pending['version'])).status_code == 409
    assert action(c, pending, 'reject')['status'] == service.DRAFT


@pytest.mark.parametrize('user', [actor(factory='huakang-a'), actor(department='sales-business'), purchaser(), owner()])
def test_scope_and_existing_roles_do_not_grant_purchase(purchase, user):
    purchase.engineering_auth['user'] = user
    assert purchase.get(BASE + '/workspace?factory_id=huakang-c').status_code == 403


def test_clerk_cannot_approve_and_head_without_write_cannot_create(purchase):
    c = purchase; fields = data(c); saved = post(c, '/documents', command(data=fields)); pending = action(c, saved, 'submit')
    assert c.post(BASE + f"/documents/{saved['id']}/actions/approve", json=command(expected_version=pending['version'])).status_code == 403
    c.engineering_auth['user'] = head()
    assert c.post(BASE + '/documents', json=command(data=fields)).status_code == 403
    c.engineering_auth['user'] = replace(head(), overrides=(AuthOverrideContext(id='deny', permission_code='material_purchase:approve', effect='deny', factory_id='huakang-c', department='pmc-warehouse'),))
    assert c.post(BASE + f"/documents/{saved['id']}/actions/approve", json=command(expected_version=pending['version'])).status_code == 403


def test_duplicate_and_conflicting_requests_are_atomic(purchase):
    c = purchase; cmd = command(data=data(c))
    with ThreadPoolExecutor(2) as pool: saved = list(pool.map(lambda _: post(c, '/documents', cmd), range(2)))
    assert saved[0] == saved[1]
    with Session(c.engine) as db: assert db.scalar(select(func.count()).select_from(MaterialPurchase)) == 1
    assert c.post(BASE + '/documents', json=cmd | {'reason': 'different'}).status_code == 409
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(lambda _: c.post(BASE + f"/documents/{saved[0]['id']}/actions/submit", json=command(expected_version=1)).status_code, range(2)))
    assert sorted(statuses) == [200, 409]


def test_migration_readiness_and_disabled_flag(purchase, monkeypatch):
    c = purchase
    before = c.demand
    with c.engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        migration().downgrade(); migration().upgrade()
    with Session(c.engine) as db:
        assert service.ready(db)
        assert service.workflow.latest(db, db.get(service.MaterialPlan, before['id'])) == before
    monkeypatch.setattr(api.settings, 'material_purchase_enabled', False)
    assert c.get(BASE + '/workspace?factory_id=huakang-c').status_code == 503
    monkeypatch.setattr(api.settings, 'material_purchase_enabled', True)
    with c.engine.begin() as connection: connection.execute(text('DROP TRIGGER material_purchase_no_update'))
    assert c.get(BASE + '/access?factory_id=huakang-c').json()['schema_ready'] is False


def test_release_is_blocked_in_all_preparation_states_and_never_writes_an_event(purchase):
    c = purchase; draft = post(c, '/documents', command(data=data(c)))
    def blocked(state):
        prior_actor = c.engineering_auth['user']; c.engineering_auth['user'] = head()
        with Session(c.engine) as db: before = db.scalar(select(func.count()).select_from(MaterialPurchaseEvent))
        response = c.post(BASE + f"/documents/{state['id']}/actions/release", json=command(expected_version=state['version']))
        assert response.status_code == 409 and '正式下发未开放' in response.text
        with Session(c.engine) as db: assert db.scalar(select(func.count()).select_from(MaterialPurchaseEvent)) == before
        c.engineering_auth['user'] = prior_actor
    blocked(draft)
    states = [draft, action(c, draft, 'submit')]; blocked(states[-1])
    c.engineering_auth['user'] = head(); states.append(action(c, states[-1], 'approve'))
    blocked(states[-1])
    c.engineering_auth['user'] = actor()
    states.append(post(c, f"/documents/{draft['id']}/change", command(expected_version=states[-1]['version'], kind='CANCEL')))
    blocked(states[-1])
    c.engineering_auth['user'] = head(); states.append(action(c, states[-1], 'approve-change'))
    blocked(states[-1])


def test_reopened_source_blocks_quantity_approval_but_allows_cancellation(purchase):
    c = purchase; approved_doc = approved(c); key = approved_doc['data']['lines'][0]['source_key']
    c.engineering_auth['user'] = actor()
    change = post(c, f"/documents/{approved_doc['id']}/change", command(expected_version=approved_doc['version'], kind='QUANTITY', quantities={key: 30}))
    c.engineering_auth['user'] = owner(); act(c, c.demand, 'reopen')
    c.engineering_auth['user'] = head()
    assert c.post(BASE + f"/documents/{change['id']}/actions/approve-change", json=command(expected_version=change['version'])).status_code == 409
    rejected = action(c, change, 'reject-change')
    c.engineering_auth['user'] = actor()
    cancel = post(c, f"/documents/{rejected['id']}/change", command(expected_version=rejected['version'], kind='CANCEL'))
    c.engineering_auth['user'] = head()
    assert action(c, cancel, 'approve-change')['status'] == service.CANCELLED


def check_report(c, doc):
    response = c.get(BASE + f"/documents/{doc['id']}/checks", params={'factory_id': 'huakang-c', 'expected_version': doc['version']})
    assert response.status_code == 200, response.text
    return response.json()


def test_preparation_checks_count_current_versions_and_do_not_apply_pending_changes(purchase):
    c = purchase; first = approved(c); key = first['data']['lines'][0]['source_key']
    c.engineering_auth['user'] = actor()
    pending = post(c, f"/documents/{first['id']}/change", command(expected_version=first['version'], kind='QUANTITY', quantities={key: 99}))
    other = post(c, '/documents', command(data=data(c)))
    with Session(c.engine) as db:
        before = list(db.scalars(select(MaterialPurchaseEvent.result_json).order_by(MaterialPurchaseEvent.id)))
    c.engineering_auth['user'] = actor(('read',))
    report = check_report(c, pending)
    assert report['source_current'] and not report['can_release']
    assert len(report['groups']) == 2  # same material, separate current workflow states
    assert {g['complete_quantity'] for g in report['groups']} == {'22'}
    assert all(g['related_document_count'] == 2 and g['possible_duplicate'] for g in report['groups'])
    assert next(g for g in report['groups'] if g['status'] == service.CHANGE)['documents'][0]['proposed_quantity'] == 99
    assert 'customer_name' not in json.dumps(report) and 'PO-100' not in json.dumps(report)
    with Session(c.engine) as db:
        assert list(db.scalars(select(MaterialPurchaseEvent.result_json).order_by(MaterialPurchaseEvent.id))) == before


def test_preparation_check_reports_stale_sources_and_rejects_old_document_or_permission(purchase):
    c = purchase; draft = post(c, '/documents', command(data=data(c)))
    pending = action(c, draft, 'submit')
    assert c.get(BASE + f"/documents/{draft['id']}/checks", params={'factory_id': 'huakang-c', 'expected_version': draft['version']}).status_code == 409
    with Session(c.engine) as db:
        row = db.get(OrderLedgerLine, 'order-1'); row.revision += 1; db.commit()
    report = check_report(c, pending)
    assert not report['source_current'] and '订单依据已变化' in report['source_issue']
    c.engineering_auth['user'] = actor(factory='huakang-a')
    assert c.get(BASE + f"/documents/{pending['id']}/checks", params={'factory_id': 'huakang-c', 'expected_version': pending['version']}).status_code == 403


def test_checks_keep_versions_units_attributes_unknown_values_and_cancelled_documents_separate(purchase):
    saved = post(purchase, '/documents', command(data=data(purchase)))
    def copy(identity, unit='码', quantity=22, attribute=None, version=None, status=service.DRAFT):
        doc = deepcopy(saved); doc['id'] = identity; doc['status'] = status
        doc['data']['lines'][0].update(purchase_unit=unit, quantity=quantity)
        if version is not None: doc['data']['demand_version'] = version
        if attribute:
            group = doc['source']['groups'][0]; group['attribute'] = attribute
            key = service.group_key(group); group['source_key'] = key; doc['data']['lines'][0]['source_key'] = key
        return doc
    docs = [copy('a'), copy('b', quantity=None), copy('c', unit='米'), copy('d', attribute='委外'),
        copy('e', version=99), copy('f', unit=''), copy('g', unit=''), copy('cancel', status=service.CANCELLED)]
    report = summarize(docs, saved['data']['demand_id'])
    assert len(report['groups']) == 6 and report['cancelled_document_count'] == 1
    grouped = next(g for g in report['groups'] if len(g['documents']) == 2)
    assert grouped['known_quantity'] == '22' and grouped['complete_quantity'] is None and grouped['missing_quantity_count'] == 1
    assert {g['attribute'] for g in report['groups']} == {'外购', '委外'}
    assert len([g for g in report['groups'] if not g['purchase_unit']]) == 2
    assert all(g['complete_quantity'] is None for g in report['groups'] if not g['purchase_unit'])
    assert not next(g for g in report['groups'] if g['demand_version'] == 99)['possible_duplicate']
    assert summarize(docs, 'other-demand')['groups'] == []


def test_cancelled_quantity_removed_only_after_responsible_approval(purchase):
    c = purchase; doc = approved(c); c.engineering_auth['user'] = actor()
    pending = post(c, f"/documents/{doc['id']}/change", command(expected_version=doc['version'], kind='CANCEL'))
    assert check_report(c, pending)['groups'][0]['complete_quantity'] == '22'
    c.engineering_auth['user'] = head(); cancelled = action(c, pending, 'approve-change')
    report = check_report(c, cancelled)
    assert report['groups'] == [] and report['cancelled_document_count'] == 1


def test_comparison_after_owner_reapproval_is_exact_read_only_and_minimal(purchase):
    c = purchase; doc = post(c, '/documents', command(data=data(c)))
    assert check_report(c, doc)['source_comparison']['status'] == 'CURRENT'
    c.engineering_auth['user'] = owner()
    reopened = act(c, c.demand, 'reopen')
    updated = demand_request(c, f"/drafts/{reopened['id']}", demand_body(c, loss_percent='10') | {'expected_version': reopened['version']})
    shared = act(c, updated, 'submit'); c.engineering_auth['user'] = purchaser()
    dated = act(c, shared, 'dates', dates={'裁床': '2026-11-13', '车缝': '2026-11-15'})
    c.engineering_auth['user'] = owner(); reviewed = act(c, dated, 'self-review')
    c.engineering_auth['user'] = actor(('read',))
    with Session(c.engine) as db:
        before = list(db.scalars(select(MaterialPurchaseEvent.result_json)))
    report = check_report(c, doc); diff = report['source_comparison']
    assert not report['source_current'] and not report['can_release']
    assert diff['status'] == 'COMPARED' and diff['target_version'] == reviewed['version']
    assert len(diff['rows']) == 1 and diff['rows'][0]['changes'] == ['QUANTITY']
    assert diff['rows'][0]['delta']['gross']['value'] == '6'  # (100 + 20) * (10% - 5%)
    assert diff['dates'] == [dict(process='裁床', before='2026-11-12', after='2026-11-13')]
    processes = diff['process_comparison']
    assert processes['available'] and {(r['process'], r['delta']['gross']['value']) for r in processes['rows']} == {('裁床', '1'), ('车缝', '5')}
    assert all(secret not in json.dumps(processes) for secret in ('parent', 'engineering_attribute', 'order_basis', 'inputs', 'PO-100'))
    assert all(secret not in json.dumps(diff) for secret in ('PO-100', 'customer_name', 'order_basis', 'inputs', '合成客户'))
    with Session(c.engine) as db:
        assert list(db.scalars(select(MaterialPurchaseEvent.result_json))) == before


def test_comparison_hides_drafts_unreviewed_versions_and_stale_order(purchase):
    c = purchase; doc = post(c, '/documents', command(data=data(c)))
    with Session(c.engine) as db:
        order = db.get(OrderLedgerLine, 'order-1'); order.revision += 1; db.commit()
    diff = check_report(c, doc)['source_comparison']
    assert diff['status'] == 'UNAVAILABLE' and diff['target_version'] is None and not diff['rows']
    c.engineering_auth['user'] = owner(); reopened = act(c, c.demand, 'reopen')
    c.engineering_auth['user'] = actor(('read',))
    diff = check_report(c, doc)['source_comparison']
    assert diff['status'] == 'UNAVAILABLE' and diff['target_version'] is None and diff['unchanged_count'] is None
    assert 'process_comparison' not in diff
    assert not diff['rows'] and not diff['dates']
    with Session(c.engine) as db:
        order = db.get(OrderLedgerLine, 'order-1'); order.revision -= 1; db.commit()
    c.engineering_auth['user'] = owner(); act(c, reopened, 'submit')
    c.engineering_auth['user'] = actor(('read',))
    assert check_report(c, doc)['source_comparison']['status'] == 'UNAVAILABLE'


def comparison_basis():
    quantity = service.trial.amount(Fraction(1, 3))
    group = dict(material_id='m1', material_version=1, code='same-code', name='布', unit='码', attribute='自制',
                 processes=['裁床'], base=quantity, loss=service.trial.amount(Fraction(0)), gross=quantity)
    return dict(version=1, groups=[group], process_dates={'裁床': '2026-11-12'})


def test_comparison_rejects_rebinding_same_demand_to_another_order(purchase):
    c = purchase; doc = post(c, '/documents', command(data=data(c)))
    c.engineering_auth['user'] = owner(); reopened = act(c, c.demand, 'reopen')
    body = demand_body(c); body['data']['order']['line_id'] = 'literal'; body['expected_version'] = reopened['version']
    updated = demand_request(c, f"/drafts/{reopened['id']}", body)
    shared = act(c, updated, 'submit'); c.engineering_auth['user'] = purchaser()
    dated = act(c, shared, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    c.engineering_auth['user'] = owner(); act(c, dated, 'self-review'); c.engineering_auth['user'] = actor(('read',))
    diff = check_report(c, doc)['source_comparison']
    assert diff['status'] == 'UNAVAILABLE' and '关联订单已更换' in diff['issue']
    assert diff['target_version'] is None and not diff['rows']


@pytest.mark.parametrize('field,value', [('attribute', '委外'), ('unit', '米'), ('material_version', 2)])
def test_comparison_never_nets_different_attributes_units_or_material_versions(field, value):
    before = comparison_basis(); after = deepcopy(before); after['version'] = 2; after['groups'][0][field] = value
    result = compare(before, after)
    assert len(result['rows']) == 2 and {r['changes'][0] for r in result['rows']} == {'ADDED', 'REMOVED'}
    assert {r['delta']['gross']['numerator'] for r in result['rows']} == {'1', '-1'}
    assert all(r['delta']['gross']['denominator'] == '3' for r in result['rows'])


def test_comparison_detects_exact_small_changes_loss_redistribution_process_and_dates():
    before = comparison_basis(); after = deepcopy(before); after['version'] = 2
    # Equal decimal display does not mean equal consumption; gross can stay equal.
    tiny = Fraction(1, 10**20)
    after['groups'][0].update(base=service.trial.amount(Fraction(1, 3) - tiny), loss=service.trial.amount(tiny), processes=['手工'])
    after['process_dates'] = {'手工': '2026-11-15'}
    result = compare(before, after); row = result['rows'][0]
    assert row['changes'] == ['QUANTITY', 'PROCESS'] and row['delta']['gross']['value'] == '0'
    assert Fraction(int(row['delta']['base']['numerator']), int(row['delta']['base']['denominator'])) == -tiny
    assert len(result['dates']) == 2 and result['unchanged_count'] == 0


def replacement_basis(c, other_order=False):
    old = approved(c); c.engineering_auth['user'] = actor()
    pending = post(c, f"/documents/{old['id']}/change", command(expected_version=old['version'], kind='CANCEL'))
    c.engineering_auth['user'] = head(); cancelled = action(c, pending, 'approve-change')
    c.engineering_auth['user'] = owner(); reopened = act(c, c.demand, 'reopen')
    inputs = deepcopy(c.demand['inputs']); inputs['loss_percent'] = '10'
    if other_order: inputs['order']['line_id'] = 'literal'
    updated = demand_request(c, f"/drafts/{reopened['id']}", command(expected_version=reopened['version'], data=inputs))
    shared = act(c, updated, 'submit'); c.engineering_auth['user'] = purchaser()
    dated = act(c, shared, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    c.engineering_auth['user'] = owner(); reviewed = act(c, dated, 'self-review')
    c.engineering_auth['user'] = actor()
    return cancelled, reviewed


@pytest.mark.parametrize('engineering_material_attribute', ['外购', '自制'], indirect=True)
def test_replacement_creates_blank_linked_draft_and_preserves_old_history(purchase):
    c = purchase; old, demand = replacement_basis(c)
    history_url = BASE + f"/documents/{old['id']}/history?factory_id=huakang-c"
    history = c.get(history_url).json()
    body = command(expected_version=old['version'], demand_version=demand['version'])
    path = f"/documents/{old['id']}/replacement"
    new = post(c, path, body)
    assert new['id'] != old['id'] and new['version'] == 1 and new['status'] == service.DRAFT
    assert new['replacement_of'] == dict(id=old['id'], version=old['version'], demand_version=old['data']['demand_version'])
    assert not new['data']['lines'] and new['data']['supplier_reference'] == '' and new['data']['tax_rate'] is None
    assert not {'approved_by', 'pending_change', 'last_change'} & new.keys()
    assert not new['release_gate']['can_release'] and not new['effective_on_order']
    assert post(c, path, body) == new  # exact receipt retry
    assert c.get(history_url).json() == history
    assert c.post(BASE + path, json=command(expected_version=old['version'], demand_version=demand['version'])).status_code == 409
    assert c.post(BASE + f"/documents/{new['id']}/actions/submit", json=command(expected_version=1)).status_code == 422
    groups = new['source']['groups']
    if len(groups) > 1:
        assert {g['attribute'] for g in groups} == {'自制', '委外'} and len({g['code'] for g in groups}) == 1
    fields = dict(new['data'], lines=[dict(source_key=g['source_key'], quantity=None, purchase_unit='', unit_price=None) for g in groups if g['purchasable']])
    saved = post(c, f"/documents/{new['id']}", command(expected_version=1, data=fields))
    assert saved['replacement_of'] == new['replacement_of']
    complete = post(c, f"/documents/{new['id']}", command(expected_version=saved['version'], data=data(c)))
    submitted_new = action(c, complete, 'submit')
    c.engineering_auth['user'] = head()
    approved_new = action(c, submitted_new, 'approve')
    assert approved_new['replacement_of'] == new['replacement_of']
    assert c.post(BASE + f"/documents/{new['id']}/actions/release", json=command(expected_version=approved_new['version'])).status_code == 409
    c.engineering_auth['user'] = actor()
    assert post(c, path, body) == new  # old receipt cannot roll the current child back to draft
    assert c.post(BASE + path, json=command(expected_version=old['version'], demand_version=demand['version'])).status_code == 409
    assert c.get(history_url).json() == history
    with Session(c.engine) as db: assert service.view(db, service.record(db, new['id']))['status'] == service.APPROVED


def test_replacement_requires_responsible_cancellation_and_new_reviewed_basis(purchase):
    c = purchase; old = approved(c); c.engineering_auth['user'] = actor()
    path = f"/documents/{old['id']}/replacement"
    assert c.post(BASE + path, json=command(expected_version=old['version'], demand_version=c.demand['version'])).status_code == 409
    pending = post(c, f"/documents/{old['id']}/change", command(expected_version=old['version'], kind='CANCEL'))
    assert c.post(BASE + path, json=command(expected_version=pending['version'], demand_version=c.demand['version'])).status_code == 409
    c.engineering_auth['user'] = head(); cancelled = action(c, pending, 'approve-change'); c.engineering_auth['user'] = actor()
    assert c.post(BASE + path, json=command(expected_version=cancelled['version'], demand_version=c.demand['version'])).status_code == 409


def test_replacement_checks_versions_permissions_and_unreviewed_source(purchase):
    c = purchase; old, demand = replacement_basis(c); path = BASE + f"/documents/{old['id']}/replacement"
    body = command(expected_version=old['version'], demand_version=demand['version'])
    assert c.post(path, json=dict(body, expected_version=old['version'] - 1)).status_code == 409
    assert c.post(path, json=dict(body, demand_version=demand['version'] - 1)).status_code == 409
    assert c.post(path, json=dict(body, data={})).status_code == 422
    for user in (head(), actor(('read',)), actor(factory='huakang-a')):
        c.engineering_auth['user'] = user
        assert c.post(path, json=body).status_code == 403
    c.engineering_auth['user'] = owner(); act(c, demand, 'reopen'); c.engineering_auth['user'] = actor()
    assert c.post(path, json=body).status_code == 409
    with Session(c.engine) as db: assert db.scalar(select(func.count()).select_from(MaterialPurchase)) == 1


def test_replacement_cannot_cross_order_basis(purchase):
    c = purchase; old, demand = replacement_basis(c, other_order=True)
    assert c.post(BASE + f"/documents/{old['id']}/replacement", json=command(expected_version=old['version'], demand_version=demand['version'])).status_code == 409


def test_concurrent_replacement_commands_create_only_one_linked_draft(purchase):
    c = purchase; old, demand = replacement_basis(c)
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(lambda _: c.post(BASE + f"/documents/{old['id']}/replacement",
            json=command(expected_version=old['version'], demand_version=demand['version'])).status_code, range(2)))
    assert sorted(statuses) == [200, 409]
    with Session(c.engine) as db: assert db.scalar(select(func.count()).select_from(MaterialPurchase)) == 2


@pytest.mark.parametrize('initial_status', [service.DRAFT, service.PENDING])
def test_cancel_unapproved_preparation_restores_prior_state_on_rejection(purchase, initial_status):
    c = purchase; fields = data(c)
    if initial_status == service.DRAFT: fields['lines'][0]['quantity'] = None
    original = post(c, '/documents', command(data=fields))
    if initial_status == service.PENDING: original = action(c, original, 'submit')
    # Stale source must not strand internal preparation; cancellation is still reviewed.
    c.engineering_auth['user'] = owner(); act(c, c.demand, 'reopen'); c.engineering_auth['user'] = actor()
    pending = post(c, f"/documents/{original['id']}/change", command(expected_version=original['version'], kind='CANCEL'))
    assert pending['pending_change']['before_status'] == initial_status and pending['data'] == original['data']
    assert c.post(BASE + f"/documents/{pending['id']}/actions/approve-change", json=command(expected_version=pending['version'])).status_code == 403
    assert c.post(BASE + f"/documents/{pending['id']}", json=command(expected_version=pending['version'], data=fields)).status_code == 409
    c.engineering_auth['user'] = head()
    assert c.post(BASE + f"/documents/{pending['id']}/actions/approve", json=command(expected_version=pending['version'])).status_code == 409
    rejected = action(c, pending, 'reject-change')
    assert rejected['status'] == initial_status and rejected['data'] == original['data'] and 'approved_by' not in rejected
    assert rejected['last_change']['before_status'] == initial_status
    c.engineering_auth['user'] = actor()
    key = original['data']['lines'][0]['source_key']
    assert c.post(BASE + f"/documents/{original['id']}/change", json=command(expected_version=rejected['version'], kind='QUANTITY', quantities={key: 99})).status_code == 409
    pending = post(c, f"/documents/{original['id']}/change", command(expected_version=rejected['version'], kind='CANCEL'))
    report = check_report(c, pending)
    assert report['groups'][0]['before_status'] == initial_status
    if initial_status == service.DRAFT:
        assert report['groups'][0]['complete_quantity'] is None and pending['pending_change']['before'][key] is None
    c.engineering_auth['user'] = head(); body = command(expected_version=pending['version'])
    cancelled = post(c, f"/documents/{pending['id']}/actions/approve-change", body)
    assert post(c, f"/documents/{pending['id']}/actions/approve-change", body) == cancelled
    assert cancelled['status'] == service.CANCELLED and cancelled['data'] == original['data'] and 'approved_by' not in cancelled
    assert not cancelled['release_gate']['can_release'] and not cancelled['effective_on_order']
    assert not check_report(c, cancelled)['groups']
    history = c.get(BASE + f"/documents/{original['id']}/history?factory_id=huakang-c").json()['items']
    assert next(item for item in history if item['version'] == original['version']) == original


def test_cancelled_empty_linked_draft_can_be_rebuilt_after_another_review(purchase):
    c = purchase; original, demand = replacement_basis(c)
    child = post(c, f"/documents/{original['id']}/replacement", command(expected_version=original['version'], demand_version=demand['version']))
    c.engineering_auth['user'] = owner(); reopened = act(c, demand, 'reopen')
    c.engineering_auth['user'] = actor()
    pending = post(c, f"/documents/{child['id']}/change", command(expected_version=1, kind='CANCEL'))
    assert pending['pending_change']['before'] == {} and pending['pending_change']['before_status'] == service.DRAFT
    c.engineering_auth['user'] = head(); cancelled = action(c, pending, 'approve-change')
    c.engineering_auth['user'] = owner(); shared = act(c, reopened, 'submit'); c.engineering_auth['user'] = purchaser()
    dated = act(c, shared, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    c.engineering_auth['user'] = owner(); reviewed = act(c, dated, 'self-review'); c.engineering_auth['user'] = actor()
    grandchild = post(c, f"/documents/{child['id']}/replacement", command(expected_version=cancelled['version'], demand_version=reviewed['version']))
    assert grandchild['replacement_of']['id'] == child['id'] and cancelled['replacement_of']['id'] == original['id']
    assert grandchild['data']['lines'] == []
    assert c.post(BASE + f"/documents/{original['id']}/replacement", json=command(expected_version=original['version'], demand_version=reviewed['version'])).status_code == 409


def test_cancel_requests_keep_unapproved_and_approved_preparation_quantities_separate(purchase):
    c = purchase; approved_doc = approved(c); c.engineering_auth['user'] = actor()
    draft = post(c, '/documents', command(data=data(c)))
    for doc in (approved_doc, draft):
        pending = post(c, f"/documents/{doc['id']}/change", command(expected_version=doc['version'], kind='CANCEL'))
    groups = check_report(c, pending)['groups']
    assert len(groups) == 2 and {g['before_status'] for g in groups} == {service.DRAFT, service.APPROVED}
    assert all(g['status'] == service.CHANGE and g['complete_quantity'] == '22' for g in groups)


def test_submit_and_cancel_same_draft_version_cannot_both_succeed(purchase):
    c = purchase; draft = post(c, '/documents', command(data=data(c)))
    commands = [(f"/documents/{draft['id']}/actions/submit", command(expected_version=1)),
                (f"/documents/{draft['id']}/change", command(expected_version=1, kind='CANCEL'))]
    with ThreadPoolExecutor(2) as pool:
        statuses = list(pool.map(lambda pair: c.post(BASE + pair[0], json=pair[1]).status_code, commands))
    assert sorted(statuses) == [200, 409]


@pytest.mark.parametrize('kind', ['CANCEL', 'QUANTITY'])
def test_legacy_pending_change_without_prior_status_still_restores_approved(purchase, kind):
    c = purchase; doc = approved(c); c.engineering_auth['user'] = actor()
    quantities = {doc['data']['lines'][0]['source_key']: 99} if kind == 'QUANTITY' else {}
    pending = post(c, f"/documents/{doc['id']}/change", command(expected_version=doc['version'], kind=kind, quantities=quantities))
    # Append a legacy-shaped snapshot only in the isolated test database; immutable events stay untouched.
    legacy = deepcopy(pending); legacy['pending_change'].pop('before_status'); legacy['version'] += 1
    with Session(c.engine) as db:
        db.get(MaterialPurchase, doc['id']).version = legacy['version']
        db.add(MaterialPurchaseEvent(id=uuid4().hex, factory_id='huakang-c', entity_id=doc['id'], version=legacy['version'],
            operation_id=uuid4().hex, request_hash='legacy-test', result_json=json.dumps(legacy), actor_id='clerk', occurred_at='2026-11-04', reason='legacy-test'))
        db.commit()
    c.engineering_auth['user'] = head(); rejected = action(c, legacy, 'reject-change')
    assert rejected['status'] == service.APPROVED and rejected['data'] == doc['data']


def process_line(process, quantity, **metadata):
    group = comparison_basis()['groups'][0]
    group.update(process=process, base=service.trial.amount(Fraction(quantity)), gross=service.trial.amount(Fraction(quantity)),
                 key='private-occurrence', parent='private-parent', engineering_attribute='private-default', **metadata)
    return group


def process_total(line, processes, quantity):
    return dict(line, processes=processes, base=service.trial.amount(Fraction(quantity)), gross=service.trial.amount(Fraction(quantity)))


def test_process_comparison_detects_redistribution_even_when_global_totals_are_identical():
    before = [process_line('裁床', 2), process_line('裁床', 2), process_line('车缝', 6)]
    after = [process_line('裁床', 3), process_line('车缝', 7)]
    totals = [process_total(before[0], ['裁床', '车缝'], 10)]
    assert compare(dict(version=1, groups=totals, process_dates={}), dict(version=2, groups=totals, process_dates={}))['rows'] == []
    result = compare_processes(before, after, totals, totals)
    assert result['available'] and result['unchanged_count'] == 0
    by_process = {row['process']: row for row in result['rows']}
    assert by_process['裁床']['before']['gross']['value'] == '4'
    assert by_process['裁床']['delta']['gross']['value'] == '-1'
    assert by_process['车缝']['delta']['gross']['value'] == '1'
    assert 'private-' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [('attribute', '委外'), ('unit', '米'), ('material_version', 2)])
def test_process_comparison_does_not_net_different_attributes_units_or_versions(field, value):
    before = [process_line('手工', Fraction(1, 3))]
    after = [process_line('手工', Fraction(1, 3), **{field: value})]
    result = compare_processes(before, after, [process_total(before[0], ['手工'], Fraction(1, 3))],
                               [process_total(after[0], ['手工'], Fraction(1, 3))])
    assert result['available'] and len(result['rows']) == 2
    assert {r['changes'][0] for r in result['rows']} == {'ADDED', 'REMOVED'}
    assert {r['delta']['gross']['numerator'] for r in result['rows']} == {'1', '-1'}
    assert all(r['delta']['gross']['denominator'] == '3' for r in result['rows'])


@pytest.mark.parametrize('defect', ['missing', 'empty', 'no_process', 'wrong_total', 'wrong_process'])
def test_incomplete_process_evidence_is_unavailable_not_zero(defect):
    lines = [process_line('裁床', 1)]; totals = [process_total(lines[0], ['裁床'], 1)]; broken = deepcopy(lines)
    if defect == 'missing': broken = None
    elif defect == 'empty': broken = []
    elif defect == 'no_process': broken[0].pop('process')
    elif defect == 'wrong_total': broken[0]['gross'] = service.trial.amount(Fraction(2))
    else: broken[0]['process'] = '手工'
    result = compare_processes(broken, lines, totals, totals)
    assert not result['available'] and result['rows'] == [] and result['unchanged_count'] is None and result['issue']


def test_process_comparison_retains_exact_loss_shift_and_unchanged_count():
    before = [process_line('手工', Fraction(1, 3)), process_line('裁床', 2)]
    after = deepcopy(before); tiny = Fraction(1, 10**20)
    after[0]['base'] = service.trial.amount(Fraction(1, 3) - tiny)
    after[0]['loss'] = service.trial.amount(tiny)
    old_total = process_total(before[0], ['手工', '裁床'], Fraction(7, 3))
    new_total = dict(old_total, base=service.trial.amount(Fraction(7, 3) - tiny), loss=service.trial.amount(tiny))
    result = compare_processes(before, after, [old_total], [new_total])
    assert result['available'] and result['unchanged_count'] == 1 and len(result['rows']) == 1
    change = result['rows'][0]
    assert change['changes'] == ['QUANTITY'] and change['delta']['gross']['value'] == '0'
    assert Fraction(int(change['delta']['base']['numerator']), int(change['delta']['base']['denominator'])) == -tiny
