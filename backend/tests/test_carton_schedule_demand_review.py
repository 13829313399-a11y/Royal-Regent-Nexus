"""Weekly source identity and external-order acknowledgements, synthetic data only."""
import json
import hashlib
from types import SimpleNamespace

import pytest

from test_carton_item_schedule import workbook, source_row, _prepare_schedule_customer, MatchingDb, order
from test_carton_procurement_api import _order_payload, _submit_order
from test_molding_sample_api import make_client, login_as
from app.services.carton_schedule_tracking import identity, so_identity, demand_snapshot, mark_changes, annotate_changes, mark_for_row
from app.services.carton_procurement_imports import _match_rows, _parse_weekly


def test_effective_po_is_shared_by_identity_duplicate_detection_and_linked_matching():
    first, second = source_row(), source_row()
    first[3], second[3] = '0001', '0002'
    rows = _parse_weekly('schedule.xlsx', workbook([first, second]))['rows']
    assert all(row.get('match_status') != 'REVIEW_REQUIRED' for row in rows)
    assert identity(rows[0]) != identity(rows[1])
    assert so_identity(rows[0]) == so_identity(rows[1])  # The historical collision.
    poisoned = {identity(rows[1]): ['o1']}
    _match_rows(MatchingDb([order(id='o1', customer_po='0001')]), 'huaxing', 'WEEKLY_SCHEDULE', [rows[1]], poisoned)
    assert rows[1]['match_status'] == 'MISSING_ORDER' and not rows[1].get('order_id')
    assert identity({**rows[0], 'source_reference': 'SO1'}) == identity({**rows[1], 'source_reference': 'SO1'})
    blank = [{**rows[0], 'customer_po': ''}, {**rows[0], 'customer_po': ''}]
    annotate_changes(blank, {}, set())
    assert all(row['schedule_identity_duplicate'] and row['schedule_change'] == 'REVIEW_REQUIRED' for row in blank)


@pytest.mark.parametrize('field,value,label', [('quantity', 720, '数量'), ('carton_rule', '12', '装箱'),
    ('inspection_window', '2026-09-01', '验货日期'), ('customer_due_date', '2026-09-01', '客户交期')])
def test_acknowledged_demand_detects_every_material_change(field, value, label):
    baseline = {'quantity': 360, 'carton_rule': '6', 'inspection_window': '2026-09-10', 'customer_due_date': '2026-09-17'}
    mark = {'marked': True, 'demand_snapshot': demand_snapshot(baseline)}
    assert mark_changes({**baseline, field: value}, mark) == [label]
    assert not mark_changes({**baseline, 'quantity': 360.0, 'carton_rule': ' 6.0 '}, mark)
    assert mark_changes(baseline, {'marked': True}) == ['原下单依据待核实']


