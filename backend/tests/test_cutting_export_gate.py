from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
import pytest
from fastapi import HTTPException

from app.services.cutting_export_gate import ExportGate
from app.services import cutting_export_gate
from test_cutting_exports import (paid_setup, fees, price, fee_save, fee_decision, fee_accountant,
    client, user, command, BASE, flow, planned, production, ok, save, decision, reviewer,
    read, api, exports, request, fresh_auth)


def test_gate_bounds_waiting_and_releases_after_failure():
    gate = ExportGate(capacity=2, timeout=.02)
    entered = Event()
    release = Event()
    def active():
        with gate.slot():
            entered.set()
            assert release.wait(2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(active)
        assert entered.wait(1)
        try:
            with pytest.raises(HTTPException) as caught:
                with gate.slot():
                    pytest.fail('Second renderer admitted while first is active')
            assert caught.value.status_code == 429
        finally:
            release.set()
        running.result()
    with pytest.raises(ValueError):
        with gate.slot():
            raise ValueError('renderer failed')
    with gate.slot():
        with pytest.raises(HTTPException):
            with gate.slot():
                pytest.fail('Another renderer admitted')


def test_queued_downloads_keep_arrival_order_under_repeated_requests():
    gate = ExportGate(capacity=5, timeout=2)
    order = []
    def download(index):
        with gate.slot():
            order.append(index)
        # A repeat request must go behind users already waiting.
        with gate.slot():
            order.append(index + 10)
    with ThreadPoolExecutor(max_workers=3) as pool:
        with gate.slot():
            jobs = []
            for index in range(3):
                jobs.append(pool.submit(download, index))
                deadline = monotonic() + 1
                while True:
                    with gate.condition:
                        if len(gate.waiters) == index + 1:
                            break
                    assert monotonic() < deadline, 'Downloader did not join queue'
                    sleep(.001)
        for job in jobs:
            job.result()
    assert order[:3] == [0, 1, 2]
    assert sorted(order[3:]) == [10, 11, 12]


def test_gate_rejects_full_queue_without_leaking_capacity():
    gate = ExportGate(capacity=1, timeout=.01)
    with gate.slot():
        with pytest.raises(HTTPException) as caught:
            with gate.slot():
                pytest.fail('Queue is full')
        assert caught.value.status_code == 429
        assert caught.value.headers['Retry-After'] == '3'
    with gate.slot():
        pass


def test_waiter_cannot_enter_after_deadline_even_when_renderer_becomes_free(monkeypatch):
    gate = ExportGate(capacity=2, timeout=2)
    expired = Event()
    monkeypatch.setattr(cutting_export_gate, 'monotonic', lambda: monotonic() + (10 if expired.is_set() else 0))
    def waiting_download():
        with pytest.raises(HTTPException) as caught:
            with gate.slot():
                pytest.fail('Expired waiter entered renderer')
        assert caught.value.status_code == 429
    with ThreadPoolExecutor(max_workers=1) as pool:
        with gate.slot():
            job = pool.submit(waiting_download)
            deadline = monotonic() + 1
            while True:
                with gate.condition:
                    if gate.waiters:
                        break
                assert monotonic() < deadline
                sleep(.001)
            expired.set()
        job.result()
    with gate.slot():
        pass


@pytest.mark.parametrize('change', ['permission', 'balance'])
def test_admission_rechecks_after_queue_and_holds_no_transaction(paid_setup, monkeypatch, change):
    p = paid_setup
    body = request()
    preview = ok(p.post(BASE+'/exports/preview', json=body))
    original_rollback = api.Session.rollback
    rolled_back = Event()
    def rollback(db):
        result = original_rollback(db)
        rolled_back.set()
        return result
    monkeypatch.setattr(api.Session, 'rollback', rollback)
    @contextmanager
    def slot():
        assert rolled_back.is_set(), 'Waiting with an authentication transaction'
        if change == 'permission':
            p.cutting_auth['user'] = user('read', department='accounting')
        else:
            save(p)  # A real write must complete before admitting the export.
        yield
    monkeypatch.setattr(api.export_gate, 'slot', slot)
    def forbidden(*args):
        pytest.fail('Stale/unauthorized queued export reached the renderer')
    monkeypatch.setattr(exports, 'package_isolated', forbidden)
    response = p.post(BASE+'/exports/download', json=body | {'token': preview['token']})
    assert response.status_code == (403 if change == 'permission' else 409)
