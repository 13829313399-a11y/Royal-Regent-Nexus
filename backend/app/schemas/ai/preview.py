from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai.evidence import AIEvidenceReferenceV1

_ALLOWED_FACTORY_IDS = {
    "huakang-a",
    "huakang-b",
    "huakang-c",
    "huakang-d",
    "huadeng",
    "huaxing",
}


class AIPreviewStatus(StrEnum):
    READY = "READY"
    STALE = "STALE"
    EXPIRED = "EXPIRED"
    ACCESS_REVOKED = "ACCESS_REVOKED"
    INVALID = "INVALID"


class AIPreviewAssumption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    label: str = Field(min_length=1, max_length=120)
    value: str = Field(min_length=1, max_length=240)

    @field_validator("label", "value")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AIPreviewManifestV1(BaseModel):
    """Closed, persistence-safe metadata shared by domain Preview adapters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ai-preview-manifest-v1"] = "ai-preview-manifest-v1"
    preview_id: str = Field(
        min_length=8,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]+$",
    )
    preview_type: str = Field(
        min_length=3,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    )
    source_revision_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    factory_id: str
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    assumptions: tuple[AIPreviewAssumption, ...] = Field(
        min_length=1,
        max_length=16,
    )
    evidence_refs: tuple[AIEvidenceReferenceV1, ...] = Field(
        min_length=1,
        max_length=8,
    )
    created_by: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    created_at: datetime
    expires_at: datetime
    status: AIPreviewStatus
    deterministic_service: bool
    can_propose_action: bool
    action_capability: Literal["CREATE_PROPOSAL_ONLY"] | None = None
    no_write_performed: Literal[True] = True

    @field_validator("factory_id")
    @classmethod
    def canonical_factory(cls, value: str) -> str:
        if value not in _ALLOWED_FACTORY_IDS:
            raise ValueError("Preview factory is not canonical")
        return value

    @field_validator("created_at", "expires_at")
    @classmethod
    def timezone_required(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Preview timestamps require a timezone")
        return value

    @model_validator(mode="after")
    def validate_closed_manifest(self) -> AIPreviewManifestV1:
        if self.expires_at <= self.created_at:
            raise ValueError("Preview expiry must follow creation")
        assumption_keys = [item.key for item in self.assumptions]
        if len(assumption_keys) != len(set(assumption_keys)):
            raise ValueError("Preview assumptions must be unique")
        evidence_ids = [item.evidence_id for item in self.evidence_refs]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Preview Evidence must be unique")
        if any(
            item.factory_id is not None and item.factory_id != self.factory_id
            for item in self.evidence_refs
        ):
            raise ValueError("Preview Evidence factory mismatch")
        if self.can_propose_action != (
            self.action_capability == "CREATE_PROPOSAL_ONLY"
        ):
            raise ValueError("Preview Action capability is inconsistent")
        if self.status is not AIPreviewStatus.READY and self.can_propose_action:
            raise ValueError("Only a ready Preview may propose an Action")
        return self


class AIScenarioCompareContractV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ai-scenario-compare-v1"] = "ai-scenario-compare-v1"
    preview_type: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
    )
    preview_ids: tuple[str, ...] = Field(min_length=2, max_length=4)
    source_revision_hashes: tuple[str, ...] = Field(min_length=1, max_length=4)
    comparable: bool
    comparison_basis: Literal["SAME_SOURCE_REVISION", "MIXED_SOURCE_REVISION"]
    warning: str = Field(min_length=1, max_length=300)
    no_write_performed: Literal[True] = True

    @model_validator(mode="after")
    def validate_comparison(self) -> AIScenarioCompareContractV1:
        if len(self.preview_ids) != len(set(self.preview_ids)):
            raise ValueError("Scenario Preview ids must be unique")
        unique_hashes = set(self.source_revision_hashes)
        if len(unique_hashes) != len(self.source_revision_hashes):
            raise ValueError("Scenario revision hashes must be unique")
        expected = len(unique_hashes) == 1
        if self.comparable != expected:
            raise ValueError("Scenario comparability does not match revisions")
        expected_basis = (
            "SAME_SOURCE_REVISION" if expected else "MIXED_SOURCE_REVISION"
        )
        if self.comparison_basis != expected_basis:
            raise ValueError("Scenario comparison basis is inconsistent")
        return self
