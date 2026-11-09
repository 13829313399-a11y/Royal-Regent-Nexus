from dataclasses import replace
from concurrent.futures import ThreadPoolExecutor
import json
from uuid import uuid4
import pytest
from sqlalchemy.orm import Session
from test_material_plan_orders import linked, reader, body, client, engineering_client, engineering_material_attribute
from test_material_plan import request, payload, BASE, sales
from test_engineering_bom import command
from app.models.customer_order_ledger import OrderLedgerLine
from app.services.material_plan_workflow import DRAFT, DATES, REVIEW, REVIEWED
from app.services.material_plan_workflow import apply
from app.schemas.material_plan import DatesRequest
from app.schemas.engineering_bom import Command
from fastapi import HTTPException
from app.services import engineering_bom as engineering


def owner(identity='sales-1'):
    actor = reader()
    codes = actor.permissions | {'material_plan:submit', 'material_plan:self_review'}
    return replace(actor, id=identity, permissions=codes, active_permission_codes=actor.active_permission_codes | codes,
        grants=(replace(actor.grants[0], permissions=codes),))


def purchaser(write=True, department='pmc-warehouse', factory='huakang-c'):
    return sales('buyer-1', actions=('dates_read', 'dates_write') if write else ('dates_read',), department=department, factory=factory)


@pytest.fixture
def flow(linked):
    linked.engineering_auth['user'] = owner()
    return linked


def act(c, saved, action, **fields):
    return request(c, f"/drafts/{saved['id']}/{action}", command(expected_version=saved['version'], **fields))


def submitted(c):
    draft = request(c, '/drafts', body(c))
    return act(c, draft, 'submit')


