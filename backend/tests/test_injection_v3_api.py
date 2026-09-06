from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.api import injection_scheduling as api
from app.db import Base, get_db
from app.models.injection_scheduling import (
    Operation,
    Run,
)
from app.services.auth import get_current_user
from app.services.injection_scheduling.calculations import now
from app.services.injection_scheduling.common import seed_settings
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, event, select
from sqlalchemy.orm import Session

BASE = "/api/injection-scheduling"


@pytest.fixture
def env(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'injection-test.db'}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    meta = MetaData()
    for table in Base.metadata.sorted_tables:
        if table.name.startswith("injection_v3_"):
            table.to_metadata(meta)
    meta.create_all(engine)
    with Session(engine) as db:
        seed_settings(db)
        db.commit()

    def get_session():
        with Session(engine, expire_on_commit=False) as db:
            yield db

    user = SimpleNamespace(
        id="test-operator",
        factories={"huaxing", "huadeng", "huakang-a", "huakang-b"},
        permissions={"read", "plan", "report", "master_write"},
    )

    def authorize(db, actor, factory, action="read"):
        if factory not in actor.factories or action not in actor.permissions:
            raise HTTPException(403, "测试账户无权限")

    monkeypatch.setattr(api, "authorize", authorize)
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[get_db] = get_session
    app.dependency_overrides[get_current_user] = lambda: user
    with TestClient(app) as client:
        yield client, engine, user
    engine.dispose()


def write(env, path, data=None, factory="huaxing", method="post", **kwargs):
    client = env[0]
    revision = client.get(BASE + "/summary", params={"factory_id": factory}).json()[
        "revision"
    ]
    payload = {
        "factory_id": factory,
        "base_revision": revision,
        "client_operation_id": uuid4().hex,
        **kwargs,
    }
    if data is not None:
        payload["data"] = data
    response = getattr(client, method)(BASE + path, json=payload)
    return response, payload


def ok(result):
    response = result[0] if isinstance(result, tuple) else result
    assert response.status_code == 200, response.text
    return response.json()


def seed_job(
    env, *, factory="huaxing", a=12, code="M-01", color="白色", planned=1000, asset=True
):
    mold = ok(
        write(
            env,
            "/molds",
            {
                "mold_code": code,
                "required_machine_a": a,
                "defaults": {"target_shots_per_day": 2400},
            },
            factory,
        )
    )["record"]
    if asset:
        ok(
            write(
                env,
                "/mold-assets",
                {
                    "master_id": mold["id"],
                    "asset_code": code + "-asset",
                    "current_factory_id": factory,
                },
                factory,
            )
        )
    machine = ok(
        write(
            env,
            "/machines",
            {"code": "01", "machine_a": a, "machine_family": "HORIZONTAL"},
            factory,
        )
    )["record"]
    demand = ok(
        write(
            env,
            "/demands",
            {
                "mold_code": code,
                "order_no": "001",
                "planned_shots": planned,
                "color_name": color,
                "material_raw": "PP",
                "delivery_due_at": (now() + timedelta(days=7)).isoformat(),
            },
            factory,
        )
    )["demand"]
    return mold, machine, demand


def test_create_enrich_auto_reload_and_no_false_running(env):
    _, machine, demand = seed_job(env)
    assert demand["target_shots_per_day"] == 2400
    result = ok(write(env, "/schedule/auto", scope={"mode": "UNSCHEDULED"}))
    assert result["scheduled_count"] == 1
    run = result["changed_runs"][0]
    assert run["machine_id"] == machine["id"]
    stored = (
        env[0]
        .get(BASE + "/timeline", params={"factory_id": "huaxing"})
        .json()["runs"][0]
    )
    assert stored["status"] == "PLANNED" and stored["actual_start_at"] is None
    assert (
        env[0]
        .get(BASE + "/summary", params={"factory_id": "huaxing"})
        .json()["running_count"]
        == 0
    )


