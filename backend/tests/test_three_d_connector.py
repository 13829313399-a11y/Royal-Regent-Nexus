import importlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from test_three_d_printing_api import (
    ADMIN_TEST_PASSWORD,
    EDGE_TOKEN,
    login,
    make_client,
)

BASE = "/api/internal/three-d-connector"
TOKEN = "isolated-connector-token-not-for-production"
PUBLIC = "/api/three-d-printing"


@pytest.fixture
def environment(monkeypatch):
    monkeypatch.setenv("THREE_D_CONNECTOR_ENABLED", "true")
    monkeypatch.setenv("THREE_D_CONNECTOR_TOKEN", TOKEN)
    monkeypatch.setenv("THREE_D_CONNECTOR_CONTROL_ENABLED", "true")
    monkeypatch.setenv("THREE_D_CONNECTOR_VERIFIED_MACHINES", "[1,2]")
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        dbm = importlib.import_module("app.db")
        models = importlib.import_module("app.models.three_d_printing")
        service = importlib.import_module("app.services.three_d_connector")
        network = importlib.import_module("app.services.three_d_network_health")
        clock = [datetime.now(UTC).replace(microsecond=0)]
        monkeypatch.setattr(service, "database_now", lambda _db: clock[0])
        with dbm.SessionLocal() as db:
            db.add(
                models.ThreeDPrintingSite(
                    id=service.SITE,
                    factory_id="huakang-a",
                    site_code="heyuan",
                    name="Isolated site",
                    enabled=True,
                )
            )
            db.flush()
            printers = list(
                db.scalars(
                    select(models.ThreeDPrintingPrinter).order_by(
                        models.ThreeDPrintingPrinter.machine_no
                    )
                )
            )
            for printer in printers[:2]:
                db.add(
                    models.ThreeDPrintingPrinterConnection(
                        printer_id=printer.id,
                        factory_id="huakang-a",
                        site_id=service.SITE,
                        lan_host=f"10.33.30.{100 + printer.machine_no}",
                        mqtt_port=8883,
                        credential_ref=f"printer-{printer.machine_no:02d}",
                        certificate_fingerprint="a" * 64,
                        connection_enabled=True,
                        connection_owner=service.OWNER,
                        record_reconcile_enabled=True,
                    )
                )
            ids = [printer.id for printer in printers]
            db.commit()
            network.store_network_health(
                db,
                network.NetworkHealthReport.model_validate(
                    {
                        "factory_id": "huakang-a",
                        "site_id": service.SITE,
                        "gateway_key": "huakang-a-heyuan-vpn-test",
                        "vpn_type": "tailscale",
                        "observed_at": datetime.now(UTC),
                        "probe_level": "network",
                        "tunnel": "ok",
                        "exposure": "ok",
                        "printers": [
                            {
                                "machine_no": n,
                                "route": "ok",
                                "tcp": "ok",
                                "tls": "ok",
                                "mqtt": "skipped",
                            }
                            for n in range(1, 12)
                        ],
                    }
                ),
            )
        yield client, dbm, models, service, clock, ids


def post(env, path, data, expected=200):
    response = env[0].post(
        BASE + path, json=data, headers={"X-Three-D-Connector-Token": TOKEN}
    )
    assert response.status_code == expected, response.text
    return response.json()


def registered(env, instance="replica-a"):
    post(env, "/heartbeat", {"instance_id": instance, "version": "test"})
    return {"instance_id": instance, "printer_id": env[5][0]}


def session(env, instance="replica-a", session_id="session-a", generation=1):
    base = registered(env, instance)
    grant = post(env, "/leases/acquire", base)
    assert grant["acquired"]
    ref = {
        **base,
        "leader_lease_id": grant["leader_lease_id"],
        "connection_session_id": session_id,
    }
    post(env, "/sessions/start", {**ref, "generation": generation})
    return ref


def event(env, ref, sequence=1, state="RUNNING", **overrides):
    return {
        **ref,
        "event_id": f"event-{ref['connection_session_id']}-{sequence}",
        "sequence": sequence,
        "observed_at": env[4][0].isoformat(),
        "state": state,
        "connected": state != "STALE",
        "device_job_key": "job-1",
        "current_file": "isolated.3mf",
        **overrides,
    }


