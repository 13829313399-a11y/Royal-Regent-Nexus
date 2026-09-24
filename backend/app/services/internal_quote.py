import copy
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from functools import wraps
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.services.transaction_lock import lock_transaction

from app.models.auth import AuthUser, AuthUserRole, EmployeeProfile, SystemNotification
from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteAlternative,
    InternalQuoteAttachment,
    InternalQuoteArtifactHandoff,
    InternalQuoteAuditLog,
    InternalQuoteExportFile,
    InternalQuoteFinalReview,
    InternalQuoteImportBatch,
    InternalQuoteReferenceSet,
    InternalQuoteReview,
    InternalQuoteSection,
    InternalQuoteSectionRevision,
)
from app.schemas.internal_quote import (
    MANDATORY_SECTION_CODES,
    SECTION_CODE_ORDER,
    InternalQuoteArchiveRequest,
    InternalQuoteAuditOut,
    InternalQuoteBatchCopyRequest,
    InternalQuoteBatchProductOut,
    InternalQuoteBusinessOwnerOut,
    InternalQuoteCloneRequest,
    InternalQuoteCostPreviewOut,
    InternalQuoteCostPreviewRequest,
    InternalQuoteCreateRequest,
    InternalQuoteDashboardOut,
    InternalQuoteHeaderUpdateRequest,
    InternalQuoteOut,
    InternalQuotePageOut,
    InternalQuoteParticipationRemoveRequest,
    InternalQuoteParticipationUpdateRequest,
    InternalQuoteProductImageOut,
    InternalQuoteReasonRequest,
    InternalQuoteReferenceFxUpdateRequest,
    InternalQuoteReferenceMaterialsUpdateRequest,
    InternalQuoteReferenceSetOut,
    InternalQuoteReferenceSyncRequest,
    InternalQuoteRevisionOut,
    InternalQuoteReviewRequest,
    InternalQuoteSectionOut,
    InternalQuoteSectionPreviewOut,
    InternalQuoteSectionPreviewRequest,
    InternalQuoteSectionSaveRequest,
    InternalQuoteTimelineOut,
    InternalQuoteWholeProductSaveOut,
    InternalQuoteWholeProductSaveRequest,
)
from app.services.auth import (
    AuthContext,
    add_auth_audit,
    build_auth_context,
    can,
    ensure_permission_in_scope,
    has_permission_in_scope,
    now_text,
)
from app.services.business_authz import ensure_permission_for_departments
from app.services.internal_quote_calculator import (
    FORMULA_VERSION,
    CalculationInputError,
    build_reference_snapshot,
    calculate_section,
    canonical_json,
    content_hash,
    decimal_text,
    decimal_value,
    resolve_sales_misc_and_settlement,
    total_from_calculation,
)
from app.services.internal_quote_prefill import prefill_molding_from_engineering
from app.services.internal_quote_history import history_price_snapshot, prepare_history_sources, seed_history_product
from app.services.permission_codes import INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE


SECTION_METADATA = {
    "sales": ("业务部", ("sales-business",)),
    "engineering": ("工程部", ("engineering",)),
    "electronic": ("电子部", ("electronic",)),
    "molding": ("啤机部", ("production", "molding")),
    "painting": ("喷油部", ("production", "painting")),
    "slush": ("搪胶部", ("slush",)),
    "sewing": ("车缝部", ("sewing",)),
    "hair": ("车发部", ("hair",)),
    "assembly": ("装配部", ("assembly",)),
}
SECTION_DEFINITIONS = tuple(
    (code, *SECTION_METADATA[code]) for code in SECTION_CODE_ORDER
)
SECTION_NAMES = {code: name for code, name, _ in SECTION_DEFINITIONS}
SECTION_DEPARTMENTS = {code: departments for code, _, departments in SECTION_DEFINITIONS}
ALL_QUOTE_DEPARTMENTS = tuple(
    dict.fromkeys(department for _, _, departments in SECTION_DEFINITIONS for department in departments)
)
MUTABLE_SECTION_STATUSES = {"draft", "rejected"}
REVIEWABLE_SECTION_STATUSES = {"pending_review", "na_pending"}
COMPLETED_SECTION_STATUSES = {"approved", "sealed", "not_applicable"}
LEGACY_SECTION_REVIEW_MODULE_VERSION = "v2"
WHOLE_QUOTE_REVIEW_MODULE_VERSION = "v3"
VIEW_DEDUP_MINUTES = 5
SECTION_EDIT_NOTIFICATION_EVENTS = {
    "quote_created",
    "quote_cloned",
    "section_rejected",
    "section_reopened",
    "reference_snapshot_updated",
}
SECTION_REVIEW_NOTIFICATION_EVENTS = {"section_submitted", "section_na_requested"}
FINAL_SUBMIT_NOTIFICATION_EVENTS = {
    "ready_for_final_review",
    "final_release_rejected",
    "final_release_invalidated",
}
FINAL_REVIEW_NOTIFICATION_EVENTS = {"final_release_submitted", "whole_quote_submitted"}
ARTIFACT_NOTIFICATION_EVENTS = {"customer_price_artifact_available"}
SEWING_TAX_REFUND_FACTORY_IDS = frozenset({"huakang-c", "huakang-d"})
ACTIONABLE_INTERNAL_QUOTE_NOTIFICATION_EVENTS = (
    SECTION_EDIT_NOTIFICATION_EVENTS
    | SECTION_REVIEW_NOTIFICATION_EVENTS
    | FINAL_SUBMIT_NOTIFICATION_EVENTS
    | FINAL_REVIEW_NOTIFICATION_EVENTS
    | ARTIFACT_NOTIFICATION_EVENTS
)


def _json_object(value: str) -> dict[str, object]:
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def is_whole_quote_review(quote: InternalQuote) -> bool:
    return quote.module_version == WHOLE_QUOTE_REVIEW_MODULE_VERSION


def _ensure_section_review_workflow(quote: InternalQuote) -> None:
    if quote.module_version == "v4":
        raise HTTPException(409, "当前报价无需审核，请保存后直接输出；已输出版本请复制新版修改")
    if is_whole_quote_review(quote):
        raise HTTPException(
            status_code=409,
            detail="当前报价采用整单审核，不支持分段提交、分段审核或分段重开",
        )


def _json_list(value: str) -> list[dict[str, object]]:
    try:
        parsed = json.loads(value or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _request_metadata(request: Request | None) -> tuple[str, str]:
    if request is None:
        return "", ""
    request_id = request.headers.get("x-request-id", "").strip() or uuid4().hex
    ip_address = request.client.host if request.client else ""
    return request_id[:96], ip_address[:128]


def ensure_quote_read(db: Session, user: AuthContext, factory_id: str) -> None:
    ensure_permission_for_departments(
        db,
        user,
        "internal_quote:read",
        factory_id,
        ALL_QUOTE_DEPARTMENTS,
    )


def ensure_quote_read_access(db: Session, user: AuthContext, quote_id: str) -> None:
    factory_id = db.scalar(
        select(InternalQuote.factory_id).where(InternalQuote.id == quote_id)
    )
    if factory_id is None:
        raise HTTPException(status_code=404, detail="内部报价不存在或已被删除")
    ensure_quote_read(db, user, factory_id)


def ensure_quote_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
    departments: tuple[str, ...],
) -> None:
    ensure_permission_for_departments(db, user, permission, factory_id, departments)


def ensure_section_permission(
    db: Session,
    user: AuthContext,
    factory_id: str,
    section_code: str,
    action: str,
) -> None:
    departments = SECTION_DEPARTMENTS.get(section_code)
    if departments is None:
        raise HTTPException(status_code=404, detail="报价分段不存在")
    if action == "edit" and any(
        has_permission_in_scope(user, permission, factory_id, department)
        for permission, department in (
            ("internal_quote:sales_edit", "sales-business"),
            ("internal_quote:engineering_edit", "engineering"),
        )
    ):
        return
    ensure_quote_permission(
        db,
        user,
        f"internal_quote:{section_code}_{action}",
        factory_id,
        departments,
    )


def _initiator_department(user: AuthContext, factory_id: str) -> str:
    preferred = user.profile.primary_department if user.profile else ""
    candidates = tuple(
        dict.fromkeys(
            department
            for department in (preferred, "sales-business", "engineering")
            if department in {"sales-business", "engineering"}
        )
    )
    for department in candidates:
        if has_permission_in_scope(user, "internal_quote:clone", factory_id, department):
            return department
    raise HTTPException(status_code=403, detail="仅业务部或工程部可复制内部报价")


def quote_write(operation):
    @wraps(operation)
    def serialized(db: Session, quote_id: str, *args, **kwargs):
        identity = db.execute(select(InternalQuote.factory_id, InternalQuote.batch_id).where(
            InternalQuote.id == quote_id,
        )).first()
        if identity is None:
            raise HTTPException(404, "内部报价不存在或已被删除")
        lock_transaction(db, "internal-quote", f"{identity.factory_id}:{identity.batch_id or quote_id}")
        quote = db.get(InternalQuote, quote_id)
        if operation.__name__ == "archive_quote" and db.scalar(select(InternalQuote.id).where(
            InternalQuote.batch_id == (quote.batch_id or quote.id), InternalQuote.module_version == "v4",
            InternalQuote.final_release_status == "issued",
        )):
            raise HTTPException(409, "批次含已输出版本，请在方案面板逐版归档，保留历史文件")
        alternative = db.get(InternalQuoteAlternative, quote_id)
        if alternative and alternative.archived and operation.__name__ not in {
            "copy_alternative", "clone_quote", "archive_alternative", "create_controlled_export",
            "create_engineering_workbook_export", "select_alternative",
        }:
            raise HTTPException(409, "方案版本已归档，请先恢复后操作")
        if quote.module_version == "v4" and quote.final_release_status == "issued" and operation.__name__ not in {
            "copy_alternative", "clone_quote", "issue_alternative", "create_controlled_export",
            "select_alternative", "archive_alternative", "report_alternative",
            "create_engineering_workbook_export",
        }:
            raise HTTPException(409, "已输出版本已冻结，请复制新版本后修改")
        try:
            return operation(db, quote_id, *args, **kwargs)
        except IntegrityError as error:
            db.rollback()
            if "internal_quote_section_revisions" in str(error) or "uq_internal_quote_section_revisions" in str(error):
                raise HTTPException(409, "报价已被其他操作更新，请重新读取后核对保存") from error
            raise
    return serialized


def _get_quote(db: Session, quote_id: str) -> InternalQuote:
    quote = db.get(InternalQuote, quote_id)
    if quote is None:
        raise HTTPException(status_code=404, detail="内部报价不存在或已被删除")
    return quote


def _get_section(db: Session, quote_id: str, section_code: str) -> InternalQuoteSection:
    if section_code not in SECTION_NAMES:
        raise HTTPException(status_code=404, detail="报价分段不存在")
    section = db.scalar(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote_id,
            InternalQuoteSection.department == section_code,
        )
    )
    if section is None:
        raise HTTPException(status_code=404, detail="报价分段不存在")
    return section


def _final_release_owner(
    db: Session,
    quote: InternalQuote,
) -> tuple[str, str]:
    sales = _get_section(db, quote.id, "sales")
    return (
        sales.submitted_by_id or quote.created_by,
        sales.submitted_by or quote.created_by_name or "负责跟客",
    )


def _ensure_active(quote: InternalQuote) -> None:
    if quote.status == "archived":
        raise HTTPException(status_code=409, detail="已归档报价不可继续修改")


def _ensure_section_participates(section: InternalQuoteSection) -> None:
    if not section.is_required:
        raise HTTPException(
            status_code=409,
            detail="该部门未参与当前内部报价，请先由业务部或工程部添加参与部门",
        )


def _check_revision(current: int, supplied: int, resource: str = "分段") -> None:
    if current == supplied:
        return
    raise HTTPException(
        status_code=409,
        detail={
            "message": f"{resource}已被其他人更新，请刷新后重试",
            "current_revision": current,
        },
    )


def _section_out(
    section: InternalQuoteSection,
    *,
    payload_override: dict[str, object] | None = None,
) -> InternalQuoteSectionOut:
    return InternalQuoteSectionOut(
        id=section.id,
        department=section.department,
        department_name=section.department_name,
        status=section.status,
        payload=payload_override if payload_override is not None else _json_object(section.payload_json),
        calculation=_json_object(section.calculation_json),
        calculation_status=section.calculation_status,
        calculation_hash=section.calculation_hash,
        calculation_formula_version=section.calculation_formula_version,
        calculation_reference_snapshot_id=section.calculation_reference_snapshot_id,
        calculated_at=section.calculated_at,
        dependency_hash=section.dependency_hash,
        dependency_status=section.dependency_status,
        revision=section.revision,
        is_required=section.is_required,
        filled_by=section.filled_by,
        filled_at=section.filled_at,
        submitted_by=section.submitted_by,
        submitted_by_id=section.submitted_by_id,
        submitted_at=section.submitted_at,
        reviewed_by=section.reviewed_by,
        reviewed_at=section.reviewed_at,
        review_comment=section.review_comment,
        updated_at=section.updated_at,
    )


def quote_to_out(
    db: Session,
    quote: InternalQuote,
    *,
    include_sections: bool = True,
    section_rows: list[InternalQuoteSection] | None = None,
) -> InternalQuoteOut:
    sections: list[InternalQuoteSectionOut] = []
    if include_sections:
        rows = section_rows
        if rows is None:
            rows = list(db.scalars(
                select(InternalQuoteSection)
                .where(InternalQuoteSection.quote_id == quote.id)
                .order_by(InternalQuoteSection.id)
            ).all())
        by_code = {section.department: section for section in rows}
        payload_overrides: dict[str, dict[str, object]] = {}
        engineering = by_code.get("engineering")
        molding = by_code.get("molding")
        if (
            engineering is not None
            and molding is not None
            and engineering.is_required
            and molding.is_required
            and not (quote.module_version == "v4" and quote.final_release_status == "issued")
        ):
            payload_overrides["molding"] = prefill_molding_from_engineering(
                _json_object(engineering.payload_json),
                _json_object(molding.payload_json),
            )
        sections = [
            _section_out(by_code[code], payload_override=payload_overrides.get(code))
            for code in SECTION_NAMES
            if code in by_code
        ]

    history = db.scalar(select(InternalQuoteAuditLog).where(
        InternalQuoteAuditLog.quote_id == quote.id, InternalQuoteAuditLog.action == "history_reference"
    ).order_by(InternalQuoteAuditLog.created_at.desc()).limit(1)) if include_sections else None
    return InternalQuoteOut(
        id=quote.id,
        factory_id=quote.factory_id,
        workshop_code=quote.workshop_code,
        workshop_name=quote.workshop_name,
        quote_no=quote.quote_no,
        product_name=quote.product_name,
        quote_type=quote.quote_type or "single",
        batch_id=quote.batch_id or quote.id,
        batch_quote_no=quote.batch_quote_no or quote.quote_no,
        batch_position=quote.batch_position or 1,
        batch_size=quote.batch_size or 1,
        baseline_quote_id=quote.baseline_quote_id or quote.id,
        region_code=quote.region_code or "",
        customer=quote.customer,
        qty=quote.qty,
        version_label=quote.version_label,
        status=quote.status,
        initiator_department=quote.initiator_department,
        business_owner_id=quote.business_owner_id,
        business_owner_name=quote.business_owner_name,
        target_customer_price=quote.target_customer_price,
        target_date=quote.target_date,
        remark=quote.remark,
        module_version=quote.module_version,
        reference_snapshot_id=quote.reference_snapshot_id,
        formula_version=quote.formula_version,
        header_revision=quote.header_revision,
        cloned_from_quote_id=quote.cloned_from_quote_id,
        history_sources=_json_list(history.detail) if history else [],
        archived_by=quote.archived_by,
        archived_at=quote.archived_at,
        archive_reason=quote.archive_reason,
        final_release_status=quote.final_release_status,
        final_submission_revision=quote.final_submission_revision,
        final_submission_manifest={key: value for key, value in _json_object(quote.final_submission_manifest_json).items()
                                   if key not in {"cost_context", "rr2_cost_summary"}},
        final_submitted_by=quote.final_submitted_by,
        final_submitted_by_name=quote.final_submitted_by_name,
        final_submitted_at=quote.final_submitted_at,
        final_reviewed_by=quote.final_reviewed_by,
        final_reviewed_by_name=quote.final_reviewed_by_name,
        final_reviewed_at=quote.final_reviewed_at,
        final_review_comment=quote.final_review_comment,
        final_release_revision=quote.final_release_revision,
        final_release_invalidated_at=quote.final_release_invalidated_at,
        final_release_invalidation_reason=quote.final_release_invalidation_reason,
        created_by=quote.created_by,
        created_by_name=quote.created_by_name,
        created_at=quote.created_at,
        updated_at=quote.updated_at,
        sections=sections,
    )


def _add_audit(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    action: str,
    *,
    department: str = "",
    detail: str = "",
    old_revision: int | None = None,
    new_revision: int | None = None,
    reason: str = "",
    request: Request | None = None,
) -> InternalQuoteAuditLog:
    request_id, ip_address = _request_metadata(request)
    audit = InternalQuoteAuditLog(
        id=f"IQA-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        department=department,
        actor_id=user.id,
        actor_name=user.display_name,
        action=action,
        detail=detail,
        old_revision=old_revision,
        new_revision=new_revision,
        reason=reason,
        request_id=request_id,
        ip_address=ip_address,
        created_at=now_text(),
    )
    db.add(audit)
    return audit


def _add_notification(
    db: Session,
    quote: InternalQuote,
    *,
    title: str,
    message: str,
    event: str,
    target_user_id: str = "",
    target_permission: str = "",
    target_department: str = "sales-business",
    department: str = "",
    reason: str = "",
    extra: dict[str, object] | None = None,
) -> SystemNotification | None:
    if not target_user_id and not target_permission:
        return None
    summary_events = {
        "ready_for_final_review",
        "final_release_submitted",
        "final_release_rejected",
        "final_release_invalidated",
        "final_release_approved",
    }
    destination = "summary" if event in summary_events else "collaboration"
    route_query = {"factory": quote.factory_id}
    if destination == "collaboration" and department in SECTION_NAMES:
        route_query["section"] = department
    payload: dict[str, object] = {
        "module": "internal-quote-desk",
        "event": event,
        "quote_id": quote.id,
        "quote_no": quote.quote_no,
        "version_label": quote.version_label,
        "customer": quote.customer,
        "department": department,
        "reason": reason,
        "route": (
            f"/modules/sales-business/internal-quote-desk/{quote.id}/{destination}"
            f"?{urlencode(route_query)}"
        ),
    }
    if extra:
        payload.update(extra)
    notification = SystemNotification(
        id=f"system-notification-{uuid4().hex[:24]}",
        target_user_id=target_user_id,
        target_permission=target_permission,
        target_factory_id=quote.factory_id,
        target_department=target_department,
        type="internal_quote",
        title=title,
        message=message,
        payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        status="unread",
        created_at=now_text(),
        read_at="",
        handled_at="",
    )
    db.add(notification)
    return notification


def _mark_quote_notifications_handled(
    db: Session,
    quote: InternalQuote,
    *,
    events: set[str] | None = None,
    department: str = "",
    payload_matches: dict[str, object] | None = None,
) -> None:
    timestamp = now_text()
    notifications = db.scalars(
        select(SystemNotification).where(
            SystemNotification.type == "internal_quote",
            SystemNotification.target_factory_id == quote.factory_id,
            SystemNotification.status != "handled",
        )
    ).all()
    for notification in notifications:
        payload = _json_object(notification.payload_json)
        if payload.get("quote_id") != quote.id:
            continue
        if events is not None and payload.get("event") not in events:
            continue
        if department and payload.get("department") != department:
            continue
        if payload_matches and any(payload.get(key) != value for key, value in payload_matches.items()):
            continue
        notification.status = "handled"
        notification.read_at = notification.read_at or timestamp
        notification.handled_at = notification.handled_at or timestamp


