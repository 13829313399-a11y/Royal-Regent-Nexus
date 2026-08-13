from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai import AIEvidenceReferenceV1, AIEvidenceSourceLevel


class AIVerificationError(ValueError):
    """A claim is not supported by its closed Evidence set."""


class AIFactStatus(StrEnum):
    UNKNOWN = "UNKNOWN"
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    PREVIEW = "PREVIEW"
    EXECUTED = "EXECUTED"
    USER_PROVIDED = "USER_PROVIDED"


class AIVerificationClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]+$", max_length=160)
    critical_formal: bool = False
    factory_id: str | None = None
    grouped_by_factory: bool = False
    evidence_ids: tuple[str, ...] = Field(default=(), max_length=16)
    asserted_status: AIFactStatus = AIFactStatus.UNKNOWN
    observed_status: AIFactStatus = AIFactStatus.UNKNOWN
    asserts_complete: bool = False
    tool_succeeded: bool = True

    @model_validator(mode="after")
    def validate_unique_evidence(self) -> AIVerificationClaim:
        if len(self.evidence_ids) != len(set(self.evidence_ids)):
            raise ValueError("claim Evidence ids must be unique")
        return self


def verify_claim(
    claim: AIVerificationClaim,
    evidence: tuple[AIEvidenceReferenceV1, ...],
) -> None:
    by_id = {item.evidence_id: item for item in evidence}
    if len(by_id) != len(evidence):
        raise AIVerificationError("duplicate Evidence id")
    if not set(claim.evidence_ids).issubset(by_id):
        raise AIVerificationError("claim references unknown Evidence")
    selected = tuple(by_id[evidence_id] for evidence_id in claim.evidence_ids)

    if not claim.tool_succeeded and claim.evidence_ids:
        raise AIVerificationError("failed Tool cannot support a successful claim")
    if claim.critical_formal and not selected:
        raise AIVerificationError("critical formal claim requires Evidence")
    if claim.critical_formal and not any(
        item.source_level is AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
        for item in selected
    ):
        raise AIVerificationError("critical formal claim lacks formal Evidence")

    factories = {item.factory_id for item in selected if item.factory_id is not None}
    if len(factories) > 1 and not claim.grouped_by_factory:
        raise AIVerificationError("cross-factory Evidence must be grouped")
    if claim.factory_id is not None and factories and factories != {claim.factory_id}:
        raise AIVerificationError("claim factory does not match Evidence")

    if (
        claim.asserted_status is AIFactStatus.PUBLISHED
        and claim.observed_status is not AIFactStatus.PUBLISHED
    ):
        raise AIVerificationError("DRAFT cannot be asserted as PUBLISHED")
    if (
        claim.asserted_status is AIFactStatus.EXECUTED
        and claim.observed_status is not AIFactStatus.EXECUTED
    ):
        raise AIVerificationError("Preview cannot be asserted as executed")
    if claim.asserts_complete and any(item.truncated for item in selected):
        raise AIVerificationError("truncated Evidence cannot support a complete-set claim")
    if (
        claim.critical_formal
        and any(
            item.source_level is AIEvidenceSourceLevel.USER_PROVIDED
            for item in selected
        )
    ):
        raise AIVerificationError("user-provided data is not formal system Evidence")