def request_command(
    env, key="command-idempotency-1", action="pause", printer_id=None, expected=202
):
    response = env[0].post(
        PUBLIC + "/printers/" + (printer_id or env[5][0]) + "/commands",
        json={
            "factory_id": "huakang-a",
            "idempotency_key": key,
            "action": action,
            "reason": "isolated test",
        },
    )
    assert response.status_code == expected, response.text
    return response.json()


def dispatch(env, ref, command):
    body = {
        **ref,
        "command_id": command["command_id"],
        "command_lease_id": command["command_lease_id"],
    }
    assert post(env, "/commands/dispatch", body)["send_permitted"]
    return body


def test_internal_gate_separate_auth_scope_and_no_auto_handoff(
    environment, monkeypatch
):
    env = environment
    data = {"instance_id": "replica-a", "version": "test"}
    assert env[0].post(BASE + "/heartbeat", json=data).status_code == 401
    assert (
        env[0]
        .post(BASE + "/heartbeat", json=data, headers={"X-Edge-Token": EDGE_TOKEN})
        .status_code
        == 401
    )
    post(env, "/heartbeat", {**data, "factory_id": "huaxing"}, 422)
    post(env, "/heartbeat", {**data, "access_code": "test-access-code"}, 422)
    base = registered(env)
    post(env, "/leases/acquire", {**base, "printer_id": env[5][2]}, 409)
    monkeypatch.setattr(env[3].settings, "three_d_connector_enabled", False)
    post(env, "/heartbeat", data, 503)


def test_two_replicas_only_one_lease_and_old_renew_rejected(environment):
    env = environment
    a, b = registered(env), registered(env, "replica-b")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda value: post(env, "/leases/acquire", value), [a, b])
        )
    assert sum(result["acquired"] for result in results) == 1
    index = 0 if results[0]["acquired"] else 1
    winner, loser = [a, b][index], [a, b][1 - index]
    lease = results[index]["leader_lease_id"]
    assert post(env, "/leases/acquire", winner)["leader_lease_id"] == lease
    env[4][0] += timedelta(seconds=31)
    new = post(env, "/leases/acquire", loser)
    assert new["acquired"] and new["leader_lease_id"] != lease
    post(env, "/leases/renew", {**winner, "leader_lease_id": lease}, 409)
    post(env, "/leases/release", {**winner, "leader_lease_id": lease}, 409)


def test_state_idempotence_order_session_generation_and_observation_time(environment):
    env = environment
    ref = session(env)
    first = event(env, ref)
    post(env, "/events", first)
    assert post(env, "/events", first)["duplicate"]
    post(env, "/events", {**first, "state": "FINISH"}, 409)
    post(env, "/events", {**first, "event_id": "different-id"}, 409)
    post(
        env,
        "/events",
        event(env, ref, 2, observed_at=(env[4][0] + timedelta(seconds=10)).isoformat()),
        409,
    )
    new = {**ref, "connection_session_id": "session-b"}
    post(env, "/sessions/start", {**new, "generation": 2})
    post(env, "/sessions/start", {**ref, "generation": 1}, 409)
    post(env, "/events", event(env, ref, 2), 409)
    post(env, "/events", event(env, new))
    stale = event(env, new, 2, "STALE")
    post(env, "/events", stale)
    with env[1].SessionLocal() as db:
        printer = db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"])
        assert printer.state == "STALE" and not printer.connected
        assert env[3].metadata(printer)["sequence"] == 2
        assert (
            db.scalar(select(func_count(env[2].ThreeDPrintingPrinterStateEvent))) == 3
        )
        assert db.scalar(select(func_count(env[2].ThreeDPrintingProductionRecord))) == 1
        run = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        assert run.print_end_at == "" and run.run_status == "unknown"
    post(env, "/events", event(env, new, 3, "FINISH", connected=False), 422)