def test_report_correction_idempotency_and_concurrency(env):
    seed_job(env)
    run = ok(write(env, "/schedule/auto", scope={"mode": "UNSCHEDULED"}))[
        "changed_runs"
    ][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    day = now()
    shift = "DAY" if 8 <= day.hour < 20 else "NIGHT"
    production_date = (day - timedelta(days=1)).date() if day.hour < 8 else day.date()
    common = {
        "run_id": run["id"],
        "production_date": production_date.isoformat(),
        "shift_code": shift,
    }
    response, payload = write(
        env,
        "/shift-reports/current",
        method="put",
        physical_shots=200,
        report_revision=0,
        **common,
    )
    first = ok(response)
    repeated = env[0].put(BASE + "/shift-reports/current", json=payload)
    assert ok(repeated) == first
    second = ok(
        write(
            env,
            "/shift-reports/current",
            method="put",
            physical_shots=250,
            report_revision=first["report"]["revision"],
            **common,
        )
    )
    assert second["physical_delta"] == 50
    third = ok(
        write(
            env,
            "/shift-reports/current",
            method="put",
            physical_shots=230,
            report_revision=second["report"]["revision"],
            **common,
        )
    )
    assert third["physical_delta"] == -20
    summary = env[0].get(BASE + "/summary", params={"factory_id": "huaxing"}).json()
    assert summary["completed_shots"] == 230 and summary["remaining_shots"] == 770
    stale = write(
        env,
        "/shift-reports/current",
        method="put",
        physical_shots=260,
        report_revision=first["report"]["revision"],
        **common,
    )[0]
    assert stale.status_code == 409
    payload["physical_shots"] = 500
    assert env[0].put(BASE + "/shift-reports/current", json=payload).status_code == 409
    with Session(env[1]) as db:
        assert (
            len(
                list(
                    db.scalars(select(Operation).where(Operation.kind == "report.save"))
                )
            )
            == 3
        )


def test_manual_small_machine_refused_and_factory_scoped_ids(env):
    _, _, demand = seed_job(env)
    small = ok(write(env, "/machines", {"code": "SMALL", "machine_a": 7}))["record"]
    result = write(
        env, "/schedule/move", demand_id=demand["id"], machine_id=small["id"]
    )[0]
    assert result.status_code == 422 and "12" in result.text and "7" in result.text
    other = ok(write(env, "/machines", {"code": "01", "machine_a": 12}, "huadeng"))[
        "record"
    ]
    assert (
        write(env, "/schedule/move", demand_id=demand["id"], machine_id=other["id"])[
            0
        ].status_code
        == 404
    )
    assert (
        write(
            env,
            f"/demands/{demand['id']}",
            {"planned_shots": 10},
            "huadeng",
            method="patch",
        )[0].status_code
        == 404
    )


def test_four_factories_shared_master_and_isolated_reads(env):
    master, _, _ = seed_job(env)
    for factory in ("huadeng", "huakang-a", "huakang-b"):
        visible = (
            env[0].get(BASE + "/molds", params={"factory_id": factory}).json()["rows"]
        )
        assert visible[0]["id"] == master["id"]
        assert (
            env[0]
            .get(BASE + "/machines", params={"factory_id": factory})
            .json()["rows"]
            == []
        )
        assert (
            env[0]
            .post(BASE + "/demands/query", json={"factory_id": factory})
            .json()["total_count"]
            == 0
        )
    env[2].factories = {"huaxing"}
    assert (
        env[0].get(BASE + "/molds", params={"factory_id": "huadeng"}).status_code == 403
    )
    assert (
        env[0].get(BASE + "/summary", params={"factory_id": "group"}).status_code == 422
    )


def test_machine_pause_recovery_and_running_not_moved(env):
    _, machine, _ = seed_job(env)
    run = ok(write(env, "/schedule/auto", scope={"mode": "UNSCHEDULED"}))[
        "changed_runs"
    ][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    assert (
        write(env, "/schedule/move", run_id=run["id"], machine_id=machine["id"])[
            0
        ].status_code
        == 409
    )
    stopped = ok(
        write(
            env,
            f"/machines/{machine['id']}/status",
            {"operating_status": "MAINTENANCE", "notes": "检修"},
        )
    )
    assert stopped["machine"]["operating_status"] == "MAINTENANCE"
    with Session(env[1]) as db:
        assert db.get(Run, run["id"]).status == "PAUSED"
    ok(write(env, f"/machines/{machine['id']}/status", {"operating_status": "IDLE"}))
    ok(write(env, f"/runs/{run['id']}/resume"))


def test_search_exact_and_or_filters_full_totals(env):
    _, _, demand = seed_job(env)
    ok(
        write(
            env,
            "/demands",
            {"mold_code": "M-010", "planned_shots": 25, "order_no": "0002"},
        )
    )
    result = (
        env[0]
        .post(
            BASE + "/demands/query",
            json={
                "factory_id": "huaxing",
                "search": {"field": "mold_code", "mode": "exact", "text": "M-01"},
                "page_size": 1,
            },
        )
        .json()
    )
    assert result["total_count"] == 1 and result["rows"][0]["id"] == demand["id"]
    query = {
        "factory_id": "huaxing",
        "filter": {
            "op": "or",
            "children": [
                {"field": "remaining_shots", "op": "gt", "value": 999},
                {"field": "order_no", "op": "eq", "value": "0002"},
            ],
        },
        "page_size": 1,
    }
    result = env[0].post(BASE + "/demands/query", json=query).json()
    assert (
        result["total_count"] == 2
        and result["filtered_summary"]["remaining_shots"] == 1025
    )
    assert len(result["rows"]) == 1 and result["next_cursor"] == 1
    assert (
        env[0]
        .post(
            BASE + "/demands/query",
            json={
                "factory_id": "huaxing",
                "filter": {"field": "x);DROP TABLE", "op": "eq", "value": "x"},
            },
        )
        .status_code
        == 422
    )


def test_partial_schedule_missing_fields_and_undo(env):
    seed_job(env)
    ok(write(env, "/demands", {"mold_code": "NO-MASTER", "planned_shots": 100}))
    scheduled = ok(write(env, "/schedule/auto", scope={"mode": "UNSCHEDULED"}))
    assert scheduled["scheduled_count"] == 1
    assert scheduled["unplaced"][0]["reason_code"] == "MISSING_RATE"
    ok(write(env, "/schedule/undo"))
    assert (
        env[0].get(BASE + "/timeline", params={"factory_id": "huaxing"}).json()["runs"]
        == []
    )
