from copy import deepcopy
from datetime import timedelta
from itertools import pairwise
from random import Random

import pytest
from app.services.injection_scheduling.calculations import timestamp
from app.services.injection_scheduling.defaults import factory_defaults
from app.services.injection_scheduling.scheduler import fit, schedule_factory

AT = timestamp("2026-12-31T08:00:00+08:00")


def demand(identity, **changes):
    return {
        "id": identity,
        "factory_id": "huaxing",
        "mold_master_id": "master",
        "mold_code": "M-01",
        "dispatch_state": "READY",
        "allocation_mode": "SEQUENTIAL_SHOTS",
        "remaining_shots": 100,
        "target_shots_per_day": 2400,
        "target_basis_hours": 24,
        "required_machine_a": 12,
        "material_raw": "PP",
        "resin": "PP",
        "color_name": "白色",
        "color_depth_rank": 0,
        "delivery_due_at": (AT + timedelta(days=2)).isoformat(),
        "downstream_lead_days": 0,
        "requirements_snapshot": {},
        **changes,
    }


def machine(identity, a=12, **changes):
    return {
        "id": identity,
        "factory_id": "huaxing",
        "code": identity,
        "machine_a": a,
        "operating_status": "IDLE",
        "machine_family": "HORIZONTAL",
        "speed_class": "NORMAL",
        **changes,
    }


def snapshot(demands, machines, **changes):
    return {
        "demands": demands,
        "machines": machines,
        "assets": [
            {
                "id": "asset",
                "master_id": "master",
                "current_factory_id": "huaxing",
                "status": "AVAILABLE",
            }
        ],
        "settings": factory_defaults(),
        "events": [],
        "runs": [],
        **changes,
    }


@pytest.mark.parametrize("seed", range(12))
def test_resource_component_matches_full_factory_recalculation(seed, monkeypatch):
    from app.services.injection_scheduling import scheduler

    rng = Random(seed)
    tasks = [
        demand(
            f"order-{i}",
            mold_master_id=f"master-{i % 4}",
            color_name=rng.choice(["白色", "黑色", "红色"]),
            remaining_shots=rng.randrange(100, 1000),
            priority_level=rng.randrange(3),
            delivery_due_at=(AT + timedelta(hours=rng.randrange(12, 100))).isoformat(),
            earliest_available_at=(AT + timedelta(hours=rng.randrange(4))).isoformat(),
        )
        for i in range(14)
    ]
    source = snapshot(tasks, [machine(f"machine-{i}") for i in range(5)])
    source["assets"] = [
        {
            "id": f"asset-{i}",
            "master_id": f"master-{i % 4}",
            "current_factory_id": "huaxing",
            "status": "AVAILABLE",
        }
        for i in range(6)
    ]
    source["events"] = [
        {
            "resource_type": "MACHINE",
            "resource_id": "machine-1",
            "start_at": AT.isoformat(),
            "end_at": (AT + timedelta(hours=8)).isoformat(),
        },
        {
            "resource_type": "MOLD",
            "resource_id": "asset-2",
            "start_at": (AT + timedelta(hours=3)).isoformat(),
            "end_at": (AT + timedelta(hours=7)).isoformat(),
        },
    ]
    original = deepcopy(source)
    partial = scheduler.schedule_factory(source, {}, AT)
    assert source == original
    monkeypatch.setattr(
        scheduler, "affected_machines", lambda queues, changed: set(queues)
    )
    full = scheduler.schedule_factory(source, {}, AT)
    assert partial == full


def test_resource_component_follows_multiple_machine_mold_hops():
    from app.services.injection_scheduling.scheduler import affected_machines

    queues = {
        "a": [{"mold_asset_id": "m1"}],
        "b": [{"mold_asset_id": "m1"}, {"mold_asset_id": "m2"}],
        "c": [{"mold_asset_id": "m2"}],
        "unrelated": [{"mold_asset_id": "m3"}],
    }
    assert affected_machines(queues, "a") == {"a", "b", "c"}


def test_exact_machine_wins_when_on_time_allowed_upsize_wins_for_due_risk():
    task = demand("a", delivery_due_at=(AT + timedelta(hours=6)).isoformat())
    source = snapshot([task], [machine("exact"), machine("up", 18)])
    assert schedule_factory(source, {}, AT)["changed_runs"][0]["machine_id"] == "exact"
    source["events"] = [
        {
            "resource_type": "MACHINE",
            "resource_id": "exact",
            "start_at": AT.isoformat(),
            "end_at": (AT + timedelta(days=1)).isoformat(),
        }
    ]
    run = schedule_factory(source, {}, AT)["changed_runs"][0]
    assert run["machine_id"] == "up" and run["delivery_slack_hours"] > 0


