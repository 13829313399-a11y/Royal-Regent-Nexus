from copy import deepcopy
from datetime import date
import json
from types import SimpleNamespace
from urllib.parse import unquote

import pytest
from sqlalchemy import select, func

from test_customer_order_ledger import engine, db, client, preview, ingest, user, ship_body
from app.services import customer_order_ledger as ledger, customer_order_schedule as schedule_service
from app.services.auth import get_current_user
from app.services.customer_order_360_dates import parse_inspection_date
from app.schemas.customer_order_ledger import ReasonIn, AmendIn
from app.models.customer_order_ledger import OrderLedgerLine, OrderLedgerVersion


@pytest.fixture(autouse=True)
def setup_360(client, monkeypatch):
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'write', 'shipment_confirm'], factory='huakang-a')
    monkeypatch.setattr(schedule_service, 'shanghai_today', lambda: date(2026, 10, 16))


def order(db, ref, inspection='', product='76543290069', **fields):
    payload = preview(factory='huakang-a', qty='100', reference=ref)
    payload.update(customer_code='360', customer_name='360')
    payload['rows'][0].update(product_no=product, line_q=inspection, **fields)
    return ingest(db, payload)


def read(client, **params):
    return client.get('/api/customer-order-ledger/schedule', params={
        'factory_id': 'huakang-a', 'customer_code': '360', **params})


def refs(result, section):
    return [row['reference_no'] for row in result['sections'][section]['items']]


def test_existing_inspection_dates_move_without_mutating_order_or_shipment(db, client):
    old = order(db, 'RL-10', '2026-10-15')
    today = order(db, 'RL-2', '2026-10-16')
    order(db, 'RL-3', '2026-12-08')
    order(db, 'UNSET', '', requested_ship_date='2020-01-01')
    history = order(db, 'HISTORY', '', inspection_date='2026/2/5')
    cancelled = order(db, 'CANCELLED', '2026-10-01')
    ledger.ship(db, old, ship_body(old, qty='30'), '业务员')
    ledger.cancel(db, cancelled, ReasonIn(expected_revision=cancelled.revision, reason='取消余数测试'), '业务员')
    db.commit()
    before = {line.id: (deepcopy(line.data), line.quantity, line.shipped_quantity, line.status, line.version, line.revision)
              for line in db.scalars(select(OrderLedgerLine))}
    versions = db.scalar(select(func.count()).select_from(OrderLedgerVersion))
    result = read(client).json()
    assert result['inspection_grouping'] == {'as_of_date': '2026-10-16', 'timezone': 'Asia/Shanghai'}
    assert refs(result, 'completed') == ['HISTORY', 'RL-10']
    assert refs(result, 'inspection_pending') == ['RL-2', 'RL-3', 'UNSET']
    assert refs(result, 'shipped') == ['RL-10']
    assert refs(result, 'cancelled') == ['CANCELLED']
    assert result['summary']['ordered_quantity'] == '600'
    assert result['summary']['remaining_quantity'] == '470'
    assert result['sections']['completed']['items'][1]['remaining_quantity'] == '70'
    assert result['sections']['completed']['items'][0]['schedule_inspection_date'] == '2026-02-05'
    assert db.scalar(select(func.count()).select_from(OrderLedgerVersion)) == versions
    db.expire_all()
    assert before == {line.id: (line.data, line.quantity, line.shipped_quantity, line.status, line.version, line.revision)
                      for line in db.scalars(select(OrderLedgerLine))}


def test_invalid_or_conflicting_dates_never_complete_and_pagination_after_classification(db, client):
    order(db, 'BAD', '2026-02-30')
    order(db, 'TBD', '待定')
    order(db, 'CONFLICT', '2026-01-01', inspection_date='2026-12-01')
    order(db, 'RL-10', '2026-10-01')
    order(db, 'RL-2', '2026-10-01')
    order(db, 'SUFFIX', '2026-10-01', product='76543290069.06')
    result = read(client, page_size=1, completed_page=2, inspection_pending_page=99).json()
    assert result['sections']['completed']['total'] == 3
    assert refs(result, 'completed') == ['RL-10']
    assert result['sections']['inspection_pending']['page'] == 3
    assert result['sections']['inspection_pending']['items'][0]['inspection_date_warning']
    assert read(client, completed_page=0).status_code == 422
    assert refs(read(client, q='CONFLICT').json(), 'inspection_pending') == ['CONFLICT']


