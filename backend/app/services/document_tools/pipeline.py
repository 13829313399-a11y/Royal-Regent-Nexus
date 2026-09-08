import copy
import json
import logging
import os
import re
import shutil
import threading
import time
import zipfile
from pathlib import Path

from sqlalchemy import case, select, update

from app.core.config import settings
from app.models.document_tools import DocumentToolArtifact as Artifact, DocumentToolCorrection as Correction, DocumentToolJob as Job, DocumentToolSource as Source
from app.services.document_tools import job_service as jobs, storage
from app.services.document_tools.document_ir import Cancelled, DocumentIR, EngineResult, Issue, ToolError, result_file


def validate_source(path: Path, kind: str):
    with path.open("rb") as source:
        signature = source.read(8)
    if kind == "pdf":
        if not signature.startswith(b"%PDF-"):
            raise ToolError("INVALID_FILE", "文件内容不是有效 PDF")
    elif kind in {"doc", "xls"}:
        if not signature.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            raise ToolError("INVALID_FILE", "文件内容与 Office 文件类型不符")
    elif kind in {"docx", "xlsx"}:
        if signature.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
            return  # Password-encrypted OOXML is an OLE container.
        if not zipfile.is_zipfile(path):
            raise ToolError("INVALID_FILE", "Office 文件结构损坏")
        with zipfile.ZipFile(path) as archive:
            info = archive.infolist()
            if len(info) > 20000 or sum(x.file_size for x in info) > 500 * 1024 * 1024:
                raise ToolError("FILE_TOO_COMPLEX", "文档解压体积过大，请拆分后上传")
            names = set(archive.namelist())
            required = "word/document.xml" if kind == "docx" else "xl/workbook.xml"
            if required not in names:
                raise ToolError("INVALID_FILE", "Office 文件类型与内容不一致")
            if any("vbaproject" in n.lower() or "activex" in n.lower() for n in names):
                raise ToolError("MACROS_UNSUPPORTED", "本工具不接受含宏或 ActiveX 的文件，请另存为普通文档")


def apply_corrections(ir, corrections):
    targets = {c.id: c for table in ir.tables for c in table.cells}
    targets.update({b.id: b for b in ir.blocks if b.table_id is None})
    for correction in corrections:
        target = targets.get(correction.target_anchor["target_id"])
        if target is None:
            raise ToolError("ANCHOR_NOT_FOUND", "需要修正的原文位置已不存在，请打开结果重新定位")
        if hasattr(target, "display_text"):
            original_kind = target.value_kind
            target.display_text = correction.new_value
            target.value = correction.new_value
            target.value_kind = "text"
            # Retain a known numeric field only for an unambiguous decimal input.
            # Identifiers, leading-zero strings, formulas and locale ambiguity stay text.
            if original_kind in {"number", "integer", "decimal", "currency"} and re.fullmatch(r"[+-]?(?:0|[1-9]\d*)(?:\.\d+)?", correction.new_value):
                target.value_kind = "decimal" if "." in correction.new_value else "integer"
            target.resolution = "manually_confirmed"
        else:
            target.text = correction.new_value
        target.source.method = "manual"
        for issue in ir.issues:
            if issue.target_id == target.id:
                issue.status = "manually_confirmed"
    return ir


def package_results(db, job, work, progress, cancelled):
    rows = []
    for artifact_id in job.options_json["artifact_ids"]:
        row = jobs.owned(db, Artifact, artifact_id, job.owner_user_id)
        if row.expires_at and row.expires_at <= time.time():
            raise ToolError("ARTIFACT_EXPIRED", "选中的一个结果已到期，请重新生成")
        rows.append(row)
    db.expunge_all()
    db.commit()
    output = work / "文档结果.zip"
    used = set()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for i, row in enumerate(rows):
            if cancelled():
                raise Cancelled()
            name = storage.safe_name(row.filename)
            stem, suffix = Path(name).stem, Path(name).suffix
            duplicate = 1
            while name.casefold() in used:
                duplicate += 1
                name = f"{stem}_{duplicate}{suffix}"
            used.add(name.casefold())
            archive.write(storage.resolve(row.storage_key), name)
            progress("package", i + 1, len(rows))
    return EngineResult(DocumentIR(source_type="package"), [result_file(output, "package")], {"files": len(rows)})


