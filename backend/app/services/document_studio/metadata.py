from __future__ import annotations

import hashlib
import json
from typing import TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.ai_artifact import AIArtifact
from app.models.ai_task import AITaskStep
from app.services.ai.artifacts.contracts import ArtifactDerivationType
from app.services.ai.artifacts.scanner import ArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactIntegrityError,
    create_derived_artifact,
    download_artifact,
)
from app.services.ai.artifacts.storage import ArtifactStorage
from app.services.auth import AuthContext

DocumentModel = TypeVar("DocumentModel", bound=BaseModel)


def canonical_model_bytes(value: BaseModel) -> bytes:
    payload = json.dumps(
        value.model_dump(mode="json", exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return payload.encode("utf-8")


def metadata_artifact_id(
    *, user_id: str, operation_id: str, kind: str, revision: int = 1
) -> str:
    canonical = f"document-metadata-v1:{user_id}:{operation_id}:{kind}:{revision}"
    return f"aiart-{hashlib.sha256(canonical.encode()).hexdigest()[:32]}"


def create_metadata_artifact(
    db: Session,
    *,
    parent: AIArtifact,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    operation_id: str,
    kind: str,
    revision: int,
    value: BaseModel,
    storage: ArtifactStorage,
    scanner: ArtifactScanner,
    settings: Settings,
    parser_version: str,
    model_version: str = "none",
) -> AIArtifact:
    artifact_id = metadata_artifact_id(
        user_id=user.id,
        operation_id=operation_id,
        kind=kind,
        revision=revision,
    )
    expected = canonical_model_bytes(value)
    existing = db.get(AIArtifact, artifact_id)
    if existing is not None:
        download = download_artifact(
            db,
            artifact_id=artifact_id,
            user=user,
            allowed_factory_ids=allowed_factory_ids,
            storage=storage,
        )
        if (
            download.record.parent_artifact_id != parent.id
            or download.record.sha256 != hashlib.sha256(expected).hexdigest()
            or download.data != expected
        ):
            raise ArtifactIntegrityError(
                "文档元数据 Artifact 的幂等结果与任务契约不一致。"
            )
        return download.record
    return create_derived_artifact(
        db,
        parent_artifact_id=parent.id,
        user=user,
        classification=parent.classification,
        derivation_type=ArtifactDerivationType.REPORT,
        filename=f"{kind}-r{revision}.json",
        declared_mime_type="application/json",
        data=expected,
        parser_version=parser_version,
        model_version=model_version,
        storage=storage,
        scanner=scanner,
        settings=settings,
        allowed_factory_ids=allowed_factory_ids,
        artifact_id=artifact_id,
    )


def load_metadata_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    model: type[DocumentModel],
) -> tuple[AIArtifact, DocumentModel]:
    download = download_artifact(
        db,
        artifact_id=artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )
    try:
        parsed = model.model_validate_json(download.data)
    except Exception as exc:
        raise ArtifactIntegrityError(
            "文档元数据 Artifact 不符合封闭契约。"
        ) from exc
    return download.record, parsed


def task_step_result_artifact_id(
    db: Session, *, task_id: str, step_key: str
) -> str | None:
    step = db.scalar(
        select(AITaskStep).where(
            AITaskStep.task_id == task_id,
            AITaskStep.step_key == step_key,
        )
    )
    if step is None or not step.result_metadata_json:
        return None
    try:
        metadata = json.loads(step.result_metadata_json)
    except json.JSONDecodeError:
        return None
    artifact_id = metadata.get("result_artifact_id") if isinstance(metadata, dict) else None
    return artifact_id if isinstance(artifact_id, str) else None
