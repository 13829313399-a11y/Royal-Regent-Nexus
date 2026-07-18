import json
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.auth import AuthUser, AuthUserRole, SystemNotification
from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteArtifactHandoff,
    InternalQuoteAuditLog,
    InternalQuoteExportFile,
    InternalQuoteReferenceSet,
    InternalQuoteReview,
    InternalQuoteSection,
    InternalQuoteSectionRevision,
)
from app.schemas.internal_quote import (
    MANDATORY_SECTION_CODES,
    InternalQuoteArchiveRequest,
    InternalQuoteAuditOut,
    InternalQuoteBusinessOwnerOut,
    InternalQuoteCloneRequest,
    InternalQuoteCreateRequest,
    InternalQuoteHeaderUpdateRequest,
    InternalQuoteOut,
    InternalQuoteParticipationUpdateRequest,
    InternalQuoteReasonRequest,
    InternalQuoteReferenceFxUpdateRequest,
    InternalQuoteReferenceSetOut,
    InternalQuoteReferenceSyncRequest,
    InternalQuoteRevisionOut,
    InternalQuoteReviewRequest,
    InternalQuoteSectionOut,
    InternalQuoteSectionSaveRequest,
    InternalQuoteTimelineOut,
)
from app.services.auth import (
    AuthContext,
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
    total_from_calculation,
)


SECTION_DEFINITIONS = (
    ("sales", "业务部", ("sales-business",)),
    ("engineering", "工程部", ("engineering",)),
    ("electronic", "电子部", ("electronic",)),
    ("molding", "啤机部", ("production", "molding")),
    ("painting", "喷油部", ("painting",)),
    ("slush", "搪胶部", ("slush",)),
    ("sewing", "车缝部", ("sewing",)),
    ("assembly", "装配部", ("assembly",)),
)
SECTION_NAMES = {code: name for code, name, _ in SECTION_DEFINITIONS}
SECTION_DEPARTMENTS = {code: departments for code, _, departments in SECTION_DEFINITIONS}
ALL_QUOTE_DEPARTMENTS = tuple(
    dict.fromkeys(department for _, _, departments in SECTION_DEFINITIONS for department in departments)
)
MUTABLE_SECTION_STATUSES = {"draft", "rejected"}
REVIEWABLE_SECTION_STATUSES = {"pending_review", "na_pending"}
COMPLETED_SECTION_STATUSES = {"approved", "not_applicable"}
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
FINAL_REVIEW_NOTIFICATION_EVENTS = {"final_release_submitted"}
ARTIFACT_NOTIFICATION_EVENTS = {"customer_price_artifact_available"}
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


def _section_out(section: InternalQuoteSection) -> InternalQuoteSectionOut:
    return InternalQuoteSectionOut(
        id=section.id,
        department=section.department,
        department_name=section.department_name,
        status=section.status,
        payload=_json_object(section.payload_json),
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
) -> InternalQuoteOut:
    sections: list[InternalQuoteSectionOut] = []
    if include_sections:
        rows = db.scalars(
            select(InternalQuoteSection)
            .where(InternalQuoteSection.quote_id == quote.id)
            .order_by(InternalQuoteSection.id)
        ).all()
        by_code = {section.department: section for section in rows}
        sections = [_section_out(by_code[code]) for code in SECTION_NAMES if code in by_code]

    return InternalQuoteOut(
        id=quote.id,
        factory_id=quote.factory_id,
        workshop_code=quote.workshop_code,
        workshop_name=quote.workshop_name,
        quote_no=quote.quote_no,
        product_name=quote.product_name,
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
        archived_by=quote.archived_by,
        archived_at=quote.archived_at,
        archive_reason=quote.archive_reason,
        final_release_status=quote.final_release_status,
        final_submission_revision=quote.final_submission_revision,
        final_submission_manifest=_json_object(quote.final_submission_manifest_json),
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
    payload: dict[str, object] = {
        "module": "internal-quote-desk",
        "event": event,
        "quote_id": quote.id,
        "quote_no": quote.quote_no,
        "version_label": quote.version_label,
        "customer": quote.customer,
        "department": department,
        "reason": reason,
        "route": f"/modules/sales-business/internal-quote-desk/{quote.id}",
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


def _cost_context(db: Session, quote: InternalQuote) -> dict[str, Decimal]:
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}

    def value(section_code: str, key: str = "total_hkd") -> Decimal:
        section = by_code.get(section_code)
        if section is None or not section.is_required or section.calculation_status != "valid":
            return Decimal("0")
        return decimal_value(_section_totals(section).get(key), f"{section_code}.{key}")

    sales_payload = _json_object(by_code["sales"].payload_json) if "sales" in by_code else {}
    sales_has_cartons = bool(sales_payload.get("cartons"))
    sales_has_packaging_materials = bool(sales_payload.get("packaging_materials"))
    indonesia_freight = decimal_value(sales_payload.get("indonesia_freight_hkd"), "印尼运费")
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
        "carton_hkd": value("sales", "carton_hkd") if sales_has_cartons else value("engineering", "carton_hkd"),
        "mold_amortization_usd": value("engineering", "mold_amortization_usd"),
    }
    components["factory_price_hkd"] = sum(
        (value for key, value in components.items() if key not in {"mold_amortization_usd"}),
        Decimal("0"),
    )
    return components


