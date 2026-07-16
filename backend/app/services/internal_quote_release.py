from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.internal_quote import (
    InternalQuote,
    InternalQuoteArtifactHandoff,
    InternalQuoteExportFile,
    InternalQuoteFinalReview,
    InternalQuoteSection,
)
from app.schemas.internal_quote import (
    InternalQuoteArtifactConsumeRequest,
    InternalQuoteArtifactHandoffOut,
    InternalQuoteFieldChangeOut,
    InternalQuoteFinalReleaseOut,
    InternalQuoteFinalReviewOut,
    InternalQuoteFinalReviewRequest,
    InternalQuoteRevisionRequest,
    InternalQuoteSectionComparisonOut,
    InternalQuoteVersionCandidateOut,
    InternalQuoteVersionComparisonOut,
)
from app.services.auth import AuthContext, now_text
from app.services.internal_quote import (
    ALL_QUOTE_DEPARTMENTS,
    COMPLETED_SECTION_STATUSES,
    SECTION_NAMES,
    _add_audit,
    _add_notification,
    _check_revision,
    _cost_context,
    _ensure_active,
    _get_quote,
    _json_object,
    ensure_quote_permission,
    ensure_quote_read,
    quote_to_out,
)
from app.services.internal_quote_artifacts import create_controlled_export
from app.services.internal_quote_calculator import (
    canonical_json,
    content_hash,
    decimal_text,
    total_from_calculation,
)


FINAL_EXPORT_STAGES = {"fully_approved", "exported"}


def _quote_sections(db: Session, quote_id: str) -> list[InternalQuoteSection]:
    return db.scalars(
        select(InternalQuoteSection)
        .where(InternalQuoteSection.quote_id == quote_id)
        .order_by(InternalQuoteSection.id)
    ).all()


def _release_manifest(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> dict[str, Any]:
    required = [section for section in sections if section.is_required]
    incomplete = [
        section.department
        for section in required
        if section.status not in COMPLETED_SECTION_STATUSES
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
                "message": "八个必需分段全部通过且计算有效后才能提交最终放行",
                "incomplete_sections": incomplete,
                "invalid_calculations": invalid,
            },
        )
    manifest: dict[str, Any] = {
        "schema_version": "internal-quote-final-release-v1",
        "quote_id": quote.id,
        "factory_id": quote.factory_id,
        "workshop_code": quote.workshop_code,
        "quote_no": quote.quote_no,
        "version_label": quote.version_label,
        "product_name": quote.product_name,
        "customer": quote.customer,
        "qty": quote.qty,
        "business_owner_id": quote.business_owner_id,
        "header_revision": quote.header_revision,
        "formula_version": quote.formula_version,
        "reference_snapshot_id": quote.reference_snapshot_id,
        "section_revisions": {section.department: section.revision for section in sections},
        "section_statuses": {section.department: section.status for section in sections},
        "section_calculation_hashes": {
            section.department: section.calculation_hash for section in sections
        },
    }
    manifest["manifest_sha256"] = content_hash(manifest)
    return manifest


def _review_out(record: InternalQuoteFinalReview) -> InternalQuoteFinalReviewOut:
    return InternalQuoteFinalReviewOut(
        id=record.id,
        quote_id=record.quote_id,
        submission_revision=record.submission_revision,
        decision=record.decision,
        header_revision=record.header_revision,
        section_revisions={
            str(key): int(value)
            for key, value in _json_object(record.section_revisions_json).items()
        },
        release_manifest=_json_object(record.release_manifest_json),
        release_manifest_sha256=record.release_manifest_sha256,
        submitted_by=record.submitted_by,
        submitted_by_name=record.submitted_by_name,
        submitted_at=record.submitted_at,
        actor_id=record.actor_id,
        actor_name=record.actor_name,
        reason=record.reason,
        created_at=record.created_at,
    )


