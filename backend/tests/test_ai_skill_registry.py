from pathlib import Path

import pytest

from app.schemas.ai import AIServerPageContext
from app.services.ai.prompts.registry import PromptRegistry
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext, AuthGrantContext, AuthOverrideContext


def _user(*, denied: bool = False) -> AuthContext:
    grant = AuthGrantContext(
        role_id="role-scheduling-reader",
        role_name="排产读取",
        factory_id="huaxing",
        department="production",
        permissions=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
        binding_id="grant-scheduling-reader",
    )
    overrides = (
        AuthOverrideContext(
            id="deny-scheduling-read",
            permission_code="injection_scheduling:read",
            effect="deny",
            factory_id="huaxing",
            department="production",
        ),
    ) if denied else ()
    return AuthContext(
        id="skill-user",
        username="skill-user",
        display_name="Skill 测试用户",
        roles=("测试角色",),
        role_codes=("test",),
        permissions=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
        overrides=overrides,
        active_permission_codes=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
    )


def _context(*, denied: bool = False) -> ToolExecutionContext:
    return ToolExecutionContext(
        None,
        _user(denied=denied),
        "request-skill-registry",
        AIServerPageContext(
            verified_route_name="injection-scheduling-v2",
            verified_path="/modules/production/injection-scheduling",
            verified_factory_id="huaxing",
            verified_module_id="injection-scheduling",
            knowledge_id="injection-scheduling",
            allowed_tool_groups=("identity", "module_knowledge", "injection_scheduling"),
        ),
    )


def _write_registry(
    tmp_path: Path,
    manifests: dict[str, str],
    prompts: dict[str, str],
) -> tuple[Path, PromptRegistry]:
    manifest_root = tmp_path / "manifests"
    prompt_root = tmp_path / "prompts"
    skill_prompt_root = prompt_root / "skills"
    manifest_root.mkdir(parents=True)
    skill_prompt_root.mkdir(parents=True)
    (prompt_root / "core_policy.md").write_text("bounded core", encoding="utf-8")
    for name, content in manifests.items():
        (manifest_root / name).write_text(content, encoding="utf-8")
    for name, content in prompts.items():
        (skill_prompt_root / name).write_text(content, encoding="utf-8")
    return manifest_root, PromptRegistry(prompt_root=prompt_root)


_MANIFEST = """id: test.read
version: 1.0.0
prompt_version: 1.0.0
owner: platform-engineering
status: current
intents: [query_test]
route_names: []
knowledge_ids: []
required_context: {factory_scope: optional}
allowed_tools: [identity.get_current_context]
model_policy: {capability: GENERAL_CHAT, reasoning: FAST}
risk_policy: {maximum: READ_ONLY}
output_contract: {schema_id: test.read.v1}
max_steps: 2
max_input_tokens: 1000
"""


def test_default_registry_has_reviewed_unique_versioned_skills_and_stable_hashes() -> None:
    tools = build_default_tool_registry()
    first = SkillRegistry(tools)
    second = SkillRegistry(tools)

    assert len(first.skills) == 17
    assert [skill.manifest.id for skill in first.skills] == sorted(
        skill.manifest.id for skill in first.skills
    )
    assert len({skill.manifest.id for skill in first.skills}) == 17
    assert [skill.content_hash for skill in first.skills] == [
        skill.content_hash for skill in second.skills
    ]
    assert all(len(skill.content_hash) == 64 for skill in first.skills)
    assert first.resolve("injection_scheduling.read_context", "1.0.0").version_ref == (
        "injection_scheduling.read_context@1.0.0"
    )
    with pytest.raises(SkillRegistryError, match="unknown Skill"):
        first.resolve("injection_scheduling.read_context", "9.9.9")
    assert first.resolve("system.module_tutor", "1.1.0").manifest.feature_tools == (
        "knowledge.search_module",
    )
    assert {
        "files.pdf_to_excel",
        "files.pdf_to_word",
        "files.pdf_split",
        "files.pdf_translation",
        "files.word_to_pdf",
    }.issubset({skill.manifest.id for skill in first.skills})