def _calculation_dependencies(
    db: Session,
    quote: InternalQuote,
    section_code: str,
) -> dict[str, object]:
    sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == quote.id)
    ).all()
    by_code = {section.department: section for section in sections}
    if section_code in {"molding", "painting", "assembly"}:
        engineering = by_code.get("engineering")
        if engineering is None:
            return {}
        return {
            "engineering_revision": engineering.revision,
            "engineering_input_hash": str(
                _json_object(engineering.calculation_json).get("input_hash", "")
            ),
        }
    if section_code == "sales":
        return {
            code: {
                "revision": section.revision,
                "calculation_hash": section.calculation_hash,
                "calculation_status": section.calculation_status,
            }
            for code, section in by_code.items()
            if code != "sales" and section.is_required
        }
    return {}


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
    factory_price_hkd = cost_context["factory_price_hkd"]
    if section.department == "sales" and section_payload.get("cartons"):
        factory_price_hkd -= cost_context["carton_hkd"]
    if section.department == "sales" and section_payload.get("packaging_materials"):
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
) -> None:
    dependents = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department.in_(("molding", "painting", "assembly")),
        )
    ).all()
    for section in dependents:
        if not section.is_required:
            continue
        if section.status == "not_applicable":
            continue
        if not _json_object(section.payload_json) and section.status == "draft":
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
        section.review_comment = "工程分段已更新，请同步依赖并重新核价"
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
            reason="工程分段 revision/hash 已变化",
            request=request,
        )


def _invalidate_sales_dependency(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    source_section_code: str,
    request: Request | None,
) -> None:
    if source_section_code == "sales":
        return
    sales = db.scalar(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.department == "sales",
        )
    )
    if (
        sales is None
        or sales.status == "not_applicable"
        or not _json_object(sales.payload_json)
    ):
        return
    if sales.calculation_status == "stale" and sales.dependency_status == "stale":
        return
    old_revision = sales.revision
    if sales.status in REVIEWABLE_SECTION_STATUSES:
        _mark_quote_notifications_handled(
            db,
            quote,
            events=SECTION_REVIEW_NOTIFICATION_EVENTS,
            department="sales",
        )
    sales.revision += 1
    sales.calculation_status = "stale"
    sales.dependency_status = "stale"
    sales.status = "rejected" if sales.status in {"approved", "pending_review"} else "draft"
    sales.review_comment = f"{SECTION_NAMES[source_section_code]}成本已更新，请重新汇总"
    sales.updated_at = now_text()
    _add_revision(db, quote, sales, user, reason=f"{source_section_code}_dependency_invalidated")
    _add_audit(
        db,
        quote,
        user,
        "dependency_invalidated",
        department="sales",
        old_revision=old_revision,
        new_revision=sales.revision,
        reason=f"{SECTION_NAMES[source_section_code]} calculation/revision 已变化",
        request=request,
    )


def _invalidate_downstream_dependencies(
    db: Session,
    quote: InternalQuote,
    user: AuthContext,
    source_section_code: str,
    request: Request | None,
) -> None:
    if source_section_code == "engineering":
        _invalidate_engineering_dependents(db, quote, user, request)
    _invalidate_sales_dependency(db, quote, user, source_section_code, request)


