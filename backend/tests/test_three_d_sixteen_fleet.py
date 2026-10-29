import importlib
from datetime import timedelta

import pytest
from sqlalchemy import select

from test_three_d_connector import environment, post, registered


def expand(env):
    _, dbm, m, service, clock, _ = env
    business = importlib.import_module("app.services.three_d_printing")
    with dbm.SessionLocal() as db:
        db.get(m.ThreeDPrintingSetting, "huakang-a").machine_count = 16
        business.seed_three_d_printing_defaults(db)
        db.flush()
        printers = list(db.scalars(select(m.ThreeDPrintingPrinter)))
        for printer in printers:
            row = db.get(m.ThreeDPrintingPrinterConnection, printer.id)
            if row is None:
                row = m.ThreeDPrintingPrinterConnection(
                    printer_id=printer.id, factory_id="huakang-a", site_id=service.SITE,
                    lan_host=f"10.33.30.{100 + printer.machine_no}", mqtt_port=8883,
                    credential_ref=f"printer-{printer.machine_no:02d}",
                    certificate_fingerprint="a" * 64,
                )
                db.add(row)
            row.connection_enabled = True
            row.connection_owner = service.OBSERVER
            row.record_reconcile_enabled = False
        db.commit()
        return {p.machine_no: p.id for p in printers}


def test_all_sixteen_observers_are_listed_and_granted_without_control(environment):
    ids = expand(environment)
    registered(environment)
    listed = post(environment, "/printers", {"instance_id": "replica-a"})
    assert {p["printer_id"] for p in listed["printers"]} == set(ids.values())
    for number, printer_id in ids.items():
        grant = post(environment, "/leases/acquire", {
            "instance_id": "replica-a", "printer_id": printer_id,
        })
        assert grant["acquired"] and grant["machine_no"] == number
        assert grant["control_verified"] is False


def test_sixteenth_machine_has_filters_resources_and_raw_and_cached_analytics(environment, monkeypatch):
    env = environment
    ids = expand(env)
    registered(env)
    m, dbm, now = env[2], env[1], env[4][0]
    efficiency = importlib.import_module("app.services.three_d_efficiency")
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    monkeypatch.setattr(efficiency, "business_now", lambda: now)
    with dbm.SessionLocal() as db:
        for seq, seconds in enumerate((120, 60)):
            db.add(m.ThreeDPrintingPrinterStateEvent(
                id=f"fleet-16-{seq}", factory_id="huakang-a", printer_id=ids[16], machine_no=16,
                connector_instance_id=env[3].instance_key("replica-a"), connection_session_id="fleet-test", sequence=seq,
                observed_at=rollups.stamp(now - timedelta(hours=2, seconds=seconds)),
                received_at=rollups.stamp(now), state="PAUSE", error_code="E16",
                temperatures_json='{"bed":150}', raw_payload_json="{}",
            ))
        db.commit()
        raw = efficiency.counters(db, 1)
        assert set(raw) == set(range(1, 17))
        assert raw[16]["pause_hours"] > 0
        assert raw[16]["error_events"] == 2
    rollups.initialize(dbm.engine, now=now)
    with dbm.SessionLocal() as db:
        assert efficiency.counters(db, 1) == raw
    response = env[0].get("/api/three-d-printing/collections/records", params={
        "factory_id": "huakang-a", "machine_no": 16,
    })
    assert response.status_code == 200
    assert env[0].get("/api/three-d-printing/collections/records", params={
        "factory_id": "huakang-a", "machine_no": 17,
    }).status_code == 422
    schemas = importlib.import_module("app.schemas.three_d_operations")
    assert schemas.Profile(machine_no=16, materials=[]).machine_no == 16
    assert schemas.Spool(material="PLA", lot="test", initial_g=100, remaining_g=100,
                         machine_no=16, slot=0).machine_no == 16
    with pytest.raises(ValueError):
        schemas.Profile(machine_no=17, materials=[])
    response = env[0].get("/api/three-d-printing/operations/analytics?days=1")
    assert response.status_code == 200
    assert {x["machine_no"] for x in response.json()["machines"]} == set(range(1, 17))


