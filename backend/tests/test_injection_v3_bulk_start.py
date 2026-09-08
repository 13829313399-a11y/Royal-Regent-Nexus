"""Bulk production starts use reviewed heads, real execution locks and receipts."""

from uuid import uuid4

import pytest
from app.models.injection_scheduling import Machine, MoldAsset, Operation, Run
from app.services.injection_scheduling import bulk_start
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as _env_fixture
from test_injection_v3_execution import more_demand

env = _env_fixture


def arrange(env, shared=False):
    _, machine, demand = seed_job(env)
    ok(write(env, "/schedule/move", demand_id=demand["id"], machine_id=machine["id"]))
    second = ok(
        write(
            env,
            "/machines",
            {"code": "02", "machine_a": 12, "machine_family": "HORIZONTAL"},
        )
    )["record"]
    if not shared:
        mold = ok(
            write(
                env,
                "/molds",
                {
                    "mold_code": "M-02",
                    "required_machine_a": 12,
                    "defaults": {"target_shots_per_day": 2400},
                },
            )
        )["record"]
        ok(
            write(
                env,
                "/mold-assets",
                {
                    "master_id": mold["id"],
                    "asset_code": "M-02-asset",
                    "current_factory_id": "huaxing",
                },
            )
        )
    task = more_demand(env, mold_code="M-01" if shared else "M-02")
    ok(write(env, "/schedule/move", demand_id=task["id"], machine_id=second["id"]))
    # A second batch on machine 01 must remain queued after a bulk start.
    tail = more_demand(env, color_name="黑色")
    ok(write(env, "/schedule/move", demand_id=tail["id"], machine_id=machine["id"]))
    runs = (
        env[0].get(BASE + "/timeline", params={"factory_id": "huaxing"}).json()["runs"]
    )
    return [
        {
            "machine_id": m["id"],
            "run_id": min(
                (r for r in runs if r["machine_id"] == m["id"]),
                key=lambda r: r["sequence"],
            )["id"],
        }
        for m in [machine, second]
    ]


def preview(env, items, factory="huaxing"):
    return ok(
        env[0].post(
            BASE + "/execution/start-preview",
            json={"factory_id": factory, "items": items},
        )
    )


def payload(review):
    return {
        "factory_id": "huaxing",
        "base_revision": review["revision"],
        "expected_revision": review["revision"],
        "client_operation_id": uuid4().hex,
        "confirm_actual_start": True,
        "items": [
            {k: row[k] for k in ["machine_id", "run_id", "review_token"]}
            for row in review["items"]
        ],
    }


def commit(env, data):
    return env[0].post(BASE + "/execution/bulk-start", json=data)


def test_review_is_read_only_and_starts_only_heads_once_with_one_timestamp(env):
    items = arrange(env)
    with Session(env[1]) as db:
        operations = len(list(db.scalars(select(Operation))))
    reviewed = preview(env, items)
    assert reviewed["eligible_count"] == 2
    assert all(row["remaining_shots"] > 0 for row in reviewed["items"])
    with Session(env[1]) as db:
        assert all(r.status == "PLANNED" for r in db.scalars(select(Run)))
        assert len(list(db.scalars(select(Operation)))) == operations
    data = payload(reviewed)
    receipt = ok(commit(env, data))
    assert receipt["started_count"] == 2, receipt
    assert ok(commit(env, data)) == receipt
    with Session(env[1]) as db:
        runs = list(db.scalars(select(Run)))
        active = [r for r in runs if r.status == "RUNNING"]
        assert len(active) == 2 and len(runs) == 3
        assert len({r.actual_start_at for r in active}) == 1
        assert all(
            r.physical_shots == 0 and len(r.execution_events) == 1 for r in active
        )
        assert len(list(db.scalars(select(Operation)))) == operations + 1
        audit = db.scalar(
            select(Operation).where(
                Operation.client_operation_id == data["client_operation_id"]
            )
        )
        assert audit is not None and len(audit.before) == 2
        assert all(
            db.get(Machine, r.machine_id).operating_status == "RUNNING" for r in active
        )