@pytest.mark.parametrize('engineering_material_attribute', ['客供'], indirect=True)
@pytest.mark.parametrize('action', ['submit', 'self-review'])
def test_legacy_customer_exemption_cannot_advance_workflow(flow, monkeypatch, action):
    with monkeypatch.context() as legacy:
        legacy.setattr(engineering, 'validate_material_loss', lambda *args: None)
        saved = request(flow, '/drafts', body(flow, loss_exemptions={'fabric': True}))
        if action == 'self-review':
            saved = act(flow, saved, 'submit'); flow.engineering_auth['user'] = purchaser()
            saved = act(flow, saved, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
            flow.engineering_auth['user'] = owner()
    history_url = BASE + f"/drafts/{saved['id']}/history?factory_id=huakang-c"
    before = flow.get(history_url).json()
    response = flow.post(BASE + f"/drafts/{saved['id']}/{action}", json=command(expected_version=saved['version']))
    assert response.status_code == 422 and '客供' in response.text
    assert flow.get(history_url).json() == before


@pytest.mark.parametrize('engineering_material_attribute', ['外购', '客供'], indirect=True)
def test_complete_flow_and_reopen_keep_immutable_history_and_never_release(flow):
    saved = submitted(flow)
    assert saved['status'] == DATES
    flow.engineering_auth['user'] = purchaser()
    queue = flow.get(BASE + '/procurement/workspace?factory_id=huakang-c').json()['items']
    assert len(queue) == 1
    assert not {'inputs', 'bom', 'order_basis', 'customer_name', 'reference'} & set(queue[0])
    assert 'PO-100' not in json.dumps(queue)
    partial = act(flow, saved, 'dates', dates={'裁床': '2026-11-12'})
    assert partial['status'] == DATES and partial['process_dates'] == {'裁床': '2026-11-12'}
    complete = act(flow, partial, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    assert complete['status'] == REVIEW
    flow.engineering_auth['user'] = owner()
    reviewed = act(flow, complete, 'self-review')
    assert reviewed['status'] == REVIEWED and reviewed['reviewed_by']['id'] == owner().id
    assert reviewed['result']['net_purchase_quantity'] is None
    assert reviewed['result']['release_gate'] == {'can_release': False, 'blockers': ['STOCK_VERIFICATION', 'ON_ORDER_ALLOCATION', 'RELEASE_WORKFLOW']}
    assert reviewed['owner_id'] == owner().id and reviewed['date_actor']['id'] == 'buyer-1'
    flow.engineering_auth['user'] = purchaser()
    assert flow.post(BASE + f"/drafts/{reviewed['id']}/dates", json=command(expected_version=reviewed['version'], dates={})).status_code == 409
    flow.engineering_auth['user'] = owner()
    reopened = act(flow, reviewed, 'reopen')
    assert reopened['status'] == DRAFT and not reopened['process_dates'] and 'reviewed_by' not in reopened
    history = flow.get(BASE + f"/drafts/{saved['id']}/history?factory_id=huakang-c").json()['items']
    assert len(history) == 6 and history[1] == reviewed
    flow.engineering_auth['user'] = purchaser()
    assert flow.get(BASE + '/procurement/workspace?factory_id=huakang-c').json()['items'] == []


@pytest.mark.parametrize('engineering_material_attribute', ['自制'], indirect=True)
def test_grouping_survives_dates_and_self_review(flow):
    saved = request(flow, '/drafts', body(flow, material_attributes={'sew': '自制', 'fabric': '委外'}))
    totals = saved['result']['totals']
    saved = act(flow, saved, 'submit'); flow.engineering_auth['user'] = purchaser()
    saved = act(flow, saved, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    assert {line['attribute'] for line in saved['lines']} == {'自制', '委外'}
    flow.engineering_auth['user'] = owner()
    saved = act(flow, saved, 'self-review')
    assert saved['result']['totals'] == totals
    assert {(t['attribute'], t['gross']['value']) for t in totals} == {('自制', '105'), ('委外', '21')}


def test_submitted_inputs_locked_and_only_owner_can_review(flow):
    saved = submitted(flow)
    assert flow.post(BASE + f"/drafts/{saved['id']}", json=body(flow) | {'expected_version': saved['version']}).status_code == 409
    assert flow.post(BASE + f"/drafts/{saved['id']}/self-review", json=command(expected_version=saved['version'])).status_code == 409
    flow.engineering_auth['user'] = purchaser()
    ready = act(flow, saved, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    flow.engineering_auth['user'] = owner('another')
    assert flow.post(BASE + f"/drafts/{saved['id']}/self-review", json=command(expected_version=ready['version'])).status_code == 404
    flow.engineering_auth['user'] = owner()
    with Session(flow.engine) as db:
        row = db.get(OrderLedgerLine, 'order-1'); row.revision += 1; db.commit()
    assert flow.post(BASE + f"/drafts/{saved['id']}/self-review", json=command(expected_version=ready['version'])).status_code == 409
    assert act(flow, ready, 'reopen')['status'] == DRAFT


@pytest.mark.parametrize('actor', [sales(), purchaser(False), purchaser(department='sales-business'), purchaser(factory='huakang-a')])
def test_procurement_write_needs_explicit_scoped_grants(flow, actor):
    saved = submitted(flow); flow.engineering_auth['user'] = actor
    assert flow.post(BASE + f"/drafts/{saved['id']}/dates", json=command(expected_version=saved['version'], dates={})).status_code == 403


def test_date_validation_clear_and_conflicting_versions(flow):
    saved = submitted(flow); flow.engineering_auth['user'] = purchaser()
    for dates in [{'unknown': '2026-11-12'}, {'裁床': 'not-date'}]:
        assert flow.post(BASE + f"/drafts/{saved['id']}/dates", json=command(expected_version=saved['version'], dates=dates)).status_code == 422
    ready = act(flow, saved, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    assert act(flow, ready, 'dates', dates={'裁床': '2026-11-12', '车缝': None})['status'] == DATES
    assert flow.post(BASE + f"/drafts/{saved['id']}/dates", json=command(expected_version=ready['version'], dates={})).status_code == 409


def test_concurrent_retry_is_single_event_and_cross_action_reuse_rejected(flow):
    saved = request(flow, '/drafts', body(flow))
    cmd = command(expected_version=saved['version'])
    path = f"/drafts/{saved['id']}/submit"
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: request(flow, path, cmd), range(2)))
    assert results[0] == results[1]
    assert flow.post(BASE + f"/drafts/{saved['id']}/reopen", json=cmd).status_code == 409
    assert flow.post(BASE + f"/drafts/{saved['id']}/submit", json=cmd | {'operation_id': uuid4().hex}).status_code == 409


def test_unbound_and_private_drafts_never_enter_procurement(flow):
    saved = request(flow, '/drafts', payload(flow))
    assert flow.post(BASE + f"/drafts/{saved['id']}/submit", json=command(expected_version=1)).status_code == 422
    flow.engineering_auth['user'] = purchaser()
    assert flow.get(BASE + '/procurement/workspace?factory_id=huakang-c').json()['items'] == []
    assert flow.post(BASE + f"/drafts/{saved['id']}/dates", json=command(expected_version=1, dates={})).status_code == 409
    assert flow.get(BASE + f"/drafts/{saved['id']}/history?factory_id=huakang-c").status_code == 403


def test_review_and_date_change_cannot_both_accept_same_version(flow):
    saved = submitted(flow); flow.engineering_auth['user'] = purchaser()
    ready = act(flow, saved, 'dates', dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    actions = [(owner(), 'self-review', Command(**command(expected_version=ready['version']))),
        (purchaser(), 'dates', DatesRequest(**command(expected_version=ready['version'], dates={'裁床': '2026-11-13', '车缝': '2026-11-16'})))]
    def run(args):
        with Session(flow.engine) as db:
            try:
                apply(db, args[0], ready['id'], args[1], args[2])
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(run, actions)) == [200, 409]


def test_date_receipt_replay_is_projected_and_revocation_still_blocks(flow):
    saved = submitted(flow); flow.engineering_auth['user'] = purchaser()
    cmd = command(expected_version=saved['version'], dates={'裁床': '2026-11-12', '车缝': '2026-11-15'})
    path = f"/drafts/{saved['id']}/dates"
    dated = request(flow, path, cmd)
    flow.engineering_auth['user'] = owner(); act(flow, dated, 'self-review')
    flow.engineering_auth['user'] = purchaser()
    assert request(flow, path, cmd) == dated
    assert 'inputs' not in dated and 'order_basis' not in dated
    flow.engineering_auth['user'] = purchaser(False)
    assert flow.post(BASE + path, json=cmd).status_code == 403
