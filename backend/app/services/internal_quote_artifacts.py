from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteArtifactHandoff,
    InternalQuoteAttachment,
    InternalQuoteExportFile,
    InternalQuoteImportBatch,
    InternalQuoteReferenceSet,
    InternalQuoteSection,
)
from app.schemas.internal_quote import (
    InternalQuoteAttachmentOut,
    InternalQuoteExportFileOut,
    InternalQuoteImportConfirmOut,
    InternalQuoteImportConfirmRequest,
    InternalQuoteImportPreviewOut,
)
from app.services.auth import AuthContext, now_text
from app.services.internal_quote import (
    MUTABLE_SECTION_STATUSES,
    _add_audit,
    _add_revision,
    _calculate_and_apply,
    _check_revision,
    _derive_quote_status,
    _ensure_active,
    _ensure_section_participates,
    _get_quote,
    _get_section,
    _invalidate_downstream_dependencies,
    _json_object,
    _section_out,
    ensure_quote_permission,
    ensure_quote_read,
    ensure_section_permission,
)
from app.services.internal_quote_calculator import CalculationInputError, canonical_json, content_hash
from app.services.internal_quote_excel import (
    P3_TEMPLATE_VERSION,
    P4_TEMPLATE_VERSION,
    build_internal_quote_workbook,
)
from app.services.internal_quote_import import IMPORT_TYPE_DEPARTMENTS, parse_internal_quote_workbook


MAX_IMPORT_SIZE = 15 * 1024 * 1024
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
IMPORT_EXTENSIONS = {".xlsx", ".xlsm"}
ATTACHMENT_CONTENT_TYPES = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".xls": "application/vnd.ms-excel",
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
OOXML_EXTENSIONS = {".xlsx", ".xlsm", ".docx"}
OLE_EXTENSIONS = {".xls", ".doc"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
EXPORT_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def safe_file_name(value: str) -> str:
    normalized = (value or "").replace("\\", "/")
    name = Path(normalized).name.strip()
    if not name or name in {".", ".."}:
        raise HTTPException(status_code=400, detail="文件名无效")
    return name[:255]


def _validate_file_size(content: bytes, limit: int, label: str) -> None:
    if not content:
        raise HTTPException(status_code=400, detail=f"{label}为空")
    if len(content) > limit:
        raise HTTPException(status_code=413, detail=f"{label}超过 {limit // 1024 // 1024}MB 限制")


def _validate_import_file(file_name: str, content: bytes) -> None:
    extension = Path(file_name).suffix.lower()
    if extension not in IMPORT_EXTENSIONS:
        raise HTTPException(status_code=400, detail="导入仅支持 .xlsx/.xlsm；旧 .xls 请先另存为 xlsx")
    _validate_file_size(content, MAX_IMPORT_SIZE, "Excel 文件")
    if not content.startswith(b"PK"):
        raise HTTPException(status_code=400, detail="Excel 文件头无效")


def _validate_attachment(file_name: str, content: bytes) -> tuple[str, str]:
    extension = Path(file_name).suffix.lower()
    if extension not in ATTACHMENT_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="附件格式不在允许的 Excel/PDF/Word/图片白名单内")
    _validate_file_size(content, MAX_ATTACHMENT_SIZE, "附件")
    valid = True
    if extension in OOXML_EXTENSIONS:
        valid = content.startswith(b"PK")
    elif extension in OLE_EXTENSIONS:
        valid = content.startswith(b"\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1")
    elif extension == ".pdf":
        valid = content.startswith(b"%PDF-")
    elif extension == ".png":
        valid = content.startswith(b"\x89PNG\r\n\x1a\n")
    elif extension in {".jpg", ".jpeg"}:
        valid = content.startswith(b"\xff\xd8\xff")
    elif extension == ".webp":
        valid = len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"
    if not valid:
        raise HTTPException(status_code=400, detail="附件真实文件头与扩展名不匹配")
    return extension, ATTACHMENT_CONTENT_TYPES[extension]


