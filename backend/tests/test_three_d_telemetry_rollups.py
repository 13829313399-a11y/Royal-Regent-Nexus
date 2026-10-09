import importlib
from datetime import UTC, datetime, timedelta
from sqlalchemy import event as sql_event

from test_three_d_connector import environment as environment_fixture, event, post, session

environment = environment_fixture


def seed(env, sessions, now):
    m = env[2]
    with sessions() as db:
        db.add(m.ThreeDPrintingConnectorInstance(
            id="rollup-ci", factory_id="huakang-a", site_id=env[3].SITE,
            connector_key="cloud-connector", instance_id="rollup-ci",
            started_at=now.isoformat(), last_seen_at=now.isoformat(),
        ))
        db.flush()
        # A rolling window, midnight/hour bridges, 120/121s gaps and a future row.
        begin = now - timedelta(days=1)
        offsets = [-1, 0, 1, 59, 60, 61, 3599, 3600, 3601, 7200, 7320, 7441,
                   82800, 82801, 86400, 86401]
        offsets += list(range(10000, 11200))
        for machine in (1, 2):
            for i, offset in enumerate(sorted(set(offsets))):
                timestamp = begin + timedelta(seconds=offset)
                db.add(m.ThreeDPrintingPrinterStateEvent(
                    id=f"r-{machine}-{i}", factory_id="huakang-a",
                    printer_id=env[5][machine-1], machine_no=machine,
                    connector_instance_id="rollup-ci", connection_session_id="rollup",
                    sequence=i, observed_at=timestamp.isoformat(timespec="milliseconds"),
                    received_at=now.isoformat(), state=["PAUSE", "IDLE", "RUNNING"][i % 3],
                    error_code="E1" if i % 5 == 0 else "0",
                    temperatures_json='{"nozzle":350}' if i % 7 == 0 else '{}',
                    raw_payload_json='{"large":"' + "x" * 8000 + '"}',
                ))
        db.commit()


