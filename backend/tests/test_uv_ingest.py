"""Synthetic B1 protocol/replay checks. No printer or production DB access."""
import importlib.util
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema
from uuid import uuid4

from app.db import Base, get_db
from app.api.uv_ingest import router
from app.models.uv_ingest import UvConnector, UvPrintEvent
from app.models.uv_printing import UvJob, UvMachine, UvReport
from app.models.uv_finance import UvInkSku, UvInkMovement
from app.services.uv_ingest import ingest_batch, provision

CONNECTOR = Path(__file__).resolve().parents[2] / "connectors/uv-printing/replay_connector.py"
spec = importlib.util.spec_from_file_location("uv_replay_connector", CONNECTOR)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


@pytest.fixture
def engine():
    url = os.getenv("UV_INGEST_TEST_DATABASE_URL")
    schema = None
    if url:
        base_engine = create_engine(url)
        assert base_engine.dialect.name == "postgresql" and base_engine.url.database.startswith("rr_uv_ingest")
        schema = "uv_ingest_test_" + uuid4().hex
        with base_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        engine = base_engine.execution_options(schema_translate_map={None: schema})
    else:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    tables = [t for t in Base.metadata.sorted_tables if t.name.startswith("uv_")]
    Base.metadata.create_all(engine, tables=tables)
    yield engine
    if schema:
        with base_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
    engine.dispose()


def seed(engine):
    with Session(engine) as db:
        db.add_all([UvMachine(id="DEMO-M01", factory_id="huakang-a", code="001", name="DEMO machine"), UvMachine(id="DEMO-M02", factory_id="huakang-a", code="002", name="DEMO other")])
        db.commit()
        connector, token = provision(db, "huakang-a", ["DEMO-M01"])
        connector_id = connector.id
        db.commit()
        return connector_id, token


@pytest.fixture
def token(engine):
    return seed(engine)[1]


def event(**changes):
    return {"source_event_id": "DEMO-E01", "generation": "DEMO-G01", "machine_id": "DEMO-M01", "source_job_id": "DEMO-J01", "seq": 1, "observed_at": "2026-09-13T01:00:00Z", "state": "completed", "completion_evidence": "explicit", "raw_task_name": "DEMO-0001", "raw_count": "10", "raw_unit": "unknown", **changes}


def ingest(engine, token, events):
    with Session(engine) as db:
        return ingest_batch(db, token, "huakang-a", events)["results"]


def test_t07_t08_stable_events_and_distinct_same_name_jobs(engine, token):
    results = ingest(engine, token, [event()] * 10 + [event(source_event_id="DEMO-E02", source_job_id="DEMO-J02", observed_at="2026-09-13T01:00:30Z")])
    assert [r["status"] for r in results] == ["accepted"] + ["duplicate"] * 9 + ["accepted"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvPrintEvent)) == 2
        assert db.scalar(select(func.count()).select_from(UvJob)) == 2


def test_conflict_immutable_and_partial_durable_ack(engine, token):
    results = ingest(engine, token, [event(), event(raw_count="11"), {"oops": 1}, event(source_event_id="DEMO-E02", source_job_id="DEMO-J02")])
    assert [r["status"] for r in results] == ["accepted", "rejected", "rejected", "accepted"]
    assert results[1]["code"] == 409
    with Session(engine) as db:
        assert db.scalar(select(UvPrintEvent).where(UvPrintEvent.source_event_id == "DEMO-E01")).payload["raw_count"] == "10"
        assert db.scalar(select(func.count()).select_from(UvJob)) == 2


def test_sequence_conflict_and_generation_identity(engine, token):
    results = ingest(engine, token, [event(), event(source_event_id="DEMO-same-seq"), event(generation="DEMO-G02")])
    assert [r["status"] for r in results] == ["accepted", "rejected", "accepted"]
    assert results[1]["code"] == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvJob)) == 2


