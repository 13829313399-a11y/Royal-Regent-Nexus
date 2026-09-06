"""Independent integration regressions for physical execution and scheduling boundaries."""

from datetime import timedelta

from app.models.injection_scheduling import CalendarEvent, Demand, MoldAsset, Run
from app.services.injection_scheduling.calculations import now, timestamp
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_injection_v3_api import BASE, ok, seed_job, write
from test_injection_v3_api import env as _env_fixture

env = _env_fixture


def current_shift():
    instant = now()
    day = instant.date() if instant.hour >= 8 else (instant - timedelta(days=1)).date()
    return {
        "production_date": day.isoformat(),
        "shift_code": "DAY" if 8 <= instant.hour < 20 else "NIGHT",
    }


def report(env, run, shots, revision=0, **extra):
    return write(
        env,
        "/shift-reports/current",
        method="put",
        run_id=run["id"],
        physical_shots=shots,
        report_revision=revision,
        **current_shift(),
        **extra,
    )


def more_demand(env, **data):
    return ok(
        write(
            env,
            "/demands",
            {
                "mold_code": "M-01",
                "material_raw": "PP",
                "color_name": "白色",
                "planned_shots": 80,
                "order_no": "002",
                "delivery_due_at": (now() + timedelta(days=8)).isoformat(),
                **data,
            },
        )
    )["demand"]


def test_machine_selected_reorder_keeps_demands(env):
    _, machine, demand = seed_job(env)
    ok(write(env, "/schedule/auto"))
    result = ok(
        write(
            env,
            "/schedule/auto",
            scope={"mode": "SELECTED", "machine_ids": [machine["id"]]},
        )
    )
    assert result["scheduled_count"] == 1
    assert result["changed_runs"][0]["demand_ids"] == [demand["id"]]


def test_replanning_existing_group_preserves_every_child_once(env):
    _, _, first = seed_job(env, planned=60)
    second = more_demand(env)
    original = ok(write(env, "/schedule/auto"))["changed_runs"]
    assert len(original) == 1 and len(original[0]["demand_ids"]) == 2
    replanned = ok(write(env, "/schedule/auto", scope={"mode": "ALL_UNSTARTED"}))
    rows = replanned["changed_runs"]
    assert replanned["scheduled_count"] == 2
    assert len({row["id"] for row in rows}) == len(rows)
    assert sorted(identity for row in rows for identity in row["demand_ids"]) == sorted(
        [first["id"], second["id"]]
    )
    assert sum(row["remaining_shots"] for row in rows) == 140


def test_changed_child_process_splits_only_unstarted_group(env):
    _, machine, first = seed_job(env, planned=60)
    second = more_demand(env)
    ok(write(env, "/schedule/auto"))
    ok(write(env, f"/demands/{second['id']}", {"color_name": "黑色"}, method="patch"))
    rows = (
        env[0].get(BASE + "/timeline", params={"factory_id": "huaxing"}).json()["runs"]
    )
    assert len(rows) == 2
    assert {tuple(row["demand_ids"]) for row in rows} == {
        (first["id"],),
        (second["id"],),
    }
    original_order = [
        row["id"] for row in sorted(rows, key=lambda row: row["sequence"])
    ]
    ok(
        write(
            env,
            "/schedule/move",
            run_id=original_order[0],
            machine_id=machine["id"],
            pinned=True,
        )
    )
    pinned = (
        env[0].get(BASE + "/timeline", params={"factory_id": "huaxing"}).json()["runs"]
    )
    assert [
        row["id"] for row in sorted(pinned, key=lambda row: row["sequence"])
    ] == original_order


def test_malformed_requirement_and_schedule_scope_return_validation_error(env):
    _, _, task = seed_job(env)
    for value in ({"machine_family": []}, {"speed_class": {}}, {"raw": []}):
        assert (
            write(
                env,
                f"/demands/{task['id']}",
                {"requirements_snapshot": value},
                method="patch",
            )[0].status_code
            == 422
        )
    assert (
        write(env, "/schedule/auto", scope={"demand_ids": [{}]})[0].status_code == 422
    )


