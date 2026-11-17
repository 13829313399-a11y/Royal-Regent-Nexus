"""Upcoming defaults and fresh historical queries use isolated business records."""
from copy import deepcopy
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from test_customer_order_ledger import engine, db, ingest, preview
from test_qc_workflow import qc_user
from app.api import qc_department as gateway
from app.db import get_db
from app.services.auth import get_current_user
from app.services import qc_workflow as wf, qc_schedule_view as view


real_business_date = view.business_date


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.setattr(wf.settings, 'qc_department_data_dir', str(tmp_path / 'companies'))
    monkeypatch.setattr(view, 'business_date', lambda: '2026-11-17')


def order(db, reference, start='', end='', factory='huaxing'):
    line = ingest(db, preview(reference=reference, factory=factory))
    line.data = {**line.data, 'planned_inspection_date': start,
                 'planned_inspection_date_to': end, 'inspection_agency': '行验'}
    db.commit()
    return line


def ids(payload):
    return {row['id'] for row in payload['items']}


def test_default_scope_includes_today_future_and_ongoing_ranges_without_deleting_history(db, monkeypatch):
    past = order(db, 'past', '2026-11-16')
    today = order(db, 'today', '2026-11-17')
    future = order(db, 'future', '2026-11-20')
    ongoing = order(db, 'ongoing', '2026-11-16', '2026-11-19')
    order(db, 'missing')
    order(db, 'invalid', '2026-02-30')
    order(db, 'reversed', '2026-11-20', '2026-11-18')
    other = order(db, 'other-factory', '2026-11-17', factory='huadeng')
    before = deepcopy(wf.sources(db, 'huaxing'))
    result = view.listing(db, 'huaxing')
    assert ids(result) == {today.id, future.id, ongoing.id}
    assert result['dateScope'] == {'mode': 'upcoming', 'from': '2026-11-17', 'to': '',
                                   'businessDate': '2026-11-17', 'timezone': 'Asia/Shanghai'}
    assert ids(view.listing(db, 'huadeng')) == {other.id}
    assert ids(view.listing(db, 'huaxing', date_from='2026-11-16', date_to='2026-11-16')) == {past.id, ongoing.id}
    assert wf.sources(db, 'huaxing') == before
    monkeypatch.setattr(view, 'business_date', lambda: '2026-11-18')
    assert ids(view.listing(db, 'huaxing')) == {future.id, ongoing.id}


def test_history_is_fetched_fresh_and_can_be_pushed_idempotently(db):
    assert view.listing(db, 'huaxing')['items'] == []
    past = order(db, 'late-business-entry', '2026-10-28')
    original = deepcopy(past.data)
    assert ids(view.listing(db, 'huaxing', date_to='2026-10-28')) == {past.id}
    assert view.listing(db, 'huaxing')['items'] == []
    body = {'requestKey': 'historical-makeup', 'items': [{'sourceId': past.id,
            'sourceRevision': past.revision, 'method': 'internal', 'batch': '首验',
            'plannedDate': '2026-10-28', 'plannedQuantity': '100'}]}
    actor = {'id': 'qc-test', 'name': '测试员'}
    task = wf.create_tasks(db, 'huaxing', body, actor)['items'][0]
    assert wf.create_tasks(db, 'huaxing', body, actor)['items'][0]['id'] == task['id']
    historical = view.listing(db, 'huaxing', date_from='2026-10-28', date_to='2026-10-28')
    assert historical['items'][0]['tasks'][0]['id'] == task['id']
    assert past.data == original
    past.data = {**past.data, 'planned_inspection_date': '2026-11-19'}
    db.commit()
    assert ids(view.listing(db, 'huaxing')) == {past.id}
    assert view.listing(db, 'huaxing', date_to='2026-10-28')['items'] == []


@pytest.mark.parametrize('start,end', [('2026-02-30', ''), ('', '2026/11/17'), ('2026-11-18', '2026-11-17')])
def test_invalid_ranges_are_rejected(db, start, end):
    with pytest.raises(HTTPException) as exc:
        view.listing(db, 'huaxing', date_from=start, date_to=end)
    assert exc.value.status_code == 422


def test_http_default_history_validation_and_factory_boundary(db, monkeypatch):
    async def healthy(*args):
        return httpx.Response(200, json={'ok': True})
    monkeypatch.setattr(gateway, 'upstream', healthy)
    past = order(db, 'history-http', '2026-10-28')
    order(db, 'other-http', '2026-10-28', factory='huadeng')
    app = FastAPI()
    app.include_router(gateway.router)
    app.dependency_overrides[get_current_user] = lambda: qc_user()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        base = client.get('/api/qc-department/huaxing/api/health').json()['frame_url']
        endpoint = base + 'api/schedule-source'
        assert client.get(endpoint).json()['items'] == []
        response = client.get(endpoint, params={'dateFrom': '2026-10-28', 'dateTo': '2026-10-28'})
        assert response.status_code == 200 and ids(response.json()) == {past.id}
        assert response.headers['cache-control'] == 'no-store'
        for query in ['dateFrom=2026-02-30', 'dateFrom=2026-11-18&dateTo=2026-11-17',
                      'dateFrom=2026-10-28&dateFrom=2026-11-17', 'factory=huadeng']:
            assert client.get(endpoint + '?' + query).status_code == 422


def test_business_day_rolls_over_at_shanghai_midnight(monkeypatch):
    class Clock:
        @staticmethod
        def now(zone):
            return datetime(2026, 11, 16, 16, 1, tzinfo=timezone.utc).astimezone(zone)
    monkeypatch.setattr(view, 'datetime', Clock)
    assert real_business_date() == '2026-11-17'
