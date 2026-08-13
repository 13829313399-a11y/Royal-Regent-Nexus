from dataclasses import replace

import pytest
from app.core.config import Settings
from app.schemas.ai import AIServerPageContext, AIToolRiskLevel, StrictToolInput
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import (
    ToolRegistry,
    ToolSpec,
    build_default_tool_registry,
)
from app.services.auth import (
    AuthContext,
    AuthGrantContext,
    AuthOverrideContext,
)
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class FactoryArguments(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=32)


class OpenArguments(BaseModel):
    model_config = ConfigDict(extra="ignore")

    factory_id: str


def auth_context(
    *,
    grants: tuple[AuthGrantContext, ...] = (),
    overrides: tuple[AuthOverrideContext, ...] = (),
) -> AuthContext:
    return AuthContext(
        id="user-ai-test",
        username="ai-test-user",
        display_name="AI 测试用户",
        roles=("测试角色",),
        role_codes=("test",),
        permissions=frozenset({"injection_scheduling:read"}),
        factory_scopes=("huaxing",),
        department_scopes=("production",),
        grants=grants,
        overrides=overrides,
        active_permission_codes=frozenset({"injection_scheduling:read"}),
    )


def read_spec(name: str = "test.read") -> ToolSpec:
    return ToolSpec(
        name=name,
        description="读取测试数据。",
        input_model=FactoryArguments,
        risk_level=AIToolRiskLevel.READ_ONLY,
        executor=lambda _context, arguments: {"factory_id": arguments.factory_id},
        serializer=lambda value: value,
        display_label="正在读取测试数据",
        tool_group="test",
        required_permission="injection_scheduling:read",
        allowed_departments=frozenset({"production"}),
        factory_argument="factory_id",
    )


def server_page_context() -> AIServerPageContext:
    return AIServerPageContext(
        verified_route_name="injection-scheduling-v2",
        verified_path="/modules/production/injection-scheduling",
        verified_factory_id="huaxing",
        verified_module_id="injection-scheduling",
        knowledge_id="injection-scheduling",
        allowed_tool_groups=("test",),
    )


def test_default_registry_exposes_only_closed_exact_identity_tool() -> None:
    registry = build_default_tool_registry()
    context = ToolExecutionContext(
        db=None,
        user=auth_context(),
        request_id="request-registry",
    )

    definitions = registry.provider_definitions(context)

    assert [item.name for item in definitions] == ["identity.get_current_context"]
    assert definitions[0].parameters["additionalProperties"] is False
    identity_spec = registry.resolve("identity.get_current_context")
    scheduling_spec = registry.resolve("injection_scheduling.get_plan_context")
    assert identity_spec is not None
    assert scheduling_spec is not None
    assert identity_spec.requires_db is False
    assert scheduling_spec.requires_db is True
    assert "requires_db" not in definitions[0].parameters
    assert registry.resolve("identity.get_current_contex") is None
    assert registry.resolve(" identity.get_current_context") is None
    assert registry.resolve("https://example.com/tool") is None


def test_registry_rejects_duplicate_names_and_open_input_models() -> None:
    spec = read_spec()
    with pytest.raises(ValueError, match="unique"):
        ToolRegistry((spec, spec))

    with pytest.raises(ValueError, match="extra='forbid'"):
        replace(spec, name="test.open", input_model=OpenArguments)

    with pytest.raises(ValueError, match="invalid tool name"):
        replace(spec, name="https://example.com/read")


def test_registry_filters_permissioned_tools_with_canonical_explicit_deny() -> None:
    grant = AuthGrantContext(
        role_id="role-reader",
        role_name="排产读取",
        factory_id="huaxing",
        department="production",
        permissions=frozenset({"injection_scheduling:read"}),
        binding_id="grant-reader",
    )
    denied_user = auth_context(
        grants=(grant,),
        overrides=(
            AuthOverrideContext(
                id="deny-ai-read",
                permission_code="injection_scheduling:read",
                effect="deny",
                factory_id="huaxing",
                department="production",
            ),
        ),
    )
    allowed_user = auth_context(grants=(grant,))
    registry = ToolRegistry((read_spec(),))

    denied = registry.provider_definitions(
        ToolExecutionContext(
            None,
            denied_user,
            "request-denied",
            page_context=server_page_context(),
        )
    )
    allowed = registry.provider_definitions(
        ToolExecutionContext(
            None,
            allowed_user,
            "request-allowed",
            page_context=server_page_context(),
        )
    )

    assert denied == ()
    assert [item.name for item in allowed] == ["test.read"]


def test_tool_execution_limits_are_bounded_settings() -> None:
    settings = Settings(_env_file=None)

    assert settings.ai_max_tool_rounds == 4
    assert settings.ai_max_tool_result_rows == 50
    assert settings.ai_max_tool_result_bytes == 65_536
    assert settings.ai_max_tool_result_fields == 64

    invalid_values = (
        {"ai_request_timeout_seconds": 0},
        {"ai_request_timeout_seconds": 121},
        {"ai_max_tool_rounds": -1},
        {"ai_max_tool_rounds": 7},
        {"ai_max_tool_result_rows": 0},
        {"ai_max_tool_result_rows": 51},
        {"ai_max_tool_result_bytes": 0},
        {"ai_max_tool_result_bytes": 65_537},
        {"ai_max_tool_result_fields": 0},
        {"ai_max_tool_result_fields": 65},
        {"ai_max_input_messages": 0},
        {"ai_max_input_messages": 13},
        {"ai_max_input_message_chars": 0},
        {"ai_max_input_message_chars": 8_001},
        {"ai_max_input_chars": 0},
        {"ai_max_input_chars": 40_001},
    )
    for invalid in invalid_values:
        with pytest.raises(ValidationError):
            Settings(_env_file=None, **invalid)