def _invalidate_final_release(
    db: Session,
    quote: InternalQuote,
    *,
    reason: str,
) -> None:
    if quote.final_release_status not in {"pending", "approved"} and quote.status not in {
        "final_reviewing",
        "fully_approved",
        "exported",
    }:
        return
    timestamp = now_text()
    quote.final_release_status = "invalidated"
    quote.final_release_invalidated_at = timestamp
    quote.final_release_invalidation_reason = reason
    _mark_quote_notifications_handled(
        db,
        quote,
        events=FINAL_REVIEW_NOTIFICATION_EVENTS,
    )
    exports = db.scalars(
        select(InternalQuoteExportFile).where(
            InternalQuoteExportFile.quote_id == quote.id,
            InternalQuoteExportFile.status == "current",
        )
    ).all()
    for record in exports:
        record.status = "superseded"
        record.superseded_at = timestamp
    handoffs = db.scalars(
        select(InternalQuoteArtifactHandoff).where(
            InternalQuoteArtifactHandoff.quote_id == quote.id,
            InternalQuoteArtifactHandoff.status.in_(("available", "consumed")),
        )
    ).all()
    for handoff in handoffs:
        handoff.status = "revoked"
        handoff.revoked_at = timestamp
        handoff.revoke_reason = reason
        _mark_quote_notifications_handled(
            db,
            quote,
            events=ARTIFACT_NOTIFICATION_EVENTS,
            payload_matches={"release_revision": handoff.release_revision},
        )


def _add_revision(
    db: Session,
    quote: InternalQuote,
    section: InternalQuoteSection,
    user: AuthContext,
    *,
    reason: str = "",
) -> None:
    db.add(
        InternalQuoteSectionRevision(
            id=f"IQR-{uuid4().hex}",
            quote_id=quote.id,
            section_id=section.id,
            factory_id=quote.factory_id,
            department=section.department,
            revision=section.revision,
            status=section.status,
            payload_json=section.payload_json,
            calculation_json=section.calculation_json,
            formula_version=section.calculation_formula_version,
            input_hash=str(_json_object(section.calculation_json).get("input_hash", "")),
            reference_snapshot_id=section.calculation_reference_snapshot_id,
            dependency_hash=section.dependency_hash,
            warnings_json=json.dumps(
                _json_object(section.calculation_json).get("warnings", []),
                ensure_ascii=False,
                sort_keys=True,
            ),
            reason=reason,
            created_by=user.id,
            created_by_name=user.display_name,
            created_at=now_text(),
        )
    )


def _reference_out(reference: InternalQuoteReferenceSet) -> InternalQuoteReferenceSetOut:
    return InternalQuoteReferenceSetOut(
        id=reference.id,
        quote_id=reference.quote_id,
        factory_id=reference.factory_id,
        version_label=reference.version_label,
        formula_version=reference.formula_version,
        source_type=reference.source_type,
        source_revision=reference.source_revision,
        snapshot=_json_object(reference.snapshot_json),
        sha256=reference.sha256,
        is_current=reference.is_current,
        created_by=reference.created_by,
        created_by_name=reference.created_by_name,
        created_at=reference.created_at,
        superseded_at=reference.superseded_at,
    )


def _create_reference_set(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    *,
    source_type: str,
    snapshot: dict[str, object] | None = None,
) -> InternalQuoteReferenceSet:
    existing = db.scalars(
        select(InternalQuoteReferenceSet)
        .where(InternalQuoteReferenceSet.quote_id == quote.id)
        .order_by(InternalQuoteReferenceSet.source_revision.desc())
    ).all()
    timestamp = now_text()
    for item in existing:
        if item.is_current:
            item.is_current = False
            item.superseded_at = timestamp
    source_revision = (existing[0].source_revision + 1) if existing else 1
    snapshot_data = snapshot or build_reference_snapshot(
        db,
        factory_id=quote.factory_id,
        workshop_code=quote.workshop_code,
    )
    snapshot_json = canonical_json(snapshot_data)
    reference = InternalQuoteReferenceSet(
        id=f"IQREF-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        version_label=f"{FORMULA_VERSION}-r{source_revision}",
        formula_version=FORMULA_VERSION,
        source_type=source_type,
        source_revision=source_revision,
        snapshot_json=snapshot_json,
        sha256=content_hash(snapshot_data),
        is_current=True,
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=timestamp,
        superseded_at="",
    )
    db.add(reference)
    db.flush()
    quote.reference_snapshot_id = reference.id
    quote.formula_version = FORMULA_VERSION
    return reference


def _find_reference_set(
    db: Session,
    quote: InternalQuote,
) -> InternalQuoteReferenceSet | None:
    if quote.reference_snapshot_id:
        reference = db.get(InternalQuoteReferenceSet, quote.reference_snapshot_id)
        if reference is not None:
            return reference
    return db.scalar(
        select(InternalQuoteReferenceSet)
        .where(
            InternalQuoteReferenceSet.quote_id == quote.id,
            InternalQuoteReferenceSet.is_current.is_(True),
        )
        .order_by(InternalQuoteReferenceSet.source_revision.desc())
    )


def _ensure_reference_set(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
) -> InternalQuoteReferenceSet:
    reference = _find_reference_set(db, quote)
    if reference is not None:
        return reference
    return _create_reference_set(db, quote, user, source_type="legacy_lazy_init")


