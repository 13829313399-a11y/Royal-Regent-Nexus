from __future__ import annotations

import hashlib
import json
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteAttachment,
    InternalQuoteExportFile,
    InternalQuoteImportBatch,
    InternalQuoteSection,
)
from app.schemas.internal_quote import (
    InternalQuoteAttachmentOut,
    InternalQuoteDetailOut,
    InternalQuoteExportFileOut,
    InternalQuoteImportConfirmRequest,
    InternalQuoteImportPreviewOut,
    InternalQuoteSectionPayload,
    InternalQuoteSectionUpdateRequest,
)
from app.services.auth import AuthContext
from app.services.internal_quote import add_quote_audit, now_text, parse_payload, update_section
from app.services.internal_quote_import import parse_internal_quote_workbook


MAX_IMPORT_SIZE = 15 * 1024 * 1024
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".xlsx", ".xlsm", ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".docx",
}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_file_name(value: str) -> str:
    name = Path(value or "").name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="文件名无效")
    return name[:255]


def create_import_preview(
    db: Session,
    quote: InternalQuote,
    import_type: str,
    file_name: str,
    content: bytes,
    current_user: AuthContext,
) -> InternalQuoteImportPreviewOut:
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(content) > MAX_IMPORT_SIZE:
        raise HTTPException(status_code=413, detail="Excel 文件不能超过 15MB")
    normalized_name = safe_file_name(file_name)
    if Path(normalized_name).suffix.lower() not in {".xlsx", ".xlsm"}:
        raise HTTPException(status_code=400, detail="请上传 xlsx 或 xlsm 工作簿")
    try:
        parsed = parse_internal_quote_workbook(content, import_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    batch_id = f"IQI-{uuid4().hex[:20].upper()}"
    now = now_text()
    preview_payload = {
        "sheet_name": parsed.sheet_name,
        "header_row": parsed.header_row,
        "rows": [row.model_dump(mode="json") for row in parsed.rows],
        "parameters": parsed.parameters,
        "warnings": parsed.warnings,
    }
    batch = InternalQuoteImportBatch(
        id=batch_id,
        quote_id=quote.id,
        factory_id=quote.factory_id,
        import_type=import_type,
        target_department=parsed.target_department,
        source_file_name=normalized_name,
        source_sha256=digest(content),
        status="previewed",
        preview_json=json.dumps(preview_payload, ensure_ascii=False),
        created_by=current_user.id,
        created_by_name=current_user.display_name or current_user.username,
        created_at=now,
    )
    db.add(batch)
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "import_preview",
        department=parsed.target_department,
        detail=f"{normalized_name} · {len(parsed.rows)} 行 · SHA256 {batch.source_sha256[:12]}",
    )
    db.commit()
    return import_batch_to_out(batch)


def load_import_batch(db: Session, quote_id: str, batch_id: str) -> InternalQuoteImportBatch:
    batch = db.get(InternalQuoteImportBatch, batch_id)
    if batch is None or batch.quote_id != quote_id:
        raise HTTPException(status_code=404, detail="内部报价导入预览不存在")
    return batch


def list_import_batches(db: Session, quote_id: str) -> list[InternalQuoteImportPreviewOut]:
    batches = db.scalars(
        select(InternalQuoteImportBatch)
        .where(InternalQuoteImportBatch.quote_id == quote_id)
        .order_by(InternalQuoteImportBatch.created_at.desc(), InternalQuoteImportBatch.id.desc())
    ).all()
    return [import_batch_to_out(batch) for batch in batches]


def import_batch_to_out(batch: InternalQuoteImportBatch) -> InternalQuoteImportPreviewOut:
    try:
        preview = json.loads(batch.preview_json or "{}")
    except json.JSONDecodeError:
        preview = {}
    return InternalQuoteImportPreviewOut(
        batch_id=batch.id,
        quote_id=batch.quote_id,
        import_type=batch.import_type,
        target_department=batch.target_department,
        source_file_name=batch.source_file_name,
        source_sha256=batch.source_sha256,
        sheet_name=str(preview.get("sheet_name") or ""),
        header_row=int(preview.get("header_row") or 0),
        rows=preview.get("rows") if isinstance(preview.get("rows"), list) else [],
        parameters=preview.get("parameters") if isinstance(preview.get("parameters"), dict) else {},
        warnings=preview.get("warnings") if isinstance(preview.get("warnings"), list) else [],
        status=batch.status,
        created_by_name=batch.created_by_name,
        created_at=batch.created_at,
        confirmed_by_name=batch.confirmed_by_name,
        confirmed_at=batch.confirmed_at,
    )


def confirm_import_batch(
    db: Session,
    quote: InternalQuote,
    batch_id: str,
    request: InternalQuoteImportConfirmRequest,
    current_user: AuthContext,
) -> InternalQuoteDetailOut:
    batch = load_import_batch(db, quote.id, batch_id)
    if batch.status != "previewed":
        raise HTTPException(status_code=409, detail="该导入预览已经确认，不能重复合并")
    preview = import_batch_to_out(batch)
    section = db.scalar(select(InternalQuoteSection).where(
        InternalQuoteSection.quote_id == quote.id,
        InternalQuoteSection.department == batch.target_department,
    ))
    if section is None:
        raise HTTPException(status_code=404, detail="导入目标分段不存在")

    current_payload = parse_payload(section.payload_json)
    rows = preview.rows if request.mode == "replace" else [*current_payload.rows, *preview.rows]
    parameters = {**current_payload.parameters, **preview.parameters}
    merged_payload = InternalQuoteSectionPayload(
        currency="HKD",
        loss_pct=current_payload.loss_pct,
        parameters=parameters,
        reference_snapshot=current_payload.reference_snapshot,
        rows=rows,
    )
    now = now_text()
    batch.status = "confirmed"
    batch.confirmed_by = current_user.id
    batch.confirmed_by_name = current_user.display_name or current_user.username
    batch.confirmed_at = now
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "import_confirm",
        department=batch.target_department,
        detail=f"{batch.source_file_name} · {request.mode} · {len(preview.rows)} 行",
    )
    return update_section(
        db,
        quote,
        batch.target_department,
        InternalQuoteSectionUpdateRequest(
            revision=request.revision,
            payload=merged_payload,
            submit=False,
        ),
        current_user,
    )