def test_module_tutor_feature_tool_is_optional_and_only_authorized_when_enabled() -> None:
    disabled = SkillRegistry(build_default_tool_registry())
    enabled = SkillRegistry(build_default_tool_registry(knowledge_hub_enabled=True))
    disabled_skill = disabled.resolve("system.module_tutor")
    enabled_skill = enabled.resolve("system.module_tutor")

    assert disabled.authorized_tool_names((disabled_skill,), _context()) == (
        "identity.get_current_context",
        "knowledge.get_module_help",
    )
    assert enabled.authorized_tool_names((enabled_skill,), _context()) == (
        "identity.get_current_context",
        "knowledge.get_module_help",
        "knowledge.search_module",
    )
    assert enabled.authorized_tool_names(
        (enabled.resolve("injection_scheduling.read_context"),),
        _context(),
    ) == (
        "injection_scheduling.compare_previews",
        "injection_scheduling.get_backlog",
        "injection_scheduling.get_plan_context",
        "knowledge.search_module",
    )


def test_registry_rejects_duplicate_id_unknown_tool_and_risk_escalation(
    tmp_path: Path,
) -> None:
    tools = build_default_tool_registry()
    manifest_root, prompts = _write_registry(
        tmp_path / "duplicate",
        {"a.yaml": _MANIFEST, "b.yaml": _MANIFEST},
        {"test.read.md": "read only"},
    )
    with pytest.raises(SkillRegistryError, match="duplicate Skill"):
        SkillRegistry(tools, manifest_root=manifest_root, prompt_registry=prompts)

    unknown_manifest = _MANIFEST.replace(
        "identity.get_current_context",
        "unknown.execute_anything",
    )
    manifest_root, prompts = _write_registry(
        tmp_path / "unknown",
        {"unknown.yaml": unknown_manifest},
        {"test.read.md": "read only"},
    )
    with pytest.raises(SkillRegistryError, match="unknown Tool"):
        SkillRegistry(tools, manifest_root=manifest_root, prompt_registry=prompts)

    unknown_feature_manifest = _MANIFEST.replace(
        "model_policy:",
        "feature_tools: [unknown.feature_read]\nmodel_policy:",
    )
    manifest_root, prompts = _write_registry(
        tmp_path / "unknown-feature",
        {"unknown-feature.yaml": unknown_feature_manifest},
        {"test.read.md": "read only"},
    )
    with pytest.raises(SkillRegistryError, match="unknown feature Tool"):
        SkillRegistry(tools, manifest_root=manifest_root, prompt_registry=prompts)

    risk_manifest = _MANIFEST.replace(
        "identity.get_current_context",
        "injection_scheduling.generate_preview",
    )
    manifest_root, prompts = _write_registry(
        tmp_path / "risk",
        {"risk.yaml": risk_manifest},
        {"test.read.md": "read only"},
    )
    with pytest.raises(SkillRegistryError, match="exceeds maximum risk"):
        SkillRegistry(tools, manifest_root=manifest_root, prompt_registry=prompts)


def test_skill_discovery_reuses_tool_iam_and_cannot_expand_permissions() -> None:
    registry = SkillRegistry(build_default_tool_registry())

    allowed = {skill.manifest.id for skill in registry.available(_context())}
    denied = {skill.manifest.id for skill in registry.available(_context(denied=True))}

    assert "injection_scheduling.read_context" in allowed
    assert "injection_scheduling.read_context" not in denied
    assert "injection_scheduling.preview_advisor" in allowed
    assert registry.authorized_tool_names(
        (registry.resolve("injection_scheduling.read_context"),),
        _context(),
    ) == (
        "injection_scheduling.compare_previews",
        "injection_scheduling.get_backlog",
        "injection_scheduling.get_plan_context",
    )
