import hashlib
import json
import secrets
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.document_tools import DocumentToolArtifact as Artifact, DocumentToolJob as Job, DocumentToolSource as Source
from app.services.document_tools import storage

OPERATIONS = {
    "word_translate": ("Word 翻译", {"doc", "docx"}),
    "excel_translate": ("Excel 翻译", {"xls", "xlsx"}),
    "pdf_translate": ("PDF 翻译", {"pdf"}),
    "word_to_pdf": ("Word → PDF", {"doc", "docx"}),
    "pdf_to_word": ("PDF → Word", {"pdf"}),
    "word_to_excel": ("Word → Excel", {"doc", "docx"}),
    "excel_to_word": ("Excel → Word", {"xls", "xlsx"}),
    "pdf_to_excel": ("PDF → Excel", {"pdf"}),
    "excel_to_pdf": ("Excel → PDF", {"xls", "xlsx"}),
    "pdf_split": ("PDF 精确分页", {"pdf"}),
}
TERMINAL = {"succeeded", "failed", "cancelled", "awaiting_input"}


def uid():
    return secrets.token_hex(16)


def now():
    return datetime.now(timezone.utc).isoformat()


def fail(code, message, status=400):
    raise HTTPException(status, detail={"code": code, "message": message})


def visible_jobs():
    # Internal task-list tombstone; retain source files and revision provenance.
    return Job.options_json["_deleted_at"].as_string().is_(None)


def owned(db, model, record_id, owner_id, *, include_deleted=False):
    record = db.scalar(select(model).where(model.id == record_id, model.owner_user_id == owner_id))
    if record is None or (model is Job and not include_deleted and record.options_json.get("_deleted_at")):
        fail("NOT_FOUND", "文件或任务不存在，或不属于当前账号", 404)
    return record


def withdraw(db, job):
    # Atomic with worker publication: whichever updates the row first wins.
    # Revoke the lease even if the worker is offline; stale workers cannot publish.
    changed = db.execute(update(Job).where(
        Job.id == job.id, Job.owner_user_id == job.owner_user_id,
        Job.execution_status.in_(["queued", "running", "awaiting_input"]),
    ).values(execution_status="cancelled", cancel_requested=True,
             finished_at=now(), lease_token=None, lease_until=None,
             error_code="", error_message=""))
    if changed.rowcount and job.kind == "inspect":
        db.execute(update(Source).where(Source.inspection_job_id == job.id).values(inspection_status="cancelled"))
    db.refresh(job)


def artifact_data(row):
    return {"id": row.id, "role": row.role, "format": row.format, "filename": row.filename,
            "size": row.size, "revision": row.revision, "expires_at": row.expires_at}


def job_data(db, row):
    source = db.get(Source, row.source_id) if row.source_id else None
    artifacts = db.scalars(select(Artifact).where(Artifact.job_id == row.id, Artifact.owner_user_id == row.owner_user_id).order_by(Artifact.created_at, Artifact.id)).all()
    return {"id": row.id, "source_id": row.source_id, "source_name": source.original_name if source else "结果打包",
            "operation": row.operation, "kind": row.kind, "execution_status": row.execution_status,
            "quality_status": row.quality_status, "stage": row.stage, "completed_units": row.completed_units,
            "total_units": row.total_units, "revision": row.artifact_revision,
            "options": {k: v for k, v in row.options_json.items() if not k.startswith("_")},
            "summary": row.summary_json, "error_code": row.error_code, "error_message": row.error_message,
            "created_at": row.created_at, "started_at": row.started_at, "finished_at": row.finished_at,
            "cancel_requested": row.cancel_requested, "parent_job_id": row.parent_job_id,
            "batch_id": row.batch_id, "artifacts": [artifact_data(a) for a in artifacts]}


