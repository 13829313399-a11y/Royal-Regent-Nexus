from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from app.api import document_jobs as document_jobs_api
from app.core.config import Settings
from app.db import Base
from app.models.ai_action import AIActionConfirmation
from app.models.ai_artifact import AIArtifact
from app.models.ai_conversation import AIConversation, AIMessage
from app.models.ai_task import AITask, AITaskEvent, AITaskStep
from app.models.auth import AuthAuditLog, AuthUser
from app.schemas.ai.task import AITaskState, AITaskStepState
from app.schemas.document_studio import (
    DocumentBlock,
    DocumentCloudConsent,
    DocumentJobCreate,
    DocumentJobOptions,
    DocumentJobReviewRequest,
    DocumentPageRange,
    DocumentPageSnapshot,
    DocumentPreflightRequest,
    DocumentReviewPatch,
    DocumentSnapshot,
    DocumentStudioTaskOptions,
)
from app.services.ai.artifacts.scanner import FakeArtifactScanner
from app.services.ai.artifacts.service import create_artifact
from app.services.ai.artifacts.storage import FakeArtifactStorage
from app.services.ai.artifacts.validation import (
    ArtifactValidationError,
    validate_artifact_upload,
    validate_derived_artifact,
)
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.task_service import transition_step, transition_task
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.ai.tools import document_studio_tools
from app.services.auth import AuthContext, AuthGrantContext
from app.services.document_studio import orchestrator as document_orchestrator
from app.services.document_studio.contracts import (
    DocumentJobType,
    DocumentProcessingMode,
    DocumentRouteDecision,
)
from app.services.document_studio.metadata import (
    create_metadata_artifact,
    load_metadata_artifact,
)
from app.services.document_studio.orchestrator import (
    DocumentJobConflictError,
    cancel_document_job,
    create_document_job,
    document_job_operational_metrics,
    get_document_job,
    list_document_jobs,
    preflight_owned_document,
    retry_document_job,
    review_document_job,
)
from app.services.document_studio.quality import build_quality_report
from app.services.document_studio.routing import (
    DOCUMENT_STUDIO_TOOL_NAMES,
    map_task_state,
    route_document_job,
)
from docx import Document
from fastapi import HTTPException
from pydantic import ValidationError
from pypdf import PdfWriter
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool


def _pdf_bytes(pages: int = 1) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://document-studio-test",
        "ai_enabled": True,
        "ai_pilot_enabled": True,
        "ai_pilot_user_ids": "owner",
        "ai_pilot_factory_ids": "huaxing",
        "ai_nif_runtime_enabled": True,
        "ai_skill_router_enabled": True,
        "ai_evidence_v1_enabled": True,
        "ai_tasks_enabled": True,
        "ai_task_worker_enabled": True,
        "ai_artifacts_enabled": True,
        "ai_artifact_workflows_enabled": True,
        "ai_document_studio_enabled": True,
        "ai_artifact_scanner_backend": "clamav",
    }
    values.update(overrides)
    return Settings(**values)


def _user() -> AuthContext:
    return AuthContext(
        id="owner",
        username="owner",
        display_name="owner",
        roles=("Document Studio Test",),
        role_codes=("document-studio-test",),
        permissions=frozenset(),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(
            AuthGrantContext(
                role_id="role-owner-huaxing",
                role_name="Document Studio Test",
                factory_id="huaxing",
                department="production",
                permissions=frozenset(),
                binding_id="binding-owner-huaxing",
            ),
        ),
    )


def _database() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            AuthUser.__table__,
            AuthAuditLog.__table__,
            AIActionConfirmation.__table__,
            AIConversation.__table__,
            AIMessage.__table__,
            AIArtifact.__table__,
            AITask.__table__,
            AITaskStep.__table__,
            AITaskEvent.__table__,
        ],
    )
    db = Session(engine)
    db.add(
        AuthUser(
            id="owner",
            username="owner",
            display_name="owner",
            password_salt="salt",
            password_hash="hash",
            status="active",
            force_password_change=0,
            avatar_png=None,
            avatar_version="",
            last_login_at="",
            created_at="2026-08-14T09:00:00+08:00",
            updated_at="2026-08-14T09:00:00+08:00",
        )
    )
    db.commit()
    return db