def _preview_payload(batch: InternalQuoteImportBatch) -> dict[str, Any]:
    preview = _json_object(batch.preview_json)
    return {
        "batch_id": batch.id,
        "quote_id": batch.quote_id,
        "import_type": batch.import_type,
        "target_department": batch.target_department,
        "source_file_name": batch.source_file_name,
        "source_sha256": batch.source_sha256,
        "source_size_bytes": batch.source_size_bytes,
        "preview_schema_version": batch.preview_schema_version,
        "target_revision": batch.target_revision,
        "sheet_name": str(preview.get("sheet_name", "")),
        "header_row": int(preview.get("header_row", 0) or 0),
        "row_count": int(preview.get("row_count", 0) or 0),
        "payload_fragment": preview.get("payload_fragment", {}),
        "diff_summary": preview.get("diff_summary", {}),
        "warnings": preview.get("warnings", []),
        "status": batch.status,
        "created_by_name": batch.created_by_name,
        "created_at": batch.created_at,
        "confirm_mode": batch.confirm_mode,
        "confirmed_revision": batch.confirmed_revision,
        "confirmed_by_name": batch.confirmed_by_name,
        "confirmed_at": batch.confirmed_at,
    }


def _import_out(batch: InternalQuoteImportBatch) -> InternalQuoteImportPreviewOut:
    return InternalQuoteImportPreviewOut.model_validate(_preview_payload(batch))


