from __future__ import annotations

import base64

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.ai.artifact import AIArtifactEgressConsent, AIArtifactReferenceInput
from app.schemas.ai.attachment import AIImageAttachmentInput
from app.services.ai.artifacts.contracts import ArtifactContentClass
from app.services.ai.artifacts.egress import require_artifact_egress_consent
from app.services.ai.artifacts.service import ArtifactInvalidError, download_artifact
from app.services.ai.artifacts.storage import ArtifactStorage
from app.services.ai.attachment_service import (
    AIAttachmentValidationError,
    PreparedImageAttachment,
    discard_raw_attachment_inputs,
    prepare_image_attachments,
)
from app.services.auth import AuthContext


def prepare_vision_artifacts(
    db: Session,
    *,
    references: list[AIArtifactReferenceInput],
    consent: AIArtifactEgressConsent | None,
    user: AuthContext,
    factory_id: str,
    allowed_factory_ids: frozenset[str],
    storage: ArtifactStorage,
    settings: Settings,
) -> tuple[PreparedImageAttachment, ...]:
    downloads = [
        download_artifact(
            db,
            artifact_id=reference.artifact_id,
            user=user,
            allowed_factory_ids=allowed_factory_ids,
            storage=storage,
        )
        for reference in references
    ]
    records = [item.record for item in downloads]
    if any(
        record.factory_id != factory_id
        or record.content_class != ArtifactContentClass.IMAGE.value
        for record in records
    ):
        raise ArtifactInvalidError(
            "图片 Artifact 与当前厂区或内容类型不匹配。",
            code="AI_ARTIFACT_VISION_SCOPE_INVALID",
        )
    require_artifact_egress_consent(
        consent,
        records,
        content_class=ArtifactContentClass.IMAGE.value,
    )
    raw_inputs = [
        AIImageAttachmentInput(
            id=record.id,
            media_type=record.detected_mime_type,
            data_url=(
                f"data:{record.detected_mime_type};base64,"
                + base64.b64encode(download.data).decode("ascii")
            ),
        )
        for record, download in zip(records, downloads, strict=True)
    ]
    try:
        return prepare_image_attachments(
            raw_inputs,
            max_count=settings.ai_max_image_attachments,
            max_bytes=settings.ai_max_image_bytes,
            max_total_bytes=settings.ai_max_image_total_bytes,
            max_encoded_chars=settings.ai_max_image_encoded_chars,
            max_pixels=settings.ai_max_image_pixels,
            max_total_pixels=settings.ai_max_image_total_pixels,
        )
    except AIAttachmentValidationError as exc:
        raise ArtifactInvalidError(
            exc.public_message,
            code=exc.code.value,
        ) from exc
    finally:
        discard_raw_attachment_inputs(raw_inputs)