def run_one(session_factory, claimed=None):
    claimed = claimed or jobs.claim_job(session_factory)
    if claimed is None:
        return False
    job_id, token = claimed
    stop = threading.Event()
    lost = threading.Event()

    def keepalive():
        while not stop.wait(max(1, settings.document_tools_lease_seconds / 4)):
            try:
                if not jobs.renew(session_factory, job_id, token):
                    lost.set()
                    return
            except Exception:
                lost.set()
                return

    def cancelled():
        if lost.is_set():
            return True
        with session_factory() as check_db:
            row = check_db.scalar(select(Job.cancel_requested).where(jobs.lease_filter(job_id, token)))
            return row is None or row is True

    def progress(stage, completed=0, total=None):
        if cancelled():
            raise Cancelled()
        jobs.mark_progress(session_factory, job_id, token, stage, completed, total)

    keeper = threading.Thread(target=keepalive, daemon=True)
    work = storage.resolve(f"temp/{job_id}/{token}")
    try:
        work.mkdir(parents=True, exist_ok=False)
        keeper.start()
        with session_factory() as db:
            job = db.get(Job, job_id)
            source = db.get(Source, job.source_id) if job.source_id else None
            options = copy.deepcopy(job.options_json)
            ir = None
            if job.kind == "revise":
                parent = jobs.owned(db, Job, job.parent_job_id, job.owner_user_id, include_deleted=True)
                ir = DocumentIR.model_validate(jobs.load_ir(db, parent))
                ir = apply_corrections(ir, db.scalars(select(Correction).where(Correction.new_job_id == job.id)).all())
            if job.kind == "package":
                result = package_results(db, job, work, progress, cancelled)
            else:
                db.expunge_all()
                db.commit()
                path = storage.resolve(source.storage_key)
                validate_source(path, source.detected_type)
                if source.credential_ciphertext:
                    options["password"] = storage.decrypt_password(source.credential_ciphertext)
                if settings.document_tools_ai_mode == "off":
                    options["ai_mode"] = "off"
                if source.detected_type == "pdf":
                    from app.services.document_tools.pdf_engine import inspect_pdf, convert_pdf
                    result = inspect_pdf(path, options, work, progress, cancelled) if job.kind == "inspect" else convert_pdf(path, job.operation, options, work, progress, cancelled, ir=ir)
                else:
                    from app.services.document_tools.office_engine import inspect_office, convert_office
                    result = inspect_office(path, options, work, progress, cancelled) if job.kind == "inspect" else convert_office(path, job.operation, options, work, progress, cancelled, ir=ir)
                result.ir.source_id = source.id
            # All downstream work uses detached scalars, never a long DB lock.
            db.expunge_all()
        progress("validate", 0, None)
        if job.kind != "inspect" and not any(f["role"] == "preview" for f in result.files):
            from app.services.document_tools.office_engine import render_office
            for item in list(result.files):
                output = Path(item["path"])
                if item["role"] != "result" or output.suffix.lower() not in {".docx", ".xlsx"}:
                    continue
                try:
                    preview = work / (output.stem + "-preview.pdf")
                    render_office(output, preview, {}, work, cancelled)
                    result.files.append(result_file(preview, "preview"))
                except Cancelled:
                    raise
                except ToolError as exc:
                    result.ir.issues.append(Issue(id="preview-unavailable", code=exc.code, message="输出校样未生成：" + exc.message))
        unresolved = [i for i in result.ir.issues if i.status == "open"]
        quality = result.quality or {"checks": [], "note": "仅报告实际执行的检查，不表示完全无损"}
        checks = quality.setdefault("checks", [])
        from app.services.document_tools.validation import validate_outputs
        checks.extend(validate_outputs(result.files))
        quality["issues"] = [i.model_dump() for i in result.ir.issues]
        quality["quality_status"] = "needs_review" if unresolved else "passed" if checks else "not_checked"
        if job.kind == "revise" and not unresolved and any(c.source.method == "manual" for t in result.ir.tables for c in t.cells):
            quality["quality_status"] = "manually_confirmed"
        publish = storage.resolve(f"jobs/{job_id}/{job.artifact_revision}/{token}")
        for block in result.ir.blocks:
            image_path = block.style.get("image_path")
            if image_path:
                image = Path(image_path).resolve()
                if image.is_relative_to(work.resolve()):
                    block.style["image_path"] = str(publish / image.relative_to(work.resolve()))
        storage.atomic_json(work / "ir.json", result.ir.model_dump(mode="json"))
        storage.atomic_json(work / "mapping.json", {"source_id": result.ir.source_id, "mappings": result.ir.mappings})
        storage.atomic_json(work / "quality.json", quality)
        files = list(result.files) + [result_file(work / "ir.json", "ir"), result_file(work / "mapping.json", "mapping"), result_file(work / "quality.json", "report", "检查报告.json")]
        artifacts = []
        publish.parent.mkdir(parents=True, exist_ok=True)
        for item in files:
            path = Path(item["path"]).resolve()
            if not path.is_relative_to(work.resolve()) or not path.is_file() or path.stat().st_size == 0:
                raise ToolError("INVALID_OUTPUT", "生成文件不完整，请重试")
            artifacts.append((item, path.relative_to(work.resolve()), path.stat().st_size, storage.digest(path)))
        if cancelled():
            raise Cancelled()
        # Publication becomes visible only with the final database CAS. Copy to
        # an attempt-private directory: Windows file watchers may hold directory
        # handles that prevent renaming the entire work tree after rendering.
        shutil.copytree(work, publish)
        for _, relative, size, sha in artifacts:
            target = publish / relative
            if target.stat().st_size != size or storage.digest(target) != sha:
                raise ToolError("INVALID_OUTPUT", "结果写入校验失败，请重试")
        with session_factory() as db:
            count = db.execute(update(Job).where(jobs.lease_filter(job_id, token), Job.cancel_requested.is_(False)).values(
                execution_status="succeeded", quality_status=quality["quality_status"],
                summary_json={**result.summary, "review_items": len(unresolved)}, lease_token=None,
                lease_until=None, finished_at=jobs.now(), stage="validate", completed_units=1, total_units=1)).rowcount
            if count != 1:
                db.rollback()
                raise Cancelled()
            for item, relative, size, sha in artifacts:
                db.add(Artifact(id=jobs.uid(), job_id=job_id, owner_user_id=job.owner_user_id,
                    revision=job.artifact_revision, role=item["role"], format=item["format"],
                    filename=storage.safe_name(item["filename"]), storage_key=storage.key_for(publish / relative),
                    size=size, sha256=sha, created_at=jobs.now(), expires_at=(time.time() + settings.document_tools_retention_days * 86400) if settings.document_tools_retention_days else None))
            if job.kind == "inspect":
                manifest = {**result.summary, "pages": [p.model_dump() for p in result.ir.pages],
                    "issues": [i.model_dump() for i in result.ir.issues],
                    "supported_operations": [op for op, (_, types) in jobs.OPERATIONS.items() if source.detected_type in types]}
                storage.atomic_json(publish / "manifest.json", manifest)
                db.execute(update(Source).where(Source.id == source.id, Source.inspection_job_id == job_id).values(inspection_status="succeeded", manifest_key=storage.key_for(publish / "manifest.json")))
            db.commit()
        return True
    except Exception as exc:
        # No raw provider errors, filenames, local paths or credentials in logs.
        if not isinstance(exc, (ToolError, Cancelled)):
            import traceback
            frames = traceback.extract_tb(exc.__traceback__)
            frame = frames[-1] if frames else None
            logging.getLogger(__name__).error("Document task failed: %s at %s:%s", type(exc).__name__, Path(frame.filename).name if frame else "unknown", frame.lineno if frame else 0)
        code = exc.code if isinstance(exc, ToolError) else "PROCESSING_FAILED"
        message = exc.message if isinstance(exc, ToolError) else "文件处理未完成，请检查文档后重试"
        with session_factory() as db:
            job = db.get(Job, job_id)
            if job:
                state = "cancelled" if isinstance(exc, Cancelled) or job.cancel_requested else "awaiting_input" if code in {"PASSWORD_REQUIRED", "INVALID_PASSWORD"} else "failed"
                committed_state = db.execute(update(Job).where(jobs.lease_filter(job_id, token)).values(
                    execution_status=case((Job.cancel_requested.is_(True), "cancelled"), else_=state),
                    error_code=code, error_message=message, lease_token=None, lease_until=None,
                    finished_at=jobs.now()).returning(Job.execution_status)).scalar_one_or_none()
                if committed_state and job.kind == "inspect":
                    db.execute(update(Source).where(Source.id == job.source_id, Source.inspection_job_id == job_id).values(inspection_status=committed_state))
                db.commit()
        return True
    finally:
        stop.set()
        if keeper.ident is not None:
            keeper.join(timeout=2)
        # Remove only this attempt's validated private temp tree.
        if work.exists() and work.resolve().is_relative_to(storage.resolve("temp").resolve()):
            shutil.rmtree(work)
