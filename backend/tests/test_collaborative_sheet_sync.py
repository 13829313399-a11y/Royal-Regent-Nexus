from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from io import BytesIO
from zipfile import ZipFile

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from test_collaborative_sheets import api, publish, endpoint, context, Task, Event, service
from app.schemas.collaborative_sheets import SyncCellsInput
from app.services import collaborative_sheet_sync as sync


def command(task, address="A2", value="甲", base="001", op=None):
    return {"operation_id": op or str(uuid4()), "expected_revision": task["revision"],
            "changes": [{"sheet": 0, "address": address, "value": value, "base_value": base, "base_revision": task["revision"]}]}


def test_disjoint_writers_merge_without_exporting_or_manifest(api, monkeypatch):
    task = publish(api)
    monkeypatch.setattr(service.files, "export_workbook", lambda *_: pytest.fail("XLSX autosave must not export"))
    a = api[0].patch(endpoint(task, "/sync"), json=command(task))
    assert a.status_code == 200, a.text
    api[1]["user"] = context("filler")
    b = api[0].patch(endpoint(task, "/sync"), json=command(task, "B2", 99, 12))
    assert b.status_code == 200, b.text
    assert b.json()["revision"] == task["revision"] + 2
    assert "workbook" not in b.json()
    assert len(b.json()["events"]) == 2
    with Session(api[2]) as db:
        assert db.get(Task, task["id"]).overrides == {"0:A2": "甲", "0:B2": 99}


def test_same_cell_aba_is_conflict_and_batch_is_atomic(api):
    task = publish(api)
    a = api[0].patch(endpoint(task, "/sync"), json=command(task)).json()
    api[0].patch(endpoint(task, "/sync"), json=command(a, value="001", base="甲"))
    request = command(task, value="乙")
    request["changes"].append(command(task, "B2", 99, 12)["changes"][0])
    rejected = api[0].patch(endpoint(task, "/sync"), json=request)
    assert rejected.status_code == 409
    assert rejected.json()["detail"]["conflicts"][0]["address"] == "A2"
    with Session(api[2]) as db:
        assert "0:B2" not in db.get(Task, task["id"]).overrides


def test_retry_after_lost_ack_is_idempotent_and_actor_bound(api):
    task = publish(api)
    request = command(task)
    first = api[0].patch(endpoint(task, "/sync"), json=request)
    newer = first.json()
    api[0].patch(endpoint(task, "/sync"), json=command(newer, "B2", 31, 12))
    retry = api[0].patch(endpoint(task, "/sync"), json=request)
    assert retry.status_code == 200
    assert retry.json()["revision"] == task["revision"] + 2
    assert all("fingerprint" not in e["detail"] for e in retry.json()["events"])
    request["changes"][0]["value"] = "reuse attack"
    assert api[0].patch(endpoint(task, "/sync"), json=request).status_code == 409
    api[1]["user"] = context("filler")
    assert api[0].patch(endpoint(task, "/sync"), json=request).status_code == 409
    with Session(api[2]) as db:
        assert len(db.scalars(select(Event).where(Event.action == "cells_saved")).all()) == 2


@pytest.mark.parametrize("address,value,code", [("C2", "formula", 422), ("B4", "merged", 422), ("A1", "header", 403), ("A2", "=1+1", 422), ("Z99", "bounds", 422)])
def test_sync_preserves_formula_range_and_scalar_rules(api, address, value, code):
    task = publish(api)
    assert api[0].patch(endpoint(task, "/sync"), json=command(task, address, value, None)).status_code == code


def test_revocation_close_and_cross_factory_cover_read_write_history(api):
    task = publish(api)
    api[1]["user"] = context("other", factory="huakang-a")
    for path in ["/changes&since=3", "/history"]:
        url = endpoint(task, "/changes") + "&since=3" if path.startswith("/changes") else endpoint(task, path)
        assert api[0].get(url).status_code == 403
    assert api[0].patch(endpoint(task, "/sync"), json=command(task)).status_code == 403
    api[1]["user"] = context()
    closed = api[0].post(endpoint(task, "/state"), json={"expected_revision": 3, "status": "closed"})
    assert closed.status_code == 200
    assert api[0].patch(endpoint(task, "/sync"), json=command(task)).status_code == 409


