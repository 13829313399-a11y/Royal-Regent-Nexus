"""Synthetic integration tests for business-notice carton changes.

All databases and file storage are confined to pytest's explicit basetemp.
"""
from decimal import Decimal

import pytest
from sqlalchemy import select

from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _order_payload, _submit_order

LEDGER = '/api/customer-order-ledger'
CARTON = '/api/carton-procurement'


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    import test_molding_sample_api
    monkeypatch.setattr(test_molding_sample_api, 'TEST_TMP_DIR', tmp_path)
    for name in ('TEMP', 'TMP', 'TMPDIR', 'COLLABORATION_STORAGE_DIR', 'ASSISTANT_STORAGE_DIR', 'DOCUMENT_TOOLS_STORAGE_DIR'):
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setenv(name, str(path))
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///' + (tmp_path / 'bootstrap.db').as_posix())
    monkeypatch.setenv('ONLINE_DOCUMENTS_ENABLED', 'false')
    monkeypatch.setenv('QC_DEPARTMENT_MANAGED', 'false')


def ok(response, status=200):
    assert response.status_code == status, response.text
    return response.json()


def seed(client, status='ISSUED', *, new_qty='120', new_date='2026-08-12', manual=False, existing=None, initial_qty='100'):
    """Create an issued carton and two real versions of a matching sales notice."""
    login_as(client, 'admin')
    _ensure_dickie_customer(client)
    login_as(client, 'admin')
    ok(client.post(CARTON + '/customers/business-sync', params={'factory_id': 'huaxing'}))
    payload = _order_payload()
    payload['product_order_quantity'] = '100'
    payload['lines'][0]['usage_quantity'] = '10'
    if manual:
        payload.update(customer_due_date='2026-08-12', due_date='2026-08-10', plan_date_manual=True)
    if status == 'DRAFT':
        payload['status'] = 'DRAFT'
    carton = existing
    if carton is None:
        carton = ok(client.post(CARTON + '/orders', json=payload), 201)
        if status == 'ISSUED':
            carton = _submit_order(client, carton)
    from app.db import SessionLocal
    from app.models.customer_order_ledger import OrderLedgerDispatch
    from app.schemas.customer_order_ledger import AmendIn, DispatchIn
    from app.services import customer_order_ledger as service
    with SessionLocal() as db:
        preview = dict(factory_id='huaxing', customer_code='dickie', customer_name='Dickie', rows=[dict(
            id='synthetic-1', reference_no=payload['contract_no'], product_no=payload['item_no'], po_no='PO-QA',
            quantity=initial_qty, requested_ship_date='2026-08-12', packaging='', lineage={}, issues=[])])
        imported = service.import_preview(db, preview=preview, files=[('qa.pdf', b'qa', 'formal')],
            source_kind='formal', actor='合成业务员', reason='测试', controls={})
        line = service.get_line(db, 'huaxing', imported['items'][0]['id'])
        service.dispatch(db, line, DispatchIn(expected_revision=line.revision, recipients=['pmc', 'warehouse']), '合成业务员')
        old = db.scalar(select(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id == line.id, OrderLedgerDispatch.recipient == 'pmc'))
        old_id = old.id
        service.amend(db, line, AmendIn(expected_revision=line.revision, quantity=new_qty,
            requested_ship_date=new_date, note='', reason='客户通知变更'), '合成业务员')
        new = db.scalar(select(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id == line.id,
            OrderLedgerDispatch.version == line.version, OrderLedgerDispatch.recipient == 'pmc'))
        new_id = new.id
        db.commit()
    return carton, old_id, new_id


def call(client, dispatch, action, payload=None, recipient='pmc', factory='huaxing'):
    return client.post(LEDGER + f'/inbox/{dispatch}/carton-change-{action}',
        params={'factory_id': factory, 'recipient': recipient}, json=payload)