def test_timeline_shift_counter_distinguishes_unreported_zero_and_correction(env):
    seed_job(env, planned=100)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]

    def timeline():
        return env[0].get(BASE + "/timeline", params={"factory_id": "huaxing"}).json()

    assert timeline()["runs"][0]["current_shift_shots"] is None
    ok(write(env, f"/runs/{run['id']}/start"))
    saved = ok(report(env, run, 0))
    assert timeline()["runs"][0]["current_shift_shots"] == 0
    ok(report(env, run, 30, saved["report"]["revision"]))
    value = timeline()
    assert value["current_production_date"] == current_shift()["production_date"]
    assert value["current_shift_code"] == current_shift()["shift_code"]
    assert value["runs"][0]["current_shift_shots"] == 30
    assert value["runs"][0]["remaining_shots"] == 70


def test_shift_clock_uses_configured_factory_boundaries():
    from app.services.injection_scheduling.reports import current_shift

    settings = {"day_start": "07:30", "night_start": "19:30"}
    day, code = current_shift("2026-09-06T07:29:59+08:00", settings)
    assert day.isoformat() == "2026-09-05" and code == "NIGHT"
    assert current_shift("2026-09-06T07:30:00+08:00", settings)[1] == "DAY"
    assert current_shift("2026-09-06T19:30:00+08:00", settings)[1] == "NIGHT"


def test_cumulative_report_after_plan_increase_and_actual_overproduction(env):
    _, _, demand = seed_job(env, planned=100)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    ok(write(env, f"/demands/{demand['id']}", {"planned_shots": 200}, method="patch"))
    first = ok(report(env, run, 150))
    assert (
        env[0]
        .get(BASE + "/summary", params={"factory_id": "huaxing"})
        .json()["remaining_shots"]
        == 50
    )
    ok(report(env, run, 230, first["report"]["revision"]))
    with Session(env[1]) as db:
        saved = db.get(Demand, demand["id"])
        assert (
            saved.completed_shots == 230
            and saved.overproduced_shots == 30
            and saved.remaining_shots == 0
        )


def test_live_rate_edit_changes_forecast_without_moving_actual_start(env):
    _, _, demand = seed_job(env)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    started = ok(write(env, f"/runs/{run['id']}/start"))["run"]
    result = ok(
        write(
            env,
            f"/demands/{demand['id']}",
            {"target_shots_per_day": 4800},
            method="patch",
        )
    )
    assert timestamp(result["changed_runs"][0]["planned_end_at"]) < timestamp(
        started["planned_end_at"]
    ) - timedelta(hours=4)
    with Session(env[1]) as db:
        assert timestamp(db.get(Run, run["id"]).actual_start_at) == timestamp(
            started["actual_start_at"]
        )


def test_material_raw_cannot_bypass_machine_restrictions(env):
    _, machine, demand = seed_job(env)
    ok(
        write(
            env,
            f"/machines/{machine['id']}",
            {"restrictions": {"forbidden_resins": ["PVC"]}},
            method="patch",
        )
    )
    changed = ok(
        write(
            env,
            f"/demands/{demand['id']}",
            {"material_raw": "PVC transparent"},
            method="patch",
        )
    )
    assert changed["demand"]["resin"] == "PVC"
    result = ok(write(env, "/schedule/auto"))
    assert (
        not result["changed_runs"]
        and result["unplaced"][0]["reason_code"] == "MATERIAL_FORBIDDEN"
    )