def create_import_preview(
    db: Session,
    quote_id: str,
    import_type: str,
    file_name: str,
    content: bytes,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteImportPreviewOut:
    if import_type not in IMPORT_TYPE_DEPARTMENTS:
        raise HTTPException(status_code=404, detail="不支持的内部报价导入类型")
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    target_department = IMPORT_TYPE_DEPARTMENTS[import_type]
    ensure_section_permission(db, user, quote.factory_id, target_department, "edit")
    section = _get_section(db, quote.id, target_department)
    _ensure_section_participates(section)
    clean_name = safe_file_name(file_name)
    _validate_import_file(clean_name, content)

    reference = db.get(InternalQuoteReferenceSet, quote.reference_snapshot_id)
    snapshot = _json_object(reference.snapshot_json) if reference is not None else {}
    fx_value = snapshot.get("fx", {}).get("rmb_hkd", "0.85") if isinstance(snapshot.get("fx", {}), dict) else "0.85"
    try:
        parsed = parse_internal_quote_workbook(
            content,
            import_type,
            rmb_hkd=Decimal(str(fx_value)),
            fallback_qty=Decimal(str(max(quote.qty, 1))),
        )
    except (ValueError, ArithmeticError) as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    existing_payload = _json_object(section.payload_json)
    list_field = {
        "mold": "molds",
        "hardware": "materials",
        "electronic": "components",
        "painting": "rows",
        "sewing": "groups",
        "assembly": "groups",
    }[import_type]
    existing_list = existing_payload.get(list_field, [])
    if not isinstance(existing_list, list):
        existing_list = []
    if import_type == "hardware":
        existing_list = [
            row for row in existing_list
            if isinstance(row, dict) and row.get("category") == "hardware"
        ]

    preview = {
        "sheet_name": parsed.sheet_name,
        "header_row": parsed.header_row,
        "row_count": parsed.row_count,
        "payload_fragment": parsed.payload_fragment,
        "diff_summary": {
            "target_revision": section.revision,
            "existing_rows": len(existing_list),
            "imported_rows": parsed.row_count,
            "replace_result_rows": parsed.row_count,
        },
        "warnings": parsed.warnings,
    }
    preview["diff_summary"]["append_result_rows"] = (
        int(preview["diff_summary"]["existing_rows"]) + parsed.row_count
    )
    batch = InternalQuoteImportBatch(
        id=f"IQIMP-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        import_type=import_type,
        target_department=parsed.target_department,
        source_file_name=clean_name,
        source_sha256=digest(content),
        source_size_bytes=len(content),
        status="previewed",
        preview_schema_version="p3-v1",
        preview_json=canonical_json(preview),
        target_revision=section.revision,
        confirm_mode="",
        confirmed_revision=0,
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=now_text(),
        confirmed_by="",
        confirmed_by_name="",
        confirmed_at="",
    )
    db.add(batch)
    _add_audit(
        db,
        quote,
        user,
        "import_preview",
        department=target_department,
        detail=json.dumps(
            {
                "batch_id": batch.id,
                "import_type": import_type,
                "source_file_name": clean_name,
                "source_sha256": batch.source_sha256,
                "row_count": parsed.row_count,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        new_revision=section.revision,
        request=request,
    )
    db.commit()
    db.refresh(batch)
    return _import_out(batch)


def list_import_batches(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteImportPreviewOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    batches = db.scalars(
        select(InternalQuoteImportBatch)
        .where(InternalQuoteImportBatch.quote_id == quote.id)
        .order_by(InternalQuoteImportBatch.created_at.desc(), InternalQuoteImportBatch.id.desc())
    ).all()
    return [_import_out(batch) for batch in batches]


def _add_decimal_values(left: object, right: object) -> str:
    try:
        result = Decimal(str(left or 0)) + Decimal(str(right or 0))
    except ArithmeticError:
        result = Decimal(str(right or 0))
    return format(result, "f")


def _merge_import_payload(
    import_type: str,
    current: dict[str, Any],
    fragment: dict[str, Any],
    mode: str,
) -> dict[str, Any]:
    merged = json.loads(json.dumps(current, ensure_ascii=False))
    list_field = {
        "mold": "molds",
        "hardware": "materials",
        "electronic": "components",
        "painting": "rows",
        "sewing": "groups",
        "assembly": "groups",
    }[import_type]
    imported_rows = fragment.get(list_field, [])
    if not isinstance(imported_rows, list):
        raise HTTPException(status_code=400, detail="导入预览结构无效")
    existing_rows = merged.get(list_field, [])
    if not isinstance(existing_rows, list):
        existing_rows = []
    if import_type == "hardware" and mode == "replace":
        retained_rows = [
            row for row in existing_rows
            if not isinstance(row, dict) or row.get("category") != "hardware"
        ]
        merged[list_field] = [*retained_rows, *imported_rows]
    else:
        merged[list_field] = imported_rows if mode == "replace" else [*existing_rows, *imported_rows]

    if import_type == "mold" and fragment.get("amortization_qty"):
        if mode == "replace" or not merged.get("amortization_qty"):
            merged["amortization_qty"] = fragment["amortization_qty"]
    elif import_type == "electronic":
        additive_fields = {
            "bonding_hkd",
            "smt_hkd",
            "labor_hkd",
            "testing_hkd",
            "packaging_hkd",
            "tax_credit_difference_hkd",
        }
        for key, value in fragment.items():
            if key == "components":
                continue
            if mode == "append" and key in additive_fields:
                merged[key] = _add_decimal_values(merged.get(key), value)
            elif mode == "replace" or key not in merged:
                merged[key] = value
    return merged


def confirm_import_batch(
    db: Session,
    quote_id: str,
    batch_id: str,
    payload: InternalQuoteImportConfirmRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteImportConfirmOut:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    batch = db.scalar(
        select(InternalQuoteImportBatch)
        .where(
            InternalQuoteImportBatch.id == batch_id,
            InternalQuoteImportBatch.quote_id == quote.id,
        )
        .with_for_update()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="导入预览批次不存在")
    ensure_section_permission(db, user, quote.factory_id, batch.target_department, "edit")
    if batch.status != "previewed":
        raise HTTPException(status_code=409, detail="该导入批次已确认，不能重复写入")

    section = _get_section(db, quote.id, batch.target_department)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in MUTABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="目标分段当前状态不可导入，请先重新打开")
    preview = _json_object(batch.preview_json)
    fragment = preview.get("payload_fragment", {})
    if not isinstance(fragment, dict):
        raise HTTPException(status_code=400, detail="导入预览批次结构无效")

    old_revision = section.revision
    section.payload_json = canonical_json(
        _merge_import_payload(
            batch.import_type,
            _json_object(section.payload_json),
            fragment,
            payload.mode,
        )
    )
    section.status = "draft"
    section.revision += 1
    section.filled_by = user.display_name
    section.filled_at = now_text()
    section.review_comment = ""
    section.updated_at = now_text()
    try:
        _calculate_and_apply(db, quote, section, user)
    except CalculationInputError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    reason = f"import_confirm:{batch.import_type}:{payload.mode}:{batch.id}"
    _add_revision(db, quote, section, user, reason=reason)
    _invalidate_downstream_dependencies(db, quote, user, section.department, request)
    _derive_quote_status(db, quote)

    batch.status = "confirmed"
    batch.confirm_mode = payload.mode
    batch.confirmed_revision = section.revision
    batch.confirmed_by = user.id
    batch.confirmed_by_name = user.display_name
    batch.confirmed_at = now_text()
    _add_audit(
        db,
        quote,
        user,
        "import_confirm",
        department=section.department,
        detail=json.dumps(
            {
                "batch_id": batch.id,
                "import_type": batch.import_type,
                "mode": payload.mode,
                "source_sha256": batch.source_sha256,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        old_revision=old_revision,
        new_revision=section.revision,
        reason=reason,
        request=request,
    )
    db.commit()
    db.refresh(batch)
    db.refresh(section)
    return InternalQuoteImportConfirmOut(batch=_import_out(batch), section=_section_out(section))


def _attachment_out(attachment: InternalQuoteAttachment) -> InternalQuoteAttachmentOut:
    return InternalQuoteAttachmentOut(
        id=attachment.id,
        quote_id=attachment.quote_id,
        department=attachment.department,
        file_name=attachment.file_name,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        sha256=attachment.sha256,
        uploaded_by=attachment.uploaded_by,
        uploaded_by_name=attachment.uploaded_by_name,
        uploaded_at=attachment.uploaded_at,
    )


def upload_attachment(
    db: Session,
    quote_id: str,
    department: str,
    file_name: str,
    content: bytes,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteAttachmentOut:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    ensure_section_permission(db, user, quote.factory_id, department, "edit")
    section = _get_section(db, quote.id, department)
    _ensure_section_participates(section)
    clean_name = safe_file_name(file_name)
    _extension, content_type = _validate_attachment(clean_name, content)
    sha256 = digest(content)
    duplicate = db.scalar(
        select(InternalQuoteAttachment.id).where(
            InternalQuoteAttachment.quote_id == quote.id,
            InternalQuoteAttachment.department == department,
            InternalQuoteAttachment.sha256 == sha256,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="该分段已存在内容相同的附件")
    attachment = InternalQuoteAttachment(
        id=f"IQATT-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        department=department,
        file_name=clean_name,
        content_type=content_type,
        size_bytes=len(content),
        sha256=sha256,
        content=content,
        uploaded_by=user.id,
        uploaded_by_name=user.display_name,
        uploaded_at=now_text(),
    )
    db.add(attachment)
    _add_audit(
        db,
        quote,
        user,
        "upload_attachment",
        department=department,
        detail=json.dumps(
            {"attachment_id": attachment.id, "file_name": clean_name, "sha256": sha256},
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    db.refresh(attachment)
    return _attachment_out(attachment)


def list_attachments(
    db: Session,
    quote_id: str,
    department: str,
    user: AuthContext,
) -> list[InternalQuoteAttachmentOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    statement = select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == quote.id)
    if department:
        statement = statement.where(InternalQuoteAttachment.department == department)
    statement = statement.order_by(InternalQuoteAttachment.uploaded_at.desc(), InternalQuoteAttachment.id.desc())
    return [_attachment_out(item) for item in db.scalars(statement).all()]


def get_attachment_download(
    db: Session,
    quote_id: str,
    attachment_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteAttachment:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    attachment = db.scalar(
        select(InternalQuoteAttachment).where(
            InternalQuoteAttachment.id == attachment_id,
            InternalQuoteAttachment.quote_id == quote.id,
        )
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    _add_audit(
        db,
        quote,
        user,
        "download_attachment",
        department=attachment.department,
        detail=attachment.id,
        request=request,
    )
    db.commit()
    return attachment


def _export_out(record: InternalQuoteExportFile) -> InternalQuoteExportFileOut:
    return InternalQuoteExportFileOut(
        id=record.id,
        quote_id=record.quote_id,
        file_name=record.file_name,
        content_type=record.content_type,
        size_bytes=record.size_bytes,
        sha256=record.sha256,
        section_revisions={
            str(key): int(value)
            for key, value in _json_object(record.section_revisions_json).items()
        },
        status=record.status,
        template_version=record.template_version,
        formula_version=record.formula_version,
        reference_snapshot_id=record.reference_snapshot_id,
        header_revision=record.header_revision,
        release_stage=record.release_stage,
        export_manifest=_json_object(record.export_manifest_json),
        exported_by=record.exported_by,
        exported_by_name=record.exported_by_name,
        exported_at=record.exported_at,
        superseded_at=record.superseded_at,
    )


def _ensure_export_permission(db: Session, quote: InternalQuote, user: AuthContext) -> None:
    ensure_quote_permission(
        db,
        user,
        "internal_quote:export",
        quote.factory_id,
        ("sales-business",),
    )


def _supersede_outdated_exports(
    db: Session,
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> None:
    current_revisions = {section.department: section.revision for section in sections}
    records = db.scalars(
        select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.quote_id == quote.id,
            InternalQuoteExportFile.status == "current",
        )
    ).all()
    timestamp = now_text()
    superseded_ids: list[str] = []
    for record in records:
        stored_revisions = {
            str(key): int(value)
            for key, value in _json_object(record.section_revisions_json).items()
        }
        if (
            record.header_revision != quote.header_revision
            or record.reference_snapshot_id != quote.reference_snapshot_id
            or record.formula_version != quote.formula_version
            or stored_revisions != current_revisions
        ):
            record.status = "superseded"
            record.superseded_at = timestamp
            superseded_ids.append(record.id)
    if superseded_ids:
        handoffs = db.scalars(
            select(InternalQuoteArtifactHandoff).where(
                InternalQuoteArtifactHandoff.export_id.in_(superseded_ids),
                InternalQuoteArtifactHandoff.status.in_(("available", "consumed")),
            )
        ).all()
        for handoff in handoffs:
            handoff.status = "revoked"
            handoff.revoked_at = timestamp
            handoff.revoke_reason = "内部报价 revision、参考快照或公式版本已变化"


def _export_sections(db: Session, quote: InternalQuote) -> list[InternalQuoteSection]:
    return db.scalars(
        select(InternalQuoteSection)
        .where(InternalQuoteSection.quote_id == quote.id)
        .order_by(InternalQuoteSection.id)
    ).all()


def _create_artifact_handoff(
    db: Session,
    quote: InternalQuote,
    record: InternalQuoteExportFile,
    user: AuthContext,
) -> InternalQuoteArtifactHandoff:
    existing = db.scalar(
        select(InternalQuoteArtifactHandoff).where(
            InternalQuoteArtifactHandoff.export_id == record.id
        )
    )
    if existing is not None:
        return existing
    export_manifest = _json_object(record.export_manifest_json)
    handoff_manifest = {
        "schema_version": "internal-quote-handoff-v1",
        "quote_id": quote.id,
        "quote_no": quote.quote_no,
        "version_label": quote.version_label,
        "customer": quote.customer,
        "product_name": quote.product_name,
        "qty": quote.qty,
        "target_customer_price": quote.target_customer_price,
        "release_revision": quote.final_release_revision,
        "release_manifest_sha256": export_manifest.get("final_release_manifest_sha256", ""),
        "export_id": record.id,
        "file_name": record.file_name,
        "file_sha256": record.sha256,
        "template_version": record.template_version,
        "formula_version": record.formula_version,
        "reference_snapshot_id": record.reference_snapshot_id,
        "section_revisions": _json_object(record.section_revisions_json),
    }
    handoff = InternalQuoteArtifactHandoff(
        id=f"IQHAND-{uuid4().hex}",
        quote_id=quote.id,
        export_id=record.id,
        factory_id=quote.factory_id,
        customer=quote.customer,
        quote_no=quote.quote_no,
        version_label=quote.version_label,
        release_revision=quote.final_release_revision,
        status="available",
        artifact_manifest_json=canonical_json(handoff_manifest),
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=now_text(),
        consumed_by="",
        consumed_by_name="",
        consumed_at="",
        consumer_reference="",
        revoked_at="",
        revoke_reason="",
    )
    db.add(handoff)
    return handoff


def create_controlled_export(
    db: Session,
    quote_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteExportFileOut:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    _ensure_export_permission(db, quote, user)
    sections = _export_sections(db, quote)
    required = [section for section in sections if section.is_required]
    incomplete = [
        section.department
        for section in required
        if section.status not in {"approved", "not_applicable"}
    ]
    invalid = [
        section.department
        for section in required
        if section.status == "approved"
        and (section.calculation_status != "valid" or section.dependency_status != "current")
    ]
    if incomplete or invalid:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "所有必需分段通过且计算有效后才能生成受控 XLSX",
                "incomplete_sections": incomplete,
                "invalid_calculations": invalid,
            },
        )

    is_final_release = (
        quote.status in {"fully_approved", "exported"}
        and quote.final_release_status == "approved"
        and quote.final_release_revision > 0
    )
    if is_final_release:
        existing_handoff = db.scalar(
            select(InternalQuoteArtifactHandoff).where(
                InternalQuoteArtifactHandoff.quote_id == quote.id,
                InternalQuoteArtifactHandoff.release_revision == quote.final_release_revision,
            )
        )
        if existing_handoff is not None:
            existing_export = db.get(InternalQuoteExportFile, existing_handoff.export_id)
            if existing_export is not None and existing_export.release_stage == "p4_final_approved":
                return _export_out(existing_export)
    release_stage = "p4_final_approved" if is_final_release else "p3_section_approved"
    template_version = P4_TEMPLATE_VERSION if is_final_release else P3_TEMPLATE_VERSION
    _supersede_outdated_exports(db, quote, sections)
    section_revisions = {section.department: section.revision for section in sections}
    manifest = {
        "template_version": template_version,
        "formula_version": quote.formula_version,
        "reference_snapshot_id": quote.reference_snapshot_id,
        "header_revision": quote.header_revision,
        "target_customer_price": quote.target_customer_price,
        "section_revisions": section_revisions,
        "section_calculation_hashes": {
            section.department: section.calculation_hash for section in sections
        },
        "release_stage": release_stage,
        "p4_final_release_required": not is_final_release,
        "final_release_revision": quote.final_release_revision if is_final_release else 0,
        "final_release_manifest_sha256": (
            str(_json_object(quote.final_submission_manifest_json).get("manifest_sha256", ""))
            if is_final_release
            else ""
        ),
        "final_submitted_by": quote.final_submitted_by if is_final_release else "",
        "final_submitted_by_name": quote.final_submitted_by_name if is_final_release else "",
        "final_submitted_at": quote.final_submitted_at if is_final_release else "",
        "final_reviewed_by": quote.final_reviewed_by if is_final_release else "",
        "final_reviewed_by_name": quote.final_reviewed_by_name if is_final_release else "",
        "final_reviewed_at": quote.final_reviewed_at if is_final_release else "",
    }
    manifest["manifest_sha256"] = content_hash(manifest)
    reference_set = db.scalar(
        select(InternalQuoteReferenceSet).where(
            InternalQuoteReferenceSet.id == quote.reference_snapshot_id,
            InternalQuoteReferenceSet.quote_id == quote.id,
        )
    )
    reference_snapshot = _json_object(reference_set.snapshot_json) if reference_set else {}
    content = build_internal_quote_workbook(quote, sections, manifest, reference_snapshot)
    record = InternalQuoteExportFile(
        id=f"IQEXP-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        file_name=safe_file_name(
            f"{quote.quote_no}_{quote.version_label}_内部报价"
            f"{'_最终放行' if is_final_release else ''}.xlsx"
        ),
        content_type=EXPORT_CONTENT_TYPE,
        size_bytes=len(content),
        sha256=digest(content),
        section_revisions_json=canonical_json(section_revisions),
        status="current",
        content=content,
        template_version=template_version,
        formula_version=quote.formula_version,
        reference_snapshot_id=quote.reference_snapshot_id,
        header_revision=quote.header_revision,
        release_stage=release_stage,
        export_manifest_json=canonical_json(manifest),
        exported_by=user.id,
        exported_by_name=user.display_name,
        exported_at=now_text(),
        superseded_at="",
    )
    previous = db.scalars(
        select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.quote_id == quote.id,
            InternalQuoteExportFile.status == "current",
        )
    ).all()
    for item in previous:
        item.status = "superseded"
        item.superseded_at = now_text()
        handoffs = db.scalars(
            select(InternalQuoteArtifactHandoff).where(
                InternalQuoteArtifactHandoff.export_id == item.id,
                InternalQuoteArtifactHandoff.status.in_(("available", "consumed")),
            )
        ).all()
        for handoff in handoffs:
            handoff.status = "revoked"
            handoff.revoked_at = now_text()
            handoff.revoke_reason = "已生成后续内部报价导出文件"
    db.add(record)
    db.flush()
    if is_final_release:
        _create_artifact_handoff(db, quote, record, user)
        quote.status = "exported"
        quote.updated_at = now_text()
    _add_audit(
        db,
        quote,
        user,
        "export",
        detail=json.dumps(
            {"export_id": record.id, "sha256": record.sha256, "release_stage": record.release_stage},
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    db.refresh(record)
    return _export_out(record)


def list_export_files(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteExportFileOut]:
    quote = _get_quote(db, quote_id)
    _ensure_export_permission(db, quote, user)
    sections = _export_sections(db, quote)
    _supersede_outdated_exports(db, quote, sections)
    records = db.scalars(
        select(InternalQuoteExportFile)
        .where(InternalQuoteExportFile.quote_id == quote.id)
        .order_by(InternalQuoteExportFile.exported_at.desc(), InternalQuoteExportFile.id.desc())
    ).all()
    db.commit()
    return [_export_out(record) for record in records]


def get_export_download(
    db: Session,
    quote_id: str,
    export_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteExportFile:
    quote = _get_quote(db, quote_id)
    _ensure_export_permission(db, quote, user)
    sections = _export_sections(db, quote)
    _supersede_outdated_exports(db, quote, sections)
    record = db.scalar(
        select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.id == export_id,
            InternalQuoteExportFile.quote_id == quote.id,
        )
    )
    if record is None:
        raise HTTPException(status_code=404, detail="导出文件不存在")
    _add_audit(
        db,
        quote,
        user,
        "download_export",
        detail=record.id,
        request=request,
    )
    db.commit()
    return record