def snapshot(carton, dispatch):
    from app.db import SessionLocal
    from app.models.customer_order_ledger import OrderLedgerDispatch
    from app.models.carton_procurement import CartonOrder, CartonPurchaseOrderIssue, CartonAuditEvent
    from sqlalchemy import func
    with SessionLocal() as db:
        order = db.get(CartonOrder, carton['id'])
        notice = db.get(OrderLedgerDispatch, dispatch)
        return (order.revision, str(order.product_order_quantity), order.customer_due_date, order.due_date,
            notice.received_at, db.scalar(select(func.count()).select_from(CartonPurchaseOrderIssue).where(
                CartonPurchaseOrderIssue.order_id == order.id)),
            db.scalar(select(func.count()).select_from(CartonAuditEvent).where(
                CartonAuditEvent.event_type == 'BUSINESS_LEDGER_CARTON_APPLIED')))


@pytest.mark.parametrize('status', ['ISSUED', 'CONFIRMED', 'DRAFT'])
def test_preview_then_confirm_is_atomic_and_idempotent(monkeypatch, status):
    with make_client(monkeypatch) as client:
        carton, old, current = seed(client, status)
        before = snapshot(carton, current)
        result = ok(call(client, current, 'preview'))
        assert result['can_confirm'], result['blocked_reason']
        assert Decimal(result['before']['product_order_quantity']) == 100
        assert Decimal(result['after']['product_order_quantity']) == 120
        assert result['fingerprint'] and snapshot(carton, current) == before
        assert call(client, old, 'preview').status_code == 409
        rejected = call(client, current, 'confirm', {'confirmed': False, 'fingerprint': result['fingerprint']})
        assert rejected.status_code == 422 and snapshot(carton, current) == before
        saved = ok(call(client, current, 'confirm', {'confirmed': True, 'fingerprint': result['fingerprint']}))
        assert saved['processed'] and Decimal(saved['after']['product_order_quantity']) == 120
        after = snapshot(carton, current)
        assert Decimal(after[1]) == 120 and after[4] and after[6] == before[6] + 1
        assert after[5] == before[5] + (1 if status == 'ISSUED' else 0)
        retry = ok(call(client, current, 'confirm', {'confirmed': True, 'fingerprint': result['fingerprint']}))
        assert retry['processed'] == saved['processed'] and snapshot(carton, current) == after
        from app.db import SessionLocal
        from app.models.customer_order_ledger import OrderLedgerDispatch
        with SessionLocal() as db:
            other = db.scalar(select(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id ==
                db.get(OrderLedgerDispatch, current).line_id, OrderLedgerDispatch.version == 2,
                OrderLedgerDispatch.recipient == 'warehouse')).id
        other_view = ok(call(client, other, 'preview', recipient='warehouse'))
        assert other_view['processed'] and not other_view['can_confirm']
        other_retry = ok(call(client, other, 'confirm', {'confirmed': True, 'fingerprint': other_view['fingerprint']}, recipient='warehouse'))
        assert other_retry['processed'] == saved['processed']
        assert snapshot(carton, current) == after


def test_stale_fingerprint_and_publish_failure_roll_back_everything(monkeypatch):
    from fastapi import HTTPException
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert preview['can_confirm'], preview['blocked_reason']
        assert call(client, current, 'confirm', {'confirmed': True, 'fingerprint': '0' * 64}).status_code == 409
        assert snapshot(carton, current) == before
        from app.services import carton_procurement as core
        def fail(*args, **kwargs):
            raise HTTPException(409, '模拟供应商版本生成失败')
        monkeypatch.setattr(core, 'create_purchase_order_issue', fail)
        assert call(client, current, 'confirm', {'confirmed': True, 'fingerprint': preview['fingerprint']}).status_code == 409
        assert snapshot(carton, current) == before


@pytest.mark.parametrize('status', ['ISSUED', 'CONFIRMED', 'DRAFT'])
def test_customer_date_change_preserves_manual_plan(monkeypatch, status):
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client, status, new_qty='100', new_date='2026-08-15', manual=True)
        preview = ok(call(client, current, 'preview'))
        assert preview['can_confirm'], preview['blocked_reason']
        assert preview['before']['due_date'] == preview['after']['due_date'] == '2026-08-10'
        assert preview['after']['customer_due_date'] == '2026-08-15' and preview['after']['plan_date_manual']
        result = ok(call(client, current, 'confirm', {'confirmed': True, 'fingerprint': preview['fingerprint']}))
        assert result['after']['customer_due_date'] == '2026-08-15'
        assert result['after']['due_date'] == '2026-08-10' and result['after']['plan_date_manual']