def _source(db: Session, storage: FakeArtifactStorage, settings: Settings):
    return create_artifact(
        db,
        user=_user(),
        factory_id="huaxing",
        classification="CONFIDENTIAL_BUSINESS",
        filename="订单.pdf",
        declared_mime_type="application/pdf",
        data=_pdf_bytes(),
        storage=storage,
        scanner=FakeArtifactScanner(),
        settings=settings,
        allowed_factory_ids=frozenset({"huaxing"}),
    )


def _docx_source(db: Session, storage: FakeArtifactStorage, settings: Settings):
    output = BytesIO()
    document = Document()
    document.add_paragraph("Word 转 PDF")
    document.save(output)
    return create_artifact(
        db,
        user=_user(),
        factory_id="huaxing",
        classification="CONFIDENTIAL_BUSINESS",
        filename="订单.docx",
        declared_mime_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        data=output.getvalue(),
        storage=storage,
        scanner=FakeArtifactScanner(),
        settings=settings,
        allowed_factory_ids=frozenset({"huaxing"}),
    )


def test_document_routing_maps_existing_tools_without_parallel_states() -> None:
    route, warnings = route_document_job(
        job_type=DocumentJobType.PDF_TO_EXCEL,
        processing_mode=DocumentProcessingMode.AI_ENHANCED,
        page_count=12,
        task_runtime_available=True,
        cloud_ocr_available=False,
        local_translation_available=False,
        office_renderer_available=False,
    )
    assert route == DocumentRouteDecision.TASK_LOCAL
    assert warnings == ("AI 增强未开放，本次将保持本地确定性处理。",)
    assert map_task_state("WAITING_INPUT").value == "REVIEW_REQUIRED"
    assert map_task_state("RETRY_PENDING").value == "RUNNING"

    translation_route, _ = route_document_job(
        job_type=DocumentJobType.PDF_TRANSLATION,
        processing_mode=DocumentProcessingMode.LOCAL_PRIVATE,
        page_count=12,
        task_runtime_available=True,
        cloud_ocr_available=False,
        local_translation_available=True,
        office_renderer_available=False,
    )
    office_route, _ = route_document_job(
        job_type=DocumentJobType.WORD_TO_PDF,
        processing_mode=DocumentProcessingMode.LOCAL_PRIVATE,
        page_count=1,
        task_runtime_available=True,
        cloud_ocr_available=False,
        local_translation_available=False,
        office_renderer_available=True,
    )
    assert translation_route == DocumentRouteDecision.TASK_LOCAL
    assert office_route == DocumentRouteDecision.TASK_LOCAL


