"""Expanded observer fleet: real application protocol, isolated synthetic devices."""

import importlib
from datetime import timedelta

from sqlalchemy import select

from test_three_d_connector import environment, event, post, registered
from test_three_d_run_reconciliation import runs, seed_product
from test_three_d_sixteen_fleet import expand


def test_new_observers_complete_once_after_disconnect_without_hardware_control(environment):
    env = environment
    ids = expand(env, 18)
    seed_product(env)
    with env[1].SessionLocal() as db:
        for number in (17, 18):
            db.get(env[2].ThreeDPrintingPrinterConnection, ids[number]).record_reconcile_enabled = True
        db.commit()
    registered(env)
    assert len(post(env, "/printers", {"instance_id": "replica-a"})["printers"]) == 18
    refs = {}
    for number in (17, 18):
        base = {"instance_id": "replica-a", "printer_id": ids[number]}
        grant = post(env, "/leases/acquire", base)
        assert grant["acquired"] and grant["machine_no"] == number
        assert grant["control_verified"] is False
        ref = {**base, "leader_lease_id": grant["leader_lease_id"],
               "connection_session_id": f"new-machine-{number}"}
        post(env, "/sessions/start", {**ref, "generation": 1})
        refs[number] = ref
        post(env, "/events", event(env, ref, state="PREPARE", current_file="part.3mf"))
    assert runs(env) == []
    for ref in refs.values():
        # The same native task ID on two printers must remain two distinct jobs.
        post(env, "/events", event(env, ref, 2, "RUNNING", progress_percent=1, current_file="part.3mf"))
    started = {r.machine_no: r.id for r in runs(env)}
    assert set(started) == {17, 18}
    assert len({r.device_job_key for r in runs(env)}) == 2
    env[4][0] += timedelta(seconds=5)
    for number, ref in refs.items():
        post(env, "/events", event(env, ref, 3, "STALE", current_file="part.3mf"))
        assert not next(r for r in runs(env) if r.machine_no == number).print_end_at
        recovered = {**ref, "connection_session_id": f"reconnected-{number}"}
        post(env, "/sessions/start", {**recovered, "generation": 2})
        post(env, "/events", event(env, recovered, 1, "RUNNING", progress_percent=50, current_file="part.3mf"))
        finished = event(env, recovered, 2, "FINISH", progress_percent=100, current_file="part.3mf")
        post(env, "/events", finished)
        assert post(env, "/events", finished)["duplicate"]
        assert post(env, "/commands/claim", recovered)["commands"] == []
    completed = runs(env)
    assert {r.machine_no: r.id for r in completed} == started
    assert all(r.run_status == "succeeded" and r.print_end_at and r.auto_record for r in completed)
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 60
        moves = list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))
        assert len(moves) == 2
        assert all(float(m.delta_g) == -20 for m in moves)
        assert list(db.scalars(select(env[2].ThreeDPrintingPrinterCommand))) == []
    for number in (17, 18):
        result = env[0].get("/api/three-d-printing/collections/records", params={
            "factory_id": "huakang-a", "machine_no": number,
        })
        assert result.status_code == 200
        assert result.json()["total"] == 1


def test_sixteen_device_health_cannot_pass_after_eighteen_device_expansion(environment):
    from test_three_d_network_health import report

    env = environment
    expand(env, 16)
    network = importlib.import_module("app.services.three_d_network_health")
    payload = network.NetworkHealthReport.model_validate(report(machine_count=16))
    with env[1].SessionLocal() as db:
        network.store_network_health(db, payload)
        assert network.network_health_snapshot(db)["status"] == "healthy"
    expand(env, 18)
    with env[1].SessionLocal() as db:
        health = network.network_health_snapshot(db)
        assert health["status"] == "degraded"
        assert health["failed_machine_numbers"] == [17, 18]
