"""Optional authoritative order basis. All writes use isolated test databases."""
from dataclasses import replace
from decimal import Decimal
import hashlib
import json
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from test_material_plan import (client, engineering_client, engineering_material_attribute, sales, payload, request, BASE)
from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.models.material_plan import MaterialPlanEvent
from app.schemas.material_plan import TrialRequest
from app.services import material_plan as service
from app.services.auth import AuthOverrideContext


def reader():
    actor = sales()
    codes = actor.permissions | {'customer_order:read'}
    return replace(actor, permissions=codes, active_permission_codes=actor.active_permission_codes | codes,
        grants=(replace(actor.grants[0], permissions=codes),))


@pytest.fixture
def linked(client):
    Line.__table__.create(client.engine)
    with Session(client.engine) as db:
        for identity, factory, reference in [('order-1', 'huakang-c', 'PO-100'), ('foreign', 'huakang-a', 'SECRET'), ('literal', 'huakang-c', 'PO%_')]:
            db.add(Line(id=identity, factory_id=factory, customer_code='synthetic', customer_name='合成客户', identity_key=identity,
                reference_no=reference, product_no=client.published['data']['item_no'], quantity=Decimal('100'), shipped_quantity=Decimal('0'),
                status='active', version=1, revision=1, data={'private_unrelated': 'must not leak'}, created_at='2026-11-04', updated_at='2026-11-04'))
        db.commit()
    client.engineering_auth['user'] = reader()
    return client


def body(client, **changes):
    return payload(client, order={'line_id': 'order-1', 'revision': 1}, **changes)


def test_bound_snapshot_preserves_order_and_attribute_groups(linked):
    original = request(linked, '/drafts', body(linked))
    basis = original['result']['order_basis']
    assert basis['line_id'] == 'order-1' and basis['quantity'] == '100.0000'
    assert 'data' not in basis and 'private_unrelated' not in json.dumps(original)
    assert original['result']['release_gate'] == {'can_release': False, 'blockers': [
        'STOCK_VERIFICATION', 'ON_ORDER_ALLOCATION', 'PROCESS_DATES', 'RELEASE_WORKFLOW']}
    assert original['result']['net_purchase_quantity'] is None
    assert '正式订单绑定' not in original['result']['pending']
    with Session(linked.engine) as db:
        row = db.get(Line, 'order-1')
        assert (row.revision, row.version, row.quantity, row.shipped_quantity) == (1, 1, 100, 0)


@pytest.mark.parametrize('engineering_material_attribute', ['自制', '委外'], indirect=True)
def test_order_bound_demand_keeps_same_code_different_attributes_separate(linked):
    saved = request(linked, '/drafts', body(linked, material_attributes={'sew': '自制', 'fabric': '委外'}))
    totals = saved['result']['totals']
    assert len({row['code'] for row in totals}) == 1
    assert {(row['attribute'], row['gross']['value']) for row in totals} == {('自制', '105'), ('委外', '21')}


def test_changed_order_blocks_recalculation_but_not_original_receipt_or_history(linked):
    command = body(linked)
    first = request(linked, '/drafts', command)
    with Session(linked.engine) as db:
        row = db.get(Line, 'order-1'); row.revision = 2; row.version = 2; row.quantity = Decimal('80'); db.commit()
    assert linked.post(BASE + '/preview', json=command).status_code == 409
    assert linked.post(BASE + f"/drafts/{first['id']}", json=body(linked) | {'expected_version': 1}).status_code == 409
    assert request(linked, '/drafts', command) == first
    assert linked.get(BASE + f"/drafts/{first['id']}/history?factory_id=huakang-c").json()['items'] == [first]
    update = body(linked, quantity='80'); update['data']['order']['revision'] = 2; update['expected_version'] = 1
    revised = request(linked, f"/drafts/{first['id']}", update)
    assert revised['result']['order_basis']['quantity'] == '80.0000'
    assert revised['result']['lines'][0]['gross']['value'] == '84'


@pytest.mark.parametrize('changes,code', [({'status': 'cancelled'}, 409), ({'quantity': None}, 409),
    ({'product_no': 'different'}, 422), ({'quantity': Decimal('99')}, 422)])