def test_commit_failure_has_no_false_ack_and_replay_recovers(engine, token, monkeypatch):
    batch = [event(), event(source_event_id="DEMO-E02", source_job_id="DEMO-J02")]
    with Session(engine) as db:
        commit = db.commit
        commits = []
        def interrupted():
            commits.append(1)
            if len(commits) == 2:
                raise RuntimeError("DEMO second commit interrupted")
            commit()
        monkeypatch.setattr(db, "commit", interrupted)
        with pytest.raises(RuntimeError, match="interrupted"):
            ingest_batch(db, token, "huakang-a", batch)
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvPrintEvent)) == 1
    assert [r["status"] for r in ingest(engine, token, batch)] == ["duplicate", "accepted"]


def test_connector_revocation_and_no_machine_scope(engine, token):
    with Session(engine) as db:
        connector = db.scalar(select(UvConnector))
        connector.enabled = False
        db.commit()
    with pytest.raises(HTTPException) as error:
        ingest(engine, token, [event()])
    assert error.value.status_code == 401
    with Session(engine) as db:
        with pytest.raises(ValueError, match="至少一台"):
            provision(db, "huakang-a", [])
        db.rollback()


def test_t12_t13_t32_no_automatic_accounting(engine, token):
    ingest(engine, token, [event(completion_evidence="inferred", time_evidence="inferred", ink_total_ml="10")])
    with Session(engine) as db:
        job = db.scalar(select(UvJob))
        assert job.state == "uncertain"
        assert job.raw_unit == "unknown" and job.suggested_piece_qty is None
        assert job.raw_count == 10 and job.ink_total_ml == 10
        assert db.scalar(select(func.count()).select_from(UvReport)) == 0


def test_t32_telemetry_preserves_actual_inventory_and_issue_cost(engine, token):
    from app.services.uv_finance import create_sku, create_movement
    from app.services.uv_printing import lock
    with Session(engine) as db:
        lock(db, "huakang-a")
        sku = create_sku(db, "huakang-a", "DEMO-admin", {"supplier": "DEMO-supplier", "material": "hard", "color": "white", "package_ml": "500"})
        create_movement(db, "huakang-a", "DEMO-admin", {"sku_id": sku["id"], "kind": "opening", "quantity_ml": "1000", "unit_cost": "0.1", "currency": "HKD", "occurred_on": "2026-09-13", "purpose": "DEMO opening"})
        create_movement(db, "huakang-a", "DEMO-admin", {"sku_id": sku["id"], "kind": "issue_out", "quantity_ml": "100", "occurred_on": "2026-09-13", "machine_id": "DEMO-M01", "purpose": "DEMO issue"})
        db.commit()
        before = {r.id: (r.signed_ml, r.cost_value, r.balance_after_ml) for r in db.scalars(select(UvInkMovement))}
        balance = db.get(UvInkSku, sku["id"])
        assert (balance.available_ml, balance.stock_value) == (900, 90)
    ingest(engine, token, [event(ink_total_ml="10")] * 10)
    with Session(engine) as db:
        balance = db.get(UvInkSku, sku["id"])
        assert (balance.available_ml, balance.stock_value) == (900, 90)
        assert {r.id: (r.signed_ml, r.cost_value, r.balance_after_ml) for r in db.scalars(select(UvInkMovement))} == before
        assert db.scalar(select(UvJob)).ink_total_ml == 10


def test_older_events_preserve_current_job_and_machine(engine, token):
    ingest(engine, token, [event(source_event_id="DEMO-new", seq=5, runtime_status="idle", raw_count="20", observed_at="2026-09-13T02:00:00Z"), event(seq=1, state="running", runtime_status="printing")])
    with Session(engine) as db:
        job, machine = db.scalar(select(UvJob)), db.get(UvMachine, "DEMO-M01")
        assert job.state == "completed" and job.raw_count == 20
        assert machine.runtime_status == "idle"
        assert machine.last_heartbeat_at == "2026-09-13T02:00:00+00:00"
        assert db.scalar(select(func.count()).select_from(UvPrintEvent)) == 2


