import asyncio
import importlib
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from app.core.config import Settings
from fastapi.testclient import TestClient
from pydantic import ValidationError

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = BACKEND_DIR.parent
TEST_TMP_DIR = BACKEND_DIR / ".pytest-tmp"
ADMIN_TEST_PASSWORD = "AdminSeed123!"


class _RestoringAppTestClient(TestClient):
    """Restore pytest-collected app modules after the env-specific app reload."""

    def __init__(self, app, original_modules: dict[str, object]):
        super().__init__(app)
        self._original_app_modules = original_modules

    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            for module_name in list(sys.modules):
                if module_name == "app" or module_name.startswith("app."):
                    del sys.modules[module_name]
            sys.modules.update(self._original_app_modules)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.schemas.ai import AIPageContextInput, AIServerPageContext
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    build_server_page_context,
    render_server_page_context,
)
from app.services.ai.module_knowledge import (
    ModuleKnowledgeError,
    ModuleKnowledgeRegistry,
    UnknownModuleKnowledgeError,
    module_knowledge_registry,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.ai.tools.identity_tools import (
    IdentityGetCurrentContextInput,
    get_current_context,
)
from app.services.ai.tools.module_help_tools import (
    ModuleGetHelpInput,
    get_module_help,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
    AuthProfileContext,
)


def _auth_context(
    *,
    allowed: bool,
    explicitly_denied: bool = False,
) -> AuthContext:
    grants = (
        AuthGrantContext(
            role_id="role-scheduling-reader",
            role_name="排产读取",
            factory_id="huaxing",
            department="production",
            permissions=frozenset({"injection_scheduling:read"}),
            binding_id="grant-huaxing-read",
        ),
    ) if allowed else ()
    overrides = (
        AuthOverrideContext(
            id="deny-huaxing-read",
            permission_code="injection_scheduling:read",
            effect="deny",
            factory_id="huaxing",
            department="production",
        ),
    ) if explicitly_denied else ()
    return AuthContext(
        id="ai-module-user",
        username="ai-module-user",
        display_name="模块帮助测试用户",
        roles=("排产测试",),
        role_codes=("test",),
        permissions=frozenset({"injection_scheduling:read"}),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=grants,
        profile=AuthProfileContext(
            primary_factory_id="huaxing",
            primary_department="production",
        ),
        overrides=overrides,
        active_permission_codes=frozenset({"injection_scheduling:read"}),
    )


def _page_context(factory_id: str | None = "huaxing") -> AIPageContextInput:
    return AIPageContextInput(
        route_name="injection-scheduling-v2",
        path="/modules/production/injection-scheduling",
        factory_id=factory_id,
        module_id="injection-scheduling",
        selected_entity=None,
    )


def _make_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    TEST_TMP_DIR.mkdir(exist_ok=True)
    database_url = f"sqlite:///{TEST_TMP_DIR / f'ai_module_{uuid4().hex}.db'}"
    fake_environment = {
        "DATABASE_URL": database_url,
        "SEED_ADMIN_PASSWORD": ADMIN_TEST_PASSWORD,
        "APP_ENV": "development",
        "AI_ENABLED": "true",
        "AI_PROVIDER": "fake",
        "AI_REGION": "cn-beijing",
        "AI_WORKSPACE_ID": "",
        "DASHSCOPE_API_KEY": "",
        "AI_DEFAULT_MODEL": "fake-model",
        "AI_BASE_URL": "",
        "AI_CLOUD_VISION_ENABLED": "false",
        "AI_NIF_RUNTIME_ENABLED": "false",
        "AI_PROVIDER_CAPABILITY_ROUTER_ENABLED": "false",
        "AI_SKILL_ROUTER_ENABLED": "false",
        "AI_EVIDENCE_V1_ENABLED": "false",
        "AI_CONTROLLED_APPLY_ENABLED": "false",
        "AI_SEMANTIC_GATEWAY_ENABLED": "false",
        "AI_KNOWLEDGE_HUB_ENABLED": "false",
        "AI_ARTIFACT_WORKFLOWS_ENABLED": "false",
        "AI_VISION_TOOL_COMPARISON_ENABLED": "false",
        "AI_PILOT_ENABLED": "true",
        "AI_PILOT_USER_IDS": "user-admin",
        "AI_PILOT_FACTORY_IDS": "huaxing",
        "AI_RUNTIME_DISABLE_PATH": "/app/backend/control/ai.disabled",
        "AI_PILOT_REQUESTS_PER_MINUTE": "60",
        "AI_PILOT_DAILY_TOKEN_BUDGET": "100000000",
    }
    for name, value in fake_environment.items():
        monkeypatch.setenv(name, value)
    original_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name == "app" or module_name.startswith("app.")
    }
    for module_name in list(sys.modules):
        if module_name == "app" or module_name.startswith("app."):
            del sys.modules[module_name]
    main = importlib.import_module("app.main")
    return _RestoringAppTestClient(main.app, original_modules)


