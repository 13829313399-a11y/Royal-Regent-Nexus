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
    InternalQuoteReasonRequest,
    InternalQuoteRevisionRequest,
    InternalQuoteSectionComparisonOut,
    InternalQuoteVersionCandidateOut,
    InternalQuoteVersionComparisonOut,
)
from app.services.auth import AuthContext, can, now_text
from app.services.internal_quote import (
    quote_write,
    ALL_QUOTE_DEPARTMENTS,
    ARTIFACT_NOTIFICATION_EVENTS,
    COMPLETED_SECTION_STATUSES,
    FINAL_REVIEW_NOTIFICATION_EVENTS,
    FINAL_SUBMIT_NOTIFICATION_EVENTS,
    SECTION_NAMES,
    _add_audit,
    _add_notification,
    _add_revision,
    _check_revision,
    _cost_context,
    _ensure_active,
    _get_quote,
    _json_object,
    _mark_quote_notifications_handled,
    ensure_quote_formula_current,
    ensure_quote_business_reviewer,
    ensure_quote_permission,
    ensure_quote_read,
    get_quote_batch_rows,
    is_whole_quote_review,
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


def _responsible_followup_id(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> str:
    sales = next(
        (section for section in sections if section.department == "sales"),
        None,
    )
    # The Sales section submitter is the person actually following this quote.
    # Historical fixtures/records may predate submitted_by_id, so fall back to
    # the quote creator without weakening the final-submit permission check.
    return (sales.submitted_by_id if sales else "") or quote.created_by


def _ensure_responsible_followup(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
    user: AuthContext,
) -> None:
    if _responsible_followup_id(quote, sections) != user.id:
        raise HTTPException(
            status_code=403,
            detail="仅负责本单的业务跟客（业务部分段提交人）可确认最终放行",
        )


def _release_manifest(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> dict[str, Any]:
    ensure_quote_formula_current(quote, sections)
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
                "message": "全部参与分段通过且计算有效后才能提交最终放行",
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
        "target_customer_price": quote.target_customer_price,
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


def _whole_review_required_sections(
    sections: list[InternalQuoteSection],
) -> list[InternalQuoteSection]:
    return [section for section in sections if section.is_required]


def _validate_whole_review_submission(
    sections: list[InternalQuoteSection],
) -> list[InternalQuoteSection]:
    required = _whole_review_required_sections(sections)
    incomplete = [
        section.department
        for section in required
        if not section.filled_at or not _json_object(section.payload_json)
    ]
    invalid = [
        section.department
        for section in required
        if section.calculation_status != "valid" or section.dependency_status != "current"
    ]
    locked = [
        section.department
        for section in required
        if section.status not in {"draft", "rejected"}
    ]
    if incomplete or invalid or locked:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "全部参与部门完成填写且计算有效后才能提交整单审核",
                "incomplete_sections": incomplete,
                "invalid_calculations": invalid,
                "locked_sections": locked,
            },
        )
    return required


def _whole_review_manifest(
    quote: InternalQuote,
    sections: list[InternalQuoteSection],
) -> dict[str, Any]:
    ensure_quote_formula_current(quote, sections)
    required = _whole_review_required_sections(sections)
    invalid = [
        section.department
        for section in required
        if section.status != "pending_review"
        or section.calculation_status != "valid"
        or section.dependency_status != "current"
    ]
    if invalid:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "整单审核中的部门状态或计算快照已变化，请退回后重新提交",
                "invalid_sections": invalid,
            },
        )
    manifest: dict[str, Any] = {
        "schema_version": "internal-quote-whole-review-v1",
        "workflow_mode": "whole_quote_review",
        "quote_id": quote.id,
        "factory_id": quote.factory_id,
        "workshop_code": quote.workshop_code,
        "quote_no": quote.quote_no,
        "version_label": quote.version_label,
        "product_name": quote.product_name,
        "customer": quote.customer,
        "qty": quote.qty,
        "target_customer_price": quote.target_customer_price,
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


def _submit_whole_quote_review(
    db: Session,
    quote: InternalQuote,
    payload: InternalQuoteRevisionRequest,
    user: AuthContext,
    request: Request | None,
) -> InternalQuoteFinalReleaseOut:
    ensure_quote_permission(
        db,
        user,
        "internal_quote:final_submit",
        quote.factory_id,
        ("sales-business",),
    )
    selected_quote = quote
    batch_quotes = get_quote_batch_rows(db, quote, for_update=True)
    root_quote = next((item for item in batch_quotes if item.batch_position == 1), batch_quotes[0])
    reviewer_ids = {item.business_owner_id for item in batch_quotes}
    if len(reviewer_ids) != 1:
        raise HTTPException(status_code=409, detail="同批产品的整单审核人不一致，请先统一审核人")
    _ensure_active(selected_quote)
    _check_revision(quote.header_revision, payload.revision, "报价头")
    prepared: list[tuple[InternalQuote, list[InternalQuoteSection], list[InternalQuoteSection]]] = []
    incomplete_products: list[str] = []
    for item in batch_quotes:
        _ensure_active(item)
        if item.status != "ready_for_final_review":
            incomplete_products.append(item.product_name)
            continue
        sections = _quote_sections(db, item.id)
        required = _validate_whole_review_submission(sections)
        prepared.append((item, sections, required))
    if incomplete_products:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "批次内全部产品完成填写后才能一次提交整批审核",
                "incomplete_products": incomplete_products,
            },
        )

    timestamp = now_text()
    manifests: dict[str, dict[str, Any]] = {}
    for item, sections, required in prepared:
        for section in required:
            old_revision = section.revision
            section.status = "pending_review"
            section.revision += 1
            section.submitted_by = user.display_name
            section.submitted_by_id = user.id
            section.submitted_at = timestamp
            section.reviewed_by = ""
            section.reviewed_at = ""
            section.review_comment = ""
            section.updated_at = timestamp
            _add_revision(db, item, section, user, reason="whole_quote_submit")
            _add_audit(
                db,
                item,
                user,
                "whole_review_lock_section",
                department=section.department,
                old_revision=old_revision,
                new_revision=section.revision,
                request=request,
            )

        old_header_revision = item.header_revision
        item.header_revision += 1
        manifest = _whole_review_manifest(item, sections)
        manifests[item.id] = manifest
        item.status = "final_reviewing"
        item.final_release_status = "pending"
        item.final_submission_revision += 1
        item.final_submission_manifest_json = canonical_json(manifest)
        item.final_submitted_by = user.id
        item.final_submitted_by_name = user.display_name
        item.final_submitted_at = timestamp
        item.final_reviewed_by = ""
        item.final_reviewed_by_name = ""
        item.final_reviewed_at = ""
        item.final_review_comment = ""
        item.final_release_invalidated_at = ""
        item.final_release_invalidation_reason = ""
        item.updated_at = timestamp
        _add_audit(
            db,
            item,
            user,
            "whole_review_submit",
            department="",
            old_revision=old_header_revision,
            new_revision=item.header_revision,
            detail=json.dumps(
                {
                    "submission_revision": item.final_submission_revision,
                    "manifest_sha256": manifest["manifest_sha256"],
                    "batch_id": item.batch_id or item.id,
                    "batch_size": len(batch_quotes),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            request=request,
        )
        _mark_quote_notifications_handled(
            db,
            item,
            events=FINAL_SUBMIT_NOTIFICATION_EVENTS,
        )
    _add_notification(
        db,
        root_quote,
        title="内部报价批次待整单审核",
        message=(
            f"{root_quote.batch_quote_no or root_quote.quote_no} 的 {len(batch_quotes)} 款产品已完成填写，"
            f"请 {root_quote.business_owner_name} 一次审核整批"
        ),
        event="whole_quote_submitted",
        target_user_id=root_quote.business_owner_id,
        department="",
        extra={
            "batch_id": root_quote.batch_id or root_quote.id,
            "batch_size": len(batch_quotes),
            "manifest_sha256": manifests[root_quote.id]["manifest_sha256"],
        },
    )
    db.commit()
    db.refresh(selected_quote)
    return InternalQuoteFinalReleaseOut(quote=quote_to_out(db, selected_quote))


def _review_whole_quote(
    db: Session,
    quote: InternalQuote,
    payload: InternalQuoteFinalReviewRequest,
    user: AuthContext,
    request: Request | None,
) -> InternalQuoteFinalReleaseOut:
    selected_quote = quote
    batch_quotes = get_quote_batch_rows(db, quote, for_update=True)
    root_quote = next((item for item in batch_quotes if item.batch_position == 1), batch_quotes[0])
    reviewer_ids = {item.business_owner_id for item in batch_quotes}
    if len(reviewer_ids) != 1:
        raise HTTPException(status_code=409, detail="同批产品的整单审核人不一致，请先统一审核人")
    ensure_quote_business_reviewer(db, user, root_quote)
    # A selected, authorized whole-quote reviewer may also be its submitter.
    # Legacy section self-review remains governed by its separate permission.
    _ensure_active(selected_quote)
    _check_revision(selected_quote.header_revision, payload.revision, "报价头")
    prepared: list[tuple[InternalQuote, list[InternalQuoteSection], dict[str, Any]]] = []
    for item in batch_quotes:
        _ensure_active(item)
        if item.status != "final_reviewing" or item.final_release_status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"产品“{item.product_name}”不在整单审核中，不能处理整批",
            )
        sections = _quote_sections(db, item.id)
        live_manifest = _whole_review_manifest(item, sections)
        submitted_manifest = _json_object(item.final_submission_manifest_json)
        if live_manifest.get("manifest_sha256") != submitted_manifest.get("manifest_sha256"):
            raise HTTPException(
                status_code=409,
                detail={
                    "message": f"产品“{item.product_name}”提交后的 revision 或计算快照已变化，请退回后重新提交",
                    "submitted_manifest_sha256": submitted_manifest.get("manifest_sha256", ""),
                    "current_manifest_sha256": live_manifest.get("manifest_sha256", ""),
                },
            )
        prepared.append((item, sections, submitted_manifest))

    timestamp = now_text()
    section_status = "approved" if payload.decision == "approve" else "rejected"
    selected_review: InternalQuoteFinalReview | None = None
    for item, sections, submitted_manifest in prepared:
        for section in _whole_review_required_sections(sections):
            old_revision = section.revision
            section.status = section_status
            section.revision += 1
            section.reviewed_by = user.display_name
            section.reviewed_at = timestamp
            section.review_comment = payload.reason
            section.updated_at = timestamp
            _add_revision(
                db,
                item,
                section,
                user,
                reason=payload.reason or f"whole_quote_{payload.decision}",
            )
            _add_audit(
                db,
                item,
                user,
                "whole_review_approve_section" if payload.decision == "approve" else "whole_review_reject_section",
                department=section.department,
                old_revision=old_revision,
                new_revision=section.revision,
                reason=payload.reason,
                request=request,
            )

        old_header_revision = item.header_revision
        item.header_revision += 1
        item.final_reviewed_by = user.id
        item.final_reviewed_by_name = user.display_name
        item.final_reviewed_at = timestamp
        item.final_review_comment = payload.reason
        item.updated_at = timestamp
        if payload.decision == "approve":
            item.status = "fully_approved"
            item.final_release_status = "approved"
            item.final_release_revision += 1
        else:
            item.status = "rejected"
            item.final_release_status = "rejected"

        review = InternalQuoteFinalReview(
            id=f"IQFINAL-{uuid4().hex}",
            quote_id=item.id,
            factory_id=item.factory_id,
            submission_revision=item.final_submission_revision,
            decision=payload.decision,
            header_revision=old_header_revision,
            section_revisions_json=canonical_json(submitted_manifest.get("section_revisions", {})),
            release_manifest_json=canonical_json(submitted_manifest),
            release_manifest_sha256=str(submitted_manifest.get("manifest_sha256", "")),
            submitted_by=item.final_submitted_by,
            submitted_by_name=item.final_submitted_by_name,
            submitted_at=item.final_submitted_at,
            actor_id=user.id,
            actor_name=user.display_name,
            reason=payload.reason,
            created_at=timestamp,
        )
        db.add(review)
        if item.id == selected_quote.id:
            selected_review = review
        _add_audit(
            db,
            item,
            user,
            "whole_review_approve" if payload.decision == "approve" else "whole_review_reject",
            department="",
            old_revision=old_header_revision,
            new_revision=item.header_revision,
            reason=payload.reason,
            detail=json.dumps(
                {
                    "submission_revision": item.final_submission_revision,
                    "release_revision": item.final_release_revision,
                    "manifest_sha256": submitted_manifest.get("manifest_sha256", ""),
                    "batch_id": item.batch_id or item.id,
                    "batch_size": len(batch_quotes),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            request=request,
        )
        _mark_quote_notifications_handled(
            db,
            item,
            events=FINAL_REVIEW_NOTIFICATION_EVENTS,
        )
    if payload.decision == "reject":
        _add_notification(
            db,
            root_quote,
            title="内部报价整批审核已退回",
            message=f"{root_quote.batch_quote_no or root_quote.quote_no} 的 {len(batch_quotes)} 款已全部退回并解锁：{payload.reason}",
            event="final_release_rejected",
            target_user_id=root_quote.final_submitted_by,
            department="",
            reason=payload.reason,
            extra={"batch_id": root_quote.batch_id or root_quote.id, "batch_size": len(batch_quotes)},
        )
    else:
        _add_notification(
            db,
            root_quote,
            title="内部报价整批审核通过",
            message=(
                f"{root_quote.batch_quote_no or root_quote.quote_no} 的 {len(batch_quotes)} 款已由 "
                f"{user.display_name} 一次审核通过，可分别生成正式报价输出"
            ),
            event="final_release_approved",
            target_user_id=root_quote.final_submitted_by,
            department="",
            extra={"batch_id": root_quote.batch_id or root_quote.id, "batch_size": len(batch_quotes)},
        )
    db.commit()
    db.refresh(selected_quote)
    if selected_review is None:
        raise RuntimeError("整批审核未生成当前产品的审核记录")
    db.refresh(selected_review)
    return InternalQuoteFinalReleaseOut(
        quote=quote_to_out(db, selected_quote),
        review=_review_out(selected_review),
    )


@quote_write
def withdraw_whole_quote_submission(
    db: Session,
    quote_id: str,
    payload: InternalQuoteReasonRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteFinalReleaseOut:
    quote = _get_quote(db, quote_id)
    ensure_quote_read(db, user, quote.factory_id)
    # The same ordered row locks are used by submit/review, so a concurrent
    # approval cannot be overwritten by the creator's withdrawal.
    batch_quotes = get_quote_batch_rows(db, quote, for_update=True)
    if any(item.created_by != user.id for item in batch_quotes):
        raise HTTPException(status_code=403, detail="只有建单人本人可以在审核前退回修改")
    if not any(can(user, "internal_quote:create", quote.factory_id, department)
               for department in ("sales-business", "engineering")):
        raise HTTPException(status_code=403, detail="当前账号没有该厂区的建单操作权限")
    if not payload.reason.strip():
        raise HTTPException(status_code=422, detail="退回修改必须填写原因")
    _check_revision(quote.header_revision, payload.revision, "报价头")
    for item in batch_quotes:
        _ensure_active(item)
        if not is_whole_quote_review(item) or item.status != "final_reviewing" or item.final_release_status != "pending":
            raise HTTPException(status_code=409, detail="只有待整单审核的报价可以退回修改；审核完成后不能撤回")

    timestamp = now_text()
    for item in batch_quotes:
        for section in _whole_review_required_sections(_quote_sections(db, item.id)):
            old_revision = section.revision
            section.status = "rejected"
            section.revision += 1
            section.submitted_by = ""
            section.submitted_by_id = ""
            section.submitted_at = ""
            section.reviewed_by = ""
            section.reviewed_at = ""
            section.review_comment = ""
            section.updated_at = timestamp
            _add_revision(db, item, section, user, reason=payload.reason)
            _add_audit(
                db, item, user, "whole_review_withdraw_section",
                department=section.department, old_revision=old_revision,
                new_revision=section.revision, reason=payload.reason, request=request,
            )
        old_header_revision = item.header_revision
        item.header_revision += 1
        item.status = "rejected"
        item.final_release_status = "invalidated"
        item.final_release_invalidated_at = timestamp
        item.final_release_invalidation_reason = payload.reason
        item.updated_at = timestamp
        # Keep the submitted manifest and submitter as evidence. Withdrawal is
        # an audit action, never a reviewer rejection or an approval record.
        _add_audit(
            db, item, user, "whole_review_withdraw", department="",
            old_revision=old_header_revision, new_revision=item.header_revision,
            reason=payload.reason,
            detail=canonical_json({
                "submission_revision": item.final_submission_revision,
                "batch_id": item.batch_id or item.id,
                "batch_size": len(batch_quotes),
            }),
            request=request,
        )
        _mark_quote_notifications_handled(db, item, events=FINAL_REVIEW_NOTIFICATION_EVENTS)
    db.commit()
    db.refresh(quote)
    return InternalQuoteFinalReleaseOut(quote=quote_to_out(db, quote))


@quote_write
def submit_final_release(
    db: Session,
    quote_id: str,
    payload: InternalQuoteRevisionRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteFinalReleaseOut:
    quote = _get_quote(db, quote_id)
    if is_whole_quote_review(quote):
        return _submit_whole_quote_review(db, quote, payload, user, request)
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
    _ensure_responsible_followup(quote, sections, user)
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
    _mark_quote_notifications_handled(
        db,
        quote,
        events=FINAL_SUBMIT_NOTIFICATION_EVENTS,
    )
    # Final release is a one-person confirmation by the responsible Sales
    # follow-up. Reuse the immutable review/export path in the same transaction
    # so manifest verification, audit history and controlled artifacts remain
    # identical to an approved legacy pending release.
    return review_final_release(
        db,
        quote.id,
        InternalQuoteFinalReviewRequest(
            revision=quote.header_revision,
            decision="approve",
            reason="负责跟客确认放行",
        ),
        user,
        request,
    )


@quote_write
def review_final_release(
    db: Session,
    quote_id: str,
    payload: InternalQuoteFinalReviewRequest,
    user: AuthContext,
    request: Request | None = None,
) -> InternalQuoteFinalReleaseOut:
    quote = _get_quote(db, quote_id)
    if is_whole_quote_review(quote):
        return _review_whole_quote(db, quote, payload, user, request)
    sections = _quote_sections(db, quote.id)
    if payload.decision == "approve":
        ensure_quote_permission(
            db,
            user,
            "internal_quote:final_submit",
            quote.factory_id,
            ("sales-business",),
        )
        _ensure_responsible_followup(quote, sections, user)
    else:
        # Kept only for returning historical pending releases created before
        # the one-person workflow. New submissions are approved immediately.
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
    _mark_quote_notifications_handled(
        db,
        quote,
        events=FINAL_REVIEW_NOTIFICATION_EVENTS,
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
        "target_customer_price",
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
        _mark_quote_notifications_handled(
            db,
            quote,
            events=ARTIFACT_NOTIFICATION_EVENTS,
            payload_matches={"release_revision": handoff.release_revision},
        )
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
        if (
            handoff.consumed_by == user.id
            and handoff.consumer_reference == payload.consumer_reference
        ):
            return _handoff_out(handoff, export)
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
    _mark_quote_notifications_handled(
        db,
        quote,
        events=ARTIFACT_NOTIFICATION_EVENTS,
        payload_matches={"release_revision": handoff.release_revision},
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