def test_history_and_cached_download_preserve_original_parts(api, monkeypatch):
    task = publish(api)
    with Session(api[2]) as db:
        original = service.source_bytes(db.get(Task, task["id"]))
    api[0].patch(endpoint(task, "/sync"), json=command(task))
    history = api[0].get(endpoint(task, "/history") + "&actor=owner&sheet=0&address=A2").json()
    assert history["items"][0]["detail"]["changes"][0]["before"] == "001"
    one = api[0].get(endpoint(task, "/download"))
    monkeypatch.setattr(service.files, "export_workbook", lambda *_: pytest.fail("cache miss"))
    two = api[0].get(endpoint(task, "/download"))
    assert one.content == two.content
    with ZipFile(BytesIO(original)) as old, ZipFile(BytesIO(one.content)) as new:
        for name in old.namelist():
            if name not in {"xl/worksheets/sheet1.xml", "xl/workbook.xml"}:
                assert old.read(name) == new.read(name), name


def test_stream_rechecks_current_department_and_login_each_heartbeat(api, monkeypatch):
    from app.api import collaborative_sheets as routes
    from app.models.auth import EmployeeProfile
    from fastapi import HTTPException
    task = publish(api, principal="department", target="engineering")
    monkeypatch.setattr(routes, "SessionLocal", lambda: Session(api[2]))
    def current_identity(request, db):
        return context("filler", department=db.get(EmployeeProfile, "filler").primary_department)
    monkeypatch.setattr(routes, "get_current_user", current_identity)
    assert routes.stream_revision(None, "huaxing", task["id"]) == task["revision"]
    with Session(api[2]) as db:
        profile = db.get(EmployeeProfile, "filler")
        profile.primary_department = "qc"
        db.commit()
    with pytest.raises(HTTPException) as denied:
        routes.stream_revision(None, "huaxing", task["id"])
    assert denied.value.status_code == 404
    def expired(request, db):
        raise HTTPException(401, "expired")
    monkeypatch.setattr(routes, "get_current_user", expired)
    with pytest.raises(HTTPException) as logged_out:
        routes.stream_revision(None, "huaxing", task["id"])
    assert logged_out.value.status_code == 401


def test_stream_closes_after_access_revoked(monkeypatch):
    import asyncio
    from app.api import collaborative_sheets as routes
    from fastapi import HTTPException
    calls = 0
    def revision(*args):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise HTTPException(403, "revoked")
        return 3
    class Request:
        async def is_disconnected(self):
            return False
    async def no_wait(*args):
        pass
    monkeypatch.setattr(routes, "stream_revision", revision)
    monkeypatch.setattr(routes.asyncio, "sleep", no_wait)
    async def collect():
        response = await routes.stream("task", Request(), "huaxing")
        return [part async for part in response.body_iterator]
    assert asyncio.run(collect()) == ["event: revision\ndata: 3\n\n", "event: access_revoked\ndata: {}\n\n"]


def test_two_actual_sqlite_connections_do_not_lose_updates(api, tmp_path):
    task = publish(api)
    import sqlite3
    path = tmp_path / "concurrency.db"
    with api[2].connect() as connection, sqlite3.connect(path) as target:
        connection.connection.driver_connection.backup(target)
    engine = create_engine(f"sqlite:///{path}", connect_args={"timeout": 10})
    barrier = Barrier(2)
    def writer(payload):
        with Session(engine) as db:
            barrier.wait(timeout=5)
            return sync.save(db, context(), "huaxing", task["id"], SyncCellsInput(**payload))
    with ThreadPoolExecutor(2) as pool:
        futures = [pool.submit(writer, command(task)), pool.submit(writer, command(task, "B2", 82, 12))]
        assert sorted(f.result()["revision"] for f in futures) == [4, 5]
    with Session(engine) as db:
        assert db.get(Task, task["id"]).overrides == {"0:A2": "甲", "0:B2": 82}
    engine.dispose()
