import hashlib
import os
import time
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.models.document_tools import DocumentToolArtifact as Artifact, DocumentToolCorrection as Correction, DocumentToolJob as Job, DocumentToolSource as Source
from app.schemas.document_tools import CreateJob, OPTION_KEYS, PackageInput, PasswordInput, ReviseJob
from app.services.auth import AuthContext, get_current_user
from app.services.document_tools import job_service as service, storage


def enabled():
    if not settings.document_tools_enabled:
        service.fail("TOOLS_DISABLED", "文档工具暂未启用", 503)


router = APIRouter(prefix="/api/tools", tags=["document-tools"], dependencies=[Depends(enabled)])
User = Annotated[AuthContext, Depends(get_current_user)]
DB = Annotated[Session, Depends(get_db)]


@router.get("/capabilities")
def capabilities(user: User):
    from app.services.document_tools.capabilities import get_capabilities
    return get_capabilities()


@router.post("/uploads", status_code=202)
def upload(user: User, db: DB, file: UploadFile = File(...), factory_id: str = Form(default="")):
    name = storage.safe_name(file.filename or "document")
    kind = Path(name).suffix.lower().lstrip(".")
    if kind not in {"doc", "docx", "xls", "xlsx", "pdf"}:
        service.fail("UNSUPPORTED_TYPE", "请选择 DOC/DOCX、XLS/XLSX 或 PDF 文件", 422)
    source_id = service.uid()
    owner_key = hashlib.sha256(user.id.encode()).hexdigest()[:24]
    path = storage.resolve(f"sources/{owner_key}/{source_id}/original.{kind}")
    path.parent.mkdir(parents=True)
    temporary = path.with_suffix(path.suffix + ".upload")
    size = 0
    sha = hashlib.sha256()
    try:
        with temporary.open("xb") as output:
            while chunk := file.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.document_tools_max_file_bytes:
                    service.fail("FILE_TOO_LARGE", f"文件超过 {settings.document_tools_max_file_bytes // 1024 // 1024} MB，请拆分后上传", 413)
                output.write(chunk)
                sha.update(chunk)
        if not size:
            service.fail("EMPTY_FILE", "文件为空，请重新选择", 422)
        os.replace(temporary, path)
        source = Source(id=source_id, owner_user_id=user.id, original_name=name, detected_type=kind,
            sha256=sha.hexdigest(), byte_size=size, storage_key=storage.key_for(path), created_at=service.now(), factory_context=factory_id[:64])
        db.add(source)
        db.flush()
        inspection = service.enqueue(db, user.id, source_id, "inspect", {}, kind="inspect")
        source.inspection_job_id = inspection.id
        db.add(Artifact(id=service.uid(), job_id=inspection.id, owner_user_id=user.id,
            revision=1, role="source", format=kind, filename=name, storage_key=source.storage_key,
            size=size, sha256=source.sha256, created_at=service.now(), expires_at=None))
        db.commit()
        return {"source_id": source_id, "inspection_job_id": inspection.id}
    except Exception:
        db.rollback()
        if temporary.exists():
            temporary.unlink()
        if path.exists():
            path.unlink()
        raise


@router.get("/sources/{source_id}")
def source_detail(source_id: str, user: User, db: DB):
    row = service.owned(db, Source, source_id, user.id)
    inspection = db.get(Job, row.inspection_job_id)
    artifacts = db.scalars(select(Artifact).join(Job, Artifact.job_id == Job.id).where(
        Job.source_id == row.id, Job.kind == "inspect", Artifact.owner_user_id == user.id,
        Artifact.role.in_(["source", "preview"]))).all()
    return {"id": row.id, "original_name": row.original_name, "detected_type": row.detected_type,
        "inspection_status": row.inspection_status, "inspection_job_id": row.inspection_job_id,
        "manifest": storage.read_json(row.manifest_key, {}), "byte_size": row.byte_size,
        "error_code": inspection.error_code if inspection else "", "error_message": inspection.error_message if inspection else "",
        "artifacts": [service.artifact_data(a) for a in artifacts]}