def _ensure_reference_set_for_read(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
) -> InternalQuoteReferenceSet:
    reference = _find_reference_set(db, quote)
    if reference is not None:
        return reference
    # Legacy quotes may predate reference snapshots. A GET may repair that
    # state only for a user who can manage references in the quote's factory;
    # cross-factory read access must never mutate foreign business data.
    ensure_quote_permission(
        db,
        user,
        "internal_quote:reference_manage",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    return _create_reference_set(db, quote, user, source_type="legacy_lazy_init")


def _section_totals(section: InternalQuoteSection) -> dict[str, object]:
    calculation = _json_object(section.calculation_json)
    totals = calculation.get("totals", {})
    return totals if isinstance(totals, dict) else {}


def quote_formula_mismatches(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> list[dict[str, str]]:
    """Return persisted quote/section calculations that predate current code."""

    mismatches: list[dict[str, str]] = []
    if quote.formula_version != FORMULA_VERSION:
        mismatches.append(
            {
                "scope": "quote",
                "section_code": "",
                "saved_formula_version": quote.formula_version or "unknown",
                "current_formula_version": FORMULA_VERSION,
            }
        )
    for section in sections:
        if not section.is_required or section.status == "not_applicable":
            continue
        if not _json_object(section.payload_json):
            continue
        if section.calculation_formula_version != FORMULA_VERSION:
            mismatches.append(
                {
                    "scope": "section",
                    "section_code": section.department,
                    "saved_formula_version": section.calculation_formula_version or "unknown",
                    "current_formula_version": FORMULA_VERSION,
                }
            )
    return mismatches


def ensure_quote_formula_current(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> None:
    mismatches = quote_formula_mismatches(quote, sections)
    if mismatches:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "报价仍使用旧版计算公式，请先执行“按当前公式重算”后再审核或导出",
                "formula_version": quote.formula_version,
                "current_formula_version": FORMULA_VERSION,
                "mismatches": mismatches,
            },
        )


def _sales_owns_packaging_material_cost(payload: dict[str, object]) -> bool:
    return bool(payload.get("packaging_materials")) or (
        payload.get("pricing_mode") == "component" and bool(payload.get("cartons"))
    )


def _validate_customer_supplied_scope(quote, section_code, payload):
    if section_code == "sales" and payload.get("customer_supplied_materials") and not (
        quote.factory_id == "huakang-b"
        and "".join(c for c in quote.customer.lower() if c.isalnum()) == "justplay"
    ):
        raise HTTPException(status_code=400, detail="客供物料仅适用于华康B JustPlay 客户")


def _cost_context(
    db: Session,
    quote: InternalQuote,
    *,
    calculation_overrides: dict[str, dict[str, object]] | None = None,
    payload_overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, Decimal]:
    if quote.module_version == "v4" and quote.final_release_status == "issued" and not calculation_overrides and not payload_overrides:
        frozen = _json_object(quote.final_submission_manifest_json).get("cost_context")
        if isinstance(frozen, dict):
            return {key: Decimal(str(value)) for key, value in frozen.items()}
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    calculation_overrides = calculation_overrides or {}
    payload_overrides = payload_overrides or {}

    def totals(section_code: str) -> dict[str, object]:
        section = by_code.get(section_code)
        if section is None or not section.is_required:
            return {}
        override = calculation_overrides.get(section_code)
        if override is not None:
            if override.get("status") != "valid":
                return {}
            value = override.get("totals", {})
            return value if isinstance(value, dict) else {}
        if section.calculation_status != "valid":
            return {}
        return _section_totals(section)

    def value(section_code: str, key: str = "total_hkd") -> Decimal:
        return decimal_value(totals(section_code).get(key), f"{section_code}.{key}")

    sales_payload = payload_overrides.get("sales")
    if sales_payload is None:
        sales_payload = _json_object(by_code["sales"].payload_json) if "sales" in by_code else {}
    sales_has_cartons = bool(sales_payload.get("cartons"))
    sales_has_packaging_materials = _sales_owns_packaging_material_cost(sales_payload)
    # Indonesia freight is a destination-specific direct cost. Historical and
    # copied payloads may still carry the field on mainland/unspecified quotes;
    # keep the stored evidence intact but never let it enter an inapplicable
    # quote's authoritative cost context.
    indonesia_freight = (
        decimal_value(sales_payload.get("indonesia_freight_hkd"), "印尼运费")
        if quote.region_code == "indonesia"
        else Decimal("0")
    )
    components = {
        "molding_hkd": value("molding"),
        "painting_hkd": value("painting"),
        "electronic_hkd": value("electronic"),
        "hardware_hkd": value("engineering", "hardware_hkd"),
        "auxiliary_hkd": value("engineering", "auxiliary_hkd"),
        "packaging_material_hkd": value("sales", "packaging_material_hkd") if sales_has_packaging_materials else value("engineering", "packaging_hkd"),
        "assembly_hkd": value("assembly", "assembly_hkd"),
        "packing_labor_hkd": value("assembly", "packaging_hkd"),
        "indonesia_freight_hkd": indonesia_freight,
        "slush_hkd": value("slush"),
        "sewing_hkd": value("sewing"),
        "hair_hkd": value("hair"),
        "carton_hkd": value("sales", "carton_hkd") if sales_has_cartons else value("engineering", "carton_hkd"),
        "customer_supplied_hkd": value("sales", "customer_supplied_hkd"),
        "mold_amortization_usd": value("engineering", "mold_amortization_usd"),
    }
    components["factory_price_hkd"] = sum(
        (value for key, value in components.items() if key not in {"mold_amortization_usd"}),
        Decimal("0"),
    )
    return components


def _summary_decimal(value: object, default: str = "0") -> Decimal:
    if value in (None, ""):
        return Decimal(default)
    try:
        parsed = Decimal(str(value))
    except Exception:
        return Decimal(default)
    return parsed if parsed.is_finite() else Decimal(default)


def _summary_markup_tiers(
    shipping_source: dict[str, object],
    fallback_markup: Decimal,
    quantity: object,
) -> tuple[list[dict[str, object]], Decimal, Decimal]:
    default_moqs = (Decimal("3000"), Decimal("5000"), Decimal("10000"))
    raw_tiers = shipping_source.get("markup_tiers", [])
    tiers: list[tuple[Decimal, Decimal, bool]] = []
    if isinstance(raw_tiers, list):
        for item in raw_tiers:
            if not isinstance(item, dict):
                tiers = []
                break
            moq = _summary_decimal(item.get("moq"))
            markup = _summary_decimal(item.get("markup_x"), decimal_text(fallback_markup))
            if moq <= 0 or moq != moq.to_integral_value() or markup < Decimal("0.01") or markup > Decimal("9.99"):
                tiers = []
                break
            tiers.append((moq, markup, item.get("include_in_output", True) is not False))
    tiers.sort(key=lambda item: item[0])
    if not tiers or any(tiers[index][0] <= tiers[index - 1][0] for index in range(1, len(tiers))):
        tiers = [(moq, fallback_markup, True) for moq in default_moqs]

    selected_moq = _summary_decimal(shipping_source.get("selected_markup_moq"))
    selected_tier = next(((moq, markup) for moq, markup, _include in tiers if moq == selected_moq), None)
    if selected_tier is not None:
        active_moq, active_markup = selected_tier
    else:
        quote_quantity = _summary_decimal(quantity, "10000")
        active_moq, active_markup, _include = tiers[0]
        for moq, markup, _include in tiers:
            if moq <= quote_quantity:
                active_moq, active_markup = moq, markup
    return (
        [
            {
                "moq": decimal_text(moq),
                "markup": decimal_text(markup),
                "is_active": moq == active_moq,
                "include_in_output": include_in_output,
            }
            for moq, markup, include_in_output in tiers
        ],
        active_moq,
        active_markup,
    )


def _rr2_cost_summary(
    sections: list[InternalQuoteSection],
    cost_context: dict[str, Decimal],
    snapshot: dict[str, object],
    quote_quantity: object = 10000,
    factory_id: str = "huaxing",
) -> dict[str, object]:
    """Build the four rr2 summary tables from saved authoritative calculations.

    The old screen mixed editable cells and browser-only formulas.  This adapter
    keeps its field names and calculation order, but reads amounts from the
    persisted section calculations so the summary cannot silently disagree with
    the released workbook.
    """

    by_code = {section.department: section for section in sections}

    def payload(code: str) -> dict[str, object]:
        section = by_code.get(code)
        value = _json_object(section.payload_json) if section is not None else {}
        if code == "electronic":
            from app.services.internal_quote_electronic import electronic_detail_payload
            return electronic_detail_payload(value)
        return value

    def calculation(code: str) -> dict[str, object]:
        section = by_code.get(code)
        if section is None or not section.is_required or section.calculation_status != "valid":
            return {}
        return _json_object(section.calculation_json)

    def totals(code: str) -> dict[str, object]:
        value = calculation(code).get("totals", {})
        return value if isinstance(value, dict) else {}

    def lines(code: str, kind: str | None = None) -> list[dict[str, object]]:
        value = calculation(code).get("line_breakdown", [])
        rows = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        return [item for item in rows if item.get("kind") == kind] if kind else rows

    def pricing_lines(code: str) -> list[dict[str, object]]:
        calculation_value = calculation(code)
        extra = calculation_value.get("pricing_breakdown", [])
        extra_rows = [item for item in extra if isinstance(item, dict)] if isinstance(extra, list) else []
        return [*lines(code), *extra_rows]

    def text_matches(value: object, pattern: str) -> bool:
        return bool(re.search(pattern, str(value or ""), flags=re.IGNORECASE))

    fx_values = snapshot.get("fx", {})
    fx_values = fx_values if isinstance(fx_values, dict) else {}
    fx_hkd_usd = _summary_decimal(fx_values.get("hkd_usd"), "7.8")
    if fx_hkd_usd <= 0:
        fx_hkd_usd = Decimal("7.8")
    fx_rmb_hkd = _summary_decimal(fx_values.get("rmb_hkd"), "0.85")
    if fx_rmb_hkd <= 0:
        fx_rmb_hkd = Decimal("0.85")

    sales_payload = payload("sales")
    sales_totals = totals("sales")
    customer_supplied_hkd = _summary_decimal(sales_totals.get("customer_supplied_hkd"))
    customer_supplied_entries = [
        {**line, "section": "sales", "label": str(line.get("item") or "客供物料"),
         "amount_hkd": decimal_text(_summary_decimal(line.get("amount_hkd")))}
        for line in lines("sales", "customer_supplied_material")
    ]
    engineering_payload = payload("engineering")
    engineering_lines = lines("engineering", "material")
    engineering_materials = engineering_payload.get("materials", [])
    engineering_materials = engineering_materials if isinstance(engineering_materials, list) else []

    categorized = {
        "吸塑": Decimal("0"),
        "胶袋": Decimal("0"),
        "彩盒/内卡": Decimal("0"),
        "电池": Decimal("0"),
        "利宝": Decimal("0"),
        "电镀": Decimal("0"),
        "其他外购": Decimal("0"),
    }
    hardware_motor = Decimal("0")
    hardware_blister = Decimal("0")
    for index, line in enumerate(engineering_lines):
        source = engineering_materials[index] if index < len(engineering_materials) and isinstance(engineering_materials[index], dict) else {}
        amount = _summary_decimal(line.get("amount_hkd"))
        category = str(line.get("category") or source.get("category") or "auxiliary")
        auxiliary_category = str(line.get("auxiliary_category") or source.get("auxiliary_category") or "其他外购")
        name = f"{line.get('item', '')} {line.get('specification', '')}"
        if category == "hardware":
            if text_matches(name, r"马达|motor"):
                hardware_motor += amount
            if text_matches(name, r"吸塑|blister"):
                hardware_blister += amount
        elif auxiliary_category in categorized:
            categorized[auxiliary_category] += amount

    for line in lines("sales", "packaging_material"):
        amount = _summary_decimal(line.get("amount_hkd"))
        category = str(line.get("category") or "")
        mapped = {
            "blister": "吸塑",
            "color_box_inner_card": "彩盒/内卡",
            "leaflet_manual": "利宝",
            "other_purchase": "其他外购",
        }.get(category, "其他外购")
        categorized[mapped] += amount
    categorized["其他外购"] += customer_supplied_hkd

    electronic_motor = Decimal("0")
    electronic_blister = Decimal("0")
    for line in lines("electronic", "electronic_component"):
        name = f"{line.get('item', '')} {line.get('specification', '')}"
        amount = _summary_decimal(line.get("amount_hkd", line.get("line_hkd")))
        if text_matches(name, r"马达|motor"):
            electronic_motor += amount
        if text_matches(name, r"吸塑|blister"):
            electronic_blister += amount

    molding_totals = totals("molding")
    has_authoritative_material_split = (
        molding_totals.get("injection_imported_material_hkd") is not None
        and molding_totals.get("injection_domestic_material_hkd") is not None
    )
    import_material = _summary_decimal(molding_totals.get("injection_imported_material_hkd"))
    domestic_material = _summary_decimal(molding_totals.get("injection_domestic_material_hkd"))
    injection_labor = _summary_decimal(molding_totals.get("injection_labor_hkd"))
    if not has_authoritative_material_split or molding_totals.get("injection_labor_hkd") is None:
        legacy_import_material = Decimal("0")
        legacy_domestic_material = Decimal("0")
        legacy_injection_labor = Decimal("0")
        for line in lines("molding", "injection"):
            quantity = _summary_decimal(line.get("quantity"), "1")
            material_amount = (
                _summary_decimal(line.get("material_amount_hkd"))
                if line.get("material_amount_hkd") is not None
                else _summary_decimal(line.get("material_cost_hkd")) * quantity
            )
            process_amount = (
                _summary_decimal(line.get("molding_amount_hkd"))
                if line.get("molding_amount_hkd") is not None
                else _summary_decimal(line.get("molding_cost_hkd")) * quantity
            )
            material_origin = str(line.get("material_origin") or "").strip().lower()
            if material_origin == "domestic" or (
                not material_origin and text_matches(line.get("material"), r"^(POM|PVC|C[- ]?PVC)")
            ):
                legacy_domestic_material += material_amount
            elif material_origin == "imported" or str(line.get("material") or "").strip():
                legacy_import_material += material_amount
            legacy_injection_labor += process_amount
        if not has_authoritative_material_split:
            import_material = legacy_import_material
            domestic_material = legacy_domestic_material
        if molding_totals.get("injection_labor_hkd") is None:
            injection_labor = legacy_injection_labor
    molding_material = (
        _summary_decimal(molding_totals.get("injection_material_hkd"))
        if molding_totals.get("injection_material_hkd") is not None
        else import_material + domestic_material
    )

    factory_price = cost_context.get("factory_price_hkd", Decimal("0"))
    painting_totals = totals("painting")
    painting_total = _summary_decimal(painting_totals.get("total_hkd"))
    painting_labor = _summary_decimal(painting_totals.get("painting_labor_hkd"))
    paint_material = _summary_decimal(painting_totals.get("paint_material_hkd"))
    if painting_totals.get("painting_labor_hkd") is None or painting_totals.get("paint_material_hkd") is None:
        painting_labor = painting_total * Decimal("0.70")
        paint_material = painting_total * Decimal("0.30")
    slush_total = _summary_decimal(totals("slush").get("total_hkd"))
    sewing_totals = totals("sewing")
    sewing_clothes_total = _summary_decimal(sewing_totals.get("clothes_hkd"))
    if sewing_totals.get("clothes_material_hkd") is not None:
        sewing_clothes_material = _summary_decimal(sewing_totals.get("clothes_material_hkd"))
    else:
        # Older calculations only stored line-level RMB amounts. Rebuild the
        # refundable material conservatively, never treating labour as material.
        sewing_clothes_material = Decimal("0")
        for line in lines("sewing", "sewing_material"):
            if str(line.get("category") or "clothes") != "clothes":
                continue
            cost_kind = str(line.get("cost_kind") or line.get("cost_type") or "")
            is_labor = cost_kind == "labor" or "人工" in f"{line.get('item', '')}{line.get('part', '')}"
            if is_labor:
                continue
            if line.get("amount_hkd") is not None:
                sewing_clothes_material += _summary_decimal(line.get("amount_hkd"))
            else:
                sewing_clothes_material += _summary_decimal(line.get("amount_rmb")) / fx_rmb_hkd
    hair_section = by_code.get("hair")
    hair_total = (
        _summary_decimal(totals("hair").get("total_hkd"))
        if hair_section is not None and hair_section.is_required
        else _summary_decimal(sewing_totals.get("hair_hkd"))
    )
    assembly_totals = totals("assembly")
    hardware_total = _summary_decimal(totals("engineering").get("hardware_hkd"))
    electronic_total = _summary_decimal(totals("electronic").get("total_hkd"))
    assembly_total = _summary_decimal(assembly_totals.get("total_hkd"))
    carton_total = cost_context.get("carton_hkd", Decimal("0"))
    # `_cost_context` is the authoritative, region-gated source. Do not read
    # the raw Sales payload here or a stale/copied mainland value can bypass
    # the destination rule in the summary and exported workbook.
    indonesia_freight = _summary_decimal(cost_context.get("indonesia_freight_hkd"))
    additional_tax = _summary_decimal(sales_payload.get("additional_tax_hkd"))

    shipping_source = sales_payload.get("shipping", {})
    shipping_source = shipping_source if isinstance(shipping_source, dict) else {}
    legacy_scenarios = sales_payload.get("scenarios", [])
    legacy_scenarios = legacy_scenarios if isinstance(legacy_scenarios, list) else []
    first_scenario = legacy_scenarios[0] if legacy_scenarios and isinstance(legacy_scenarios[0], dict) else {}
    fallback_markup = _summary_decimal(
        shipping_source.get("markup_x", first_scenario.get("markup", snapshot.get("markup", "1.2"))),
        "1.2",
    )
    markup_tiers, active_markup_moq, markup = _summary_markup_tiers(
        shipping_source,
        fallback_markup,
        quote_quantity,
    )
    packaging_markup = _summary_decimal(
        shipping_source.get("packaging_markup_x"),
        decimal_text(markup),
    )
    if packaging_markup <= 0 or packaging_markup > Decimal("9.99"):
        packaging_markup = markup
    try:
        misc_ratio, settlement = resolve_sales_misc_and_settlement(
            shipping_source,
            legacy_scenarios,
            snapshot,
        )
    except CalculationInputError:
        # Saved historical payloads must remain readable even if an obsolete
        # divisor is malformed. Save/preview paths enforce the strict bounds.
        misc_ratio = Decimal("0.02")
        settlement = Decimal("1") - misc_ratio
    freight_share = _summary_decimal(
        shipping_source.get("freight_pct", first_scenario.get("freight_share", snapshot.get("freight_share", "0.48"))),
        "0.48",
    )
    if freight_share > 1:
        freight_share /= 100
    lift_share = _summary_decimal(shipping_source.get("lifting_pct", first_scenario.get("lift_share", "")))
    if lift_share > 1:
        lift_share /= 100
    if lift_share <= 0:
        lift_share = Decimal("1") - freight_share

    freight_source = sales_payload.get("freight_calc", {})
    freight_source = freight_source if isinstance(freight_source, dict) else {}
    legacy_transport_enabled = freight_source.get("enabled", True) is not False
    freight_charge_enabled = legacy_transport_enabled and freight_source.get("freight_enabled", True) is not False
    lifting_charge_enabled = legacy_transport_enabled and freight_source.get("lifting_enabled", True) is not False
    freight_enabled = freight_charge_enabled or lifting_charge_enabled
    freight_options = sales_totals.get("freight_options", [])
    freight_options = [row for row in freight_options if isinstance(row, dict)] if isinstance(freight_options, list) else []

    def transport_parts(row: dict[str, object]) -> tuple[Decimal, Decimal]:
        if row.get("has_lifting_fee") is True:
            return (
                _summary_decimal(row.get("freight_per_piece_hkd")) if freight_charge_enabled else Decimal("0"),
                _summary_decimal(row.get("lifting_per_piece_hkd")) if lifting_charge_enabled else Decimal("0"),
            )
        legacy_total = _summary_decimal(row.get("per_piece_hkd"))
        return (
            legacy_total * freight_share if freight_charge_enabled else Decimal("0"),
            legacy_total * lift_share if lifting_charge_enabled else Decimal("0"),
        )

    yt40 = next((
        row for row in freight_options
        if str(row.get("route_key") or row.get("key") or "") == "yt40"
    ), None)
    freight, cabinet = transport_parts(yt40) if freight_enabled and yt40 else (Decimal("0"), Decimal("0"))

    # The misc ratio is a share of the grossed-up quote, not a replacement for
    # direct costs such as Indonesia freight and additional tax.  This mirrors
    # the released workbook formulas:
    #
    #   quoted price = shipping floor * markup / (1 - misc ratio)
    #   misc amount  = quoted price * misc ratio
    #
    # Consequently ``quoted price - misc amount`` always equals the price
    # before the misc gross-up.  Keep the direct miscellaneous costs separate
    # so they remain in cost totals exactly once without being displayed as the
    # percentage-based ``t2.misc`` amount.
    direct_misc_cost = indonesia_freight + additional_tax
    shipping_floor = factory_price + additional_tax
    sales_has_cartons = bool(sales_payload.get("cartons"))
    sales_has_packaging_materials = _sales_owns_packaging_material_cost(sales_payload)
    section_labels = {
        "engineering": "工程采购",
        "electronic": "电子",
        "molding": "胶件",
        "painting": "喷油",
        "slush": "搪胶",
        "sewing": "车缝",
        "hair": "车发",
        "assembly": "装配",
        "sales": "包装材料",
    }
    amount_fields = {
        "material": "amount_hkd",
        "carton": "per_piece_hkd",
        "electronic_component": "amount_hkd",
        "electronic_quote_expenses": "quote_pricing_hkd",
        "injection": "amount_hkd",
        "blow": "amount_hkd",
        "painting": "amount_hkd",
        "painting_quick_labor": "amount_hkd",
        "painting_quick_paint": "amount_hkd",
        "painting_quick_paint_tax": "amount_hkd",
        "slush": "amount_hkd",
        "hair": "amount_hkd",
        "sewing_quick": "amount_hkd",
        "sewing_material": "amount_hkd",
        "sewing_labor": "amount_hkd",
        "assembly_process": "amount_hkd_pcs",
        "assembly_manual_total": "amount_hkd_pcs",
        "packaging_material": "amount_hkd",
        "justplay_fixed_packaging": "amount_hkd",
    }

    def section_pricing_target(code: str) -> Decimal:
        if code == "engineering":
            value = _summary_decimal(totals(code).get("hardware_hkd")) + _summary_decimal(totals(code).get("auxiliary_hkd"))
            if not sales_has_packaging_materials:
                value += _summary_decimal(totals(code).get("packaging_hkd"))
            if not sales_has_cartons:
                value += _summary_decimal(totals(code).get("carton_hkd"))
            return value
        if code == "sales":
            value = _summary_decimal(totals(code).get("packaging_material_hkd")) if sales_has_packaging_materials else Decimal("0")
            if sales_has_cartons:
                value += _summary_decimal(totals(code).get("carton_hkd"))
            return value
        return _summary_decimal(totals(code).get("total_hkd"))

    def pricing_line_allowed(code: str, line: dict[str, object]) -> bool:
        kind = str(line.get("kind") or "")
        if kind not in amount_fields:
            return False
        if code == "engineering" and kind == "material":
            return str(line.get("category") or "auxiliary") != "packaging" or not sales_has_packaging_materials
        if code == "engineering" and kind == "carton":
            return not sales_has_cartons
        if code == "sales" and kind in {"packaging_material", "justplay_fixed_packaging"}:
            return sales_has_packaging_materials
        if code == "sales" and kind == "carton":
            return sales_has_cartons
        return True

    pricing_entries: list[dict[str, object]] = []
    for section_code in section_labels:
        target = section_pricing_target(section_code)
        if target <= 0:
            continue
        candidates: list[tuple[dict[str, object], Decimal]] = []
        for line in pricing_lines(section_code):
            if not pricing_line_allowed(section_code, line):
                continue
            amount = _summary_decimal(line.get("quote_pricing_hkd") if section_code == "electronic" and "quote_pricing_hkd" in line else line.get(amount_fields[str(line.get("kind"))]))
            if amount > 0:
                candidates.append((line, amount))
        candidate_total = sum((amount for _line, amount in candidates), Decimal("0"))
        if candidate_total <= 0:
            pricing_entries.append({
                "section": section_code,
                "label": section_labels[section_code],
                "kind": "",
                "category": "",
                "auxiliary_category": "",
                "amount_hkd": target,
                "pricing_component_id": "",
                "markup_override": None,
            })
            continue
        allocation_factor = target / candidate_total
        for line, amount in candidates:
            label = str(line.get("group") or line.get("item") or line.get("process") or section_labels[section_code]).strip()
            entry: dict[str, object] = {
                "section": section_code,
                "label": label or section_labels[section_code],
                **({"electronic_quote_id": line["electronic_quote_id"], "electronic_quote_name": line.get("electronic_quote_name", "")} if "electronic_quote_id" in line else {}),
                "kind": str(line.get("kind") or ""),
                "category": str(line.get("category") or ""),
                "auxiliary_category": str(line.get("auxiliary_category") or ""),
                "amount_hkd": amount * allocation_factor,
                "pricing_component_id": str(line.get("pricing_component_id") or "").strip(),
                "formula_allocation_factor": (
                    str(allocation_factor * amount / _summary_decimal(line.get("amount_hkd", line.get("line_hkd"))))
                    if "quote_pricing_hkd" in line and _summary_decimal(line.get("amount_hkd", line.get("line_hkd"))) > 0
                    else decimal_text(allocation_factor)
                ),
                "markup_override": (
                    _summary_decimal(line.get("markup_override"))
                    if line.get("markup_override") not in (None, "")
                    else None
                ),
            }
            for field in (
                "process",
                "persons",
                "total_persons",
                "teams",
                "production_qty",
                "standard_work_hours",
                "formula_code",
                "carton_length_in",
                "carton_width_in",
                "carton_height_in",
                "qty_per_carton",
                "adhesive_extra_hkd",
                "cartons_per_pallet",
                "paper_pallet_extra_hkd",
                "formula",
            ):
                if line.get(field) not in (None, ""):
                    entry[field] = line.get(field)
            pricing_entries.append(entry)

    allocated_factory_cost = sum(
        (_summary_decimal(entry.get("amount_hkd")) for entry in pricing_entries),
        Decimal("0"),
    )
    marked_factory_price = max(factory_price - customer_supplied_hkd, Decimal("0"))
    if allocated_factory_cost > marked_factory_price > 0:
        allocation_factor = marked_factory_price / allocated_factory_cost
        for entry in pricing_entries:
            entry["amount_hkd"] = _summary_decimal(entry.get("amount_hkd")) * allocation_factor
            if entry.get("formula_allocation_factor") not in (None, ""):
                entry["formula_allocation_factor"] = decimal_text(
                    _summary_decimal(entry.get("formula_allocation_factor"), "1")
                    * allocation_factor
                )
        allocated_factory_cost = marked_factory_price
    unallocated_factory_cost = marked_factory_price - allocated_factory_cost
    if unallocated_factory_cost > Decimal("0.000001"):
        pricing_entries.append({
            "section": "other",
            "label": "主体未分配成本",
            "kind": "",
            "category": "",
            "auxiliary_category": "",
            "amount_hkd": unallocated_factory_cost,
            "pricing_component_id": "",
            "markup_override": None,
        })

    raw_component_rows = sales_payload.get("pricing_components", [])
    raw_component_rows = raw_component_rows if isinstance(raw_component_rows, list) else []
    component_definitions: list[dict[str, object]] = []
    seen_component_ids: set[str] = set()
    if sales_payload.get("pricing_mode") == "component":
        for item in raw_component_rows:
            if not isinstance(item, dict):
                continue
            component_id = str(item.get("id") or "").strip()
            component_name = str(item.get("name") or "").strip()
            key = component_id.casefold()
            if not component_id or not component_name or key in seen_component_ids:
                continue
            seen_component_ids.add(key)
            component_markup = _summary_decimal(item.get("markup_x"), decimal_text(markup))
            if component_markup <= 0 or component_markup > Decimal("9.99"):
                component_markup = markup
            component_definitions.append({
                "id": component_id,
                "name": component_name,
                "markup": component_markup,
                "inherits_main_markup": item.get("markup_x") in (None, ""),
            })

    pricing_mode = "component" if component_definitions else "standard"
    base_pricing_groups: list[dict[str, object]] = []
    global_pricing_entries: list[dict[str, object]] = []
    component_pricing_entries = pricing_entries
    global_pricing_cost = Decimal("0")
    if component_definitions:
        def is_global_packaging_entry(entry: dict[str, object]) -> bool:
            section_code = str(entry.get("section") or "")
            kind = str(entry.get("kind") or "")
            category = str(entry.get("category") or "")
            label = str(entry.get("label") or "")
            if section_code == "sales":
                return True
            if section_code == "engineering" and (
                kind == "carton" or category == "packaging"
            ):
                return True
            return section_code == "assembly" and (
                category == "packaging"
                or bool(re.search(r"包装|pack", label, flags=re.IGNORECASE))
            )

        global_pricing_entries = [
            entry for entry in pricing_entries if is_global_packaging_entry(entry)
        ]
        component_pricing_entries = [
            entry for entry in pricing_entries if not is_global_packaging_entry(entry)
        ]
        for entry in pricing_entries:
            entry["is_global"] = is_global_packaging_entry(entry)
        global_pricing_cost = sum(
            (
                _summary_decimal(entry.get("amount_hkd"))
                for entry in global_pricing_entries
            ),
            Decimal("0"),
        )
        default_component_id = str(component_definitions[0]["id"])
        component_ids = {str(item["id"]) for item in component_definitions}
        component_costs = {component_id: Decimal("0") for component_id in component_ids}
        for entry in component_pricing_entries:
            component_id = str(entry.get("pricing_component_id") or "")
            if component_id not in component_ids:
                component_id = default_component_id
            component_costs[component_id] += _summary_decimal(entry.get("amount_hkd"))
        base_pricing_groups = [
            {
                "id": str(item["id"]),
                "name": str(item["name"]),
                "cost_hkd": component_costs[str(item["id"])],
                "markup": _summary_decimal(item["markup"]),
                "is_main": index == 0,
                "inherits_main_markup": bool(item.get("inherits_main_markup")),
            }
            for index, item in enumerate(component_definitions)
        ]
    else:
        detached: dict[tuple[str, str], dict[str, object]] = {}
        detached_total = Decimal("0")
        for entry in pricing_entries:
            override = entry.get("markup_override")
            override = _summary_decimal(override) if override is not None else None
            if override is None or override == markup:
                continue
            amount = _summary_decimal(entry.get("amount_hkd"))
            key = (str(entry.get("label") or "明细"), decimal_text(override))
            row = detached.setdefault(key, {
                "id": f"detail-{len(detached) + 1:02d}",
                "name": key[0],
                "cost_hkd": Decimal("0"),
                "markup": override,
                "is_main": False,
                "inherits_main_markup": False,
            })
            row["cost_hkd"] = _summary_decimal(row["cost_hkd"]) + amount
            detached_total += amount
        base_pricing_groups = [{
            "id": "main",
            "name": "主倍率汇总",
            "cost_hkd": max(marked_factory_price - detached_total, Decimal("0")),
            "markup": markup,
            "is_main": True,
            "inherits_main_markup": True,
        }, *detached.values()]

    def priced_groups(extra_main_cost: Decimal = Decimal("0")) -> tuple[list[dict[str, str]], Decimal, Decimal]:
        rows_out: list[dict[str, str]] = []
        after_markup_total = (
            (global_pricing_cost + additional_tax + extra_main_cost)
            * packaging_markup
            if component_definitions
            else Decimal("0")
        )
        for group in base_pricing_groups:
            pricing_base = _summary_decimal(group["cost_hkd"])
            if group.get("is_main") and not component_definitions:
                pricing_base += global_pricing_cost + additional_tax + extra_main_cost
            group_markup = _summary_decimal(group["markup"], decimal_text(markup))
            after_markup = pricing_base * group_markup
            after_settlement = after_markup / settlement
            after_markup_total += after_markup
            rows_out.append({
                "id": str(group["id"]),
                "name": str(group["name"]),
                "cost_hkd": decimal_text(group["cost_hkd"]),
                "pricing_base_hkd": decimal_text(pricing_base),
                "markup": decimal_text(group_markup),
                "settlement": decimal_text(settlement),
                "quoted_hkd": decimal_text(after_settlement),
                "inherits_main_markup": "true" if group.get("inherits_main_markup") else "false",
            })
        return rows_out, after_markup_total + customer_supplied_hkd, after_markup_total / settlement + customer_supplied_hkd

    pricing_groups, _base_after_markup, base_price = priced_groups()
    global_pricing_markup = (
        packaging_markup
        if component_definitions
        else (
            _summary_decimal(base_pricing_groups[0].get("markup"), decimal_text(markup))
            if base_pricing_groups
            else markup
        )
    )
    global_pricing_base = global_pricing_cost + additional_tax
    global_pricing_quote = (
        global_pricing_base * global_pricing_markup / settlement
        if settlement > 0
        else Decimal("0")
    )
    percentage_misc = (base_price - customer_supplied_hkd) * misc_ratio

    t1_values = {
        "base_price": base_price,
        "material": molding_material,
        "imp_mat": import_material,
        "dom_mat": domestic_material,
        "blow": _summary_decimal(molding_totals.get("blow_hkd")),
        "slush": slush_total,
        "sewing_hair": hair_total,
        "sewing_cloth": sewing_clothes_total,
        "hardware": max(hardware_total - hardware_motor, Decimal("0")),
        "electronic": max(electronic_total - electronic_motor, Decimal("0")),
        "motor": hardware_motor + electronic_motor,
        "suction": categorized["吸塑"] + hardware_blister + electronic_blister,
        "glue_bag": categorized["胶袋"],
    }
    t2_values = {
        "color_box": categorized["彩盒/内卡"],
        "code_before": markup,
        "code_after": Decimal("0"),
        "battery": categorized["电池"],
        "libao": categorized["利宝"],
        "plating": categorized["电镀"],
        "other_buy": categorized["其他外购"],
        "carton": carton_total,
        "freight": freight,
        "cabinet": cabinet,
        "misc": percentage_misc,
    }
    t3_values = {
        "injection_labor": injection_labor,
        "painting_labor": painting_labor,
        "paint_material": paint_material,
        "assembly_labor": assembly_total,
    }

    no_labor_cost = (
        # ``material`` is the visible combined injection-resin cost.  The two
        # legacy split keys remain in the API solely for tax/Excel compatibility
        # and must not be counted a second time.
        sum((
            value for key, value in t1_values.items()
            if key not in {"base_price", "imp_mat", "dom_mat"}
        ), Decimal("0"))
        + sum((value for key, value in t2_values.items() if key not in {"code_before", "code_after"}), Decimal("0"))
        + t3_values["injection_labor"]
        + direct_misc_cost
    )
    labor_cost = t3_values["painting_labor"] + t3_values["paint_material"] + t3_values["assembly_labor"]
    total_cost = no_labor_cost + labor_cost
    base_price = t1_values["base_price"]
    gross = base_price - no_labor_cost
    profit = base_price - total_cost

    tax_13_cost = (
        domestic_material + t1_values["hardware"] + t1_values["motor"]
        + t2_values["color_box"] + t2_values["battery"] + t2_values["libao"]
        + t2_values["other_buy"] - customer_supplied_hkd + t3_values["paint_material"] + t1_values["glue_bag"]
    )
    tax_rates = snapshot.get("tax_rates", {})
    tax_rates = tax_rates if isinstance(tax_rates, dict) else {}
    sewing_tax_refund_enabled = str(factory_id or "").strip().lower() in SEWING_TAX_REFUND_FACTORY_IDS
    sewing_clothes_rate = (
        _summary_decimal(tax_rates.get("sewing_clothes"), "0.115") * 100
        if sewing_tax_refund_enabled
        else None
    )
    tax_specs = (
        ("tax13", "含税13%类成本", tax_13_cost, None),
        ("labor13", "人工类13%", injection_labor + t3_values["painting_labor"] + t3_values["assembly_labor"], None),
        # Carton is carried as a cost category only.  It is intentionally
        # excluded from tax deduction in the authoritative summary.
        ("carton", "纸箱类", t2_values["carton"], None),
        ("tax1", "含税1%", t2_values["plating"], _summary_decimal(tax_rates.get("tax_1_percent"), "0.0099") * 100),
        ("slush3", "搪胶类3%", t1_values["slush"], _summary_decimal(tax_rates.get("slush"), "0.03") * 100),
        ("sewhair13", "车发类13%", t1_values["sewing_hair"], _summary_decimal(tax_rates.get("sewing_hair"), "0.115") * 100),
        (
            "sewcloth13",
            "车衣物料退税（仅华康C/D）",
            sewing_clothes_material,
            sewing_clothes_rate,
        ),
        ("suction6", "吸塑类6%", t1_values["suction"], _summary_decimal(tax_rates.get("blister"), "0.06") * 100),
        ("freight9", "运费类9%", t2_values["freight"], _summary_decimal(tax_rates.get("freight_tax_9"), "0.0826") * 100),
        ("tax13b", "含税13%类", tax_13_cost, _summary_decimal(tax_rates.get("tax_13_percent"), "0.115") * 100),
    )
    tax_rows: list[dict[str, object]] = []
    total_deduction = Decimal("0")
    for key, label, amount, rate_percent in tax_specs:
        deduction = amount * rate_percent / 100 if rate_percent is not None else Decimal("0")
        total_deduction += deduction
        tax_rows.append({
            "key": key,
            "label": label,
            "amount_hkd": decimal_text(amount),
            "rate_percent": None if rate_percent is None else decimal_text(rate_percent),
            "deduction_hkd": None if rate_percent is None else decimal_text(deduction),
        })
    after_deduction = total_cost - total_deduction
    t2_values["code_after"] = base_price / after_deduction if after_deduction > 0 else Decimal("0")

    def rows_from(values: dict[str, Decimal], definitions: tuple[tuple[str, str], ...]) -> list[dict[str, str]]:
        return [{"key": key, "label": label, "value": decimal_text(values[key])} for key, label in definitions]

    t1_rows: list[dict[str, object]] = rows_from(t1_values, (
        ("base_price", "货价"), ("material", "料价"), ("blow", "吹气"),
        ("slush", "搪胶"), ("sewing_hair", "车发"), ("sewing_cloth", "车衣"), ("hardware", "五金"),
        ("electronic", "电子"), ("motor", "马达"), ("suction", "吸塑"), ("glue_bag", "胶袋"),
    ))
    # Transitional compatibility for released Excel code and older clients.
    # New UI consumers hide these rows and use the combined ``material`` row.
    t1_rows.extend((
        {"key": "imp_mat", "label": "进口料", "value": decimal_text(import_material), "display": False},
        {"key": "dom_mat", "label": "国内料", "value": decimal_text(domestic_material), "display": False},
    ))
    t2_rows = rows_from(t2_values, (
        ("color_box", "彩盒/内咭"), ("code_before", "未减税前码数"), ("code_after", "减税后码数"),
        ("battery", "电池"), ("libao", "利宝"), ("plating", "电镀"), ("other_buy", "其他外购"),
        ("carton", "纸箱"), ("freight", "运费"), ("cabinet", "吊柜费"), ("misc", "杂项"),
    ))
    t3_rows = [
        *rows_from(t3_values, (("injection_labor", "啤工"), ("painting_labor", "喷油工"), ("paint_material", "油漆"), ("assembly_labor", "装配工"))),
        {"key": "no_labor_cost", "label": "不含人工成本", "value": decimal_text(no_labor_cost)},
        {"key": "labor_ratio", "label": "人工比例", "value": decimal_text(labor_cost / base_price * 100 if base_price else Decimal("0")), "format": "percent"},
        {"key": "gross", "label": "毛利", "value": decimal_text(gross)},
        {"key": "gross_ratio", "label": "毛利率", "value": decimal_text(gross / base_price * 100 if base_price else Decimal("0")), "format": "percent"},
        {"key": "profit", "label": "利润", "value": decimal_text(profit)},
        {"key": "profit_ratio", "label": "利润率", "value": decimal_text(profit / base_price * 100 if base_price else Decimal("0")), "format": "percent"},
        {"key": "total_cost", "label": "总成本", "value": decimal_text(total_cost)},
    ]

    mold_share_usd = cost_context.get("mold_amortization_usd", Decimal("0"))
    shipping_rows: list[dict[str, str]] = []
    if freight_enabled:
        option_rows: list[tuple[str, Decimal, Decimal, Decimal]] = [
            ("出厂价", Decimal("0"), Decimal("0"), Decimal("0"))
        ]
        option_rows.extend(
            (
                str(row.get("item") or row.get("label") or "出货场景"),
                *transport_parts(row),
                _summary_decimal(row.get("total_cartons")),
            )
            for row in freight_options
        )
        for name, row_freight, row_lift, total_cartons in option_rows:
            with_freight = shipping_floor + row_freight + row_lift
            row_pricing_groups, after_markup, after_settlement = priced_groups(row_freight + row_lift)
            total_usd = after_settlement / fx_hkd_usd
            shipping_rows.append({
                "name": name,
                "total_cartons": decimal_text(total_cartons),
                "shipping_floor_hkd": decimal_text(shipping_floor),
                "freight_hkd": decimal_text(row_freight),
                "lift_hkd": decimal_text(row_lift),
                "with_freight_hkd": decimal_text(with_freight),
                "after_markup_hkd": decimal_text(after_markup),
                "after_settlement_hkd": decimal_text(after_settlement),
                "total_hkd": decimal_text(after_settlement),
                "total_usd": decimal_text(total_usd),
                "mold_amortization_usd": decimal_text(mold_share_usd),
                "total_with_mold_usd": decimal_text(total_usd + mold_share_usd),
                "pricing_groups": row_pricing_groups,
            })

    return {
        "currency": "HKD",
        "indonesia_freight_hkd": decimal_text(indonesia_freight),
        "t1": t1_rows,
        "t2": t2_rows,
        "t3": t3_rows,
        "t4": tax_rows,
        "molding_material_breakdown": {
            "total_hkd": decimal_text(molding_material),
            "imported_hkd": decimal_text(import_material),
            "domestic_hkd": decimal_text(domestic_material),
        },
        "totals": {
            "rmb_purchase_cost_hkd": decimal_text(
                domestic_material + t1_values["sewing_hair"] + t1_values["sewing_cloth"]
                + t1_values["hardware"] + t1_values["electronic"] + t1_values["motor"]
                + t2_values["color_box"] + t2_values["battery"] + t2_values["libao"]
                + t2_values["plating"] + t2_values["other_buy"] + t2_values["carton"]
                + t2_values["misc"] + t1_values["glue_bag"] + t3_values["paint_material"]
                + direct_misc_cost - customer_supplied_hkd
            ),
            "total_deduction_hkd": decimal_text(total_deduction),
            "after_deduction_cost_hkd": decimal_text(after_deduction),
        },
        "shipping_pricing": {
            "enabled": freight_enabled,
            "freight_enabled": freight_charge_enabled,
            "lifting_enabled": lifting_charge_enabled,
            "freight_share_percent": decimal_text(freight_share * 100),
            "lift_share_percent": decimal_text(lift_share * 100),
            "markup": decimal_text(markup),
            "active_markup_moq": decimal_text(active_markup_moq),
            "markup_tiers": markup_tiers,
            "misc_ratio": decimal_text(misc_ratio),
            "settlement": decimal_text(settlement),
            "factory_price_hkd": decimal_text(factory_price),
            "additional_tax_hkd": decimal_text(additional_tax),
            "shipping_floor_hkd": decimal_text(shipping_floor),
            "hkd_usd": decimal_text(fx_hkd_usd),
            "mold_amortization_usd": decimal_text(mold_share_usd),
            "pricing_mode": pricing_mode,
            "pricing_groups": pricing_groups,
            "customer_supplied_hkd": decimal_text(customer_supplied_hkd),
            "customer_supplied_pricing": {
                "cost_hkd": decimal_text(customer_supplied_hkd),
                "quoted_hkd": decimal_text(customer_supplied_hkd),
                "entries": customer_supplied_entries,
            },
            "pricing_entries": [
                {
                    **entry,
                    "amount_hkd": decimal_text(entry.get("amount_hkd")),
                    "markup_override": (
                        None
                        if entry.get("markup_override") is None
                        else decimal_text(entry.get("markup_override"))
                    ),
                }
                for entry in pricing_entries
            ],
            "global_pricing": {
                "cost_hkd": decimal_text(global_pricing_cost),
                "pricing_base_hkd": decimal_text(global_pricing_base),
                "markup": decimal_text(global_pricing_markup),
                "settlement": decimal_text(settlement),
                "quoted_hkd": decimal_text(global_pricing_quote),
                "entries": [
                    {
                        **entry,
                        "amount_hkd": decimal_text(entry.get("amount_hkd")),
                        "markup_override": (
                            None
                            if entry.get("markup_override") is None
                            else decimal_text(entry.get("markup_override"))
                        ),
                    }
                    for entry in global_pricing_entries
                ],
            },
            "rows": shipping_rows,
        },
    }


def _calculation_dependencies(
    db: Session,
    quote: InternalQuote,
    section_code: str,
    *,
    payload_overrides: dict[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    payload_overrides = payload_overrides or {}
    if section_code == "molding":
        engineering = by_code.get("engineering")
        if engineering is None:
            return {}
        engineering_payload = payload_overrides.get("engineering")
        if engineering_payload is None:
            engineering_payload = _json_object(engineering.payload_json)
        source_molds = engineering_payload.get("molds", [])
        molds = source_molds if isinstance(source_molds, list) else []
        molding_dependency_fields = (
            "source_row",
            "item",
            "chinese_name",
            "mold_no",
            "material",
            "material_type",
            "color",
            "net_weight_g",
            "cavity",
            "quantity",
            "machine_code",
            "target_output",
            "cycle_time_seconds",
        )
        projected_molds = [
            {key: row.get(key) for key in molding_dependency_fields}
            for row in molds
            if isinstance(row, dict)
        ]
        return {
            # Only Engineering fields that are actually projected into Molding
            # participate in this fingerprint.  Workflow revisions and unrelated
            # Engineering costs must not return an already reviewed section.
            "engineering_molds_hash": content_hash(projected_molds),
        }
    if section_code == "sales":
        # Sales approves only the packaging, carton, freight and markup data it
        # owns. Combined quote totals are rebuilt from every section's latest
        # authoritative calculation during summary/export/final release, so a
        # later department save must not force Sales to save and submit again.
        return {}
    return {}


def _downstream_dependency_hashes(
    db: Session,
    quote: InternalQuote,
    source_section_code: str,
) -> dict[str, str]:
    target_codes: list[str] = []
    if source_section_code == "engineering":
        # Only Molding is populated from Engineering mold rows.  Painting and
        # Assembly own their own quotation/routing inputs and are not downstream
        # calculation consumers of the complete Engineering section.
        target_codes.append("molding")
    return {
        target_code: content_hash(_calculation_dependencies(db, quote, target_code))
        for target_code in target_codes
    }


def _calculate_and_apply(
    db: Session,
    quote: InternalQuote,
    section: InternalQuoteSection,
    user: AuthContext,
) -> dict[str, object]:
    reference = _ensure_reference_set(db, quote, user)
    snapshot = _json_object(reference.snapshot_json)
    cost_context = _cost_context(db, quote)
    dependencies = _calculation_dependencies(db, quote, section.department)
    section_payload = _json_object(section.payload_json)
    _validate_customer_supplied_scope(quote, section.department, section_payload)
    factory_price_hkd = cost_context["factory_price_hkd"]
    if section.department == "sales":
        factory_price_hkd -= cost_context["customer_supplied_hkd"]
    if section.department == "sales" and section_payload.get("cartons"):
        factory_price_hkd -= cost_context["carton_hkd"]
    if section.department == "sales" and _sales_owns_packaging_material_cost(section_payload):
        factory_price_hkd -= cost_context["packaging_material_hkd"]
    calculation = calculate_section(
        section.department,
        section_payload,
        snapshot,
        reference.id,
        context={
            "factory_price_hkd": decimal_text(factory_price_hkd),
            "mold_amortization_usd": decimal_text(cost_context["mold_amortization_usd"]),
            "dependencies": dependencies,
        },
    )
    section.calculation_json = canonical_json(calculation)
    section.calculation_status = str(calculation["status"])
    section.calculation_hash = str(calculation["calculation_hash"])
    section.calculation_formula_version = FORMULA_VERSION
    section.calculation_reference_snapshot_id = reference.id
    section.calculated_at = now_text()
    section.dependency_hash = str(calculation["dependency_hash"])
    section.dependency_status = "current"
    return calculation


def _invalidate_engineering_dependents(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    request: Request | None,
    previous_dependency_hashes: dict[str, str] | None = None,
) -> None:
    dependents = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department == "molding",
        )
    ).all()
    for section in dependents:
        if not section.is_required:
            continue
        if section.status == "not_applicable":
            continue
        if not _json_object(section.payload_json) and section.status == "draft":
            continue
        current_dependency_hash = content_hash(
            _calculation_dependencies(db, quote, section.department)
        )
        if previous_dependency_hashes is not None:
            if previous_dependency_hashes.get(section.department) == current_dependency_hash:
                continue
        elif section.dependency_hash == current_dependency_hash:
            continue
        if section.calculation_status == "stale" and section.dependency_status == "stale":
            continue
        old_revision = section.revision
        if section.status in REVIEWABLE_SECTION_STATUSES:
            _mark_quote_notifications_handled(
                db,
                quote,
                events=SECTION_REVIEW_NOTIFICATION_EVENTS,
                department=section.department,
            )
        section.revision += 1
        section.calculation_status = "stale"
        section.dependency_status = "stale"
        section.status = "rejected" if section.status in {"approved", "pending_review"} else "draft"
        section.review_comment = "工程模具资料已更新，请同步依赖并重新核价"
        section.updated_at = now_text()
        _add_revision(db, quote, section, user, reason="engineering_dependency_invalidated")
        _add_audit(
            db,
            quote,
            user,
            "dependency_invalidated",
            department=section.department,
            old_revision=old_revision,
            new_revision=section.revision,
            reason="工程模具计算依赖已变化",
            request=request,
        )


def _invalidate_downstream_dependencies(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    source_section_code: str,
    request: Request | None,
    previous_dependency_hashes: dict[str, str] | None = None,
) -> None:
    if source_section_code == "engineering":
        _invalidate_engineering_dependents(
            db,
            quote,
            user,
            request,
            previous_dependency_hashes,
        )
def _derive_quote_status(db: Session, quote: InternalQuote) -> None:
    if quote.status == "archived":
        return
    if quote.module_version == "v4":
        quote.status = "exported" if quote.final_release_status == "issued" else "drafting"
        quote.updated_at = now_text()
        return
    sections = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.is_required.is_(True),
        )
    ).all()
    if is_whole_quote_review(quote):
        if quote.final_release_status == "pending":
            quote.status = "final_reviewing"
        elif quote.final_release_status == "approved":
            if quote.status != "exported":
                quote.status = "fully_approved"
        else:
            complete = bool(sections) and all(
                section.filled_at
                and bool(_json_object(section.payload_json))
                and section.calculation_status == "valid"
                and section.dependency_status == "current"
                for section in sections
            )
            quote.status = "ready_for_final_review" if complete else "drafting"
        quote.updated_at = now_text()
        return
    statuses = {section.status for section in sections}
    if sections and statuses <= COMPLETED_SECTION_STATUSES:
        quote.status = "ready_for_final_review"
    elif statuses & REVIEWABLE_SECTION_STATUSES:
        quote.status = "section_reviewing"
    else:
        quote.status = "drafting"
    quote.updated_at = now_text()