def func_count(model):
    from sqlalchemy import func

    return func.count(model.id)


def test_observer_streams_state_without_creating_runs_or_commands(environment):
    from pathlib import Path
    import importlib.util

    env = environment
    spec = importlib.util.spec_from_file_location("observer_setup", Path(__file__).resolve().parents[2] / "deploy/three-d-printing/enable_observer.py")
    setup = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(setup)
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterConnection, env[5][0])
        row.connection_owner = "edge-legacy"
        row.connection_enabled = False
        db.commit()
        first = setup.enable(db, 1)
        db.commit()
        assert setup.enable(db, 1) == first
        assert row.connection_enabled and row.connection_owner == env[3].OBSERVER
        db.commit()
    ref = session(env)
    grant = post(env, "/leases/acquire", {k: ref[k] for k in ("instance_id", "printer_id")})
    assert grant["control_verified"] is False
    assert {"printer_id": ref["printer_id"]} in post(
        env, "/printers", {"instance_id": ref["instance_id"]}
    )["printers"]
    post(env, "/events", event(env, ref, progress_percent=42,
                               nozzle_target=255, bed_target=70, layer_num=84, total_layers=200))
    with env[1].SessionLocal() as db:
        printer = db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"])
        assert printer.connected and printer.state == "RUNNING"
        assert printer.progress_percent == 42
        output = importlib.import_module("app.services.three_d_printing").printer_out(printer)
        assert {key: output[key] for key in ("nozzle_target", "bed_target", "layer_num", "total_layers")} == {
            "nozzle_target": 255, "bed_target": 70, "layer_num": 84, "total_layers": 200,
        }
    request_command(env, expected=409)
    assert post(env, "/commands/claim", ref)["commands"] == []
    assert post(env, "/reconcile", ref) == {"reconciled": False, "reason": "observation_only"}
    post(env, "/events", event(env, ref, 2, "FINISH"))
    post(env, "/leases/release", {k: ref[k] for k in ("instance_id", "printer_id", "leader_lease_id")})
    with env[1].SessionLocal() as db:
        assert db.scalar(select(func_count(env[2].ThreeDPrintingProductionRecord))) == 0
        assert db.scalar(select(func_count(env[2].ThreeDPrintingPrinterCommand))) == 0
        assert db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"]).state == "STALE"


def test_observer_preserves_existing_run_and_cannot_dispatch_old_command(environment):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    request_command(env)
    command = post(env, "/commands/claim", ref)["commands"][0]
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        before = {c.name: getattr(record, c.name) for c in record.__table__.columns}
        row = db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"])
        row.connection_owner = env[3].OBSERVER
        # Observation mode does not record unless an operator turns its switch on.
        row.record_reconcile_enabled = False
        db.commit()
    post(env, "/commands/dispatch", {
        **ref, "command_id": command["command_id"], "command_lease_id": command["command_lease_id"]
    }, 409)
    post(env, "/events", event(env, ref, 2, "FINISH"))
    assert post(env, "/reconcile", ref)["reason"] == "observation_only"
    env[4][0] += timedelta(seconds=31)
    post(env, "/heartbeat", {"instance_id": ref["instance_id"], "version": "test"})
    with env[1].SessionLocal() as db:
        record = db.scalar(select(env[2].ThreeDPrintingProductionRecord))
        assert {c.name: getattr(record, c.name) for c in record.__table__.columns} == before
        assert db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"]).state == "STALE"


