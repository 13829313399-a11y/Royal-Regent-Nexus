from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, ValidationError

from app.services.ai.skills.contracts import RegisteredSkill, SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_registry import ToolAccessContext


class IntentComplexity(StrEnum):
    SIMPLE = "SIMPLE"
    ANALYTICAL = "ANALYTICAL"


class _ClosedClassification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent: str
    complexity: IntentComplexity


@dataclass(frozen=True, slots=True)
class SkillRoute:
    primary_skill: RegisteredSkill
    intent: str
    complexity: IntentComplexity
    source: str


_ANALYTICAL_HINTS = (
    "比较",
    "分析",
    "原因",
    "建议",
    "优化",
    "趋势",
    "差异",
    "为什么",
)


class SkillRouter:
    """Rules first; a closed model classification can only select an allowed Skill."""

    def __init__(self, registry: SkillRegistry) -> None:
        self._registry = registry

    def route(
        self,
        *,
        text: str,
        context: ToolAccessContext,
        has_file: bool = False,
        has_image: bool = False,
        model_classification: Mapping[str, object] | None = None,
    ) -> SkillRoute:
        available = self._registry.available(context)
        by_id = {item.manifest.id: item for item in available}
        if not by_id:
            raise SkillRegistryError("no authorized Skill is available")

        normalized = re.sub(r"\s+", " ", text.strip().lower())[:8_000]
        deterministic = self._deterministic_skill_id(
            normalized,
            has_file=has_file,
            has_image=has_image,
        )
        if deterministic in by_id:
            skill = by_id[deterministic]
            return SkillRoute(
                primary_skill=skill,
                intent=self._matching_intent(skill, normalized),
                complexity=self._complexity(normalized),
                source="rule",
            )

        classified = self._validated_model_route(model_classification, available)
        if classified is not None:
            skill, intent, complexity = classified
            return SkillRoute(skill, intent, complexity, "closed_classifier")

        fallback_id = (
            "business.current_page_query"
            if "business.current_page_query" in by_id
            else "system.module_tutor"
        )
        if fallback_id not in by_id:
            fallback_id = min(by_id)
        fallback = by_id[fallback_id]
        return SkillRoute(
            fallback,
            fallback.manifest.intents[0],
            self._complexity(normalized),
            "deterministic_fallback",
        )

    @staticmethod
    def _deterministic_skill_id(
        text: str,
        *,
        has_file: bool,
        has_image: bool,
    ) -> str | None:
        if has_image:
            return "vision.screenshot_observation"
        if has_file and any(word in text for word in ("翻译", "译成", "translate")):
            return "files.document_translation"
        if has_file and any(
            word in text for word in ("映射", "表头", "字段", "excel", "工作簿")
        ):
            return "files.workbook_mapping_preview"

        domain_rules = (
            (("报价", "询价", "quote"), "internal_quote.read_summary"),
            (("试模", "模具样品", "molding"), "molding_sample.read_summary"),
            (("纸箱", "carton"), "carton_procurement.read_summary"),
            (("原料", "原材料", "库存", "raw material"), "raw_material.read_summary"),
            (("客户订单", "订单审计", "导出审计", "customer order"), "customer_order.capability_and_audit"),
            (("候选方案", "排产建议", "生成预览", "对比预览", "优化排产"), "injection_scheduling.preview_advisor"),
            (("排产", "积压", "backlog", "计划上下文"), "injection_scheduling.read_context"),
        )
        for hints, skill_id in domain_rules:
            if any(hint in text for hint in hints):
                return skill_id
        if any(word in text for word in ("怎么用", "帮助", "说明页面", "功能介绍")):
            return "system.module_tutor"
        return None

    @staticmethod
    def _complexity(text: str) -> IntentComplexity:
        return (
            IntentComplexity.ANALYTICAL
            if any(hint in text for hint in _ANALYTICAL_HINTS)
            else IntentComplexity.SIMPLE
        )

    @staticmethod
    def _matching_intent(skill: RegisteredSkill, text: str) -> str:
        for intent in skill.manifest.intents:
            if intent.replace("_", " ") in text or intent in text:
                return intent
        return skill.manifest.intents[0]

    @staticmethod
    def _validated_model_route(
        raw: Mapping[str, object] | None,
        available: tuple[RegisteredSkill, ...],
    ) -> tuple[RegisteredSkill, str, IntentComplexity] | None:
        if raw is None:
            return None
        try:
            classification = _ClosedClassification.model_validate(raw)
        except ValidationError:
            return None
        matches = [
            skill
            for skill in available
            if classification.intent in skill.manifest.intents
        ]
        if len(matches) != 1:
            return None
        return matches[0], classification.intent, classification.complexity