def test_refresh_across_day_and_changed_order_return_to_pending(db, client, monkeypatch):
    line = order(db, 'TODAY', '2026-10-16')
    assert refs(read(client).json(), 'inspection_pending') == ['TODAY']
    monkeypatch.setattr(schedule_service, 'shanghai_today', lambda: date(2026, 10, 17))
    assert refs(read(client).json(), 'completed') == ['TODAY']
    ledger.amend(db, line, AmendIn(expected_revision=line.revision, quantity='100', requested_ship_date='2026-12-30',
        note='', reason='客户调整交期'), '业务员')
    db.commit()
    result = read(client).json()
    assert refs(result, 'inspection_pending') == ['TODAY']
    assert result['sections']['completed']['total'] == 0
    assert result['sections']['inspection_pending']['items'][0]['id'] == line.id


def test_full_product_suffix_groups_are_not_interleaved_by_natural_sort(db, client):
    order(db, 'FIRST', '2026-10-01', product='102.01')
    order(db, 'MIDDLE', '2026-10-02', product='102.1')
    order(db, 'LAST', '2026-10-03', product='102.01')
    assert refs(read(client).json(), 'completed') == ['FIRST', 'LAST', 'MIDDLE']


def test_other_customer_and_factory_keep_shipment_sections(db, client):
    data = preview(factory='huakang-a')
    data.update(customer_code='headstart', customer_name='HeadStart')
    data['rows'][0]['line_q'] = '2020-01-01'
    ingest(db, data)
    result = read(client, customer_code='headstart').json()
    assert 'inspection_grouping' not in result
    assert set(result['sections']) == {'unshipped', 'shipped', 'cancelled'}
    assert read(client, factory_id='huaxing').status_code == 403


def test_existing_workbook_organize_requires_export_permission_and_correct_factory(client):
    url = '/api/customer-order-ledger/schedule/organize-360'
    files = {'schedule_file': ('schedule.xlsx', b'not-a-workbook')}
    # A read/write ledger grant does not grant Excel export.
    assert client.post(url, params={'factory_id': 'huakang-a'}, files=files).status_code == 403
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'export'], factory='huaxing')
    assert client.post(url, params={'factory_id': 'huakang-a'}, files=files).status_code == 403
    assert client.post(url, params={'factory_id': 'huaxing'}, files=files).status_code == 400
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'export'], factory='huakang-a')
    assert client.post(url, params={'factory_id': 'huakang-a'}, files={'schedule_file': ('wrong.pdf', b'PDF')}).status_code == 400
    assert client.post(url, params={'factory_id': 'huakang-a'}, files={'schedule_file': ('empty.xlsx', b'')}).status_code == 400


def test_organize_download_exposes_bounded_warnings_and_audits_full_report(client, monkeypatch):
    from app.api import customer_order_ledger as api
    report = {'as_of_date': '2026-10-16', 'sheets': {'ITEM表': {'moved_to_completed': 5, 'moved_to_pending': 1}},
              'warnings': [f'ITEM表第{i}行：' + '日期不明确需核对' * 50 for i in range(10)]}
    recorded = {}

    async def job(*args, **kwargs):
        return b'workbook', '整理.xlsx', report, 'source-sha'

    def record(*args, **kwargs):
        recorded.update(kwargs)
        return SimpleNamespace(id='audit-1')

    monkeypatch.setattr(api, 'run_order_job', job)
    monkeypatch.setattr(api.mapping, '_record_export_audit', record)
    client.test_app.dependency_overrides[get_current_user] = lambda: user(['read', 'export'], factory='huakang-a')
    response = client.post('/api/customer-order-ledger/schedule/organize-360', params={'factory_id': 'huakang-a'},
                           files={'schedule_file': ('schedule.xlsx', b'original')})
    assert response.status_code == 200 and response.content == b'workbook'
    header = response.headers['x-schedule-organize-report']
    assert len(header) < 5000
    actual = json.loads(unquote(header))
    assert actual['warning_count'] == 10 and len(actual['warnings']) == 3
    assert actual['sheets'] == report['sheets']
    assert all(len(w) <= 100 for w in actual['warnings'])
    assert json.loads(recorded['confirmation_reason'].split('整理报告：', 1)[1]) == report


@pytest.mark.parametrize('value', ['2026-02-30', '4/6自检', '无需验货', 'TBD', '', 46310, '2026-10-15 / 2026-11-15'])
def test_ambiguous_dates_are_not_parsed(value):
    assert parse_inspection_date(value) is None