def test_invalid_order_basis_never_persists(linked, changes, code):
    with Session(linked.engine) as db:
        row = db.get(Line, 'order-1')
        for key, value in changes.items(): setattr(row, key, value)
        db.commit()
    assert linked.post(BASE + '/drafts', json=body(linked)).status_code == code
    with Session(linked.engine) as db:
        assert db.scalar(select(func.count()).select_from(MaterialPlanEvent)) == 0


def test_search_scope_literal_queries_and_missing_schema(linked):
    response = linked.get(BASE + '/orders?factory_id=huakang-c').json()
    assert {row['line_id'] for row in response['items']} == {'order-1', 'literal'}
    literal = linked.get(BASE + '/orders', params={'factory_id': 'huakang-c', 'q': '%_'}).json()
    assert [row['line_id'] for row in literal['items']] == ['literal']
    command = body(linked); command['data']['order']['line_id'] = 'foreign'
    assert linked.post(BASE + '/drafts', json=command).status_code == 404
    Line.__table__.drop(linked.engine)
    assert linked.get(BASE + '/orders?factory_id=huakang-c').status_code == 503
    assert linked.post(BASE + '/drafts', json=body(linked)).status_code == 503
    # An unavailable order subsystem must not disable independent manual trials.
    assert request(linked, '/preview', payload(linked))['release_gate']['can_release'] is False


def test_order_permission_revocation_hides_snapshots_and_blocks_replay(linked):
    command = body(linked); saved = request(linked, '/drafts', command)
    linked.engineering_auth['user'] = sales()
    assert linked.get(BASE + '/orders?factory_id=huakang-c').status_code == 403
    assert linked.post(BASE + '/preview', json=command).status_code == 403
    assert linked.post(BASE + '/drafts', json=command).status_code == 403
    assert linked.get(BASE + '/workspace?factory_id=huakang-c').json()['drafts'] == []
    assert linked.get(BASE + f"/drafts/{saved['id']}/history?factory_id=huakang-c").status_code == 403
    assert linked.post(BASE + f"/drafts/{saved['id']}", json=payload(linked) | {'expected_version': 1}).status_code == 403


@pytest.mark.parametrize('wrong_scope', ['department', 'factory', 'deny'])
def test_order_permission_must_be_sales_and_same_factory(linked, wrong_scope):
    actor = reader()
    order_grant = replace(actor.grants[0], permissions=frozenset({'customer_order:read'}))
    if wrong_scope == 'department': order_grant = replace(order_grant, department='pmc-warehouse')
    if wrong_scope == 'factory': order_grant = replace(order_grant, factory_id='huakang-a')
    actor = replace(actor, grants=(sales().grants[0], order_grant))
    if wrong_scope == 'deny':
        actor = replace(actor, overrides=(AuthOverrideContext(id='deny', permission_code='customer_order:read',
            effect='deny', factory_id='huakang-c', department='sales-business'),))
    linked.engineering_auth['user'] = actor
    assert linked.get(BASE + '/orders?factory_id=huakang-c').status_code == 403
    assert linked.post(BASE + '/drafts', json=body(linked)).status_code == 403


def test_old_unbound_receipt_with_attributes_replays(linked):
    command = payload(linked, material_attributes={'sew': '外购'})
    saved = request(linked, '/drafts', command)
    legacy = TrialRequest.model_validate(command).model_dump(mode='json'); legacy['data'].pop('order')
    # Simulate an old immutable receipt by inserting a new operation, never editing evidence.
    command['operation_id'] = uuid4().hex; legacy['operation_id'] = command['operation_id']
    legacy_hash = hashlib.sha256(service.bom.dump([reader().id, '', legacy]).encode()).hexdigest()
    saved['inputs'].pop('order'); saved['result'].pop('order_basis'); saved['result'].pop('release_gate')
    with Session(linked.engine) as db:
        db.add(MaterialPlanEvent(id=uuid4().hex, factory_id='huakang-c', operation_id=command['operation_id'], request_hash=legacy_hash,
            entity_id=saved['id'], version=1, result_json=json.dumps(saved), actor_id=reader().id, occurred_at=saved['occurred_at'], reason=saved['reason']))
        db.commit()
    assert request(linked, '/drafts', command) == saved
    command['data']['order'] = {'line_id': 'order-1', 'revision': 1}
    assert linked.post(BASE + '/drafts', json=command).status_code == 409
