"""B1 durable per-item ingest. Never creates reports, wages or ink movements."""
from __future__ import annotations

import argparse
import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select

from app.models.uv_ingest import UvConnector, UvConnectorMachine, UvPrintEvent
from app.models.uv_printing import UvJob, UvMachine
from app.services.uv_printing import lock

Identifier = Annotated[str, Field(min_length=1, max_length=255, pattern=r"^\S(?:.*\S)?$")]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=24, decimal_places=6, allow_inf_nan=False)]


class IngestEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_event_id: Identifier
    generation: Annotated[str, Field(min_length=1, max_length=128)]
    machine_id: Annotated[str, Field(min_length=1, max_length=64)]
    source_job_id: Identifier | None = None
    seq: Annotated[int, Field(ge=0, le=2147483647, strict=True)]
    observed_at: datetime
    kind: Literal["job", "heartbeat"] = "job"
    state: Literal["observed", "running", "completed", "cancelled", "uncertain"] = "observed"
    raw_task_name: Annotated[str, Field(max_length=4096)] = ""
    raw_product_name: Annotated[str, Field(max_length=4096)] | None = None
    raw_count: Quantity | None = None
    raw_unit: Literal["piece", "board", "cycle", "unknown"] = "unknown"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    time_evidence: Literal["observed", "inferred", "unknown"] = "unknown"
    completion_evidence: Literal["explicit", "inferred", "none"] = "none"
    runtime_status: Literal["unknown", "idle", "printing", "offline", "error"] = "unknown"
    progress_pct: Annotated[Decimal, Field(ge=0, le=100)] | None = None
    print_time_seconds: Annotated[int, Field(ge=0, le=2147483647, strict=True)] | None = None
    print_area_m2: Quantity | None = None
    ink_total_ml: Quantity | None = None
    ink_measurement: Literal["cumulative", "delta"] = "cumulative"
    raw: dict = Field(default_factory=dict)

    @field_validator("observed_at", "started_at", "completed_at")
    @classmethod
    def utc(cls, value):
        if value is not None:
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("明确时区的事件时间是必填证据")
            return value.astimezone(UTC)
        return value

    @model_validator(mode="after")
    def evidence(self):
        if self.kind == "job" and not self.source_job_id:
            raise ValueError("作业事件必须有稳定 source_job_id")
        if self.kind == "heartbeat" and self.source_job_id:
            raise ValueError("心跳不能携带作业身份")
        if self.started_at and self.completed_at and self.completed_at < self.started_at:
            raise ValueError("结束时间不能早于开始时间")
        if len(json.dumps(self.raw, ensure_ascii=False, allow_nan=False).encode()) > 16384:
            raise ValueError("原始证据超过 16 KiB")
        return self


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def authenticate(db, token):
    if not token or len(token) > 256:
        raise HTTPException(401, "无效连接器凭据")
    connector = db.scalar(select(UvConnector).where(UvConnector.credential_hash == digest(token), UvConnector.enabled.is_(True)))
    if connector is None:
        raise HTTPException(401, "无效连接器凭据")
    return connector


def provision(db, factory_id, machine_ids, connector_id=None):
    """Privileged local administration only. Return a newly generated secret once."""
    lock(db, factory_id)
    if not machine_ids:
        raise ValueError("连接器必须绑定至少一台机台")
    for machine_id in set(machine_ids):
        machine = db.get(UvMachine, machine_id)
        if machine is None or machine.factory_id != factory_id or not machine.enabled:
            raise ValueError("机台不存在、不属于华康A或已停用")
    token = secrets.token_urlsafe(48)
    connector = UvConnector(id=connector_id or uuid4().hex, factory_id=factory_id, credential_hash=digest(token))
    db.add(connector)
    db.flush()
    db.add_all([UvConnectorMachine(connector_id=connector.id, machine_id=m) for m in set(machine_ids)])
    db.flush()
    return connector, token


