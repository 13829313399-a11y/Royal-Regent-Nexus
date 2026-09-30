"""Opt-in real PostgreSQL acceptance; each test uses an isolated disposable schema."""

import asyncio
import importlib
import os
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from test_three_d_connector import environment as environment_fixture

environment = environment_fixture


def test_postgres_hour_rollups_match_raw_boundaries(postgres, monkeypatch):
    from test_three_d_telemetry_rollups import compare
    env, engine, sessions, _ = postgres
    compare(env, engine, sessions, monkeypatch)


def test_postgres_event_during_rollup_refresh_cannot_lose_invalidation(postgres, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from threading import Event as Signal
    from test_three_d_telemetry_rollups import seed

    env, engine, sessions, _ = postgres
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    now = datetime(2026, 9, 29, 0, 59, tzinfo=UTC)
    seed(env, sessions, now)
    observed = now - timedelta(hours=21)
    bucket = rollups.stamp(rollups.hour(observed))
    with sessions() as db:
        rollups.invalidate(db, observed)
        db.commit()
    locked, inserted, release = Signal(), Signal(), Signal()
    original = rollups.scan
    def blocked_scan(*args, **kwargs):
        locked.set()
        assert release.wait(10)
        return original(*args, **kwargs)
    monkeypatch.setattr(rollups, "scan", blocked_scan)
    def ingest():
        with sessions() as db:
            db.add(env[2].ThreeDPrintingPrinterStateEvent(
                id="concurrent-rollup-frame", factory_id="huakang-a",
                printer_id=env[5][0], machine_no=1,
                connector_instance_id="rollup-ci", connection_session_id="concurrent-rollup",
                sequence=1, observed_at=rollups.stamp(observed), received_at=rollups.stamp(now),
                state="PAUSE", error_code="CONCURRENT",
            ))
            db.flush()
            inserted.set()
            rollups.invalidate(db, observed)
            db.commit()
    with ThreadPoolExecutor(2) as pool:
        refresh = pool.submit(rollups.cached_hour, engine, bucket)
        assert locked.wait(10)
        incoming = pool.submit(ingest)
        try:
            assert inserted.wait(10)
        finally:
            release.set()
        refresh.result(timeout=10)
        incoming.result(timeout=10)
    with sessions() as db:
        assert db.get(env[2].ThreeDPrintingTelemetryRollup, ("huakang-a", bucket)).dirty
    result = rollups.cached_hour(engine, bucket)
    assert result["1"]["failure_codes"]["CONCURRENT"] == 1


def test_postgres_analytics_matches_streaming_reference(postgres, monkeypatch):
    from datetime import UTC, datetime, timedelta
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import event as sql_event
    from sqlalchemy import inspect

    env, engine, sessions, _ = postgres
    efficiency = importlib.import_module("app.services.three_d_efficiency")
    now = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(efficiency, "business_now", lambda: now)
    # Includes batch boundaries, 120/121-second gaps, two printers, missing
    # temperatures, alarms, repeated errors and an excluded future frame.
    for factory in (env[1].SessionLocal, sessions):
        with factory() as db:
            db.add(env[2].ThreeDPrintingConnectorInstance(
                id="analytics-ci", factory_id="huakang-a", site_id=env[3].SITE,
                connector_key="cloud-connector", instance_id="analytics-ci",
                started_at=now.isoformat(), last_seen_at=now.isoformat(),
            ))
            db.flush()
            offsets = list(range(1100)) + [1219, 1340, 1460, 8000]
            for machine_no in (1, 2):
                for i, offset in enumerate(offsets):
                    timestamp = now - timedelta(seconds=7200 - offset)
                    db.add(env[2].ThreeDPrintingPrinterStateEvent(
                        id=f"analytics-{machine_no}-{i}", factory_id="huakang-a",
                        printer_id=env[5][machine_no - 1], machine_no=machine_no,
                        connector_instance_id="analytics-ci", connection_session_id="analytics",
                        sequence=i, observed_at=timestamp.isoformat(), received_at=timestamp.isoformat(),
                        state=["PAUSE", "IDLE", "RUNNING"][i % 3],
                        error_code="E1" if i % 4 == 0 else "0",
                        temperatures_json='{"nozzle":350}' if i % 5 == 0 else '{}',
                        raw_payload_json='{"large":"' + "x" * 8000 + '"}',
                    ))
            db.commit()
    migration_path = Path(__file__).parents[1] / "alembic/versions/20260929_0129_three_d_analytics_index.py"
    spec = importlib.util.spec_from_file_location("analytics_index_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    # Exercise populated SQLite and PostgreSQL upgrades/rollbacks, including
    # PostgreSQL's concurrent DDL outside the migration transaction.
    for target in (env[1].engine, engine):
        with target.connect() as connection:
            context = MigrationContext.configure(connection)
            with context.begin_transaction(), Operations.context(context):
                migration.downgrade()
                migration.upgrade()
        indexes = inspect(target).get_indexes("three_d_printing_printer_state_events")
        index = next(i for i in indexes if i["name"] == migration.INDEX)
        assert index["column_names"][:3] == ["factory_id", "machine_no", "observed_at"]
        if target.dialect.name == "postgresql":
            assert index["include_columns"] == ["state", "error_code", "temperatures_json"]
    statements = []
    def inspect_query(_conn, cursor, statement, _params, context, _many):
        if "FROM three_d_printing_printer_state_events" in statement:
            assert not getattr(cursor, "name", None)
            assert "raw_payload_json" not in statement
            assert "GROUP BY" in statement
            statements.append(statement)
    sql_event.listen(engine, "after_cursor_execute", inspect_query)
    try:
        with sessions() as db:
            actual = efficiency.counters(db, 1)
    finally:
        sql_event.remove(engine, "after_cursor_execute", inspect_query)
    with env[1].SessionLocal() as db:
        expected = efficiency.counters(db, 1)
    assert statements and actual == expected


@pytest.fixture
def postgres(environment, monkeypatch):
    value = os.environ.get("THREE_D_TEST_POSTGRES_URL")
    if not value:
        pytest.skip("set THREE_D_TEST_POSTGRES_URL for isolated PostgreSQL acceptance")
    url = make_url(value)
    assert url.get_backend_name() == "postgresql" and url.host in {
        "127.0.0.1",
        "localhost",
    }
    assert url.database == "pr06_test", (
        "only explicitly named disposable test database permitted"
    )
    schema = "pr06_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    env = environment
    monkeypatch.setattr(
        env[3], "database_now", lambda db: db.scalar(select(func.clock_timestamp()))
    )
    tables = [
        t
        for t in env[1].Base.metadata.sorted_tables
        if t.name.startswith("three_d_printing_")
    ]
    env[1].Base.metadata.create_all(engine, tables=tables)
    with env[1].engine.connect() as source, engine.begin() as target:
        for table in tables:
            rows = [dict(row) for row in source.execute(select(table)).mappings()]
            if rows:
                target.execute(table.insert(), rows)
    try:
        yield (
            env,
            engine,
            sessionmaker(engine),
            url.set(query={**url.query, "options": f"-csearch_path={schema}"}),
        )
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def test_real_postgres_competing_leaders_claim_dispatch_and_skip_locked(postgres):
    env, _engine, sessions, _ = postgres
    service = env[3]
    schema = importlib.import_module("app.schemas.three_d_connector")

    def call(method, payload):
        with sessions() as db:
            return getattr(service, method)(db, payload)

    for name in ("pg-a", "pg-b"):
        call("heartbeat", schema.Heartbeat(instance_id=name, version="test"))
    requests = [
        schema.LeaseRequest(instance_id=name, printer_id=env[5][0])
        for name in ("pg-a", "pg-b")
    ]
    with ThreadPoolExecutor(2) as pool:
        grants = list(pool.map(lambda body: call("acquire", body), requests))
    assert sum(g["acquired"] for g in grants) == 1
    index = next(i for i, g in enumerate(grants) if g["acquired"])
    ref = {
        **requests[index].model_dump(),
        "leader_lease_id": grants[index]["leader_lease_id"],
        "connection_session_id": "pg-session",
    }
    call("start_session", schema.SessionStart(**ref, generation=1))
    call(
        "store_event",
        schema.StateEvent(
            **ref,
            event_id="pg-event",
            sequence=1,
            observed_at=env[4][0],
            connected=True,
            state="RUNNING",
            device_job_key="pg-job",
        ),
    )
    public = importlib.import_module("app.schemas.three_d_printing")
    with sessions() as db:
        command = service.create_command(
            db,
            printer_id=env[5][0],
            payload=public.ThreeDPrinterCommandCreate(
                factory_id="huakang-a",
                action="pause",
                reason="test",
                idempotency_key="pg-command",
            ),
            user=SimpleNamespace(id="pg-user", display_name="Postgres test"),
        )
        command_id = command.id
    # Verify actual SKIP LOCKED behavior while an independent transaction owns the row.
    with sessions() as locker, sessions() as contender:
        locker.scalar(
            select(env[2].ThreeDPrintingPrinterCommand)
            .where(env[2].ThreeDPrintingPrinterCommand.id == command_id)
            .with_for_update()
        )
        assert list(contender.scalars(service.claim_statement(env[5][0]))) == []
    with ThreadPoolExecutor(2) as pool:
        claims = list(
            pool.map(
                lambda _: call("claim_command", schema.SessionRef(**ref)), range(2)
            )
        )
    assert (
        claims[0]["commands"][0]["command_lease_id"]
        == claims[1]["commands"][0]["command_lease_id"]
    )
    command_ref = schema.CommandRef(
        **ref,
        command_id=command_id,
        command_lease_id=claims[0]["commands"][0]["command_lease_id"],
    )
    with ThreadPoolExecutor(2) as pool:
        results = list(
            pool.map(lambda _: call("dispatch_command", command_ref), range(2))
        )
    assert sum(result["send_permitted"] for result in results) == 1


def test_real_postgres_notify_commit_rollback_and_subscriber_fanout(
    postgres, monkeypatch
):
    env, _, sessions, url = postgres
    live = importlib.import_module("app.services.three_d_live")
    monkeypatch.setattr(
        live.settings, "database_url", url.render_as_string(hide_password=False)
    )

    async def check():
        hub = live.LiveHub()
        a, b = hub.subscribe(), hub.subscribe()
        hub.start()
        try:
            # Listener announces readiness only after LISTEN is effective.
            await asyncio.wait_for(a.get(), 5)
            await asyncio.wait_for(b.get(), 5)
            with sessions() as db:
                env[3].notify(db, "printer_state", "rolled-back")
                db.rollback()
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(a.get(), 0.3)
            with sessions() as db:
                env[3].notify(db, "printer_state", "committed")
                db.commit()
            await asyncio.wait_for(a.get(), 3)
            await asyncio.wait_for(b.get(), 3)
        finally:
            await hub.stop()

    asyncio.run(check())