@router.post("/sources/{source_id}/password", status_code=202)
def password(source_id: str, payload: PasswordInput, user: User, db: DB):
    source = service.owned(db, Source, source_id, user.id)
    if source.inspection_status != "awaiting_input":
        service.fail("PASSWORD_NOT_REQUESTED", "当前文件不需要补充密码", 409)
    source.credential_ciphertext = storage.encrypt_password(payload.password)
    job = service.enqueue(db, user.id, source.id, "inspect", {}, kind="inspect")
    source.inspection_job_id, source.inspection_status = job.id, "queued"
    db.commit()
    return {"job_id": job.id}


@router.post("/jobs", status_code=202)
def create_job(payload: CreateJob, user: User, db: DB):
    source = service.owned(db, Source, payload.source_id, user.id)
    if source.inspection_status != "succeeded":
        service.fail("SOURCE_NOT_READY", "文件检查尚未完成，请先处理文件提示", 409)
    if source.detected_type not in service.OPERATIONS[payload.operation][1]:
        service.fail("TYPE_MISMATCH", "所选转换方向与源文件类型不符", 422)
    options = payload.options.model_dump(include=OPTION_KEYS[payload.operation])
    if payload.operation.endswith("_translate"):
        from app.services.document_tools.translation_engine import validate_translation_options
        from app.services.document_tools.document_ir import ToolError
        try:
            validate_translation_options(options, payload.operation)
        except ToolError as exc:
            service.fail(exc.code, exc.message, 422)
    job = service.enqueue(db, user.id, source.id, payload.operation, options, payload.client_request_id, payload.batch_id)
    db.commit()
    return {"job_id": job.id}