def _login_admin(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": ADMIN_TEST_PASSWORD},
    )
    assert response.status_code == 200


def _chat_payload(page_context: dict[str, object]) -> dict[str, object]:
    return {
        "messages": [
            {
                "role": "user",
                "content": [{"type": "input_text", "text": "这个页面怎么用？"}],
            }
        ],
        "page_context": page_context,
    }


def _valid_page_payload() -> dict[str, object]:
    return {
        "route_name": "injection-scheduling-v2",
        "path": "/modules/production/injection-scheduling",
        "factory_id": "huaxing",
        "module_id": "injection-scheduling",
        "selected_entity": None,
    }


def test_context_builder_allows_only_exact_route_and_canonical_factory() -> None:
    allowed = build_server_page_context(_page_context(), _auth_context(allowed=True))

    assert allowed == AIServerPageContext(
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
    )
    rendered = render_server_page_context(allowed)
    assert rendered is not None
    assert "injection-scheduling-v2" in rendered
    assert "/modules/production/injection-scheduling" in rendered
    assert "huaxing" in rendered

    with pytest.raises(AIPageContextValidationError):
        build_server_page_context(
            _page_context("not-a-factory"),
            _auth_context(allowed=True),
        )


def test_explicit_deny_removes_factory_from_model_and_scheduling_group() -> None:
    denied_user = _auth_context(allowed=True, explicitly_denied=True)
    denied = build_server_page_context(_page_context(), denied_user)

    assert denied is not None
    assert denied.verified_factory_id is None
    assert denied.allowed_tool_groups == ("identity", "module_knowledge")
    rendered = render_server_page_context(denied)
    assert rendered is not None
    assert "huaxing" not in rendered
    identity = get_current_context(
        ToolExecutionContext(None, denied_user, "request-denied", denied),
        IdentityGetCurrentContextInput(),
    )
    assert identity.current_factory is None


@pytest.mark.parametrize(
    "patch",
    [
        {"route_name": "injection-scheduling"},
        {"path": "/modules/production/injection-scheduling/other"},
        {"module_id": "pricing"},
        {"selected_entity": {"type": "task", "id": "forged-task"}},
        {"unexpected": "client-owned-state"},
    ],
)
def test_page_context_schema_rejects_unknown_route_module_entity_and_extra(
    patch: dict[str, object],
) -> None:
    payload = _valid_page_payload()
    payload.update(patch)
    with pytest.raises(ValidationError):
        AIPageContextInput.model_validate(payload)


def test_registry_is_group_fail_closed_without_verified_page_context() -> None:
    registry = build_default_tool_registry()
    user = _auth_context(allowed=True)
    without_page = ToolExecutionContext(None, user, "request-no-page")
    forged_page = ToolExecutionContext(
        None,
        user,
        "request-forged-page",
        {
            "verified_factory_id": "huaxing",
            "allowed_tool_groups": ["injection_scheduling", "module_knowledge"],
        },
    )

    assert [item.name for item in registry.provider_definitions(without_page)] == [
        "identity.get_current_context"
    ]
    assert [item.name for item in registry.provider_definitions(forged_page)] == [
        "identity.get_current_context"
    ]

    allowed_page = build_server_page_context(_page_context(), user)
    assert allowed_page is not None
    allowed_names = {
        item.name
        for item in registry.provider_definitions(
            ToolExecutionContext(None, user, "request-allowed-page", allowed_page)
        )
    }
    assert allowed_names == {
        "identity.get_current_context",
        "knowledge.get_module_help",
        "injection_scheduling.get_plan_context",
        "injection_scheduling.get_backlog",
        "injection_scheduling.compare_previews",
    }

    denied_page = build_server_page_context(
        _page_context(),
        _auth_context(allowed=True, explicitly_denied=True),
    )
    assert denied_page is not None
    denied_names = {
        item.name
        for item in registry.provider_definitions(
            ToolExecutionContext(None, user, "request-denied-page", denied_page)
        )
    }
    assert denied_names == {
        "identity.get_current_context",
        "knowledge.get_module_help",
    }


