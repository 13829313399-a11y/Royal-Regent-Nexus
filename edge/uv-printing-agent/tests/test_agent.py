import json
from pathlib import Path
import pytest
from uv_agent.outbox import Outbox, Backpressure
from uv_agent.adapters.generic_csv_log import GenericCsvLog, HEADERS
from uv_agent.adapters.simulator import Simulator
from uv_agent.transport import Transport


def test_atomic_cursor_restart_and_partial_ack(tmp_path):
    path = tmp_path / "outbox.db"
    box = Outbox(path, min_free_bytes=0)
    box.append("source", [{"kind":"start"}, {"kind":"finish"}], {"offset":123})
    original = box.pending()
    box.close()
    box = Outbox(path, min_free_bytes=0)
    assert box.pending() == original and box.cursor("source") == {"offset":123}
    box.acknowledge([dict(event_id=original[1]["event_id"], status="persisted")])
    assert box.db.execute("SELECT contiguous FROM ack_watermark").fetchone()[0] == 0
    box.acknowledge([dict(event_id=original[0]["event_id"], status="duplicate")])
    assert box.db.execute("SELECT contiguous FROM ack_watermark").fetchone()[0] == 2
    box.append("source", [{"kind":"next"}], {"offset":124})
    assert box.pending()[0]["sequence"] == 3
    assert box.pending()[0]["stream_id"] == original[0]["stream_id"]
    box.close()


def test_capacity_preserves_evidence_and_cursor(tmp_path):
    box = Outbox(tmp_path/"queue.db", queue_limit=1, min_free_bytes=0)
    box.append("source", [{"kind":"start"}], {"offset":1})
    with pytest.raises(Backpressure):
        box.append("source", [{"kind":"finish"}], {"offset":2})
    assert box.cursor("source")["offset"] == 1 and len(box.pending()) == 1
    box.acknowledge([dict(event_id=box.pending()[0]["event_id"], status="rejected", code="bad")])
    assert not box.pending() and box.diagnostics()["quarantine_count"] == 1
    assert box.db.execute("SELECT count(*) FROM outbox").fetchone()[0] == 1
    box.close()


def test_rebind_required_keeps_original_event_queued(tmp_path):
    box=Outbox(tmp_path/'retry.db',min_free_bytes=0)
    box.append('source',[{'kind':'job_complete','binding_version':1}],{'offset':123})
    original=box.pending()[0]
    box.acknowledge([dict(event_id=original['event_id'],status='rejected',code='stream_rebind_required',retryable=True)])
    assert box.pending()==[original] and box.diagnostics()['quarantine_count']==0
    box.close()
    box=Outbox(tmp_path/'retry.db',min_free_bytes=0)
    assert box.pending()==[original]
    box.acknowledge([dict(event_id=original['event_id'],status='persisted')])
    assert not box.pending()
    box.close()


def test_log_partial_gb_duplicate_lines_rotation_and_bad_units(tmp_path):
    path = tmp_path/"jobs.csv"
    header = ','.join(HEADERS)+'\n'
    line = "相同证据,UV-01,JOB-1,progress,2026-09-23T08:01:00+08:00,1,board,cumulative,\n"
    path.write_bytes((header+line+line[:20]).encode("gb18030"))
    adapter = GenericCsvLog(path, encoding="gb18030")
    first = adapter.read_events_since(None)
    assert len(first.events) == 1
    with path.open('ab') as output:
        output.write(line[20:].encode("gb18030"))
    second = adapter.read_events_since(first.cursor)
    assert len(second.events) == 1
    assert second.events[0]["source_identity"]["generation"] == first.events[0]["source_identity"]["generation"]
    assert second.events[0]["source_identity"]["byte_offset"] != first.events[0]["source_identity"]["byte_offset"]
    rotated = tmp_path/"rotated.csv"
    path.replace(rotated)
    path.write_bytes((header+line.replace(',board,', ',invalid,')+line).encode("gb18030"))
    third = adapter.read_events_since(second.cursor)
    assert len(third.events) == len(third.rejected) == 1
    assert third.cursor["generation"] != second.cursor["generation"]
    path.write_bytes((header+line).encode("gb18030"))
    fourth = adapter.read_events_since(third.cursor)
    assert len(fourth.events) == 1 and fourth.cursor["generation"] != third.cursor["generation"]


