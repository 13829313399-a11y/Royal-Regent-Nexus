from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.core.time import business_now
from app.schemas.ai.evidence import AIEvidenceSourceLevel
from app.schemas.ai.preview import AIPreviewManifestV1, AIPreviewStatus
from app.services.ai.previews.registry import PreviewRegistry, PreviewRegistryError
from app.services.auth import AuthContext, authorization_decision


@dataclass(frozen=True, slots=True)
class PreviewVerificationContext:
    user: AuthContext
    factory_id: str
    current_source_revision_hash: str
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class PreviewVerificationResult:
    status: AIPreviewStatus
    reason_codes: tuple[str, ...]
    can_propose_action: bool


def verify_preview(
    manifest: AIPreviewManifestV1,
    *,
    registry: PreviewRegistry,
    context: PreviewVerificationContext,
) -> PreviewVerificationResult:
    """Recompute Preview usability from current IAM, source revision and time."""

    try:
        spec = registry.require(manifest.preview_type)
    except PreviewRegistryError:
        return PreviewVerificationResult(
            status=AIPreviewStatus.INVALID,
            reason_codes=("PREVIEW_TYPE_UNREGISTERED",),
            can_propose_action=False,
        )

    reasons: list[str] = []
    if manifest.factory_id != context.factory_id:
        reasons.append("PREVIEW_FACTORY_MISMATCH")
    if manifest.source_revision_hash != context.current_source_revision_hash:
        reasons.append("PREVIEW_SOURCE_STALE")
    current = context.now or business_now()
    if current.tzinfo is None or current.utcoffset() is None:
        reasons.append("PREVIEW_TIME_INVALID")
    elif manifest.expires_at <= current:
        reasons.append("PREVIEW_EXPIRED")

    assumption_values = {item.key: item.value for item in manifest.assumptions}
    assumption_keys = set(assumption_values)
    if not spec.required_assumption_keys.issubset(assumption_keys):
        reasons.append("PREVIEW_ASSUMPTIONS_INCOMPLETE")
    elif any(
        not assumption_values[key].startswith(expected)
        for key, expected in spec.required_assumption_values
    ):
        reasons.append("PREVIEW_ASSUMPTIONS_INVALID")
    if manifest.deterministic_service != spec.deterministic_service:
        reasons.append("PREVIEW_ORIGIN_MISMATCH")

    formal_evidence = any(
        item.source_level is AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
        for item in manifest.evidence_refs
    )
    user_evidence = any(
        item.source_level is AIEvidenceSourceLevel.USER_PROVIDED
        for item in manifest.evidence_refs
    )
    inference_evidence = any(
        item.source_level is AIEvidenceSourceLevel.MODEL_INFERENCE
        for item in manifest.evidence_refs
    )
    if spec.deterministic_service and not formal_evidence:
        reasons.append("PREVIEW_FORMAL_EVIDENCE_MISSING")
    if not spec.deterministic_service and not (user_evidence and inference_evidence):
        reasons.append("PREVIEW_MAPPING_EVIDENCE_INCOMPLETE")

    authorized = any(
        authorization_decision(
            context.user,
            spec.required_permission,
            context.factory_id,
            department,
        )[0]
        for department in spec.allowed_departments
    )
    if not authorized:
        reasons.append("PREVIEW_ACCESS_REVOKED")

    if "PREVIEW_ACCESS_REVOKED" in reasons:
        status = AIPreviewStatus.ACCESS_REVOKED
    elif "PREVIEW_EXPIRED" in reasons:
        status = AIPreviewStatus.EXPIRED
    elif "PREVIEW_SOURCE_STALE" in reasons:
        status = AIPreviewStatus.STALE
    elif reasons:
        status = AIPreviewStatus.INVALID
    else:
        status = AIPreviewStatus.READY
    can_propose = status is AIPreviewStatus.READY and spec.may_create_action_proposal
    return PreviewVerificationResult(
        status=status,
        reason_codes=tuple(dict.fromkeys(reasons)),
        can_propose_action=can_propose,
    )
