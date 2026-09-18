import importlib
import json
from datetime import timedelta

from sqlalchemy import select
from test_three_d_connector import PUBLIC
from test_three_d_connector import environment as environment_fixture
from test_three_d_connector import event, post, session

environment = environment_fixture


def runs(env):
    with env[1].SessionLocal() as db:
        return list(db.scalars(select(env[2].ThreeDPrintingProductionRecord)))


def seed_product(env, *, duplicate=False, name="part", material="PLA"):
    with env[1].SessionLocal() as db:
        for i in range(2 if duplicate else 1):
            db.add(
                env[2].ThreeDPrintingProduct(
                    id=f"product-{i}",
                    factory_id="huakang-a",
                    name=name,
                    material_name=material,
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


def test_state_sweep_settles_run_that_missed_its_terminal_event(environment, monkeypatch):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    record = runs(env)[0]
    assert record.print_end_at == ""
    # The FINISH frame never arrives; the device is later observed idle again.
    post(env, "/events", event(env, ref, 2, "IDLE"))
    assert runs(env)[0].print_end_at == ""
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    with env[1].SessionLocal() as db:
        result = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert result.settled == [record.id]
    settled = runs(env)[0]
    assert settled.print_end_at and settled.run_status == "unknown"
    flags = json.loads(settled.data_quality_flags_json)
    assert "completion_evidence_missing" in flags
    # Inventory stays consumed once: no double deduction, no reversal.
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80
    # A repeat sweep is a no-op rather than a second settlement.
    with env[1].SessionLocal() as db:
        again = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert again.settled == []


def test_state_sweep_records_success_when_finish_was_observed(environment, monkeypatch):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    post(env, "/events", event(env, ref, 2, "FINISH"))
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        assert record.run_status == "succeeded"
        record.run_status, record.print_end_at = "running", ""
        db.commit()
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    with env[1].SessionLocal() as db:
        result = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert result.settled == [record.id]
    settled = runs(env)[0]
    assert settled.run_status == "succeeded" and settled.print_end_at
    assert "closed_by_state_sweep" in json.loads(settled.data_quality_flags_json)


def test_state_sweep_closes_run_when_device_moved_to_another_job(environment, monkeypatch):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    first = runs(env)[0]
    post(env, "/events", event(env, ref, 2, device_job_key="job-2"))
    post(env, "/events", event(env, ref, 3, "FINISH", device_job_key="job-2"))
    by_id = {record.id: record for record in runs(env)}
    assert len(by_id) == 2
    assert by_id[first.id].print_end_at == "" and by_id[first.id].reconciliation_status == "pending"
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    with env[1].SessionLocal() as db:
        result = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert result.settled_for_other_job == [first.id]
    with env[1].SessionLocal() as db:
        closed = db.get(env[2].ThreeDPrintingProductionRecord, first.id)
        assert closed.print_end_at and closed.reconciliation_status == "pending"
        assert "device_job_changed_without_end" in json.loads(closed.data_quality_flags_json)
    # Inventory is still consumed exactly once for the only run that was created.
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80


def test_recording_is_gated_by_its_own_switch_not_by_connection_owner(environment, monkeypatch):
    env = environment
    seed_product(env)
    ref = session(env)
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")

    def set_connection(**values):
        with env[1].SessionLocal() as db:
            row = db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"])
            for key, value in values.items():
                setattr(row, key, value)
            db.commit()

    # A switch off never records and never settles, and explicit reconcile refuses.
    set_connection(record_reconcile_enabled=False, connection_owner=env[3].OBSERVER)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    assert runs(env) == []
    assert post(env, "/reconcile", ref) == {"reconciled": False, "reason": "observation_only"}
    with env[1].SessionLocal() as db:
        blocked = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert blocked.eligible == 0 and blocked.settled == []

    # Switched on for an observation-only connection: records work, control still does not.
    set_connection(record_reconcile_enabled=True, connection_owner=env[3].OBSERVER)
    post(env, "/events", event(env, ref, 2, current_file="part.3mf"))
    record = runs(env)[0]
    assert record.print_end_at == ""
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80
    response = env[0].post(
        PUBLIC + "/printers/" + ref["printer_id"] + "/commands",
        json={
            "factory_id": "huakang-a",
            "idempotency_key": "observer-control-1",
            "action": "pause",
            "reason": "isolated test",
        },
    )
    assert response.status_code == 409 and "只读接入" in response.text
    # The same observation-only connection settles a finished run from device state.
    post(env, "/events", event(env, ref, 3, "IDLE"))
    with env[1].SessionLocal() as db:
        settled = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert settled.settled == [record.id]
    assert runs(env)[0].print_end_at


def test_record_reconcile_since_blocks_retroactive_record_creation(environment, monkeypatch):
    """A rollout guard keeps history observed before the switch from being recorded."""
    env = environment
    seed_product(env)
    ref = session(env)
    service = env[3]
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"])
        row.connection_owner = service.OBSERVER
        db.commit()
    observed_now = env[4][0].isoformat()
    old = (env[4][0] - timedelta(days=1)).isoformat()
    monkeypatch.setattr(service.settings, "three_d_record_reconcile_since", observed_now)
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"])
        assert service.record_reconcile_allowed(row, env[4][0]) is True
        assert service.record_reconcile_allowed(row, env[4][0] - timedelta(days=1)) is False
        # An unset guard is the default and records normally.
        monkeypatch.setattr(service.settings, "three_d_record_reconcile_since", "")
        assert service.record_reconcile_allowed(row, env[4][0] - timedelta(days=1)) is True
    # The same guard is what the sweep and the event path consult.
    monkeypatch.setattr(service.settings, "three_d_record_reconcile_since", observed_now)
    post(env, "/events", event(env, ref, current_file="part.3mf", observed_at=observed_now))
    assert len(runs(env)) == 1 and runs(env)[0].print_start_at
    assert old < observed_now

    # A guard must never stop the sweep from completing a run it already created.
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    monkeypatch.setattr(service.settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    post(env, "/events", event(env, ref, 2, "IDLE", observed_at=observed_now))
    with env[1].SessionLocal() as db:
        settled = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert settled.settled == [runs(env)[0].id]
    assert runs(env)[0].print_end_at


def test_state_sweep_never_touches_readonly_observation_or_live_runs(environment, monkeypatch):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    record = runs(env)[0]
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_terminal_grace_seconds", 0)
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    # A switch turned off cannot settle anything, even while events keep arriving.
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"])
        row.record_reconcile_enabled = False
        db.commit()
    post(env, "/events", event(env, ref, 2, "IDLE"))
    with env[1].SessionLocal() as db:
        observed = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert observed.settled == [] and observed.eligible == 0
    with env[1].SessionLocal() as db:
        db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"]).record_reconcile_enabled = True
        db.commit()
    # A device that is still printing is never settled.
    post(env, "/events", event(env, ref, 3, "RUNNING"))
    with env[1].SessionLocal() as db:
        still_running = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert still_running.settled == []
    assert runs(env)[0].id == record.id and runs(env)[0].print_end_at == ""


def test_same_file_run_is_resumed_inside_the_reprint_window_only(environment, monkeypatch):
    env = environment
    seed_product(env)
    first = session(env)
    post(env, "/events", event(env, first, current_file="part.3mf"))
    post(env, "/events", event(env, first, 2, "FINISH"))
    original = runs(env)[0]
    assert original.inventory_consumed and original.print_end_at
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_same_file_window_seconds", 600)
    # A new device job for the identical file right after the finish is one run.
    post(env, "/events", event(env, first, 3, device_job_key="job-restart",
                               current_file="part.3mf"))
    after_restart = runs(env)
    assert len(after_restart) == 1
    resumed = after_restart[0]
    assert resumed.id == original.id
    assert resumed.device_job_key == original.device_job_key
    assert resumed.reconciliation_status == "pending"
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80
        movements = list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))
        assert len(movements) == 1
    # A later finish settles that same resumed run rather than opening a third.
    post(env, "/events", event(env, first, 4, "FINISH", device_job_key="job-restart",
                               current_file="part.3mf"))
    assert len(runs(env)) == 1 and runs(env)[0].run_status == "succeeded"
    # The identical file printed again beyond the window is a real second run.
    monkeypatch.setattr(env[3].settings, "three_d_reconciliation_same_file_window_seconds", -1)
    second = {"instance_id": first["instance_id"], "printer_id": first["printer_id"]}
    grant = post(env, "/leases/acquire", second)
    second.update(leader_lease_id=grant["leader_lease_id"],
                  connection_session_id="session-reprint")
    post(env, "/sessions/start", {**second, "generation": 2})
    post(env, "/events", event(env, second, 1, device_job_key="job-reprint",
                               current_file="part.3mf"))
    reprinted = runs(env)
    assert len(reprinted) == 2
    assert len({record.id for record in reprinted}) == 2


def test_boot_sweep_settles_open_run_without_a_quiet_window(environment):
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    # A device that ended while Nexus was down: the state is terminal but fresh, and
    # this process never observed the transition, so no state_since exists for it.
    post(env, "/events", event(env, ref, 2, "FINISH"))
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        record.print_end_at = ""
        record.run_status = "running"
        db.commit()
    sweep = importlib.import_module("app.services.three_d_run_reconciliation")
    # The periodic sweep refuses without a quiet window...
    with env[1].SessionLocal() as db:
        steady = sweep.sweep_open_runs(db, factory_id="huakang-a", now=env[4][0])
        db.commit()
    assert steady.settled == [] and steady.awaiting_evidence == []
    assert runs(env)[0].print_end_at == ""
    # ...while the boot/reconnect pass settles it from the pushed full status.
    with env[1].SessionLocal() as db:
        boot = sweep.sweep_open_runs(
            db,
            factory_id="huakang-a",
            now=env[4][0],
            actor="system:boot-sweep",
            ignore_state_since=True,
        )
        db.commit()
    assert boot.settled == [record.id]
    settled = runs(env)[0]
    assert settled.run_status == "succeeded" and settled.print_end_at
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 80


def test_missing_product_and_material_are_backfilled_from_later_telemetry(environment):
    env = environment
    # The product exists but the first frame carried no file name at all.
    seed_product(env, name="part")
    ref = session(env)
    post(env, "/events", event(env, ref, current_file=""))
    record = runs(env)[0]
    assert record.product_name == "待匹配产品"
    assert "product_match_required" in json.loads(record.data_quality_flags_json)
    # A later frame carries the file name and the device's live material.
    post(env, "/events", event(env, ref, 2, current_file="part.3mf", live_material="PETG 灰色"))
    filled = runs(env)[0]
    assert filled.id == record.id
    assert filled.product_id == "product-0" and filled.product_name == "part"
    assert float(filled.weight_g) == 10 and filled.quantity == 2
    assert "product_match_required" not in json.loads(filled.data_quality_flags_json)
    assert filled.material_name
    # Backfill records the missing facts only; it never posts inventory on its own, so
    # a run created before its material was known cannot double-consume stock.
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 100
        assert not list(db.scalars(select(env[2].ThreeDPrintingInventoryMovement)))


def test_open_run_from_an_earlier_day_is_settled_by_device_identity(environment):
    """Cross-midnight closure: settlement never depends on "today's" record.

    A physically verified backdated frame is rejected by the ingest staleness guard, so
    this uses the same shape the real cutover produces: a run that opened on an earlier
    business date is still open, and the device's terminal frame arrives later.
    """
    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    record = runs(env)[0]
    with env[1].SessionLocal() as db:
        stale = db.get(env[2].ThreeDPrintingProductionRecord, record.id)
        stale.business_date = "2026-09-16"
        db.commit()
    # The terminal frame carries no business date at all, so the run is located by its
    # device identity rather than by the current day.
    post(env, "/events", event(env, ref, 2, "FINISH"))
    closed = runs(env)[0]
    assert closed.id == record.id
    assert closed.run_status == "succeeded" and closed.print_end_at
    assert closed.business_date == "2026-09-16"


def test_device_live_material_fills_a_run_whose_product_has_no_material(environment):
    env = environment
    seed_product(env, material="")
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    record = runs(env)[0]
    assert record.product_id == "product-0" and not record.material_name
    # The device reports its loaded filament later (and independently of the product).
    post(env, "/events", event(env, ref, 2, current_file="part.3mf",
                               live_material="PETG 灰色"))
    filled = runs(env)[0]
    assert filled.material_name == "PETG 灰色"
    assert "material_source_device" in json.loads(filled.data_quality_flags_json)


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