def _derive_quote_status(db: Session, quote: InternalQuote) -> None:
    if quote.status == "archived":
        return
    sections = db.scalars(
        select(InternalQuoteSection).where(
            InternalQuoteSection.quote_id == quote.id,
            InternalQuoteSection.is_required.is_(True),
        )
    ).all()
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
    timestamp = now_text()
    quote = InternalQuote(
        id=f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:10].upper()}",
        factory_id=payload.factory_id,
        workshop_code=payload.workshop_code,
        workshop_name=payload.workshop_name,
        quote_no=payload.quote_no,
        product_name=payload.product_name,
        customer=payload.customer,
        qty=payload.qty,
        version_label=payload.version_label,
        status="drafting",
        initiator_department=payload.initiator_department,
        business_owner_id=payload.business_owner_id,
        business_owner_name=payload.business_owner_name,
        target_customer_price=payload.target_customer_price,
        target_date=payload.target_date,
        remark=payload.remark,
        module_version="v2",
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
    db.add(quote)
    try:
        db.flush()
        _create_reference_set(db, quote, user, source_type="create")
        participating_sections = set(payload.participating_sections)
        _create_sections(db, quote, user, participating_sections)
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
                },
                ensure_ascii=False,
            ),
            new_revision=1,
            request=request,
        )
        for section_code, section_name, departments in SECTION_DEFINITIONS:
            if section_code not in participating_sections:
                continue
            _add_notification(
                db,
                quote,
                title=f"新内部报价待{section_name}协作",
                message=f"{quote.quote_no} / {quote.product_name} 已建单，请进入{section_name}分段处理",
                event="quote_created",
                target_permission=f"internal_quote:{section_code}_edit",
                target_department=departments[0],
                department=section_code,
            )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="报价编号与版本已存在") from None
    db.refresh(quote)
    return quote_to_out(db, quote)


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
    statement = select(InternalQuote).where(InternalQuote.factory_id == factory_id)
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
    return [
        quote_to_out(db, quote, include_sections=include_sections)
        for quote in db.scalars(statement).all()
    ]


def _has_business_owner_binding(
    db: Session,
    user: AuthUser,
    factory_id: str,
) -> bool:
    context = build_auth_context(db, user)
    return can(
        context,
        "internal_quote:sales_edit",
        factory_id,
        "sales-business",
    ) and any(
        grant.factory_id in {factory_id, "*"}
        and grant.department in {"sales-business", "*"}
        and "internal_quote:sales_edit" in grant.permissions
        for grant in context.grants
    )


