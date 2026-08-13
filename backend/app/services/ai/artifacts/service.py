from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now, parse_business_timestamp
from app.models.ai_artifact import AIArtifact
from app.schemas.ai.artifact import AIArtifactData, AIArtifactDeleteData
from app.services.ai.artifacts.contracts import (
    CLASSIFICATION_RANK,
    ArtifactClassification,
    ArtifactDerivationType,
    ArtifactParserStatus,
    ArtifactScannerStatus,
    ArtifactStatus,
)
from app.services.ai.artifacts.scanner import (
    ArtifactScanner,
    ArtifactScannerUnavailable,
)
from app.services.ai.artifacts.storage import (
    ArtifactStorage,
    ArtifactStorageError,
    storage_key_for,
)
from app.services.ai.artifacts.validation import (
    ArtifactValidationError,
    validate_artifact_upload,
)
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext

artifact_logger = logging.getLogger("app.ai.artifacts")


class ArtifactError(RuntimeError):
    code = "AI_ARTIFACT_ERROR"
    status_code = 400
    retryable = False

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


class ArtifactNotFoundError(ArtifactError):
    code = "AI_ARTIFACT_NOT_FOUND"
    status_code = 404


class ArtifactInvalidError(ArtifactError):
    code = "AI_ARTIFACT_INVALID"
    status_code = 422

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class ArtifactScannerFailedError(ArtifactError):
    code = "AI_ARTIFACT_SCANNER_UNAVAILABLE"
    status_code = 503
    retryable = True


class ArtifactStorageFailedError(ArtifactError):
    code = "AI_ARTIFACT_STORAGE_UNAVAILABLE"
    status_code = 503
    retryable = True


class ArtifactIntegrityError(ArtifactError):
    code = "AI_ARTIFACT_INTEGRITY_FAILED"
    status_code = 409


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    record: AIArtifact
    data: bytes


def _now_text(now: datetime | None = None) -> str:
    return (now or business_now()).isoformat(timespec="seconds")


def _parse_classification(value: str | ArtifactClassification) -> ArtifactClassification:
    try:
        return ArtifactClassification(str(value))
    except ValueError as exc:
        raise ArtifactInvalidError(
            "文件分类无效。", code="AI_ARTIFACT_CLASSIFICATION_INVALID"
        ) from exc


def _user_has_factory(user: AuthContext, factory_id: str) -> bool:
    return factory_id in ALLOWED_FACTORY_IDS and (
        "*" in user.factory_scopes or factory_id in user.factory_scopes
    )


def _require_factory(
    user: AuthContext,
    factory_id: str,
    *,
    allowed_factory_ids: frozenset[str] | None = None,
) -> str:
    normalized = factory_id.strip()
    if (
        not _user_has_factory(user, normalized)
        or allowed_factory_ids is not None
        and normalized not in allowed_factory_ids
    ):
        raise ArtifactInvalidError(
            "当前账号无该厂区的文件权限。", code="AI_ARTIFACT_FACTORY_DENIED"
        )
    return normalized


def artifact_data(record: AIArtifact) -> AIArtifactData:
    return AIArtifactData.model_validate(record)


def _validated(
    *, filename: str, declared_mime_type: str, data: bytes
):
    try:
        return validate_artifact_upload(
            filename=filename,
            declared_mime_type=declared_mime_type,
            data=data,
        )
    except ArtifactValidationError as exc:
        raise ArtifactInvalidError(exc.public_message, code=exc.code) from exc


def _scan(scanner: ArtifactScanner, data: bytes) -> str:
    try:
        result = scanner.scan(data)
    except ArtifactScannerUnavailable as exc:
        raise ArtifactScannerFailedError("文件扫描服务暂不可用，上传已阻止。") from exc
    if not result.clean:
        raise ArtifactInvalidError(
            "文件未通过安全扫描。", code="AI_ARTIFACT_SCAN_REJECTED"
        )
    return result.result_code


def _persist(
    db: Session,
    *,
    storage: ArtifactStorage,
    record: AIArtifact,
    data: bytes,
) -> AIArtifact:
    wrote = False
    try:
        storage.put(record.storage_key, data)
        wrote = True
        db.add(record)
        db.commit()
        db.refresh(record)
    except ArtifactStorageError as exc:
        db.rollback()
        raise ArtifactStorageFailedError("文件存储暂不可用，上传未登记。") from exc
    except SQLAlchemyError:
        db.rollback()
        if wrote:
            try:
                storage.delete(record.storage_key)
            except ArtifactStorageError:
                artifact_logger.error(
                    "artifact_orphan_cleanup_failed artifact_id=%s size=%s type=%s hash_prefix=%s status=DB_ROLLBACK",
                    record.id,
                    record.size_bytes,
                    record.detected_mime_type,
                    record.sha256[:12],
                )
        raise
    artifact_logger.info(
        "artifact_registered artifact_id=%s size=%s type=%s hash_prefix=%s status=%s",
        record.id,
        record.size_bytes,
        record.detected_mime_type,
        record.sha256[:12],
        record.status,
    )
    return record