@pytest.mark.parametrize("network_status", ["degraded", "stale", "unreachable", "unconfigured"])
def test_observer_recovers_independently_of_site_probe(environment, monkeypatch, network_status):
    env = environment
    network = importlib.import_module("app.services.three_d_network_health")
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterConnection, env[5][0])
        row.connection_owner = env[3].OBSERVER
        row.record_reconcile_enabled = False
        db.commit()
    unhealthy = lambda _db: {
        "configured": network_status != "unconfigured", "status": network_status,
        "observed_at": env[4][0].isoformat(), "failed_machine_numbers": [6],
        "message": "6号机探测失败",
    }
    monkeypatch.setattr(env[3], "network_health_snapshot", unhealthy)
    monkeypatch.setattr(network, "network_health_snapshot", unhealthy)
    # Recovery must work even when diagnostics never return to all-healthy.
    ref = session(env)
    post(env, "/events", event(env, ref))
    post(env, "/heartbeat", {"instance_id": ref["instance_id"], "version": "test"})
    assert post(env, "/commands/claim", ref)["commands"] == []
    request_command(env, expected=409)
    # The same outage still blocks a printer configured for hardware control.
    post(env, "/leases/acquire", {"instance_id": ref["instance_id"], "printer_id": env[5][1]}, 409)
    response = env[0].get(PUBLIC + "/dashboard?factory_id=huakang-a")
    assert response.status_code == 200, response.text
    printer = next(p for p in response.json()["printers"] if p["id"] == ref["printer_id"])
    assert printer["connected"] and printer["state"] == "RUNNING"
    with env[1].SessionLocal() as db:
        assert db.scalar(select(func_count(env[2].ThreeDPrintingProductionRecord))) == 0
    # Actual loss of device evidence remains offline; the fix is not a longer TTL.
    env[4][0] += timedelta(seconds=31)
    post(env, "/heartbeat", {"instance_id": ref["instance_id"], "version": "test"})
    with env[1].SessionLocal() as db:
        assert not db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"]).connected


def test_command_claim_dispatch_evidence_and_immutable_idempotent_result(environment):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    requested = request_command(env)
    assert request_command(env)["id"] == requested["id"]
    request_command(env, action="resume", expected=409)
    command = post(env, "/commands/claim", ref)["commands"][0]
    assert post(env, "/commands/claim", ref)["commands"][0] == command
    body = dispatch(env, ref, command)
    assert not post(env, "/commands/dispatch", body)["send_permitted"]
    early = {
        **body,
        "status": "succeeded",
        "reason": "state_evidence",
        "evidence_event_id": "event-session-a-1",
    }
    post(env, "/commands/ack", early, 409)
    state = event(env, ref, 2, "PAUSE")
    post(env, "/events", state)
    ack = {**early, "evidence_event_id": state["event_id"]}
    assert post(env, "/commands/ack", ack)["status"] == "succeeded"
    assert post(env, "/commands/ack", ack)["status"] == "succeeded"
    post(
        env,
        "/commands/ack",
        {**body, "status": "unknown", "reason": "send_uncertain"},
        409,
    )
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterCommand, command["command_id"])
        assert row.attempt_count == 1
        assert (
            json.loads(row.result_evidence_json)["ack"]["event_id"] == state["event_id"]
        )


def test_unsent_lease_reclaim_fences_old_ack_but_sent_command_never_retries(
    environment,
):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    request_command(env)
    old = post(env, "/commands/claim", ref)["commands"][0]
    env[4][0] += timedelta(seconds=9)
    current = post(env, "/commands/claim", ref)["commands"][0]
    assert (
        current["command_lease_id"] != old["command_lease_id"]
        and current["attempt_count"] == 2
    )
    oldbody = {
        **ref,
        "command_id": old["command_id"],
        "command_lease_id": old["command_lease_id"],
    }
    post(env, "/commands/dispatch", oldbody, 409)
    post(
        env,
        "/commands/ack",
        {**oldbody, "status": "unknown", "reason": "send_uncertain"},
        409,
    )
    body = dispatch(env, ref, current)
    env[4][0] += timedelta(seconds=9)
    assert post(env, "/commands/claim", ref)["commands"] == []
    assert not post(env, "/commands/dispatch", body)["send_permitted"]
    with env[1].SessionLocal() as db:
        row = db.get(env[2].ThreeDPrintingPrinterCommand, old["command_id"])
        assert row.status == "unknown" and row.attempt_count == 2


