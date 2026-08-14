from __future__ import annotations

import hashlib
import json

from app.core.config import settings
from app.models.ai_artifact import AIArtifact
from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.document_studio import (
    DocumentSnapshot,
    DocumentStudioTaskOptions,
    DocumentStudioToolMetrics,
    DocumentStudioToolResult,
)
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
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.auth import ALLOWED_FACTORY_IDS
from app.services.document_studio.contracts import (
    DocumentJobType,
    DocumentProcessingMode,
)
from app.services.document_studio.evidence import extract_local_snapshot
from app.services.document_studio.extractors.qwen_ocr import enhance_snapshot_with_qwen
from app.services.document_studio.metadata import (
    create_metadata_artifact,
    load_metadata_artifact,
    metadata_artifact_id,
    task_step_result_artifact_id,
)
from app.services.document_studio.pipelines.pdf_to_excel import (
    convert_pdf_to_evidence_workbook,
)
from app.services.document_studio.pipelines.pdf_to_word import convert_pdf_to_word
from app.services.document_studio.pipelines.pdf_translation import (
    PdfTranslationError,
    translate_snapshot,
)
from app.services.document_studio.pipelines.word_to_pdf import convert_word_to_pdf
from app.services.document_studio.preflight import preflight_document
from app.services.document_studio.providers.qwen_document import (
    QwenDocumentError,
    QwenDocumentProvider,
    get_document_provider_status,
)
from app.services.document_studio.providers.qwen_reconcile import (
    QwenReconcileError,
    QwenReconcileProvider,
    apply_reconcile_result,
    reconcile_provider_available,
)
from app.services.document_studio.providers.signed_file_source import (
    BrokerSignedFileSource,
)
from app.services.document_studio.quality import build_quality_report
from app.services.document_studio.renderers.office_pdf_renderer import (
    OfficePdfRenderError,
)
from app.services.document_studio.renderers.pdf_translation_renderer import (
    render_pdf_translation,
)
from app.services.document_translation import document_translation_status
from app.services.pdf_split import split_pdf

PARSER_VERSION = "document-studio-deterministic-v1"
MODEL_VERSION = "none"


def _office_renderer_available() -> bool:
    return bool(
        settings.document_office_renderer_enabled
        and settings.document_office_renderer_network_isolation_verified
    )


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


def _db(context: ToolExecutionContext):
    if context.db is None:
        raise ValueError("Document Studio Tool requires a managed database")
    if not (
        settings.ai_document_studio_enabled
        and settings.ai_artifacts_enabled
        and settings.ai_artifact_workflows_enabled
    ):
        raise ValueError("Document Studio Artifact workflow is disabled")
    return context.db


def _source_download(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
):
    db = _db(context)
    download = download_artifact(
        db,
        artifact_id=arguments.source_artifact_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        storage=_storage(),
    )
    source = download.record
    if source.factory_id != arguments.factory_id:
        raise ArtifactInvalidError(
            "文件厂区与文档 Task 厂区不一致。",
            code="DOCUMENT_JOB_FACTORY_MISMATCH",
        )
    if source.sha256 != arguments.source_sha256:
        raise ArtifactIntegrityError("源文件哈希与文档 Task 契约不一致。")
    return db, download


