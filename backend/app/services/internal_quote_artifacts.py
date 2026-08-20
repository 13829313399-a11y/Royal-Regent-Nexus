from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO
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
    InternalQuoteAttachmentContentPreviewOut,
    InternalQuoteAttachmentPreviewSheetOut,
    InternalQuoteExportFileOut,
    InternalQuoteImportConfirmOut,
    InternalQuoteImportConfirmRequest,
    InternalQuoteImportPreviewOut,
)
from app.services.auth import AuthContext, has_permission_in_scope, now_text
from app.services.internal_quote import (
    MUTABLE_SECTION_STATUSES,
    SECTION_DEPARTMENTS,
    _add_audit,
    _add_revision,
    _calculate_and_apply,
    _check_revision,
    _cost_context,
    _derive_quote_status,
    _downstream_dependency_hashes,
    _ensure_active,
    _ensure_section_participates,
    _get_quote,
    _get_section,
    _invalidate_downstream_dependencies,
    _json_object,
    _rr2_cost_summary,
    _section_out,
    ensure_quote_permission,
    ensure_quote_read,
    ensure_section_permission,
)
from app.services.internal_quote_calculator import CalculationInputError, canonical_json, content_hash
from app.services.internal_quote_excel import (
    ENGINEERING_WORKBOOK_TEMPLATE_VERSION,
    P3_TEMPLATE_VERSION,
    P4_TEMPLATE_VERSION,
    WORKBOOK_LAYOUT_VERSION,
    build_internal_quote_engineering_workbook,
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
IMPORT_LIST_FIELDS = {
    "mold": ("molds",),
    "hardware": ("materials",),
    "electronic": ("components",),
    "molding": ("injection_lines", "blow_lines"),
    "painting": ("rows",),
    "slush": ("lines",),
    "sewing": ("groups",),
    "assembly": ("groups",),
}
IMPORT_BATCH_FIELD = "import_batch_id"


@dataclass(frozen=True)
class EngineeringWorkbookDownload:
    file_name: str
    content_type: str
    content: bytes
    sha256: str
    template_version: str


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
    if import_type == "molding":
        injection_rows = existing_payload.get("injection_lines", [])
        blow_rows = existing_payload.get("blow_lines", [])
        existing_list = [
            *(injection_rows if isinstance(injection_rows, list) else []),
            *(blow_rows if isinstance(blow_rows, list) else []),
        ]
    else:
        list_field = {
            "mold": "molds",
            "hardware": "materials",
            "electronic": "components",
            "painting": "rows",
            "slush": "lines",
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
        "rmb_hkd_rate": str(fx_value),
        # Keep the original workbook only inside the server-side preview
        # record.  The public preview contract deliberately omits this field.
        # Confirmation materializes it as a normal quote attachment so the
        # final controlled XLSX can append every uploaded worksheet intact.
        "source_workbook_base64": base64.b64encode(content).decode("ascii"),
        "payload_fragment": parsed.payload_fragment,
        "diff_summary": {
            "target_revision": section.revision,
            "existing_rows": len(existing_list),
            "imported_rows": parsed.row_count,
            "replace_result_rows": parsed.row_count,
        },
        "warnings": parsed.warnings,
        "embedded_images": [
            {
                "source_row": image.source_row,
                "file_name": image.file_name,
                "content_type": image.content_type,
                "data_base64": base64.b64encode(image.content).decode("ascii"),
            }
            for image in parsed.embedded_images
        ],
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
        preview_schema_version="p3-v3",
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
    rmb_hkd_rate: object = "0.85",
) -> dict[str, Any]:
    # Every mapped workbook owns one deterministic data region. Re-importing
    # that template replaces that region so users never have to decide between
    # append/replace and repeated imports cannot duplicate quote amounts.
    mode = "replace"
    merged = json.loads(json.dumps(current, ensure_ascii=False))
    if import_type == "molding":
        for list_field in ("injection_lines", "blow_lines"):
            imported_rows = fragment.get(list_field, [])
            if not isinstance(imported_rows, list):
                raise HTTPException(status_code=400, detail="啤机导入预览结构无效")
            existing_rows = merged.get(list_field, [])
            if not isinstance(existing_rows, list):
                existing_rows = []
            merged[list_field] = imported_rows if mode == "replace" else [*existing_rows, *imported_rows]
        if fragment.get("injection_loss_rate_percent") is not None:
            if mode == "replace" or merged.get("injection_loss_rate_percent") is None:
                merged["injection_loss_rate_percent"] = fragment["injection_loss_rate_percent"]
        return merged

    list_field = {
        "mold": "molds",
        "hardware": "materials",
        "electronic": "components",
        "painting": "rows",
        "slush": "lines",
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
        rmb_hkd_fields = (
            ("bonding_rmb", "bonding_hkd"),
            ("smt_rmb", "smt_hkd"),
            ("labor_rmb", "labor_hkd"),
            ("testing_rmb", "testing_hkd"),
            ("packaging_rmb", "packaging_hkd"),
        )
        uses_rmb_contract = fragment.get("pricing_currency") == "RMB" or any(
            rmb_field in fragment for rmb_field, _ in rmb_hkd_fields
        )
        if uses_rmb_contract:
            try:
                fx = Decimal(str(rmb_hkd_rate))
            except ArithmeticError:
                fx = Decimal("0.85")
            if fx <= 0:
                fx = Decimal("0.85")
            if mode == "append":
                for rmb_field, hkd_field in rmb_hkd_fields:
                    if rmb_field not in merged and hkd_field in merged:
                        merged[rmb_field] = format(Decimal(str(merged.get(hkd_field) or 0)) * fx, "f")
            for rmb_field, _ in rmb_hkd_fields:
                if rmb_field not in fragment:
                    continue
                merged[rmb_field] = (
                    _add_decimal_values(merged.get(rmb_field), fragment[rmb_field])
                    if mode == "append"
                    else fragment[rmb_field]
                )
            for key, value in fragment.items():
                if key == "components" or key in {item for pair in rmb_hkd_fields for item in pair} or key.startswith("tax_credit_difference_"):
                    continue
                if mode == "replace" or key not in merged:
                    merged[key] = value
            merged["pricing_currency"] = "RMB"
            for _, hkd_field in rmb_hkd_fields:
                merged.pop(hkd_field, None)
            merged.pop("tax_credit_difference_hkd", None)
            merged.pop("tax_credit_difference_rmb", None)
            return merged

        additive_fields = {
            "bonding_rmb",
            "smt_rmb",
            "labor_rmb",
            "testing_rmb",
            "packaging_rmb",
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


def _tag_import_fragment(
    import_type: str,
    fragment: dict[str, Any],
    batch_id: str,
) -> dict[str, Any]:
    tagged = json.loads(json.dumps(fragment, ensure_ascii=False))
    for list_field in IMPORT_LIST_FIELDS[import_type]:
        rows = tagged.get(list_field, [])
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                row[IMPORT_BATCH_FIELD] = batch_id
    return tagged


def _collect_attachment_ids(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        attachment_ids = value.get("image_attachment_ids", [])
        if isinstance(attachment_ids, list):
            found.update(str(item) for item in attachment_ids if str(item))
        for child in value.values():
            found.update(_collect_attachment_ids(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_collect_attachment_ids(child))
    return found


def _remove_import_rows(
    rows: object,
    batch_ids: set[str],
    *,
    hardware_only: bool = False,
) -> tuple[list[Any], list[Any]]:
    source_rows = rows if isinstance(rows, list) else []
    matching_markers = any(
        isinstance(row, dict) and str(row.get(IMPORT_BATCH_FIELD, "")) in batch_ids
        for row in source_rows
    )
    removed: list[Any] = []
    retained: list[Any] = []
    for row in source_rows:
        is_hardware = isinstance(row, dict) and row.get("category") == "hardware"
        if hardware_only and not is_hardware:
            retained.append(row)
            continue
        should_remove = (
            isinstance(row, dict)
            and str(row.get(IMPORT_BATCH_FIELD, "")) in batch_ids
        ) if matching_markers else True
        if should_remove:
            removed.append(row)
        else:
            retained.append(row)
    return retained, removed


def _clear_import_generated_payload(
    current: dict[str, Any],
    batches: list[InternalQuoteImportBatch],
) -> tuple[dict[str, Any], set[str]]:
    cleared = json.loads(json.dumps(current, ensure_ascii=False))
    removed_attachment_ids: set[str] = set()
    batches_by_type: dict[str, list[InternalQuoteImportBatch]] = {}
    for batch in batches:
        batches_by_type.setdefault(batch.import_type, []).append(batch)

    for import_type, type_batches in batches_by_type.items():
        batch_ids = {batch.id for batch in type_batches}
        for list_field in IMPORT_LIST_FIELDS.get(import_type, ()):
            retained, removed = _remove_import_rows(
                cleared.get(list_field, []),
                batch_ids,
                hardware_only=import_type == "hardware",
            )
            cleared[list_field] = retained
            removed_attachment_ids.update(_collect_attachment_ids(removed))

        fragments = [
            _json_object(batch.preview_json).get("payload_fragment", {})
            for batch in type_batches
        ]
        if import_type == "electronic":
            for fragment in fragments:
                if not isinstance(fragment, dict):
                    continue
                for key in fragment:
                    if key != "components":
                        cleared.pop(key, None)
        elif import_type == "molding" and any(
            isinstance(fragment, dict) and "injection_loss_rate_percent" in fragment
            for fragment in fragments
        ):
            cleared.pop("injection_loss_rate_percent", None)
        elif import_type == "mold" and any(
            isinstance(fragment, dict) and "amortization_qty" in fragment
            for fragment in fragments
        ):
            cleared.pop("amortization_qty", None)
    return cleared, removed_attachment_ids


def _materialize_imported_mold_images(
    db: Session,
    quote: InternalQuote,
    section: InternalQuoteSection,
    fragment: dict[str, Any],
    preview: dict[str, Any],
    user: AuthContext,
) -> list[str]:
    image_records = preview.get("embedded_images", [])
    mold_rows = fragment.get("molds", [])
    if not isinstance(image_records, list) or not isinstance(mold_rows, list):
        return []

    attachments_by_row: dict[int, list[str]] = {}
    materialized_attachment_ids: list[str] = []
    for record in image_records:
        if not isinstance(record, dict):
            continue
        try:
            source_row = int(record.get("source_row", 0) or 0)
            content = base64.b64decode(str(record.get("data_base64", "")), validate=True)
        except (ValueError, TypeError, binascii.Error) as error:
            raise HTTPException(status_code=400, detail="导入预览中的模具图片数据无效，请重新上传报价单") from error
        clean_name = safe_file_name(str(record.get("file_name", "")))
        _extension, content_type = _validate_attachment(clean_name, content)
        if not content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="导入预览包含非图片模具附件")
        sha256 = digest(content)
        attachment = db.scalar(
            select(InternalQuoteAttachment).where(
                InternalQuoteAttachment.quote_id == quote.id,
                InternalQuoteAttachment.department == section.department,
                InternalQuoteAttachment.sha256 == sha256,
            )
        )
        if attachment is None:
            attachment = InternalQuoteAttachment(
                id=f"IQATT-{uuid4().hex}",
                quote_id=quote.id,
                factory_id=quote.factory_id,
                department=section.department,
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
            db.flush()
        attachments_by_row.setdefault(source_row, []).append(attachment.id)
        materialized_attachment_ids.append(attachment.id)

    for row in mold_rows:
        if not isinstance(row, dict):
            continue
        try:
            source_row = int(row.get("source_row", 0) or 0)
        except (TypeError, ValueError):
            continue
        attachment_ids = list(dict.fromkeys(attachments_by_row.get(source_row, [])))
        if attachment_ids:
            row["image_attachment_ids"] = attachment_ids
    return list(dict.fromkeys(materialized_attachment_ids))


def _materialize_imported_source_workbook(
    db: Session,
    quote: InternalQuote,
    section: InternalQuoteSection,
    batch: InternalQuoteImportBatch,
    preview: dict[str, Any],
    user: AuthContext,
) -> str:
    encoded = str(preview.get("source_workbook_base64", ""))
    if not encoded:
        return ""
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError, binascii.Error) as error:
        raise HTTPException(
            status_code=400,
            detail="导入预览中的原始 Excel 数据无效，请重新上传报价单",
        ) from error
    if digest(content) != batch.source_sha256:
        raise HTTPException(
            status_code=400,
            detail="导入预览中的原始 Excel 校验失败，请重新上传报价单",
        )
    _extension, content_type = _validate_attachment(batch.source_file_name, content)
    attachment = db.scalar(
        select(InternalQuoteAttachment).where(
            InternalQuoteAttachment.quote_id == quote.id,
            InternalQuoteAttachment.department == section.department,
            InternalQuoteAttachment.sha256 == batch.source_sha256,
        )
    )
    if attachment is None:
        attachment = InternalQuoteAttachment(
            id=f"IQATT-{uuid4().hex}",
            quote_id=quote.id,
            factory_id=quote.factory_id,
            department=section.department,
            file_name=batch.source_file_name,
            content_type=content_type,
            size_bytes=len(content),
            sha256=batch.source_sha256,
            content=content,
            uploaded_by=user.id,
            uploaded_by_name=user.display_name,
            uploaded_at=now_text(),
        )
        db.add(attachment)
        db.flush()
    # The materialized attachment becomes the single durable binary source.
    # Removing the temporary base64 copy keeps confirmed preview rows compact.
    preview.pop("source_workbook_base64", None)
    batch.preview_json = canonical_json(preview)
    return attachment.id


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
    effective_mode = "replace"
    fragment = _tag_import_fragment(batch.import_type, fragment, batch.id)
    preview["payload_fragment"] = fragment
    source_workbook_attachment_id = _materialize_imported_source_workbook(
        db,
        quote,
        section,
        batch,
        preview,
        user,
    )
    embedded_image_attachment_ids: list[str] = []
    if batch.import_type == "mold":
        embedded_image_attachment_ids = _materialize_imported_mold_images(
            db,
            quote,
            section,
            fragment,
            preview,
            user,
        )
    preview["source_workbook_attachment_id"] = source_workbook_attachment_id
    preview["embedded_image_attachment_ids"] = embedded_image_attachment_ids
    batch.preview_json = canonical_json(preview)

    previous_dependency_hashes = _downstream_dependency_hashes(
        db,
        quote,
        section.department,
    )
    old_revision = section.revision
    section.payload_json = canonical_json(
        _merge_import_payload(
            batch.import_type,
            _json_object(section.payload_json),
            fragment,
            effective_mode,
            preview.get("rmb_hkd_rate", "0.85"),
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
    reason = f"import_confirm:{batch.import_type}:{effective_mode}:{batch.id}"
    _add_revision(db, quote, section, user, reason=reason)
    _invalidate_downstream_dependencies(
        db,
        quote,
        user,
        section.department,
        request,
        previous_dependency_hashes,
    )
    _derive_quote_status(db, quote)

    batch.status = "confirmed"
    batch.confirm_mode = effective_mode
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
                "mode": effective_mode,
                "source_sha256": batch.source_sha256,
                "source_workbook_attachment_id": source_workbook_attachment_id,
                "embedded_image_count": len(embedded_image_attachment_ids),
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


def _attachment_out(
    attachment: InternalQuoteAttachment,
    import_batch: InternalQuoteImportBatch | None = None,
) -> InternalQuoteAttachmentOut:
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
        is_import_source=import_batch is not None,
        import_batch_id=import_batch.id if import_batch is not None else "",
        import_type=import_batch.import_type if import_batch is not None else "",
    )


def _can_access_attachment_department(
    user: AuthContext,
    quote: InternalQuote,
    department: str,
) -> bool:
    if department == "product-image":
        return True
    if any(
        has_permission_in_scope(user, permission, quote.factory_id, scope_department)
        for permission, scope_department in (
            ("internal_quote:sales_edit", "sales-business"),
            ("internal_quote:engineering_edit", "engineering"),
        )
    ):
        return True
    return any(
        has_permission_in_scope(
            user,
            f"internal_quote:{department}_edit",
            quote.factory_id,
            scope_department,
        )
        for scope_department in SECTION_DEPARTMENTS.get(department, ())
    )


def _ensure_attachment_access(
    user: AuthContext,
    quote: InternalQuote,
    department: str,
) -> None:
    if not _can_access_attachment_department(user, quote, department):
        raise HTTPException(status_code=403, detail="当前账号只能访问分配给本部门的报价资料")


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
    if section.status not in {"draft", "rejected"}:
        raise HTTPException(
            status_code=409,
            detail="当前分段已提交或审核完成，请先返回修改或合法重开后再上传附件",
        )
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


def upload_product_image(
    db: Session,
    quote_id: str,
    file_name: str,
    content: bytes,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteAttachmentOut:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:create",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    if quote.status in {"final_reviewing", "fully_approved", "exported"}:
        raise HTTPException(status_code=409, detail="产品已提交审核或完成输出，不能更换主图")
    clean_name = safe_file_name(file_name)
    extension, content_type = _validate_attachment(clean_name, content)
    if extension not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="产品主图仅支持 JPG/JPEG/PNG/WEBP 图片")
    sha256 = digest(content)
    duplicate = db.scalar(
        select(InternalQuoteAttachment.id).where(
            InternalQuoteAttachment.quote_id == quote.id,
            InternalQuoteAttachment.department == "product-image",
            InternalQuoteAttachment.sha256 == sha256,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="该产品已使用相同主图")
    attachment = InternalQuoteAttachment(
        id=f"IQATT-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        department="product-image",
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
        "upload_product_image",
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
    if department:
        _ensure_attachment_access(user, quote, department)
    statement = select(InternalQuoteAttachment).where(InternalQuoteAttachment.quote_id == quote.id)
    if department:
        statement = statement.where(InternalQuoteAttachment.department == department)
    statement = statement.order_by(InternalQuoteAttachment.uploaded_at.desc(), InternalQuoteAttachment.id.desc())
    attachments = [
        item for item in db.scalars(statement).all()
        if _can_access_attachment_department(user, quote, item.department)
    ]
    batches = list(db.scalars(
        select(InternalQuoteImportBatch)
        .where(
            InternalQuoteImportBatch.quote_id == quote.id,
            InternalQuoteImportBatch.status == "confirmed",
        )
        .order_by(InternalQuoteImportBatch.confirmed_at.desc(), InternalQuoteImportBatch.id.desc())
    ).all())
    source_batch_by_attachment_id: dict[str, InternalQuoteImportBatch] = {}
    for batch in batches:
        preview = _json_object(batch.preview_json)
        source_attachment_id = str(preview.get("source_workbook_attachment_id", ""))
        if source_attachment_id:
            source_batch_by_attachment_id.setdefault(source_attachment_id, batch)
            continue
        # Compatibility for imports confirmed before source attachment ids were
        # written into preview metadata.
        for attachment in attachments:
            if (
                attachment.department == batch.target_department
                and attachment.sha256 == batch.source_sha256
            ):
                source_batch_by_attachment_id.setdefault(attachment.id, batch)
                break
    return [
        _attachment_out(item, source_batch_by_attachment_id.get(item.id))
        for item in attachments
    ]


def delete_import_attachment(
    db: Session,
    quote_id: str,
    attachment_id: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> None:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    attachment = db.scalar(
        select(InternalQuoteAttachment)
        .where(
            InternalQuoteAttachment.id == attachment_id,
            InternalQuoteAttachment.quote_id == quote.id,
        )
        .with_for_update()
    )
    if attachment is None:
        raise HTTPException(status_code=404, detail="附件不存在")
    ensure_section_permission(db, user, quote.factory_id, attachment.department, "edit")
    section = _get_section(db, quote.id, attachment.department)
    _ensure_section_participates(section)
    _check_revision(section.revision, revision)
    if section.status not in MUTABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前分段已提交或审核完成，请先返回修改或合法重开后再删除导入附件")

    candidate_batches = list(db.scalars(
        select(InternalQuoteImportBatch)
        .where(
            InternalQuoteImportBatch.quote_id == quote.id,
            InternalQuoteImportBatch.target_department == attachment.department,
            InternalQuoteImportBatch.status == "confirmed",
        )
        .with_for_update()
    ).all())
    batches = []
    for batch in candidate_batches:
        preview = _json_object(batch.preview_json)
        source_attachment_id = str(preview.get("source_workbook_attachment_id", ""))
        if source_attachment_id == attachment.id or (
            not source_attachment_id and batch.source_sha256 == attachment.sha256
        ):
            batches.append(batch)
    if not batches:
        raise HTTPException(status_code=409, detail="该附件不是结构化报价导入源文件，不能执行联动清除")

    previous_dependency_hashes = _downstream_dependency_hashes(db, quote, section.department)
    old_revision = section.revision
    cleared_payload, imported_image_ids = _clear_import_generated_payload(
        _json_object(section.payload_json),
        batches,
    )
    section.payload_json = canonical_json(cleared_payload)
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

    reason = f"import_attachment_delete:{','.join(batch.id for batch in batches)}"
    _add_revision(db, quote, section, user, reason=reason)
    _invalidate_downstream_dependencies(
        db,
        quote,
        user,
        section.department,
        request,
        previous_dependency_hashes,
    )
    _derive_quote_status(db, quote)

    for batch in batches:
        preview = _json_object(batch.preview_json)
        preview["deleted_attachment_id"] = attachment.id
        preview["deleted_by"] = user.id
        preview["deleted_at"] = now_text()
        batch.preview_json = canonical_json(preview)
        batch.status = "deleted"

    db.delete(attachment)
    if imported_image_ids:
        remaining_payloads = [
            _json_object(item.payload_json)
            for item in db.scalars(
                select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
            ).all()
        ]
        referenced_ids = set().union(*(_collect_attachment_ids(item) for item in remaining_payloads))
        for image_id in imported_image_ids - referenced_ids:
            image_attachment = db.scalar(
                select(InternalQuoteAttachment).where(
                    InternalQuoteAttachment.id == image_id,
                    InternalQuoteAttachment.quote_id == quote.id,
                )
            )
            if image_attachment is not None:
                db.delete(image_attachment)

    _add_audit(
        db,
        quote,
        user,
        "delete_import_attachment",
        department=section.department,
        detail=json.dumps(
            {
                "attachment_id": attachment.id,
                "file_name": attachment.file_name,
                "batch_ids": [batch.id for batch in batches],
                "import_types": sorted({batch.import_type for batch in batches}),
                "removed_image_attachment_ids": sorted(imported_image_ids),
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
    _ensure_attachment_access(user, quote, attachment.department)
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


def get_attachment_preview(
    db: Session,
    quote_id: str,
    attachment_id: str,
    user: AuthContext,
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
    _ensure_attachment_access(user, quote, attachment.department)
    if Path(attachment.file_name).suffix.lower() not in ATTACHMENT_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="该附件不支持在线预览")
    return attachment


def _preview_cell(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _trim_preview_rows(rows: list[list[Any]]) -> tuple[list[list[Any]], int]:
    while rows and not any(value not in (None, "") for value in rows[-1]):
        rows.pop()
    total_columns = max((len(row) for row in rows), default=0)
    while total_columns and all(
        len(row) < total_columns or row[total_columns - 1] in (None, "")
        for row in rows
    ):
        total_columns -= 1
    return [row[:total_columns] for row in rows], total_columns


def _xlsx_content_preview(attachment: InternalQuoteAttachment) -> InternalQuoteAttachmentContentPreviewOut:
    from openpyxl import load_workbook

    workbook = load_workbook(BytesIO(attachment.content), read_only=True, data_only=True)
    sheets: list[InternalQuoteAttachmentPreviewSheetOut] = []
    try:
        for worksheet in workbook.worksheets:
            total_rows = int(worksheet.max_row or 0)
            total_columns = int(worksheet.max_column or 0)
            rows = [
                [_preview_cell(value) for value in row]
                for row in worksheet.iter_rows(
                    min_row=1,
                    max_row=min(total_rows, 200),
                    min_col=1,
                    max_col=min(total_columns, 40),
                    values_only=True,
                )
            ] if total_rows and total_columns else []
            rows, _ = _trim_preview_rows(rows)
            sheets.append(InternalQuoteAttachmentPreviewSheetOut(
                name=worksheet.title,
                rows=rows,
                total_rows=total_rows,
                total_columns=total_columns,
                truncated=total_rows > 200 or total_columns > 40,
            ))
    finally:
        workbook.close()
    return InternalQuoteAttachmentContentPreviewOut(
        file_name=attachment.file_name,
        kind="excel",
        sheets=sheets,
    )


def _xls_content_preview(attachment: InternalQuoteAttachment) -> InternalQuoteAttachmentContentPreviewOut:
    import xlrd

    workbook = xlrd.open_workbook(file_contents=attachment.content, on_demand=True)
    sheets: list[InternalQuoteAttachmentPreviewSheetOut] = []
    try:
        for worksheet in workbook.sheets():
            total_rows = int(worksheet.nrows)
            total_columns = int(worksheet.ncols)
            rows = [
                [_preview_cell(worksheet.cell_value(row_index, column_index)) for column_index in range(min(total_columns, 40))]
                for row_index in range(min(total_rows, 200))
            ]
            rows, _ = _trim_preview_rows(rows)
            sheets.append(InternalQuoteAttachmentPreviewSheetOut(
                name=worksheet.name,
                rows=rows,
                total_rows=total_rows,
                total_columns=total_columns,
                truncated=total_rows > 200 or total_columns > 40,
            ))
    finally:
        workbook.release_resources()
    return InternalQuoteAttachmentContentPreviewOut(
        file_name=attachment.file_name,
        kind="excel",
        sheets=sheets,
    )


def _docx_content_preview(attachment: InternalQuoteAttachment) -> InternalQuoteAttachmentContentPreviewOut:
    from docx import Document

    document = Document(BytesIO(attachment.content))
    paragraphs = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    for table in document.tables:
        for row in table.rows:
            text = " ｜ ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if text:
                paragraphs.append(text)
    truncated = len(paragraphs) > 500
    return InternalQuoteAttachmentContentPreviewOut(
        file_name=attachment.file_name,
        kind="word",
        paragraphs=paragraphs[:500],
        warnings=["文档内容较长，当前仅显示前 500 段；完整内容请下载原文件。"] if truncated else [],
    )


def _legacy_doc_content_preview(attachment: InternalQuoteAttachment) -> InternalQuoteAttachmentContentPreviewOut:
    decoded = attachment.content.decode("utf-16le", errors="ignore")
    candidates = re.findall(r"[\u3400-\u9fffA-Za-z0-9，。；：、（）()《》“”‘’\-_/ .]{4,}", decoded)
    paragraphs = []
    for candidate in candidates:
        text = re.sub(r"\s+", " ", candidate).strip(" \x00")
        if text and text not in paragraphs:
            paragraphs.append(text)
        if len(paragraphs) >= 500:
            break
    return InternalQuoteAttachmentContentPreviewOut(
        file_name=attachment.file_name,
        kind="word",
        paragraphs=paragraphs,
        warnings=["旧版 DOC 采用只读文本提取预览，原始排版、图片和部分文字可能无法还原；请下载原文件核对。"],
    )


def get_attachment_content_preview(
    db: Session,
    quote_id: str,
    attachment_id: str,
    user: AuthContext,
) -> InternalQuoteAttachmentContentPreviewOut:
    attachment = get_attachment_preview(db, quote_id, attachment_id, user)
    extension = Path(attachment.file_name).suffix.lower()
    try:
        if extension in {".xlsx", ".xlsm"}:
            return _xlsx_content_preview(attachment)
        if extension == ".xls":
            return _xls_content_preview(attachment)
        if extension == ".docx":
            return _docx_content_preview(attachment)
        if extension == ".doc":
            return _legacy_doc_content_preview(attachment)
    except Exception as exc:
        raise HTTPException(status_code=422, detail="附件内容无法解析，请下载原文件核对") from exc
    raise HTTPException(status_code=415, detail="该附件使用原文件在线预览")


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


def _ensure_export_sections_ready(
    sections: list[InternalQuoteSection],
) -> None:
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
        and (
            section.calculation_status != "valid"
            or section.dependency_status != "current"
        )
    ]
    if incomplete or invalid:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "所有必需分段通过且计算有效后才能生成 XLSX",
                "incomplete_sections": incomplete,
                "invalid_calculations": invalid,
            },
        )


def _handoff_manifest(
    quote: InternalQuote,
    record: InternalQuoteExportFile,
) -> dict[str, object]:
    export_manifest = _json_object(record.export_manifest_json)
    return {
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
        "workbook_layout_version": export_manifest.get("workbook_layout_version", ""),
        "formula_version": record.formula_version,
        "reference_snapshot_id": record.reference_snapshot_id,
        "section_revisions": _json_object(record.section_revisions_json),
    }


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
    handoff_manifest = _handoff_manifest(quote, record)
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
    _ensure_export_sections_ready(sections)
    attachments = db.scalars(
        select(InternalQuoteAttachment)
        .where(InternalQuoteAttachment.quote_id == quote.id)
        .order_by(
            InternalQuoteAttachment.uploaded_at,
            InternalQuoteAttachment.id,
        )
    ).all()
    is_final_release = (
        quote.status in {"fully_approved", "exported"}
        and quote.final_release_status == "approved"
        and quote.final_release_revision > 0
    )
    existing_handoff: InternalQuoteArtifactHandoff | None = None
    layout_refresh = False
    if is_final_release:
        current_exports = db.scalars(
            select(InternalQuoteExportFile)
            .where(
                InternalQuoteExportFile.quote_id == quote.id,
                InternalQuoteExportFile.status == "current",
                InternalQuoteExportFile.release_stage == "p4_final_approved",
            )
            .order_by(
                InternalQuoteExportFile.exported_at.desc(),
                InternalQuoteExportFile.id.desc(),
            )
        ).all()
        for current_export in current_exports:
            current_manifest = _json_object(current_export.export_manifest_json)
            if (
                current_manifest.get("workbook_layout_version") == WORKBOOK_LAYOUT_VERSION
                and str(current_manifest.get("final_release_revision") or "0")
                == str(quote.final_release_revision)
            ):
                return _export_out(current_export)
        existing_handoff = db.scalar(
            select(InternalQuoteArtifactHandoff).where(
                InternalQuoteArtifactHandoff.quote_id == quote.id,
                InternalQuoteArtifactHandoff.release_revision == quote.final_release_revision,
            )
        )
        if existing_handoff is not None:
            existing_export = db.get(InternalQuoteExportFile, existing_handoff.export_id)
            if existing_export is not None and existing_export.release_stage == "p4_final_approved":
                existing_manifest = _json_object(existing_export.export_manifest_json)
                if existing_manifest.get("workbook_layout_version") == WORKBOOK_LAYOUT_VERSION:
                    return _export_out(existing_export)
                # The final-release business payload remains immutable.  A
                # presentation-only refresh gets a new export record while the
                # one-per-release customer handoff continues to reference its
                # original, structurally compatible P4 v2 artifact.
                layout_refresh = True
    release_stage = "p4_final_approved" if is_final_release else "p3_section_approved"
    template_version = P4_TEMPLATE_VERSION if is_final_release else P3_TEMPLATE_VERSION
    _supersede_outdated_exports(db, quote, sections)
    section_revisions = {section.department: section.revision for section in sections}
    manifest = {
        "template_version": template_version,
        "workbook_layout_version": WORKBOOK_LAYOUT_VERSION,
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
        "spreadsheet_attachments": [
            {
                "id": attachment.id,
                "department": attachment.department,
                "file_name": attachment.file_name,
                "sha256": attachment.sha256,
            }
            for attachment in attachments
            if Path(attachment.file_name).suffix.lower() in IMPORT_EXTENSIONS
        ],
    }
    manifest["manifest_sha256"] = content_hash(manifest)
    reference_set = db.scalar(
        select(InternalQuoteReferenceSet).where(
            InternalQuoteReferenceSet.id == quote.reference_snapshot_id,
            InternalQuoteReferenceSet.quote_id == quote.id,
        )
    )
    reference_snapshot = _json_object(reference_set.snapshot_json) if reference_set else {}
    cost_context = _cost_context(db, quote)
    rr2_cost_summary = _rr2_cost_summary(
        sections,
        cost_context,
        reference_snapshot,
        quote.qty,
        factory_id=quote.factory_id,
    )
    content = build_internal_quote_workbook(
        quote,
        sections,
        manifest,
        reference_snapshot,
        rr2_cost_summary,
        cost_context,
        attachments,
    )
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
        if (
            layout_refresh
            and existing_handoff is not None
            and existing_handoff.status == "consumed"
            and item.id == existing_handoff.export_id
        ):
            # A consumed customer handoff is immutable.  Keep its exact P4
            # artifact current alongside the presentation-refreshed workbook.
            continue
        item.status = "superseded"
        item.superseded_at = now_text()
        handoffs = db.scalars(
            select(InternalQuoteArtifactHandoff).where(
                InternalQuoteArtifactHandoff.export_id == item.id,
                InternalQuoteArtifactHandoff.status.in_(("available", "consumed")),
            )
        ).all()
        for handoff in handoffs:
            if layout_refresh and existing_handoff is not None and handoff.id == existing_handoff.id:
                continue
            handoff.status = "revoked"
            handoff.revoked_at = now_text()
            handoff.revoke_reason = "已生成后续内部报价导出文件"
    db.add(record)
    db.flush()
    if is_final_release and existing_handoff is None:
        _create_artifact_handoff(db, quote, record, user)
    elif (
        is_final_release
        and layout_refresh
        and existing_handoff is not None
        and existing_handoff.status == "available"
    ):
        existing_handoff.export_id = record.id
        existing_handoff.artifact_manifest_json = canonical_json(
            _handoff_manifest(quote, record)
        )
    if is_final_release:
        quote.status = "exported"
        quote.updated_at = now_text()
    _add_audit(
        db,
        quote,
        user,
        "export",
        detail=json.dumps(
            {
                "export_id": record.id,
                "sha256": record.sha256,
                "release_stage": record.release_stage,
                "workbook_layout_version": WORKBOOK_LAYOUT_VERSION,
                "layout_refresh": layout_refresh,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    db.refresh(record)
    return _export_out(record)


def create_engineering_workbook_export(
    db: Session,
    quote_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> EngineeringWorkbookDownload:
    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    _ensure_export_permission(db, quote, user)
    sections = _export_sections(db, quote)
    _ensure_export_sections_ready(sections)
    content = build_internal_quote_engineering_workbook(quote, sections)
    download = EngineeringWorkbookDownload(
        file_name=safe_file_name(
            f"{quote.quote_no}_{quote.version_label}_工程资料.xlsx"
        ),
        content_type=EXPORT_CONTENT_TYPE,
        content=content,
        sha256=digest(content),
        template_version=ENGINEERING_WORKBOOK_TEMPLATE_VERSION,
    )
    _add_audit(
        db,
        quote,
        user,
        "engineering_data_export",
        detail=json.dumps(
            {
                "file_name": download.file_name,
                "sha256": download.sha256,
                "template_version": download.template_version,
                "section_revisions": {
                    section.department: section.revision for section in sections
                },
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    return download


def list_export_files(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteExportFileOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    # Export history is read-only quote metadata. Keep legacy status
    # reconciliation for local exporters, but never mutate foreign data while
    # serving a cross-factory read-only request.
    if has_permission_in_scope(
        user,
        "internal_quote:export",
        quote.factory_id,
        "sales-business",
    ):
        sections = _export_sections(db, quote)
        _supersede_outdated_exports(db, quote, sections)
        db.commit()
    records = db.scalars(
        select(InternalQuoteExportFile)
        .where(InternalQuoteExportFile.quote_id == quote.id)
        .order_by(InternalQuoteExportFile.exported_at.desc(), InternalQuoteExportFile.id.desc())
    ).all()
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