def compare(env, engine, sessions, monkeypatch):
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    efficiency = importlib.import_module("app.services.three_d_efficiency")
    now = datetime(2026, 9, 29, 0, 59, 0, tzinfo=UTC)
    monkeypatch.setattr(efficiency, "business_now", lambda: now)
    seed(env, sessions, now)
    with sessions() as db:
        reference = efficiency.counters(db, 1)
    migration_path = Path(__file__).parents[1] / "alembic/versions/20260929_0130_three_d_telemetry_rollups.py"
    spec = importlib.util.spec_from_file_location("rollup_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        with context.begin_transaction(), Operations.context(context):
            migration.downgrade()
            migration.upgrade()
    assert rollups.initialize(engine, now=now) > 0
    assert rollups.initialize(engine, now=now) == 0
    queries = []

    def capture(_conn, cursor, statement, parameters, context, _many):
        if "FROM three_d_printing_printer_state_events" in statement:
            assert "raw_payload_json" not in statement
            assert context.execution_options.get("yield_per") == 500
            queries.append((statement, parameters))

    sql_event.listen(engine, "after_cursor_execute", capture)
    try:
        with sessions() as db:
            actual = efficiency.counters(db, 1)
        assert actual == reference
        # Only the two partial hours are read, with eleven indexed machine seeks.
        assert len(queries) == 22
        assert all("machine_no =" in sql for sql, _ in queries)
        # Exact hour boundary: exclude the interval arriving from outside the window.
        now += timedelta(minutes=1)
        monkeypatch.setattr(efficiency, "business_now", lambda: now)
        with sessions() as db:
            boundary = efficiency.counters(db, 1)
    finally:
        sql_event.remove(engine, "after_cursor_execute", capture)
    with sessions() as db:
        db.get(env[2].ThreeDPrintingTelemetryRollupState, "huakang-a").initialized_at = ""
        db.commit()
    with sessions() as db:
        expected = efficiency.counters(db, 1)
    assert boundary == expected


def test_late_event_rebuilds_only_its_hour_and_keeps_cross_hour_bridge(environment, monkeypatch):
    env = environment
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    efficiency = importlib.import_module("app.services.three_d_efficiency")
    now = datetime(2026, 9, 29, 0, 59, tzinfo=UTC)
    monkeypatch.setattr(efficiency, "business_now", lambda: now)
    seed(env, env[1].SessionLocal, now)
    rollups.initialize(env[1].engine, now=now)
    late = now - timedelta(hours=20, minutes=1)
    with env[1].SessionLocal() as db:
        db.add(env[2].ThreeDPrintingPrinterStateEvent(
            id="late-frame", factory_id="huakang-a", printer_id=env[5][0], machine_no=1,
            connector_instance_id="rollup-ci", connection_session_id="late", sequence=1,
            observed_at=rollups.stamp(late), received_at=rollups.stamp(now), state="PAUSE",
            error_code="LATE", temperatures_json='{"bed":150}',
        ))
        rollups.invalidate(db, late)
        db.commit()
    rebuilt = []
    original = rollups.cached_hour
    def observed(engine, bucket):
        rebuilt.append(bucket)
        return original(engine, bucket)
    monkeypatch.setattr(rollups, "cached_hour", observed)
    with env[1].SessionLocal() as db:
        actual = efficiency.counters(db, 1)
    assert rebuilt == [rollups.stamp(rollups.hour(late))]
    with env[1].SessionLocal() as db:
        db.get(env[2].ThreeDPrintingTelemetryRollupState, "huakang-a").initialized_at = ""
        db.commit()
    with env[1].SessionLocal() as db:
        assert actual == efficiency.counters(db, 1)


def test_hour_rollups_match_raw_boundaries_and_read_only_partial_hours(environment, monkeypatch):
    env = environment
    compare(env, env[1].engine, env[1].SessionLocal, monkeypatch)


def test_background_refresh_is_bounded_and_leaves_current_hour_dirty(environment):
    env = environment
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    now = datetime(2026, 9, 29, 0, 59, tzinfo=UTC)
    with env[1].SessionLocal() as db:
        for hours in range(4):
            rollups.invalidate(db, now - timedelta(hours=hours))
        db.commit()
    assert rollups.refresh_closed_hours(env[1].engine, now=now) == 0
    with env[1].SessionLocal() as db:
        db.add(env[2].ThreeDPrintingTelemetryRollupState(
            factory_id="huakang-a", initialized_at=rollups.stamp(now)))
        db.commit()
    assert rollups.refresh_closed_hours(env[1].engine, now=now) == 2
    assert rollups.refresh_closed_hours(env[1].engine, now=now) == 1
    assert rollups.refresh_closed_hours(env[1].engine, now=now) == 0
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingTelemetryRollup,
                      ("huakang-a", rollups.stamp(rollups.hour(now)))).dirty


def test_existing_database_startup_does_not_bypass_rollup_migration(environment):
    env = environment
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    env[2].ThreeDPrintingTelemetryRollupState.__table__.drop(env[1].engine)
    env[2].ThreeDPrintingTelemetryRollup.__table__.drop(env[1].engine)
    env[1].init_db()
    rollups.available.cache_clear()
    assert not rollups.available(env[1].engine)
    with env[1].SessionLocal() as db:
        assert rollups.counters(db, env[4][0] - timedelta(days=1), env[4][0]) is None


def test_connector_invalidates_atomically_and_duplicate_does_not_dirty_again(environment, monkeypatch):
    env = environment
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    ref = session(env)
    original = event(env, ref)
    post(env, "/events", original)
    bucket = rollups.stamp(rollups.hour(env[4][0]))
    rollups.cached_hour(env[1].engine, bucket)
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingTelemetryRollup, ("huakang-a", bucket)).dirty is False
    post(env, "/events", original)
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingTelemetryRollup, ("huakang-a", bucket)).dirty is False
    incoming = event(env, ref, event_id="new-rollup-event", sequence=2)
    real_notify = env[3].notify
    def fail(*_args, **_kwargs):
        raise RuntimeError("roll back event and derived invalidation")
    monkeypatch.setattr(env[3], "notify", fail)
    import pytest
    with pytest.raises(RuntimeError):
        post(env, "/events", incoming)
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingPrinterStateEvent, incoming["event_id"]) is None
        assert db.get(env[2].ThreeDPrintingTelemetryRollup, ("huakang-a", bucket)).dirty is False
    monkeypatch.setattr(env[3], "notify", real_notify)
    post(env, "/events", incoming)
    with env[1].SessionLocal() as db:
        assert db.get(env[2].ThreeDPrintingTelemetryRollup, ("huakang-a", bucket)).dirty is True
