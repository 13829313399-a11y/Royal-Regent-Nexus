"""Amended business demand remains orderable without rewriting issued purchases."""
from decimal import Decimal

import pytest

from test_carton_item_schedule import workbook, source_row, MatchingDb, order, _prepare_schedule_customer
from test_carton_schedule_demand_review import upload, source, mark_payload, dashboard
from test_carton_procurement_api import _order_payload, _submit_order
from test_molding_sample_api import make_client, login_as
from app.services.carton_procurement_imports import _parse_weekly, _match_rows
from app.services.carton_schedule_tracking import annotate_changes, customer_key


def test_amendments_match_regular_orders_and_retain_source_type():
    rows = _parse_weekly('amended.xlsx', workbook([source_row('改单')]))['rows']
    _match_rows(MatchingDb([order(customer_po='0989551378')]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['order_type'] == '改单'
    assert rows[0]['order_id'] == 'o1' and rows[0]['match_status'] == 'MATCHED'


def test_amended_and_regular_rows_with_the_same_identity_still_require_duplicate_review():
    rows = _parse_weekly('duplicate.xlsx', workbook([source_row(), source_row('改单')]))['rows']
    annotate_changes(rows, {}, set())
    assert all(row['match_status'] == 'REVIEW_REQUIRED' and row['schedule_identity_duplicate'] for row in rows)


def test_amended_delivery_date_is_compared_with_the_placed_order():
    values = source_row('改单'); values[10] = '2026-09-20'
    rows = _parse_weekly('amended-date.xlsx', workbook([values]))['rows']
    placed = order()
    _match_rows(MatchingDb([placed]), 'huaxing', 'WEEKLY_SCHEDULE', rows)
    assert rows[0]['match_status'] == 'DATE_MISMATCH'
    assert rows[0]['date_difference'] == {'business_date': '2026-09-20', 'order_date': '2026-09-17'}
    assert placed.customer_due_date == '2026-09-17'


@pytest.mark.parametrize('field,value', [(1, ''), (5, ''), (7, 0), (7, -1), (7, None)])
def test_amendments_still_require_identity_and_positive_quantity(field, value):
    values = source_row('改单'); values[field] = value
    row = _parse_weekly('invalid.xlsx', workbook([values]))['rows'][0]
    assert row['match_status'] == 'REVIEW_REQUIRED'


def test_partial_amendment_keeps_remaining_original_and_explicit_full_cancellation_is_reviewed():
    original = _parse_weekly('before.xlsx', workbook([source_row()]))['rows'][0]
    amended = source_row('改单', contract='NEW', qty=240)
    current = _parse_weekly('partial.xlsx', workbook([source_row(qty=120), amended]))['rows']
    previous = {customer_key(original): [original]}
    annotate_changes(current, previous, set())
    assert [(r['contract_no'], r['quantity'], r['schedule_change']) for r in current] == [
        ('53135', 120, 'MODIFIED'), ('NEW', 240, 'NEW')]
    # Omission alone cannot cancel a purchase. Cancellation needs explicit source evidence.
    only_amended = _parse_weekly('omitted.xlsx', workbook([amended]))['rows']
    annotate_changes(only_amended, previous, set())
    assert only_amended[0]['schedule_change'] == 'NEW'
    cancelled = _parse_weekly('full.xlsx', workbook([
        amended, ['取消单'], source_row(qty=0)]))['rows']
    original['order_id'] = 'o1'
    annotate_changes(cancelled, previous, set())
    assert cancelled[1]['schedule_change'] == 'CANCELLED_AFTER_ORDER'


def test_v5_projection_preserves_proven_po_links_after_parser_upgrade():
    from app.services.carton_procurement import _project_item_schedule_rows
    row = dict(template='unified-item', schedule_customer_code='DICKIE', contract_no='C1',
               item_no='I1', customer_po='0001', source_reference='', order_type='正单',
               schedule_section='PENDING', schedule_change='UNCHANGED', order_id='O1', match_status='MATCHED')
    summary = {'parser_version': 'schedule-item-effective-po-v5', 'rows': [row]}
    _project_item_schedule_rows('B1', summary)
    assert row['order_id'] == 'O1' and row['match_status'] == 'MATCHED'
    assert not row.get('legacy_match_stale')


def test_amended_source_can_create_and_mark_and_changed_placed_demand_remains_visible(monkeypatch):
    with make_client(monkeypatch) as client:
        _prepare_schedule_customer(client); login_as(client, 'admin')
        values = source_row('改单', contract='AMENDED-CREATE')
        batch = upload(client, 'amended.xlsx', [values])
        row = batch['parse_summary']['rows'][0]
        assert row['schedule_change'] == 'BASELINE' and row['match_status'] == 'MISSING_ORDER'
        payload = {**_order_payload(), 'contract_no': values[1], 'item_no': values[5],
                   'customer_po': values[3], 'product_order_quantity': 360,
                   'customer_due_date': '2026-09-17', 'schedule_source': source(batch)}
        created = client.post('/api/carton-procurement/orders', json=payload)
        assert created.status_code == 201, created.text
        placed = _submit_order(client, created.json())
        values[7] = 720
        changed = upload(client, 'amended-increase.xlsx', [values])
        assert changed['parse_summary']['rows'][0]['match_status'] == 'QUANTITY_MISMATCH'
        assert changed['parse_summary']['rows'][0]['schedule_change'] == 'MODIFIED'
        assert any(item['kind'] == 'QUANTITY_INCREASE' for item in dashboard(client)['items'])
        orders = client.get('/api/carton-procurement/orders', params={'factory_id': 'huaxing'}).json()['items']
        saved = next(item for item in orders if item['id'] == placed['id'])
        assert saved['revision'] == placed['revision'] and Decimal(saved['product_order_quantity']) == 360
        # A separate externally ordered amendment supports the same frozen-demand review.
        values[1] = 'AMENDED-MARK'
        manual = upload(client, 'manual.xlsx', [values])
        marked = client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(manual))
        assert marked.status_code == 200, marked.text
        values[8] = 12; values[10] = '2026-09-01'
        revised = upload(client, 'manual-changed.xlsx', [values])
        alerts = dashboard(client)['items']
        assert any(item['reminder'] and item['reminder']['state'] == 'CHANGE_REVIEW' for item in alerts)
        assert client.post('/api/carton-procurement/schedule-order-marks', json=mark_payload(revised)).status_code == 422
