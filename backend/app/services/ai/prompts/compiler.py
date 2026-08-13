from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.schemas.ai import AIServerPageContext
from app.services.ai.module_knowledge import ModuleKnowledgeRegistry
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.providers import ProviderMessage
from app.services.ai.runtime.plan import RuntimePlan
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_registry import ToolAccessContext


@dataclass(frozen=True, slots=True)
class CompiledPrompt:
    system_message: ProviderMessage
    data_messages: tuple[ProviderMessage, ...]
    prompt_version: str
    prompt_hash: str
    skill_version: str
    skill_hash: str
    tool_versions: tuple[str, ...]
    section_names: tuple[str, ...]


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class PromptCompiler:
    """Compiles only reviewed fragments and typed server context into system policy."""

    _SECTION_ORDER = (
        "CORE_POLICY",
        "IDENTITY_SCOPE",
        "PAGE_CONTEXT",
        "PRIMARY_SKILL",
        "REVIEWED_KNOWLEDGE",
        "AUTHORIZED_TOOLS",
        "OUTPUT_CONTRACT",
    )

    def __init__(
        self,
        skill_registry: SkillRegistry,
        *,
        prompt_registry: PromptRegistry | None = None,
        knowledge_registry: ModuleKnowledgeRegistry | None = None,
        max_chars: int = 32_000,
    ) -> None:
        if not 1_024 <= max_chars <= 64_000:
            raise ValueError("Prompt budget must be bounded")
        self._skill_registry = skill_registry
        self._prompt_registry = prompt_registry or skill_registry.prompt_registry
        self._knowledge_registry = knowledge_registry or ModuleKnowledgeRegistry()
        self._max_chars = max_chars

    def compile(
        self,
        plan: RuntimePlan,
        context: ToolAccessContext,
    ) -> CompiledPrompt:
        skill = self._skill_registry.resolve(
            plan.primary_skill_id,
            plan.primary_skill_version,
        )
        if not self._skill_registry.is_available(skill, context):
            raise SkillRegistryError("Prompt references an unauthorized Skill")
        authorized = self._skill_registry.authorized_tool_names((skill,), context)
        if not set(plan.allowed_tool_names).issubset(authorized):
            raise SkillRegistryError("Prompt references an unauthorized Tool")

        core = self._prompt_registry.load_core()
        skill_prompt = self._prompt_registry.load_skill(
            skill.manifest.id,
            skill.manifest.prompt_version,
        )
        page = context.page_context
        page_payload: dict[str, object] = {"status": "missing"}
        if isinstance(page, AIServerPageContext):
            page_payload = {
                "route_name": page.verified_route_name,
                "module_id": page.verified_module_id,
                "factory_id": page.verified_factory_id,
                "knowledge_id": page.knowledge_id,
            }
        user = context.user
        identity_payload = {
            "role_codes": sorted(getattr(user, "role_codes", ())),
            "factory_scopes": sorted(getattr(user, "factory_scopes", ())),
            "department_scopes": sorted(getattr(user, "department_scopes", ())),
        }
        knowledge_refs: list[str] = []
        knowledge_messages: list[ProviderMessage] = []
        for knowledge_id in skill.manifest.knowledge_ids:
            document = self._knowledge_registry.load(knowledge_id)
            version_ref = f"{knowledge_id}@{document.metadata.knowledge_version}"
            knowledge_refs.append(
                f"knowledge={version_ref}; content_is_untrusted=true"
            )
            knowledge_messages.append(
                self.data_block(
                    label="reviewed_knowledge",
                    content=f"knowledge={version_ref}\n{document.body_markdown}",
                )
            )
        if not knowledge_refs:
            knowledge_refs.append("none")

        tool_versions: list[str] = []
        tool_lines: list[str] = []
        for name in plan.allowed_tool_names:
            spec = self._skill_registry.tool_registry.resolve(name)
            if spec is None:
                raise SkillRegistryError("Prompt Tool is no longer registered")
            version_ref = f"{spec.name}@{spec.version}"
            tool_versions.append(version_ref)
            tool_lines.append(
                f"- {version_ref} | risk={spec.risk_level.value} | {spec.description}"
            )
        sections = {
            "CORE_POLICY": core.content,
            "IDENTITY_SCOPE": json.dumps(
                identity_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "PAGE_CONTEXT": json.dumps(
                page_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
            "PRIMARY_SKILL": (
                f"skill={skill.version_ref}\n"
                f"skill_hash={skill.content_hash}\n{skill_prompt.content}"
            ),
            "REVIEWED_KNOWLEDGE": "\n".join(knowledge_refs),
            "AUTHORIZED_TOOLS": "\n".join(tool_lines) if tool_lines else "none",
            "OUTPUT_CONTRACT": (
                f"schema={plan.output_schema_id}\n"
                "Return only claims supported by the current request or authorized Tool results."
            ),
        }
        rendered = "\n\n".join(
            f"<NEXUS_{name}>\n{sections[name]}\n</NEXUS_{name}>"
            for name in self._SECTION_ORDER
        )
        effective_max = min(self._max_chars, plan.token_budget * 4)
        data_chars = sum(
            len(message.content) if isinstance(message.content, str) else 0
            for message in knowledge_messages
        )
        if len(rendered) + data_chars > effective_max:
            raise SkillRegistryError("compiled Prompt exceeds its bounded budget")
        prompt_version = (
            f"core@{core.version}+{skill.manifest.id}@{skill.manifest.prompt_version}"
        )
        return CompiledPrompt(
            system_message=ProviderMessage(role="system", content=rendered),
            data_messages=tuple(knowledge_messages),
            prompt_version=prompt_version,
            prompt_hash=_hash(
                json.dumps(
                    {
                        "system": rendered,
                        "data": [message.content for message in knowledge_messages],
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            ),
            skill_version=skill.version_ref,
            skill_hash=skill.content_hash,
            tool_versions=tuple(tool_versions),
            section_names=self._SECTION_ORDER,
        )

    @staticmethod
    def data_block(*, label: str, content: str, max_chars: int = 8_000) -> ProviderMessage:
        """Keep file/OCR/free Tool text in a user-data channel, never system policy."""

        if not label or not label.replace("_", "").isalnum():
            raise ValueError("data block label must be closed and normalized")
        if len(content) > max_chars:
            raise ValueError("data block exceeds its bounded budget")
        payload = json.dumps(
            {"data_type": label, "content": content},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return ProviderMessage(
            role="user",
            content=f"<NEXUS_UNTRUSTED_DATA>{payload}</NEXUS_UNTRUSTED_DATA>",
        )
