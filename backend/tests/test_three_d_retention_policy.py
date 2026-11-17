import json
from datetime import UTC, datetime, timedelta
from importlib import import_module

from sqlalchemy import func, select

from test_three_d_connector import environment, event, post, session
from test_three_d_connector_postgres import postgres


def test_stable_raw_window_and_durable_boundaries(environment):
    env = environment
    ref = session(env)
    start = env[4][0]
    workspace = import_module("app.services.three_d_workspace")
    rollup = import_module("app.services.three_d_telemetry_rollups")
    retain = import_module("app.services.three_d_telemetry_retention")
    replay = import_module("scripts.replay_three_d_runs")
    model, tick = env[2].ThreeDPrintingPrinterStateEvent, env[2].ThreeDPrintingTelemetryTick
    packets = []
    for seq, (offset, state, progress, temp) in enumerate(
            [(0,"RUNNING",2,208),(2,"RUNNING",9,211),(4,"RUNNING",11,213),
             (6,"RUNNING",15,218),(8,"RUNNING",20,350),(10,"FINISH",100,215)], 1):
        env[4][0] = start + timedelta(seconds=offset)
        packet = event(env, ref, seq, state, progress_percent=progress, nozzle_temperature=temp)
        post(env, "/events", packet)
        packets.append(packet)
    with env[1].SessionLocal() as db:
        regular = db.get(model, packets[1]["event_id"])
        assert regular.payload_version == 2
        assert regular.progress == 0 and regular.temperatures_json == "{}" and regular.current_file == ""
        history = workspace.printer_detail(db, ref["printer_id"])
        assert next(x for x in history["events"] if x["id"] == regular.id)["progress"] == 9
        stats = rollup.scan(db, start, start + timedelta(seconds=11))
        assert stats["1"]["temperature_alarm_events"] == 1
        signature = lambda runs: [(r.device_job_key,r.current_file,r.started_at,r.ended_at,r.end_state) for r in runs]
        jobs_before = signature(replay.replay_runs(replay.load_events(db,"","")))
        records_before = [(r.id,r.gcode_file,r.print_start_at,r.print_end_at) for r in
                          db.scalars(select(env[2].ThreeDPrintingProductionRecord))]
    assert retain.process_due(env[1].engine, now=start+timedelta(days=2))[1:] == [0,0]
    counts = retain.process_due(env[1].engine, now=start+timedelta(days=4))
    assert counts[1] and counts[2]
    with env[1].SessionLocal() as db:
        assert db.get(tick, packets[1]["event_id"]) is not None
        assert db.get(model, packets[1]["event_id"]) is None
        anomaly = db.get(model,packets[4]["event_id"])
        assert anomaly.payload_version == 3 and json.loads(anomaly.temperatures_json)["nozzle"] == 350
        assert json.loads(anomaly.raw_payload_json)["device_job_key"] == "job-1"
        assert rollup.scan(db,start,start+timedelta(seconds=11)) == stats
        assert signature(replay.replay_runs(replay.load_events(db,"",""))) == jobs_before
        assert [(r.id,r.gcode_file,r.print_start_at,r.print_end_at) for r in
                db.scalars(select(env[2].ThreeDPrintingProductionRecord))] == records_before
        assert workspace.printer_detail(db,ref["printer_id"])["printer"]["progress_percent"] == 100
    assert post(env,"/events",packets[1])["duplicate"]
    post(env,"/events",{**packets[1],"progress_percent":12},expected=409)
    assert retain.process_due(env[1].engine,now=start+timedelta(days=4)) == [0,0,0]


