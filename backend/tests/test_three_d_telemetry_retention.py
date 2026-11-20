from datetime import timedelta
from importlib import import_module

from test_three_d_connector import environment


def test_retention_preserves_timing_and_retry_evidence_across_cutoff(environment):
    _, db_module, models, service, clock, printer_ids = environment
    retention = import_module("app.services.three_d_telemetry_retention")
    storage = import_module("app.services.three_d_telemetry_storage")
    raw = '{"connected":true,"bed_temperature":25,"nozzle_temperature":25}'
    cutoff = clock[0] - timedelta(days=3)
    with db_module.SessionLocal.begin() as db:
        db.add(models.ThreeDPrintingConnectorInstance(
            id="retention-ci", factory_id="huakang-a", site_id=service.SITE,
            connector_key="test", instance_id="retention-ci",
            started_at=cutoff.isoformat(), last_seen_at=clock[0].isoformat(),
        ))
        db.flush()
        for index, (key, age, version) in enumerate([
            ("expired", 1, storage.JOURNAL_FRAME),
            ("boundary", 0, storage.JOURNAL_FRAME),
            ("evidence", 2, storage.FULL_EVENT),
        ]):
            timestamp = (cutoff - timedelta(seconds=age)).isoformat(timespec="milliseconds")
            db.add(models.ThreeDPrintingPrinterStateEvent(
                id=key, factory_id="huakang-a", machine_no=1, printer_id=printer_ids[0],
                connector_instance_id="retention-ci", connection_session_id="retention-session",
                sequence=index, state="IDLE", observed_at=timestamp, received_at=timestamp,
                payload_version=version, raw_payload_json=raw,
            ))
    assert retention.process_due(db_module.engine, now=clock[0]) == [2, 1, 1]
    assert retention.process_due(db_module.engine, now=clock[0]) == [0, 0, 0]
    with db_module.SessionLocal() as db:
        assert db.get(retention.Event, "expired") is None
        tick = db.get(retention.Tick, "expired")
        assert tick.observed_at == (cutoff - timedelta(seconds=1)).isoformat(timespec="milliseconds")
        assert tick.payload_digest == storage.payload_digest(raw)
        assert db.get(retention.Event, "boundary").raw_payload_json == raw
        evidence = db.get(retention.Event, "evidence")
        assert evidence.payload_version == storage.RETAINED_EVIDENCE
        assert storage.body_matches(evidence, raw)
