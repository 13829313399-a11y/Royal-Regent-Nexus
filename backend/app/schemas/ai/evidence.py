from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

_ALLOWED_FACTORY_IDS = {
    "huakang-a",
    "huakang-b",
    "huakang-c",
    "huakang-d",
    "huadeng",
    "huaxing",
}


class AIEvidenceSourceLevel(StrEnum):
    FORMAL_DOMAIN_SERVICE = "FORMAL_DOMAIN_SERVICE"
    VERSIONED_MODULE_KNOWLEDGE = "VERSIONED_MODULE_KNOWLEDGE"
    AUTHENTICATED_SERVER_CONTEXT = "AUTHENTICATED_SERVER_CONTEXT"
    USER_PROVIDED = "USER_PROVIDED"
    MODEL_INFERENCE = "MODEL_INFERENCE"


class AIEvidenceReferenceV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(
        min_length=8,
        max_length=160,
        pattern=r"^[a-z0-9][a-z0-9._:-]+$",
    )
    source_level: AIEvidenceSourceLevel
    source_name: str = Field(
        min_length=3,
        max_length=160,
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$",
    )
    factory_id: str | None = None
    as_of: datetime
    entity_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    entity_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    entity_revision: int | None = Field(default=None, ge=0)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    truncated: bool = False
    cursor: str | None = Field(default=None, min_length=1, max_length=512)
    access_policy: Literal["REAUTHORIZE_ON_OPEN"] = "REAUTHORIZE_ON_OPEN"

    @field_validator("factory_id")
    @classmethod
    def validate_factory_id(cls, value: str | None) -> str | None:
        if value is not None and value not in _ALLOWED_FACTORY_IDS:
            raise ValueError("Evidence factory is not canonical")
        return value

    @field_validator("as_of")
    @classmethod
    def validate_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Evidence as_of must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_entity_and_source(self) -> AIEvidenceReferenceV1:
        if (self.entity_type is None) != (self.entity_id is None):
            raise ValueError("Evidence entity type and id must be paired")
        if (
            self.source_level is AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
            and self.factory_id is None
        ):
            raise ValueError("formal Evidence must identify a factory")
        return self


class AIEvidenceEnvelopeV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["ai-evidence-v1"] = "ai-evidence-v1"
    evidence: tuple[AIEvidenceReferenceV1, ...] = Field(max_length=16)
