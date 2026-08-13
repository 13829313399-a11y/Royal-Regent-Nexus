from __future__ import annotations

from pathlib import Path
from typing import Annotated
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db
from app.schemas.ai.artifact import AIArtifactData, AIArtifactDeleteData
from app.services.ai.artifacts.contracts import MAX_DOCUMENT_BYTES
from app.services.ai.artifacts.scanner import (
    ArtifactScanner,
    ClamAVArtifactScanner,
    UnavailableArtifactScanner,
)
from app.services.ai.artifacts.service import (
    ArtifactError,
    ArtifactNotFoundError,
    artifact_data,
    create_artifact,
    delete_artifact,
    download_artifact,
    get_owned_artifact,
)
from app.services.ai.artifacts.storage import (
    ArtifactStorage,
    LocalImmutableArtifactStorage,
)
from app.services.ai.pilot_guard import AIPilotGuard, AIPilotGuardError
from app.services.auth import AuthContext, add_auth_audit, get_current_user

router = APIRouter(prefix="/api/ai/artifacts", tags=["ai-artifacts"])
artifact_pilot_guard = AIPilotGuard()

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def get_artifact_storage() -> ArtifactStorage:
    return LocalImmutableArtifactStorage(settings.ai_artifact_storage_dir)


def get_artifact_scanner() -> ArtifactScanner:
    if settings.ai_artifact_scanner_backend == "clamav":
        return ClamAVArtifactScanner(
            settings.ai_artifact_clamav_host,
            settings.ai_artifact_clamav_port,
            settings.ai_artifact_clamav_timeout_seconds,
        )
    return UnavailableArtifactScanner()


ArtifactStorageDependency = Annotated[ArtifactStorage, Depends(get_artifact_storage)]
ArtifactScannerDependency = Annotated[ArtifactScanner, Depends(get_artifact_scanner)]


def _artifact_error(error: ArtifactError) -> HTTPException:
    return HTTPException(
        status_code=error.status_code,
        detail={
            "code": error.code,
            "message": error.public_message,
            "retryable": error.retryable,
        },
    )


def _require_artifacts(user: AuthContext) -> frozenset[str]:
    if not settings.ai_artifacts_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    try:
        access = artifact_pilot_guard.evaluate_access(user, settings)
        allowed_factories = artifact_pilot_guard.configured_factory_ids(settings)
    except AIPilotGuardError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.payload()) from exc
    if not access.granted:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_PILOT_ACCESS_DENIED",
                "message": "当前账号未开放 AI 文件权限。",
                "retryable": False,
            },
        )
    return allowed_factories


def _audit(
    db: Session,
    *,
    user: AuthContext,
    operation: str,
    request: Request,
    artifact_id: str = "",
) -> None:
    detail = f"operation={operation}"
    if artifact_id:
        detail += f" artifact_id={artifact_id}"
    add_auth_audit(
        db,
        f"ai_artifact_{operation}",
        username=user.username,
        user_id=user.id,
        detail=detail,
        request=request,
    )
    db.commit()


@router.post(
    "",
    response_model=AIArtifactData,
    status_code=status.HTTP_201_CREATED,
)
async def post_artifact(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
    factory_id: Annotated[str, Form(min_length=1, max_length=64)],
    classification: Annotated[str, Form(min_length=1, max_length=32)],
    file: Annotated[UploadFile, File()],
):
    allowed_factories = _require_artifacts(current_user)
    try:
        data = await file.read(MAX_DOCUMENT_BYTES + 1)
        record = create_artifact(
            db,
            user=current_user,
            factory_id=factory_id,
            classification=classification,
            filename=file.filename or "",
            declared_mime_type=file.content_type or "",
            data=data,
            storage=storage,
            scanner=scanner,
            settings=settings,
            allowed_factory_ids=allowed_factories,
        )
        _audit(
            db,
            user=current_user,
            operation="upload",
            request=request,
            artifact_id=record.id,
        )
        return artifact_data(record)
    except ArtifactError as exc:
        _audit(
            db,
            user=current_user,
            operation="upload_denied",
            request=request,
        )
        raise _artifact_error(exc) from exc
    finally:
        await file.close()