def _result_id(context: ToolExecutionContext, arguments: DocumentStudioTaskOptions) -> str:
    canonical = json.dumps(
        {
            "contract": "document-studio-deterministic-v1",
            "user_id": context.user.id,
            **arguments.model_dump(mode="json"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"aiart-{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:32]}"


def _result(
    *,
    stage: str,
    arguments: DocumentStudioTaskOptions,
    source: AIArtifact,
    result: AIArtifact | None = None,
    replay: bool = True,
    metrics: DocumentStudioToolMetrics | None = None,
    review_required: bool = False,
) -> DocumentStudioToolResult:
    target = result or source
    return DocumentStudioToolResult(
        stage=stage,
        operation_id=arguments.operation_id,
        factory_id=source.factory_id,
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        result_artifact_id=target.id,
        result_sha256=target.sha256,
        parser_version=(target.parser_version or PARSER_VERSION),
        model_version=(target.model_version or MODEL_VERSION),
        idempotent_replay=replay,
        result_file_name=target.original_filename,
        review_required=review_required,
        metrics=metrics or DocumentStudioToolMetrics(),
    )


def inspect_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    _, download = _source_download(context, arguments)
    preflight = preflight_document(
        source=download.record,
        data=download.data,
        job_type=arguments.job_type,
        processing_mode=arguments.processing_mode,
        task_runtime_available=True,
        cloud_ocr_available=settings.ai_document_cloud_ocr_enabled,
        local_translation_available=bool(
            document_translation_status(settings.document_translation_model_dir)[
                "available"
            ]
        ),
        office_renderer_available=_office_renderer_available(),
    )
    return _result(
        stage="INSPECT",
        arguments=arguments,
        source=download.record,
        metrics=DocumentStudioToolMetrics(page_count=preflight.page_count),
    )


def _validated_passthrough(
    stage: str,
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    _, download = _source_download(context, arguments)
    return _result(stage=stage, arguments=arguments, source=download.record)


def _metadata_result(
    *,
    stage: str,
    arguments: DocumentStudioTaskOptions,
    source: AIArtifact,
    artifact: AIArtifact,
    replay: bool,
    review_required: bool = False,
    metrics: DocumentStudioToolMetrics | None = None,
) -> DocumentStudioToolResult:
    return _result(
        stage=stage,
        arguments=arguments,
        source=source,
        result=artifact,
        replay=replay,
        review_required=review_required,
        metrics=metrics,
    )


def _current_snapshot_artifact_id(db, *, task_id: str | None) -> str | None:
    return task_step_result_artifact_id(
        db, task_id=task_id, step_key="reconcile_document"
    ) or task_step_result_artifact_id(
        db, task_id=task_id, step_key="extract_document"
    )


def extract_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    db, download = _source_download(context, arguments)
    artifact_id = metadata_artifact_id(
        user_id=context.user.id,
        operation_id=arguments.operation_id,
        kind="document-snapshot",
    )
    existing = db.get(AIArtifact, artifact_id)
    if existing is not None:
        _, snapshot = load_metadata_artifact(
            db,
            artifact_id=artifact_id,
            user=context.user,
            allowed_factory_ids=_allowed_factories(),
            storage=_storage(),
            model=DocumentSnapshot,
        )
        return _metadata_result(
            stage="EXTRACT",
            arguments=arguments,
            source=download.record,
            artifact=existing,
            replay=True,
            metrics=DocumentStudioToolMetrics(
                page_count=snapshot.page_count,
                table_count=sum(len(page.tables) for page in snapshot.pages),
                text_page_count=sum(bool(page.blocks) for page in snapshot.pages),
                ocr_page_count=sum(
                    page.extraction_route.value != "NATIVE" for page in snapshot.pages
                ),
                cloud_page_count=sum(
                    page.extraction_route.value == "QWEN_OCR" for page in snapshot.pages
                ),
            ),
        )
    snapshot = extract_local_snapshot(
        data=download.data,
        source_artifact_id=download.record.id,
        source_sha256=download.record.sha256,
        document_kind=arguments.options.profile,
    )
    model_version = MODEL_VERSION
    if (
        arguments.processing_mode == DocumentProcessingMode.AI_ENHANCED
        and settings.ai_document_cloud_ocr_enabled
    ):
        if download.record.classification == "RESTRICTED":
            raise ArtifactInvalidError(
                "RESTRICTED 文档禁止发送到云端 OCR。",
                code="DOCUMENT_CLOUD_RESTRICTED",
            )
        if arguments.cloud_consent is None:
            raise ArtifactInvalidError(
                "AI 增强文档缺少云端处理同意。",
                code="DOCUMENT_CLOUD_CONSENT_REQUIRED",
            )
        status = get_document_provider_status(settings)
        if status.available:
            try:
                snapshot = enhance_snapshot_with_qwen(
                    snapshot,
                    data=download.data,
                    artifact_id=download.record.id,
                    filename=download.record.original_filename,
                    provider=QwenDocumentProvider(
                        settings,
                        signed_file_source=BrokerSignedFileSource(settings),
                    ),
                )
                model_version = settings.ai_document_ocr_model
            except QwenDocumentError as exc:
                payload = snapshot.model_dump(mode="json")
                payload["warnings"] = [
                    *payload["warnings"],
                    f"云 OCR 未完成（{exc.code}），已保留本地结果并进入质量检查。",
                ]
                snapshot = DocumentSnapshot.model_validate(payload)
        else:
            payload = snapshot.model_dump(mode="json")
            payload["warnings"] = [
                *payload["warnings"],
                f"云 OCR 未就绪（{status.reason_code}），已保留本地结果并进入质量检查。",
            ]
            snapshot = DocumentSnapshot.model_validate(payload)
    if arguments.job_type == DocumentJobType.PDF_TRANSLATION:
        try:
            snapshot = translate_snapshot(
                snapshot,
                settings=settings,
                requested_direction=arguments.options.translation_direction,
                protected_tokens=arguments.options.protected_tokens,
            )
            model_version = "local-ctranslate2"
        except PdfTranslationError as exc:
            raise ArtifactInvalidError(
                str(exc), code="DOCUMENT_TRANSLATION_FAILED"
            ) from exc
    artifact = create_metadata_artifact(
        db,
        parent=download.record,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        operation_id=arguments.operation_id,
        kind="document-snapshot",
        revision=snapshot.revision,
        value=snapshot,
        storage=_storage(),
        scanner=_scanner(),
        settings=settings,
        parser_version=PARSER_VERSION,
        model_version=model_version,
    )
    return _metadata_result(
        stage="EXTRACT",
        arguments=arguments,
        source=download.record,
        artifact=artifact,
        replay=False,
        metrics=DocumentStudioToolMetrics(
            page_count=snapshot.page_count,
            table_count=sum(len(page.tables) for page in snapshot.pages),
            text_page_count=sum(bool(page.blocks) for page in snapshot.pages),
            ocr_page_count=sum(
                page.extraction_route.value != "NATIVE" for page in snapshot.pages
            ),
            cloud_page_count=sum(
                page.extraction_route.value == "QWEN_OCR" for page in snapshot.pages
            ),
        ),
    )


def reconcile_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    db, download = _source_download(context, arguments)
    snapshot_id = task_step_result_artifact_id(
        db, task_id=context.task_id, step_key="extract_document"
    )
    if snapshot_id is None:
        raise ArtifactIntegrityError("文档 Task 缺少可核对的 Snapshot。")
    artifact, snapshot = load_metadata_artifact(
        db,
        artifact_id=snapshot_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        storage=_storage(),
        model=DocumentSnapshot,
    )
    if (
        snapshot.source_artifact_id != download.record.id
        or snapshot.source_sha256 != download.record.sha256
    ):
        raise ArtifactIntegrityError("文档 Snapshot 与源 Artifact 不一致。")
    replay = True
    if (
        arguments.processing_mode == DocumentProcessingMode.AI_ENHANCED
        and arguments.job_type == DocumentJobType.PDF_TO_EXCEL
        and reconcile_provider_available(settings)
    ):
        try:
            result = QwenReconcileProvider(settings).reconcile(snapshot)
            reconciled = apply_reconcile_result(snapshot, result)
            if reconciled.revision != snapshot.revision:
                artifact = create_metadata_artifact(
                    db,
                    parent=download.record,
                    user=context.user,
                    allowed_factory_ids=_allowed_factories(),
                    operation_id=arguments.operation_id,
                    kind="document-snapshot",
                    revision=reconciled.revision,
                    value=reconciled,
                    storage=_storage(),
                    scanner=_scanner(),
                    settings=settings,
                    parser_version="document-studio-reconcile-v1",
                    model_version=settings.ai_document_reconcile_model,
                )
                snapshot = reconciled
                replay = False
        except QwenReconcileError as exc:
            payload = snapshot.model_dump(mode="json")
            payload["warnings"] = [
                *payload["warnings"],
                f"结构化对齐未完成（{exc.code}），已保留提取结果并进入质量检查。",
            ]
            snapshot = DocumentSnapshot.model_validate(payload)
            artifact = create_metadata_artifact(
                db,
                parent=download.record,
                user=context.user,
                allowed_factory_ids=_allowed_factories(),
                operation_id=arguments.operation_id,
                kind="document-snapshot",
                revision=snapshot.revision + 1,
                value=snapshot.model_copy(update={"revision": snapshot.revision + 1}),
                storage=_storage(),
                scanner=_scanner(),
                settings=settings,
                parser_version="document-studio-reconcile-v1",
                model_version=settings.ai_document_reconcile_model,
            )
            snapshot = snapshot.model_copy(update={"revision": snapshot.revision + 1})
            replay = False
    return _metadata_result(
        stage="RECONCILE",
        arguments=arguments,
        source=download.record,
        artifact=artifact,
        replay=replay,
        metrics=DocumentStudioToolMetrics(
            page_count=snapshot.page_count,
            table_count=sum(len(page.tables) for page in snapshot.pages),
        ),
    )


def review_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    db, download = _source_download(context, arguments)
    snapshot_id = _current_snapshot_artifact_id(db, task_id=context.task_id)
    if snapshot_id is None:
        raise ArtifactIntegrityError("文档 Task 缺少可复核的 Snapshot。")
    _, snapshot = load_metadata_artifact(
        db,
        artifact_id=snapshot_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        storage=_storage(),
        model=DocumentSnapshot,
    )
    report = build_quality_report(
        snapshot,
        review_threshold=arguments.options.review_threshold,
    )
    quality_id = metadata_artifact_id(
        user_id=context.user.id,
        operation_id=arguments.operation_id,
        kind="document-quality",
        revision=snapshot.revision,
    )
    replay = db.get(AIArtifact, quality_id) is not None
    quality_artifact = create_metadata_artifact(
        db,
        parent=download.record,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
        operation_id=arguments.operation_id,
        kind="document-quality",
        revision=snapshot.revision,
        value=report,
        storage=_storage(),
        scanner=_scanner(),
        settings=settings,
        parser_version=PARSER_VERSION,
    )
    return _metadata_result(
        stage="REVIEW",
        arguments=arguments,
        source=download.record,
        artifact=quality_artifact,
        replay=replay,
        review_required=report.review_required,
        metrics=DocumentStudioToolMetrics(
            page_count=report.page_count,
            table_count=report.table_count,
            text_page_count=report.native_text_page_count,
            ocr_page_count=report.ocr_page_count,
        ),
    )


def _result_lineage(arguments: DocumentStudioTaskOptions) -> tuple[str, str]:
    if arguments.job_type == DocumentJobType.PDF_TRANSLATION:
        return "document-studio-pdf-translation-v1", "local-ctranslate2"
    if arguments.job_type == DocumentJobType.WORD_TO_PDF:
        return "document-studio-office-render-v1", "libreoffice"
    return PARSER_VERSION, MODEL_VERSION


def _existing_result(
    context: ToolExecutionContext,
    *,
    artifact_id: str,
    source: AIArtifact,
    arguments: DocumentStudioTaskOptions,
) -> AIArtifact | None:
    db = _db(context)
    if db.get(AIArtifact, artifact_id) is None:
        return None
    result = get_owned_artifact(
        db,
        artifact_id=artifact_id,
        user=context.user,
        allowed_factory_ids=_allowed_factories(),
    )
    if (
        result.parent_artifact_id != source.id
        or result.derivation_type != ArtifactDerivationType.OTHER_DERIVED.value
        or result.classification != source.classification
        or result.parser_version != _result_lineage(arguments)[0]
        or result.model_version != _result_lineage(arguments)[1]
    ):
        raise ArtifactIntegrityError("文档 Task 派生结果与幂等契约不一致。")
    return result


def render_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    db, download = _source_download(context, arguments)
    source = download.record
    result_id = _result_id(context, arguments)
    existing = _existing_result(
        context,
        artifact_id=result_id,
        source=source,
        arguments=arguments,
    )
    if existing is not None:
        return _result(
            stage="RENDER",
            arguments=arguments,
            source=source,
            result=existing,
            replay=True,
        )

    metrics = DocumentStudioToolMetrics()
    if arguments.job_type == DocumentJobType.PDF_TO_EXCEL:
        snapshot_id = _current_snapshot_artifact_id(db, task_id=context.task_id)
        if snapshot_id is None:
            raise ArtifactIntegrityError("PDF 转 Excel 任务缺少已复核 Snapshot。")
        _, snapshot = load_metadata_artifact(
            db,
            artifact_id=snapshot_id,
            user=context.user,
            allowed_factory_ids=_allowed_factories(),
            storage=_storage(),
            model=DocumentSnapshot,
        )
        converted = convert_pdf_to_evidence_workbook(
            download.data,
            source.original_filename,
            snapshot=snapshot,
            options=arguments.options,
        )
        filename = converted.output_file_name
        mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        content = converted.content
        metrics = DocumentStudioToolMetrics(
            page_count=converted.page_count,
            table_count=converted.table_count,
            text_page_count=converted.text_page_count,
            ocr_page_count=converted.ocr_page_count,
        )
    elif arguments.job_type == DocumentJobType.PDF_TO_WORD:
        converted = convert_pdf_to_word(
            download.data,
            source.original_filename,
            mode=arguments.options.word_mode,
        )
        filename = converted.output_file_name
        mime_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        content = converted.content
        metrics = DocumentStudioToolMetrics(
            page_count=converted.page_count,
            table_count=converted.table_count,
            text_page_count=converted.text_page_count,
            ocr_page_count=converted.ocr_page_count,
            image_count=converted.image_count,
        )
    elif arguments.job_type == DocumentJobType.PDF_SPLIT:
        converted = split_pdf(
            download.data,
            source.original_filename,
            mode=arguments.options.split_mode,
            page_ranges=arguments.options.split_page_ranges,
        )
        filename = converted.output_file_name
        mime_type = "application/zip"
        content = converted.content
        metrics = DocumentStudioToolMetrics(
            page_count=converted.page_count,
            file_count=converted.file_count,
        )
    elif arguments.job_type == DocumentJobType.PDF_TRANSLATION:
        snapshot_id = _current_snapshot_artifact_id(db, task_id=context.task_id)
        if snapshot_id is None:
            raise ArtifactIntegrityError("PDF 翻译任务缺少已复核 Snapshot。")
        _, snapshot = load_metadata_artifact(
            db,
            artifact_id=snapshot_id,
            user=context.user,
            allowed_factory_ids=_allowed_factories(),
            storage=_storage(),
            model=DocumentSnapshot,
        )
        content, filename, mime_type = render_pdf_translation(
            source_pdf=download.data,
            snapshot=snapshot,
            source_filename=source.original_filename,
            layout=arguments.options.translation_layout,
            include_editable_docx=arguments.options.include_editable_docx,
        )
        metrics = DocumentStudioToolMetrics(
            page_count=snapshot.page_count,
            text_page_count=sum(bool(page.blocks) for page in snapshot.pages),
        )
    elif arguments.job_type == DocumentJobType.WORD_TO_PDF:
        if not _office_renderer_available():
            raise ArtifactInvalidError(
                "Word 转 PDF 隔离渲染器未开放。",
                code="DOCUMENT_OFFICE_RENDERER_UNAVAILABLE",
            )
        try:
            converted = convert_word_to_pdf(
                download.data,
                source.original_filename,
                settings=settings,
            )
        except OfficePdfRenderError as exc:
            raise ArtifactInvalidError(str(exc), code=exc.code) from exc
        filename = converted.output_file_name
        mime_type = "application/pdf"
        content = converted.content
        metrics = DocumentStudioToolMetrics(
            page_count=converted.page_count,
            blank_page_count=converted.blank_page_count,
        )
    else:
        raise ArtifactInvalidError(
            "当前文档 Task 尚未接入确定性渲染器。",
            code="DOCUMENT_JOB_RENDERER_UNAVAILABLE",
        )

    derived = create_derived_artifact(
        db,
        parent_artifact_id=source.id,
        user=context.user,
        classification=source.classification,
        derivation_type=ArtifactDerivationType.OTHER_DERIVED,
        filename=filename,
        declared_mime_type=mime_type,
        data=content,
        parser_version=_result_lineage(arguments)[0],
        model_version=_result_lineage(arguments)[1],
        storage=_storage(),
        scanner=_scanner(),
        settings=settings,
        allowed_factory_ids=_allowed_factories(),
        artifact_id=result_id,
    )
    return _result(
        stage="RENDER",
        arguments=arguments,
        source=source,
        result=derived,
        replay=False,
        metrics=metrics,
    )


def verify_document_task(
    context: ToolExecutionContext,
    arguments: DocumentStudioTaskOptions,
) -> DocumentStudioToolResult:
    _, download = _source_download(context, arguments)
    result = _existing_result(
        context,
        artifact_id=_result_id(context, arguments),
        source=download.record,
        arguments=arguments,
    )
    if result is None:
        raise ArtifactIntegrityError("文档 Task 缺少可验证的派生结果。")
    return _result(
        stage="VERIFY",
        arguments=arguments,
        source=download.record,
        result=result,
        replay=True,
    )


def serialize_document_tool_result(value: object) -> DocumentStudioToolResult:
    if isinstance(value, DocumentStudioToolResult):
        return value
    return DocumentStudioToolResult.model_validate(value)


def document_studio_tool_specs() -> tuple[ToolSpec, ...]:
    def spec(
        *,
        name: str,
        description: str,
        executor,
        label: str,
        risk: AIToolRiskLevel,
        timeout: float,
    ) -> ToolSpec:
        return ToolSpec(
            name=name,
            description=description,
            input_model=DocumentStudioTaskOptions,
            risk_level=risk,
            executor=executor,
            serializer=serialize_document_tool_result,
            display_label=label,
            tool_group="identity",
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=timeout,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
            version="1.0.0",
        )

    return (
        spec(
            name="artifacts.inspect_document",
            description="重新鉴权源 Artifact 并执行轻量文档预检。",
            executor=inspect_document_task,
            label="正在预检文档",
            risk=AIToolRiskLevel.READ_ONLY,
            timeout=90,
        ),
        spec(
            name="artifacts.extract_document",
            description="锁定确定性文档提取阶段及不可变输入。",
            executor=extract_document_task,
            label="正在提取文档",
            risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            timeout=90,
        ),
        spec(
            name="artifacts.reconcile_document",
            description="核对文档提取输入与任务契约。",
            executor=reconcile_document_task,
            label="正在核对文档结构",
            risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            timeout=90,
        ),
        spec(
            name="artifacts.review_document",
            description="确认确定性管线没有待人工复核项。",
            executor=review_document_task,
            label="正在检查复核项",
            risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            timeout=90,
        ),
        spec(
            name="artifacts.render_document",
            description="调用现有确定性转换器并生成不可变派生 Artifact。",
            executor=render_document_task,
            label="正在生成文档结果",
            risk=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            timeout=600,
        ),
        spec(
            name="artifacts.verify_document",
            description="重新鉴权并验证文档派生结果的谱系和完整性。",
            executor=verify_document_task,
            label="正在验证文档结果",
            risk=AIToolRiskLevel.READ_ONLY,
            timeout=90,
        ),
    )
