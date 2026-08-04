from itertools import pairwise

from test_injection_scheduling_phase3_api import (
    ADMIN_TEST_PASSWORD,
    login,
    machine_payload,
    make_client,
    mold_payload,
    order_payload,
)


def _phase4_fixture(client):
    factory_id = "huaxing"
    machines = []
    for index, machine_class in ((1, "7A"), (2, "12A")):
        payload = machine_payload(factory_id, f"V2-P4-CP-{index}")
        payload.update(
            machine_class=machine_class,
            injection_capacity_g=260,
        )
        machines.append(
            client.post("/api/injection-scheduling/machines", json=payload).json()
        )
    mold_data = mold_payload(factory_id, "V2-P4-CP-MOLD")
    mold_data.update(
        recommended_machine_class="7A",
        whole_shot_net_weight_g=120,
        material_code="ABS",
        color_profile="浅蓝",
        copy_count=1,
    )
    mold = client.post("/api/injection-scheduling/molds", json=mold_data).json()
    orders = []
    for index in (1, 2, 3):
        payload = order_payload(factory_id, f"V2-P4-CP-ORDER-{index}", 80)
        payload.update(
            mold_id=mold["id"],
            delivery_due_date="2026-08-08",
        )
        orders.append(
            client.post("/api/injection-scheduling/orders", json=payload).json()
        )
    draft = client.post(
        "/api/injection-scheduling/plans/drafts",
        json={
            "factory_id": factory_id,
            "expected_revision": 0,
            "business_date": "2026-08-04",
        },
    ).json()
    return factory_id, machines, mold, orders, draft


def _run_payload(factory_id, orders, draft, **overrides):
    payload = {
        "factory_id": factory_id,
        "plan_id": draft["id"],
        "expected_plan_revision": draft["revision"],
        "rule_revision": draft["rule_revision"],
        "mode": "PREVIEW",
        "horizon_start": "2026-08-04T08:00:00+08:00",
        "horizon_end": "2026-08-10T20:00:00+08:00",
        "order_ids": [item["id"] for item in orders],
        "respect_locked_tasks": True,
        "solver": "CP_SAT",
        "time_limit_seconds": 10,
        "objective_weights": {
            "tardiness_weight": 100,
            "transition_weight": 2,
            "class_gap_weight": 2,
            "load_balance_weight": 25,
            "existing_task_move_cost": 40,
        },
        "scenario_group_id": "scenario-phase4-cp",
        "scenario_name": "方案 A · 综合平衡",
        "alternative_no": 1,
    }
    payload.update(overrides)
    return payload


def test_v2_phase4_cp_sat_is_feasible_deterministic_and_replayable(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id, machines, _, orders, draft = _phase4_fixture(client)
        payload = _run_payload(factory_id, orders, draft)

        first = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase4-cp-preview-001"},
            json=payload,
        )
        assert first.status_code == 201, first.text
        first_run = first.json()
        assert first_run["solver_type"] == "CP_SAT"
        assert first_run["requested_solver"] == "CP_SAT"
        assert first_run["solver_status"] in {"OPTIMAL", "FEASIBLE"}
        assert first_run["fallback_used"] is False
        assert first_run["scenario_group_id"] == "scenario-phase4-cp"
        assert first_run["summary"]["scheduled_count"] == 3
        assert first_run["summary"]["objective_value"] is not None
        assert all(
            item["explanation"]["solver"]["machine_no_overlap"]
            and item["explanation"]["solver"]["mold_copy_no_overlap"]
            for item in first_run["assignments"]
        )
        by_machine = {}
        for item in first_run["assignments"]:
            by_machine.setdefault(item["machine_id"], []).append(item)
        for assignments in by_machine.values():
            ordered = sorted(assignments, key=lambda item: item["planned_start"])
            assert all(
                left["planned_finish"] <= right["planned_start"]
                for left, right in pairwise(ordered)
            )

        second = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase4-cp-preview-002"},
            json={
                **payload,
                "scenario_name": "方案 A · 权重回放",
                "alternative_no": 2,
                "replay_of_run_id": first_run["id"],
            },
        )
        assert second.status_code == 201, second.text
        second_run = second.json()
        assert second_run["replay_of_run_id"] == first_run["id"]
        comparable = lambda run: [
            (
                item["order_id"],
                item["machine_id"],
                item["mold_copy_no"],
                item["planned_start"],
                item["planned_finish"],
            )
            for item in run["assignments"]
        ]
        assert comparable(first_run) == comparable(second_run)
        assert machines[0]["id"] != machines[1]["id"]
        applied = client.post(
            f"/api/injection-scheduling/auto-schedule/runs/{first_run['id']}/apply",
            json={
                "factory_id": factory_id,
                "expected_plan_revision": draft["revision"],
                "expected_rule_revision": draft["rule_revision"],
                "request_id": "v2-phase4-cp-apply-001",
                "review_override_reason": "",
            },
        )
        assert applied.status_code == 200, applied.text
        assert applied.json()["run"]["solver_type"] == "CP_SAT"
        assert all(
            item["auto_schedule_run_id"] == first_run["id"]
            for item in applied.json()["plan"]["tasks"]
        )


def test_v2_phase4_cp_sat_unavailable_and_time_limit_fall_back(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        factory_id, _, _, orders, draft = _phase4_fixture(client)
        from app.services.injection_scheduling_scheduler import run_service
        from app.services.injection_scheduling_scheduler.cp_sat import (
            CpSatUnavailableError,
        )
        from app.services.injection_scheduling_scheduler.heuristic import (
            HeuristicResult,
        )

        def unavailable(**_kwargs):
            raise CpSatUnavailableError("测试模拟 OR-Tools 不可用")

        monkeypatch.setattr(run_service, "solve_cp_sat", unavailable)
        unavailable_response = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase4-cp-unavailable"},
            json=_run_payload(
                factory_id,
                orders,
                draft,
                scenario_group_id="scenario-phase4-fallback",
                scenario_name="不可用回退",
            ),
        )
        assert unavailable_response.status_code == 201, unavailable_response.text
        unavailable_run = unavailable_response.json()
        assert unavailable_run["solver_type"] == "HEURISTIC"
        assert unavailable_run["solver_status"] == "UNAVAILABLE"
        assert unavailable_run["fallback_used"] is True
        assert "OR-Tools 不可用" in unavailable_run["fallback_reason"]

        def timed_out(**_kwargs):
            return HeuristicResult(
                (),
                {
                    "scheduled_count": 0,
                    "review_count": 0,
                    "unassigned_count": 0,
                    "solver_status": "TIME_LIMIT",
                },
                (),
            )

        monkeypatch.setattr(run_service, "solve_cp_sat", timed_out)
        timeout_response = client.post(
            "/api/injection-scheduling/auto-schedule/runs",
            headers={"X-Request-ID": "v2-phase4-cp-time-limit"},
            json=_run_payload(
                factory_id,
                orders,
                draft,
                scenario_group_id="scenario-phase4-fallback",
                scenario_name="超时回退",
                alternative_no=2,
            ),
        )
        assert timeout_response.status_code == 201, timeout_response.text
        timeout_run = timeout_response.json()
        assert timeout_run["solver_type"] == "HEURISTIC"
        assert timeout_run["solver_status"] == "TIME_LIMIT"
        assert timeout_run["fallback_used"] is True
        assert timeout_run["summary"]["scheduled_count"] == 3