@pytest.mark.parametrize('invalid', ['manual_basis', 'quantity_mismatch', 'missing_binding'])
def test_matching_and_quantity_guards_leave_notice_and_order_untouched(monkeypatch, invalid):
    from decimal import Decimal
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        from app.db import SessionLocal
        from app.models.carton_master import CartonMasterRecord
        from app.models.carton_procurement import CartonOrder
        with SessionLocal() as db:
            if invalid == 'missing_binding':
                binding = db.scalar(select(CartonMasterRecord).where(CartonMasterRecord.factory_id == 'huaxing',
                    CartonMasterRecord.kind == 'BUSINESS_CUSTOMER', CartonMasterRecord.code == 'dickie'))
                binding.status = 'INACTIVE'
            else:
                order = db.get(CartonOrder, carton['id'])
                if invalid == 'manual_basis': order.quantity_basis = 'EXPLICIT'
                else: order.product_order_quantity = Decimal('90')
            db.commit()
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert not preview['can_confirm'] and preview['blocked_reason']
        assert snapshot(carton, current) == before
        assert call(client, current, 'confirm', {'confirmed': True, 'fingerprint': '0' * 64}).status_code == 409
        assert snapshot(carton, current) == before


def test_reduction_below_physical_receipts_is_blocked_without_signing(monkeypatch):
    from test_carton_transaction_guards_api import draft, confirm
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client, new_qty='5')
        receipt = ok(draft(client, carton, 8), 201)
        ok(confirm(client, receipt))
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert not preview['can_confirm'] and preview['blocked_reason']
        assert snapshot(carton, current) == before


def test_other_factory_and_unprivileged_actor_cannot_access_notice(monkeypatch):
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        before = snapshot(carton, current)
        cross = call(client, current, 'preview', factory='huakang-a')
        assert cross.status_code in (403, 404)
        login_as(client, 'qc_inspector')
        assert call(client, current, 'preview').status_code == 403
        assert call(client, current, 'confirm', {'confirmed': True, 'fingerprint': '0' * 64}).status_code == 403
        assert snapshot(carton, current) == before


def test_order_changed_after_preview_invalidates_fingerprint(monkeypatch):
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        preview = ok(call(client, current, 'preview'))
        assert preview['can_confirm'], preview['blocked_reason']
        changed = ok(client.post(CARTON + f"/orders/{carton['order_no']}/dates", json={
            'factory_id': 'huaxing', 'expected_revision': carton['revision'], 'due_date': '2026-08-13',
            'plan_date_manual': True, 'reason': '仓库同时调整计划交期'}))
        assert changed['revision'] > carton['revision']
        before = snapshot(carton, current)
        assert call(client, current, 'confirm', {'confirmed': True, 'fingerprint': preview['fingerprint']}).status_code == 409
        assert snapshot(carton, current) == before


def test_multiple_matching_carton_orders_are_not_auto_allocated(monkeypatch):
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        payload = _order_payload()
        payload['customer_po'] = 'ANOTHER-PO'
        ok(client.post(CARTON + '/orders', json=payload), 201)
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert not preview['can_confirm'] and preview['blocked_reason']
        assert snapshot(carton, current) == before


def test_reduction_cannot_override_supplier_goods_in_transit(monkeypatch):
    from test_carton_supplier_portal import setup_portal, accept_all, ship_payload
    with make_client(monkeypatch) as client:
        order = setup_portal(client)
        visible = accept_all(client)
        ok(client.post('/api/carton-supplier/shipments', json=ship_payload(visible)), 201)
        carton, _, current = seed(client, existing=order, initial_qty='3600', new_qty='5')
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert not preview['can_confirm'] and preview['blocked_reason']
        assert snapshot(carton, current) == before