def test_shared_physical_mold_has_no_arbitrary_winner(env):
    items = arrange(env, shared=True)
    reviewed = preview(env, items)
    assert reviewed["eligible_count"] == 0
    assert all("共用" in row["reason"] for row in reviewed["items"])
    assert ok(commit(env, payload(reviewed)))["started_count"] == 0
    single = preview(env, items[:1])
    assert ok(commit(env, payload(single)))["started_count"] == 1
    assert preview(env, items[1:])["eligible_count"] == 0


def test_partial_failure_rolls_back_failed_machine_and_preserves_retry(
    env, monkeypatch
):
    items = arrange(env)
    reviewed = preview(env, items)
    original = bulk_start.action

    def fail_after_mutation(db, factory, run_id, *args, **kwargs):
        result = original(db, factory, run_id, *args, **kwargs)
        if run_id == items[1]["run_id"]:
            raise HTTPException(409, "设备刚刚停机")
        return result

    monkeypatch.setattr(bulk_start, "action", fail_after_mutation)
    result = ok(commit(env, payload(reviewed)))
    assert result["started_count"] == result["failed_count"] == 1
    assert result["results"][1]["reason"] == "设备刚刚停机"
    with Session(env[1]) as db:
        failed = db.get(Run, items[1]["run_id"])
        assert failed.status == "PLANNED" and failed.actual_start_at is None
        assert failed.execution_events == []
        assert db.get(Machine, failed.machine_id).operating_status == "IDLE"
    monkeypatch.setattr(bulk_start, "action", original)
    assert ok(commit(env, payload(preview(env, items[1:]))))["started_count"] == 1


def test_changed_head_is_never_silently_substituted(env):
    items = arrange(env)
    reviewed = preview(env, items)
    with Session(env[1]) as db:
        db.get(Run, items[0]["run_id"]).sequence = 99999
        db.commit()
    result = ok(commit(env, payload(reviewed)))
    assert result["started_count"] == 1
    assert "下一批已变化" in result["results"][0]["reason"]
    with Session(env[1]) as db:
        assert all(
            r.status == "PLANNED"
            for r in db.scalars(
                select(Run).where(Run.machine_id == items[0]["machine_id"])
            )
        )


def test_resource_changed_after_review_is_rejected_even_without_factory_revision(env):
    items = arrange(env)
    reviewed = preview(env, items)
    with Session(env[1]) as db:
        run = db.get(Run, items[0]["run_id"])
        db.get(MoldAsset, run.mold_asset_id).notes = "重新核对模具资料"
        db.commit()
    result = ok(commit(env, payload(reviewed)))
    assert result["started_count"] == 1
    assert "资料已变化" in result["results"][0]["reason"]


def test_stale_revision_and_unconfirmed_requests_write_nothing(env):
    items = arrange(env)
    reviewed = preview(env, items)
    unconfirmed = {**payload(reviewed), "confirm_actual_start": False}
    assert commit(env, unconfirmed).status_code == 422
    ok(write(env, "/machines", {"code": "03", "machine_a": 12}))
    assert commit(env, payload(reviewed)).status_code == 409
    with Session(env[1]) as db:
        assert all(r.status == "PLANNED" for r in db.scalars(select(Run)))


@pytest.mark.parametrize("blocked", ["MAINTENANCE", "FAULT", "DISABLED"])
def test_device_stop_blocks_bulk_but_missing_removable_tools_does_not(env, blocked):
    items = arrange(env)
    assert preview(env, items)["eligible_count"] == 2
    with Session(env[1]) as db:
        db.get(Machine, items[0]["machine_id"]).operating_status = blocked
        db.commit()
    reviewed = preview(env, items)
    assert reviewed["eligible_count"] == 1
    assert "不可生产" in reviewed["items"][0]["reason"]
    assert ok(commit(env, payload(reviewed)))["started_count"] == 1


def test_report_permission_factory_boundary_and_duplicate_selection(env):
    items = arrange(env)
    reviewed = preview(env, items)
    assert preview(env, items, "huadeng")["eligible_count"] == 0
    assert (
        env[0]
        .post(
            BASE + "/execution/start-preview",
            json={"factory_id": "huaxing", "items": items + items},
        )
        .status_code
        == 422
    )
    env[2].permissions.remove("report")
    assert (
        env[0]
        .post(
            BASE + "/execution/start-preview",
            json={"factory_id": "huaxing", "items": items},
        )
        .status_code
        == 403
    )
    assert commit(env, payload(reviewed)).status_code == 403