@router.get("/jobs")
def list_jobs(user: User, db: DB, page: int = Query(default=1, ge=1), page_size: int = Query(default=20, ge=1, le=100), batch_id: str | None = None, status: str | None = None):
    filters = [Job.owner_user_id == user.id, service.visible_jobs()]
    if batch_id:
        filters.append(Job.batch_id == batch_id)
    if status:
        filters.append(Job.execution_status == status)
    total = db.scalar(select(func.count()).select_from(Job).where(*filters))
    rows = db.scalars(select(Job).where(*filters).order_by(Job.created_at.desc(), Job.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    return {"items": [service.job_data(db, r) for r in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, user: User, db: DB):
    return service.job_data(db, service.owned(db, Job, job_id, user.id))


@router.get("/jobs/{job_id}/issues")
def issues(job_id: str, user: User, db: DB, page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), page_index: int | None = None, table_id: str | None = None, severity: str | None = None):
    job = service.owned(db, Job, job_id, user.id)
    ir = service.load_ir(db, job)
    rows = ir.get("issues", [])
    if page_index is not None:
        rows = [r for r in rows if r.get("source", {}).get("page_index") == page_index]
    if table_id:
        ids = {c["id"] for t in ir.get("tables", []) if t["id"] == table_id for c in t["cells"]}
        rows = [r for r in rows if r.get("target_id") in ids or r.get("target_id") == table_id]
    if severity:
        rows = [r for r in rows if r.get("severity") == severity]
    return {"items": rows[(page - 1) * page_size:page * page_size], "total": len(rows), "page": page, "page_size": page_size}


@router.get("/jobs/{job_id}/result")
def result(job_id: str, user: User, db: DB, table_id: str | None = None, target_id: str | None = None, offset: int = Query(default=0, ge=0), limit: int = Query(default=200, ge=1, le=1000)):
    ir = service.load_ir(db, service.owned(db, Job, job_id, user.id))
    if target_id:
        for table in ir.get("tables", []):
            index = next((n for n, cell in enumerate(table["cells"]) if cell["id"] == target_id), None)
            if index is not None:
                table_id, offset = table["id"], index // limit * limit
                break
    tables = [t for t in ir.get("tables", []) if not table_id or t["id"] == table_id]
    total = sum(len(t["cells"]) for t in tables)
    cursor = 0
    selected_ids = set()
    for table in tables:
        count = len(table["cells"])
        table["cells"] = table["cells"][max(0, offset - cursor):max(0, min(count, offset + limit - cursor))]
        selected_ids.update(c["id"] for c in table["cells"])
        cursor += count
    blocks = ir.get("blocks", [])[offset:offset + limit]
    for block in blocks:
        block.get("style", {}).pop("image_path", None)
    manifest = dict(ir.get("engine_manifest", {}))
    candidates = manifest.pop("regional_candidates", [])
    if candidates:
        manifest["regional_candidate_count"] = len(candidates)
    display_cells = manifest.pop("display_cells", {})
    if display_cells:
        manifest["display_cell_count"] = sum(len(cells) for cells in display_cells.values() if isinstance(cells, dict))
    selected_ids.update(b["id"] for b in blocks)
    return {**ir, "engine_manifest": manifest, "tables": tables, "blocks": blocks, "issues": ir.get("issues", [])[:100],
        "mappings": [m for m in ir.get("mappings", []) if m.get("target_id") in selected_ids or m.get("result_id") in selected_ids][:limit],
        "total_cells": total, "total_blocks": len(ir.get("blocks", [])), "offset": offset, "limit": limit}


@router.post("/jobs/{job_id}/cancel")
def cancel(job_id: str, user: User, db: DB):
    job = service.owned(db, Job, job_id, user.id)
    service.withdraw(db, job)
    db.commit()
    return service.job_data(db, job)


@router.delete("/jobs/{job_id}", status_code=204)
def delete_job(job_id: str, user: User, db: DB):
    job = service.owned(db, Job, job_id, user.id, include_deleted=True)
    if not job.options_json.get("_deleted_at"):
        service.withdraw(db, job)
        # Logical deletion only: other revisions/packages can still use these files.
        job.options_json = {**job.options_json, "_deleted_at": service.now()}
        db.commit()


@router.post("/jobs/{job_id}/retry", status_code=202)
def retry(job_id: str, user: User, db: DB):
    parent = service.owned(db, Job, job_id, user.id)
    if parent.execution_status not in {"failed", "cancelled"}:
        service.fail("RETRY_NOT_AVAILABLE", "仅失败或已取消任务可以重试", 409)
    job = service.enqueue(db, user.id, parent.source_id, parent.operation, dict(parent.options_json),
        batch_id=parent.batch_id, parent=parent.parent_job_id if parent.kind == "revise" else parent.id,
        kind=parent.kind, revision=parent.artifact_revision)
    if parent.kind == "revise":
        for old in db.scalars(select(Correction).where(Correction.new_job_id == parent.id)).all():
            db.add(Correction(id=service.uid(), parent_job_id=old.parent_job_id, new_job_id=job.id,
                author_user_id=user.id, target_anchor=old.target_anchor, old_value=old.old_value,
                new_value=old.new_value, reason=old.reason, created_at=service.now()))
    if parent.kind == "inspect":
        source = service.owned(db, Source, parent.source_id, user.id)
        source.inspection_job_id, source.inspection_status = job.id, "queued"
    db.commit()
    return {"job_id": job.id}


@router.post("/jobs/{job_id}/revise", status_code=202)
def revise(job_id: str, payload: ReviseJob, user: User, db: DB):
    parent = service.owned(db, Job, job_id, user.id)
    if parent.operation.endswith("_translate"):
        service.fail("TRANSLATION_REVISION_UNSUPPORTED", "请下载译文修改，或调整翻译设置后重新生成", 422)
    if parent.execution_status != "succeeded" or parent.operation not in service.OPERATIONS:
        service.fail("RESULT_NOT_READY", "请先选择已生成的转换结果", 409)
    if payload.base_revision != parent.artifact_revision:
        service.fail("STALE_REVISION", "结果版本已变化，请刷新后重新修改", 409)
    ir = service.load_ir(db, parent)
    targets = {c["id"]: c for t in ir.get("tables", []) for c in t["cells"]}
    targets.update({b["id"]: b for b in ir.get("blocks", []) if not b.get("table_id")})
    for correction in payload.corrections:
        if correction.target_id not in targets:
            service.fail("ANCHOR_NOT_FOUND", "修正位置不存在，请重新选择", 422)
    options = dict(parent.options_json)
    options.pop("_recognize_region", None)
    if payload.options is not None:
        irrelevant = payload.options.model_fields_set - OPTION_KEYS[parent.operation]
        if irrelevant:
            service.fail("INVALID_OPTIONS", "修订选项与当前转换方向不符", 422)
        options.update(payload.options.model_dump(exclude_unset=True))
    if payload.region:
        source = service.owned(db, Source, parent.source_id, user.id)
        if source.detected_type != "pdf" or parent.operation == "pdf_split":
            service.fail("REGION_UNSUPPORTED", "区域重识别仅用于 PDF 结构转换", 422)
        pages = ir.get("pages", [])
        selected = next((p for p in pages if p["page_index"] == payload.region.page_index), None)
        if not selected or payload.region.bbox_pt[2] > selected["width_pt"] or payload.region.bbox_pt[3] > selected["height_pt"]:
            service.fail("INVALID_REGION", "识别区域超出原页面范围", 422)
        options["_recognize_region"] = payload.region.model_dump()
    job = service.enqueue(db, user.id, parent.source_id, parent.operation, options, parent=parent.id, kind="revise", revision=parent.artifact_revision + 1)
    for correction in payload.corrections:
        target = targets[correction.target_id]
        db.add(Correction(id=service.uid(), parent_job_id=parent.id, new_job_id=job.id, author_user_id=user.id,
            target_anchor={"target_id": correction.target_id, "source": target.get("source", {})},
            old_value=target.get("display_text", target.get("text", "")), new_value=correction.new_value,
            reason=correction.reason, created_at=service.now()))
    db.commit()
    return {"job_id": job.id}


def serve_artifact(artifact_id, user, db, download=False):
    row = service.owned(db, Artifact, artifact_id, user.id)
    if row.expires_at and row.expires_at <= time.time():
        service.fail("ARTIFACT_EXPIRED", "文件已到保存期限，请重新生成", 410)
    path = storage.resolve(row.storage_key)
    if not path.is_file():
        service.fail("FILE_NOT_FOUND", "文件暂不可用，请重试或重新生成", 404)
    return FileResponse(path, media_type=storage.MIME.get(row.format, "application/octet-stream"),
        filename=row.filename, content_disposition_type="attachment" if download else "inline",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.get("/artifacts/{artifact_id}/content")
def content(artifact_id: str, user: User, db: DB):
    return serve_artifact(artifact_id, user, db)


@router.get("/artifacts/{artifact_id}/download")
def download(artifact_id: str, user: User, db: DB):
    return serve_artifact(artifact_id, user, db, True)


@router.post("/packages", status_code=202)
def package(payload: PackageInput, user: User, db: DB):
    if len(set(payload.artifact_ids)) != len(payload.artifact_ids):
        service.fail("DUPLICATE_ARTIFACT", "请勿重复选择同一结果", 422)
    for artifact_id in payload.artifact_ids:
        artifact = service.owned(db, Artifact, artifact_id, user.id)
        if artifact.role not in {"result", "package"}:
            service.fail("INVALID_ARTIFACT", "只能打包转换结果文件", 422)
        if artifact.expires_at and artifact.expires_at <= time.time():
            service.fail("ARTIFACT_EXPIRED", "选中的结果已到期", 410)
    job = service.enqueue(db, user.id, None, "package", {"artifact_ids": payload.artifact_ids}, payload.client_request_id, kind="package")
    db.commit()
    return {"job_id": job.id}


@router.get("/sources/{source_id}/split-suggestions")
def suggestions(source_id: str, user: User, db: DB, page_index: int = Query(default=0, ge=0), target_height_pt: float = Query(default=842, gt=1), axis: str = Query(default="y", pattern="^[xy]$")):
    source = service.owned(db, Source, source_id, user.id)
    if source.detected_type != "pdf" or source.inspection_status != "succeeded":
        service.fail("SOURCE_NOT_READY", "请先完成 PDF 文件检查", 409)
    from app.services.document_tools.pdf_engine import split_suggestions
    from app.services.document_tools.document_ir import ToolError
    try:
        return split_suggestions(storage.resolve(source.storage_key), page_index, target_height_pt, axis,
            storage.decrypt_password(source.credential_ciphertext) or None)
    except ToolError as exc:
        service.fail(exc.code, exc.message, 422)