def _create_sections(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    participating_sections: set[str],
    payloads: dict[str, str] | None = None,
) -> None:
    timestamp = now_text()
    for code, name, _ in SECTION_DEFINITIONS:
        is_required = code in participating_sections
        section = InternalQuoteSection(
            id=f"{quote.id}-{code}",
            quote_id=quote.id,
            department=code,
            department_name=name,
            status="draft",
            payload_json=(payloads or {}).get(code, "{}") if is_required else "{}",
            calculation_json="{}",
            calculation_status="pending",
            calculation_hash="",
            calculation_formula_version=quote.formula_version,
            calculation_reference_snapshot_id=quote.reference_snapshot_id,
            calculated_at="",
            dependency_hash="",
            dependency_status="current",
            revision=1,
            is_required=is_required,
            filled_by="",
            filled_at="",
            submitted_by="",
            submitted_by_id="",
            submitted_at="",
            reviewed_by="",
            reviewed_at="",
            review_comment="",
            updated_at=timestamp,
        )
        db.add(section)
        db.flush()
        _add_revision(db, quote, section, user, reason="initial")


def _initial_section_payloads(payload: InternalQuoteCreateRequest, product_index: int = 0) -> dict[str, str]:
    component_names = payload.products[product_index].pricing_components
    if not component_names:
        return {}
    components = [
        {"id": f"component-{index:02d}", "name": name}
        for index, name in enumerate(component_names, start=1)
    ]
    return {
        "sales": json.dumps(
            {
                "pricing_mode": "component", "pricing_components": components,
                "justplay_packaging": {
                    "adhesive_extra_hkd": 0, "paper_pallet_extra_hkd": 0,
                    "pallet_length_mm": 1000, "pallet_width_mm": 1150, "pallet_height_mm": 1300,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    }


def create_quote(
    db: Session,
    payload: InternalQuoteCreateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    ensure_permission_in_scope(
        db,
        user,
        "internal_quote:create",
        payload.factory_id,
        payload.initiator_department,
    )
    owner_name = validate_quote_business_owner(db, payload.business_owner_id, payload.factory_id, user.id)
    history_sources = prepare_history_sources(db, payload, user)
    timestamp = now_text()
    products = payload.products
    batch_id = f"IQB-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:12].upper()}"
    quote_ids = [
        f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:10].upper()}"
        for _item in products
    ]
    baseline_quote_id = quote_ids[0]
    batch_size = len(products)
    participating_sections = set(payload.participating_sections)
    notified_sections = set(participating_sections)
    batch_snapshot = build_reference_snapshot(
        db,
        factory_id=payload.factory_id,
        workshop_code=payload.workshop_code,
    )
    quotes: list[InternalQuote] = []
    for position, (quote_id, product) in enumerate(zip(quote_ids, products, strict=True), start=1):
        item_quote_no = payload.quote_no if position == 1 else f"{payload.quote_no[:123]}-P{position:02d}"
        quote = InternalQuote(
            id=quote_id,
            factory_id=payload.factory_id,
            workshop_code=payload.workshop_code,
            workshop_name=payload.workshop_name,
            quote_no=item_quote_no,
            product_name=product.product_name,
            quote_type=payload.quote_type,
            batch_id=batch_id,
            batch_quote_no=payload.quote_no,
            batch_position=position,
            batch_size=batch_size,
            baseline_quote_id=baseline_quote_id,
            region_code=product.region_code,
            customer=payload.customer,
            qty=product.qty,
            version_label=payload.version_label,
            status="drafting",
            initiator_department=payload.initiator_department,
            business_owner_id=payload.business_owner_id,
            business_owner_name=owner_name,
            target_customer_price=payload.target_customer_price,
            target_date=payload.target_date,
            remark=payload.remark,
            module_version=(
                "v4" if payload.workflow_mode == "direct_output" else
                WHOLE_QUOTE_REVIEW_MODULE_VERSION
                if payload.workflow_mode == "whole_quote_review"
                else LEGACY_SECTION_REVIEW_MODULE_VERSION
            ),
            reference_snapshot_id="",
            formula_version=FORMULA_VERSION,
            header_revision=1,
            cloned_from_quote_id="",
            archived_by="",
            archived_at="",
            archive_reason="",
            created_by=user.id,
            created_by_name=user.display_name,
            created_at=timestamp,
            updated_at=timestamp,
        )
        quotes.append(quote)
        db.add(quote)
    try:
        for quote in quotes:
            db.flush()
            product = products[quote.batch_position - 1]
            product_snapshot = history_price_snapshot(db, product, history_sources, batch_snapshot)
            _create_reference_set(
                db,
                quote,
                user,
                source_type="batch_create" if batch_size > 1 else "create",
                snapshot=product_snapshot,
            )
            product = products[quote.batch_position - 1]
            section_payloads, source_evidence, source_sections = seed_history_product(
                db, quote, product, history_sources,
                _initial_section_payloads(payload, quote.batch_position - 1), product_snapshot, user,
            )
            notified_sections.update(source_sections)
            _create_sections(
                db,
                quote,
                user,
                participating_sections | source_sections,
                section_payloads,
            )
            if source_evidence:
                by_code = {s.department: s for s in db.scalars(select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)).all()}
                for code in SECTION_NAMES:
                    section = by_code[code]
                    if not section.is_required or not _json_object(section.payload_json):
                        continue
                    if code == "molding":
                        section.payload_json = canonical_json(prefill_molding_from_engineering(
                            _json_object(by_code["engineering"].payload_json), _json_object(section.payload_json)))
                    section.revision += 1
                    _calculate_and_apply(db, quote, section, user)
                    section.filled_by, section.filled_at = user.display_name, timestamp
                    _add_revision(db, quote, section, user, reason="history_reference")
                    db.flush()
                _add_audit(db, quote, user, "history_reference", detail=canonical_json(source_evidence), request=request)
            _add_audit(
                db,
                quote,
                user,
                "create",
                department=payload.initiator_department,
                detail=json.dumps(
                    {
                        "quote_no": quote.quote_no,
                        "version_label": quote.version_label,
                        "target_customer_price": quote.target_customer_price,
                        "workflow_mode": payload.workflow_mode,
                        "quote_type": payload.quote_type,
                        "batch_id": batch_id,
                        "batch_position": quote.batch_position,
                        "batch_size": batch_size,
                    },
                    ensure_ascii=False,
                ),
                new_revision=1,
                request=request,
            )
        root_quote = quotes[0]
        for section_code, section_name, departments in SECTION_DEFINITIONS:
            if section_code not in notified_sections:
                continue
            _add_notification(
                db,
                root_quote,
                title=f"新内部报价待{section_name}协作",
                message=(
                    f"{root_quote.batch_quote_no} / {root_quote.product_name} 等 {batch_size} 款已建单，"
                    f"请进入{section_name}处理"
                ),
                event="quote_created",
                target_permission=f"internal_quote:{section_code}_edit",
                target_department=departments[0],
                department=section_code,
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="报价编号与版本已存在") from None
    except Exception:
        db.rollback()
        raise
    root_quote = quotes[0]
    db.refresh(root_quote)
    return quote_to_out(db, root_quote)


def _list_quote_sections(
    db: Session,
    quotes: list[InternalQuote],
) -> dict[str, list[InternalQuoteSection]]:
    if not quotes:
        return {}
    grouped: dict[str, list[InternalQuoteSection]] = defaultdict(list)
    for section in db.scalars(
        select(InternalQuoteSection)
        .where(InternalQuoteSection.quote_id.in_([quote.id for quote in quotes]))
        .order_by(InternalQuoteSection.quote_id, InternalQuoteSection.id)
    ).all():
        grouped[section.quote_id].append(section)
    return grouped


def list_quotes(
    db: Session,
    user: AuthContext,
    factory_id: str,
    *,
    status: str = "",
    keyword: str = "",
    include_sections: bool = False,
) -> list[InternalQuoteOut]:
    ensure_quote_read(db, user, factory_id)
    statement = select(InternalQuote).where(
        InternalQuote.factory_id == factory_id,
        InternalQuote.batch_position == 1,
    )
    if status:
        statement = statement.where(InternalQuote.status == status)
    if keyword:
        normalized = f"%{keyword.strip()}%"
        statement = statement.where(
            InternalQuote.quote_no.like(normalized)
            | InternalQuote.product_name.like(normalized)
            | InternalQuote.customer.like(normalized)
        )
    statement = statement.order_by(InternalQuote.updated_at.desc(), InternalQuote.id.desc())
    quotes = list(db.scalars(statement).all())
    sections_by_quote = _list_quote_sections(db, quotes) if include_sections else {}
    return [
        quote_to_out(
            db,
            quote,
            include_sections=include_sections,
            section_rows=sections_by_quote.get(quote.id, []) if include_sections else None,
        )
        for quote in quotes
    ]


def list_quotes_page(
    db: Session,
    user: AuthContext,
    factory_id: str,
    *,
    page: int,
    page_size: int,
    status: str = "",
    keyword: str = "",
    customer: str = "",
    include_sections: bool = False,
) -> InternalQuotePageOut:
    """Return one factory-scoped page without loading the remaining quote rows."""

    ensure_quote_read(db, user, factory_id)
    statement = select(InternalQuote).where(
        InternalQuote.factory_id == factory_id,
        InternalQuote.batch_position == 1,
    )
    if status:
        statement = statement.where(InternalQuote.status == status)
    if customer:
        statement = statement.where(InternalQuote.customer == customer)
    if keyword:
        normalized = f"%{keyword.strip()}%"
        statement = statement.where(
            InternalQuote.quote_no.like(normalized)
            | InternalQuote.product_name.like(normalized)
            | InternalQuote.customer.like(normalized)
            | InternalQuote.version_label.like(normalized)
            | InternalQuote.created_by_name.like(normalized)
            | InternalQuote.business_owner_name.like(normalized)
        )

    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    total_pages = max(1, (total + page_size - 1) // page_size)
    rows = list(db.scalars(
        statement
        .order_by(InternalQuote.updated_at.desc(), InternalQuote.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all())
    sections_by_quote = _list_quote_sections(db, rows) if include_sections else {}
    customers = [
        value
        for value in db.scalars(
            select(InternalQuote.customer)
            .where(
                InternalQuote.factory_id == factory_id,
                InternalQuote.batch_position == 1,
                InternalQuote.customer != "",
            )
            .distinct()
            .order_by(InternalQuote.customer)
        ).all()
        if value
    ]
    return InternalQuotePageOut(
        items=[
            quote_to_out(
                db,
                quote,
                include_sections=include_sections,
                section_rows=sections_by_quote.get(quote.id, []) if include_sections else None,
            )
            for quote in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        customers=customers,
    )


_DASHBOARD_COMPLETED_STATUSES = {"fully_approved", "exported"}
_DASHBOARD_CANCELED_STATUSES = {"archived"}


def _internal_quote_timestamp(value: str) -> datetime | None:
    normalized = (value or "").strip()
    if not normalized:
        return None
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=None) if parsed.tzinfo is not None else parsed


def _dashboard_period_bounds(period: str) -> tuple[datetime, datetime, str]:
    now = _internal_quote_timestamp(now_text()) or datetime.now()
    if period == "week":
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        label = "本周"
    elif period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "本月"
    else:
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        label = "本年"
    return start, now, label


def get_quote_dashboard(
    db: Session,
    user: AuthContext,
    factory_id: str,
    *,
    period: str = "month",
) -> InternalQuoteDashboardOut:
    """Return factory-scoped dashboard statistics from the full quote set.

    The selected period is the current calendar week, month or year and is
    based on quote creation time. Completion speed is measured only for quotes
    that reached final release/export: creation -> final review, with updated
    time retained as a compatibility fallback for historical completed rows.
    """

    ensure_quote_read(db, user, factory_id)
    normalized_period = period if period in {"week", "month", "year"} else "month"
    period_start, period_end, period_label = _dashboard_period_bounds(normalized_period)
    start_text = period_start.strftime("%Y-%m-%d %H:%M:%S")
    end_text = period_end.strftime("%Y-%m-%d %H:%M:%S")

    quotes = db.scalars(
        select(InternalQuote)
        .where(
            InternalQuote.factory_id == factory_id,
            InternalQuote.batch_position == 1,
            InternalQuote.created_at >= start_text,
            InternalQuote.created_at <= end_text,
        )
        .order_by(InternalQuote.updated_at.desc(), InternalQuote.id.desc())
    ).all()
    quote_ids = [quote.id for quote in quotes]
    section_rows = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id.in_(quote_ids))
    ).all() if quote_ids else []
    sections_by_quote: dict[str, list[InternalQuoteSection]] = defaultdict(list)
    for section in section_rows:
        sections_by_quote[section.quote_id].append(section)

    completed = [quote for quote in quotes if quote.status in _DASHBOARD_COMPLETED_STATUSES]
    canceled = [quote for quote in quotes if quote.status in _DASHBOARD_CANCELED_STATUSES]
    in_progress = [
        quote for quote in quotes
        if quote.status not in _DASHBOARD_COMPLETED_STATUSES | _DASHBOARD_CANCELED_STATUSES
    ]
    total = len(quotes)

    status_counts = (
        ("in_progress", "进行中", len(in_progress)),
        ("completed", "已完成", len(completed)),
        ("canceled", "已取消", len(canceled)),
    )
    status_distribution = [
        {
            "key": key,
            "label": label,
            "count": count,
            "percentage": round(count / total * 100, 1) if total else 0.0,
        }
        for key, label, count in status_counts
    ]

    customer_counts = Counter((quote.customer or "未填写客户").strip() or "未填写客户" for quote in quotes)
    customer_quote_counts = [
        {
            "customer": customer,
            "count": count,
            "percentage": round(count / total * 100, 1) if total else 0.0,
        }
        for customer, count in sorted(customer_counts.items(), key=lambda item: (-item[1], item[0].casefold()))
    ]

    progress_items: list[dict[str, object]] = []
    for quote in in_progress:
        required_sections = [section for section in sections_by_quote.get(quote.id, []) if section.is_required]
        approved_sections = sum(section.status in COMPLETED_SECTION_STATUSES for section in required_sections)
        required_count = len(required_sections)
        percentage = round(approved_sections / required_count * 100, 1) if required_count else 0.0
        progress_items.append(
            {
                "quote_id": quote.id,
                "quote_no": quote.quote_no,
                "product_name": quote.product_name,
                "customer": quote.customer or "未填写客户",
                "status": quote.status,
                "approved_sections": approved_sections,
                "required_sections": required_count,
                "percentage": percentage,
                "updated_at": quote.updated_at,
            }
        )
    progress_items.sort(key=lambda item: str(item["updated_at"]), reverse=True)
    progress_items.sort(key=lambda item: float(item["percentage"]))

    speed_samples: dict[str, list[float]] = defaultdict(list)
    for quote in completed:
        created_at = _internal_quote_timestamp(quote.created_at)
        completed_at = _internal_quote_timestamp(quote.final_reviewed_at or quote.updated_at)
        if created_at is None or completed_at is None or completed_at < created_at:
            continue
        customer = (quote.customer or "未填写客户").strip() or "未填写客户"
        speed_samples[customer].append((completed_at - created_at).total_seconds() / 3600)

    customer_speed = []
    for customer, samples in speed_samples.items():
        average_hours = sum(samples) / len(samples)
        customer_speed.append(
            {
                "customer": customer,
                "completed_count": len(samples),
                "average_hours": round(average_hours, 2),
                "average_days": round(average_hours / 24, 2),
                "fastest_hours": round(min(samples), 2),
                "slowest_hours": round(max(samples), 2),
            }
        )
    customer_speed.sort(key=lambda item: (float(item["average_hours"]), str(item["customer"]).casefold()))

    return InternalQuoteDashboardOut(
        factory_id=factory_id,
        period=normalized_period,
        period_label=period_label,
        period_start=start_text,
        period_end=end_text,
        totals={
            "total": total,
            "in_progress": len(in_progress),
            "completed": len(completed),
            "canceled": len(canceled),
        },
        status_distribution=status_distribution,
        customer_quote_counts=customer_quote_counts,
        progress_items=progress_items,
        customer_speed=customer_speed,
    )


def _is_sales_quote_reviewer(user: AuthContext) -> bool:
    # Employee organization is authoritative; old accounts fall back to an
    # active, explicit Sales binding. Wildcard access is not Sales membership.
    department = user.profile.primary_department.strip() if user.profile else ""
    if department:
        return department == "sales-business"
    return any(grant.department == "sales-business" for grant in user.grants)


def _can_review_quote(user: AuthContext, factory_id: str, created_by: str) -> bool:
    return _is_sales_quote_reviewer(user) and (
        can(user, "internal_quote:sales_review", factory_id, "sales-business")
        or (created_by == user.id and can(
            user, INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE, factory_id, "sales-business",
        ))
    )


def validate_quote_business_owner(
    db: Session, owner_id: str, factory_id: str, created_by: str,
) -> str:
    owner = db.get(AuthUser, owner_id)
    if owner is None or owner.status != "active" or not _can_review_quote(
        build_auth_context(db, owner), factory_id, created_by,
    ):
        raise HTTPException(status_code=400, detail="请选择在当前厂区具备审核权限的业务部人员")
    return owner.display_name or owner.username


def _can_self_review_own_quote(user: AuthContext, quote: InternalQuote) -> bool:
    return _is_sales_quote_reviewer(user) and quote.created_by == user.id and can(
        user,
        INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE,
        quote.factory_id,
        "sales-business",
    )


def ensure_quote_business_reviewer(
    db: Session,
    user: AuthContext,
    quote: InternalQuote,
) -> None:
    """Restrict every section review to the reviewer selected on the quote header."""

    if not quote.business_owner_id or quote.business_owner_id != user.id:
        reviewer_name = quote.business_owner_name or "建单时指定的业务审核负责人"
        raise HTTPException(
            status_code=403,
            detail=f"仅建单时指定的业务审核负责人（{reviewer_name}）可审核全部部门分段",
        )
    if not _is_sales_quote_reviewer(user):
        raise HTTPException(status_code=403, detail="只有业务部人员可以审核内部报价")
    if _can_review_quote(user, quote.factory_id, quote.created_by):
        return
    raise HTTPException(
        status_code=403,
        detail="当前账号没有分段审核权限；个人自审权限仅适用于本人创建且由本人负责的报价单",
    )


def list_business_owners(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> list[InternalQuoteBusinessOwnerOut]:
    ensure_quote_read(db, user, factory_id)
    users = db.scalars(
        select(AuthUser)
        .outerjoin(AuthUserRole, AuthUserRole.user_id == AuthUser.id)
        .outerjoin(EmployeeProfile, EmployeeProfile.user_id == AuthUser.id)
        .where(
            AuthUser.status == "active",
            or_(
                EmployeeProfile.primary_department == "sales-business",
                AuthUserRole.department == "sales-business",
            ),
        )
        .distinct()
        .order_by(AuthUser.display_name, AuthUser.username, AuthUser.id)
    ).all()
    return [
        InternalQuoteBusinessOwnerOut(
            id=item.id,
            username=item.username,
            display_name=item.display_name or item.username,
        )
        for item in users
        if _can_review_quote(build_auth_context(db, item), factory_id, user.id)
    ]


def _record_view(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    request: Request | None,
) -> None:
    latest = db.scalar(
        select(InternalQuoteAuditLog)
        .where(
            InternalQuoteAuditLog.quote_id == quote.id,
            InternalQuoteAuditLog.actor_id == user.id,
            InternalQuoteAuditLog.action == "view",
        )
        .order_by(InternalQuoteAuditLog.created_at.desc())
    )
    if latest is not None:
        try:
            viewed_at = datetime.strptime(latest.created_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            viewed_at = datetime.min
        if datetime.now() - viewed_at <= timedelta(minutes=VIEW_DEDUP_MINUTES):
            return
    _add_audit(db, quote, user, "view", request=request)
    db.commit()


def get_quote_detail(
    db: Session,
    quote_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    _record_view(db, quote, user, request)
    return quote_to_out(db, quote)


def get_quote_batch_rows(
    db: Session, quote: InternalQuote, *, for_update: bool = False,
) -> list[InternalQuote]:
    """Return the ordered product quotes that participate in one batch decision."""

    statement = select(InternalQuote).where(InternalQuote.factory_id == quote.factory_id)
    if quote.batch_id:
        statement = statement.where(
            InternalQuote.batch_id == quote.batch_id,
        )
    else:
        statement = statement.where(InternalQuote.id == quote.id)
    statement = statement.order_by(InternalQuote.batch_position, InternalQuote.id)
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    rows = list(db.scalars(statement).all())
    return rows or [quote]


def _product_image_out(attachment: InternalQuoteAttachment | None) -> InternalQuoteProductImageOut | None:
    if attachment is None:
        return None
    return InternalQuoteProductImageOut(
        id=attachment.id,
        file_name=attachment.file_name,
        content_type=attachment.content_type,
        size_bytes=attachment.size_bytes,
        uploaded_by_name=attachment.uploaded_by_name,
        uploaded_at=attachment.uploaded_at,
    )


_BATCH_HEADER_DIFFERENCE_FIELDS = (
    "qty",
    "customer",
    "target_customer_price",
    "target_date",
    "remark",
)

_DIFFERENCE_FIELD_LABELS = {
    "materials": "材料明细", "molds": "模具明细", "cartons": "纸箱明细",
    "injection_lines": "注塑明细", "blow_lines": "吹气明细", "operations": "工序明细",
    "products": "产品明细", "components": "零件明细", "groups": "产品组",
    "processes": "工序", "packaging_materials": "包装材料", "testing_fee_moqs": "测试费 MOQ",
    "customer_supplied_materials": "客供物料", "fee_rate_percent": "保管费率 %",
    "justplay_packaging": "胶纸及纸托板参数", "adhesive_extra_hkd": "胶纸附加金额 HKD/件",
    "pallet_length_mm": "托板长度 mm", "pallet_width_mm": "托板宽度 mm", "pallet_height_mm": "托板高度 mm",
    "cartons_per_pallet": "每托板装箱数", "paper_pallet_extra_hkd": "纸托板附加金额 HKD/件",
    "item": "名称", "name": "名称", "specification": "规格", "category": "类别",
    "quantity": "用量", "qty": "数量", "unit_price_rmb": "RMB 单价",
    "unit_price_hkd": "HKD 单价", "loss_rate": "损耗率", "tax_rate_percent": "税点",
    "remark": "备注", "material": "材质", "material_type": "料型", "grade": "料型",
    "net_weight_g": "净重", "cycle_time_seconds": "周期", "target_output": "目标数",
    "persons": "人数", "total_persons": "总人数", "production_qty": "生产量",
    "teams": "小组数", "testing_fee_total_usd": "测试费用",
}


def _difference_path_label(path: tuple[str | int, ...]) -> str:
    labels: list[str] = []
    for part in path:
        if isinstance(part, int):
            labels.append(f"第 {part + 1} 行")
        else:
            labels.append(_DIFFERENCE_FIELD_LABELS.get(part, part.replace("_", " ")))
    return " · ".join(labels) or "内容"


def _payload_difference_details(
    value: object,
    baseline_value: object,
    *,
    path: tuple[str | int, ...] = (),
    limit: int = 60,
) -> list[str]:
    if value == baseline_value or limit <= 0:
        return []
    if isinstance(value, dict) and isinstance(baseline_value, dict):
        details: list[str] = []
        for key in sorted(set(value) | set(baseline_value)):
            details.extend(_payload_difference_details(
                value.get(key), baseline_value.get(key), path=(*path, key), limit=limit - len(details)
            ))
            if len(details) >= limit:
                break
        return details
    if isinstance(value, list) and isinstance(baseline_value, list):
        details: list[str] = []
        for index in range(max(len(value), len(baseline_value))):
            current = value[index] if index < len(value) else None
            baseline = baseline_value[index] if index < len(baseline_value) else None
            details.extend(_payload_difference_details(
                current, baseline, path=(*path, index), limit=limit - len(details)
            ))
            if len(details) >= limit:
                break
        return details
    return [_difference_path_label(path)]


def _batch_product_differences(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    reference: InternalQuoteReferenceSet | None,
    baseline: InternalQuote,
    baseline_sections: list[InternalQuoteSection],
    baseline_reference: InternalQuoteReferenceSet | None,
) -> tuple[list[str], list[str], dict[str, list[str]]]:
    different_header_fields = [
        field
        for field in _BATCH_HEADER_DIFFERENCE_FIELDS
        if getattr(quote, field) != getattr(baseline, field)
    ]
    reference_sha256 = reference.sha256 if reference is not None else ""
    baseline_reference_sha256 = baseline_reference.sha256 if baseline_reference is not None else ""
    if reference_sha256 != baseline_reference_sha256:
        different_header_fields.append("reference_snapshot")

    section_by_code = {section.department: section for section in sections}
    baseline_section_by_code = {section.department: section for section in baseline_sections}
    different_sections: list[str] = []
    different_section_details: dict[str, list[str]] = {}
    for code in SECTION_CODE_ORDER:
        section = section_by_code.get(code)
        baseline_section = baseline_section_by_code.get(code)
        section_signature = None if section is None else content_hash({
            "is_required": section.is_required,
            "payload": _json_object(section.payload_json),
        })
        baseline_signature = None if baseline_section is None else content_hash({
            "is_required": baseline_section.is_required,
            "payload": _json_object(baseline_section.payload_json),
        })
        if section_signature != baseline_signature:
            different_sections.append(code)
            if section is None or baseline_section is None or section.is_required != baseline_section.is_required:
                different_section_details[code] = ["参与状态"]
            else:
                different_section_details[code] = _payload_difference_details(
                    _json_object(section.payload_json),
                    _json_object(baseline_section.payload_json),
                ) or ["部门内容"]
    return different_header_fields, different_sections, different_section_details


def list_quote_batch_products(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteBatchProductOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    rows = get_quote_batch_rows(db, quote)
    quote_ids = [item.id for item in rows]
    sections_by_quote = _list_quote_sections(db, rows)
    references = {
        item.id: db.get(InternalQuoteReferenceSet, item.reference_snapshot_id)
        if item.reference_snapshot_id else None
        for item in rows
    }
    images: dict[str, InternalQuoteAttachment] = {}
    if quote_ids:
        for attachment in db.scalars(
            select(InternalQuoteAttachment)
            .where(
                InternalQuoteAttachment.quote_id.in_(quote_ids),
                InternalQuoteAttachment.department == "product-image",
            )
            .order_by(
                InternalQuoteAttachment.quote_id,
                InternalQuoteAttachment.uploaded_at.desc(),
                InternalQuoteAttachment.id.desc(),
            )
        ).all():
            images.setdefault(attachment.quote_id, attachment)
    baseline = next((item for item in rows if item.id == (quote.baseline_quote_id or rows[0].id)), rows[0])
    baseline_sections = sections_by_quote.get(baseline.id, [])
    baseline_reference = references.get(baseline.id)
    output: list[InternalQuoteBatchProductOut] = []
    for item in rows:
        different_header_fields, different_sections, different_section_details = (
            ([], [], {})
            if item.id == baseline.id
            else _batch_product_differences(
                item,
                sections_by_quote.get(item.id, []),
                references.get(item.id),
                baseline,
                baseline_sections,
                baseline_reference,
            )
        )
        output.append(InternalQuoteBatchProductOut(
            quote_id=item.id,
            quote_no=item.quote_no,
            product_name=item.product_name,
            qty=item.qty,
            position=item.batch_position or 1,
            batch_size=item.batch_size or len(rows),
            quote_type=item.quote_type or "single",
            region_code=item.region_code or "",
            status=item.status,
            header_revision=item.header_revision,
            is_baseline=item.id == baseline.id,
            differs_from_baseline=bool(different_header_fields or different_sections),
            different_header_fields=different_header_fields,
            different_sections=different_sections,
            different_section_details=different_section_details,
            main_image=_product_image_out(images.get(item.id)),
        ))
    return output


def _without_import_batch_ids(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _without_import_batch_ids(item)
            for key, item in value.items()
            if key != "import_batch_id"
        }
    if isinstance(value, list):
        return [_without_import_batch_ids(item) for item in value]
    return value


def _remap_attachment_ids(value: object, mapping: dict[str, str]) -> object:
    if isinstance(value, dict):
        return {
            key: [mapping[item] for item in child if item in mapping]
            if key == "image_attachment_ids" and isinstance(child, list)
            else _remap_attachment_ids(child, mapping)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_remap_attachment_ids(item, mapping) for item in value]
    return value


@quote_write
def copy_batch_baseline_to_product(
    db: Session,
    quote_id: str,
    target_quote_id: str,
    payload: InternalQuoteBatchCopyRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    context_quote = _get_quote(db, quote_id)
    target = _get_quote(db, target_quote_id)
    ensure_quote_read(db, user, context_quote.factory_id)
    initiator_department = _initiator_department(user, context_quote.factory_id)
    ensure_permission_in_scope(
        db,
        user,
        "internal_quote:clone",
        context_quote.factory_id,
        initiator_department,
    )
    rows = get_quote_batch_rows(db, context_quote)
    baseline = next((item for item in rows if item.id == (context_quote.baseline_quote_id or rows[0].id)), rows[0])
    if target.factory_id != context_quote.factory_id or target.batch_id != context_quote.batch_id:
        raise HTTPException(status_code=409, detail="目标产品不属于当前报价批次")
    if target.id == baseline.id:
        raise HTTPException(status_code=409, detail="基准款不能复制到自身")
    _ensure_active(target)
    if target.status in {"final_reviewing", "fully_approved", "exported"}:
        raise HTTPException(status_code=409, detail="目标产品已提交审核或完成输出，不能覆盖复制")
    _check_revision(target.header_revision, payload.revision, "目标产品报价头")

    source_sections = list(db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == baseline.id)
    ).all())
    target_sections = list(db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == target.id)
    ).all())
    source_by_code = {section.department: section for section in source_sections}
    target_by_code = {section.department: section for section in target_sections}
    # A component's name and identity must still match after a baseline copy;
    # never silently attach B's old picture to a differently named A component.
    source_components = _json_object(source_by_code["sales"].payload_json).get("pricing_components", []) if "sales" in source_by_code else []
    target_components = _json_object(target_by_code["sales"].payload_json).get("pricing_components", []) if "sales" in target_by_code else []
    source_component_names = {str(c.get("id")): c.get("name") for c in source_components}
    retained_component_images = {f"component-image:{c.get('id')}" for c in target_components
                                 if source_component_names.get(str(c.get("id"))) == c.get("name")}
    timestamp = now_text()
    old_header_revision = target.header_revision
    for field in (
        "customer",
        "qty",
        "business_owner_id",
        "business_owner_name",
        "target_customer_price",
        "target_date",
        "remark",
        "module_version",
    ):
        setattr(target, field, getattr(baseline, field))
    target.cloned_from_quote_id = baseline.id
    target.header_revision += 1
    target.final_release_status = ""
    target.final_submission_manifest_json = "{}"
    target.final_submitted_by = ""
    target.final_submitted_by_name = ""
    target.final_submitted_at = ""
    target.final_reviewed_by = ""
    target.final_reviewed_by_name = ""
    target.final_reviewed_at = ""
    target.final_review_comment = ""
    target.updated_at = timestamp

    source_reference = _find_reference_set(db, baseline)
    source_snapshot = (
        _json_object(source_reference.snapshot_json)
        if source_reference is not None
        else build_reference_snapshot(
            db,
            factory_id=baseline.factory_id,
            workshop_code=baseline.workshop_code,
        )
    )
    _create_reference_set(db, target, user, source_type="batch_baseline_copy", snapshot=source_snapshot)

    db.execute(delete(InternalQuoteImportBatch).where(InternalQuoteImportBatch.quote_id == target.id))
    db.execute(
        delete(InternalQuoteAttachment).where(
            InternalQuoteAttachment.quote_id == target.id,
            InternalQuoteAttachment.department != "product-image",
            ~InternalQuoteAttachment.department.in_(retained_component_images),
        )
    )

    source_attachments = db.scalars(
        select(InternalQuoteAttachment).where(
            InternalQuoteAttachment.quote_id == baseline.id,
            InternalQuoteAttachment.department != "product-image",
            ~InternalQuoteAttachment.department.startswith("component-image:"),
        )
    ).all()
    attachment_ids = {attachment.id: f"IQATT-{uuid4().hex}" for attachment in source_attachments}
    for attachment in source_attachments:
        db.add(InternalQuoteAttachment(
            id=attachment_ids[attachment.id],
            quote_id=target.id,
            factory_id=target.factory_id,
            department=attachment.department,
            file_name=attachment.file_name,
            content_type=attachment.content_type,
            size_bytes=attachment.size_bytes,
            sha256=attachment.sha256,
            content=attachment.content,
            uploaded_by=user.id,
            uploaded_by_name=user.display_name,
            uploaded_at=timestamp,
        ))

    for code in SECTION_NAMES:
        source_section = source_by_code.get(code)
        target_section = target_by_code.get(code)
        if source_section is None or target_section is None:
            continue
        old_revision = target_section.revision
        copied_payload = _remap_attachment_ids(
            _without_import_batch_ids(_json_object(source_section.payload_json)), attachment_ids,
        )
        if code == "sales" and baseline.region_code != target.region_code:
            # Indonesia freight belongs to the destination-specific product,
            # not to the batch baseline.  Preserve an Indonesia target's own
            # value when copying common fields, and never carry the field into
            # a mainland/unspecified target.
            target_payload = _json_object(target_section.payload_json)
            target_indonesia_freight = target_payload.get("indonesia_freight_hkd")
            copied_payload.pop("indonesia_freight_hkd", None)
            if target.region_code == "indonesia" and target_indonesia_freight is not None:
                copied_payload["indonesia_freight_hkd"] = target_indonesia_freight
        target_section.is_required = source_section.is_required
        target_section.payload_json = canonical_json(copied_payload)
        target_section.status = "draft"
        target_section.revision += 1
        target_section.filled_by = user.display_name if source_section.is_required and copied_payload else ""
        target_section.filled_at = timestamp if source_section.is_required and copied_payload else ""
        target_section.submitted_by = ""
        target_section.submitted_by_id = ""
        target_section.submitted_at = ""
        target_section.reviewed_by = ""
        target_section.reviewed_at = ""
        target_section.review_comment = ""
        target_section.updated_at = timestamp
        if source_section.is_required and copied_payload:
            _calculate_and_apply(db, target, target_section, user)
        else:
            target_section.calculation_json = "{}"
            target_section.calculation_status = "pending"
            target_section.calculation_hash = ""
            target_section.calculation_formula_version = target.formula_version
            target_section.calculation_reference_snapshot_id = target.reference_snapshot_id
            target_section.calculated_at = ""
            target_section.dependency_hash = ""
            target_section.dependency_status = "current"
        _add_revision(db, target, target_section, user, reason="batch_baseline_copy")
        _add_audit(
            db,
            target,
            user,
            "batch_copy_section",
            department=code,
            old_revision=old_revision,
            new_revision=target_section.revision,
            request=request,
        )

    _derive_quote_status(db, target)
    _add_audit(
        db,
        target,
        user,
        "batch_copy_baseline",
        detail=json.dumps(
            {
                "baseline_quote_id": baseline.id,
                "target_quote_id": target.id,
                "copied_attachment_count": len(source_attachments),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        old_revision=old_header_revision,
        new_revision=target.header_revision,
        request=request,
    )
    db.commit()
    db.refresh(target)
    return quote_to_out(db, target)


@quote_write
def update_quote_header(
    db: Session,
    quote_id: str,
    payload: InternalQuoteHeaderUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:header_edit",
        quote.factory_id,
        ("sales-business",),
    )
    _ensure_active(quote)
    if quote.status in {"final_reviewing", "fully_approved", "exported"}:
        raise HTTPException(status_code=409, detail="最终审核或放行后的报价头不可直接修改，请先退回或重开分段")
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    started_section = any(
        section.is_required
        and (
            section.status != "draft"
            or section.revision > 1
            or bool(section.filled_at)
        )
        for section in sections
    )
    if started_section and not (
        is_whole_quote_review(quote) and quote.status == "rejected"
    ):
        raise HTTPException(
            status_code=409,
            detail="已有参与分段开始填写；为避免数量或负责人变更与成本 revision 不一致，报价头只能在协作填写前修改",
        )
    _check_revision(quote.header_revision, payload.revision, "报价头")
    owner_name = None
    if payload.business_owner_id is not None or payload.business_owner_name is not None:
        owner_name = validate_quote_business_owner(
            db, payload.business_owner_id or quote.business_owner_id, quote.factory_id, quote.created_by,
        )
    prospective_customer = payload.customer if payload.customer is not None else quote.customer
    if payload.customer is not None and payload.customer != quote.customer:
        sales = next((section for section in sections if section.department == "sales"), None)
        sales_payload = _json_object(sales.payload_json) if sales is not None else {}
        has_components = (
            sales_payload.get("pricing_mode") == "component"
            and bool(sales_payload.get("pricing_components"))
        )
        normalized_factory = re.sub(r"[^a-z0-9]", "", quote.factory_id.casefold())
        normalized_customer = re.sub(r"[^a-z0-9]", "", prospective_customer.casefold())
        is_justplay = normalized_factory == "huakangb" and normalized_customer == "justplay"
        if is_justplay and not has_components:
            raise HTTPException(
                status_code=409,
                detail="切换为华康B JustPlay 客户前，业务部分段必须先建立报价分项",
            )
        if not is_justplay and has_components:
            raise HTTPException(
                status_code=409,
                detail="当前报价含 JustPlay 独立分项，不能直接切换为普通客户，请另建普通客户报价",
            )
    cost_inputs_changed = (
        (payload.customer is not None and payload.customer != quote.customer)
        or (payload.qty is not None and payload.qty != quote.qty)
    )
    if started_section and cost_inputs_changed:
        ensure_quote_formula_current(quote, sections)
    old_revision = quote.header_revision
    for field, value in payload.model_dump(exclude={"revision"}, exclude_none=True).items():
        setattr(quote, field, value)
    if owner_name is not None:
        quote.business_owner_name = owner_name
    quote.header_revision += 1
    quote.updated_at = now_text()
    if started_section and cost_inputs_changed:
        for section_code in SECTION_CODE_ORDER:
            section = next(
                (row for row in sections if row.department == section_code),
                None,
            )
            if (
                section is None
                or not section.is_required
                or section.status == "not_applicable"
                or not _json_object(section.payload_json)
            ):
                continue
            old_section_revision = section.revision
            section.revision += 1
            try:
                _calculate_and_apply(db, quote, section, user)
            except CalculationInputError as error:
                db.rollback()
                raise HTTPException(status_code=400, detail=str(error)) from error
            section.status = "draft"
            section.review_comment = "报价客户或数量已调整，系统已按新报价头重算"
            section.updated_at = now_text()
            _add_revision(db, quote, section, user, reason="header_cost_input_recalculated")
            _add_audit(
                db,
                quote,
                user,
                "header_recalculated_section",
                department=section.department,
                old_revision=old_section_revision,
                new_revision=section.revision,
                reason="客户或数量变更",
                request=request,
            )
        quote.final_release_status = "rejected"
        _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "header_edit",
        department="sales",
        old_revision=old_revision,
        new_revision=quote.header_revision,
        request=request,
    )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


@quote_write
def add_quote_participation(
    db: Session,
    quote_id: str,
    payload: InternalQuoteParticipationUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:create",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")

    sections = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department.in_(payload.add_sections),
        )
    ).all()
    newly_active = [section for section in sections if not section.is_required]
    if not newly_active:
        raise HTTPException(status_code=409, detail="所选部门已参与当前内部报价")

    had_final_release = quote.final_release_status in {"pending", "approved"} or quote.status in {
        "final_reviewing",
        "fully_approved",
        "exported",
    }
    added_names = "、".join(section.department_name for section in newly_active)
    _invalidate_final_release(db, quote, reason=f"新增参与部门：{added_names}")

    old_header_revision = quote.header_revision
    timestamp = now_text()
    for section in newly_active:
        section.is_required = True
        section.status = "draft"
        section.payload_json = "{}"
        section.calculation_json = "{}"
        section.calculation_status = "pending"
        section.calculation_hash = ""
        section.calculation_formula_version = quote.formula_version
        section.calculation_reference_snapshot_id = quote.reference_snapshot_id
        section.calculated_at = ""
        section.dependency_hash = ""
        section.dependency_status = "current"
        section.revision += 1
        section.filled_by = ""
        section.filled_at = ""
        section.submitted_by = ""
        section.submitted_by_id = ""
        section.submitted_at = ""
        section.reviewed_by = ""
        section.reviewed_at = ""
        section.review_comment = ""
        section.updated_at = timestamp
        _add_revision(db, quote, section, user, reason="participation_added")
        _add_notification(
            db,
            quote,
            title=f"内部报价新增{section.department_name}协作",
            message=f"{quote.quote_no} 已追加{section.department_name}参与，请进入分段填写",
            event="participation_added",
            target_permission=f"internal_quote:{section.department}_edit",
            target_department=SECTION_DEPARTMENTS[section.department][0],
            department=section.department,
            extra={"section_revision": section.revision},
        )

    quote.header_revision += 1
    quote.updated_at = timestamp
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "participation_added",
        department=quote.initiator_department,
        detail=json.dumps(
            {
                "added_sections": [section.department for section in newly_active],
                "added_names": [section.department_name for section in newly_active],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        old_revision=old_header_revision,
        new_revision=quote.header_revision,
        request=request,
    )
    if had_final_release:
        _add_notification(
            db,
            quote,
            title="内部报价最终放行已失效",
            message=f"{quote.quote_no} 因新增{added_names}参与，需重新完成分段审批和最终放行",
            event="final_release_invalidated",
            target_user_id=_final_release_owner(db, quote)[0],
            department="sales",
        )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


@quote_write
def remove_quote_participation(
    db: Session,
    quote_id: str,
    payload: InternalQuoteParticipationRemoveRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:create",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")

    sections = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department.in_(payload.remove_sections),
        )
    ).all()
    active_sections = [section for section in sections if section.is_required]
    if not active_sections:
        raise HTTPException(status_code=409, detail="所选部门未参与当前内部报价")

    had_final_release = quote.final_release_status in {"pending", "approved"} or quote.status in {
        "final_reviewing",
        "fully_approved",
        "exported",
    }
    removed_names = "、".join(section.department_name for section in active_sections)
    _invalidate_final_release(db, quote, reason=f"移除参与部门：{removed_names}")

    old_header_revision = quote.header_revision
    timestamp = now_text()
    for section in active_sections:
        previous_dependency_hashes = _downstream_dependency_hashes(
            db,
            quote,
            section.department,
        )
        old_section_revision = section.revision
        section.is_required = False
        section.status = "draft"
        section.payload_json = "{}"
        section.calculation_json = "{}"
        section.calculation_status = "pending"
        section.calculation_hash = ""
        section.calculation_formula_version = quote.formula_version
        section.calculation_reference_snapshot_id = quote.reference_snapshot_id
        section.calculated_at = ""
        section.dependency_hash = ""
        section.dependency_status = "current"
        section.revision += 1
        section.filled_by = ""
        section.filled_at = ""
        section.submitted_by = ""
        section.submitted_by_id = ""
        section.submitted_at = ""
        section.reviewed_by = ""
        section.reviewed_at = ""
        section.review_comment = ""
        section.updated_at = timestamp
        _add_revision(db, quote, section, user, reason="participation_removed")
        _add_audit(
            db,
            quote,
            user,
            "participation_section_removed",
            department=section.department,
            old_revision=old_section_revision,
            new_revision=section.revision,
            reason=f"不再需要{section.department_name}报价",
            request=request,
        )
        _mark_quote_notifications_handled(
            db,
            quote,
            events=ACTIONABLE_INTERNAL_QUOTE_NOTIFICATION_EVENTS | {"participation_added"},
            department=section.department,
        )
        _invalidate_downstream_dependencies(
            db,
            quote,
            user,
            section.department,
            request,
            previous_dependency_hashes,
        )

    quote.header_revision += 1
    quote.updated_at = timestamp
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "participation_removed",
        department=quote.initiator_department,
        detail=json.dumps(
            {
                "removed_sections": [section.department for section in active_sections],
                "removed_names": [section.department_name for section in active_sections],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        old_revision=old_header_revision,
        new_revision=quote.header_revision,
        request=request,
    )
    if had_final_release:
        _add_notification(
            db,
            quote,
            title="内部报价最终放行已失效",
            message=f"{quote.quote_no} 因移除{removed_names}参与，需重新完成分段审批和最终放行",
            event="final_release_invalidated",
            target_user_id=_final_release_owner(db, quote)[0],
            department="sales",
        )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


@quote_write
def clone_quote(
    db: Session,
    quote_id: str,
    payload: InternalQuoteCloneRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    source = _get_quote(db, quote_id)
    ensure_quote_read(db, user, source.factory_id)
    initiator_department = _initiator_department(user, source.factory_id)
    ensure_permission_in_scope(
        db,
        user,
        "internal_quote:clone",
        source.factory_id,
        initiator_department,
    )
    owner_name = validate_quote_business_owner(db, payload.business_owner_id, source.factory_id, user.id)
    source_sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == source.id)
    ).all()
    payloads = {section.department: section.payload_json for section in source_sections}
    timestamp = now_text()
    target_id = f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:10].upper()}"
    target = InternalQuote(
        id=target_id,
        factory_id=source.factory_id,
        workshop_code=source.workshop_code,
        workshop_name=source.workshop_name,
        quote_no=payload.quote_no,
        product_name=source.product_name,
        quote_type="single",
        batch_id=target_id,
        batch_quote_no=payload.quote_no,
        batch_position=1,
        batch_size=1,
        baseline_quote_id=target_id,
        region_code=source.region_code,
        customer=source.customer,
        qty=source.qty,
        version_label=payload.version_label,
        status="drafting",
        initiator_department=initiator_department,
        business_owner_id=payload.business_owner_id,
        business_owner_name=owner_name,
        target_customer_price=(
            source.target_customer_price
            if payload.target_customer_price is None
            else payload.target_customer_price
        ),
        target_date=payload.target_date,
        remark=source.remark if payload.remark is None else payload.remark,
        module_version=(
            "v4" if payload.workflow_mode == "direct_output" else
            WHOLE_QUOTE_REVIEW_MODULE_VERSION
            if payload.workflow_mode == "whole_quote_review"
            else LEGACY_SECTION_REVIEW_MODULE_VERSION
            if payload.workflow_mode == "section_review"
            else source.module_version
        ),
        reference_snapshot_id="",
        formula_version=FORMULA_VERSION,
        header_revision=1,
        cloned_from_quote_id=source.id,
        archived_by="",
        archived_at="",
        archive_reason="",
        created_by=user.id,
        created_by_name=user.display_name,
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.add(target)
    try:
        db.flush()
        source_reference = (
            db.get(InternalQuoteReferenceSet, source.reference_snapshot_id)
            if source.reference_snapshot_id
            else None
        )
        source_snapshot = (
            _json_object(source_reference.snapshot_json)
            if source_reference is not None
            else build_reference_snapshot(
                db,
                factory_id=source.factory_id,
                workshop_code=source.workshop_code,
            )
        )
        _create_reference_set(
            db,
            target,
            user,
            source_type="clone",
            snapshot=source_snapshot,
        )
        participating_sections = (
            set(payload.participating_sections)
            if payload.participating_sections is not None
            else {section.department for section in source_sections if section.is_required}
        )
        participating_sections.update(MANDATORY_SECTION_CODES)
        _create_sections(db, target, user, participating_sections, payloads)
        _add_audit(
            db,
            source,
            user,
            "clone_source",
            department=initiator_department,
            detail=target.id,
            request=request,
        )
        _add_audit(
            db,
            target,
            user,
            "clone",
            department=initiator_department,
            detail=source.id,
            new_revision=1,
            request=request,
        )
        for section_code, section_name, departments in SECTION_DEFINITIONS:
            if section_code not in participating_sections:
                continue
            _add_notification(
                db,
                target,
                title=f"复制内部报价待{section_name}重新核价",
                message=f"{target.quote_no} / {target.product_name} 已由历史版本复制，请进入{section_name}分段重新核价",
                event="quote_cloned",
                target_permission=f"internal_quote:{section_code}_edit",
                target_department=departments[0],
                department=section_code,
                extra={"source_quote_id": source.id},
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="复制后的报价编号与版本已存在") from None
    db.refresh(target)
    return quote_to_out(db, target)


def preview_quote_costs(
    db: Session,
    quote_id: str,
    payload: InternalQuoteCostPreviewRequest,
    user: AuthContext,
) -> InternalQuoteCostPreviewOut:
    """Preview every dirty department together using the authoritative calculator."""

    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    draft_by_code = {draft.section_code: draft for draft in payload.drafts}
    payload_overrides: dict[str, dict[str, object]] = {}
    for section_code, draft in draft_by_code.items():
        ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
        section = by_code.get(section_code)
        if section is None:
            raise HTTPException(status_code=404, detail="报价分段不存在")
        _ensure_section_participates(section)
        _check_revision(section.revision, draft.revision)
        if section.status not in MUTABLE_SECTION_STATUSES:
            raise HTTPException(status_code=409, detail=f"{section.department_name}当前状态不可试算")
        payload_overrides[section_code] = draft.payload

    reference = _find_reference_set(db, quote)
    if reference is None:
        raise HTTPException(status_code=409, detail="报价缺少冻结参考快照，暂时无法实时试算")
    snapshot = _json_object(reference.snapshot_json)
    saved_context = _cost_context(db, quote)
    calculation_overrides: dict[str, dict[str, object]] = {}
    calculations: dict[str, dict[str, object]] = {}
    warnings: list[dict[str, object]] = []

    for section_code in SECTION_CODE_ORDER:
        draft = draft_by_code.get(section_code)
        if draft is None:
            continue
        current_context = _cost_context(
            db,
            quote,
            calculation_overrides=calculation_overrides,
            payload_overrides=payload_overrides,
        )
        factory_price_hkd = current_context["factory_price_hkd"]
        _validate_customer_supplied_scope(quote, section_code, draft.payload)
        if section_code == "sales":
            factory_price_hkd -= current_context["customer_supplied_hkd"]
        if section_code == "sales" and draft.payload.get("cartons"):
            factory_price_hkd -= current_context["carton_hkd"]
        if section_code == "sales" and _sales_owns_packaging_material_cost(draft.payload):
            factory_price_hkd -= current_context["packaging_material_hkd"]
        try:
            calculation = calculate_section(
                section_code,
                draft.payload,
                snapshot,
                reference.id,
                context={
                    "factory_price_hkd": decimal_text(factory_price_hkd),
                    "mold_amortization_usd": decimal_text(current_context["mold_amortization_usd"]),
                    "dependencies": _calculation_dependencies(
                        db,
                        quote,
                        section_code,
                        payload_overrides=payload_overrides,
                    ),
                },
            )
        except CalculationInputError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        calculations[section_code] = calculation
        warning_rows = calculation.get("warnings", [])
        if isinstance(warning_rows, list):
            warnings.extend(
                {"section_code": section_code, **item}
                for item in warning_rows
                if isinstance(item, dict)
            )
        if calculation.get("status") == "valid":
            calculation_overrides[section_code] = calculation

    preview_context = _cost_context(
        db,
        quote,
        calculation_overrides=calculation_overrides,
        payload_overrides=payload_overrides,
    )
    preview_sections = [copy.copy(section) for section in sections]
    for section in preview_sections:
        preview_payload = payload_overrides.get(section.department)
        preview_calculation = calculations.get(section.department)
        if preview_payload is not None:
            section.payload_json = canonical_json(preview_payload)
        if preview_calculation is not None:
            section.calculation_json = canonical_json(preview_calculation)
            section.calculation_status = str(preview_calculation.get("status", "blocked"))
            section.calculation_formula_version = FORMULA_VERSION
            section.calculation_reference_snapshot_id = reference.id
    rr2_cost_summary = _rr2_cost_summary(
        [section for section in preview_sections if section.is_required],
        preview_context,
        snapshot,
        quote.qty,
        factory_id=quote.factory_id,
    )
    saved_factory_price = saved_context["factory_price_hkd"]
    preview_factory_price = preview_context["factory_price_hkd"]
    return InternalQuoteCostPreviewOut(
        quote_id=quote.id,
        calculations=calculations,
        warnings=warnings,
        saved_factory_price_hkd=decimal_text(saved_factory_price),
        preview_factory_price_hkd=decimal_text(preview_factory_price),
        delta_hkd=decimal_text(preview_factory_price - saved_factory_price),
        components_hkd={
            key: decimal_text(value)
            for key, value in preview_context.items()
            if key not in {"factory_price_hkd", "mold_amortization_usd"}
        },
        rr2_cost_summary=rr2_cost_summary,
        formula_version=FORMULA_VERSION,
        reference_snapshot_id=reference.id,
        generated_at=now_text(),
    )


def preview_section_cost(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteSectionPreviewRequest,
    user: AuthContext,
) -> InternalQuoteSectionPreviewOut:
    preview = preview_quote_costs(
        db,
        quote_id,
        InternalQuoteCostPreviewRequest(
            drafts=[
                {
                    "section_code": section_code,
                    "revision": payload.revision,
                    "payload": payload.payload,
                }
            ]
        ),
        user,
    )
    calculation = preview.calculations.get(section_code, {})
    return InternalQuoteSectionPreviewOut(
        quote_id=preview.quote_id,
        section_code=section_code,
        section_revision=payload.revision,
        calculation_status=str(calculation.get("status", "blocked")),
        calculation=calculation,
        warnings=preview.warnings,
        saved_factory_price_hkd=preview.saved_factory_price_hkd,
        preview_factory_price_hkd=preview.preview_factory_price_hkd,
        delta_hkd=preview.delta_hkd,
        components_hkd=preview.components_hkd,
        rr2_cost_summary=preview.rr2_cost_summary,
        formula_version=preview.formula_version,
        reference_snapshot_id=preview.reference_snapshot_id,
        generated_at=preview.generated_at,
    )


def _save_section_in_transaction(
    db: Session,
    quote: InternalQuote,
    section: InternalQuoteSection,
    next_payload: dict[str, object],
    reason: str,
    user: AuthContext,
    request: Request | None,
) -> InternalQuoteSection:
    if section.department == "electronic" and "quote_groups" in _json_object(section.payload_json) and "quote_groups" not in next_payload:
        raise HTTPException(status_code=409, detail="电子部包含多份独立报价，请刷新页面后逐份编辑，不能用旧版单份数据覆盖")
    next_payload_json = canonical_json(next_payload)
    current_payload_json = canonical_json(_json_object(section.payload_json))
    payload_unchanged = next_payload_json == current_payload_json
    if payload_unchanged and (
        not next_payload
        or (
            section.calculation_status == "valid"
            and section.dependency_status == "current"
            and section.calculation_formula_version == FORMULA_VERSION
            and section.calculation_reference_snapshot_id == quote.reference_snapshot_id
        )
    ):
        return section
    previous_dependency_hashes = _downstream_dependency_hashes(
        db,
        quote,
        section.department,
    )
    old_revision = section.revision
    section.payload_json = next_payload_json
    if quote.module_version == "v4":
        # Copy/issue carry the header revision: any saved department edit must
        # invalidate an older page's view of this product before it can freeze it.
        quote.header_revision += 1
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
    _add_revision(db, quote, section, user, reason=reason)
    _invalidate_downstream_dependencies(
        db,
        quote,
        user,
        section.department,
        request,
        previous_dependency_hashes,
    )
    _add_audit(
        db,
        quote,
        user,
        "save",
        department=section.department,
        old_revision=old_revision,
        new_revision=section.revision,
        reason=reason,
        request=request,
    )
    return section


@quote_write
def save_section(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteSectionSaveRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in MUTABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前状态不可编辑，请先重新打开")
    _save_section_in_transaction(
        db, quote, section, payload.payload, payload.reason, user, request
    )
    _derive_quote_status(db, quote)
    db.commit()
    db.refresh(section)
    return _section_out(section)


@quote_write
def save_whole_product_sections(
    db: Session,
    quote_id: str,
    payload: InternalQuoteWholeProductSaveRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteWholeProductSaveOut:
    """Save a product's dirty departments as one database transaction."""

    quote = _get_quote(db, quote_id)
    _ensure_active(quote)
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    drafts = {draft.section_code: draft for draft in payload.sections}

    # Check every optimistic-lock revision before changing any department.
    for section_code, draft in drafts.items():
        ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
        section = by_code.get(section_code)
        if section is None:
            raise HTTPException(status_code=404, detail="报价分段不存在")
        _ensure_section_participates(section)
        _check_revision(section.revision, draft.revision)
        if section.status not in MUTABLE_SECTION_STATUSES:
            raise HTTPException(status_code=409, detail=f"{section.department_name}当前状态不可编辑")

    try:
        for section_code in SECTION_CODE_ORDER:
            draft = drafts.get(section_code)
            if draft is None:
                continue
            section = by_code[section_code]
            _save_section_in_transaction(
                db,
                quote,
                section,
                draft.payload,
                payload.reason,
                user,
                request,
            )
        _derive_quote_status(db, quote)
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(quote)
    refreshed = db.scalars(
        select(InternalQuoteSection)
        .where(InternalQuoteSection.quote_id == quote.id)
        .order_by(InternalQuoteSection.id)
    ).all()
    refreshed_by_code = {section.department: section for section in refreshed}
    return InternalQuoteWholeProductSaveOut(
        quote=quote_to_out(db, quote, section_rows=list(refreshed)),
        sections=[
            _section_out(refreshed_by_code[code])
            for code in SECTION_CODE_ORDER
            if code in drafts and code in refreshed_by_code
        ],
    )


@quote_write
def submit_section(
    db: Session,
    quote_id: str,
    section_code: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    _ensure_section_review_workflow(quote)
    ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, revision)
    if section.status not in MUTABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前状态不可提交审核")
    if not _json_object(section.payload_json):
        raise HTTPException(status_code=400, detail="请先填写并保存本分段内容")
    try:
        calculation = _calculate_and_apply(db, quote, section, user)
    except CalculationInputError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if calculation.get("status") != "valid" or section.dependency_status != "current":
        raise HTTPException(
            status_code=409,
            detail={
                "message": "分段计算存在阻断警告或依赖已失效，不能提交审核",
                "warnings": calculation.get("warnings", []),
            },
        )
    old_revision = section.revision
    section.status = "pending_review"
    section.revision += 1
    section.submitted_by = user.display_name
    section.submitted_by_id = user.id
    section.submitted_at = now_text()
    section.reviewed_by = ""
    section.reviewed_at = ""
    section.review_comment = ""
    section.updated_at = now_text()
    _add_revision(db, quote, section, user, reason="submit")
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "submit",
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=SECTION_EDIT_NOTIFICATION_EVENTS,
        department=section_code,
    )
    _add_notification(
        db,
        quote,
        title=f"{section.department_name}分段待审核",
        message=(
            f"{quote.quote_no} 的{section.department_name}分段已提交，"
            f"请业务审核负责人 {quote.business_owner_name} 审核"
        ),
        event="section_submitted",
        target_user_id=quote.business_owner_id,
        department=section_code,
        extra={"section_revision": section.revision},
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


@quote_write
def request_section_na(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    _ensure_section_review_workflow(quote)
    ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in MUTABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前状态不可申请不适用")
    old_revision = section.revision
    section.status = "na_pending"
    section.revision += 1
    section.submitted_by = user.display_name
    section.submitted_by_id = user.id
    section.submitted_at = now_text()
    section.reviewed_by = ""
    section.reviewed_at = ""
    section.review_comment = payload.reason
    section.updated_at = now_text()
    _add_revision(db, quote, section, user, reason=payload.reason)
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "request_na",
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        reason=payload.reason,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=SECTION_EDIT_NOTIFICATION_EVENTS,
        department=section_code,
    )
    _add_notification(
        db,
        quote,
        title=f"{section.department_name}不适用申请待审核",
        message=(
            f"{quote.quote_no} 的{section.department_name}分段申请不适用，"
            f"请业务审核负责人 {quote.business_owner_name} 审核：{payload.reason}"
        ),
        event="section_na_requested",
        target_user_id=quote.business_owner_id,
        department=section_code,
        reason=payload.reason,
        extra={"section_revision": section.revision},
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


@quote_write
def withdraw_section_submission(
    db: Session,
    quote_id: str,
    section_code: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    _ensure_section_review_workflow(quote)
    ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, revision)
    if section.status not in REVIEWABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="仅待审核分段可返回修改")
    if section.submitted_by_id != user.id:
        raise HTTPException(status_code=403, detail="仅原提交人可在审核前返回修改")

    old_revision = section.revision
    section.status = "draft"
    section.revision += 1
    section.submitted_by = ""
    section.submitted_by_id = ""
    section.submitted_at = ""
    section.reviewed_by = ""
    section.reviewed_at = ""
    section.review_comment = ""
    section.updated_at = now_text()
    _add_revision(db, quote, section, user, reason="withdraw")
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "withdraw",
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        reason="提交人返回修改",
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=SECTION_REVIEW_NOTIFICATION_EVENTS,
        department=section_code,
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


@quote_write
def review_section(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReviewRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    _ensure_section_review_workflow(quote)
    ensure_quote_business_reviewer(db, user, quote)
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in REVIEWABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前状态不在审核中")
    if (
        section.submitted_by_id == user.id
        and not _can_self_review_own_quote(user, quote)
    ):
        raise HTTPException(status_code=403, detail="提交人不能审核自己的分段")

    if section.status == "pending_review" and payload.decision == "approve":
        try:
            calculation = _calculate_and_apply(db, quote, section, user)
        except CalculationInputError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        if calculation.get("status") != "valid" or section.dependency_status != "current":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "分段计算存在阻断警告或依赖已失效，不能审核通过",
                    "warnings": calculation.get("warnings", []),
                },
            )

    review_type = "not_applicable" if section.status == "na_pending" else "section"
    previous_dependency_hashes = (
        _downstream_dependency_hashes(db, quote, section_code)
        if review_type == "not_applicable" and payload.decision == "approve"
        else None
    )
    old_revision = section.revision
    if payload.decision == "approve":
        section.status = "not_applicable" if review_type == "not_applicable" else "approved"
        if review_type == "not_applicable":
            section.calculation_status = "not_applicable"
            section.dependency_status = "current"
    else:
        section.status = "rejected"
    section.revision += 1
    section.reviewed_by = user.display_name
    section.reviewed_at = now_text()
    section.review_comment = payload.reason
    section.updated_at = now_text()
    db.add(
        InternalQuoteReview(
            id=f"IQV-{uuid4().hex}",
            quote_id=quote.id,
            section_id=section.id,
            factory_id=quote.factory_id,
            department=section_code,
            review_type=review_type,
            decision=payload.decision,
            section_revision=old_revision,
            reason=payload.reason,
            actor_id=user.id,
            actor_name=user.display_name,
            created_at=now_text(),
        )
    )
    _add_revision(db, quote, section, user, reason=payload.reason or payload.decision)
    if previous_dependency_hashes is not None:
        _invalidate_downstream_dependencies(
            db,
            quote,
            user,
            section_code,
            request,
            previous_dependency_hashes,
        )
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "approve_na" if review_type == "not_applicable" and payload.decision == "approve" else payload.decision,
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        reason=payload.reason,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=SECTION_REVIEW_NOTIFICATION_EVENTS,
        department=section_code,
    )
    if payload.decision == "reject":
        _add_notification(
            db,
            quote,
            title=f"{section.department_name}分段已退回",
            message=f"{quote.quote_no} 的{section.department_name}分段被退回：{payload.reason}",
            event="section_rejected",
            target_user_id=section.submitted_by_id,
            department=section_code,
            reason=payload.reason,
            extra={"section_revision": section.revision},
        )
    if quote.status == "ready_for_final_review":
        final_release_owner_id, final_release_owner_name = _final_release_owner(db, quote)
        _add_notification(
            db,
            quote,
            title="内部报价已具备跟客放行条件",
            message=(
                f"{quote.quote_no} 所有参与分段均已完成，"
                f"请负责跟客 {final_release_owner_name} 确认最终放行"
            ),
            event="ready_for_final_review",
            target_user_id=final_release_owner_id,
            department="sales",
            extra={"header_revision": quote.header_revision},
        )
    db.commit()
    db.refresh(section)
    return _section_out(section)


@quote_write
def reopen_section(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    _ensure_section_review_workflow(quote)
    ensure_section_permission(db, user, quote.factory_id, section_code, "edit")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in COMPLETED_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="仅已通过或不适用分段可重新打开")
    had_final_release = quote.final_release_status in {"pending", "approved"} or quote.status in {
        "final_reviewing",
        "fully_approved",
        "exported",
    }
    _invalidate_final_release(
        db,
        quote,
        reason=f"{section.department_name}分段已重开：{payload.reason}",
    )
    old_revision = section.revision
    was_not_applicable = section.status == "not_applicable"
    section.status = "draft"
    section.revision += 1
    section.submitted_by = ""
    section.submitted_by_id = ""
    section.submitted_at = ""
    section.reviewed_by = ""
    section.reviewed_at = ""
    section.review_comment = payload.reason
    section.updated_at = now_text()
    if was_not_applicable:
        section.calculation_status = "pending"
        section.dependency_status = "current"
    _add_revision(db, quote, section, user, reason=payload.reason)
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "reopen",
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        reason=payload.reason,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=FINAL_SUBMIT_NOTIFICATION_EVENTS,
    )
    _add_notification(
        db,
        quote,
        title=f"{section.department_name}分段已重开",
        message=f"{quote.quote_no} 的{section.department_name}分段已重开：{payload.reason}",
        event="section_reopened",
        target_permission=f"internal_quote:{section_code}_edit",
        target_department=SECTION_DEPARTMENTS[section_code][0],
        department=section_code,
        reason=payload.reason,
        extra={"section_revision": section.revision},
    )
    if had_final_release:
        _add_notification(
            db,
            quote,
            title="内部报价最终放行已失效",
            message=f"{quote.quote_no} 因{section.department_name}分段重开，需重新完成审批和最终放行",
            event="final_release_invalidated",
            target_user_id=_final_release_owner(db, quote)[0],
            department=section_code,
            reason=payload.reason,
        )
    db.commit()
    db.refresh(section)
    return _section_out(section)