def test_cumulative_fixture_and_simulator_capabilities():
    fixture = Path(__file__).parents[1]/"fixtures/synthetic/jobs.csv"
    result = GenericCsvLog(fixture).read_events_since(None)
    assert [x["payload"]["count"] for x in result.events] == ["0", "1", "3"]
    adapter = Simulator()
    assert adapter.capabilities()["submitNativeJob"] is False
    assert adapter.read_snapshot()["progress"] is None
    cursor = None
    for _ in range(4):
        result = adapter.read_events_since(cursor)
        cursor = result.cursor
    assert result.events[0]["kind"] == "job_complete"


@pytest.mark.parametrize("url", ["http://factory.example", "https://user:pass@example.com", "file:///etc/passwd", "https://example.com/secret"])
def test_transport_rejects_unapproved_origins(url):
    with pytest.raises(ValueError):
        Transport(url)


def test_rotation_drains_unread_tail_across_restart_and_keeps_job(tmp_path):
    path=tmp_path/'jobs.csv'
    header=','.join(HEADERS)+'\n'
    lines=[f'event-{i},UV-01,JOB-1,{"start" if i==0 else "progress"},2026-09-23T08:01:00+08:00,{i},board,cumulative,\n' for i in range(250)]
    path.write_text(header+''.join(lines),encoding='utf-8')
    first=GenericCsvLog(path).read_events_since(None)
    assert len(first.events)==200
    path.replace(tmp_path/'jobs.1.csv')
    path.write_text(header+'end,UV-01,JOB-1,complete,2026-09-23T08:02:00+08:00,250,board,cumulative,\n',encoding='utf-8')
    second=GenericCsvLog(path).read_events_since(first.cursor)
    assert len(second.events)==50
    third=GenericCsvLog(path).read_events_since(second.cursor)
    assert len(third.events)==1
    assert third.events[0]['source_identity']['job_identity']==first.events[0]['source_identity']['job_identity']
    assert third.cursor['generation']!=first.cursor['generation']


def test_oversized_line_is_quarantined_without_blocking_following_row(tmp_path):
    path=tmp_path/'jobs.csv'
    header=','.join(HEADERS)+'\n'
    line='valid,UV-01,JOB-1,progress,2026-09-23T08:01:00+08:00,1,board,cumulative,\n'
    path.write_bytes((header+line+'x'*180000+'\n'+line).encode('utf-8'))
    result=GenericCsvLog(path).read_events_since(None)
    assert len(result.events)==2 and len(result.rejected)==1
    assert result.rejected[0]['byte_length']==180001
    assert result.cursor['offset']==path.stat().st_size


def test_pairing_retry_does_not_relabel_existing_identity(tmp_path,monkeypatch):
    from uv_agent import identity
    path=tmp_path/'identity.json'
    monkeypatch.setattr(identity,'save',lambda path,value:Path(path).write_text(json.dumps(value)))
    monkeypatch.setattr(identity,'load',lambda path:json.loads(Path(path).read_text()))
    class Cloud:
        base_url='https://qa.invalid'
        def request(self,path,body):
            return dict(agent_id='first',factory_id='huakang-a')
    identity.enroll(Cloud(),path,'code-one')
    original=path.read_text()
    identity.enroll(Cloud(),path,'code-one')
    assert path.read_text()==original
    with pytest.raises(ValueError,match='separate_state_directory'):
        identity.enroll(Cloud(),path,'code-two')
    assert path.read_text()==original
