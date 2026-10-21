"""Mixed actions use existing source transitions inside one transaction."""
from uuid import uuid4
import pytest
from sqlalchemy import select
from test_molding_sample_api import make_client, login_as, ensure_test_user
from test_carton_procurement_api import _create_order, _order_payload
from test_carton_supplier_portal import grant_supplier_permissions
from test_carton_special_requests import create_body, command, ok, BASE, FACTORY

ENDPOINT = '/api/carton-unified-orders'


@pytest.fixture(autouse=True)
def isolated_directory(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)


def sources(client):
    login_as(client, 'admin')
    order = _create_order(client, submit_supplier=False)
    sample = ok(client.post(BASE, json=create_body()), 201)
    # Workshop comes from the same-factory authoritative master table.
    from app.db import SessionLocal
    from app.models.carton_master import CartonMasterRecord
    with SessionLocal() as db:
        workshop = CartonMasterRecord(id='batch-workshop', factory_id=FACTORY, kind='WORKSHOP', identity='BATCH', code='BATCH', status='ACTIVE', revision=1, data_json='{"name":"测试车间"}')
        db.add(workshop); db.commit()
    misc = ok(client.post(BASE, json={**create_body('WORKSHOP_MISC'), 'workshop_id': workshop.id}), 201)
    refs = [{'kind': 'PURCHASE', 'id': order['order_no'], 'expected_revision': order['revision']}]
    refs += [{'kind': row['kind'], 'id': row['id'], 'expected_revision': row['revision']} for row in (sample, misc)]
    return order, sample, misc, refs


def payload(refs, action='CONFIRM'):
    return dict(factory_id=FACTORY, request_id=uuid4().hex, items=refs, action=action, reason='' if action == 'CONFIRM' else '测试批量操作原因')


def statuses(client, order, sample, misc):
    regular = ok(client.post(ENDPOINT+'/selected', json={'factory_id': FACTORY, 'items': [{'kind': 'PURCHASE', 'id': order['order_no']}]}))[0]['order']
    return [regular['status']] + [ok(client.get(BASE+'/'+row['id'], params={'factory_id': FACTORY}))['status'] for row in (sample, misc)]


def test_mixed_confirm_is_atomic_revision_guarded_and_replay_safe(monkeypatch):
    with make_client(monkeypatch) as client:
        order, sample, misc, refs = sources(client)
        body = payload(refs)
        stale = {**body, 'items': [*refs[:-1], {**refs[-1], 'expected_revision': 999}]}
        assert client.post(ENDPOINT+'/batch-actions', json=stale).status_code == 409
        assert statuses(client, order, sample, misc) == ['CONFIRMED', 'SUBMITTED', 'SUBMITTED']
        result = ok(client.post(ENDPOINT+'/batch-actions', json=body))
        assert result['count'] == 3
        assert statuses(client, order, sample, misc) == ['PENDING_SUPPLIER', 'SENT', 'SENT']
        assert ok(client.post(ENDPOINT+'/batch-actions', json=body)) == result
        assert client.post(ENDPOINT+'/batch-actions', json={**body, 'reason': '改变请求内容'}).status_code == 409


def test_last_child_failure_rolls_back_purchase_issues_and_all_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        order, sample, misc, refs = sources(client)
        from app.services import carton_special_requests as special
        original = special.action
        def fail_last(db, user, identifier, *args, **kwargs):
            if identifier == misc['id']:
                from fastapi import HTTPException
                raise HTTPException(409, '模拟最后单据冲突')
            return original(db, user, identifier, *args, **kwargs)
        monkeypatch.setattr(special, 'action', fail_last)
        assert client.post(ENDPOINT+'/batch-actions', json=payload(refs)).status_code == 409
        assert statuses(client, order, sample, misc) == ['CONFIRMED', 'SUBMITTED', 'SUBMITTED']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonPurchaseOrderIssue
        with SessionLocal() as db:
            assert db.scalar(select(CartonPurchaseOrderIssue).where(CartonPurchaseOrderIssue.order_id == order['id'])) is None


@pytest.mark.parametrize('action', ['CANCEL', 'DELETE'])
def test_mixed_cancel_delete_and_retained_confirmed_number(monkeypatch, action):
    with make_client(monkeypatch) as client:
        order, sample, misc, refs = sources(client)
        body = payload(refs, action)
        result = ok(client.post(ENDPOINT+'/batch-actions', json=body))
        assert result['count'] == 3 and ok(client.post(ENDPOINT+'/batch-actions', json=body)) == result
        if action == 'CANCEL':
            assert statuses(client, order, sample, misc) == ['CANCELLED'] * 3
        else:
            from app.db import SessionLocal
            from app.models.carton_procurement import CartonOrder, CartonOrderLine
            from app.models.carton_special_requests import SpecialRequest
            with SessionLocal() as db:
                retained = db.get(CartonOrder, order['id'])
                assert retained is not None and retained.deleted_at
                assert db.scalar(select(CartonOrderLine).where(CartonOrderLine.order_id == retained.id)) is not None
                assert db.get(SpecialRequest, sample['id']) is not None
            assert ok(client.get(ENDPOINT, params={'factory_id': FACTORY}))['total'] == 0
            assert ok(client.post(ENDPOINT+'/selected', json={'factory_id': FACTORY, 'items': refs})) == []
            replacement = ok(client.post('/api/carton-procurement/orders', json=_order_payload()), 201)
            assert replacement['order_no'] != order['order_no']


def test_selection_and_commands_recheck_source_factory_and_action_permissions(monkeypatch):
    with make_client(monkeypatch) as client:
        order, sample, misc, refs = sources(client)
        assert len(ok(client.post(ENDPOINT+'/selected', json={'factory_id': FACTORY, 'items': refs}))) == 3
        assert client.post(ENDPOINT+'/batch-actions', json=payload([refs[1], refs[1]])).status_code == 422
        assert client.post(ENDPOINT+'/batch-actions', json={**payload(refs), 'factory_id': 'huakang-a'}).status_code in {403, 404}
        ensure_test_user('engineer')
        grant_supplier_permissions('user-engineer', ('carton_procurement:special_request_submit',))
        login_as(client, 'engineer')
        assert client.post(ENDPOINT+'/batch-actions', json=payload(refs)).status_code == 403
        assert client.post(ENDPOINT+'/selected', json={'factory_id': FACTORY, 'items': refs}).status_code == 403
        login_as(client, 'admin')
        assert statuses(client, order, sample, misc) == ['CONFIRMED', 'SUBMITTED', 'SUBMITTED']


def test_session_is_rechecked_after_factory_lock_before_replay_or_mutation(monkeypatch):
    with make_client(monkeypatch) as client:
        order, sample, misc, refs = sources(client)
        from app.services import carton_special_requests as special
        from app.models.auth import AuthSession
        original = special.locked_actor
        def revoke(db, user, factory):
            actor = original(db, user, factory)
            for session in db.scalars(select(AuthSession).where(AuthSession.user_id == actor.id)):
                session.status = 'revoked'
            db.flush()
            return actor
        monkeypatch.setattr(special, 'locked_actor', revoke)
        assert client.post(ENDPOINT+'/batch-actions', json=payload(refs)).status_code == 401
        monkeypatch.setattr(special, 'locked_actor', original)
        login_as(client, 'admin')
        assert statuses(client, order, sample, misc) == ['CONFIRMED', 'SUBMITTED', 'SUBMITTED']