def list_section_revisions(
    db: Session,
    quote_id: str,
    section_code: str,
    user: AuthContext,
) -> list[InternalQuoteRevisionOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    section = _get_section(db, quote_id, section_code)
    revisions = db.scalars(
        select(InternalQuoteSectionRevision)
        .where(InternalQuoteSectionRevision.section_id == section.id)
        .order_by(InternalQuoteSectionRevision.revision.desc())
    ).all()
    return [
        InternalQuoteRevisionOut(
            id=item.id,
            revision=item.revision,
            status=item.status,
            payload=_json_object(item.payload_json),
            calculation=_json_object(item.calculation_json),
            formula_version=item.formula_version,
            input_hash=item.input_hash,
            reference_snapshot_id=item.reference_snapshot_id,
            dependency_hash=item.dependency_hash,
            warnings=_json_list(item.warnings_json),
            reason=item.reason,
            created_by=item.created_by,
            created_by_name=item.created_by_name,
            created_at=item.created_at,
        )
        for item in revisions
    ]


def get_quote_summary(db: Session, quote_id: str, user: AuthContext) -> dict[str, object]:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:summary_read",
        quote.factory_id,
        ALL_QUOTE_DEPARTMENTS,
    )
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    participating_sections = [section for section in sections if section.is_required]
    reference = _ensure_reference_set_for_read(db, quote, user)
    counts: dict[str, int] = {}
    for section in participating_sections:
        counts[section.status] = counts.get(section.status, 0) + 1
    cost_context = _cost_context(db, quote)
    rr2_cost_summary = _rr2_cost_summary(
        participating_sections,
        cost_context,
        _json_object(reference.snapshot_json),
        quote.qty,
        factory_id=quote.factory_id,
    )
    if quote.module_version == "v4" and quote.final_release_status == "issued":
        rr2_cost_summary = _json_object(quote.final_submission_manifest_json).get("rr2_cost_summary", rr2_cost_summary)
    section_summaries: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    formula_mismatches = quote_formula_mismatches(quote, participating_sections)
    if formula_mismatches:
        warnings.append(
            {
                "section_code": "",
                "code": "formula_version_stale",
                "message": "该报价使用旧版公式，请按当前公式重算后再审核或导出",
                "severity": "blocking",
                "mismatches": formula_mismatches,
            }
        )
    for section in participating_sections:
        calculation = _json_object(section.calculation_json)
        calculation_warnings = calculation.get("warnings", [])
        if isinstance(calculation_warnings, list):
            warnings.extend(
                {"section_code": section.department, **item}
                for item in calculation_warnings
                if isinstance(item, dict)
            )
        if section.calculation_status in {"blocked", "stale"}:
            warnings.append(
                {
                    "section_code": section.department,
                    "code": f"calculation_{section.calculation_status}",
                    "message": f"{section.department_name}计算状态为 {section.calculation_status}",
                    "severity": "blocking",
                }
            )
        section_summaries.append(
            {
                "section_code": section.department,
                "section_name": section.department_name,
                "section_status": section.status,
                "revision": section.revision,
                "calculation_status": section.calculation_status,
                "dependency_status": section.dependency_status,
                "total_hkd": decimal_text(
                    total_from_calculation(calculation)
                    if section.calculation_status == "valid"
                    else Decimal("0")
                ),
                "is_draft_amount": section.status not in COMPLETED_SECTION_STATUSES,
            }
        )
    db.commit()
    return {
        "quote_id": quote.id,
        "status": quote.status,
        "formula_version": quote.formula_version,
        "current_formula_version": FORMULA_VERSION,
        "reference_snapshot_id": reference.id,
        "reference_snapshot_sha256": reference.sha256,
        "required_sections": len(participating_sections),
        "completed_sections": sum(
            1 for section in participating_sections if section.status in COMPLETED_SECTION_STATUSES
        ),
        "status_counts": counts,
        "calculation_phase": "blocked" if any(item.get("severity") == "blocking" for item in warnings) else "calculated",
        "components_hkd": {
            key: decimal_text(value)
            for key, value in cost_context.items()
            if key.endswith("_hkd") and key != "factory_price_hkd"
        },
        "factory_price_hkd": decimal_text(cost_context["factory_price_hkd"]),
        "mold_amortization_usd": decimal_text(cost_context["mold_amortization_usd"]),
        "rr2_cost_summary": rr2_cost_summary,
        "sections": section_summaries,
        "warnings": warnings,
    }