def test_start_and_resume_honor_live_resource_calendar(env):
    _, machine, _ = seed_job(env)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    event = ok(
        write(
            env,
            "/calendar-events",
            {
                "resource_type": "MACHINE",
                "resource_id": machine["id"],
                "start_at": (now() - timedelta(minutes=1)).isoformat(),
                "end_at": (now() + timedelta(hours=2)).isoformat(),
            },
        )
    )["record"]
    assert write(env, f"/runs/{run['id']}/start")[0].status_code == 409
    ok(
        write(
            env,
            f"/calendar-events/{event['id']}",
            {"end_at": (now() - timedelta(seconds=1)).isoformat()},
            method="patch",
        )
    )
    ok(write(env, f"/runs/{run['id']}/start"))
    ok(write(env, f"/runs/{run['id']}/pause"))
    ok(
        write(
            env,
            "/calendar-events",
            {
                "resource_type": "FACTORY",
                "start_at": now().isoformat(),
                "end_at": (now() + timedelta(hours=1)).isoformat(),
            },
        )
    )
    assert write(env, f"/runs/{run['id']}/resume")[0].status_code == 409


def test_unknown_mold_calendar_unplaces_only_affected_plan(env):
    _, _, demand = seed_job(env)
    ok(write(env, "/schedule/auto"))
    with Session(env[1]) as db:
        asset = db.scalar(select(MoldAsset))
        asset_id = asset.id
    changed = ok(
        write(
            env,
            "/calendar-events",
            {
                "resource_type": "MOLD",
                "resource_id": asset_id,
                "start_at": now().isoformat(),
            },
        )
    )
    assert changed["unplaced"][0]["demand_id"] == demand["id"]
    assert not changed["changed_runs"]


def test_pin_keeps_position_but_calendar_and_edits_can_shift_forecast(env):
    _, machine, demand = seed_job(env)
    moved = ok(
        write(
            env,
            "/schedule/move",
            demand_id=demand["id"],
            machine_id=machine["id"],
            pinned=True,
        )
    )
    ok(
        write(
            env,
            f"/demands/{demand['id']}",
            {"order_note": "ordinary edit"},
            method="patch",
        )
    )
    stop_end = now() + timedelta(hours=3)
    result = ok(
        write(
            env,
            "/calendar-events",
            {
                "resource_type": "MACHINE",
                "resource_id": machine["id"],
                "start_at": now().isoformat(),
                "end_at": stop_end.isoformat(),
            },
        )
    )
    assert result["changed_runs"][0]["id"] == moved["moved_run_id"]
    assert timestamp(result["changed_runs"][0]["planned_start_at"]) >= stop_end


def test_early_machine_recovery_closes_finite_status_calendar(env):
    _, machine, _ = seed_job(env)
    ok(
        write(
            env,
            f"/machines/{machine['id']}/status",
            {
                "operating_status": "FAULT",
                "recovery_at": (now() + timedelta(hours=8)).isoformat(),
            },
        )
    )
    ok(write(env, f"/machines/{machine['id']}/status", {"operating_status": "IDLE"}))
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    assert timestamp(run["setup_start_at"]) < now() + timedelta(minutes=1)
    with Session(env[1]) as db:
        assert timestamp(db.scalar(select(CalendarEvent)).end_at) <= now()