def test_fixed_registry_loads_versioned_help_and_rejects_path_like_ids() -> None:
    document = module_knowledge_registry.load_for_route("injection-scheduling-v2")

    assert document.metadata.knowledge_id == "injection-scheduling"
    assert document.metadata.knowledge_version == "1.0.0"
    assert document.metadata.route_names == ("injection-scheduling-v2",)
    assert document.metadata.source_files[-1] == "src/data/enterpriseMock.ts"
    assert document.metadata.status_labels["PUBLISHED"].startswith("当前执行")
    assert document.metadata.status_labels["DRAFT"].startswith("排产草案")
    assert "只读演示数据" in document.body_markdown
    assert "ERP" in document.body_markdown

    with pytest.raises(UnknownModuleKnowledgeError):
        module_knowledge_registry.load_for_route("unknown-route")
    with pytest.raises(UnknownModuleKnowledgeError):
        module_knowledge_registry.load("../../backend/.env")


def test_loader_fails_closed_for_missing_incomplete_and_nonexistent_sources(
    tmp_path: Path,
) -> None:
    with pytest.raises(ModuleKnowledgeError):
        ModuleKnowledgeRegistry(
            repository_root=tmp_path,
            knowledge_files={"injection-scheduling": "../outside.md"},
        )

    missing_registry = ModuleKnowledgeRegistry(
        repository_root=tmp_path,
        knowledge_files={"injection-scheduling": "docs/missing.md"},
    )
    with pytest.raises(ModuleKnowledgeError, match="unavailable"):
        missing_registry.load("injection-scheduling")

    help_path = tmp_path / "docs" / "help.md"
    help_path.parent.mkdir(parents=True)
    help_path.write_text(
        '<!-- ai-module-knowledge-metadata\n{}\n-->\n# incomplete',
        encoding="utf-8",
    )
    incomplete_registry = ModuleKnowledgeRegistry(
        repository_root=tmp_path,
        knowledge_files={"injection-scheduling": "docs/help.md"},
    )
    with pytest.raises(ModuleKnowledgeError, match="metadata is invalid"):
        incomplete_registry.load("injection-scheduling")

    production_document = (
        REPOSITORY_ROOT / "docs" / "ai" / "modules" / "injection-scheduling.md"
    ).read_text(encoding="utf-8")
    help_path.write_text(
        production_document.replace(
            '"src/router/index.ts"',
            '"missing/source.py"',
            1,
        ),
        encoding="utf-8",
    )
    nonexistent_source_registry = ModuleKnowledgeRegistry(
        repository_root=tmp_path,
        knowledge_files={"injection-scheduling": "docs/help.md"},
    )
    with pytest.raises(ModuleKnowledgeError, match="source file is unavailable"):
        nonexistent_source_registry.load("injection-scheduling")


def test_module_help_tool_uses_only_verified_server_context() -> None:
    user = _auth_context(allowed=True)
    verified = build_server_page_context(_page_context(), user)
    assert verified is not None

    result = get_module_help(
        ToolExecutionContext(None, user, "request-help", verified),
        ModuleGetHelpInput(),
    )
    assert result.source_type == "VERSIONED_MODULE_KNOWLEDGE"
    assert result.knowledge_id == "injection-scheduling"
    assert result.status_labels["PUBLISHED"].startswith("当前执行")
    assert result.status_labels["DRAFT"].startswith("排产草案")
    assert any("demo" in claim for claim in result.prohibited_claims)

    with pytest.raises(ValueError, match="verified module context"):
        get_module_help(
            ToolExecutionContext(None, user, "request-unverified"),
            ModuleGetHelpInput(),
        )


