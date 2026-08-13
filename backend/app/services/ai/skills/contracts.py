from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai import AIToolRiskLevel
from app.services.ai.providers import ModelCapability, ReasoningPolicy

_SKILL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_VERSION_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_CONTRACT_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$"


class SkillRegistryError(ValueError):
    """A Git-authored Skill failed closed validation."""


class SkillRequiredContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    factory_scope: Literal["none", "optional", "required"] = "optional"


class SkillModelPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability: ModelCapability
    reasoning: ReasoningPolicy = ReasoningPolicy.BALANCED


class SkillRiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    maximum: AIToolRiskLevel


class SkillOutputContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_id: str = Field(pattern=_CONTRACT_PATTERN, min_length=3, max_length=160)


class SkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(pattern=_SKILL_ID_PATTERN, min_length=3, max_length=160)
    version: str = Field(pattern=_VERSION_PATTERN, max_length=32)
    prompt_version: str = Field(pattern=_VERSION_PATTERN, max_length=32)
    owner: str = Field(pattern=r"^[a-z][a-z0-9-]*$", min_length=2, max_length=80)
    status: Literal["legacy", "current", "pilot"]
    intents: tuple[str, ...] = Field(min_length=1, max_length=16)
    route_names: tuple[str, ...] = Field(default=(), max_length=16)
    knowledge_ids: tuple[str, ...] = Field(default=(), max_length=8)
    required_context: SkillRequiredContext
    allowed_tools: tuple[str, ...] = Field(default=(), max_length=32)
    feature_tools: tuple[str, ...] = Field(default=(), max_length=16)
    model_policy: SkillModelPolicy
    risk_policy: SkillRiskPolicy
    output_contract: SkillOutputContract
    max_steps: int = Field(default=4, ge=1, le=6)
    max_input_tokens: int = Field(default=8_000, ge=256, le=16_000)
    eval_suite_ref: str | None = Field(
        default=None,
        pattern=r"^[a-z][a-z0-9_]*$",
        max_length=128,
    )

    @field_validator(
        "intents",
        "route_names",
        "knowledge_ids",
        "allowed_tools",
        "feature_tools",
    )
    @classmethod
    def validate_normalized_unique_values(
        cls,
        values: tuple[str, ...],
    ) -> tuple[str, ...]:
        if any(not value or value != value.strip() for value in values):
            raise ValueError("Skill list values must be normalized and non-empty")
        if len(values) != len(set(values)):
            raise ValueError("Skill list values must be unique")
        return values

    @model_validator(mode="after")
    def validate_disjoint_tool_sets(self) -> SkillManifest:
        if set(self.allowed_tools).intersection(self.feature_tools):
            raise ValueError("Skill required and feature Tool lists must be disjoint")
        return self


@dataclass(frozen=True, slots=True)
class RegisteredSkill:
    manifest: SkillManifest
    manifest_hash: str
    prompt_hash: str
    content_hash: str

    @property
    def version_ref(self) -> str:
        return f"{self.manifest.id}@{self.manifest.version}"
