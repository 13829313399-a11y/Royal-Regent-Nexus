from dataclasses import replace

import pytest
from app.schemas.ai import AIToolRiskLevel, StrictToolInput
from app.services.ai.tool_registry import (
    ToolIdempotency,
    ToolRegistry,
    ToolRetryPolicy,
    ToolSideEffectClass,
    build_default_tool_registry,
)
from pydantic import Field


class _Arguments(StrictToolInput):
    factory_id: str = Field(min_length=1)


def _legacy_spec():
    from app.services.ai.tool_registry import ToolSpec

    return ToolSpec(
        name="test.read",
        description="读取测试数据。",
        input_model=_Arguments,
        risk_level=AIToolRiskLevel.READ_ONLY,
        executor=lambda _context, arguments: {"factory_id": arguments.factory_id},
        serializer=lambda value: value,
        display_label="读取测试数据",
        tool_group="test",
        required_permission="injection_scheduling:read",
        allowed_departments=frozenset({"production"}),
        factory_argument="factory_id",
    )


def test_legacy_tool_defaults_are_never_retry_and_worker_validation_fails_closed() -> None:
    legacy = _legacy_spec()

    assert legacy.side_effect_class == ToolSideEffectClass.UNCLASSIFIED
    assert legacy.idempotency == ToolIdempotency.UNKNOWN
    assert legacy.retry_policy == ToolRetryPolicy.NEVER_RETRY
    with pytest.raises(ValueError, match="side effect is unclassified"):
        ToolRegistry((legacy,)).validate_worker_contracts()


def test_default_worker_tools_have_explicit_versions_and_execution_contracts() -> None:
    registry = build_default_tool_registry(controlled_apply_enabled=True)

    registry.validate_worker_contracts()
    assert all(spec.version == "1.0.0" for spec in registry.specs)
    assert all(
        spec.side_effect_class != ToolSideEffectClass.UNCLASSIFIED
        and spec.idempotency != ToolIdempotency.UNKNOWN
        for spec in registry.specs
    )
    side_effecting = [
        spec for spec in registry.specs
        if spec.side_effect_class != ToolSideEffectClass.NONE
    ]
    assert {spec.name for spec in side_effecting} == {
        "injection_scheduling.generate_preview",
        "injection_scheduling.propose_apply",
    }
    assert all(spec.retry_policy == ToolRetryPolicy.NEVER_RETRY for spec in side_effecting)


def test_retry_contract_rejects_non_idempotent_or_side_effecting_tools() -> None:
    legacy = _legacy_spec()
    with pytest.raises(ValueError, match="SAFE_TRANSIENT"):
        replace(
            legacy,
            retry_policy=ToolRetryPolicy.SAFE_TRANSIENT,
            side_effect_class=ToolSideEffectClass.PREVIEW_STATE,
            idempotency=ToolIdempotency.NON_IDEMPOTENT,
            risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        )
    with pytest.raises(ValueError, match="SAFE_TRANSIENT"):
        replace(
            legacy,
            retry_policy=ToolRetryPolicy.SAFE_TRANSIENT,
            side_effect_class=ToolSideEffectClass.NONE,
            idempotency=ToolIdempotency.UNKNOWN,
        )
