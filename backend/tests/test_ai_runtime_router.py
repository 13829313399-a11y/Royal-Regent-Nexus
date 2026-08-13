import asyncio

import pytest
from app.core.config import Settings
from app.schemas.ai import AIServerPageContext, AIToolRiskLevel
from app.services.ai.orchestrator import AIOrchestrator, ValidatedChatInput
from app.services.ai.providers import ProviderMessage
from app.services.ai.providers.fake import FakeProvider
from app.services.ai.runtime.plan import RuntimePlan, RuntimePlanBuilder
from app.services.ai.skills.contracts import SkillRegistryError
from app.services.ai.skills.registry import SkillRegistry
from app.services.ai.skills.router import IntentComplexity, SkillRouter
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext, AuthGrantContext
from pydantic import ValidationError


def _context() -> ToolExecutionContext:
    grant = AuthGrantContext(
        role_id="runtime-role",
        role_name="Runtime 测试",
        factory_id="huaxing",
        department="production",
        permissions=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
        binding_id="runtime-grant",
    )
    user = AuthContext(
        id="runtime-user",
        username="runtime-user",
        display_name="Runtime 用户",
        roles=("测试",),
        role_codes=("test",),
        permissions=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=(grant,),
        active_permission_codes=frozenset(
            {"injection_scheduling:read", "injection_scheduling:edit"}
        ),
    )
    return ToolExecutionContext(
        None,
        user,
        "request-runtime",
        AIServerPageContext(
            verified_route_name="injection-scheduling-v2",
            verified_path="/modules/production/injection-scheduling",
            verified_factory_id="huaxing",
            verified_module_id="injection-scheduling",
            knowledge_id="injection-scheduling",
            allowed_tool_groups=(
                "identity",
                "module_knowledge",
                "injection_scheduling",
            ),
        ),
    )


def test_rules_route_chinese_page_file_and_image_hints_deterministically() -> None:
    router = SkillRouter(
        SkillRegistry(
            build_default_tool_registry(
                artifact_workflows_enabled=True,
                vision_tool_comparison_enabled=True,
            )
        )
    )
    context = _context()

    cases = (
        ("帮我看看积压订单", False, False, "injection_scheduling.read_context"),
        (
            "分析并优化排产，生成候选方案",
            False,
            False,
            "injection_scheduling.preview_advisor",
        ),
        ("解释这个页面怎么用", False, False, "system.module_tutor"),
        ("把这个文档翻译成中文", True, False, "files.document_translation"),
        (
            "识别 Excel 表头并预览字段映射",
            True,
            False,
            "files.workbook_mapping_preview",
        ),
        ("说明这张截图", False, True, "vision.screenshot_observation"),
    )
    for text, has_file, has_image, expected in cases:
        first = router.route(
            text=text,
            context=context,
            has_file=has_file,
            has_image=has_image,
        )
        second = router.route(
            text=text,
            context=context,
            has_file=has_file,
            has_image=has_image,
        )
        assert first == second
        assert first.primary_skill.manifest.id == expected
    assert router.route(text="为什么排产不同", context=context).complexity is (
        IntentComplexity.ANALYTICAL
    )


def test_closed_classifier_unknown_intent_and_injection_use_deterministic_fallback() -> (
    None
):
    router = SkillRouter(SkillRegistry(build_default_tool_registry()))
    context = _context()

    classified = router.route(
        text="普通问题",
        context=context,
        model_classification={
            "intent": "query_backlog",
            "complexity": "SIMPLE",
        },
    )
    unknown = router.route(
        text="普通问题",
        context=context,
        model_classification={
            "intent": "run_arbitrary_sql",
            "complexity": "SIMPLE",
            "tool": "unknown.execute",
        },
    )

    assert classified.primary_skill.manifest.id == "injection_scheduling.read_context"
    assert classified.source == "closed_classifier"
    assert unknown.primary_skill.manifest.id == "business.current_page_query"
    assert unknown.source == "deterministic_fallback"