@pytest.mark.parametrize("mode", ["cloud-connector", "cloud-observer"])
def test_old_edge_cannot_overwrite_or_claim_cloud_owned_printer(environment, mode):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    request_command(env)
    with env[1].SessionLocal() as db:
        db.get(env[2].ThreeDPrintingPrinterConnection, ref["printer_id"]).connection_owner = mode
        db.commit()
    headers = {"X-Edge-Token": EDGE_TOKEN}
    response = env[0].post(
        PUBLIC + "/edge/heartbeat",
        headers=headers,
        json={
            "factory_id": "huakang-a",
            "agent_key": "old-edge",
            "name": "old edge",
            "capabilities": ["status"],
        },
    )
    assert response.status_code == 200, response.text
    response = env[0].post(
        PUBLIC + "/edge/status",
        headers=headers,
        json={
            "factory_id": "huakang-a",
            "agent_key": "old-edge",
            "statuses": [{"machine_no": 1, "state": "FINISH", "connected": True}],
        },
    )
    assert response.status_code == 200, response.text
    with env[1].SessionLocal() as db:
        assert (
            db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"]).state == "RUNNING"
        )
    response = env[0].post(
        PUBLIC + "/edge/commands/claim",
        headers=headers,
        json={"factory_id": "huakang-a", "agent_key": "old-edge", "limit": 10},
    )
    assert response.status_code == 200 and response.json()["commands"] == []


def test_network_loss_blocks_acquire_and_control_but_accepts_stale_evidence(
    environment,
):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    with env[1].SessionLocal() as db:
        row = db.scalar(
            select(env[2].ThreeDPrintingAuditEvent).where(
                env[2].ThreeDPrintingAuditEvent.entity_type == "network_health"
            )
        )
        report = json.loads(row.detail_json)
        report["tunnel"] = "failed"
        row.detail_json = json.dumps(report)
        db.commit()
    request_command(env, expected=409)
    post(env, "/commands/claim", ref, 409)
    post(env, "/events", event(env, ref, 2, "STALE"))
    post(
        env,
        "/leases/acquire",
        {"instance_id": ref["instance_id"], "printer_id": env[5][1]},
        409,
    )


def test_postgresql_claim_is_skip_locked(environment):
    statement = environment[3].claim_statement(environment[5][0])
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in sql and "LIMIT" in sql


def test_parallel_claim_retries_share_lease_but_dispatch_permission_is_once(
    environment,
):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    request_command(env)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: post(env, "/commands/claim", ref)["commands"][0], range(2)
            )
        )
    assert claims[0] == claims[1]
    body = {
        **ref,
        "command_id": claims[0]["command_id"],
        "command_lease_id": claims[0]["command_lease_id"],
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        permits = list(
            pool.map(lambda _: post(env, "/commands/dispatch", body), range(2))
        )
    assert sum(value["send_permitted"] for value in permits) == 1


def test_event_and_projection_rollback_together_and_retry_recovers(
    environment, monkeypatch
):
    env = environment
    ref = session(env)
    value = event(env, ref)
    original_notify = env[3].notify

    def unavailable(*_args):
        raise RuntimeError("isolated notification failure")

    monkeypatch.setattr(env[3], "notify", unavailable)
    with pytest.raises(RuntimeError, match="isolated notification"):
        env[0].post(
            BASE + "/events", json=value, headers={"X-Three-D-Connector-Token": TOKEN}
        )
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingPrinterStateEvent, value["event_id"]) is None
        printer = db.get(env[2].ThreeDPrintingPrinter, ref["printer_id"])
        assert env[3].metadata(printer)["sequence"] == 0 and printer.state == "STALE"
    monkeypatch.setattr(env[3], "notify", original_notify)
    post(env, "/events", value)


def test_state_change_expires_old_intent_without_blocking_new_command(environment):
    env = environment
    ref = session(env)
    post(env, "/events", event(env, ref))
    old = request_command(env)
    post(env, "/events", event(env, ref, 2, "PAUSE"))
    new = request_command(env, key="new-resume-command", action="resume")
    leased = post(env, "/commands/claim", ref)["commands"][0]
    assert leased["command_id"] == new["id"]
    with env[1].SessionLocal() as db:
        assert (
            db.get(env[2].ThreeDPrintingPrinterCommand, old["id"]).status == "expired"
        )
