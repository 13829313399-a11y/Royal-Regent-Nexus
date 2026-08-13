from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from anyio import from_thread
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.models.ai_artifact import AIArtifact
from app.schemas.ai.artifact import AIArtifactEgressConsent
from app.services.ai.artifacts.contracts import (
    ArtifactContentClass,
    ArtifactDerivationType,
)
from app.services.ai.artifacts.egress import require_artifact_egress_consent
from app.services.ai.artifacts.scanner import ArtifactScanner
from app.services.ai.artifacts.service import (
    ArtifactInvalidError,
    create_derived_artifact,
    download_artifact,
)
from app.services.ai.artifacts.storage import ArtifactStorage
from app.services.ai.cloud_document_translation import translate_cloud_fragments
from app.services.ai.providers import LLMProvider
from app.services.auth import AuthContext
from app.services.document_translation import (
    DocumentTranslationResult,
    TranslationDirection,
    TranslationFunction,
    translate_document,
)

TRANSLATION_TERMS_VERSION = "document-translation-terms-v1"


@dataclass(frozen=True, slots=True)
class ArtifactTranslationResult:
    source: AIArtifact
    derived: AIArtifact
    document: DocumentTranslationResult


async def translate_artifact(
    db: Session,
    *,
    artifact_id: str,
    user: AuthContext,
    direction: TranslationDirection,
    mode: str,
    selected_sheet_names: Sequence[str] | None,
    consent: AIArtifactEgressConsent | None,
    provider: LLMProvider | None,
    request_id: str,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    scanner: ArtifactScanner,
    settings: Settings,
    translator_override: TranslationFunction | None = None,
    legacy_cloud_consent_accepted: bool = False,
) -> ArtifactTranslationResult:
    download = download_artifact(
        db,
        artifact_id=artifact_id,
        user=user,
        allowed_factory_ids=allowed_factory_ids,
        storage=storage,
    )
    source = download.record
    if (
        source.normalized_extension not in {".xlsx", ".docx"}
        or source.content_class
        not in {ArtifactContentClass.WORKBOOK.value, ArtifactContentClass.DOCUMENT.value}
    ):
        raise ArtifactInvalidError(
            "Artifact 翻译只接受无宏 .xlsx 或 .docx 文件。",
            code="AI_ARTIFACT_TRANSLATION_TYPE_INVALID",
        )
    if mode not in {"local_private", "ai_smart_cloud"}:
        raise ArtifactInvalidError(
            "翻译模式无效。", code="AI_ARTIFACT_TRANSLATION_MODE_INVALID"
        )

    translator: TranslationFunction | None = translator_override
    model_dir: str | None = settings.document_translation_model_dir
    model_version = f"ctranslate2:{direction}"
    if mode == "ai_smart_cloud":
        if not settings.ai_cloud_document_translation_enabled or provider is None:
            raise ArtifactInvalidError(
                "AI Smart / Cloud 翻译尚未启用。",
                code="AI_ARTIFACT_CLOUD_TRANSLATION_DISABLED",
            )
        if legacy_cloud_consent_accepted:
            # Compatibility bridge for the pre-Artifact multipart endpoint.  Its
            # cloud_consent boolean is scoped to this single uploaded document;
            # new Artifact endpoints must always use the versioned strict contract.
            if consent is not None:
                raise ArtifactInvalidError(
                    "旧版云端同意不能与 Artifact 云端同意同时提交。",
                    code="AI_ARTIFACT_EGRESS_CONSENT_AMBIGUOUS",
                )
        else:
            require_artifact_egress_consent(
                consent,
                [source],
                content_class=source.content_class,
            )

        async def translate_fragments(texts, fragment_direction):
            return await translate_cloud_fragments(
                texts,
                fragment_direction,
                provider=provider,
                settings=settings,
                request_id=request_id,
            )

        def cloud_translator(texts, fragment_direction):
            return from_thread.run(translate_fragments, texts, fragment_direction)

        translator = cloud_translator
        model_dir = None
        model_version = settings.ai_default_model
    elif consent is not None:
        raise ArtifactInvalidError(
            "本地翻译不能提交云端处理同意。",
            code="AI_ARTIFACT_EGRESS_CONSENT_UNEXPECTED",
        )

    result = await run_in_threadpool(
        translate_document,
        download.data,
        source.original_filename,
        direction=direction,
        translator=translator,
        model_dir=model_dir,
        device=settings.document_translation_device,
        selected_sheet_names=selected_sheet_names,
    )
    derived = create_derived_artifact(
        db,
        parent_artifact_id=source.id,
        user=user,
        classification=source.classification,
        derivation_type=ArtifactDerivationType.TRANSLATION,
        filename=result.output_file_name,
        declared_mime_type=result.media_type,
        data=result.content,
        parser_version=TRANSLATION_TERMS_VERSION,
        model_version=model_version,
        storage=storage,
        scanner=scanner,
        settings=settings,
        allowed_factory_ids=allowed_factory_ids,
    )
    return ArtifactTranslationResult(source=source, derived=derived, document=result)
