from __future__ import annotations

import asyncio
import hashlib
from io import BytesIO

import pytest
from app.api import ai as ai_api
from app.schemas.ai.artifact import AIArtifactEgressConsent, AIArtifactReferenceInput
from app.services.ai.artifacts import translation_adapter
from app.services.ai.artifacts.egress import require_artifact_egress_consent
from app.services.ai.artifacts.scanner import FakeArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactInvalidError,
    create_artifact,
    download_artifact,
)
from app.services.ai.artifacts.storage import FakeArtifactStorage
from app.services.ai.artifacts.translation_adapter import (
    TRANSLATION_TERMS_VERSION,
    translate_artifact,
)
from app.services.ai.artifacts.vision_adapter import prepare_vision_artifacts
from app.services.ai.artifacts.workbook_adapter import (
    inspect_workbook_artifact,
    require_matching_snapshot,
)
from app.services.ai.attachment_service import clear_prepared_attachments
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tools import artifact_workflow_tools
from app.services.ai.tools.artifact_workflow_tools import (
    ArtifactTranslateLocalInput,
    translate_document_local_task,
)
from app.services.document_translation import DocumentTranslationResult
from openpyxl import Workbook
from pydantic import ValidationError
from tests.ai_artifact_helpers import (
    artifact_database,
    artifact_settings,
    artifact_user,
    png_bytes,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook_bytes(value: str = "采购订单") -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "订单"
    sheet.append(["订单号", "说明", "数量", "公式"])
    sheet.append(["00123", value, 12, "=C2*2"])
    sheet["A2"].number_format = "00000"
    sheet.column_dimensions["E"].hidden = True
    sheet.merge_cells("A4:B4")
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def workflow_settings():
    return artifact_settings().model_copy(
        update={"ai_artifact_workflows_enabled": True}
    )


def _create_workbook(db, storage, scanner, *, user=None, value="采购订单"):
    return create_artifact(
        db,
        user=user or artifact_user(),
        factory_id="huaxing",
        classification="CONFIDENTIAL_BUSINESS",
        filename="订单.xlsx",
        declared_mime_type=XLSX_MIME,
        data=workbook_bytes(value),
        storage=storage,
        scanner=scanner,
        settings=workflow_settings(),
        allowed_factory_ids=frozenset({"huaxing"}),
    )


def test_workbook_artifact_snapshot_keeps_source_immutable_and_bound_to_sha() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source = _create_workbook(db, storage, scanner, user=user)
    before = storage.read(source.storage_key)

    snapshot, parsed = inspect_workbook_artifact(
        db,
        artifact_id=source.id,
        user=user,
        factory_id="huaxing",
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
    )

    assert storage.read(source.storage_key) == before
    assert snapshot.source_lineage.artifact_id == source.id
    assert snapshot.source_lineage.source_sha256 == source.sha256
    assert parsed.parser_status == "READY"
    assert parsed.parser_version == "workbook-semantic-snapshot-v1"
    assert snapshot.sheets[0].hidden_column_count == 1
    assert snapshot.sheets[0].merged_regions == ["A4:B4"]
    assert "00123" not in snapshot.model_dump_json()

    stale = snapshot.model_copy(update={"snapshot_sha256": "0" * 64})
    with pytest.raises(ArtifactInvalidError) as captured:
        require_matching_snapshot(snapshot, stale)
    assert captured.value.code == "AI_ARTIFACT_SNAPSHOT_STALE"


def test_artifact_egress_consent_is_exact_and_never_inherited_across_content_classes() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    source = _create_workbook(db, storage, scanner)
    valid = AIArtifactEgressConsent(
        accepted=True,
        notice_version="aliyun-cn-beijing-workbook-v1",
        provider="qwen",
        region="cn-beijing",
        classification="CONFIDENTIAL_BUSINESS",
        content_class="WORKBOOK",
        artifact_ids=[source.id],
    )
    require_artifact_egress_consent(valid, [source], content_class="WORKBOOK")

    with pytest.raises(ValidationError):
        AIArtifactEgressConsent.model_validate(
            {
                **valid.model_dump(),
                "notice_version": "aliyun-cn-beijing-image-v1",
            }
        )
    image_consent = AIArtifactEgressConsent(
        accepted=True,
        notice_version="aliyun-cn-beijing-image-v1",
        provider="qwen",
        region="cn-beijing",
        classification="CONFIDENTIAL_BUSINESS",
        content_class="IMAGE",
        artifact_ids=[source.id],
    )
    with pytest.raises(ArtifactInvalidError) as captured:
        require_artifact_egress_consent(
            image_consent,
            [source],
            content_class="WORKBOOK",
        )
    assert captured.value.code == "AI_ARTIFACT_EGRESS_CONSENT_REQUIRED"


def test_local_translation_creates_scanned_derived_artifact_and_preserves_source() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source = _create_workbook(db, storage, scanner, user=user)
    source_bytes = storage.read(source.storage_key)

    result = asyncio.run(
        translate_artifact(
            db,
            artifact_id=source.id,
            user=user,
            direction="zh_to_en",
            mode="local_private",
            selected_sheet_names=["订单"],
            consent=None,
            provider=None,
            request_id="request-local-artifact-translation",
            allowed_factory_ids=frozenset({"huaxing"}),
            storage=storage,
            scanner=scanner,
            settings=workflow_settings(),
            translator_override=lambda texts, _direction: [
                "Purchase Order" if value == "采购订单" else value for value in texts
            ],
        )
    )

    assert storage.read(source.storage_key) == source_bytes
    assert hashlib.sha256(source_bytes).hexdigest() == source.sha256
    assert result.derived.id != source.id
    assert result.derived.parent_artifact_id == source.id
    assert result.derived.derivation_type == "TRANSLATION"
    assert result.derived.classification == source.classification
    assert result.derived.parser_version == TRANSLATION_TERMS_VERSION
    assert result.derived.model_version == "ctranslate2:zh_to_en"
    assert result.derived.scanner_status == "CLEAN"
    assert storage.read(result.derived.storage_key) == result.document.content


def test_legacy_workbook_adapter_preserves_generic_multipart_content_type(
    monkeypatch,
) -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source_bytes = workbook_bytes()
    monkeypatch.setattr(ai_api, "settings", workflow_settings())
    monkeypatch.setattr(
        ai_api,
        "_require_artifacts",
        lambda _user: frozenset({"huaxing"}),
    )

    source = ai_api._legacy_workbook_artifact(
        db,
        content=source_bytes,
        filename="订单.xlsx",
        factory_id="huaxing",
        user=user,
        storage=storage,
        scanner=scanner,
    )

    assert source is not None
    assert source.declared_mime_type == XLSX_MIME
    assert storage.read(source.storage_key) == source_bytes


def test_legacy_cloud_consent_bridge_does_not_weaken_new_artifact_contract(
    monkeypatch,
) -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source_bytes = workbook_bytes()
    source = _create_workbook(db, storage, scanner, user=user)
    translated_bytes = workbook_bytes("Purchase Order")
    config = workflow_settings().model_copy(
        update={"ai_cloud_document_translation_enabled": True}
    )

    def fake_translate(*_args, **_kwargs):
        return DocumentTranslationResult(
            content=translated_bytes,
            output_file_name="订单_中译英.xlsx",
            media_type=XLSX_MIME,
            translated_unit_count=1,
            skipped_unit_count=3,
            processed_part_count=1,
        )

    monkeypatch.setattr(translation_adapter, "translate_document", fake_translate)
    arguments = {
        "db": db,
        "artifact_id": source.id,
        "user": user,
        "direction": "zh_to_en",
        "mode": "ai_smart_cloud",
        "selected_sheet_names": ["订单"],
        "consent": None,
        "provider": object(),
        "request_id": "request-legacy-cloud-bridge",
        "allowed_factory_ids": frozenset({"huaxing"}),
        "storage": storage,
        "scanner": scanner,
        "settings": config,
    }

    with pytest.raises(ArtifactInvalidError) as captured:
        asyncio.run(translate_artifact(**arguments))
    assert captured.value.code == "AI_ARTIFACT_EGRESS_CONSENT_REQUIRED"

    result = asyncio.run(
        translate_artifact(**arguments, legacy_cloud_consent_accepted=True)
    )
    assert result.derived.parent_artifact_id == source.id
    assert storage.read(source.storage_key) == source_bytes


def test_vision_uses_owned_factory_bound_artifacts_and_reuses_image_sanitizer() -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source_bytes = png_bytes(size=(8, 6))
    source = create_artifact(
        db,
        user=user,
        factory_id="huaxing",
        classification="CONFIDENTIAL_BUSINESS",
        filename="screen.png",
        declared_mime_type="image/png",
        data=source_bytes,
        storage=storage,
        scanner=scanner,
        settings=workflow_settings(),
        allowed_factory_ids=frozenset({"huaxing"}),
    )
    consent = AIArtifactEgressConsent(
        accepted=True,
        notice_version="aliyun-cn-beijing-image-v1",
        provider="qwen",
        region="cn-beijing",
        classification="CONFIDENTIAL_BUSINESS",
        content_class="IMAGE",
        artifact_ids=[source.id],
    )
    prepared = prepare_vision_artifacts(
        db,
        references=[AIArtifactReferenceInput(artifact_id=source.id)],
        consent=consent,
        user=user,
        factory_id="huaxing",
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
        settings=workflow_settings(),
    )
    try:
        assert prepared[0].attachment_id == source.id
        assert (prepared[0].width, prepared[0].height) == (8, 6)
        assert prepared[0].source == "USER_PROVIDED"
        assert storage.read(source.storage_key) == source_bytes
    finally:
        clear_prepared_attachments(prepared)

    with pytest.raises(ArtifactInvalidError) as captured:
        prepare_vision_artifacts(
            db,
            references=[AIArtifactReferenceInput(artifact_id=source.id)],
            consent=consent,
            user=user,
            factory_id="huakang_a",
            allowed_factory_ids=frozenset({"huaxing", "huakang_a"}),
            storage=storage,
            settings=workflow_settings(),
        )
    assert captured.value.code == "AI_ARTIFACT_VISION_SCOPE_INVALID"


def test_task_translation_has_deterministic_derived_id_and_safe_replay(monkeypatch) -> None:
    db = artifact_database()
    storage = FakeArtifactStorage()
    scanner = FakeArtifactScanner()
    user = artifact_user()
    source = _create_workbook(db, storage, scanner, user=user)
    translated_bytes = workbook_bytes("Purchase Order")
    calls = 0

    def fake_translate(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return DocumentTranslationResult(
            content=translated_bytes,
            output_file_name="订单_中译英.xlsx",
            media_type=XLSX_MIME,
            translated_unit_count=1,
            skipped_unit_count=3,
            processed_part_count=1,
        )

    monkeypatch.setattr(artifact_workflow_tools, "settings", workflow_settings())
    monkeypatch.setattr(artifact_workflow_tools, "_storage", lambda: storage)
    monkeypatch.setattr(artifact_workflow_tools, "_scanner", lambda: scanner)
    monkeypatch.setattr(artifact_workflow_tools, "translate_document", fake_translate)
    arguments = ArtifactTranslateLocalInput(
        factory_id="huaxing",
        artifact_id=source.id,
        operation_id="translation-operation-001",
        direction="zh_to_en",
        selected_sheet_names=("订单",),
    )
    context = ToolExecutionContext(
        db=db,
        user=user,
        request_id="task:translation:attempt",
    )

    first = translate_document_local_task(context, arguments)
    second = translate_document_local_task(context, arguments)

    assert first.result_artifact_id == second.result_artifact_id
    assert first.idempotent_replay is False
    assert second.idempotent_replay is True
    assert calls == 1
    derived = download_artifact(
        db,
        artifact_id=first.result_artifact_id,
        user=user,
        allowed_factory_ids=frozenset({"huaxing"}),
        storage=storage,
    )
    assert derived.record.parent_artifact_id == source.id
    assert derived.data == translated_bytes
