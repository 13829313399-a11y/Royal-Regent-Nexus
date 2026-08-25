from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.carton_mark import (
    CartonMarkCustomer,
    CartonMarkDocument,
    CartonMarkTemplate,
)
from app.models.carton_procurement import CartonAuditEvent
from app.schemas.carton_mark import (
    CartonMarkCustomerOptionOut,
    CartonMarkDocumentCheckResponse,
    CartonMarkTemplateOut,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    has_permission_in_scope,
)
from app.services.carton_procurement import require_carton_factory


CARTON_MARK_WRITE_DEPARTMENTS = ("pmc-warehouse", "carton")
CARTON_MARK_READ_DEPARTMENTS = (
    *CARTON_MARK_WRITE_DEPARTMENTS,
    "qa",
    "qc",
)
CARTON_MARK_DOCUMENT_KINDS = frozenset({"source_excel", "print_pdf"})


@dataclass(frozen=True)
class CartonMarkDocumentDownload:
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    content: bytes


@dataclass(frozen=True)
class CartonMarkDocumentRecheckSource:
    excel_file_name: str
    excel_bytes: bytes
    pdf_file_name: str
    pdf_bytes: bytes


def _now_text() -> str:
    return business_now().isoformat(timespec="seconds")


def _audit(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    event_type: str,
    template_id: str,
    detail: dict[str, object],
) -> None:
    db.add(
        CartonAuditEvent(
            id=f"CAE-{uuid4().hex}",
            factory_id=factory_id,
            event_type=event_type,
            entity_type="carton_mark_template",
            entity_id=template_id,
            detail_json=json.dumps(
                detail,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            actor_user_id=user.id,
            actor_name=user.display_name,
            created_at=_now_text(),
        )
    )


def _normalize_required(value: str, label: str, max_length: int) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{label}不能为空")
    if len(normalized) > max_length:
        raise HTTPException(status_code=422, detail=f"{label}过长")
    return normalized


def _business_key(*, customer_name: str, po: str, item: str, contract_number: str) -> str:
    normalized = "\x1f".join(
        " ".join(value.strip().split()).casefold()
        for value in (customer_name, po, item, contract_number)
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _document_fingerprint(excel_sha256: str, pdf_sha256: str) -> str:
    return hashlib.sha256(f"{excel_sha256}:{pdf_sha256}".encode("ascii")).hexdigest()


def _excel_content_type(file_name: str) -> str:
    if Path(file_name).suffix.lower() == ".xls":
        return "application/vnd.ms-excel"
    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def ensure_carton_mark_scope(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
    candidate_departments: tuple[str, ...],
) -> str:
    factory_id = require_carton_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in candidate_departments
    ):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        permission,
        factory_id,
        candidate_departments[0],
    )
    return factory_id


def list_carton_mark_customer_options(
    db: Session,
    factory_id: str,
) -> list[CartonMarkCustomerOptionOut]:
    factory_id = require_carton_factory(factory_id)
    customers = db.scalars(
        select(CartonMarkCustomer)
        .where(CartonMarkCustomer.factory_id == factory_id)
        .order_by(CartonMarkCustomer.normalized_name, CartonMarkCustomer.id)
    ).all()
    return [
        CartonMarkCustomerOptionOut(id=customer.id, name=customer.name)
        for customer in customers
    ]


def _active_template(db: Session, factory_id: str, template_id: str) -> CartonMarkTemplate:
    template = db.scalar(
        select(CartonMarkTemplate).where(
            CartonMarkTemplate.id == template_id,
            CartonMarkTemplate.factory_id == factory_id,
            CartonMarkTemplate.is_archived.is_(False),
        )
    )
    if template is None:
        raise HTTPException(status_code=404, detail="箱唛资料不存在")
    return template


def _documents_for_templates(
    db: Session,
    template_ids: list[str],
) -> dict[str, dict[str, CartonMarkDocument]]:
    if not template_ids:
        return {}
    documents: dict[str, dict[str, CartonMarkDocument]] = {}
    for document in db.scalars(
        select(CartonMarkDocument).where(CartonMarkDocument.template_id.in_(template_ids))
    ).all():
        documents.setdefault(document.template_id, {})[document.kind] = document
    return documents