def get_quote_reference_set(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> InternalQuoteReferenceSetOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    reference = _ensure_reference_set_for_read(db, quote, user)
    db.commit()
    return _reference_out(reference)


def _replace_quote_reference_set(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    *,
    source_type: str,
    snapshot: dict[str, object] | None,
    reason: str,
    audit_action: str,
    change_description: str,
    audit_detail: str = "",
    request: Request | None = None,
) -> InternalQuoteOut:
    had_final_release = quote.final_release_status in {"pending", "approved"} or quote.status in {
        "final_reviewing",
        "fully_approved",
        "exported",
    }
    _invalidate_final_release(db, quote, reason=f"{change_description}：{reason}")
    old_header_revision = quote.header_revision
    reference = _create_reference_set(
        db,
        quote,
        user,
        source_type=source_type,
        snapshot=snapshot,
    )
    quote.header_revision += 1
    quote.updated_at = now_text()

    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    for section_code in SECTION_CODE_ORDER:
        section = by_code.get(section_code)
        if section is None or not section.is_required:
            continue
        section.calculation_reference_snapshot_id = reference.id
        section.calculation_formula_version = FORMULA_VERSION
        if section.status == "not_applicable" or not _json_object(section.payload_json):
            section.calculation_status = "pending" if section.status != "not_applicable" else "not_applicable"
            section.dependency_status = "current"
            continue
        old_revision = section.revision
        if section.status in REVIEWABLE_SECTION_STATUSES:
            _mark_quote_notifications_handled(
                db,
                quote,
                events=SECTION_REVIEW_NOTIFICATION_EVENTS,
                department=section.department,
            )
        section.revision += 1
        try:
            _calculate_and_apply(db, quote, section, user)
        except CalculationInputError as error:
            failure = {
                "section_code": section.department,
                "formula_version": FORMULA_VERSION,
                "input_hash": content_hash(_json_object(section.payload_json)),
                "reference_snapshot_id": reference.id,
                "line_breakdown": [],
                "currency_totals": {"HKD": "0.0000", "RMB": "0.0000", "USD": "0.0000"},
                "totals": {},
                "warnings": [
                    {"code": "invalid_input", "message": str(error), "severity": "blocking"}
                ],
                "dependencies": {},
                "dependency_hash": content_hash({}),
                "status": "blocked",
            }
            failure["calculation_hash"] = content_hash(failure)
            section.calculation_json = canonical_json(failure)
            section.calculation_status = "blocked"
            section.calculation_hash = str(failure["calculation_hash"])
            section.calculated_at = now_text()
            section.dependency_hash = str(failure["dependency_hash"])
            section.dependency_status = "current"
        if section.status in {"approved", "pending_review", "na_pending"}:
            section.status = "rejected"
            section.review_comment = f"{change_description}，请重新核价并提交"
        else:
            section.status = "draft"
        section.updated_at = now_text()
        _add_revision(db, quote, section, user, reason=reason)
        _add_audit(
            db,
            quote,
            user,
            "reference_recalculated",
            department=section.department,
            old_revision=old_revision,
            new_revision=section.revision,
            reason=reason,
            request=request,
        )
        _add_notification(
            db,
            quote,
            title=f"{section.department_name}参考数据已更新",
            message=f"{quote.quote_no} {change_description}，请重新核价并提交{section.department_name}分段",
            event="reference_snapshot_updated",
            target_permission=f"internal_quote:{section.department}_edit",
            target_department=SECTION_DEPARTMENTS[section.department][0],
            department=section.department,
            reason=reason,
            extra={"section_revision": section.revision, "reference_snapshot_id": reference.id},
        )

    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        audit_action,
        old_revision=old_header_revision,
        new_revision=quote.header_revision,
        reason=reason,
        detail=f"{reference.id} | {audit_detail}" if audit_detail else reference.id,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=FINAL_SUBMIT_NOTIFICATION_EVENTS,
    )
    if had_final_release:
        _add_notification(
            db,
            quote,
            title="内部报价最终放行已失效",
            message=f"{quote.quote_no} 因参考快照更新需重新完成分段审批和最终放行",
            event="final_release_invalidated",
            target_user_id=_final_release_owner(db, quote)[0],
            department="sales",
            reason=reason,
        )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