def submit_final_release(
    db: Session,
    quote_id: str,
    payload: InternalQuoteRevisionRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteFinalReleaseOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:final_submit",
        quote.factory_id,
        ("sales-business",),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    if quote.status != "ready_for_final_review":
        raise HTTPException(status_code=409, detail="当前报价尚未达到最终提交条件")

    sections = _quote_sections(db, quote.id)
    quote.header_revision += 1
    manifest = _release_manifest(quote, sections)
    timestamp = now_text()
    quote.status = "final_reviewing"
    quote.final_release_status = "pending"
    quote.final_submission_revision += 1
    quote.final_submission_manifest_json = canonical_json(manifest)
    quote.final_submitted_by = user.id
    quote.final_submitted_by_name = user.display_name
    quote.final_submitted_at = timestamp
    quote.final_reviewed_by = ""
    quote.final_reviewed_by_name = ""
    quote.final_reviewed_at = ""
    quote.final_review_comment = ""
    quote.final_release_invalidated_at = ""
    quote.final_release_invalidation_reason = ""
    quote.updated_at = timestamp
    _add_audit(
        db,
        quote,
        user,
        "final_submit",
        department="sales",
        old_revision=payload.revision,
        new_revision=quote.header_revision,
        detail=json.dumps(
            {
                "submission_revision": quote.final_submission_revision,
                "manifest_sha256": manifest["manifest_sha256"],
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    _add_notification(
        db,
        quote,
        title="内部报价待最终业务放行",
        message=f"{quote.quote_no} 已由 {user.display_name} 提交，请另一名业务主管复核",
        event="final_release_submitted",
        target_permission="internal_quote:final_approve",
        target_department="sales-business",
        department="sales",
        extra={
            "submission_revision": quote.final_submission_revision,
            "header_revision": quote.header_revision,
            "manifest_sha256": manifest["manifest_sha256"],
        },
    )
    db.commit()
    db.refresh(quote)
    return InternalQuoteFinalReleaseOut(quote=quote_to_out(db, quote))


def review_final_release(
    db: Session,
    quote_id: str,
    payload: InternalQuoteFinalReviewRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteFinalReleaseOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:final_approve",
        quote.factory_id,
        ("sales-business",),
    )
    _ensure_active(quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    if quote.status != "final_reviewing" or quote.final_release_status != "pending":
        raise HTTPException(status_code=409, detail="当前报价不在最终放行审核中")
    if quote.final_submitted_by == user.id:
        raise HTTPException(status_code=403, detail="最终提交人不能审核自己的报价")

    sections = _quote_sections(db, quote.id)
    live_manifest = _release_manifest(quote, sections)
    submitted_manifest = _json_object(quote.final_submission_manifest_json)
    if live_manifest.get("manifest_sha256") != submitted_manifest.get("manifest_sha256"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": "最终提交后报价 revision 或计算快照已变化，请重新提交",
                "submitted_manifest_sha256": submitted_manifest.get("manifest_sha256", ""),
                "current_manifest_sha256": live_manifest.get("manifest_sha256", ""),
            },
        )

    timestamp = now_text()
    old_header_revision = quote.header_revision
    quote.header_revision += 1
    quote.final_reviewed_by = user.id
    quote.final_reviewed_by_name = user.display_name
    quote.final_reviewed_at = timestamp
    quote.final_review_comment = payload.reason
    quote.updated_at = timestamp
    if payload.decision == "approve":
        quote.status = "fully_approved"
        quote.final_release_status = "approved"
        quote.final_release_revision += 1
    else:
        quote.status = "ready_for_final_review"
        quote.final_release_status = "rejected"

    review = InternalQuoteFinalReview(
        id=f"IQFINAL-{uuid4().hex}",
        quote_id=quote.id,
        factory_id=quote.factory_id,
        submission_revision=quote.final_submission_revision,
        decision=payload.decision,
        header_revision=old_header_revision,
        section_revisions_json=canonical_json(submitted_manifest.get("section_revisions", {})),
        release_manifest_json=canonical_json(submitted_manifest),
        release_manifest_sha256=str(submitted_manifest.get("manifest_sha256", "")),
        submitted_by=quote.final_submitted_by,
        submitted_by_name=quote.final_submitted_by_name,
        submitted_at=quote.final_submitted_at,
        actor_id=user.id,
        actor_name=user.display_name,
        reason=payload.reason,
        created_at=timestamp,
    )
    db.add(review)
    _add_audit(
        db,
        quote,
        user,
        "final_approve" if payload.decision == "approve" else "final_reject",
        department="sales",
        old_revision=old_header_revision,
        new_revision=quote.header_revision,
        reason=payload.reason,
        detail=json.dumps(
            {
                "submission_revision": quote.final_submission_revision,
                "release_revision": quote.final_release_revision,
                "manifest_sha256": submitted_manifest.get("manifest_sha256", ""),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )

    if payload.decision == "reject":
        _add_notification(
            db,
            quote,
            title="内部报价最终放行已退回",
            message=f"{quote.quote_no} 最终放行被退回：{payload.reason}",
            event="final_release_rejected",
            target_user_id=quote.final_submitted_by,
            department="sales",
            reason=payload.reason,
            extra={"submission_revision": quote.final_submission_revision},
        )
        db.commit()
        db.refresh(quote)
        db.refresh(review)
        return InternalQuoteFinalReleaseOut(
            quote=quote_to_out(db, quote),
            review=_review_out(review),
        )

    _add_notification(
        db,
        quote,
        title="内部报价最终放行完成",
        message=f"{quote.quote_no} 已由 {user.display_name} 最终放行，受控文件可导出并交接客价转换台",
        event="final_release_approved",
        target_user_id=quote.final_submitted_by,
        department="sales",
        extra={"release_revision": quote.final_release_revision},
    )
    _add_notification(
        db,
        quote,
        title="内部报价 artifact 可导入",
        message=f"{quote.quote_no} / {quote.customer} 已最终放行，可在客价转换台导入",
        event="customer_price_artifact_available",
        target_permission="customer_price:import_internal_quote",
        target_department="sales-business",
        department="sales",
        extra={"release_revision": quote.final_release_revision},
    )
    export = create_controlled_export(db, quote.id, user, request)
    db.refresh(quote)
    db.refresh(review)
    return InternalQuoteFinalReleaseOut(
        quote=quote_to_out(db, quote),
        review=_review_out(review),
        export=export,
    )


def list_final_reviews(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteFinalReviewOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    records = db.scalars(
        select(InternalQuoteFinalReview)
        .where(InternalQuoteFinalReview.quote_id == quote.id)
        .order_by(
            InternalQuoteFinalReview.submission_revision.desc(),
            InternalQuoteFinalReview.created_at.desc(),
        )
    ).all()
    return [_review_out(record) for record in records]


def _candidate(quote: InternalQuote) -> InternalQuoteVersionCandidateOut:
    return InternalQuoteVersionCandidateOut(
        id=quote.id,
        quote_no=quote.quote_no,
        version_label=quote.version_label,
        product_name=quote.product_name,
        customer=quote.customer,
        status=quote.status,
        final_release_status=quote.final_release_status,
        final_release_revision=quote.final_release_revision,
        updated_at=quote.updated_at,
    )


def _root_quote_id(db: Session, quote: InternalQuote) -> str:
    current = quote
    seen = {quote.id}
    while current.cloned_from_quote_id and current.cloned_from_quote_id not in seen:
        parent = db.get(InternalQuote, current.cloned_from_quote_id)
        if parent is None:
            break
        seen.add(parent.id)
        current = parent
    return current.id


def _versions_related(db: Session, left: InternalQuote, right: InternalQuote) -> bool:
    if left.factory_id != right.factory_id or left.workshop_code != right.workshop_code:
        return False
    return left.quote_no == right.quote_no or _root_quote_id(db, left) == _root_quote_id(db, right)


def list_version_candidates(
    db: Session,
    quote_id: str,
    user: AuthContext,
) -> list[InternalQuoteVersionCandidateOut]:
    quote = _get_quote(db, quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:summary_read",
        quote.factory_id,
        ALL_QUOTE_DEPARTMENTS,
    )
    rows = db.scalars(
        select(InternalQuote)
        .where(
            InternalQuote.factory_id == quote.factory_id,
            InternalQuote.workshop_code == quote.workshop_code,
            InternalQuote.id != quote.id,
        )
        .order_by(InternalQuote.updated_at.desc(), InternalQuote.id.desc())
    ).all()
    return [_candidate(item) for item in rows if _versions_related(db, quote, item)]


def _changes(before: Any, after: Any, path: str = "", *, limit: int = 500) -> list[InternalQuoteFieldChangeOut]:
    if before == after:
        return []
    if isinstance(before, dict) and isinstance(after, dict):
        output: list[InternalQuoteFieldChangeOut] = []
        for key in sorted(set(before) | set(after), key=str):
            child_path = f"{path}.{key}" if path else str(key)
            output.extend(_changes(before.get(key), after.get(key), child_path, limit=limit - len(output)))
            if len(output) >= limit:
                break
        return output
    return [InternalQuoteFieldChangeOut(path=path or "$", before=before, after=after)]


def _section_total(section: InternalQuoteSection | None) -> Decimal:
    if section is None or section.calculation_status != "valid":
        return Decimal("0")
    return total_from_calculation(_json_object(section.calculation_json))


def compare_quote_versions(
    db: Session,
    target_quote_id: str,
    base_quote_id: str,
    user: AuthContext,
) -> InternalQuoteVersionComparisonOut:
    target = _get_quote(db, target_quote_id)
    base = _get_quote(db, base_quote_id)
    ensure_quote_permission(
        db,
        user,
        "internal_quote:summary_read",
        target.factory_id,
        ALL_QUOTE_DEPARTMENTS,
    )
    ensure_quote_read(db, user, base.factory_id)
    if not _versions_related(db, target, base):
        raise HTTPException(status_code=400, detail="仅可比较同一报价号或复制版本链中的内部报价")

    header_fields = (
        "quote_no",
        "version_label",
        "product_name",
        "customer",
        "qty",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
        "formula_version",
        "reference_snapshot_id",
        "final_release_status",
        "final_release_revision",
    )
    header_changes = [
        InternalQuoteFieldChangeOut(path=field, before=getattr(base, field), after=getattr(target, field))
        for field in header_fields
        if getattr(base, field) != getattr(target, field)
    ]
    base_sections = {section.department: section for section in _quote_sections(db, base.id)}
    target_sections = {section.department: section for section in _quote_sections(db, target.id)}
    section_comparisons: list[InternalQuoteSectionComparisonOut] = []
    total_before = _cost_context(db, base)["factory_price_hkd"]
    total_after = _cost_context(db, target)["factory_price_hkd"]
    for section_code in SECTION_NAMES:
        before_section = base_sections.get(section_code)
        after_section = target_sections.get(section_code)
        before_total = _section_total(before_section)
        after_total = _section_total(after_section)
        section_comparisons.append(
            InternalQuoteSectionComparisonOut(
                section_code=section_code,
                section_name=SECTION_NAMES[section_code],
                before_status=before_section.status if before_section else "missing",
                after_status=after_section.status if after_section else "missing",
                before_revision=before_section.revision if before_section else 0,
                after_revision=after_section.revision if after_section else 0,
                before_total_hkd=decimal_text(before_total),
                after_total_hkd=decimal_text(after_total),
                delta_hkd=decimal_text(after_total - before_total),
                payload_changes=_changes(
                    _json_object(before_section.payload_json) if before_section else {},
                    _json_object(after_section.payload_json) if after_section else {},
                ),
            )
        )
    return InternalQuoteVersionComparisonOut(
        base=_candidate(base),
        target=_candidate(target),
        header_changes=header_changes,
        sections=section_comparisons,
        total_before_hkd=decimal_text(total_before),
        total_after_hkd=decimal_text(total_after),
        total_delta_hkd=decimal_text(total_after - total_before),
    )


def _refresh_handoff(
    db: Session,
    handoff: InternalQuoteArtifactHandoff,
) -> tuple[InternalQuote, InternalQuoteExportFile]:
    quote = _get_quote(db, handoff.quote_id)
    export = db.get(InternalQuoteExportFile, handoff.export_id)
    is_current = (
        export is not None
        and export.status == "current"
        and export.release_stage == "p4_final_approved"
        and quote.status in FINAL_EXPORT_STAGES
        and quote.final_release_status == "approved"
        and quote.final_release_revision == handoff.release_revision
    )
    if not is_current and handoff.status != "revoked":
        handoff.status = "revoked"
        handoff.revoked_at = now_text()
        handoff.revoke_reason = "最终放行 artifact 已失效或被后续版本取代"
    if export is None:
        raise HTTPException(status_code=404, detail="内部报价 artifact 文件不存在")
    return quote, export


def _handoff_out(
    handoff: InternalQuoteArtifactHandoff,
    export: InternalQuoteExportFile,
) -> InternalQuoteArtifactHandoffOut:
    return InternalQuoteArtifactHandoffOut(
        id=handoff.id,
        quote_id=handoff.quote_id,
        export_id=handoff.export_id,
        factory_id=handoff.factory_id,
        customer=handoff.customer,
        quote_no=handoff.quote_no,
        version_label=handoff.version_label,
        release_revision=handoff.release_revision,
        status=handoff.status,
        artifact_manifest=_json_object(handoff.artifact_manifest_json),
        file_name=export.file_name,
        content_type=export.content_type,
        size_bytes=export.size_bytes,
        sha256=export.sha256,
        created_by=handoff.created_by,
        created_by_name=handoff.created_by_name,
        created_at=handoff.created_at,
        consumed_by=handoff.consumed_by,
        consumed_by_name=handoff.consumed_by_name,
        consumed_at=handoff.consumed_at,
        consumer_reference=handoff.consumer_reference,
        revoked_at=handoff.revoked_at,
        revoke_reason=handoff.revoke_reason,
    )


def list_customer_price_artifacts(
    db: Session,
    factory_id: str,
    user: AuthContext,
    *,
    status: str = "available",
    customer: str = "",
    keyword: str = "",
) -> list[InternalQuoteArtifactHandoffOut]:
    ensure_quote_permission(
        db,
        user,
        "customer_price:import_internal_quote",
        factory_id,
        ("sales-business",),
    )
    statement = select(InternalQuoteArtifactHandoff).where(
        InternalQuoteArtifactHandoff.factory_id == factory_id
    )
    if status:
        statement = statement.where(InternalQuoteArtifactHandoff.status == status)
    if customer.strip():
        statement = statement.where(InternalQuoteArtifactHandoff.customer == customer.strip())
    if keyword.strip():
        token = f"%{keyword.strip()}%"
        statement = statement.where(
            or_(
                InternalQuoteArtifactHandoff.quote_no.like(token),
                InternalQuoteArtifactHandoff.customer.like(token),
                InternalQuoteArtifactHandoff.version_label.like(token),
            )
        )
    records = db.scalars(
        statement.order_by(
            InternalQuoteArtifactHandoff.created_at.desc(),
            InternalQuoteArtifactHandoff.id.desc(),
        )
    ).all()
    output: list[InternalQuoteArtifactHandoffOut] = []
    for handoff in records:
        _, export = _refresh_handoff(db, handoff)
        if status and handoff.status != status:
            continue
        output.append(_handoff_out(handoff, export))
    db.commit()
    return output


def consume_customer_price_artifact(
    db: Session,
    handoff_id: str,
    payload: InternalQuoteArtifactConsumeRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteArtifactHandoffOut:
    handoff = db.get(InternalQuoteArtifactHandoff, handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="内部报价 artifact 不存在")
    ensure_quote_permission(
        db,
        user,
        "customer_price:import_internal_quote",
        handoff.factory_id,
        ("sales-business",),
    )
    quote, export = _refresh_handoff(db, handoff)
    if handoff.status == "revoked":
        db.commit()
        raise HTTPException(status_code=409, detail="内部报价 artifact 已失效，不能导入")
    if handoff.status == "consumed":
        raise HTTPException(status_code=409, detail="内部报价 artifact 已被客价转换台导入")
    handoff.status = "consumed"
    handoff.consumed_by = user.id
    handoff.consumed_by_name = user.display_name
    handoff.consumed_at = now_text()
    handoff.consumer_reference = payload.consumer_reference
    _add_audit(
        db,
        quote,
        user,
        "handoff_consume",
        department="sales",
        detail=json.dumps(
            {
                "handoff_id": handoff.id,
                "export_id": export.id,
                "consumer_reference": payload.consumer_reference,
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    db.refresh(handoff)
    return _handoff_out(handoff, export)


def get_customer_price_artifact_download(
    db: Session,
    handoff_id: str,
    user: AuthContext,
    request: Request | None = None,
) -> tuple[InternalQuoteArtifactHandoff, InternalQuoteExportFile]:
    handoff = db.get(InternalQuoteArtifactHandoff, handoff_id)
    if handoff is None:
        raise HTTPException(status_code=404, detail="内部报价 artifact 不存在")
    ensure_quote_permission(
        db,
        user,
        "customer_price:import_internal_quote",
        handoff.factory_id,
        ("sales-business",),
    )
    quote, export = _refresh_handoff(db, handoff)
    if handoff.status == "revoked":
        db.commit()
        raise HTTPException(status_code=409, detail="内部报价 artifact 已失效，不能下载")
    _add_audit(
        db,
        quote,
        user,
        "handoff_download",
        department="sales",
        detail=json.dumps(
            {"handoff_id": handoff.id, "export_id": export.id, "sha256": export.sha256},
            ensure_ascii=False,
            sort_keys=True,
        ),
        request=request,
    )
    db.commit()
    return handoff, export