def test_obviously_oversized_requires_explicit_manual_action_and_no_rate_boost():
    source = snapshot([demand("a", required_machine_a=5)], [machine("large", 18)])
    assert not schedule_factory(source, {}, AT)["changed_runs"]
    assert (
        fit(
            source["demands"][0],
            source["machines"][0],
            source["settings"],
            manual_oversize=True,
        )
        is None
    )
    source = snapshot([demand("a")], [machine("up", 18)])
    run = schedule_factory(source, {}, AT)["changed_runs"][0]
    assert timestamp(run["planned_end_at"]) - timestamp(
        run["planned_start_at"]
    ) == timedelta(hours=1)


def test_one_physical_mold_is_serial_but_confirmed_duplicate_assets_allow_parallel():
    first = demand("a", requirements_snapshot={"forbidden_machine_codes": ["second"]})
    second = demand(
        "b",
        requirements_snapshot={"forbidden_machine_codes": ["first"]},
        color_name="黑色",
    )
    source = snapshot([first, second], [machine("first"), machine("second")])
    runs = sorted(
        schedule_factory(source, {}, AT)["changed_runs"],
        key=lambda r: r["setup_start_at"],
    )
    assert timestamp(runs[0]["planned_end_at"]) <= timestamp(runs[1]["setup_start_at"])
    source["assets"].append({**source["assets"][0], "id": "duplicate"})
    runs = schedule_factory(source, {}, AT)["changed_runs"]
    assert len({r["mold_asset_id"] for r in runs}) == 2
    assert max(timestamp(r["setup_start_at"]) for r in runs) < min(
        timestamp(r["planned_end_at"]) for r in runs
    )


def test_urgent_dark_order_precedes_later_light_and_counts_successor_cleaning():
    source = snapshot(
        [
            demand("urgent", color_name="黑色", color_depth_rank=5, priority_level=1),
            demand("later", delivery_due_at=(AT + timedelta(days=3)).isoformat()),
        ],
        [machine("one")],
    )
    runs = sorted(
        schedule_factory(source, {}, AT)["changed_runs"], key=lambda r: r["sequence"]
    )
    assert runs[0]["demand_ids"] == ["urgent"]
    assert runs[1]["explanation"]["color_change_minutes"] > 0


def test_material_grade_core_pull_high_speed_and_forbidden_code_constraints():
    settings = factory_defaults()
    task = demand(
        "a", material_raw="PMMA MF-001", resin="PMMA", material_grade="MF-001"
    )
    allowed = machine(
        "新15", restrictions={"only_resin": "PMMA", "only_grade": "MF-001"}
    )
    assert fit(task, allowed, settings) is None
    assert (
        fit({**task, "material_grade": "MF-002"}, allowed, settings)
        == "GRADE_FORBIDDEN"
    )
    assert (
        fit(
            {**task, "requirements_snapshot": {"required_capabilities": ["CORE_PULL"]}},
            {**allowed, "capabilities": {"CORE_PULL": False}},
            settings,
        )
        == "CAPABILITY_REQUIRED"
    )
    assert (
        fit(
            {**task, "requirements_snapshot": {"speed_class": "HIGH_SPEED"}},
            allowed,
            settings,
        )
        == "HIGH_SPEED_REQUIRED"
    )
    assert (
        fit(
            {
                **task,
                "requirements_snapshot": {"forbidden_machine_codes": ["新15", "新16"]},
            },
            allowed,
            settings,
        )
        == "FORBIDDEN_MACHINE"
    )


def test_inserting_new_recipe_replaces_both_neighbor_transitions_and_is_deterministic():
    source = snapshot([demand("a"), demand("b", color_name="黑色")], [machine("one")])
    old = schedule_factory(source, {}, AT)
    source["runs"] = old["changed_runs"]
    source["demands"].append(
        demand("insert", priority_level=2, material_raw="ABS", resin="ABS")
    )
    first = schedule_factory(deepcopy(source), {}, AT)
    second = schedule_factory(deepcopy(source), {}, AT)
    assert first == second
    runs = sorted(first["changed_runs"], key=lambda r: r["sequence"])
    assert len(runs) == 3 and runs[0]["demand_ids"] == ["insert"]
    assert runs[1]["explanation"]["color_change_minutes"] >= 60
    assert all(
        timestamp(a["planned_end_at"]) <= timestamp(b["setup_start_at"])
        for a, b in pairwise(runs)
    )


def test_optional_commercial_fields_do_not_block_and_incomplete_task_remains_visible():
    source = snapshot(
        [
            demand("ready", price_per_shot=None, net_weight_g=None),
            demand("missing", target_shots_per_day=None),
            demand("no-due", delivery_due_at=None, color_name="绿色"),
            demand("held", dispatch_state="WAIT_NOTICE"),
        ],
        [machine("one")],
    )
    result = schedule_factory(source, {}, AT)
    assert {item["demand_id"] for item in result["unplaced"]} == {"missing", "held"}
    runs = sorted(result["changed_runs"], key=lambda r: r["sequence"])
    assert runs[0]["demand_ids"] == ["ready"] and runs[1]["demand_ids"] == ["no-due"]
