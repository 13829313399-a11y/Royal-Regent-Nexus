from __future__ import annotations

from collections.abc import Sequence

from app.models.ai_artifact import AIArtifact
from app.schemas.ai.artifact import AIArtifactEgressConsent
from app.services.ai.artifacts.contracts import ArtifactClassification
from app.services.ai.artifacts.service import ArtifactInvalidError


def require_artifact_egress_consent(
    consent: AIArtifactEgressConsent | None,
    records: Sequence[AIArtifact],
    *,
    content_class: str,
) -> None:
    """Fail closed unless consent is bound to every exact outbound Artifact."""

    if not records:
        raise ArtifactInvalidError(
            "没有可发送的文件。",
            code="AI_ARTIFACT_EGRESS_EMPTY",
        )
    if any(record.classification == ArtifactClassification.RESTRICTED.value for record in records):
        raise ArtifactInvalidError(
            "受限文件不允许发送到云端 AI。",
            code="AI_ARTIFACT_EGRESS_RESTRICTED",
        )
    expected_ids = [record.id for record in records]
    expected_classification = records[0].classification
    if any(record.classification != expected_classification for record in records):
        raise ArtifactInvalidError(
            "一次云端处理只能使用同一分类的文件。",
            code="AI_ARTIFACT_EGRESS_CLASSIFICATION_MIXED",
        )
    if (
        consent is None
        or consent.content_class != content_class
        or consent.artifact_ids != expected_ids
        or consent.classification != expected_classification
    ):
        raise ArtifactInvalidError(
            "请针对本次文件、分类和云端处理类型重新确认。",
            code="AI_ARTIFACT_EGRESS_CONSENT_REQUIRED",
        )