def test_unknown_recovery_hides_sentinel_but_keeps_machine_and_mold_occupied(env):
    _, machine, demand = seed_job(env, planned=1000)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    started = ok(write(env, f"/runs/{run['id']}/start"))["run"]["actual_start_at"]
    ok(report(env, run, 230))
    target = ok(write(env, "/machines", {"code": "02", "machine_a": 12}))["record"]
    second = more_demand(env)
    stopped = ok(
        write(
            env,
            f"/machines/{machine['id']}/status",
            {"operating_status": "MAINTENANCE"},
        )
    )
    active = next(row for row in stopped["changed_runs"] if row["id"] == run["id"])
    assert (
        active["forecast_unknown"]
        and active["forecast_status"] == "WAITING_FOR_RECOVERY"
    )
    assert (
        active["planned_end_at"]
        is active["expected_stock_ready_at"]
        is active["delivery_slack_hours"]
        is None
    )
    with Session(env[1]) as db:
        saved = db.get(Run, run["id"])
        assert timestamp(saved.planned_end_at) > now() + timedelta(days=700)
        assert db.get(Demand, demand["id"]).planned_end_at is None
        # Existing QA records predate the persisted marker; read paths must hide them too.
        saved.explanation = {
            key: value
            for key, value in saved.explanation.items()
            if key != "forecast_unknown"
        }
        db.commit()
    timeline = (
        env[0]
        .get(BASE + "/timeline", params={"factory_id": "huaxing"})
        .json()["runs"][0]
    )
    assert (
        timeline["planned_end_at"] is None
        and timeline["snapshot"]["planned_end_at"] is None
    )
    assert timeline["physical_shots"] == 230 and timeline["actual_start_at"] == started
    assert (
        write(env, "/schedule/move", demand_id=second["id"], machine_id=target["id"])[
            0
        ].status_code
        == 409
    )
    automatic = ok(write(env, "/schedule/auto", scope={"mode": "ALL_UNSTARTED"}))
    assert automatic["scheduled_count"] == 1
    assert automatic["impact"]["late_orders_after"] == 0
    assert second["id"] in {item["demand_id"] for item in automatic["unplaced"]}
    ok(write(env, f"/machines/{machine['id']}/status", {"operating_status": "IDLE"}))
    resumed = ok(write(env, f"/runs/{run['id']}/resume"))
    active = next(row for row in resumed["changed_runs"] if row["id"] == run["id"])
    assert not active["forecast_unknown"]
    assert timestamp(active["planned_end_at"]) < now() + timedelta(days=1)
    assert resumed["run"]["actual_start_at"] == started
    ok(write(env, f"/runs/{run['id']}/pause"))
    with Session(env[1]) as db:
        db.get(Run, run["id"]).explanation = {}
        db.commit()
    finished = ok(write(env, f"/runs/{run['id']}/finish"))["run"]
    assert finished["planned_end_at"] == finished["actual_end_at"]
    assert not finished["forecast_unknown"]


def test_automatic_continuous_group_and_fifo_correction(env):
    _, _, first = seed_job(env, planned=60)
    second = more_demand(env)
    result = ok(write(env, "/schedule/auto"))
    assert len(result["changed_runs"]) == 1
    run = result["changed_runs"][0]
    assert run["demand_ids"] == [first["id"], second["id"]]
    with Session(env[1]) as db:
        assert (
            db.get(Demand, first["id"]).planned_end_at
            < db.get(Demand, second["id"]).planned_end_at
        )
    ok(write(env, f"/runs/{run['id']}/start"))
    saved = ok(report(env, run, 100))
    with Session(env[1]) as db:
        assert db.get(Demand, first["id"]).completed_shots == 60
        assert db.get(Demand, second["id"]).completed_shots == 40
        assert db.get(Run, run["id"]).physical_shots == 100
    ok(write(env, f"/demands/{first['id']}", {"planned_shots": 30}, method="patch"))
    with Session(env[1]) as db:
        assert db.get(Demand, first["id"]).completed_shots == 30
        assert db.get(Demand, second["id"]).completed_shots == 70
    ok(report(env, run, 80, saved["report"]["revision"]))
    with Session(env[1]) as db:
        assert db.get(Demand, second["id"]).completed_shots == 50


def test_explicit_group_preserves_demands_and_rejects_recipe_mix(env):
    _, machine, first = seed_job(env, planned=60)
    second = more_demand(env)
    grouped = ok(
        write(
            env,
            "/schedule/group",
            demand_ids=[first["id"], second["id"]],
            machine_id=machine["id"],
        )
    )
    assert len(grouped["changed_runs"][0]["demand_ids"]) == 2
    third = more_demand(env, color_name="黑色", order_no="003")
    assert (
        write(
            env,
            "/schedule/group",
            demand_ids=[first["id"], second["id"], third["id"]],
            machine_id=machine["id"],
        )[0].status_code
        == 422
    )


