from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import settings
from app.models.ai_artifact import AIArtifact
from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel, StrictToolInput
from app.services.ai.artifacts.contracts import ArtifactDerivationType
from app.services.ai.artifacts.scanner import (
    ArtifactScanner,
    ClamAVArtifactScanner,
    UnavailableArtifactScanner,
)
from app.services.ai.artifacts.service import (
    ArtifactIntegrityError,
    ArtifactInvalidError,
    create_derived_artifact,
    download_artifact,
    get_owned_artifact,
)
from app.services.ai.artifacts.storage import (
    ArtifactStorage,
    LocalImmutableArtifactStorage,
)
from app.services.ai.artifacts.translation_adapter import TRANSLATION_TERMS_VERSION
from app.services.ai.artifacts.workbook_adapter import inspect_workbook_artifact
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.auth import ALLOWED_FACTORY_IDS
from app.services.document_translation import translate_document

_OPERATION_ID = r"^[A-Za-z0-9._-]{8,128}$"


class ArtifactWorkbookInspectInput(StrictToolInput):
    factory_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    artifact_id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    operation_id: str = Field(pattern=_OPERATION_ID)


class ArtifactTranslateLocalInput(StrictToolInput):
    factory_id: str = Field(pattern=r"^[a-z][a-z0-9-]{1,63}$")
    artifact_id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    operation_id: str = Field(pattern=_OPERATION_ID)
    direction: Literal["zh_to_en", "en_to_zh"]
    selected_sheet_names: tuple[str, ...] | None = Field(
        default=None,
        max_length=50,
    )


class ArtifactWorkflowResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["USER_PROVIDED"] = "USER_PROVIDED"
    operation_id: str
    factory_id: str
    source_artifact_id: str
    source_sha256: str
    result_artifact_id: str
    result_sha256: str
    parser_version: str
    model_version: str
    source_unchanged: Literal[True] = True
    idempotent_replay: bool
    result_file_name: str
    sheet_count: int | None = None
    snapshot_sha256: str | None = None
    translated_unit_count: int | None = None
    skipped_unit_count: int | None = None
    processed_part_count: int | None = None


def _storage() -> ArtifactStorage:
    return LocalImmutableArtifactStorage(settings.ai_artifact_storage_dir)


def _scanner() -> ArtifactScanner:
    if settings.ai_artifact_scanner_backend == "clamav":
        return ClamAVArtifactScanner(
            settings.ai_artifact_clamav_host,
            settings.ai_artifact_clamav_port,
            settings.ai_artifact_clamav_timeout_seconds,
        )
    return UnavailableArtifactScanner()


def _allowed_factories() -> frozenset[str]:
    return frozenset(
        value.strip()
        for value in settings.ai_pilot_factory_ids.split(",")
        if value.strip() in ALLOWED_FACTORY_IDS
    )