def _template_out(
    template: CartonMarkTemplate,
    documents: dict[str, CartonMarkDocument],
) -> CartonMarkTemplateOut:
    excel = documents.get("source_excel")
    pdf = documents.get("print_pdf")
    if excel is None or pdf is None:
        raise RuntimeError(f"箱唛资料 {template.id} 的持久化文档不完整")
    check_result = CartonMarkDocumentCheckResponse.model_validate_json(
        template.check_result_json
    )
    return CartonMarkTemplateOut(
        id=template.id,
        factory_id=template.factory_id,
        customer_name=template.customer_name,
        po=template.po,
        item=template.item,
        contract_number=template.contract_number,
        version=template.version,
        check_status=template.check_status,
        check_result=check_result,
        excel_file_name=excel.file_name,
        excel_file_size=excel.size_bytes,
        pdf_file_name=pdf.file_name,
        pdf_file_size=pdf.size_bytes,
        created_at=template.created_at,
        updated_at=template.updated_at,
        created_by_name=template.created_by_name,
        qc_ready=(
            template.check_status == "核对通过"
            or bool(template.manual_released_at)
        ),
        manual_released=bool(template.manual_released_at),
        manual_release_reason=template.manual_release_reason,
        manual_release_source_status=template.manual_release_source_status,
        manual_released_by_name=template.manual_released_by_name,
        manual_released_at=template.manual_released_at,
    )


