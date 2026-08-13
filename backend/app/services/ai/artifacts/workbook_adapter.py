from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ai_artifact import AIArtifact
from app.schemas.ai.workbook import AIWorkbookSemanticSnapshot
from app.services.ai.artifacts.contracts import (
    ArtifactContentClass,
    ArtifactParserStatus,
)
from app.services.ai.artifacts.service import (
    ArtifactInvalidError,
    download_artifact,
)
from app.services.ai.artifacts.storage import ArtifactStorage
from app.services.ai.workbook_inspection import INSPECTOR_VERSION, inspect_workbook
from app.services.auth import AuthContext


def inspect_workbook_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    factory_id: str,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
) -> tuple[AIWorkbookSemanticSnapshot, AIArtifact]:
    download = download_artifact(
        db,
        artifact_id=artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )
    record = download.record
    if record.factory_id != factory_id:
        raise ArtifactInvalidError(
            "文件厂区与当前操作厂区不一致。",
            code="AI_ARTIFACT_FACTORY_MISMATCH",
        )
    if (
        record.content_class != ArtifactContentClass.WORKBOOK.value
        or record.normalized_extension != ".xlsx"
    ):
        raise ArtifactInvalidError(
            "Artifact 工作簿流程只接受无宏 .xlsx 文件。",
            code="AI_ARTIFACT_WORKBOOK_TYPE_INVALID",
        )

    record.parser_status = ArtifactParserStatus.PENDING.value
    record.parser_version = INSPECTOR_VERSION
    db.commit()
    try:
        snapshot = inspect_workbook(
            source_file_name=record.original_filename,
            content=download.data,
            factory_id=factory_id,
        )
    except Exception:
        record.parser_status = ArtifactParserStatus.FAILED.value
        db.commit()
        raise
    if snapshot.source_lineage.source_sha256 != record.sha256:
        record.parser_status = ArtifactParserStatus.FAILED.value
        db.commit()
        raise ArtifactInvalidError(
            "工作簿快照与源文件哈希不一致。",
            code="AI_ARTIFACT_SNAPSHOT_SHA_MISMATCH",
        )
    record.parser_status = ArtifactParserStatus.READY.value
    record.parser_version = INSPECTOR_VERSION
    db.commit()
    return (
        snapshot.model_copy(
            update={
                "source_lineage": snapshot.source_lineage.model_copy(
                    update={"artifact_id": record.id}
                )
            }
        ),
        record,
    )


def require_matching_snapshot(
    current: AIWorkbookSemanticSnapshot,
    supplied: AIWorkbookSemanticSnapshot | None,
) -> AIWorkbookSemanticSnapshot:
    if supplied is None:
        return current
    if (
        supplied.factory_id != current.factory_id
        or supplied.source_lineage.source_sha256
        != current.source_lineage.source_sha256
        or supplied.snapshot_sha256 != current.snapshot_sha256
        or supplied.source_lineage.artifact_id not in {None, current.source_lineage.artifact_id}
    ):
        raise ArtifactInvalidError(
            "工作簿快照已变化，请重新 Inspect 后再生成映射建议。",
            code="AI_ARTIFACT_SNAPSHOT_STALE",
        )
    return current