def test_old_fallback_po_evidence_is_projected_only_when_its_source_is_provable():
    from app.services.carton_procurement import _schedule_event_key
    base = dict(schedule_customer_code='DICKIE', contract_no='C1', item_no='I1', source_reference='',
                source_sheet='ITEM', source_row=4, order_type='正单', schedule_section='PENDING')
    first, second = {**base, 'customer_po': 'PO-A'}, {**base, 'customer_po': 'PO-B', 'source_row': 5}
    db = SimpleNamespace(get=lambda model, identifier: SimpleNamespace(factory_id='huaxing', parse_summary_json=json.dumps({'rows': [first, second]})))
    old_key = so_identity(first)
    old_operation = hashlib.sha256(json.dumps([old_key, 'B', 'ITEM', 4], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    detail = {'batch_id': 'B', 'source_sheet': 'ITEM', 'source_row': 4}
    assert _schedule_event_key(db, 'huaxing', old_operation, detail, {}) == identity(first)
    assert _schedule_event_key(db, 'huaxing', old_key, detail, {}) == old_key
    assert mark_for_row(first, {old_key: {'marked': True}})['review_required'] is True
    assert not mark_changes(first, mark_for_row(first, {old_key: {'marked': False}}))


def test_legacy_matching_normalizes_source_and_order_po_consistently():
    for source_po, order_po in [('ＰＯ－００１', 'PO-001'), ('PO-001', 'ＰＯ－００１')]:
        row = dict(template='weekly', contract_no='53135', item_no='0040220-1', customer_po=source_po,
                   quantity=60, unit='只', packaging_type='外箱', specification='10*20*30', paper_quality='A=A')
        _match_rows(MatchingDb([order(customer_po=order_po)]), 'huaxing', 'WEEKLY_SCHEDULE', [row])
        assert row.get('order_id') == 'o1' and row['match_status'] != 'MISSING_ORDER'


def test_deleted_exact_order_does_not_make_a_live_split_source_ambiguous():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.models.carton_procurement import CartonOrder
    from app.services.carton_order_split import annotate_schedule
    engine = create_engine('sqlite://')
    CartonOrder.__table__.create(engine)
    fields = dict(factory_id='huaxing', customer_code='DICKIE', customer_name='DICKIE', supplier_id='S1',
                  supplier_name_snapshot='供应商', item_no='I1', product_order_quantity=360, order_date='2026-10-20',
                  due_date='2026-10-30', status='PENDING_SUPPLIER', created_by='U1', updated_by='U1',
                  created_at='2026-10-20T00:00:00', updated_at='2026-10-20T00:00:00')
    plan = dict(id='SPLIT1', order_id='PARENT', customer_code='DICKIE', customer_name='DICKIE', item_no='I1',
                status='ACTIVE', targets=[dict(contract_no='TARGET', customer_po='PO-T', product_quantity='360', lines=[])])
    row = dict(template='unified-item', schedule_customer_code='DICKIE', contract_no='TARGET', item_no='I1',
               customer_po='PO-T', quantity=360)
    try:
        with Session(engine) as db:
            db.add_all([CartonOrder(**fields, id='PARENT', order_no='CO-PARENT', contract_no='ORIGINAL', customer_po='PO-P'),
                        CartonOrder(**fields, id='OLD', order_no='CO-OLD', contract_no='TARGET', customer_po='PO-T',
                                    deleted_at='2026-10-20T00:00:00')])
            db.commit()
            matched = dict(row)
            assert annotate_schedule(db, 'huaxing', matched, [plan])
            assert matched['match_status'] == 'MATCHED' and matched['order_id'] == 'PARENT'
            db.get(CartonOrder, 'OLD').deleted_at = None
            db.commit()
            conflicted = dict(row)
            assert annotate_schedule(db, 'huaxing', conflicted, [plan])
            assert conflicted['match_status'] == 'AMBIGUOUS'
    finally:
        engine.dispose()


def upload(client, name, rows, content=None):
    result = client.post('/api/carton-procurement/weekly-imports', params={'factory_id': 'huaxing'},
        data={'customer_code': 'DICKIE'}, files={'file': (name, content if content is not None else workbook(rows))})
    assert result.status_code == 201, result.text
    return result.json()


def source(batch):
    return {'batch_id': batch['id'], 'source_sheet': '子弹枪ITEM表', 'source_row': 4}


def mark_payload(batch, **extra):
    return {'factory_id': 'huaxing', **source(batch), 'marked': True, **extra}


def dashboard(client):
    response = client.get('/api/carton-procurement/dashboard/workspace', params={'factory_id': 'huaxing'})
    assert response.status_code == 200, response.text
    return response.json()


def test_manual_acknowledgement_requires_reviewed_reason_and_never_mutates_orders_or_stock(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client); login_as(client, 'admin')
        values = source_row(contract='REVIEW-001')
        baseline = upload(client, 'baseline.xlsx', [values])
        saved = client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(baseline))
        assert saved.status_code == 200, saved.text
        assert saved.json()['demand_snapshot']['quantity'] == '360'
        # Legacy marks reconstruct only their exact immutable source, never today's row.
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonAuditEvent
        from sqlalchemy import select
        with SessionLocal() as db:
            event = db.scalar(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'SCHEDULE_ORDER_MARK_CHANGED'))
            detail = json.loads(event.detail_json); detail.pop('demand_snapshot'); event.detail_json = json.dumps(detail)
            db.commit()
        changed = list(values); changed[7] = 720; changed[8] = 12; changed[10] = '2026-09-01'
        changed_content = workbook([changed])
        current = upload(client, 'changed.xlsx', [changed], changed_content)
        assert current['parse_summary']['rows'][0]['schedule_change'] == 'MODIFIED'
        alert = dashboard(client)
        assert alert['items'][0]['reminder']['state'] == 'CHANGE_REVIEW'
        assert alert['items'][0]['differenceQuantity'] == 360
        assert alert['weekly_attention_count'] == 1
        duplicate = upload(client, 'changed.xlsx', [changed], changed_content)
        assert duplicate['id'] == current['id'] and duplicate['duplicate']
        assert dashboard(client)['total'] == 1
        assert client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(current)).status_code == 422
        assert client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(baseline, reason='供应商已确认')).status_code == 409
        bulk = {'factory_id': 'huaxing', 'batch_id': current['id'], 'marked': True,
                'rows': [{'source_sheet': '子弹枪ITEM表', 'source_row': 4}], 'reason': '供应商确认追加并提前交付'}
        confirmed = client.post('/api/carton-procurement/schedule-order-marks/bulk', json=bulk)
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()['changed_count'] == 1
        assert client.post('/api/carton-procurement/schedule-order-marks/bulk', json=bulk).json()['changed_count'] == 0
        assert dashboard(client)['total'] == 0
        assert client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['total'] == 0
        assert client.get('/api/carton-procurement/inventory/balances', params={'factory_id': 'huaxing'}).json() == []
        with SessionLocal() as db:
            events = db.scalars(select(CartonAuditEvent).where(CartonAuditEvent.event_type == 'SCHEDULE_ORDER_MARK_CHANGED').order_by(CartonAuditEvent.sequence)).all()
            assert len(events) == 2
            detail = json.loads(events[-1].detail_json)
            assert detail['reason'] == bulk['reason'] and detail['demand_snapshot']['quantity'] == '720'