@router.post(
    "/vision-upload",
    response_model=AIArtifactData,
    status_code=status.HTTP_201_CREATED,
)
async def post_vision_artifact(
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
    scanner: ArtifactScannerDependency,
    factory_id: Annotated[str, Form(min_length=1, max_length=64)],
    classification: Annotated[str, Form(min_length=1, max_length=32)],
    file: Annotated[UploadFile, File()],
):
    if not settings.ai_artifact_workflows_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    allowed_factories = _require_artifacts(current_user)
    try:
        if Path(file.filename or "").suffix.lower() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
        }:
            raise HTTPException(status_code=422, detail="只支持静态图片 Artifact。")
        data = await file.read(MAX_DOCUMENT_BYTES + 1)
        record = create_artifact(
            db,
            user=current_user,
            factory_id=factory_id,
            classification=classification,
            filename=file.filename or "",
            declared_mime_type=file.content_type or "",
            data=data,
            storage=storage,
            scanner=scanner,
            settings=settings,
            allowed_factory_ids=allowed_factories,
        )
        _audit(
            db,
            user=current_user,
            operation="vision_upload",
            request=request,
            artifact_id=record.id,
        )
        return artifact_data(record)
    except ArtifactError as exc:
        _audit(
            db,
            user=current_user,
            operation="vision_upload_denied",
            request=request,
        )
        raise _artifact_error(exc) from exc
    finally:
        await file.close()


@router.get("/{artifact_id}", response_model=AIArtifactData)
def get_artifact(
    artifact_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
):
    allowed_factories = _require_artifacts(current_user)
    try:
        record = get_owned_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
        )
        _audit(
            db,
            user=current_user,
            operation="metadata_read",
            request=request,
            artifact_id=record.id,
        )
        return artifact_data(record)
    except ArtifactError as exc:
        if isinstance(exc, ArtifactNotFoundError):
            _audit(
                db,
                user=current_user,
                operation="metadata_denied",
                request=request,
            )
        raise _artifact_error(exc) from exc


@router.get("/{artifact_id}/download")
def get_artifact_download(
    artifact_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
) -> Response:
    allowed_factories = _require_artifacts(current_user)
    try:
        download = download_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
        )
        _audit(
            db,
            user=current_user,
            operation="download",
            request=request,
            artifact_id=download.record.id,
        )
        fallback = f"artifact{download.record.normalized_extension}"
        disposition = (
            f'attachment; filename="{fallback}"; '
            f"filename*=UTF-8''{quote(download.record.original_filename, safe='')}"
        )
        return Response(
            content=download.data,
            media_type=download.record.detected_mime_type,
            headers={
                "Content-Disposition": disposition,
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox",
            },
        )
    except ArtifactError as exc:
        _audit(
            db,
            user=current_user,
            operation="download_denied",
            request=request,
        )
        raise _artifact_error(exc) from exc


@router.delete("/{artifact_id}", response_model=AIArtifactDeleteData)
def remove_artifact(
    artifact_id: str,
    request: Request,
    db: DbSession,
    current_user: CurrentUser,
    storage: ArtifactStorageDependency,
):
    allowed_factories = _require_artifacts(current_user)
    try:
        result = delete_artifact(
            db,
            artifact_id=artifact_id,
            user=current_user,
            allowed_factory_ids=allowed_factories,
            storage=storage,
            settings=settings,
        )
        _audit(
            db,
            user=current_user,
            operation="delete",
            request=request,
            artifact_id=result.id,
        )
        return result
    except ArtifactError as exc:
        _audit(
            db,
            user=current_user,
            operation="delete_denied",
            request=request,
        )
        raise _artifact_error(exc) from exc