def _deterministic_artifact_id(
    *,
    user_id: str,
    source: AIArtifact,
    arguments: ArtifactTranslateLocalInput,
) -> str:
    payload = json.dumps(
        {
            "contract": "artifact-translation-task-v1",
            "user_id": user_id,
            "source_artifact_id": source.id,
            "source_sha256": source.sha256,
            "operation_id": arguments.operation_id,
            "direction": arguments.direction,
            "selected_sheet_names": arguments.selected_sheet_names,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"aiart-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:32]}"


def _require_context(context: ToolExecutionContext):
    if context.db is None:
        raise ValueError("Artifact workflow Tool requires a managed database")
    if not settings.ai_artifact_workflows_enabled:
        raise ValueError("Artifact workflow adapter is disabled")
    return context.db


def inspect_workbook_task(
    context: ToolExecutionContext,
    arguments: ArtifactWorkbookInspectInput,
) -> ArtifactWorkflowResult:
    db = _require_context(context)
    previous = get_owned_artifact(
        db,
        artifact_id=arguments.artifact_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
    )
    was_ready = previous.parser_status == "READY"
    snapshot, source = inspect_workbook_artifact(
        db,
        artifact_id=arguments.artifact_id,
        user=context.user,
        factory_id=arguments.factory_id,
        allowed_factory_ids=_allowed_factories(),
        storage=_storage(),
    )
    return ArtifactWorkflowResult(
        operation_id=arguments.operation_id,
        factory_id=source.factory_id,
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        result_artifact_id=source.id,
        result_sha256=source.sha256,
        parser_version=source.parser_version,
        model_version=source.model_version,
        idempotent_replay=was_ready,
        result_file_name=source.original_filename,
        sheet_count=snapshot.sheet_count,
        snapshot_sha256=snapshot.snapshot_sha256,
    )


def _existing_translation(
    context: ToolExecutionContext,
    *,
    derived_id: str,
    source: AIArtifact,
    arguments: ArtifactTranslateLocalInput,
) -> ArtifactWorkflowResult | None:
    assert context.db is not None
    existing = context.db.get(AIArtifact, derived_id)
    if existing is None:
        return None
    visible = get_owned_artifact(
        context.db,
        artifact_id=derived_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
    )
    expected_model = f"ctranslate2:{arguments.direction}"
    if (
        visible.parent_artifact_id != source.id
        or visible.derivation_type != ArtifactDerivationType.TRANSLATION.value
        or visible.parser_version != TRANSLATION_TERMS_VERSION
        or visible.model_version != expected_model
        or visible.classification != source.classification
    ):
        raise ArtifactIntegrityError("派生文件幂等结果与 Task 契约不一致。")
    return ArtifactWorkflowResult(
        operation_id=arguments.operation_id,
        factory_id=source.factory_id,
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        result_artifact_id=visible.id,
        result_sha256=visible.sha256,
        parser_version=visible.parser_version,
        model_version=visible.model_version,
        idempotent_replay=True,
        result_file_name=visible.original_filename,
    )


def translate_document_local_task(
    context: ToolExecutionContext,
    arguments: ArtifactTranslateLocalInput,
) -> ArtifactWorkflowResult:
    db = _require_context(context)
    download = download_artifact(
        db,
        artifact_id=arguments.artifact_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        storage=_storage(),
    )
    source = download.record
    if source.factory_id != arguments.factory_id:
        raise ArtifactInvalidError(
            "文件厂区与 Task 厂区不一致。",
            code="AI_ARTIFACT_FACTORY_MISMATCH",
        )
    if source.normalized_extension not in {".xlsx", ".docx"}:
        raise ArtifactInvalidError(
            "Task 翻译只接受无宏 .xlsx 或 .docx。",
            code="AI_ARTIFACT_TRANSLATION_TYPE_INVALID",
        )
    derived_id = _deterministic_artifact_id(
        user_id=context.user.id,
        source=source,
        arguments=arguments,
    )
    replay = _existing_translation(
        context,
        derived_id=derived_id,
        source=source,
        arguments=arguments,
    )
    if replay is not None:
        return replay

    result = translate_document(
        download.data,
        source.original_filename,
        direction=arguments.direction,
        model_dir=settings.document_translation_model_dir,
        device=settings.document_translation_device,
        selected_sheet_names=arguments.selected_sheet_names,
    )
    derived = create_derived_artifact(
        db,
        parent_artifact_id=source.id,
        user=context.user,
        classification=source.classification,
        derivation_type=ArtifactDerivationType.TRANSLATION,
        filename=result.output_file_name,
        declared_mime_type=result.media_type,
        data=result.content,
        parser_version=TRANSLATION_TERMS_VERSION,
        model_version=f"ctranslate2:{arguments.direction}",
        storage=_storage(),
        scanner=_scanner(),
        settings=settings,
        allowed_factory_ids=_allowed_factories(),
        artifact_id=derived_id,
    )
    return ArtifactWorkflowResult(
        operation_id=arguments.operation_id,
        factory_id=source.factory_id,
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        result_artifact_id=derived.id,
        result_sha256=derived.sha256,
        parser_version=derived.parser_version,
        model_version=derived.model_version,
        idempotent_replay=False,
        result_file_name=derived.original_filename,
        translated_unit_count=result.translated_unit_count,
        skipped_unit_count=result.skipped_unit_count,
        processed_part_count=result.processed_part_count,
    )


def serialize_artifact_workflow_result(value: object) -> ArtifactWorkflowResult:
    if isinstance(value, ArtifactWorkflowResult):
        return value
    return ArtifactWorkflowResult.model_validate(value)


def artifact_workflow_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="artifacts.inspect_workbook",
            description="通过不可变 Artifact 读取工作簿语义快照；只生成预览元数据。",
            input_model=ArtifactWorkbookInspectInput,
            risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            executor=inspect_workbook_task,
            serializer=serialize_artifact_workflow_result,
            display_label="正在检查工作簿 Artifact",
            tool_group="identity",
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=60,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
            version="1.0.0",
        ),
        ToolSpec(
            name="artifacts.translate_document_local",
            description="使用服务器本地模型翻译 Artifact，并生成不可变派生 Artifact。",
            input_model=ArtifactTranslateLocalInput,
            risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            executor=translate_document_local_task,
            serializer=serialize_artifact_workflow_result,
            display_label="正在本地翻译文件 Artifact",
            tool_group="identity",
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=600,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
            version="1.0.0",
        ),
    )
