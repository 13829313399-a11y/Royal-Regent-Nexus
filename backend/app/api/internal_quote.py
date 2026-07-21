from urllib.parse import quote as url_quote
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.internal_quote import (
    InternalQuoteArchiveRequest,
    InternalQuoteArtifactConsumeRequest,
    InternalQuoteArtifactHandoffOut,
    InternalQuoteAttachmentOut,
    InternalQuoteBusinessOwnerOut,
    InternalQuoteCloneRequest,
    InternalQuoteCreateRequest,
    InternalQuoteCustomerCreateRequest,
    InternalQuoteCustomerOut,
    InternalQuoteCustomerUpdateRequest,
    InternalQuoteDashboardOut,
    InternalQuoteHeaderUpdateRequest,
    InternalQuoteExportFileOut,
    InternalQuoteImportConfirmOut,
    InternalQuoteImportConfirmRequest,
    InternalQuoteImportPreviewOut,
    InternalQuoteFinalReleaseOut,
    InternalQuoteFinalReviewOut,
    InternalQuoteFinalReviewRequest,
    InternalQuoteOut,
    InternalQuotePageOut,
    InternalQuoteParticipationRemoveRequest,
    InternalQuoteParticipationUpdateRequest,
    InternalQuotePricingBaselineOut,
    InternalQuotePricingBaselineUpdateRequest,
    InternalQuoteReasonRequest,
    InternalQuoteReferenceFxUpdateRequest,
    InternalQuoteReferenceSetOut,
    InternalQuoteReferenceSyncRequest,
    InternalQuoteRevisionOut,
    InternalQuoteReviewRequest,
    InternalQuoteRevisionRequest,
    InternalQuoteSectionOut,
    InternalQuoteSectionPreviewOut,
    InternalQuoteSectionPreviewRequest,
    InternalQuoteSectionSaveRequest,
    InternalQuoteTimelineOut,
    InternalQuoteVersionCandidateOut,
    InternalQuoteVersionComparisonOut,
)
from app.services.auth import AuthContext, get_current_user
from app.services.internal_quote import (
    add_quote_participation,
    archive_quote,
    clone_quote,
    create_quote,
    ensure_quote_read,
    get_quote_detail,
    get_quote_dashboard,
    get_quote_reference_set,
    get_quote_summary,
    get_quote_timeline,
    list_quotes,
    list_quotes_page,
    list_business_owners,
    list_section_revisions,
    preview_section_cost,
    remove_quote_participation,
    reopen_section,
    request_section_na,
    review_section,
    save_section,
    submit_section,
    sync_quote_reference_set,
    update_quote_reference_fx,
    update_quote_header,
    withdraw_section_submission,
)
from app.services.internal_quote_calculator import FORMULA_VERSION, SECTION_INPUT_CONTRACTS
from app.services.internal_quote_baseline import get_pricing_baseline, update_pricing_baseline
from app.services.internal_quote_customers import (
    create_customer,
    delete_customer,
    list_customers,
    update_customer,
)
from app.services.internal_quote_templates import XLSX_CONTENT_TYPE, build_internal_quote_import_template
from app.services.internal_quote_artifacts import (
    confirm_import_batch,
    create_controlled_export,
    create_import_preview,
    get_attachment_download,
    get_attachment_preview,
    get_export_download,
    list_attachments,
    list_export_files,
    list_import_batches,
    upload_attachment,
)
from app.services.internal_quote_release import (
    compare_quote_versions,
    consume_customer_price_artifact,
    get_customer_price_artifact_download,
    list_customer_price_artifacts,
    list_final_reviews,
    list_version_candidates,
    review_final_release,
    submit_final_release,
)


router = APIRouter(prefix="/api/internal-quotes", tags=["internal-quotes"])
customer_price_artifact_router = APIRouter(
    prefix="/api/customer-price/internal-quote-artifacts",
    tags=["customer-price-internal-quote-artifacts"],
)