def create_attachment(
    db: Session,
    quote: InternalQuote,
    department: str,
    file_name: str,
    content_type: str,
    content: bytes,
    current_user: AuthContext,
) -> InternalQuoteAttachmentOut:
    if not content:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(content) > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=413, detail="附件不能超过 10MB")
    normalized_name = safe_file_name(file_name)
    if Path(normalized_name).suffix.lower() not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="附件仅支持 Excel、PDF、Word 和常见图片格式")
    if department and department not in {
        "sales", "engineering", "electronic", "molding", "painting", "slush", "sewing", "assembly",
    }:
        raise HTTPException(status_code=400, detail="附件部门无效")
    now = now_text()
    attachment = InternalQuoteAttachment(
        id=f"IQA-FILE-{uuid4().hex[:18].upper()}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        department=department,
        file_name=normalized_name,
        content_type=(content_type or "application/octet-stream")[:128],
        size_bytes=len(content),
        sha256=digest(content),
        content=content,
        uploaded_by=current_user.id,
        uploaded_by_name=current_user.display_name or current_user.username,
        uploaded_at=now,
    )
    db.add(attachment)
    add_quote_audit(
        db,
        quote.id,
        current_user,
        "attachment_upload",
        department=department,
        detail=f"{normalized_name} · {len(content)} bytes · SHA256 {attachment.sha256[:12]}",
    )
    db.commit()
    return attachment_to_out(attachment)


def list_attachments(db: Session, quote_id: str) -> list[InternalQuoteAttachmentOut]:
    rows = db.scalars(
        select(InternalQuoteAttachment)
        .where(InternalQuoteAttachment.quote_id == quote_id)
        .order_by(InternalQuoteAttachment.uploaded_at.desc(), InternalQuoteAttachment.id.desc())
    ).all()
    return [attachment_to_out(row) for row in rows]


def get_attachment(db: Session, quote_id: str, attachment_id: str) -> InternalQuoteAttachment:
    row = db.get(InternalQuoteAttachment, attachment_id)
    if row is None or row.quote_id != quote_id:
        raise HTTPException(status_code=404, detail="内部报价附件不存在")
    return row


def attachment_to_out(row: InternalQuoteAttachment) -> InternalQuoteAttachmentOut:
    return InternalQuoteAttachmentOut(
        id=row.id,
        quote_id=row.quote_id,
        department=row.department,
        file_name=row.file_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        uploaded_by_name=row.uploaded_by_name,
        uploaded_at=row.uploaded_at,
    )


def create_export_file(
    db: Session,
    quote: InternalQuote,
    detail: InternalQuoteDetailOut,
    file_name: str,
    content: bytes,
    current_user: AuthContext,
) -> InternalQuoteExportFile:
    revisions = {section.department: section.revision for section in detail.sections}
    exported_at = now_text()
    current_files = db.scalars(
        select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.quote_id == quote.id,
            InternalQuoteExportFile.status == "current",
        )
    ).all()
    for current_file in current_files:
        current_file.status = "superseded"
        current_file.superseded_at = exported_at
    row = InternalQuoteExportFile(
        id=f"IQE-{uuid4().hex[:20].upper()}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        file_name=safe_file_name(file_name),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=len(content),
        sha256=digest(content),
        section_revisions_json=json.dumps(revisions, ensure_ascii=False),
        status="current",
        content=content,
        exported_by=current_user.id,
        exported_by_name=current_user.display_name or current_user.username,
        exported_at=exported_at,
    )
    db.add(row)
    return row


def list_export_files(db: Session, quote_id: str) -> list[InternalQuoteExportFileOut]:
    rows = db.scalars(
        select(InternalQuoteExportFile)
        .where(InternalQuoteExportFile.quote_id == quote_id)
        .order_by(InternalQuoteExportFile.exported_at.desc(), InternalQuoteExportFile.id.desc())
    ).all()
    return [export_to_out(row) for row in rows]


def get_export_file(db: Session, quote_id: str, export_id: str) -> InternalQuoteExportFile:
    row = db.get(InternalQuoteExportFile, export_id)
    if row is None or row.quote_id != quote_id:
        raise HTTPException(status_code=404, detail="受控导出文件不存在")
    return row


def export_to_out(row: InternalQuoteExportFile) -> InternalQuoteExportFileOut:
    try:
        revisions = json.loads(row.section_revisions_json or "{}")
    except json.JSONDecodeError:
        revisions = {}
    return InternalQuoteExportFileOut(
        id=row.id,
        quote_id=row.quote_id,
        file_name=row.file_name,
        content_type=row.content_type,
        size_bytes=row.size_bytes,
        sha256=row.sha256,
        section_revisions=revisions if isinstance(revisions, dict) else {},
        status=row.status,
        exported_by_name=row.exported_by_name,
        exported_at=row.exported_at,
        superseded_at=row.superseded_at,
    )


def supersede_export_files(db: Session, quote_id: str, superseded_at: str) -> None:
    rows = db.scalars(select(InternalQuoteExportFile).where(
        InternalQuoteExportFile.quote_id == quote_id,
        InternalQuoteExportFile.status == "current",
    )).all()
    for row in rows:
        row.status = "superseded"
        row.superseded_at = superseded_at
