import importlib
import json

from sqlalchemy import select
from test_three_d_connector import environment as environment_fixture
from test_three_d_connector import event, post, session

environment = environment_fixture


def runs(env):
    with env[1].SessionLocal() as db:
        return list(db.scalars(select(env[2].ThreeDPrintingProductionRecord)))


def seed_product(env, *, duplicate=False):
    with env[1].SessionLocal() as db:
        for i in range(2 if duplicate else 1):
            db.add(
                env[2].ThreeDPrintingProduct(
                    id=f"product-{i}",
                    factory_id="huakang-a",
                    name="part",
                    material_name="PLA",
                    weight_g=10,
                    default_quantity=2,
                    is_active=True,
                    created_at="2026-09-04",
                    updated_at="2026-09-04",
                )
            )
        db.add(
            env[2].ThreeDPrintingInventory(
                id="stock",
                factory_id="huakang-a",
                material_name="PLA",
                stock_g=100,
                created_at="2026-09-04",
                updated_at="2026-09-04",
            )
        )
        db.commit()


def test_reconnect_reconcile_does_not_reconsume_and_terminal_is_immutable(environment):
    env = environment
    seed_product(env)
    ref = session(env)
    start = event(env, ref, current_file="part.3mf")
    post(env, "/events", start)
    post(env, "/events", start)
    post(env, "/events", event(env, ref, 2, "STALE"))
    assert runs(env)[0].run_status == "unknown"
    ref = {**ref, "connection_session_id": "reconnected"}
    post(env, "/sessions/start", {**ref, "generation": 2})
    post(env, "/events", event(env, ref, 1, current_file="part.3mf"))
    post(env, "/reconcile", ref)
    post(env, "/events", event(env, ref, 2, "PAUSE"))
    assert runs(env)[0].run_status == "paused"
    post(env, "/events", event(env, ref, 3, "IDLE"))
    assert runs(env)[0].print_end_at == ""
    post(env, "/events", event(env, ref, 4, "FINISH"))
    finished = runs(env)[0]
    assert finished.run_status == "succeeded" and finished.print_end_at
    post(env, "/events", event(env, ref, 5, "RUNNING"))
    assert len(runs(env)) == 1 and runs(env)[0].print_end_at == finished.print_end_at
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80
        movements = list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))
        assert len(movements) == 1 and float(movements[0].delta_g) == -20


def test_job_changed_missing_identity_and_duplicate_names_remain_pending(environment):
    env = environment
    seed_product(env, duplicate=True)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    record = runs(env)[0]
    assert not record.product_id and "product_match_required" in json.loads(
        record.data_quality_flags_json
    )
    post(env, "/events", event(env, ref, 2, device_job_key="job-2"))
    records = runs(env)
    assert len(records) == 2
    old = next(r for r in records if r.id == record.id)
    assert not old.print_end_at and old.reconciliation_status == "pending"
    post(env, "/events", event(env, ref, 3, device_job_key=""))
    assert len(runs(env)) == 2
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 100


def test_printer_namespaced_identity_and_legacy_open_run_not_blindly_bound(environment):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    other = {"instance_id": ref["instance_id"], "printer_id": env[5][1]}
    grant = post(env, "/leases/acquire", other)
    other.update(
        leader_lease_id=grant["leader_lease_id"], connection_session_id="other-printer"
    )
    post(env, "/sessions/start", {**other, "generation": 1})
    post(env, "/events", event(env, other))
    assert len(runs(env)) == 2
    assert len({record.device_job_key for record in runs(env)}) == 2
    with env[1].SessionLocal() as db:
        old = db.scalar(
            select(env[2].ThreeDPrintingProductionRecord).where(
                env[2].ThreeDPrintingProductionRecord.machine_no == 2
            )
        )
        old.device_job_key = None
        old.source_system = "legacy"
        db.commit()
    post(env, "/events", event(env, other, 2, "FINISH"))
    old = next(r for r in runs(env) if r.machine_no == 2)
    assert not old.print_end_at and old.reconciliation_status == "pending"


def test_live_snapshot_scope_redaction_cursor_and_revoke(environment):
    import asyncio

    from starlette.requests import Request

    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    live = importlib.import_module("app.services.three_d_live")
    cookie = "; ".join(f"{k}={v}" for k, v in env[0].cookies.items())

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/three-d-printing/live/events",
            "headers": [(b"cookie", cookie.encode())],
            "query_string": b"",
        },
        receive=receive,
    )
    initial = live.snapshot(request, "huakang-a")
    assert (
        "credential_ref" not in initial[1]
        and "leader_lease_id" not in initial[1]
        and "10.33.30." not in initial[1]
    )
    assert (
        env[0].get("/api/three-d-printing/live/events?factory_id=huaxing").status_code
        == 400
    )

    async def check():
        stream = live.events(request, "huakang-a", initial, "old-cursor")
        first = await anext(stream)
        assert "event: reset" in first and initial[0] in first
        assert len(live.hub.subscribers) == 1
        for _ in range(100):
            live.hub.publish()
        assert next(iter(live.hub.subscribers)).qsize() == 1
        assert env[0].post("/api/auth/logout").status_code == 204
        revoked = await asyncio.wait_for(anext(stream), 2)
        assert "event: access_revoked" in revoked and "401" in revoked
        await stream.aclose()
        assert not live.hub.subscribers

    asyncio.run(check())
