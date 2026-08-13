from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai import AIToolRiskLevel
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_registry import ToolAccessContext

_SKILL_ID_PATTERN = r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
_TOOL_ID_PATTERN = _SKILL_ID_PATTERN
_RISK_ORDER = {
    AIToolRiskLevel.READ_ONLY: 0,
    AIToolRiskLevel.PREVIEW_WITH_AUDIT: 1,
    AIToolRiskLevel.CONSEQUENTIAL_WRITE: 2,
    AIToolRiskLevel.HIGH_RISK_WRITE: 3,
}


class RuntimePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = Field(default="1", pattern=r"^1$")
    primary_skill_id: str = Field(pattern=_SKILL_ID_PATTERN, max_length=160)
    primary_skill_version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$")
    supporting_skill_ids: tuple[str, ...] = Field(default=(), max_length=3)
    allowed_tool_names: tuple[str, ...] = Field(default=(), max_length=32)
    maximum_risk: AIToolRiskLevel
    max_steps: int = Field(ge=1, le=6)
    token_budget: int = Field(ge=256, le=16_000)
    output_schema_id: str = Field(
        pattern=r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$",
        max_length=160,
    )

    @field_validator("supporting_skill_ids", "allowed_tool_names")
    @classmethod
    def validate_unique_closed_ids(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(values) != len(set(values)):
            raise ValueError("Runtime Plan ids must be unique")
        pattern = re.compile(_TOOL_ID_PATTERN)
        if any(pattern.fullmatch(value) is None for value in values):
            raise ValueError("Runtime Plan contains an invalid id")
        return values


class RuntimePlanBuilder:
    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def build(
        self,
        *,
        primary_skill_id: str,
        context: ToolAccessContext,
        primary_skill_version: str | None = None,
        supporting_skill_ids: tuple[str, ...] = (),
        proposed_tool_names: tuple[str, ...] | None = None,
        proposed_max_steps: int | None = None,
        proposed_maximum_risk: AIToolRiskLevel | None = None,
        proposed_token_budget: int | None = None,
    ) -> RuntimePlan:
        primary = self._registry.resolve(primary_skill_id, primary_skill_version)
        if (
            len(supporting_skill_ids) != len(set(supporting_skill_ids))
            or primary_skill_id in supporting_skill_ids
        ):
            raise SkillRegistryError("Runtime Plan Skill ids must be unique")
        supporting = tuple(self._registry.resolve(skill_id) for skill_id in supporting_skill_ids)
        selected = (primary, *supporting)
        if any(not self._registry.is_available(skill, context) for skill in selected):
            raise SkillRegistryError("Runtime Plan references an unauthorized Skill")

        authorized_tools = self._registry.authorized_tool_names(selected, context)
        if proposed_tool_names is not None:
            if len(proposed_tool_names) != len(set(proposed_tool_names)):
                raise SkillRegistryError("Runtime Plan Tool names must be unique")
            if not set(proposed_tool_names).issubset(authorized_tools):
                raise SkillRegistryError("Runtime Plan references an unauthorized Tool")
            authorized_tools = proposed_tool_names

        max_steps = proposed_max_steps or primary.manifest.max_steps
        if max_steps > primary.manifest.max_steps or not 1 <= max_steps <= 6:
            raise SkillRegistryError("Runtime Plan exceeds the Skill step limit")
        token_budget = proposed_token_budget or primary.manifest.max_input_tokens
        if token_budget > primary.manifest.max_input_tokens or not 256 <= token_budget <= 16_000:
            raise SkillRegistryError("Runtime Plan exceeds the Skill token budget")
        maximum_risk = proposed_maximum_risk or primary.manifest.risk_policy.maximum
        if _RISK_ORDER[maximum_risk] > _RISK_ORDER[primary.manifest.risk_policy.maximum]:
            raise SkillRegistryError("Runtime Plan exceeds the Skill risk limit")

        for name in authorized_tools:
            spec = self._registry.tool_registry.resolve(name)
            assert spec is not None
            if _RISK_ORDER[spec.risk_level] > _RISK_ORDER[maximum_risk]:
                raise SkillRegistryError("Runtime Plan Tool exceeds its risk limit")

        return RuntimePlan(
            primary_skill_id=primary.manifest.id,
            primary_skill_version=primary.manifest.version,
            supporting_skill_ids=tuple(skill.manifest.id for skill in supporting),
            allowed_tool_names=authorized_tools,
            maximum_risk=maximum_risk,
            max_steps=max_steps,
            token_budget=token_budget,
            output_schema_id=primary.manifest.output_contract.schema_id,
        )