def test_identity_and_module_help_never_checkout_database_session() -> None:
    # ``test_ai_api`` deliberately reloads ``app.*`` modules. Resolve the security
    # boundary types at test runtime so this assertion never mixes pre/post-reload
    # Pydantic classes; production code must keep its fail-closed isinstance check.
    current_schemas = importlib.import_module("app.schemas.ai")
    current_context_builder = importlib.import_module(
        "app.services.ai.context_builder"
    )
    current_providers = importlib.import_module("app.services.ai.providers")
    current_executor = importlib.import_module("app.services.ai.tool_executor")
    current_registry = importlib.import_module("app.services.ai.tool_registry")

    user = _auth_context(allowed=True)
    page_input = current_schemas.AIPageContextInput.model_validate(
        _page_context().model_dump()
    )
    verified = current_context_builder.build_server_page_context(page_input, user)
    assert verified is not None
    checkout_count = 0

    def forbidden_session_factory():
        nonlocal checkout_count
        checkout_count += 1
        raise AssertionError("non-database tools must not checkout a Session")

    registry = current_registry.build_default_tool_registry()
    executor = current_executor.ToolExecutor(registry, Settings(_env_file=None))
    context = current_executor.ToolExecutionContext(
        None,
        user,
        "request-non-db-tools",
        verified,
        session_factory=forbidden_session_factory,
    )

    outcomes = [
        asyncio.run(
            executor.execute(
                current_providers.ProviderToolCall(
                    call_id=f"call-non-db-{index}",
                    name=tool_name,
                    arguments_json="{}",
                ),
                context,
            )
        )
        for index, tool_name in enumerate(
            ("identity.get_current_context", "knowledge.get_module_help"),
            start=1,
        )
    ]

    assert all(outcome.ok for outcome in outcomes)
    assert checkout_count == 0


def test_api_injects_only_server_verified_context_and_registered_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _make_client(monkeypatch) as client:
        _login_admin(client)
        ai_api = importlib.import_module("app.api.ai")
        fake_module = importlib.import_module("app.services.ai.providers.fake")
        provider = fake_module.FakeProvider()
        client.app.dependency_overrides[ai_api._provider] = lambda: provider

        invalid_factory = _valid_page_payload()
        invalid_factory["factory_id"] = "not-a-factory"
        invalid_response = client.post(
            "/api/ai/responses",
            json=_chat_payload(invalid_factory),
        )
        selected_entity = _valid_page_payload()
        selected_entity["selected_entity"] = {"type": "task", "id": "T-1"}
        entity_response = client.post(
            "/api/ai/responses",
            json=_chat_payload(selected_entity),
        )
        response = client.post(
            "/api/ai/responses",
            json=_chat_payload(_valid_page_payload()),
        )

    assert invalid_response.status_code == 422
    assert invalid_response.json()["detail"] == {
        "code": "AI_INVALID_PAGE_CONTEXT",
        "message": "当前页面上下文无效，请刷新页面后重试。",
        "retryable": False,
    }
    assert "not-a-factory" not in invalid_response.text
    assert entity_response.status_code == 422
    assert response.status_code == 200
    assert len(provider.requests) == 1
    provider_request = provider.requests[0]
    assert [message.role for message in provider_request.input] == [
        "system",
        "system",
        "user",
    ]
    server_context = provider_request.input[1].content
    assert "injection-scheduling-v2" in server_context
    assert "/modules/production/injection-scheduling" in server_context
    assert "huaxing" in server_context
    assert "selected_entity" not in server_context
    assert {tool.name for tool in provider_request.tools} == {
        "identity.get_current_context",
        "knowledge.get_module_help",
        "injection_scheduling.get_plan_context",
        "injection_scheduling.get_backlog",
        "injection_scheduling.compare_previews",
        "injection_scheduling.generate_preview",
    }
    assert all(
        tool.parameters["additionalProperties"] is False
        for tool in provider_request.tools
    )