def create_carton_mark_template(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    customer_name: str,
    po: str,
    item: str,
    contract_number: str,
    excel_file_name: str,
    excel_bytes: bytes,
    pdf_file_name: str,
    pdf_bytes: bytes,
    check_result: CartonMarkDocumentCheckResponse,
) -> CartonMarkTemplateOut:
    factory_id = require_carton_factory(factory_id)
    customer_name = _normalize_required(customer_name, "客户名称", 255)
    managed_customer = db.scalar(
        select(CartonMarkCustomer).where(
            CartonMarkCustomer.factory_id == factory_id,
            CartonMarkCustomer.normalized_name
            == " ".join(customer_name.split()).casefold(),
        )
    )
    if managed_customer is None:
        raise HTTPException(
            status_code=422,
            detail="所选客名不在当前厂区箱唛客户库，请联系纸箱部主管维护",
        )
    customer_name = managed_customer.name
    item = _normalize_required(item, "ITEM", 128)
    contract_number = _normalize_required(contract_number, "合同号", 128)
    po = " ".join(po.strip().split()) or contract_number
    if len(po) > 128:
        raise HTTPException(status_code=422, detail="PO 过长")

    excel_sha256 = hashlib.sha256(excel_bytes).hexdigest()
    pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    document_fingerprint = _document_fingerprint(excel_sha256, pdf_sha256)
    duplicate = db.scalar(
        select(CartonMarkTemplate.id).where(
            CartonMarkTemplate.factory_id == factory_id,
            CartonMarkTemplate.document_fingerprint == document_fingerprint,
        )
    )
    if duplicate is not None:
        raise HTTPException(status_code=409, detail="这组 Excel 与打印 PDF 已经归档")

    business_key = _business_key(
        customer_name=customer_name,
        po=po,
        item=item,
        contract_number=contract_number,
    )
    previous_version = db.scalar(
        select(func.max(CartonMarkTemplate.version)).where(
            CartonMarkTemplate.factory_id == factory_id,
            CartonMarkTemplate.business_key_sha256 == business_key,
        )
    )
    version = int(previous_version or 0) + 1
    check_status = check_result.summary.overall_status
    if check_status not in {"核对通过", "发现差异", "需复核"}:
        raise HTTPException(status_code=422, detail="箱唛核对结果状态无效")

    timestamp = _now_text()
    template = CartonMarkTemplate(
        id=f"CMT-{uuid4().hex}",
        factory_id=factory_id,
        customer_name=customer_name,
        po=po,
        item=item,
        contract_number=contract_number,
        business_key_sha256=business_key,
        document_fingerprint=document_fingerprint,
        version=version,
        check_status=check_status,
        check_result_json=json.dumps(
            check_result.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        excel_sha256=excel_sha256,
        pdf_sha256=pdf_sha256,
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=timestamp,
        updated_at=timestamp,
        is_archived=False,
        archived_by="",
        archived_by_name="",
        archived_at="",
    )
    excel_document = CartonMarkDocument(
        id=f"CMD-{uuid4().hex}",
        template_id=template.id,
        factory_id=factory_id,
        kind="source_excel",
        file_name=check_result.excel_file_name,
        content_type=_excel_content_type(check_result.excel_file_name),
        size_bytes=len(excel_bytes),
        sha256=excel_sha256,
        content=excel_bytes,
        created_at=timestamp,
    )
    pdf_document = CartonMarkDocument(
        id=f"CMD-{uuid4().hex}",
        template_id=template.id,
        factory_id=factory_id,
        kind="print_pdf",
        file_name=check_result.pdf_file_name,
        content_type="application/pdf",
        size_bytes=len(pdf_bytes),
        sha256=pdf_sha256,
        content=pdf_bytes,
        created_at=timestamp,
    )
    try:
        db.add(template)
        db.flush()
        db.add_all((excel_document, pdf_document))
        _audit(
            db,
            user,
            factory_id=factory_id,
            event_type="CARTON_MARK_TEMPLATE_CREATED",
            template_id=template.id,
            detail={
                "version": version,
                "check_status": check_status,
                "excel_sha256": excel_sha256,
                "pdf_sha256": pdf_sha256,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="这组箱唛文档已存在，或同一业务版本发生并发冲突",
        ) from exc
    db.refresh(template)
    return _template_out(
        template,
        {"source_excel": excel_document, "print_pdf": pdf_document},
    )


def list_carton_mark_templates(db: Session, factory_id: str) -> list[CartonMarkTemplateOut]:
    factory_id = require_carton_factory(factory_id)
    templates = list(
        db.scalars(
            select(CartonMarkTemplate)
            .where(
                CartonMarkTemplate.factory_id == factory_id,
                CartonMarkTemplate.is_archived.is_(False),
            )
            .order_by(CartonMarkTemplate.created_at.desc(), CartonMarkTemplate.id.desc())
        ).all()
    )
    documents = _documents_for_templates(db, [template.id for template in templates])
    return [_template_out(template, documents.get(template.id, {})) for template in templates]


def get_carton_mark_template(
    db: Session,
    factory_id: str,
    template_id: str,
) -> CartonMarkTemplateOut:
    factory_id = require_carton_factory(factory_id)
    template = _active_template(db, factory_id, template_id)
    documents = _documents_for_templates(db, [template.id])
    return _template_out(template, documents.get(template.id, {}))


def get_carton_mark_document_recheck_source(
    db: Session,
    factory_id: str,
    template_id: str,
) -> CartonMarkDocumentRecheckSource:
    factory_id = require_carton_factory(factory_id)
    template = _active_template(db, factory_id, template_id)
    documents = _documents_for_templates(db, [template.id]).get(template.id, {})
    excel = documents.get("source_excel")
    pdf = documents.get("print_pdf")
    if excel is None or pdf is None:
        raise HTTPException(status_code=409, detail="箱唛资料缺少客人 Excel 或打印 PDF，无法重新核对")
    return CartonMarkDocumentRecheckSource(
        excel_file_name=excel.file_name,
        excel_bytes=excel.content,
        pdf_file_name=pdf.file_name,
        pdf_bytes=pdf.content,
    )


def update_carton_mark_document_check_result(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    template_id: str,
    check_result: CartonMarkDocumentCheckResponse,
) -> CartonMarkTemplateOut:
    factory_id = require_carton_factory(factory_id)
    template = _active_template(db, factory_id, template_id)
    check_status = check_result.summary.overall_status
    if check_status not in {"核对通过", "发现差异", "需复核"}:
        raise HTTPException(status_code=422, detail="箱唛核对结果状态无效")

    manual_release_revoked = bool(template.manual_released_at)
    template.check_status = check_status
    template.check_result_json = json.dumps(
        check_result.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    template.manual_release_reason = ""
    template.manual_release_source_status = ""
    template.manual_released_by = ""
    template.manual_released_by_name = ""
    template.manual_released_at = ""
    template.updated_at = _now_text()
    _audit(
        db,
        user,
        factory_id=factory_id,
        event_type="CARTON_MARK_TEMPLATE_RECHECKED",
        template_id=template.id,
        detail={
            "version": template.version,
            "check_status": check_status,
            "manual_release_revoked": manual_release_revoked,
            "excel_sha256": template.excel_sha256,
            "pdf_sha256": template.pdf_sha256,
        },
    )
    db.commit()
    db.refresh(template)
    documents = _documents_for_templates(db, [template.id])
    return _template_out(template, documents.get(template.id, {}))


def manually_release_carton_mark_template(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    template_id: str,
    reason: str,
) -> CartonMarkTemplateOut:
    factory_id = require_carton_factory(factory_id)
    template = _active_template(db, factory_id, template_id)
    if template.check_status == "核对通过":
        raise HTTPException(status_code=409, detail="该模板已经自动核对通过，无需人工放行")
    if template.manual_released_at:
        raise HTTPException(status_code=409, detail="该模板已经人工放行，请勿重复操作")

    normalized_reason = _normalize_required(reason, "人工放行理由", 500)
    if len(normalized_reason) < 5:
        raise HTTPException(status_code=422, detail="人工放行理由至少需要 5 个字符")

    timestamp = _now_text()
    template.manual_release_reason = normalized_reason
    template.manual_release_source_status = template.check_status
    template.manual_released_by = user.id
    template.manual_released_by_name = user.display_name
    template.manual_released_at = timestamp
    template.updated_at = timestamp
    _audit(
        db,
        user,
        factory_id=factory_id,
        event_type="CARTON_MARK_TEMPLATE_MANUALLY_RELEASED",
        template_id=template.id,
        detail={
            "version": template.version,
            "source_check_status": template.check_status,
            "reason": normalized_reason,
            "excel_sha256": template.excel_sha256,
            "pdf_sha256": template.pdf_sha256,
        },
    )
    db.commit()
    db.refresh(template)
    documents = _documents_for_templates(db, [template.id])
    return _template_out(template, documents.get(template.id, {}))


def get_authorized_carton_mark_document(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    template_id: str,
    kind: str,
) -> CartonMarkDocumentDownload:
    factory_id = ensure_carton_mark_scope(
        db,
        user,
        "carton_mark:read",
        factory_id,
        CARTON_MARK_READ_DEPARTMENTS,
    )
    if kind not in CARTON_MARK_DOCUMENT_KINDS:
        raise HTTPException(status_code=422, detail="箱唛文档类型无效")
    template = _active_template(db, factory_id, template_id)
    document = db.scalar(
        select(CartonMarkDocument).where(
            CartonMarkDocument.template_id == template.id,
            CartonMarkDocument.factory_id == factory_id,
            CartonMarkDocument.kind == kind,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="箱唛文档不存在")
    return CartonMarkDocumentDownload(
        file_name=document.file_name,
        content_type=document.content_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        content=document.content,
    )


def archive_carton_mark_template(
    db: Session,
    user: AuthContext,
    *,
    factory_id: str,
    template_id: str,
) -> None:
    factory_id = require_carton_factory(factory_id)
    template = _active_template(db, factory_id, template_id)
    timestamp = _now_text()
    template.is_archived = True
    template.archived_by = user.id
    template.archived_by_name = user.display_name
    template.archived_at = timestamp
    template.updated_at = timestamp
    _audit(
        db,
        user,
        factory_id=factory_id,
        event_type="CARTON_MARK_TEMPLATE_ARCHIVED",
        template_id=template.id,
        detail={
            "version": template.version,
            "check_status": template.check_status,
            "excel_sha256": template.excel_sha256,
            "pdf_sha256": template.pdf_sha256,
        },
    )
    db.commit()