def test_document_job_flag_off_capability_fails_closed_without_500(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(document_jobs_api, "settings", Settings(_env_file=None))

    capabilities = document_jobs_api.get_document_job_capabilities(_user())

    assert capabilities.available is False
    assert capabilities.supported_job_types == ()
    with pytest.raises(HTTPException) as captured:
        document_jobs_api._require_document_jobs(_user())
    assert captured.value.status_code == 404


def test_preflight_reauthorizes_artifact_hash_factory_and_page_count() -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    source = _source(db, storage, settings)

    result = preflight_owned_document(
        db,
        payload=DocumentPreflightRequest(
            factory_id="huaxing",
            source_artifact_id=source.id,
            job_type="PDF_TO_EXCEL",
            processing_mode="LOCAL_PRIVATE",
        ),
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
    )

    assert result.source_sha256 == source.sha256
    assert result.page_count == 1
    assert result.scanned_pages == 1
    assert result.route_decision == DocumentRouteDecision.TASK_LOCAL


def test_document_job_creation_reuses_ai_task_idempotency_and_projects_history() -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    source = _source(db, storage, settings)
    registry = build_default_tool_registry(
        artifact_workflows_enabled=True,
        document_studio_enabled=True,
    )
    SkillRegistry(registry).resolve("files.pdf_to_excel", "1.0.0")
    assert all(registry.resolve(name) is not None for name in DOCUMENT_STUDIO_TOOL_NAMES)

    payload = DocumentJobCreate(
        operation_id="docop-" + "a" * 32,
        idempotency_key="docop-" + "a" * 32,
        factory_id="huaxing",
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        job_type="PDF_TO_EXCEL",
        processing_mode="LOCAL_PRIVATE",
        page_range=DocumentPageRange(),
        options=DocumentJobOptions(),
    )
    first = create_document_job(
        db,
        payload=payload,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
        request_id="request-document-job-1",
        registry=registry,
    )
    replay = create_document_job(
        db,
        payload=payload,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
        request_id="request-document-job-2",
        registry=registry,
    )

    assert replay.task_id == first.task_id
    assert first.state.value == "READY"
    assert db.query(AITask).count() == 1
    assert db.query(AITaskStep).count() == 6
    history = list_document_jobs(
        db,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        factory_id="huaxing",
        limit=20,
    )
    assert [item.task_id for item in history.items] == [first.task_id]
    metrics = document_job_operational_metrics(
        db,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        factory_id="huaxing",
        storage=storage,
    )
    assert metrics.total_jobs == 1
    assert metrics.active_jobs == 1
    assert metrics.cloud_page_count == 0

    task = db.get(AITask, first.task_id)
    assert task is not None
    cancel_document_job(
        db,
        task=task,
        user=_user(),
        expected_revision=1,
        reason_code="USER_CANCELLED",
        settings=settings,
    )
    assert task.state == "CANCELLING"

    changed = payload.model_copy(update={"source_sha256": "0" * 64})
    with pytest.raises(DocumentJobConflictError):
        create_document_job(
            db,
            payload=changed,
            user=_user(),
            allowed_factory_ids=frozenset({"huaxing"}),
            storage=storage,
            settings=settings,
            request_id="request-document-job-3",
            registry=registry,
        )


def test_pdf_zip_is_only_allowed_as_a_validated_derived_artifact() -> None:
    archive = BytesIO()
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as output:
        output.writestr("订单_第1页.pdf", _pdf_bytes())
    data = archive.getvalue()

    derived = validate_derived_artifact(
        filename="订单_拆分结果.zip",
        declared_mime_type="application/zip",
        data=data,
    )
    assert derived.normalized_extension == ".zip"
    assert derived.content_class.value == "DOCUMENT"

    with pytest.raises(ArtifactValidationError):
        validate_artifact_upload(
            filename="订单_拆分结果.zip",
            declared_mime_type="application/zip",
            data=data,
        )
    malicious = BytesIO()
    with ZipFile(malicious, "w", compression=ZIP_DEFLATED) as output:
        output.writestr("../escape.pdf", _pdf_bytes())
    with pytest.raises(ArtifactValidationError):
        validate_derived_artifact(
            filename="bad.zip",
            declared_mime_type="application/zip",
            data=malicious.getvalue(),
        )


def test_expired_source_projects_an_expired_job_without_restoring_download_access() -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    source = _source(db, storage, settings)
    detail = create_document_job(
        db,
        payload=DocumentJobCreate(
            operation_id="docop-" + "1" * 32,
            idempotency_key="docop-" + "1" * 32,
            factory_id="huaxing",
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            job_type="PDF_TO_WORD",
            processing_mode="LOCAL_PRIVATE",
        ),
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
        request_id="request-document-expired",
        registry=build_default_tool_registry(
            artifact_workflows_enabled=True,
            document_studio_enabled=True,
        ),
    )
    source.status = "EXPIRED"
    db.commit()

    expired = get_document_job(
        db,
        task_id=detail.task_id or "",
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
    )

    assert expired.state.value == "EXPIRED"
    assert expired.result_artifact_id is None


def test_failed_document_job_retries_only_idempotent_failed_steps() -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    source = _source(db, storage, settings)
    registry = build_default_tool_registry(
        artifact_workflows_enabled=True,
        document_studio_enabled=True,
    )
    detail = create_document_job(
        db,
        payload=DocumentJobCreate(
            operation_id="docop-" + "f" * 32,
            idempotency_key="docop-" + "f" * 32,
            factory_id="huaxing",
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            job_type="PDF_TO_EXCEL",
            processing_mode="LOCAL_PRIVATE",
        ),
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
        request_id="request-document-retry",
        registry=registry,
    )
    task = db.get(AITask, detail.task_id)
    assert task is not None
    step = (
        db.query(AITaskStep)
        .filter(AITaskStep.task_id == task.id)
        .order_by(AITaskStep.ordinal)
        .first()
    )
    assert step is not None
    transition_task(
        db,
        task=task,
        requested_state=AITaskState.UNDERSTOOD,
        actor_type="SYSTEM",
        reason_code="TEST_UNDERSTOOD",
        settings=settings,
    )
    transition_task(
        db,
        task=task,
        requested_state=AITaskState.RUNNING,
        actor_type="SYSTEM",
        reason_code="TEST_RUNNING",
        settings=settings,
    )
    transition_step(
        db,
        task=task,
        step=step,
        requested_state=AITaskStepState.RUNNING,
        actor_type="SYSTEM",
        reason_code="TEST_STEP_RUNNING",
    )
    transition_step(
        db,
        task=task,
        step=step,
        requested_state=AITaskStepState.FAILED,
        actor_type="SYSTEM",
        reason_code="TEST_STEP_FAILED",
        failure_code="TASK_TEST_FAILURE",
    )
    transition_task(
        db,
        task=task,
        requested_state=AITaskState.FAILED,
        actor_type="SYSTEM",
        reason_code="TEST_TASK_FAILED",
        failure_code="TASK_TEST_FAILURE",
        settings=settings,
    )
    db.commit()

    retry_document_job(
        db,
        task=task,
        user=_user(),
        expected_revision=task.revision,
        settings=settings,
    )

    assert task.state == "RETRY_PENDING"
    assert step.state == "RETRY_PENDING"


def test_pdf_split_adapter_creates_one_replay_safe_derived_artifact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    source = _source(db, storage, settings)
    source_bytes = storage.read(source.storage_key)
    monkeypatch.setattr(document_studio_tools, "settings", settings)
    monkeypatch.setattr(document_studio_tools, "_storage", lambda: storage)
    monkeypatch.setattr(document_studio_tools, "_scanner", lambda: scanner)
    arguments = DocumentStudioTaskOptions(
        operation_id="docop-" + "e" * 32,
        factory_id="huaxing",
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        job_type="PDF_SPLIT",
        processing_mode="LOCAL_PRIVATE",
        page_range=DocumentPageRange(),
        options=DocumentJobOptions(),
    )
    context = ToolExecutionContext(
        db=db,
        user=_user(),
        request_id="document-render-test",
    )

    first = document_studio_tools.render_document_task(context, arguments)
    replay = document_studio_tools.render_document_task(context, arguments)
    verified = document_studio_tools.verify_document_task(context, arguments)

    assert first.result_artifact_id != source.id
    assert first.idempotent_replay is False
    assert replay.result_artifact_id == first.result_artifact_id
    assert replay.idempotent_replay is True
    assert verified.result_artifact_id == first.result_artifact_id
    assert storage.read(source.storage_key) == source_bytes
    derived = db.get(AIArtifact, first.result_artifact_id)
    assert derived is not None
    assert derived.parent_artifact_id == source.id
    assert derived.normalized_extension == ".zip"
    assert db.query(AIArtifact).count() == 2


@pytest.mark.parametrize("job_type", ["PDF_TO_WORD", "PDF_SPLIT", "WORD_TO_PDF"])
def test_non_content_document_jobs_skip_unneeded_extraction_and_review(
    monkeypatch: pytest.MonkeyPatch,
    job_type: str,
) -> None:
    settings = _settings(ai_document_cloud_ocr_enabled=True)
    db = _database()
    storage = FakeArtifactStorage()
    source = (
        _docx_source(db, storage, settings)
        if job_type == "WORD_TO_PDF"
        else _source(db, storage, settings)
    )
    monkeypatch.setattr(document_studio_tools, "settings", settings)
    monkeypatch.setattr(document_studio_tools, "_storage", lambda: storage)
    monkeypatch.setattr(document_studio_tools, "_scanner", FakeArtifactScanner)
    monkeypatch.setattr(
        document_studio_tools,
        "extract_local_snapshot",
        lambda **_kwargs: pytest.fail("content extraction must be skipped"),
    )
    arguments = DocumentStudioTaskOptions(
        operation_id="docop-" + "7" * 32,
        factory_id="huaxing",
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        job_type=job_type,
        processing_mode="AI_ENHANCED",
        page_range=DocumentPageRange(),
        options=DocumentJobOptions(),
    )
    context = ToolExecutionContext(
        db=db,
        user=_user(),
        request_id="document-pass-through-test",
    )

    extracted = document_studio_tools.extract_document_task(context, arguments)
    reconciled = document_studio_tools.reconcile_document_task(context, arguments)
    reviewed = document_studio_tools.review_document_task(context, arguments)

    assert [extracted.stage, reconciled.stage, reviewed.stage] == [
        "EXTRACT",
        "RECONCILE",
        "REVIEW",
    ]
    assert extracted.result_artifact_id == source.id
    assert reconciled.result_artifact_id == source.id
    assert reviewed.result_artifact_id == source.id
    assert reviewed.review_required is False


def test_ai_enhanced_extraction_falls_back_when_signed_source_scheme_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        ai_document_cloud_ocr_enabled=True,
        ai_region="cn-beijing",
        ai_workspace_id="workspace-test",
        dashscope_api_key="test-secret",
        ai_document_signed_file_service_url="ftp://document-broker",
        ai_document_signed_file_service_token="broker-secret",
        ai_document_signed_file_allowed_hosts="lease.example.test",
    )
    db = _database()
    storage = FakeArtifactStorage()
    source = _source(db, storage, settings)
    snapshot = DocumentSnapshot(
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        page_count=1,
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=595,
                height=842,
                extraction_route="LOCAL_OCR",
                blocks=(
                    DocumentBlock(
                        block_id="p1-b1",
                        kind="PARAGRAPH",
                        bbox=(10, 10, 200, 40),
                        raw_text="订单 0012",
                        normalized_text="订单 0012",
                        confidence=0.8,
                        source="LOCAL_OCR",
                        needs_review=True,
                    ),
                ),
            ),
        ),
    )
    monkeypatch.setattr(document_studio_tools, "settings", settings)
    monkeypatch.setattr(document_studio_tools, "_storage", lambda: storage)
    monkeypatch.setattr(document_studio_tools, "_scanner", FakeArtifactScanner)
    monkeypatch.setattr(
        document_studio_tools,
        "extract_local_snapshot",
        lambda **_kwargs: snapshot,
    )
    arguments = DocumentStudioTaskOptions(
        operation_id="docop-" + "6" * 32,
        factory_id="huaxing",
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        job_type="PDF_TO_EXCEL",
        processing_mode="AI_ENHANCED",
        page_range=DocumentPageRange(),
        options=DocumentJobOptions(),
        cloud_consent=DocumentCloudConsent(
            accepted=True,
            provider="qwen",
            region="cn-beijing",
            purpose="DOCUMENT_PARSE",
            notice_version="document-cloud-v1",
        ),
    )
    context = ToolExecutionContext(
        db=db,
        user=_user(),
        request_id="document-local-fallback-test",
    )

    result = document_studio_tools.extract_document_task(context, arguments)
    _, stored_snapshot = load_metadata_artifact(
        db,
        artifact_id=result.result_artifact_id,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        model=DocumentSnapshot,
    )

    assert result.stage == "EXTRACT"
    assert result.model_version == "none"
    assert stored_snapshot.pages[0].extraction_route.value == "LOCAL_OCR"
    assert stored_snapshot.warnings == (
        "云 OCR 未就绪（DOCUMENT_SIGNED_SOURCE_INVALID），已使用本地结果继续处理。",
    )