def test_po_fallback_keeps_purchases_separate_and_stale_demand_cannot_create_or_mark(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client); login_as(client, 'admin')
        values = source_row(contract='PO-ISOLATED'); values[3] = 'PO-A'
        first = upload(client, 'po-a.xlsx', [values])
        payload = {**_order_payload(), 'contract_no': values[1], 'item_no': values[5],
                   'customer_po': 'PO-A', 'product_order_quantity': 360, 'customer_due_date': '2026-09-17', 'schedule_source': source(first)}
        created = client.post('/api/carton-procurement/orders', json=payload)
        assert created.status_code == 201, created.text
        original = _submit_order(client, created.json())
        values[3] = 'PO-B'; second = upload(client, 'po-b.xlsx', [values])
        row = second['parse_summary']['rows'][0]
        assert row['schedule_identity'] != first['parse_summary']['rows'][0]['schedule_identity']
        assert not row.get('order_id') and row['match_status'] == 'MISSING_ORDER' and row['schedule_change'] == 'NEW'
        assert client.post('/api/carton-procurement/orders', json={**payload, 'schedule_source': source(second)}).status_code == 422
        second_order = client.post('/api/carton-procurement/orders', json={**payload, 'customer_po': 'PO-B', 'schedule_source': source(second)})
        assert second_order.status_code == 201, second_order.text
        assert second_order.json()['id'] != original['id']
        unchanged = next(item for item in client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['items'] if item['id'] == original['id'])
        assert unchanged['revision'] == original['revision'] and unchanged['product_order_quantity'] == original['product_order_quantity']
        values[1] = 'STALE-001'; old = upload(client, 'old.xlsx', [values])
        values[7] = 720; latest = upload(client, 'new.xlsx', [values])
        stale = {**payload, 'contract_no': 'STALE-001', 'customer_po': 'PO-B', 'schedule_source': source(old)}
        assert client.post('/api/carton-procurement/orders', json=stale).status_code == 409
        assert client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(old)).status_code == 409
        accepted = client.post('/api/carton-procurement/orders', json={**stale, 'product_order_quantity': 720, 'schedule_source': source(latest)})
        assert accepted.status_code == 201, accepted.text


def test_deleted_active_order_no_longer_claims_source_or_blocks_recreation(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client); login_as(client, 'admin')
        values = source_row(contract='DELETED-SOURCE'); values[3] = 'PO-RECOVER'
        first = upload(client, 'before-deletion.xlsx', [values])
        payload = {**_order_payload(), 'contract_no': values[1], 'item_no': values[5],
                   'customer_po': 'PO-RECOVER', 'product_order_quantity': 360, 'schedule_source': source(first)}
        created = client.post('/api/carton-procurement/orders', json=payload)
        assert created.status_code == 201, created.text
        original = _submit_order(client, created.json())
        linked = upload(client, 'with-live-order.xlsx', [values])
        assert linked['parse_summary']['rows'][0]['order_id'] == original['id']
        from app.db import SessionLocal
        from app.models.carton_procurement import CartonOrder
        from app.services.carton_procurement import _schedule_order_links
        with SessionLocal() as db:
            historical = db.get(CartonOrder, original['id'])
            # Legacy rows may be logically deleted while retaining their former active status.
            historical.deleted_at = '2026-10-20T00:00:00+08:00'
            db.commit()
            assert not _schedule_order_links(db, 'huaxing')
        refreshed_values = list(values); refreshed_values[6] = '刷新后核对产品名称'
        refreshed = upload(client, 'after-deletion.xlsx', [refreshed_values])
        assert not refreshed['parse_summary']['rows'][0].get('order_id')
        assert refreshed['parse_summary']['rows'][0]['match_status'] == 'MISSING_ORDER'
        replay = client.post('/api/carton-procurement/orders', json={**payload, 'schedule_source': source(linked)})
        assert replay.status_code == 201, replay.text
        assert replay.json()['id'] != original['id']