def test_runtime_plan_rejects_unknown_tool_skill_step_risk_and_token_escalation() -> (
    None
):
    registry = SkillRegistry(build_default_tool_registry())
    builder = RuntimePlanBuilder(registry)
    context = _context()

    plan = builder.build(
        primary_skill_id="injection_scheduling.read_context",
        context=context,
    )
    assert plan.maximum_risk is AIToolRiskLevel.READ_ONLY
    assert set(plan.allowed_tool_names) == {
        "injection_scheduling.compare_previews",
        "injection_scheduling.get_backlog",
        "injection_scheduling.get_plan_context",
    }
    with pytest.raises(SkillRegistryError, match="unknown Skill"):
        builder.build(primary_skill_id="unknown.injected_skill", context=context)
    with pytest.raises(SkillRegistryError, match="unauthorized Tool"):
        builder.build(
            primary_skill_id="injection_scheduling.read_context",
            context=context,
            proposed_tool_names=("unknown.execute",),
        )
    with pytest.raises(SkillRegistryError, match="step limit"):
        builder.build(
            primary_skill_id="injection_scheduling.read_context",
            context=context,
            proposed_max_steps=6,
        )
    with pytest.raises(SkillRegistryError, match="risk limit"):
        builder.build(
            primary_skill_id="injection_scheduling.read_context",
            context=context,
            proposed_maximum_risk=AIToolRiskLevel.CONSEQUENTIAL_WRITE,
        )
    with pytest.raises(SkillRegistryError, match="token budget"):
        builder.build(
            primary_skill_id="injection_scheduling.read_context",
            context=context,
            proposed_token_budget=12_000,
        )
    with pytest.raises(ValidationError):
        RuntimePlan.model_validate(
            {
                **plan.model_dump(mode="json"),
                "primary_skill_id": "https://evil.example/skill",
            }
        )


def test_supporting_skill_can_only_reduce_to_common_authorized_tools() -> None:
    registry = SkillRegistry(build_default_tool_registry())
    builder = RuntimePlanBuilder(registry)
    context = _context()

    plan = builder.build(
        primary_skill_id="injection_scheduling.read_context",
        supporting_skill_ids=("business.current_page_query",),
        context=context,
    )

    assert set(plan.allowed_tool_names) == {
        "injection_scheduling.compare_previews",
        "injection_scheduling.get_backlog",
        "injection_scheduling.get_plan_context",
    }


def test_fake_provider_skill_selection_and_tool_surface_are_repeatable() -> None:
    settings = Settings(
        _env_file=None,
        app_env="test",
        ai_enabled=True,
        ai_nif_runtime_enabled=True,
        ai_provider_capability_router_enabled=True,
        ai_skill_router_enabled=True,
        ai_provider="fake",
        ai_default_model="fake-model",
        ai_vision_model="fake-model",
        ai_max_tool_rounds=4,
    )
    tools = build_default_tool_registry()
    provider = FakeProvider()
    context = _context()
    chat = ValidatedChatInput(
        messages=(ProviderMessage(role="user", content="帮我查看积压订单"),),
        message_count=1,
        input_chars=8,
        server_page_context=context.page_context,
    )
    orchestrator = AIOrchestrator(
        provider=provider,
        settings=settings,
        tool_registry=tools,
        tool_executor=ToolExecutor(tools, settings),
    )

    async def collect():
        return [
            event
            async for event in orchestrator.stream(
                chat,
                request_id="request-skill-integration",
                user_id="runtime-user",
                tool_context=context,
            )
        ]

    events = asyncio.run(collect())
    started = events[0]
    completed = events[-1]
    request = provider.requests[0]

    assert started.payload["skill_id"] == "injection_scheduling.read_context"
    assert completed.payload["skill_id"] == "injection_scheduling.read_context"
    assert started.payload["prompt_hash"] == completed.payload["prompt_hash"]
    assert started.payload["tool_versions"] == completed.payload["tool_versions"]
    assert all(item.endswith("@1.0.0") for item in started.payload["tool_versions"])
    assert {tool.name for tool in request.tools} == {
        "injection_scheduling.compare_previews",
        "injection_scheduling.get_backlog",
        "injection_scheduling.get_plan_context",
    }
    assert isinstance(request.input[0], ProviderMessage)
    assert "<NEXUS_CORE_POLICY>" in request.input[0].content
    assert "identity.get_current_context" not in {tool.name for tool in request.tools}