def test_heartbeat_does_not_create_job(engine, token):
    ingest(engine, token, [event(kind="heartbeat", source_job_id=None)])
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvJob)) == 0


def test_ingest_preserves_reconciled_quantity(engine, token):
    ingest(engine, token, [event()])
    with Session(engine) as db:
        job = db.scalar(select(UvJob))
        job.raw_unit, job.suggested_piece_qty = "board", 47
        db.commit()
    ingest(engine, token, [event(source_event_id="DEMO-next", seq=2)])
    with Session(engine) as db:
        job = db.scalar(select(UvJob))
        assert job.raw_unit == "board" and job.suggested_piece_qty == 47


@pytest.mark.parametrize("changes", [{"connector_id": "forged"}, {"machine_id": "DEMO-M02"}, {"machine_id": "MISSING"}, {"observed_at": "2026-09-13T01:00:00"}, {"raw_count": "-1"}, {"raw_count": "NaN"}, {"seq": True}, {"raw_unit": "meters"}])
def test_event_scope_and_validation(engine, token, changes):
    assert ingest(engine, token, [event(**changes)])[0]["status"] == "rejected"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvPrintEvent)) == 0


def test_credential_and_disabled_machine(engine, token):
    with pytest.raises(HTTPException) as error:
        ingest(engine, "invalid", [event()])
    assert error.value.status_code == 401
    with Session(engine) as db:
        machine = db.get(UvMachine, "DEMO-M01")
        machine.enabled = False
        db.commit()
    assert ingest(engine, token, [event()])[0]["code"] == 403


def test_api_requires_explicit_scope_and_independent_credential(engine, token, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, 'uv_printing_enabled', True)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    def database():
        with Session(engine) as db:
            yield db
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        endpoint = "/api/uv-printing/ingest/events"
        headers = {"Authorization": "Bearer " + token}
        assert client.post(endpoint, json={"events": [event()]}, headers=headers).status_code == 422
        assert client.post(endpoint, json={"factory_id": "huakang-b", "events": [event()]}, headers=headers).status_code == 403
        assert client.post(endpoint, json={"factory_id": "huakang-a", "events": [event()]}).status_code == 401
        assert client.post(endpoint, json={"factory_id": "huakang-a", "connector_id": "spoof", "events": [event()]}, headers=headers).status_code == 422
        assert client.post(endpoint, json={"factory_id": "huakang-a", "events": [event()]}, headers=headers).json()["results"][0]["status"] == "accepted"
        monkeypatch.setattr(settings, 'uv_printing_enabled', False)
        assert client.post(endpoint, json={"factory_id": "huakang-a", "events": [event()]}, headers=headers).status_code == 503


def test_telemetry_delta_replay_and_mixed_modes(engine, token):
    first = event(ink_total_ml="10", ink_measurement="delta")
    ingest(engine, token, [first, first, event(source_event_id="DEMO-E02", seq=2, ink_total_ml="5", ink_measurement="delta")])
    with Session(engine) as db:
        assert db.scalar(select(UvJob)).ink_total_ml == 15
    ingest(engine, token, [event(source_event_id="DEMO-E03", seq=3, ink_total_ml="20", ink_measurement="cumulative")])
    with Session(engine) as db:
        assert db.scalar(select(UvJob)).ink_total_ml is None


def file_record(**changes):
    return {k: v for k, v in event(**changes).items() if k not in ("source_event_id", "generation", "machine_id")}