def test_numbering_cutoff_preserves_old_runs_and_does_not_match_reused_numbers(environment, monkeypatch):
    from test_three_d_connector import event, session
    from test_three_d_run_reconciliation import runs, seed_product

    env = environment
    seed_product(env)
    ref = session(env)
    post(env, "/events", event(env, ref, current_file="part.3mf"))
    original_id = runs(env)[0].id
    cutoff = env[4][0].date()
    with env[1].SessionLocal() as db:
        original = db.get(env[2].ThreeDPrintingProductionRecord, original_id)
        original.business_date = (cutoff - timedelta(days=1)).isoformat()
        db.commit()
        before = {c.name: getattr(original, c.name) for c in original.__table__.columns}
    monkeypatch.setattr(env[3].settings, "three_d_record_numbering_since", cutoff)
    # Reobserving the exact known job may not create a second record or change history.
    post(env, "/events", event(env, ref, 2, "FINISH", current_file="part.3mf"))
    assert len(runs(env)) == 1
    # A different device job with the same file must start a new record today.
    post(env, "/events", event(env, ref, 3, "RUNNING", current_file="part.3mf", device_job_key="new-device-job"))
    current = runs(env)
    assert len(current) == 2
    old = next(r for r in current if r.id == original_id)
    assert {c.name: getattr(old, c.name) for c in old.__table__.columns} == before
    assert next(r for r in current if r.id != original_id).business_date == cutoff.isoformat()
    with env[1].SessionLocal() as db:
        assert float(db.get(env[2].ThreeDPrintingInventory, "stock").stock_g) == 60


def test_current_machine_statistics_exclude_previous_numbering(environment, monkeypatch):
    from datetime import datetime
    from app.core.time import BUSINESS_TIME_ZONE

    env = environment
    ids = expand(env)
    registered(env)
    m, dbm = env[2], env[1]
    now = datetime(2026, 10, 29, 12, tzinfo=BUSINESS_TIME_ZONE)
    cutoff = now.replace(hour=0)
    efficiency = importlib.import_module("app.services.three_d_efficiency")
    operations = importlib.import_module("app.services.three_d_operations")
    rollups = importlib.import_module("app.services.three_d_telemetry_rollups")
    monkeypatch.setattr(efficiency, "business_now", lambda: now)
    monkeypatch.setattr(operations, "business_now", lambda: now)
    monkeypatch.setattr(env[3].settings, "three_d_record_numbering_since", cutoff.date())
    with dbm.SessionLocal() as db:
        for label, day, start, end in [
            ("old", "2026-10-28", cutoff - timedelta(hours=2), cutoff + timedelta(hours=1)),
            ("new", "2026-10-29", cutoff + timedelta(hours=2), cutoff + timedelta(hours=3)),
        ]:
            db.add(m.ThreeDPrintingProductionRecord(
                id=label, factory_id="huakang-a", business_date=day, machine_no=6,
                status="production", run_status="succeeded", duration_hours=1,
                print_start_at=start.isoformat(), print_end_at=end.isoformat(),
                created_at=start.isoformat(), updated_at=end.isoformat(),
            ))
        for seq, instant in enumerate([cutoff - timedelta(seconds=60), cutoff + timedelta(hours=2)]):
            db.add(m.ThreeDPrintingPrinterStateEvent(
                id=f"numbering-{seq}", factory_id="huakang-a", printer_id=ids[6], machine_no=6,
                connector_instance_id=env[3].instance_key("replica-a"),
                connection_session_id="numbering-test", sequence=seq,
                observed_at=rollups.stamp(instant), received_at=rollups.stamp(instant),
                state="FINISH", error_code="OLD_ERROR" if seq == 0 else "",
                temperatures_json="{}", raw_payload_json="{}",
            ))
        db.commit()
        raw = efficiency.counters(db, 30)
        assert raw[6]["error_events"] == 0
        assert raw[6]["lifetime_hours_since_service"] == 1
        report = operations.analytics(db, 30)
        machine = next(r for r in report["machines"] if r["machine_no"] == 6)
        assert machine["completed"] == 1
        assert machine["occupied_hours"] == 1
        assert machine["availability"] == pytest.approx(1 / 12)
        assert report["effective_from"] == cutoff.isoformat()
        assert db.get(m.ThreeDPrintingProductionRecord, "old").business_date == "2026-10-28"
    rollups.initialize(dbm.engine, now=now)
    with dbm.SessionLocal() as db:
        assert efficiency.counters(db, 30) == raw