def list_business_owners(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> list[InternalQuoteBusinessOwnerOut]:
    ensure_quote_read(db, user, factory_id)
    users = db.scalars(
        select(AuthUser)
        .join(AuthUserRole, AuthUserRole.user_id == AuthUser.id)
        .where(
            AuthUser.status == "active",
            AuthUserRole.factory_id.in_((factory_id, "*")),
            AuthUserRole.department.in_(("sales-business", "*")),
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
        if _has_business_owner_binding(db, item, factory_id)
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
    _check_revision(quote.header_revision, payload.revision, "报价头")
    old_revision = quote.header_revision
    for field, value in payload.model_dump(exclude={"revision"}, exclude_none=True).items():
        setattr(quote, field, value)
    quote.header_revision += 1
    quote.updated_at = now_text()
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
            target_user_id=quote.business_owner_id,
            department="sales",
        )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


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
    source_sections = db.scalars(
        select(InternalQuoteSection).where(InternalQuoteSection.quote_id == source.id)
    ).all()
    payloads = {section.department: section.payload_json for section in source_sections}
    timestamp = now_text()
    target = InternalQuote(
        id=f"IQ-{datetime.now().strftime('%Y%m%d')}-{uuid4().hex[:10].upper()}",
        factory_id=source.factory_id,
        workshop_code=source.workshop_code,
        workshop_name=source.workshop_name,
        quote_no=payload.quote_no,
        product_name=source.product_name,
        customer=source.customer,
        qty=source.qty,
        version_label=payload.version_label,
        status="drafting",
        initiator_department=initiator_department,
        business_owner_id=payload.business_owner_id,
        business_owner_name=payload.business_owner_name,
        target_customer_price=(
            source.target_customer_price
            if payload.target_customer_price is None
            else payload.target_customer_price
        ),
        target_date=payload.target_date,
        remark=source.remark if payload.remark is None else payload.remark,
        module_version="v2",
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
    old_revision = section.revision
    section.payload_json = json.dumps(payload.payload, ensure_ascii=False, sort_keys=True)
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
    _add_revision(db, quote, section, user, reason=payload.reason)
    _invalidate_downstream_dependencies(db, quote, user, section_code, request)
    _derive_quote_status(db, quote)
    _add_audit(
        db,
        quote,
        user,
        "save",
        department=section_code,
        old_revision=old_revision,
        new_revision=section.revision,
        reason=payload.reason,
        request=request,
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


def submit_section(
    db: Session,
    quote_id: str,
    section_code: str,
    revision: int,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
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
    _invalidate_downstream_dependencies(db, quote, user, section_code, request)
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
        message=f"{quote.quote_no} 的{section.department_name}分段已提交，请主管审核",
        event="section_submitted",
        target_permission=f"internal_quote:{section_code}_review",
        target_department=SECTION_DEPARTMENTS[section_code][0],
        department=section_code,
        extra={"section_revision": section.revision},
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


def request_section_na(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
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
    _invalidate_downstream_dependencies(db, quote, user, section_code, request)
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
        message=f"{quote.quote_no} 的{section.department_name}分段申请不适用：{payload.reason}",
        event="section_na_requested",
        target_permission=f"internal_quote:{section_code}_review",
        target_department=SECTION_DEPARTMENTS[section_code][0],
        department=section_code,
        reason=payload.reason,
        extra={"section_revision": section.revision},
    )
    db.commit()
    db.refresh(section)
    return _section_out(section)


def review_section(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReviewRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
    ensure_section_permission(db, user, quote.factory_id, section_code, "review")
    _ensure_active(quote)
    section = _get_section(db, quote_id, section_code)
    _ensure_section_participates(section)
    _check_revision(section.revision, payload.revision)
    if section.status not in REVIEWABLE_SECTION_STATUSES:
        raise HTTPException(status_code=409, detail="当前状态不在审核中")
    if section.submitted_by_id == user.id:
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

    old_revision = section.revision
    review_type = "not_applicable" if section.status == "na_pending" else "section"
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
    _invalidate_downstream_dependencies(db, quote, user, section_code, request)
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
        _add_notification(
            db,
            quote,
            title="内部报价已具备最终提交条件",
            message=f"{quote.quote_no} 所有参与分段均已完成，请提交最终业务放行",
            event="ready_for_final_review",
            target_user_id=quote.business_owner_id,
            department="sales",
            extra={"header_revision": quote.header_revision},
        )
    db.commit()
    db.refresh(section)
    return _section_out(section)


def reopen_section(
    db: Session,
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteSectionOut:
    quote = _get_quote(db, quote_id)
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
    _invalidate_downstream_dependencies(db, quote, user, section_code, request)
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
            target_user_id=quote.business_owner_id,
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
    section_summaries: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
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
    for section_code in (
        "engineering",
        "electronic",
        "molding",
        "painting",
        "slush",
        "sewing",
        "assembly",
        "sales",
    ):
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
            target_user_id=quote.business_owner_id,
            department="sales",
            reason=reason,
        )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)


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


def update_quote_reference_fx(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReferenceFxUpdateRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:sales_edit",
        quote.factory_id,
        ("sales-business",),
    )
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
        f"业务汇率调整：RMB→HKD {format(old_rmb_hkd, 'f')}→{payload.rmb_hkd}；"
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
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    old_revision = quote.header_revision
    quote.status = "archived"
    quote.header_revision += 1
    quote.archived_by = user.id
    quote.archived_at = now_text()
    quote.archive_reason = payload.reason
    quote.updated_at = now_text()
    _add_audit(
        db,
        quote,
        user,
        "archive",
        department="sales",
        old_revision=old_revision,
        new_revision=quote.header_revision,
        reason=payload.reason,
        request=request,
    )
    _mark_quote_notifications_handled(
        db,
        quote,
        events=ACTIONABLE_INTERNAL_QUOTE_NOTIFICATION_EVENTS,
    )
    db.commit()
    db.refresh(quote)
    return quote_to_out(db, quote)
