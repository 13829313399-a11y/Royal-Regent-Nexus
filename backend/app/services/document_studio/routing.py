from __future__ import annotations

from app.schemas.ai.task import AITaskState
from app.services.document_studio.contracts import (
    DocumentJobState,
    DocumentJobType,
    DocumentProcessingMode,
    DocumentRouteDecision,
)

DOCUMENT_STUDIO_PRIMARY_SKILLS: dict[DocumentJobType, str] = {
    DocumentJobType.PDF_TO_EXCEL: "files.pdf_to_excel",
    DocumentJobType.PDF_TO_WORD: "files.pdf_to_word",
    DocumentJobType.WORD_TO_PDF: "files.word_to_pdf",
    DocumentJobType.PDF_TRANSLATION: "files.pdf_translation",
    DocumentJobType.PDF_SPLIT: "files.pdf_split",
}

DETERMINISTIC_DOCUMENT_JOB_TYPES = frozenset(
    {
        DocumentJobType.PDF_TO_EXCEL,
        DocumentJobType.PDF_TO_WORD,
        DocumentJobType.PDF_SPLIT,
    }
)


def available_document_job_types(
    *,
    local_translation_available: bool,
    office_renderer_available: bool,
) -> frozenset[DocumentJobType]:
    available = set(DETERMINISTIC_DOCUMENT_JOB_TYPES)
    if local_translation_available:
        available.add(DocumentJobType.PDF_TRANSLATION)
    if office_renderer_available:
        available.add(DocumentJobType.WORD_TO_PDF)
    return frozenset(available)

DOCUMENT_STUDIO_TOOL_NAMES = (
    "artifacts.inspect_document",
    "artifacts.extract_document",
    "artifacts.reconcile_document",
    "artifacts.review_document",
    "artifacts.render_document",
    "artifacts.verify_document",
)

_TASK_STATE_MAP: dict[AITaskState, DocumentJobState] = {
    AITaskState.CREATED: DocumentJobState.READY,
    AITaskState.UNDERSTOOD: DocumentJobState.READY,
    AITaskState.PLANNED: DocumentJobState.READY,
    AITaskState.RUNNING: DocumentJobState.RUNNING,
    AITaskState.WAITING_INPUT: DocumentJobState.REVIEW_REQUIRED,
    AITaskState.WAITING_APPROVAL: DocumentJobState.REVIEW_REQUIRED,
    AITaskState.VERIFYING: DocumentJobState.VERIFYING,
    AITaskState.COMPLETED: DocumentJobState.COMPLETED,
    AITaskState.CANCELLING: DocumentJobState.RUNNING,
    AITaskState.CANCELLED: DocumentJobState.CANCELLED,
    AITaskState.FAILED: DocumentJobState.FAILED,
    AITaskState.RETRY_PENDING: DocumentJobState.RUNNING,
}


def map_task_state(value: str | AITaskState) -> DocumentJobState:
    return _TASK_STATE_MAP[AITaskState(value)]


def route_document_job(
    *,
    job_type: DocumentJobType,
    processing_mode: DocumentProcessingMode,
    page_count: int,
    task_runtime_available: bool,
    cloud_ocr_available: bool,
    local_translation_available: bool,
    office_renderer_available: bool,
) -> tuple[DocumentRouteDecision, tuple[str, ...]]:
    warnings: list[str] = []
    if job_type == DocumentJobType.WORD_TO_PDF:
        if office_renderer_available and task_runtime_available:
            return DocumentRouteDecision.TASK_LOCAL, ()
        return (
            DocumentRouteDecision.UNSUPPORTED,
            ("Word 转 PDF 的受限 Office 渲染器尚未开放。",),
        )
    if job_type == DocumentJobType.PDF_TRANSLATION:
        if not local_translation_available:
            return (
                DocumentRouteDecision.UNSUPPORTED,
                ("PDF 翻译所需的离线中英模型尚未就绪。",),
            )
        if not task_runtime_available:
            return (
                DocumentRouteDecision.UNSUPPORTED,
                ("PDF 翻译只在 Document Job 运行时中执行。",),
            )
        if processing_mode == DocumentProcessingMode.AI_ENHANCED:
            if cloud_ocr_available:
                return DocumentRouteDecision.TASK_AI_ENHANCED, ()
            warnings.append("云端 OCR 未开放，将使用本地提取与离线翻译。")
        return DocumentRouteDecision.TASK_LOCAL, tuple(warnings)
    if job_type not in DETERMINISTIC_DOCUMENT_JOB_TYPES:
        return DocumentRouteDecision.UNSUPPORTED, ("当前文档任务类型不受支持。",)
    if page_count > 80:
        return (
            DocumentRouteDecision.UNSUPPORTED,
            ("现有确定性 PDF 工具单次最多处理 80 页。",),
        )
    if processing_mode == DocumentProcessingMode.AI_ENHANCED and not cloud_ocr_available:
        warnings.append("AI 增强未开放，本次将保持本地确定性处理。")
    if task_runtime_available:
        if (
            processing_mode == DocumentProcessingMode.AI_ENHANCED
            and cloud_ocr_available
        ):
            return DocumentRouteDecision.TASK_AI_ENHANCED, tuple(warnings)
        return DocumentRouteDecision.TASK_LOCAL, tuple(warnings)
    warnings.append("Document Job 运行时未开放，可回退到现有同步工具。")
    return DocumentRouteDecision.SYNC_LOCAL, tuple(warnings)
