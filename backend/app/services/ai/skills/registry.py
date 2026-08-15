from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.schemas.ai import AIServerPageContext
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.skills.contracts import (
    RegisteredSkill,
    SkillManifest,
    SkillRegistryError,
)
from app.services.ai.tool_registry import ToolAccessContext, ToolRegistry

_MANIFEST_ROOT = Path(__file__).resolve().parent / "manifests"
_RISK_ORDER = {
    "READ_ONLY": 0,
    "PREVIEW_WITH_AUDIT": 1,
    "CONSEQUENTIAL_WRITE": 2,
    "HIGH_RISK_WRITE": 3,
}
_OPTIONAL_FEATURE_TOOLS = {
    "artifacts.extract_document",
    "artifacts.inspect_document",
    "artifacts.inspect_workbook",
    "artifacts.reconcile_document",
    "artifacts.render_document",
    "artifacts.review_document",
    "artifacts.translate_document_local",
    "artifacts.verify_document",
    "knowledge.search_module",
    "vision.compare_injection_backlog",
    "vision.observe_injection_backlog_image",
}


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class SkillRegistry:
    """Git-first Skill registry that can only reduce the Tool surface."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        *,
        manifest_root: Path = _MANIFEST_ROOT,
        prompt_registry: PromptRegistry | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._manifest_root = manifest_root.resolve()
        self._prompt_registry = prompt_registry or PromptRegistry()
        self._skills = self._load_all()

    @property
    def skills(self) -> tuple[RegisteredSkill, ...]:
        return tuple(sorted(self._skills.values(), key=lambda item: item.manifest.id))

    @property
    def tool_registry(self) -> ToolRegistry:
        return self._tool_registry

    @property
    def prompt_registry(self) -> PromptRegistry:
        return self._prompt_registry

    def resolve(self, skill_id: str, version: str | None = None) -> RegisteredSkill:
        skill = self._skills.get(skill_id)
        if skill is None or (version is not None and skill.manifest.version != version):
            raise SkillRegistryError("unknown Skill or Skill version")
        return skill

    def available(
        self,
        context: ToolAccessContext,
    ) -> tuple[RegisteredSkill, ...]:
        return tuple(skill for skill in self.skills if self.is_available(skill, context))

    def is_available(
        self,
        skill: RegisteredSkill,
        context: ToolAccessContext,
    ) -> bool:
        page_context = context.page_context
        manifest = skill.manifest
        if manifest.route_names:
            if not isinstance(page_context, AIServerPageContext):
                return False
            if page_context.verified_route_name not in manifest.route_names:
                return False
        if manifest.required_context.factory_scope == "required" and (
            not isinstance(page_context, AIServerPageContext)
            or page_context.verified_factory_id is None
        ):
            return False
        if not manifest.allowed_tools:
            return not manifest.feature_tools or any(
                self._tool_registry.resolve(name) is not None
                for name in manifest.feature_tools
            )
        available_names = {
            spec.name
            for spec in self._tool_registry.specs
            if self._tool_registry.is_available(spec, context)
        }
        return bool(
            available_names.intersection(
                (*manifest.allowed_tools, *manifest.feature_tools)
            )
        )

    def authorized_tool_names(
        self,
        skills: Iterable[RegisteredSkill],
        context: ToolAccessContext,
    ) -> tuple[str, ...]:
        selected = tuple(skills)
        if not selected:
            raise SkillRegistryError("at least one Skill is required")
        allowed = self._registered_skill_tools(selected[0])
        for skill in selected[1:]:
            allowed.intersection_update(self._registered_skill_tools(skill))
        return tuple(
            spec.name
            for spec in self._tool_registry.specs
            if spec.name in allowed and self._tool_registry.is_available(spec, context)
        )

    def _load_all(self) -> dict[str, RegisteredSkill]:
        try:
            paths = tuple(sorted(self._manifest_root.glob("*.yaml")))
        except OSError as exc:
            raise SkillRegistryError("Skill manifest registry is unavailable") from exc
        if not paths:
            raise SkillRegistryError("Skill manifest registry is empty")
        loaded: dict[str, RegisteredSkill] = {}
        for path in paths:
            try:
                raw = path.read_text(encoding="utf-8")
                payload = yaml.safe_load(raw)
                manifest = SkillManifest.model_validate(payload)
            except (OSError, UnicodeError, yaml.YAMLError, ValidationError) as exc:
                raise SkillRegistryError(f"invalid Skill manifest: {path.name}") from exc
            if manifest.id in loaded:
                raise SkillRegistryError("duplicate Skill id")
            unknown_tools = [
                name for name in manifest.allowed_tools if self._tool_registry.resolve(name) is None
            ]
            if unknown_tools:
                raise SkillRegistryError("Skill references an unknown Tool")
            if any(name not in _OPTIONAL_FEATURE_TOOLS for name in manifest.feature_tools):
                raise SkillRegistryError("Skill references an unknown feature Tool")
            for name in (*manifest.allowed_tools, *manifest.feature_tools):
                spec = self._tool_registry.resolve(name)
                if spec is None:
                    continue
                if _RISK_ORDER[spec.risk_level.value] > _RISK_ORDER[
                    manifest.risk_policy.maximum.value
                ]:
                    raise SkillRegistryError("Skill Tool exceeds maximum risk")
            prompt = self._prompt_registry.load_skill(
                manifest.id,
                manifest.prompt_version,
            )
            canonical = json.dumps(
                manifest.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            manifest_hash = _hash(canonical)
            content_hash = _hash(f"{manifest_hash}:{prompt.content_hash}")
            loaded[manifest.id] = RegisteredSkill(
                manifest=manifest,
                manifest_hash=manifest_hash,
                prompt_hash=prompt.content_hash,
                content_hash=content_hash,
            )
        return loaded

    def _registered_skill_tools(self, skill: RegisteredSkill) -> set[str]:
        manifest = skill.manifest
        return {
            name
            for name in (*manifest.allowed_tools, *manifest.feature_tools)
            if self._tool_registry.resolve(name) is not None
        }