def test_co_output_physical_counter_is_not_sum_of_product_equivalents(env):
    _, _, first = seed_job(env, planned=100)
    vector = {"A": 2, "B": 1}
    ok(
        write(
            env,
            f"/demands/{first['id']}",
            {
                "item_no": "A",
                "allocation_mode": "CO_OUTPUT_UNITS",
                "required_units": 100,
                "effective_outputs_per_shot": 2,
                "output_configuration": vector,
                "co_output_group": "confirmed-1",
            },
            method="patch",
        )
    )
    second = more_demand(
        env,
        item_no="B",
        allocation_mode="CO_OUTPUT_UNITS",
        required_units=80,
        effective_outputs_per_shot=1,
        output_configuration=vector,
        co_output_group="confirmed-1",
    )
    result = ok(write(env, "/schedule/auto"))
    assert len(result["changed_runs"]) == 1
    run = result["changed_runs"][0]
    assert run["remaining_shots"] == 80
    ok(write(env, f"/runs/{run['id']}/start"))
    ok(report(env, run, 80))
    with Session(env[1]) as db:
        assert db.get(Run, run["id"]).physical_shots == 80
        assert db.get(Demand, first["id"]).good_units == 160
        assert db.get(Demand, second["id"]).good_units == 80
        assert db.get(Demand, first["id"]).completed_shots == 0


def test_transfer_remaining_and_old_report_correction_keep_history_on_original_run(env):
    _, _, first = seed_job(env, planned=60)
    second = more_demand(env)
    target = ok(write(env, "/machines", {"code": "02", "machine_a": 12}))["record"]
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    original = ok(report(env, run, 100))
    ok(write(env, f"/runs/{run['id']}/pause"))
    transferred = ok(
        write(env, f"/runs/{run['id']}/transfer", target_machine_id=target["id"])
    )
    successor = next(
        row for row in transferred["changed_runs"] if row["id"] != run["id"]
    )
    assert successor["remaining_shots"] == 40
    ok(write(env, f"/runs/{successor['id']}/start"))
    ok(report(env, successor, 20))
    ok(report(env, run, 50, original["report"]["revision"]))
    with Session(env[1]) as db:
        assert db.get(Run, run["id"]).status == "TRANSFERRED"
        assert db.get(Run, run["id"]).physical_shots == 50
        assert db.get(Run, successor["id"]).physical_shots == 20
        assert db.get(Demand, first["id"]).completed_shots == 60
        assert db.get(Demand, second["id"]).completed_shots == 10
    history = (
        env[0]
        .get(
            BASE + "/timeline",
            params={"factory_id": "huaxing", "include_finished": True},
        )
        .json()["runs"]
    )
    assert {row["id"] for row in history} == {run["id"], successor["id"]}


def test_asset_relocation_cancels_source_plans_but_not_identity(env):
    _, _, demand = seed_job(env)
    ok(write(env, "/schedule/auto"))
    asset = (
        env[0]
        .get(BASE + "/mold-assets", params={"factory_id": "huaxing"})
        .json()["rows"][0]
    )
    changed = ok(
        write(
            env,
            f"/mold-assets/{asset['id']}/relocate",
            destination_factory_id="huadeng",
        )
    )
    assert (
        changed["record"]["id"] == asset["id"]
        and changed["record"]["current_factory_id"] == "huadeng"
    )
    assert changed["source_impact"]["unplaced"][0]["demand_id"] == demand["id"]
    assert (
        not env[0]
        .get(BASE + "/mold-assets", params={"factory_id": "huaxing"})
        .json()["rows"]
    )


def test_reports_reject_fraction_and_bool_physical_counters(env):
    seed_job(env)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    assert report(env, run, 1.5)[0].status_code == 422
    assert report(env, run, True)[0].status_code == 422