def _accept(db, connector, factory_id, event):
    if factory_id != "huakang-a" or connector.factory_id != factory_id:
        raise HTTPException(403, "连接器厂区不匹配")
    machine = db.get(UvMachine, event.machine_id)
    allowed = db.get(UvConnectorMachine, (connector.id, event.machine_id))
    if allowed is None or machine is None or machine.factory_id != factory_id or not machine.enabled:
        raise HTTPException(403, "机台不在已启用连接器范围")
    payload = event.model_dump(mode="json")
    fingerprint = digest(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False))
    existing = db.scalar(select(UvPrintEvent).where(UvPrintEvent.connector_id == connector.id, UvPrintEvent.generation == event.generation, UvPrintEvent.source_event_id == event.source_event_id))
    if existing:
        if existing.fingerprint != fingerprint:
            raise HTTPException(409, "event_id_conflict: 同一事件身份对应不同内容")
        return {"status": "duplicate", "receipt_id": existing.id, "job_id": existing.job_id}
    now = datetime.now(UTC)
    # Reject future clock poison; old observations remain usable historical evidence.
    if event.observed_at > now + timedelta(minutes=5):
        raise HTTPException(422, "事件时钟超前超过5分钟，请校准后人工核对")
    stamp = event.observed_at.isoformat()
    job = None
    if event.kind == "job":
        job = db.scalar(select(UvJob).where(UvJob.factory_id == factory_id, UvJob.connector_id == connector.id, UvJob.generation == event.generation, UvJob.source_job_id == event.source_job_id))
        if job and job.machine_id != machine.id:
            raise HTTPException(409, "同一来源作业不能跨机台复用")
        previous = None if job is None else db.scalar(select(UvPrintEvent).where(UvPrintEvent.job_id == job.id).order_by(UvPrintEvent.seq.desc(), UvPrintEvent.observed_at.desc(), UvPrintEvent.id.desc()).limit(1))
        if job and db.scalar(select(UvPrintEvent.id).where(UvPrintEvent.job_id == job.id, UvPrintEvent.seq == event.seq).limit(1)):
            raise HTTPException(409, "job_sequence_conflict: 同一作业序号不能用于不同事件")
        if job is None:
            job = UvJob(factory_id=factory_id, machine_id=machine.id, connector_id=connector.id, generation=event.generation, source_job_id=event.source_job_id, source_event_id=event.source_event_id, raw_task_name=event.raw_task_name)
            db.add(job)
            db.flush()
        if previous is None or event.seq > previous.seq:
            job.source_event_id = event.source_event_id
            job.raw_task_name, job.raw_product_name = event.raw_task_name, event.raw_product_name
            job.state = "uncertain" if event.state == "completed" and event.completion_evidence != "explicit" else event.state
            job.started_at = event.started_at.isoformat() if event.started_at else job.started_at
            job.completed_at = event.completed_at.isoformat() if event.completed_at else None
            job.time_evidence = event.time_evidence
            job.raw_count = event.raw_count
            # A human unit reconciliation is not overwritten by later telemetry.
            if job.suggested_piece_qty is None and not job.product_id and not job.reconcile_note:
                job.raw_unit = event.raw_unit
            job.print_time_seconds, job.print_area_m2 = event.print_time_seconds, event.print_area_m2
            job.version += 1
            job.updated_at = now.isoformat()
        # Never mix cumulative counters with deltas. Mixed evidence remains raw only.
        history = list(db.scalars(select(UvPrintEvent).where(UvPrintEvent.job_id == job.id)))
        ink_events = [r.payload for r in history if r.payload.get("ink_total_ml") is not None]
        if event.ink_total_ml is not None:
            ink_events.append(payload)
        modes = {r["ink_measurement"] for r in ink_events}
        if modes == {"delta"}:
            job.ink_total_ml = sum((Decimal(r["ink_total_ml"]) for r in ink_events), Decimal(0))
            if job.ink_total_ml >= Decimal("1000000000000000000"):
                raise HTTPException(422, "累计遥测墨量超过存储精度，需核对来源")
        elif modes == {"cumulative"}:
            latest = max(ink_events, key=lambda r: (r["seq"], r["observed_at"]))
            job.ink_total_ml = Decimal(latest["ink_total_ml"])
        elif len(modes) > 1:
            job.ink_total_ml = None
    receipt = UvPrintEvent(factory_id=factory_id, connector_id=connector.id, machine_id=machine.id, generation=event.generation, source_event_id=event.source_event_id, source_job_id=event.source_job_id, job_id=job.id if job else None, seq=event.seq, observed_at=stamp, received_at=now.isoformat(), fingerprint=fingerprint, payload=payload)
    # Observation time, not receipt time: replay never makes an offline machine fresh.
    if machine.last_heartbeat_at is None or event.observed_at > datetime.fromisoformat(machine.last_heartbeat_at):
        machine.last_heartbeat_at = stamp
        machine.runtime_status = event.runtime_status
        machine.progress_pct = event.progress_pct
        machine.current_task_name = event.raw_task_name or None
        machine.connector_id = connector.id
        machine.connector_mode = "jsonl-reference"
        machine.updated_at = now.isoformat()
        machine.version += 1
    db.add(receipt)
    db.flush()
    return {"status": "accepted", "receipt_id": receipt.id, "job_id": receipt.job_id}


def ingest_batch(db, token, factory_id, events):
    """Owns the session transaction. Each accepted receipt is committed BEFORE ACK."""
    authenticate(db, token)  # No unauthenticated item validation oracle.
    db.rollback()
    if factory_id != "huakang-a":
        raise HTTPException(403, "连接器厂区不匹配")
    results = []
    for index, raw in enumerate(events):
        identity = {k: raw.get(k) for k in ("source_event_id", "generation")} if isinstance(raw, dict) else {}
        try:
            event = IngestEvent.model_validate(raw)
            lock(db, factory_id)
            connector = authenticate(db, token)
            result = _accept(db, connector, factory_id, event)
            db.commit()
        except ValidationError:
            db.rollback()
            result = {"status": "rejected", "code": 422, "reason": "invalid_event: 事件字段、单位或时间证据无效"}
        except HTTPException as exc:
            db.rollback()
            result = {"status": "rejected", "code": exc.status_code, "reason": exc.detail}
        except Exception:
            db.rollback()
            raise  # No ACK on commit failure: replay recovers already committed items.
        results.append({"index": index, **identity, **result})
    return {"factory_id": factory_id, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Create a scoped UV connector credential; secret printed once")
    parser.add_argument("--factory-id", required=True, choices=["huakang-a"])
    parser.add_argument("--machine-id", action="append", required=True)
    args = parser.parse_args()
    from app.db import SessionLocal
    with SessionLocal() as db:
        connector, token = provision(db, args.factory_id, args.machine_id)
        db.commit()
        print(json.dumps({"connector_id": connector.id, "token": token}))


if __name__ == "__main__":
    main()