def create_artifact(
    db: Session,
    *,
    user: AuthContext,
    factory_id: str,
    classification: str | ArtifactClassification,
    filename: str,
    declared_mime_type: str,
    data: bytes,
    storage: ArtifactStorage,
    scanner: ArtifactScanner,
    settings: Settings,
    allowed_factory_ids: frozenset[str] | None = None,
    now: datetime | None = None,
) -> AIArtifact:
    factory = _require_factory(
        user, factory_id, allowed_factory_ids=allowed_factory_ids
    )
    artifact_classification = _parse_classification(classification)
    validated = _validated(
        filename=filename, declared_mime_type=declared_mime_type, data=data
    )
    scanner_code = _scan(scanner, validated.data)
    current = now or business_now()
    artifact_id = f"aiart-{uuid4().hex}"
    record = AIArtifact(
        id=artifact_id,
        owner_user_id=user.id,
        factory_id=factory,
        original_filename=validated.original_filename,
        normalized_extension=validated.normalized_extension,
        declared_mime_type=validated.declared_mime_type,
        detected_mime_type=validated.detected_mime_type,
        content_class=validated.content_class.value,
        size_bytes=validated.size_bytes,
        sha256=validated.sha256,
        classification=artifact_classification.value,
        storage_key=storage_key_for(artifact_id),
        status=ArtifactStatus.ACTIVE.value,
        scanner_status=ArtifactScannerStatus.CLEAN.value,
        scanner_result_code=scanner_code,
        parser_status=ArtifactParserStatus.NOT_REQUESTED.value,
        parser_version="",
        model_version="",
        parent_artifact_id=None,
        derivation_type=ArtifactDerivationType.ORIGINAL.value,
        retention_until=_now_text(
            current + timedelta(days=settings.ai_artifact_retention_days)
        ),
        deleted_at="",
        storage_deleted_at="",
        tombstone_expires_at="",
        backup_delete_by="",
        created_at=_now_text(current),
        updated_at=_now_text(current),
    )
    return _persist(db, storage=storage, record=record, data=validated.data)


def get_owned_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str] | None = None,
    include_revoked: bool = False,
) -> AIArtifact:
    record = db.scalar(select(AIArtifact).where(AIArtifact.id == artifact_id))
    allowed = (
        record is not None
        and record.owner_user_id == user.id
        and _user_has_factory(user, record.factory_id)
        and (allowed_factory_ids is None or record.factory_id in allowed_factory_ids)
        and (include_revoked or record.status == ArtifactStatus.ACTIVE.value)
    )
    if not allowed:
        raise ArtifactNotFoundError("文件不存在。")
    return record