def enqueue(db, owner_id, source_id, operation, options, client_request_id=None, batch_id="", parent=None, kind="convert", revision=1):
    fingerprint = hashlib.sha256(json.dumps({"source_id": source_id, "operation": operation, "options": options, "parent": parent}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if client_request_id:
        previous = db.scalar(select(Job).where(Job.owner_user_id == owner_id, Job.client_request_id == client_request_id))
        if previous:
            if previous.options_json.get("_deleted_at"):
                fail("TASK_DELETED", "原任务已删除，请重新提交任务", 409)
            if previous.request_fingerprint != fingerprint:
                fail("REQUEST_CONFLICT", "该提交编号已经用于不同的任务，请重新提交", 409)
            return previous
    row = Job(id=uid(), owner_user_id=owner_id, source_id=source_id, operation=operation,
              options_json=options, client_request_id=client_request_id, batch_id=batch_id,
              request_fingerprint=fingerprint, kind=kind, parent_job_id=parent,
              artifact_revision=revision, created_at=now())
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        if client_request_id:
            previous = db.scalar(select(Job).where(Job.owner_user_id == owner_id, Job.client_request_id == client_request_id))
            if previous and previous.request_fingerprint == fingerprint:
                if previous.options_json.get("_deleted_at"):
                    fail("TASK_DELETED", "原任务已删除，请重新提交任务", 409)
                return previous
        fail("REQUEST_CONFLICT", "提交发生冲突，请刷新后重试", 409)
    return row


def load_ir(db, job):
    row = db.scalar(select(Artifact).where(Artifact.job_id == job.id, Artifact.owner_user_id == job.owner_user_id, Artifact.role == "ir"))
    if row is None:
        fail("RESULT_NOT_READY", "任务尚未生成可核对的结构结果", 409)
    if row.expires_at and row.expires_at <= time.time():
        fail("ARTIFACT_EXPIRED", "结果已到保存期限，请重新生成", 410)
    return storage.read_json(row.storage_key)


def claim_job(session_factory):
    """Short transaction; PG row locking, SQLite conditional atomic update."""
    stamp = time.time()
    with session_factory() as db:
        expired = and_(Job.execution_status == "running", Job.lease_until < stamp)
        db.execute(update(Job).where(expired, Job.cancel_requested.is_(True)).values(execution_status="cancelled", lease_token=None, lease_until=None, finished_at=now()))
        db.execute(update(Job).where(expired, Job.attempt >= settings.document_tools_max_attempts).values(execution_status="failed", error_code="WORKER_RETRIES_EXHAUSTED", error_message="任务多次中断，请检查引擎后点击重试", lease_token=None, lease_until=None, finished_at=now()))
        for state in ("failed", "cancelled"):
            db.execute(update(Source).where(Source.inspection_status.not_in(TERMINAL), Source.inspection_job_id.in_(
                select(Job.id).where(Job.kind == "inspect", Job.execution_status == state))).values(inspection_status=state))
        eligible = or_(Job.execution_status == "queued", and_(expired, Job.attempt < settings.document_tools_max_attempts))
        query = select(Job.id).where(eligible, Job.cancel_requested.is_(False)).order_by(Job.created_at, Job.id).limit(1)
        if db.bind.dialect.name == "postgresql":
            query = query.with_for_update(skip_locked=True)
        candidate = db.scalar(query)
        if candidate is None:
            db.commit()
            return None
        token = uid()
        changed = db.execute(update(Job).where(Job.id == candidate, eligible, Job.cancel_requested.is_(False)).values(
            execution_status="running", quality_status="not_checked", lease_token=token,
            lease_until=stamp + settings.document_tools_lease_seconds, attempt=Job.attempt + 1,
            started_at=now(), finished_at=None, stage="inspect", completed_units=0, total_units=None,
            error_code="", error_message="")).rowcount
        db.commit()
        return (candidate, token) if changed == 1 else None


def lease_filter(job_id, token):
    return and_(Job.id == job_id, Job.lease_token == token, Job.execution_status == "running", Job.lease_until > time.time())


def renew(session_factory, job_id, token):
    with session_factory() as db:
        changed = db.execute(update(Job).where(lease_filter(job_id, token), Job.cancel_requested.is_(False)).values(lease_until=time.time() + settings.document_tools_lease_seconds)).rowcount
        db.commit()
        return changed == 1


def mark_progress(session_factory, job_id, token, stage, completed, total):
    from app.services.document_tools.document_ir import Cancelled
    if stage not in {"inspect", "extract", "recognize", "translate", "rebuild", "validate", "package"}:
        raise ValueError("Unknown processing stage")
    with session_factory() as db:
        count = db.execute(update(Job).where(lease_filter(job_id, token), Job.cancel_requested.is_(False)).values(stage=stage, completed_units=completed, total_units=total)).rowcount
        db.commit()
        if count != 1:
            raise Cancelled()


def heartbeat_status():
    cutoff = time.time() - 30
    online = False
    for path in (storage.root() / "heartbeats").glob("*.json"):
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
            online = online or state.get("timestamp", 0) >= cutoff
        except (ValueError, OSError):
            continue
    return {"online": online}