def test_t11_queue_restart_network_failure_lost_ack(engine, token, tmp_path):
    source, path = tmp_path / "DEMO.jsonl", tmp_path / "queue.sqlite"
    source.write_text(json.dumps(file_record()) + "\n", encoding="utf8")
    queue = replay.Queue(path)
    assert queue.read_file(source, "DEMO-G01", "DEMO-M01") == 1
    original = queue.pending()[0]
    with pytest.raises(ValueError, match="different machine"):
        queue.read_file(source, "DEMO-G01", "DEMO-M02")
    queue.close()
    queue = replay.Queue(path)
    assert queue.read_file(source, "DEMO-G01", "DEMO-M01") == 0
    assert queue.pending()[0] == original
    def lost_ack(url, body, key):
        payload = json.loads(body)
        ingest(engine, key, payload["events"])
        raise TimeoutError("DEMO ACK lost")
    with pytest.raises(TimeoutError):
        queue.flush("https://example.invalid/api/uv-printing/ingest/events", token, sender=lost_ack)
    assert len(queue.pending()) == 1
    def sender(url, body, key):
        payload = json.loads(body)
        return {"factory_id": "huakang-a", "results": ingest(engine, key, payload["events"])}
    result = queue.flush("https://example.invalid/api/uv-printing/ingest/events", token, sender=sender)
    assert result["removed"] == 1 and result["results"][0]["status"] == "duplicate"
    assert queue.pending() == []
    queue.close()


def test_queue_partial_line_rotation_and_ack_identity(tmp_path):
    source = tmp_path / "DEMO.jsonl"
    line = json.dumps(file_record())
    source.write_text(line, encoding="utf8")
    queue = replay.Queue(tmp_path / "queue.sqlite")
    assert queue.read_file(source, "DEMO-G01", "DEMO-M01") == 0
    source.write_text(line + "\n", encoding="utf8")
    assert queue.read_file(source, "DEMO-G01", "DEMO-M01") == 1
    original = queue.pending()[0]
    bad = {"index": 0, "generation": "DEMO-G01", "source_event_id": "OTHER", "status": "accepted", "receipt_id": "receipt"}
    with pytest.raises(ValueError):
        queue.flush("https://example.invalid/ingest", "DEMO-token", sender=lambda *a: {"factory_id": "huakang-a", "results": [bad]})
    assert queue.pending() == [original]
    source.write_text(json.dumps(file_record(raw_count="11")) + "\n", encoding="utf8")
    with pytest.raises(ValueError, match="rewritten"):
        queue.read_file(source, "DEMO-G01", "DEMO-M01")
    assert queue.read_file(source, "DEMO-G02", "DEMO-M01") == 1
    queue.close()


def test_queue_rejected_retained_and_no_http(tmp_path):
    queue = replay.Queue(tmp_path / "queue.sqlite")
    with pytest.raises(ValueError, match="HTTPS"):
        queue.flush("http://127.0.0.1/ingest", "DEMO-token")
    source = tmp_path / "DEMO.jsonl"
    source.write_text(json.dumps(file_record()) + "\n", encoding="utf8")
    queue.read_file(source, "DEMO-G01", "DEMO-M01")
    e = queue.pending()[0]
    ack = {"index": 0, "generation": e["generation"], "source_event_id": e["source_event_id"], "status": "rejected", "code": 422}
    assert queue.flush("https://example.invalid/ingest", "DEMO-token", sender=lambda *a: {"factory_id": "huakang-a", "results": [ack]})["removed"] == 0
    assert len(queue.pending()) == 1
    queue.close()


def test_postgres_concurrent_replay():
    url = os.getenv("UV_INGEST_TEST_DATABASE_URL")
    if not url:
        pytest.skip("Explicit isolated PostgreSQL URL required")
    engine = create_engine(url)
    assert engine.dialect.name == "postgresql" and engine.url.database.startswith("rr_uv_ingest")
    tables = [t for t in Base.metadata.sorted_tables if t.name.startswith("uv_")]
    Base.metadata.drop_all(engine, tables=tables)
    Base.metadata.create_all(engine, tables=tables)
    _, token = seed(engine)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda _: ingest(engine, token, [event()])[0]["status"], range(10)))
    assert results.count("accepted") == 1 and results.count("duplicate") == 9
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(UvJob)) == 1
        assert db.scalar(select(func.count()).select_from(UvPrintEvent)) == 1
    engine.dispose()
