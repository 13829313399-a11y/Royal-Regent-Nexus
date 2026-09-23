from datetime import UTC, datetime
from uuid import uuid4
from .base import ReadResult, capabilities


class Simulator:
    def probe(self):
        return dict(available=True, synthetic=True)

    def capabilities(self):
        return capabilities("inferred")

    def health(self):
        return dict(state="ready", synthetic=True)

    def read_snapshot(self):
        return dict(work_state="unknown", progress=None, synthetic=True)

    def read_events_since(self, cursor):
        state = dict(cursor or dict(step=0, generation=uuid4().hex, job_id=uuid4().hex))
        step = state["step"]
        kind = "job_start" if step == 0 else "job_complete" if step == 3 else "job_progress"
        event = dict(kind=kind, observed_at=datetime.now(UTC).isoformat(), adapter_type="simulator", adapter_version="1.0.0", source_identity=dict(generation=state["generation"], step=step), evidence=dict(level="inferred", synthetic=True), payload=dict(native_job_id=state["job_id"], count=str(step), count_unit="board", counter_mode="cumulative", ink_total_ml=None, work_state="idle" if step==3 else "running"))
        if step == 3:
            state = dict(step=0, generation=state["generation"], job_id=uuid4().hex)
        else:
            state["step"] += 1
        return ReadResult([event], state, [])
