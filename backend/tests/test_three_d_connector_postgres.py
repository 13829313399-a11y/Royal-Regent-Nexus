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