@quote_write
def sync_quote_reference_set(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReferenceSyncRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:reference_manage",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    return _replace_quote_reference_set(
        db,
        quote,
        user,
        source_type="manual_sync",
        snapshot=None,
        reason=payload.reason,
        audit_action="reference_sync",
        change_description="参考数据快照已同步",
        request=request,
    )


@quote_write
def recalculate_quote_formula(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReferenceSyncRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:reference_manage",
        quote.factory_id,
        ("sales-business", "engineering"),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    current_reference = _ensure_reference_set(db, quote, user)
    return _replace_quote_reference_set(
        db,
        quote,
        user,
        source_type="formula_recalculate",
        snapshot=_json_object(current_reference.snapshot_json),
        reason=payload.reason,
        audit_action="formula_recalculate",
        change_description="报价已按当前公式重算",
        audit_detail=f"{quote.formula_version}->{FORMULA_VERSION}",
        request=request,
    )


@quote_write
def update_quote_reference_fx(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReferenceFxUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_section_permission(db, user, quote.factory_id, "sales", "edit")
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")

    current_reference = _ensure_reference_set(db, quote, user)
    snapshot = _json_object(current_reference.snapshot_json)
    existing_fx = snapshot.get("fx", {})
    fx = dict(existing_fx) if isinstance(existing_fx, dict) else {}
    old_rmb_hkd = decimal_value(fx.get("rmb_hkd"), "RMB→HKD 汇率")
    old_hkd_usd = decimal_value(fx.get("hkd_usd"), "HKD→USD 汇率")
    new_rmb_hkd = decimal_value(payload.rmb_hkd, "RMB→HKD 汇率")
    new_hkd_usd = decimal_value(payload.hkd_usd, "HKD→USD 汇率")
    if old_rmb_hkd == new_rmb_hkd and old_hkd_usd == new_hkd_usd:
        return quote_to_out(db, quote)

    fx["rmb_hkd"] = payload.rmb_hkd
    fx["hkd_usd"] = payload.hkd_usd
    snapshot["fx"] = fx
    reason = (
        f"报价汇率调整：RMB→HKD {format(old_rmb_hkd, 'f')}→{payload.rmb_hkd}；"
        f"HKD→USD {format(old_hkd_usd, 'f')}→{payload.hkd_usd}"
    )
    return _replace_quote_reference_set(
        db,
        quote,
        user,
        source_type="manual_fx",
        snapshot=snapshot,
        reason=reason,
        audit_action="reference_fx_update",
        change_description="参考汇率已调整",
        audit_detail=(
            f"rmb_hkd={payload.rmb_hkd};hkd_usd={payload.hkd_usd};"
            f"previous_reference={current_reference.id}"
        ),
        request=request,
    )


@quote_write
def update_quote_reference_materials(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReferenceMaterialsUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    # Sales and engineering are the two cross-department quotation owners.
    # Production departments keep their existing section-only edit boundary.
    ensure_section_permission(db, user, quote.factory_id, "sales", "edit")
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")

    current_reference = _ensure_reference_set(db, quote, user)
    snapshot = _json_object(current_reference.snapshot_json)
    old_material_prices = snapshot.get("material_prices", {})
    normalized_material_prices = {
        f"{row.material}|{row.grade}": row.price_hkd_lb
        for row in payload.material_prices
    }
    if old_material_prices == normalized_material_prices:
        return quote_to_out(db, quote)

    snapshot["material_prices"] = normalized_material_prices
    reason = (
        f"本报价专用料价已更新："
        f"{len(old_material_prices) if isinstance(old_material_prices, dict) else 0} 项→"
        f"{len(normalized_material_prices)} 项"
    )
    return _replace_quote_reference_set(
        db,
        quote,
        user,
        source_type="manual_materials",
        snapshot=snapshot,
        reason=reason,
        audit_action="reference_materials_update",
        change_description="本报价专用料价已调整",
        audit_detail=(
            f"material_count={len(normalized_material_prices)};"
            f"previous_reference={current_reference.id}"
        ),
        request=request,
    )


def get_quote_timeline(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> InternalQuoteTimelineOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:timeline_read",
        quote.factory_id,
        ALL_QUOTE_DEPARTMENTS,
    )
    rows = db.scalars(
        select(InternalQuoteAuditLog)
        .where(InternalQuoteAuditLog.quote_id == quote.id)
        .order_by(InternalQuoteAuditLog.created_at.desc(), InternalQuoteAuditLog.id.desc())
    ).all()

    def convert(item: InternalQuoteAuditLog) -> InternalQuoteAuditOut:
        return InternalQuoteAuditOut(
            id=item.id,
            department=item.department,
            actor_id=item.actor_id,
            actor_name=item.actor_name,
            action=item.action,
            detail=item.detail,
            old_revision=item.old_revision,
            new_revision=item.new_revision,
            reason=item.reason,
            created_at=item.created_at,
        )

    return InternalQuoteTimelineOut(
        business_events=[convert(item) for item in rows if item.action != "view"],
        view_records=[convert(item) for item in rows if item.action == "view"],
    )


@quote_write
def archive_quote(
    db: Session,
    quote_id: str,
    payload: InternalQuoteArchiveRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:archive",
        quote.factory_id,
        ("sales-business",),
    )
    selected_quote = quote
    batch_quotes = get_quote_batch_rows(db, quote)
    for item in batch_quotes:
        _ensure_active(item)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    timestamp = now_text()
    for item in batch_quotes:
        old_revision = item.header_revision
        item.status = "archived"
        item.header_revision += 1
        item.archived_by = user.id
        item.archived_at = timestamp
        item.archive_reason = payload.reason
        item.updated_at = timestamp
        _add_audit(
            db,
            item,
            user,
            "archive",
            department="sales",
            old_revision=old_revision,
            new_revision=item.header_revision,
            reason=payload.reason,
            detail=json.dumps(
                {"batch_id": item.batch_id or item.id, "batch_size": len(batch_quotes)},
                ensure_ascii=False,
                sort_keys=True,
            ),
            request=request,
        )
        _mark_quote_notifications_handled(
            db,
            item,
            events=ACTIONABLE_INTERNAL_QUOTE_NOTIFICATION_EVENTS,
        )
    db.commit()
    db.refresh(selected_quote)
    return quote_to_out(db, selected_quote)


@quote_write
def delete_quote(
    db: Session,
    quote_id: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> None:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)

    is_creator = quote.created_by == user.id
    is_sales_supervisor = has_permission_in_scope(
        user,
        "internal_quote:archive",
        quote.factory_id,
        "sales-business",
    )
    if not is_creator and not is_sales_supervisor:
        raise HTTPException(status_code=403, detail="仅建单人或本厂区业务主管可删除内部报价")

    _check_revision(quote.header_revision, revision, "报价头")
    batch_quotes = get_quote_batch_rows(db, quote)
    quote_ids = [item.id for item in batch_quotes]
    if db.scalar(select(InternalQuoteAlternative.quote_id).where(InternalQuoteAlternative.quote_id.in_(quote_ids))):
        raise HTTPException(409, "已有方案版本记录的报价不可删除，请在方案面板归档")
    has_export = db.scalar(
        select(func.count(InternalQuoteExportFile.id)).where(
            InternalQuoteExportFile.quote_id.in_(quote_ids)
        )
    )
    has_handoff = db.scalar(
        select(func.count(InternalQuoteArtifactHandoff.id)).where(
            InternalQuoteArtifactHandoff.quote_id.in_(quote_ids)
        )
    )
    if (
        any(item.status in {"released", "fully_approved", "exported"} for item in batch_quotes)
        or any(item.final_release_status == "approved" for item in batch_quotes)
        or bool(has_export)
        or bool(has_handoff)
    ):
        raise HTTPException(
            status_code=409,
            detail="已放行、已导出或已进入报客价交接的报价不能删除，请使用归档保留审计记录",
        )

    add_auth_audit(
        db,
        "internal_quote_deleted",
        username=user.username,
        user_id=user.id,
        detail=(
            f"删除内部报价批次：{quote.factory_id}/{quote.batch_quote_no or quote.quote_no}/{quote.version_label}，"
            f"产品数={len(batch_quotes)}，建单人={quote.created_by_name or quote.created_by}，revision={quote.header_revision}"
        ),
        request=request,
    )
    for item in batch_quotes:
        _mark_quote_notifications_handled(
            db,
            item,
            events=ACTIONABLE_INTERNAL_QUOTE_NOTIFICATION_EVENTS,
        )

    # Explicitly remove children so SQLite test/local databases remain correct
    # even when foreign-key cascade enforcement is not enabled on a connection.
    for model in (
        InternalQuoteArtifactHandoff,
        InternalQuoteExportFile,
        InternalQuoteFinalReview,
        InternalQuoteAttachment,
        InternalQuoteImportBatch,
        InternalQuoteReview,
        InternalQuoteSectionRevision,
        InternalQuoteAuditLog,
        InternalQuoteSection,
        InternalQuoteReferenceSet,
    ):
        db.execute(delete(model).where(model.quote_id.in_(quote_ids)))
    db.execute(delete(InternalQuote).where(InternalQuote.id.in_(quote_ids)))
    db.commit()