def test_document_job_request_contract_rejects_open_or_inconsistent_options() -> None:
    with pytest.raises(ValidationError):
        DocumentJobOptions(split_mode="ranges", split_page_ranges="")
    with pytest.raises(ValidationError):
        DocumentJobCreate.model_validate(
            {
                "operation_id": "docop-" + "a" * 32,
                "idempotency_key": "docop-" + "a" * 32,
                "factory_id": "huaxing",
                "source_artifact_id": "aiart-" + "a" * 32,
                "source_sha256": "b" * 64,
                "job_type": "PDF_TO_EXCEL",
                "processing_mode": "LOCAL_PRIVATE",
                "unknown": True,
            }
        )

    enhanced_without_cloud_consent = DocumentJobCreate(
        operation_id="docop-" + "b" * 32,
        idempotency_key="docop-" + "b" * 32,
        factory_id="huaxing",
        source_artifact_id="aiart-" + "a" * 32,
        source_sha256="b" * 64,
        job_type="PDF_SPLIT",
        processing_mode="AI_ENHANCED",
    )
    assert enhanced_without_cloud_consent.cloud_consent is None


def test_review_patch_rebinds_snapshot_and_resumes_the_same_task() -> None:
    settings = _settings()
    db = _database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    source = _source(db, storage, settings)
    operation_id = "docop-" + "9" * 32
    detail = create_document_job(
        db,
        payload=DocumentJobCreate(
            operation_id=operation_id,
            idempotency_key=operation_id,
            factory_id="huaxing",
            source_artifact_id=source.id,
            source_sha256=source.sha256,
            job_type="PDF_TO_EXCEL",
            processing_mode="LOCAL_PRIVATE",
        ),
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=settings,
        request_id="document-review-test",
        registry=build_default_tool_registry(
            artifact_workflows_enabled=True,
            document_studio_enabled=True,
        ),
    )
    task = db.get(AITask, detail.task_id)
    assert task is not None
    snapshot = DocumentSnapshot(
        source_artifact_id=source.id,
        source_sha256=source.sha256,
        page_count=1,
        pages=(
            DocumentPageSnapshot(
                page_number=1,
                width=595,
                height=842,
                extraction_route="LOCAL_OCR",
                blocks=(
                    DocumentBlock(
                        block_id="p1-b1",
                        kind="PARAGRAPH",
                        bbox=(10, 10, 200, 40),
                        raw_text="O012",
                        normalized_text="0012",
                        confidence=0.7,
                        source="LOCAL_OCR",
                        needs_review=True,
                    ),
                ),
            ),
        ),
    )
    report = build_quality_report(snapshot, review_threshold=0.85)
    snapshot_artifact = create_metadata_artifact(
        db,
        parent=source,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        operation_id=operation_id,
        kind="document-snapshot",
        revision=1,
        value=snapshot,
        storage=storage,
        scanner=scanner,
        settings=settings,
        parser_version="test",
    )
    quality_artifact = create_metadata_artifact(
        db,
        parent=source,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        operation_id=operation_id,
        kind="document-quality",
        revision=1,
        value=report,
        storage=storage,
        scanner=scanner,
        settings=settings,
        parser_version="test",
    )
    reconcile_step = db.query(AITaskStep).filter_by(
        task_id=task.id,
        step_key="reconcile_document",
    ).one()
    review_step = db.query(AITaskStep).filter_by(
        task_id=task.id,
        step_key="review_document",
    ).one()
    document_orchestrator._replace_step_result_artifact(
        reconcile_step,
        source=source,
        result=snapshot_artifact,
        review_required=False,
    )
    document_orchestrator._replace_step_result_artifact(
        review_step,
        source=source,
        result=quality_artifact,
        review_required=True,
    )
    reconcile_step.state = AITaskStepState.COMPLETED.value
    review_step.state = AITaskStepState.WAITING_INPUT.value
    task.state = AITaskState.WAITING_INPUT.value
    db.commit()
    revision = task.revision

    review_document_job(
        db,
        task=task,
        payload=DocumentJobReviewRequest(
            expected_revision=revision,
            expected_input_hash=task.input_hash,
            expected_runtime_plan_hash=task.runtime_plan_hash,
            patches=(
                DocumentReviewPatch(
                    patch_id="docpatch-" + "8" * 32,
                    operation_id=operation_id,
                    issue_id=report.issues[0].issue_id,
                    action="ACCEPT",
                    expected_snapshot_sha256=report.snapshot_sha256,
                ),
            ),
        ),
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        scanner=scanner,
        settings=settings,
    )

    refreshed = get_document_job(
        db,
        task_id=task.id,
        user=_user(),
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
    )
    assert refreshed.task_id == detail.task_id
    assert refreshed.state.value == "RUNNING"
    assert refreshed.quality_report is not None
    assert refreshed.quality_report.review_required is False