def download_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str] | None,
    storage: ArtifactStorage,
) -> ArtifactDownload:
    record = get_owned_artifact(
        db,
        artifact_id=artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    if record.scanner_status != ArtifactScannerStatus.CLEAN.value:
        raise ArtifactNotFoundError("文件不存在。")
    try:
        data = storage.read(record.storage_key)
    except ArtifactStorageError as exc:
        raise ArtifactStorageFailedError("文件暂不可下载。") from exc
    import hashlib

    if len(data) != record.size_bytes or hashlib.sha256(data).hexdigest() != record.sha256:
        artifact_logger.error(
            "artifact_integrity_failed artifact_id=%s size=%s type=%s hash_prefix=%s status=%s",
            record.id,
            record.size_bytes,
            record.detected_mime_type,
            record.sha256[:12],
            record.status,
        )
        raise ArtifactIntegrityError("文件完整性校验失败，下载已阻止。")
    return ArtifactDownload(record=record, data=data)


def create_derived_artifact(
    db: Session,
    *,
    parent_artifact_id: str,
    user: AuthContext,
    classification: str | ArtifactClassification,
    derivation_type: str | ArtifactDerivationType,
    filename: str,
    declared_mime_type: str,
    data: bytes,
    parser_version: str,
    model_version: str,
    storage: ArtifactStorage,
    scanner: ArtifactScanner,
    settings: Settings,
    allowed_factory_ids: frozenset[str] | None = None,
    now: datetime | None = None,
    artifact_id: str | None = None,
) -> AIArtifact:
    parent = get_owned_artifact(
        db,
        artifact_id=parent_artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    if parent.scanner_status != ArtifactScannerStatus.CLEAN.value:
        raise ArtifactNotFoundError("源文件不存在。")
    target_classification = _parse_classification(classification)
    parent_classification = ArtifactClassification(parent.classification)
    if CLASSIFICATION_RANK[target_classification] < CLASSIFICATION_RANK[parent_classification]:
        raise ArtifactInvalidError(
            "派生文件不能降低源文件分类。",
            code="AI_ARTIFACT_CLASSIFICATION_DOWNGRADE",
        )
    try:
        derivation = ArtifactDerivationType(str(derivation_type))
    except ValueError as exc:
        raise ArtifactInvalidError("派生类型无效。") from exc
    if derivation is ArtifactDerivationType.ORIGINAL:
        raise ArtifactInvalidError("派生文件不能标记为原件。")
    if not parser_version.strip() and not model_version.strip():
        raise ArtifactInvalidError("派生文件必须记录解析器或模型版本。")
    validated = _validated(
        filename=filename, declared_mime_type=declared_mime_type, data=data
    )
    scanner_code = _scan(scanner, validated.data)
    current = now or business_now()
    parent_retention = parse_business_timestamp(parent.retention_until)
    if parent_retention is None or parent_retention <= current:
        raise ArtifactNotFoundError("源文件不存在。")
    default_retention = current + timedelta(days=settings.ai_artifact_retention_days)
    retention = min(default_retention, parent_retention)
    artifact_id = artifact_id or f"aiart-{uuid4().hex}"
    try:
        storage_key = storage_key_for(artifact_id)
    except ArtifactStorageError as exc:
        raise ArtifactInvalidError(
            "派生文件幂等标识无效。",
            code="AI_ARTIFACT_DERIVATION_ID_INVALID",
        ) from exc
    existing = db.get(AIArtifact, artifact_id)
    if existing is not None:
        if (
            existing.owner_user_id != user.id
            or existing.factory_id != parent.factory_id
            or existing.parent_artifact_id != parent.id
            or existing.derivation_type != derivation.value
            or existing.classification != target_classification.value
            or existing.sha256 != validated.sha256
            or existing.parser_version != parser_version.strip()[:64]
            or existing.model_version != model_version.strip()[:128]
        ):
            raise ArtifactIntegrityError("派生文件幂等结果与本次请求不一致。")
        return existing
    record = AIArtifact(
        id=artifact_id,
        owner_user_id=user.id,
        factory_id=parent.factory_id,
        original_filename=validated.original_filename,
        normalized_extension=validated.normalized_extension,
        declared_mime_type=validated.declared_mime_type,
        detected_mime_type=validated.detected_mime_type,
        content_class=validated.content_class.value,
        size_bytes=validated.size_bytes,
        sha256=validated.sha256,
        classification=target_classification.value,
        storage_key=storage_key,
        status=ArtifactStatus.ACTIVE.value,
        scanner_status=ArtifactScannerStatus.CLEAN.value,
        scanner_result_code=scanner_code,
        parser_status=ArtifactParserStatus.READY.value,
        parser_version=parser_version.strip()[:64],
        model_version=model_version.strip()[:128],
        parent_artifact_id=parent.id,
        derivation_type=derivation.value,
        retention_until=_now_text(retention),
        deleted_at="",
        storage_deleted_at="",
        tombstone_expires_at="",
        backup_delete_by="",
        created_at=_now_text(current),
        updated_at=_now_text(current),
    )
    return _persist(db, storage=storage, record=record, data=validated.data)


def delete_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str] | None,
    storage: ArtifactStorage,
    settings: Settings,
    now: datetime | None = None,
) -> AIArtifactDeleteData:
    record = get_owned_artifact(
        db,
        artifact_id=artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
    )
    current = now or business_now()
    current_text = _now_text(current)
    record.status = ArtifactStatus.DELETION_PENDING.value
    record.deleted_at = current_text
    record.tombstone_expires_at = _now_text(
        current + timedelta(days=settings.ai_artifact_tombstone_retention_days)
    )
    record.backup_delete_by = _now_text(
        current + timedelta(days=settings.ai_artifact_backup_delete_sla_days)
    )
    record.updated_at = current_text
    db.commit()
    try:
        storage.delete(record.storage_key)
    except ArtifactStorageError:
        artifact_logger.error(
            "artifact_online_delete_pending artifact_id=%s size=%s type=%s hash_prefix=%s status=%s",
            record.id,
            record.size_bytes,
            record.detected_mime_type,
            record.sha256[:12],
            record.status,
        )
    else:
        record.status = ArtifactStatus.DELETED.value
        record.storage_deleted_at = current_text
        record.updated_at = current_text
        db.commit()
    return AIArtifactDeleteData(
        id=record.id,
        status=record.status,
        access_revoked=True,
        deleted_at=current_text,
        online_delete_due_by=_now_text(current + timedelta(hours=24)),
        backup_delete_by=record.backup_delete_by,
    )
