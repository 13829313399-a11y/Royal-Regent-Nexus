from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.api.ai_artifacts import (
    ArtifactScannerDependency,
    ArtifactStorageDependency,
    _require_artifacts,
)
from app.core.config import settings
from app.db import get_db
from app.schemas.document_studio import (
    DocumentJobCancelRequest,
    DocumentJobCapabilities,
    DocumentJobCreate,
    DocumentJobDetail,
    DocumentJobEventPage,
    DocumentJobList,
    DocumentJobOperationalMetrics,
    DocumentJobResult,
    DocumentJobRetryRequest,
    DocumentJobReviewRequest,
    DocumentPreflightRequest,
    DocumentPreflightResult,
    DocumentSnapshot,
)
from app.services.ai.artifacts.service import ArtifactError
from app.services.ai.pilot_guard import AIPilotGuardError, build_pilot_guard
from app.services.ai.task_service import AITaskNotFoundError, get_owned_task
from app.services.auth import AuthContext, add_auth_audit, get_current_user
from app.services.document_studio.orchestrator import (
    DocumentJobError,
    DocumentJobNotFoundError,
    cancel_document_job,
    create_document_job,
    document_job_events,
    document_job_operational_metrics,
    document_job_result,
    document_job_snapshot,
    get_document_job,
    list_document_jobs,
    office_renderer_available,
    preflight_owned_document,
    retry_document_job,
    review_document_job,
    task_runtime_available,
)
from app.services.document_studio.providers.qwen_document import (
    get_document_provider_status,
)
from app.services.document_studio.routing import available_document_job_types
from app.services.document_translation import document_translation_status

router = APIRouter(prefix="/api/tools/document-jobs", tags=["document-jobs"])
document_job_guard = build_pilot_guard()

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _error(error: DocumentJobError | ArtifactError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.public_message,
            "retryable": error.retryable,
        },
    )


def _audit(
    db: Session,
    *,
    user: AuthContext,
    request: Request,
    operation: str,
    task_id: str = "",
) -> None:
    detail = f"operation={operation}"
    if task_id:
        detail += f" task_id={task_id}"
    add_auth_audit(
        db,
        f"document_job_{operation}",
        username=user.username,
        user_id=user.id,
        detail=detail,
        request=request,
    )
    db.commit()


def _require_document_jobs(user: AuthContext) -> frozenset[str]:
    if not settings.ai_document_studio_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    return _require_artifacts(user)


def _capability_access(user: AuthContext) -> tuple[bool, frozenset[str]]:
    try:
        access = document_job_guard.evaluate_access(user, settings)
        factories = document_job_guard.configured_factory_ids(settings)
    except AIPilotGuardError:
        return False, frozenset()
    return access.granted, factories


@router.get("/capabilities", response_model=DocumentJobCapabilities)
def get_document_job_capabilities(
    current_user: CurrentUser,
    factory_id: Annotated[str | None, Query(max_length=64)] = None,
) -> DocumentJobCapabilities:
    access_granted, allowed_factories = _capability_access(current_user)
    factory_allowed = bool(
        factory_id is None
        or factory_id in allowed_factories
        and ("*" in current_user.factory_scopes or factory_id in current_user.factory_scopes)
    )
    artifact_available = bool(
        access_granted
        and factory_allowed
        and settings.ai_document_studio_enabled
        and settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
    )
    runtime_available = bool(
        access_granted and factory_allowed and task_runtime_available(settings)
    )
    local_translation_available = bool(
        document_translation_status(settings.document_translation_model_dir)["available"]
    )
    return DocumentJobCapabilities(
        available=runtime_available,
        artifact_upload_available=artifact_available,
        task_runtime_available=runtime_available,
        cloud_ocr_available=bool(
            runtime_available and get_document_provider_status(settings).available
        ),
        local_translation_available=bool(
            runtime_available and local_translation_available
        ),
        office_renderer_available=bool(
            runtime_available and office_renderer_available(settings)
        ),
        supported_job_types=(
            tuple(
                sorted(
                    available_document_job_types(
                        local_translation_available=local_translation_available,
                        office_renderer_available=office_renderer_available(settings),
                    ),
                    key=lambda item: item.value,
                )
            )
            if runtime_available
            else ()
        ),
    )