def test_co_output_good_units_for_same_product_are_not_duplicated(env):
    _, _, first = seed_job(env, planned=100)
    vector = {"A": 2}
    common = {
        "item_no": "A",
        "allocation_mode": "CO_OUTPUT_UNITS",
        "required_units": 100,
        "effective_outputs_per_shot": 2,
        "output_configuration": vector,
        "co_output_group": "A-1",
    }
    ok(write(env, f"/demands/{first['id']}", common, method="patch"))
    second = more_demand(env, **common)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    assert run["remaining_shots"] == 100
    ok(write(env, f"/runs/{run['id']}/start"))
    assert report(env, run, 80, good_units={"not-an-output": 1})[0].status_code == 422
    ok(report(env, run, 80, scrap_units={"A": 10}))
    with Session(env[1]) as db:
        assert db.get(Demand, first["id"]).good_units == 100
        assert db.get(Demand, second["id"]).good_units == 50
    assert (
        write(
            env,
            f"/demands/{first['id']}",
            {"allocation_mode": "SEQUENTIAL_SHOTS"},
            method="patch",
        )[0].status_code
        == 409
    )


def test_changing_mold_drops_old_master_values_and_asset_match(env):
    seed_job(env)
    demand = more_demand(env)
    mold = ok(
        write(
            env,
            "/molds",
            {
                "mold_code": "M-02",
                "required_machine_a": 24,
                "defaults": {"target_shots_per_day": 4800},
            },
        )
    )["record"]
    changed = ok(
        write(env, f"/demands/{demand['id']}", {"mold_code": "M-02"}, method="patch")
    )["demand"]
    assert (
        changed["mold_master_id"] == mold["id"]
        and changed["required_machine_a"] == 24
        and changed["target_shots_per_day"] == 4800
    )
    changed = ok(
        write(
            env,
            f"/demands/{demand['id']}",
            {"mold_code": "NO-SUCH-MOLD"},
            method="patch",
        )
    )["demand"]
    assert changed["mold_master_id"] is None and changed["required_machine_a"] is None


def test_invalid_nested_constraints_and_dates_return_validation_errors(env):
    _, machine, demand = seed_job(env)
    assert (
        write(
            env,
            f"/machines/{machine['id']}",
            {"capabilities": {"CORE_PULL": "false"}},
            method="patch",
        )[0].status_code
        == 422
    )
    assert (
        write(
            env,
            f"/demands/{demand['id']}",
            {"requirements_snapshot": {"required_capabilities": "CORE_PULL"}},
            method="patch",
        )[0].status_code
        == 422
    )
    assert (
        write(env, "/settings", {"allowed_upsize": []}, method="patch")[0].status_code
        == 422
    )
    assert (
        write(
            env,
            "/calendar-events",
            {"resource_type": "FACTORY", "start_at": "not-a-date", "end_at": "invalid"},
        )[0].status_code
        == 422
    )
    assert (
        env[0]
        .post(
            BASE + "/demands/query",
            json={
                "factory_id": "huaxing",
                "filter": {
                    "field": "delivery_due_at",
                    "op": "on_day",
                    "value": "invalid",
                },
            },
        )
        .status_code
        == 422
    )


def test_finish_with_remainder_creates_new_execution_segment_and_preserves_old_report(
    env,
):
    seed_job(env, planned=100)
    run = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    ok(write(env, f"/runs/{run['id']}/start"))
    ok(report(env, run, 60))
    ok(write(env, f"/runs/{run['id']}/finish"))
    following = ok(write(env, "/schedule/auto"))["changed_runs"][0]
    assert following["id"] != run["id"] and following["remaining_shots"] == 40
    with Session(env[1]) as db:
        assert (
            db.get(Run, run["id"]).status == "FINISHED"
            and db.get(Run, run["id"]).physical_shots == 60
        )
        assert db.get(Run, following["id"]).actual_start_at is None
    ok(write(env, f"/runs/{following['id']}/start"))
    ok(report(env, following, 20))
    assert (
        env[0]
        .get(BASE + "/summary", params={"factory_id": "huaxing"})
        .json()["completed_shots"]
        == 80
    )