@router.get("", response_model=list[InternalQuoteOut] | InternalQuotePageOut)
def get_internal_quotes(
    factory_id: str = Query(min_length=1, max_length=64),
    status_filter: str = Query(default="", alias="status", max_length=32),
    keyword: str = Query(default="", max_length=128),
    customer: str = Query(default="", max_length=128),
    page: int | None = Query(default=None, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    include_sections: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    if page is not None:
        return list_quotes_page(
            db,
            current_user,
            factory_id,
            page=page,
            page_size=page_size,
            status=status_filter,
            keyword=keyword,
            customer=customer,
            include_sections=include_sections,
        )
    return list_quotes(
        db,
        current_user,
        factory_id,
        status=status_filter,
        keyword=keyword,
        include_sections=include_sections,
    )


@router.get("/business-owners", response_model=list[InternalQuoteBusinessOwnerOut])
def get_internal_quote_business_owners(
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_business_owners(db, current_user, factory_id)


@router.get("/customers", response_model=list[InternalQuoteCustomerOut])
def get_internal_quote_customers(
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_customers(db, factory_id, current_user)


@router.post(
    "/customers",
    response_model=InternalQuoteCustomerOut,
    status_code=status.HTTP_201_CREATED,
)
def post_internal_quote_customer(
    payload: InternalQuoteCustomerCreateRequest,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_customer(db, factory_id, payload, current_user, request)


@router.put("/customers/{customer_id}", response_model=InternalQuoteCustomerOut)
def put_internal_quote_customer(
    customer_id: str,
    payload: InternalQuoteCustomerUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_customer(db, customer_id, payload, current_user, request)


@router.delete("/customers/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_internal_quote_customer(
    customer_id: str,
    request: Request,
    revision: int = Query(ge=1),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    delete_customer(db, customer_id, revision, current_user, request)
    return None


@router.get("/dashboard", response_model=InternalQuoteDashboardOut)
def get_internal_quote_dashboard(
    factory_id: str = Query(min_length=1, max_length=64),
    period: Literal["week", "month", "year"] = Query(default="month"),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_quote_dashboard(db, current_user, factory_id, period=period)


@router.post("", response_model=InternalQuoteOut, status_code=status.HTTP_201_CREATED)
def post_internal_quote(
    payload: InternalQuoteCreateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_quote(db, payload, current_user, request)


@router.get("/calculation-contracts", response_model=dict[str, object])
def get_internal_quote_calculation_contracts(
    factory_id: str = Query(min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    ensure_quote_read(db, current_user, factory_id)
    return {"formula_version": FORMULA_VERSION, "sections": SECTION_INPUT_CONTRACTS}


@router.get("/pricing-baseline", response_model=InternalQuotePricingBaselineOut)
def get_internal_quote_pricing_baseline(
    factory_id: str = Query(min_length=1, max_length=64),
    workshop_code: str = Query(default="huaxing-workshop", min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_pricing_baseline(db, factory_id, workshop_code, current_user)


@router.put("/pricing-baseline", response_model=InternalQuotePricingBaselineOut)
def put_internal_quote_pricing_baseline(
    payload: InternalQuotePricingBaselineUpdateRequest,
    request: Request,
    factory_id: str = Query(min_length=1, max_length=64),
    workshop_code: str = Query(default="huaxing-workshop", min_length=1, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_pricing_baseline(
        db,
        factory_id,
        workshop_code,
        payload,
        current_user,
        request,
    )


@router.get("/{quote_id}", response_model=InternalQuoteOut)
def get_internal_quote(
    quote_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_quote_detail(db, quote_id, current_user, request)


@router.patch("/{quote_id}", response_model=InternalQuoteOut)
def patch_internal_quote(
    quote_id: str,
    payload: InternalQuoteHeaderUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_quote_header(db, quote_id, payload, current_user, request)


@router.post("/{quote_id}/participation", response_model=InternalQuoteOut)
def post_internal_quote_participation(
    quote_id: str,
    payload: InternalQuoteParticipationUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return add_quote_participation(db, quote_id, payload, current_user, request)


@router.post("/{quote_id}/participation/remove", response_model=InternalQuoteOut)
def post_internal_quote_participation_remove(
    quote_id: str,
    payload: InternalQuoteParticipationRemoveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return remove_quote_participation(db, quote_id, payload, current_user, request)


@router.get("/{quote_id}/reference-snapshot", response_model=InternalQuoteReferenceSetOut)
def get_internal_quote_reference_snapshot(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_quote_reference_set(db, quote_id, current_user)


@router.post("/{quote_id}/reference-snapshot/sync", response_model=InternalQuoteOut)
def post_internal_quote_reference_snapshot_sync(
    quote_id: str,
    payload: InternalQuoteReferenceSyncRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return sync_quote_reference_set(db, quote_id, payload, current_user, request)


@router.put("/{quote_id}/reference-snapshot/fx", response_model=InternalQuoteOut)
def put_internal_quote_reference_snapshot_fx(
    quote_id: str,
    payload: InternalQuoteReferenceFxUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_quote_reference_fx(db, quote_id, payload, current_user, request)


@router.post("/{quote_id}/clone", response_model=InternalQuoteOut, status_code=status.HTTP_201_CREATED)
def post_internal_quote_clone(
    quote_id: str,
    payload: InternalQuoteCloneRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return clone_quote(db, quote_id, payload, current_user, request)


@router.post("/{quote_id}/archive", response_model=InternalQuoteOut)
def post_internal_quote_archive(
    quote_id: str,
    payload: InternalQuoteArchiveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return archive_quote(db, quote_id, payload, current_user, request)


@router.put("/{quote_id}/sections/{section_code}", response_model=InternalQuoteSectionOut)
def put_internal_quote_section(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteSectionSaveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return save_section(db, quote_id, section_code, payload, current_user, request)


@router.post(
    "/{quote_id}/sections/{section_code}/preview",
    response_model=InternalQuoteSectionPreviewOut,
)
def post_internal_quote_section_preview(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteSectionPreviewRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return preview_section_cost(db, quote_id, section_code, payload, current_user)


@router.post("/{quote_id}/sections/{section_code}/submit", response_model=InternalQuoteSectionOut)
def post_internal_quote_section_submit(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteRevisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return submit_section(db, quote_id, section_code, payload.revision, current_user, request)


@router.post("/{quote_id}/sections/{section_code}/withdraw", response_model=InternalQuoteSectionOut)
def post_internal_quote_section_withdraw(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteRevisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return withdraw_section_submission(
        db,
        quote_id,
        section_code,
        payload.revision,
        current_user,
        request,
    )


@router.post("/{quote_id}/sections/{section_code}/review", response_model=InternalQuoteSectionOut)
def post_internal_quote_section_review(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return review_section(db, quote_id, section_code, payload, current_user, request)


@router.post("/{quote_id}/sections/{section_code}/request-na", response_model=InternalQuoteSectionOut)
def post_internal_quote_section_request_na(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return request_section_na(db, quote_id, section_code, payload, current_user, request)


@router.post("/{quote_id}/sections/{section_code}/reopen", response_model=InternalQuoteSectionOut)
def post_internal_quote_section_reopen(
    quote_id: str,
    section_code: str,
    payload: InternalQuoteReasonRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return reopen_section(db, quote_id, section_code, payload, current_user, request)


@router.get(
    "/{quote_id}/sections/{section_code}/revisions",
    response_model=list[InternalQuoteRevisionOut],
)
def get_internal_quote_section_revisions(
    quote_id: str,
    section_code: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_section_revisions(db, quote_id, section_code, current_user)


@router.get("/{quote_id}/summary", response_model=dict[str, object])
def get_internal_quote_summary_route(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_quote_summary(db, quote_id, current_user)


@router.post("/{quote_id}/final-submit", response_model=InternalQuoteFinalReleaseOut)
def post_internal_quote_final_submit(
    quote_id: str,
    payload: InternalQuoteRevisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return submit_final_release(db, quote_id, payload, current_user, request)


@router.post("/{quote_id}/final-review", response_model=InternalQuoteFinalReleaseOut)
def post_internal_quote_final_review(
    quote_id: str,
    payload: InternalQuoteFinalReviewRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return review_final_release(db, quote_id, payload, current_user, request)


@router.get("/{quote_id}/final-reviews", response_model=list[InternalQuoteFinalReviewOut])
def get_internal_quote_final_reviews(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_final_reviews(db, quote_id, current_user)


@router.get(
    "/{quote_id}/version-candidates",
    response_model=list[InternalQuoteVersionCandidateOut],
)
def get_internal_quote_version_candidates(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_version_candidates(db, quote_id, current_user)


@router.get(
    "/{quote_id}/compare/{base_quote_id}",
    response_model=InternalQuoteVersionComparisonOut,
)
def get_internal_quote_version_comparison(
    quote_id: str,
    base_quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return compare_quote_versions(db, quote_id, base_quote_id, current_user)


@router.get("/{quote_id}/timeline", response_model=InternalQuoteTimelineOut)
def get_internal_quote_timeline_route(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return get_quote_timeline(db, quote_id, current_user)


@router.post(
    "/{quote_id}/imports/{import_type}/preview",
    response_model=InternalQuoteImportPreviewOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_quote_import_preview(
    quote_id: str,
    import_type: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    content = await file.read()
    return create_import_preview(
        db,
        quote_id,
        import_type,
        file.filename or "",
        content,
        current_user,
        request,
    )


@router.get("/{quote_id}/imports/{import_type}/template")
def get_internal_quote_import_template(
    quote_id: str,
    import_type: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    get_quote_detail(db, quote_id, current_user)
    try:
        content, file_name = build_internal_quote_import_template(import_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return Response(
        content=content,
        media_type=XLSX_CONTENT_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(file_name)}",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post(
    "/{quote_id}/imports/{batch_id}/confirm",
    response_model=InternalQuoteImportConfirmOut,
)
def post_internal_quote_import_confirm(
    quote_id: str,
    batch_id: str,
    payload: InternalQuoteImportConfirmRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return confirm_import_batch(db, quote_id, batch_id, payload, current_user, request)


@router.get("/{quote_id}/imports", response_model=list[InternalQuoteImportPreviewOut])
def get_internal_quote_imports(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_import_batches(db, quote_id, current_user)


@router.post(
    "/{quote_id}/attachments",
    response_model=InternalQuoteAttachmentOut,
    status_code=status.HTTP_201_CREATED,
)
async def post_internal_quote_attachment(
    quote_id: str,
    request: Request,
    department: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    content = await file.read()
    return upload_attachment(
        db,
        quote_id,
        department,
        file.filename or "",
        content,
        current_user,
        request,
    )


@router.get("/{quote_id}/attachments", response_model=list[InternalQuoteAttachmentOut])
def get_internal_quote_attachments(
    quote_id: str,
    department: str = Query(default="", max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_attachments(db, quote_id, department, current_user)


@router.get("/{quote_id}/attachments/{attachment_id}/download")
def get_internal_quote_attachment_download(
    quote_id: str,
    attachment_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    attachment = get_attachment_download(
        db,
        quote_id,
        attachment_id,
        current_user,
        request,
    )
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(attachment.file_name)}",
            "X-Content-SHA256": attachment.sha256,
        },
    )


@router.get("/{quote_id}/attachments/{attachment_id}/preview")
def get_internal_quote_attachment_preview(
    quote_id: str,
    attachment_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    attachment = get_attachment_preview(db, quote_id, attachment_id, current_user)
    return Response(
        content=attachment.content,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f"inline; filename*=UTF-8''{url_quote(attachment.file_name)}",
            "Cache-Control": "private, max-age=3600",
            "X-Content-SHA256": attachment.sha256,
        },
    )


@router.post(
    "/{quote_id}/exports",
    response_model=InternalQuoteExportFileOut,
    status_code=status.HTTP_201_CREATED,
)
def post_internal_quote_export(
    quote_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return create_controlled_export(db, quote_id, current_user, request)


@router.get("/{quote_id}/exports", response_model=list[InternalQuoteExportFileOut])
def get_internal_quote_exports(
    quote_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_export_files(db, quote_id, current_user)


@router.get("/{quote_id}/exports/{export_id}/download")
def get_internal_quote_export_download(
    quote_id: str,
    export_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    record = get_export_download(db, quote_id, export_id, current_user, request)
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(record.file_name)}",
            "X-Content-SHA256": record.sha256,
            "X-Internal-Quote-Export-Status": record.status,
        },
    )


@customer_price_artifact_router.get("", response_model=list[InternalQuoteArtifactHandoffOut])
def get_customer_price_internal_quote_artifacts(
    factory_id: str = Query(min_length=1, max_length=64),
    status_filter: str = Query(default="available", alias="status", max_length=32),
    customer: str = Query(default="", max_length=128),
    keyword: str = Query(default="", max_length=128),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_customer_price_artifacts(
        db,
        factory_id,
        current_user,
        status=status_filter,
        customer=customer,
        keyword=keyword,
    )


@customer_price_artifact_router.post(
    "/{handoff_id}/consume",
    response_model=InternalQuoteArtifactHandoffOut,
)
def post_customer_price_internal_quote_artifact_consume(
    handoff_id: str,
    payload: InternalQuoteArtifactConsumeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return consume_customer_price_artifact(
        db,
        handoff_id,
        payload,
        current_user,
        request,
    )


@customer_price_artifact_router.get("/{handoff_id}/download")
def get_customer_price_internal_quote_artifact_download(
    handoff_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _, record = get_customer_price_artifact_download(
        db,
        handoff_id,
        current_user,
        request,
    )
    return Response(
        content=record.content,
        media_type=record.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{url_quote(record.file_name)}",
            "X-Content-SHA256": record.sha256,
            "X-Internal-Quote-Release-Stage": record.release_stage,
        },
    )