@router.post("/preflight", response_model=DocumentPreflightResult)
def post_document_preflight(
    payload: DocumentPreflightRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentPreflightResult:
    allowed_factories = _require_document_jobs(current_user)
    try:
        result = preflight_owned_document(
            db,
            payload=payload,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
            settings=settings,
        )
        _audit(db, user=current_user, request=request, operation="preflight")
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc
    except ArtifactError as exc:
        raise _error(exc) from exc


@router.post("", response_model=DocumentJobDetail, status_code=status.HTTP_201_CREATED)
def post_document_job(
    payload: DocumentJobCreate,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentJobDetail:
    allowed_factories = _require_document_jobs(current_user)
    try:
        result = create_document_job(
            db,
            payload=payload,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
            settings=settings,
            request_id=str(request.state.request_id),
        )
        _audit(
            db,
            user=current_user,
            request=request,
            operation="create",
            task_id=result.task_id or "",
        )
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc
    except ArtifactError as exc:
        raise _error(exc) from exc


@router.get("", response_model=DocumentJobList)
def get_document_jobs(
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
    factory_id: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> DocumentJobList:
    allowed_factories = _require_document_jobs(current_user)
    try:
        return list_document_jobs(
            db,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            factory_id=factory_id,
            limit=limit,
            storage=storage,
        )
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.get("/metrics", response_model=DocumentJobOperationalMetrics)
def get_document_job_metrics(
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
    factory_id: Annotated[str | None, Query(max_length=64)] = None,
) -> DocumentJobOperationalMetrics:
    allowed_factories = _require_document_jobs(current_user)
    try:
        return document_job_operational_metrics(
            db,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            factory_id=factory_id,
            storage=storage,
        )
    except DocumentJobError as exc:
        raise _error(exc) from exc


def _owned_task(
    db: Session,
    *,
    task_id: str,
    user: AuthContext,
    allowed_factories: frozenset[str],
):
    try:
        return get_owned_task(
            db,
            task_id=task_id,
            user=user,
            allowed_factory_scopes=allowed_factories,
        )
    except AITaskNotFoundError as exc:
        raise DocumentJobNotFoundError("文档任务不存在。") from exc


@router.get("/{task_id}", response_model=DocumentJobDetail)
def get_document_job_detail(
    task_id: str,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentJobDetail:
    allowed_factories = _require_document_jobs(current_user)
    try:
        return get_document_job(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.get("/{task_id}/events", response_model=DocumentJobEventPage)
def get_document_job_events(
    task_id: str,
    db: DbSession,
    current_user: CurrentUser,
    after: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
) -> DocumentJobEventPage:
    allowed_factories = _require_document_jobs(current_user)
    try:
        task = _owned_task(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        return document_job_events(db, task=task, after=after, limit=limit)
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.get("/{task_id}/snapshot", response_model=DocumentSnapshot)
def get_document_job_snapshot(
    task_id: str,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentSnapshot:
    allowed_factories = _require_document_jobs(current_user)
    try:
        return document_job_snapshot(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/cancel", response_model=DocumentJobDetail)
def post_document_job_cancel(
    task_id: str,
    payload: DocumentJobCancelRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentJobDetail:
    allowed_factories = _require_document_jobs(current_user)
    try:
        task = _owned_task(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        cancel_document_job(
            db,
            task=task,
            user=current_user,
            expected_revision=payload.expected_revision,
            reason_code=payload.reason_code,
            settings=settings,
        )
        result = get_document_job(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        _audit(
            db,
            user=current_user,
            request=request,
            operation="cancel",
            task_id=task_id,
        )
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/review", response_model=DocumentJobDetail)
def post_document_job_review(
    task_id: str,
    payload: DocumentJobReviewRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
) -> DocumentJobDetail:
    allowed_factories = _require_document_jobs(current_user)
    try:
        task = _owned_task(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        review_document_job(
            db,
            task=task,
            payload=payload,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
            scanner=scanner,
            settings=settings,
        )
        result = get_document_job(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        _audit(
            db,
            user=current_user,
            request=request,
            operation="review",
            task_id=task_id,
        )
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.post("/{task_id}/retry", response_model=DocumentJobDetail)
def post_document_job_retry(
    task_id: str,
    payload: DocumentJobRetryRequest,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentJobDetail:
    allowed_factories = _require_document_jobs(current_user)
    try:
        task = _owned_task(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factories=allowed_factories,
        )
        retry_document_job(
            db,
            task=task,
            user=current_user,
            expected_revision=payload.expected_revision,
            settings=settings,
        )
        result = get_document_job(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        _audit(
            db,
            user=current_user,
            request=request,
            operation="retry",
            task_id=task_id,
        )
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc


@router.get("/{task_id}/result", response_model=DocumentJobResult)
def get_document_job_result(
    task_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> DocumentJobResult:
    allowed_factories = _require_document_jobs(current_user)
    try:
        detail = get_document_job(
            db,
            task_id=task_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        result = document_job_result(
            db,
            detail=detail,
            user=current_user,
            allowed_factory_ids=allowed_factories,
        )
        _audit(
            db,
            user=current_user,
            request=request,
            operation="result",
            task_id=task_id,
        )
        return result
    except DocumentJobError as exc:
        raise _error(exc) from exc
    except ArtifactError as exc:
        raise _error(exc) from exc
