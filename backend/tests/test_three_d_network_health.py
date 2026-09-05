import importlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from test_three_d_printing_api import (
    ADMIN_TEST_PASSWORD,
    EDGE_TOKEN,
    login,
    make_client,
)

BASE = "/api/three-d-printing"
TOKEN = "pr05-isolated-network-collector-token"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("THREE_D_NETWORK_HEALTH_TOKEN", TOKEN)
    with make_client(monkeypatch) as client:
        login(client, "admin", ADMIN_TEST_PASSWORD)
        dbm = importlib.import_module("app.db")
        models = importlib.import_module("app.models.three_d_printing")
        with dbm.SessionLocal() as db:
            db.add(
                models.ThreeDPrintingSite(
                    id="3dsite-huakang-a-heyuan",
                    factory_id="huakang-a",
                    site_code="heyuan",
                    name="Test Heyuan",
                    timezone="Asia/Shanghai",
                    enabled=True,
                )
            )
            db.commit()
        yield client


def report(**changes):
    return {
        "factory_id": "huakang-a",
        "site_id": "3dsite-huakang-a-heyuan",
        "gateway_key": "huakang-a-heyuan-vpn-a",
        "vpn_type": "wireguard",
        "observed_at": datetime.now(UTC).isoformat(),
        "tunnel": "ok",
        "exposure": "ok",
        "printers": [
            {
                "machine_no": n,
                "route": "ok",
                "tcp": "ok",
                "tls": "ok",
                "mqtt": "ok",
                "latency_ms": 1,
            }
            for n in range(1, 12)
        ],
        **changes,
    }


def publish(client, value):
    return client.post(
        BASE + "/network/health", json=value, headers={"X-Three-D-Network-Token": TOKEN}
    )


def dashboard(client):
    response = client.get(BASE + "/dashboard", params={"factory_id": "huakang-a"})
    assert response.status_code == 200, response.text
    return response.json()


def edge(client, state, connected=True):
    response = client.post(
        BASE + "/edge/status",
        headers={"X-Edge-Token": EDGE_TOKEN},
        json={
            "factory_id": "huakang-a",
            "agent_key": "pr05-test-edge",
            "statuses": [
                {
                    "machine_no": 1,
                    "connected": connected,
                    "state": state,
                    "current_file": "test-print.gcode",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text


def register(client):
    response = client.post(
        BASE + "/edge/heartbeat",
        headers={"X-Edge-Token": EDGE_TOKEN},
        json={
            "factory_id": "huakang-a",
            "agent_key": "pr05-test-edge",
            "name": "Test Edge",
            "version": "test",
            "host_fingerprint": "test",
            "capabilities": ["status"],
        },
    )
    assert response.status_code == 200, response.text


def test_collector_auth_scope_order_and_duplicate_reports(client):
    value = report()
    assert client.post(BASE + "/network/health", json=value).status_code == 401
    assert publish(client, {**value, "factory_id": "huaxing"}).status_code == 422
    assert (
        publish(client, {**value, "access_code": "test-access-code"}).status_code
        == 422
    )
    assert (
        publish(client, {**value, "printers": value["printers"][:-1]}).status_code
        == 422
    )
    result = publish(client, value)
    assert result.status_code == 200 and result.json()["status"] == "healthy", (
        result.text
    )
    assert publish(client, value).status_code == 200
    assert publish(client, {**value, "tunnel": "failed"}).status_code == 409
    assert (
        publish(
            client,
            {
                **value,
                "observed_at": (datetime.now(UTC) - timedelta(minutes=10)).isoformat(),
            },
        ).status_code
        == 409
    )
    assert (
        publish(
            client,
            {
                **value,
                "observed_at": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
            },
        ).status_code
        == 409
    )
    assert (
        client.get(
            BASE + "/network/health", params={"factory_id": "huaxing"}
        ).status_code
        == 400
    )
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.three_d_printing")
    from sqlalchemy import select

    with dbm.SessionLocal() as db:
        events = list(
            db.scalars(
                select(models.ThreeDPrintingAuditEvent).where(
                    models.ThreeDPrintingAuditEvent.entity_type == "network_health"
                )
            )
        )
        assert len(events) == 1


def test_tunnel_outage_blocks_commands_keeps_open_job_and_ui_stale(client):
    register(client)
    edge(client, "RUNNING")
    initial = dashboard(client)
    row = initial["records"][0]
    printer = initial["printers"][0]
    command_data = {
        "factory_id": "huakang-a",
        "action": "pause",
        "reason": "isolated test",
        "idempotency_key": "pr05-pause",
    }
    assert (
        client.post(
            BASE + "/printers/" + printer["id"] + "/commands", json=command_data
        ).status_code
        == 202
    )
    assert publish(client, report(tunnel="failed")).status_code == 200
    edge(client, "UNKNOWN")
    edge(client, "IDLE")  # Untrusted terminal-looking update during known site outage.
    state = dashboard(client)
    assert state["network_health"]["status"] == "unreachable"
    assert state["printers"][0]["state"] == "STALE"
    assert (
        not state["printers"][0]["connected"] and state["printers"][0]["status_stale"]
    )
    assert (
        state["records"][0]["id"] == row["id"]
        and state["records"][0]["print_end_at"] == ""
    )
    assert (
        client.post(
            BASE + "/printers/" + printer["id"] + "/commands",
            json={**command_data, "idempotency_key": "new-outage-command"},
        ).status_code
        == 409
    )
    claims = client.post(
        BASE + "/edge/commands/claim",
        headers={"X-Edge-Token": EDGE_TOKEN},
        json={"factory_id": "huakang-a", "agent_key": "pr05-test-edge", "limit": 10},
    )
    assert claims.status_code == 200 and claims.json()["commands"] == []
    assert publish(client, report()).status_code == 200
    edge(client, "RUNNING")
    assert len(dashboard(client)["records"]) == 1


def test_missing_collector_report_expires_and_unknown_state_does_not_complete(client):
    register(client)
    edge(client, "RUNNING")
    edge(client, "UNKNOWN")
    assert dashboard(client)["records"][0]["print_end_at"] == ""
    assert publish(client, report()).status_code == 200
    dbm = importlib.import_module("app.db")
    models = importlib.import_module("app.models.three_d_printing")
    from sqlalchemy import select

    with dbm.SessionLocal() as db:
        event = db.scalar(
            select(models.ThreeDPrintingAuditEvent).where(
                models.ThreeDPrintingAuditEvent.entity_type == "network_health"
            )
        )
        data = json.loads(event.detail_json)
        data["observed_at"] = (datetime.now(UTC) - timedelta(seconds=91)).isoformat()
        event.detail_json = json.dumps(data)
        db.commit()
    state = dashboard(client)
    assert state["network_health"]["status"] == "stale"
    assert all(p["state"] == "STALE" for p in state["printers"])
    assert state["records"][0]["print_end_at"] == ""


def test_incomplete_exposure_or_probe_cannot_report_healthy(client):
    network_only = report(probe_level="network")
    for printer in network_only["printers"]:
        printer["mqtt"] = "skipped"
    result = publish(client, network_only)
    assert result.status_code == 200 and result.json()["status"] == "healthy"
    result = publish(client, report(exposure="unknown"))
    assert result.status_code == 200 and result.json()["status"] == "degraded"
    value = report()
    value["printers"][0].update(tls="failed", mqtt="skipped")
    result = publish(client, value)
    assert result.status_code == 200 and result.json()["failed_machine_numbers"] == [1]
    assert result.json()["status"] == "degraded"
    value = report()
    value["printers"][0].update(route="failed")
    assert publish(client, value).status_code == 422