def test_retiring_ties_preserves_order_and_partial_hours(environment):
    env = environment
    ref = session(env)
    start = env[4][0]
    rollup = import_module("app.services.three_d_telemetry_rollups")
    retain = import_module("app.services.three_d_telemetry_retention")
    model = env[2].ThreeDPrintingPrinterStateEvent
    post(env,"/events",event(env,ref))
    with env[1].SessionLocal() as db:
        first = db.get(model,"event-session-a-1")
        enc = json.loads(first.raw_payload_json)
        for i,(offset,state,version) in enumerate([(60,"RUNNING",2),(60,"RUNNING",1),
                                                  (60,"PAUSE",1),(115,"PAUSE",1)],2):
            tm = rollup.stamp(start+timedelta(seconds=offset))
            entry = dict(enc,event_id=f"tie-{i}",state=state,sequence=i,observed_at=tm)
            db.add(model(id=entry["event_id"],factory_id=first.factory_id,printer_id=first.printer_id,
                         machine_no=first.machine_no,connector_instance_id=first.connector_instance_id,
                         connection_session_id=first.connection_session_id,sequence=i,state=state,
                         observed_at=tm,received_at=rollup.stamp(start+timedelta(seconds=offset,milliseconds=i)),
                         payload_version=version,raw_payload_json=json.dumps(entry)))
        db.commit()
        baseline = rollup.scan(db,start,start+timedelta(seconds=116))
        assert baseline["1"]["pause_seconds"] == 55 and baseline["1"]["observed_seconds"] == 115
    retain.process_due(env[1].engine,now=start+timedelta(days=4))
    with env[1].SessionLocal() as db:
        assert rollup.scan(db,start,start+timedelta(seconds=116)) == baseline


def test_postgres_initial_sweep_preserves_identity_and_is_resumable(postgres, monkeypatch, tmp_path):
    env, target, sessions, _ = postgres
    from scripts import compact_three_d_legacy_payloads as initial
    from app.services.three_d_telemetry_storage import compact_payload
    monkeypatch.setattr(initial,"engine",target)
    m = env[2]
    when = (datetime.now(UTC)-timedelta(days=6)).isoformat(timespec="milliseconds")
    raw = json.dumps(dict(event_id="pg-old",device_job_key="作业-42",connected=True,state="FAILED",
                          error_code="E2",nozzle_temperature=338,bed_target=70,live_material="PLA"),ensure_ascii=False)
    with sessions() as db:
        db.add(m.ThreeDPrintingConnectorInstance(id="ret-ci",factory_id="huakang-a",site_id=env[3].SITE,
               connector_key="test",instance_id="ret-ci",started_at=when,last_seen_at=when))
        db.flush()
        db.add(m.ThreeDPrintingPrinterStateEvent(id="pg-old",factory_id="huakang-a",printer_id=env[5][0],
               machine_no=1,connector_instance_id="ret-ci",connection_session_id="s",sequence=1,
               state="FAILED",observed_at=when,received_at=when,error_code="E2",current_file="test.3mf",
               raw_payload_json=raw))
        journal = dict(event_id="pg-journal", device_job_key="job-ordinary", connected=True,
                       state="RUNNING", nozzle_temperature=212, bed_temperature=60)
        db.add(m.ThreeDPrintingPrinterStateEvent(id="pg-journal",factory_id="huakang-a",
               printer_id=env[5][0],machine_no=1,connector_instance_id="ret-ci",
               connection_session_id="s",sequence=2,state="RUNNING",observed_at=when,
               received_at=when,payload_version=2,raw_payload_json=json.dumps(journal)))
        db.commit()
    path=tmp_path/"checkpoint.json"
    assert initial.run(path)["mode"] == "preview" and not path.exists()
    result=initial.run(path,execute=True,pages=8,pause=0,reserve_gib=0.001)
    assert result["done"] and result["changed"]==2
    assert initial.run(path,execute=True,pages=8,pause=0,reserve_gib=0.001)==result
    with sessions() as db:
        assert db.get(m.ThreeDPrintingTelemetryTick, "pg-journal")
        row=db.get(m.ThreeDPrintingPrinterStateEvent,"pg-old")
        assert json.loads(row.raw_payload_json)==json.loads(compact_payload(raw))
        assert (row.state,row.current_file,row.error_code,row.observed_at)==("FAILED","test.3mf","E2",when)