@pytest.mark.parametrize('kind', ['reduce', 'cancel'])
def test_reduce_and_cancel_apply_existing_procurement_guards(monkeypatch, kind):
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client, new_qty='80' if kind == 'reduce' else '100')
        if kind == 'cancel':
            from app.db import SessionLocal
            from app.models.customer_order_ledger import OrderLedgerDispatch
            from app.schemas.customer_order_ledger import ReasonIn
            from app.services import customer_order_ledger as service
            with SessionLocal() as db:
                prior = db.get(OrderLedgerDispatch, current)
                line = service.get_line(db, 'huaxing', prior.line_id)
                service.cancel(db, line, ReasonIn(expected_revision=line.revision, reason='客户通知订单取消'), '合成业务员')
                current = db.scalar(select(OrderLedgerDispatch).where(OrderLedgerDispatch.line_id == line.id,
                    OrderLedgerDispatch.version == line.version, OrderLedgerDispatch.recipient == 'pmc')).id
                db.commit()
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert preview['can_confirm'], preview['blocked_reason']
        assert snapshot(carton, current) == before
        result = ok(call(client, current, 'confirm', {'confirmed': True, 'fingerprint': preview['fingerprint']}))
        assert result['processed']
        if kind == 'reduce':
            assert Decimal(result['after']['product_order_quantity']) == 80
        else:
            assert result['after']['status'] == 'CANCELLED'
        assert snapshot(carton, current)[4]


def test_customer_responsibility_revoked_after_preview_blocks_confirm(monkeypatch):
    from test_carton_customer_packaging import assign
    from test_molding_sample_api import ensure_test_user
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        from app.db import SessionLocal
        from app.models.auth import AuthPermission, AuthUser, AuthUserPermissionOverride
        with SessionLocal() as db:
            user = db.scalar(select(AuthUser).where(AuthUser.username == 'warehouse_keeper'))
            for code in ('customer_order:inbox_read', 'customer_order:inbox_receive',
                         'carton_procurement:read', 'carton_procurement:order_write'):
                permission = db.scalar(select(AuthPermission).where(AuthPermission.code == code))
                assert permission is not None, code
                db.add(AuthUserPermissionOverride(id='test-business-' + code, user_id=user.id,
                    permission_id=permission.id, effect='allow', factory_id='huaxing', department='pmc-warehouse',
                    status='active', reason='合成测试授权'))
            db.commit()
        from app.services import business_authz
        monkeypatch.setattr(business_authz.settings, 'authz_mode', 'enforce')
        login_as(client, 'warehouse_keeper')
        preview = ok(call(client, current, 'preview'))
        assert preview['can_confirm'], preview['blocked_reason']
        login_as(client, 'admin')
        ensure_test_user('carton_warehouse')
        with SessionLocal() as db:
            other = db.scalar(select(AuthUser).where(AuthUser.username == 'carton_warehouse')).id
        customer = next(row for row in ok(client.get(CARTON + '/customers', params={'factory_id': 'huaxing'}))['items']
                        if row['customer_code'] == 'DICKIE')
        assign(client, customer, [other])
        login_as(client, 'warehouse_keeper')
        before = snapshot(carton, current)
        result = call(client, current, 'confirm', {'confirmed': True, 'fingerprint': preview['fingerprint']})
        assert result.status_code == 403, result.text
        assert snapshot(carton, current) == before


def test_real_historical_split_plan_blocks_automatic_change(monkeypatch):
    from test_carton_order_split import save, split_body
    with make_client(monkeypatch) as client:
        carton, _, current = seed(client)
        data = split_body(carton)
        data['targets'][0]['lines'].append({'order_line_id': carton['lines'][1]['id'],
            'pending_quantity': '40', 'stock': []})
        plan = save(client, carton, data)
        assert plan['id']
        before = snapshot(carton, current)
        preview = ok(call(client, current, 'preview'))
        assert not preview['can_confirm'] and preview['blocked_reason']
        assert snapshot(carton, current) == before
