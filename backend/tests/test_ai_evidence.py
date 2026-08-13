import asyncio
import json
from datetime import UTC, datetime

import pytest
from app.core.config import Settings
from app.schemas.ai import (
    AIEvidenceReferenceV1,
    AIEvidenceSourceLevel,
    AIServerPageContext,
)
from app.services.ai.evidence import (
    EvidenceError,
    build_tool_evidence,
    reauthorize_evidence_open,
)
from app.services.ai.providers import ProviderToolCall
from app.services.ai.tool_executor import ToolExecutionContext, ToolExecutor
from app.services.ai.tool_registry import build_default_tool_registry
from app.services.auth import AuthContext, AuthGrantContext
from pydantic import ValidationError


def _user(*, factory_id: str = "huaxing") -> AuthContext:
    grant = AuthGrantContext(
        role_id="evidence-role",
        role_name="Evidence 测试",
        factory_id=factory_id,
        department="production",
        permissions=frozenset({"injection_scheduling:read"}),
        binding_id=f"evidence-grant-{factory_id}",
    )
    return AuthContext(
        id="evidence-user",
        username="private-evidence-user",
        display_name="Evidence 用户",
        roles=("测试",),
        role_codes=("test",),
        permissions=frozenset({"injection_scheduling:read"}),
        factory_scopes=(factory_id,),
        department_scopes=("production",),
        grants=(grant,),
        active_permission_codes=frozenset({"injection_scheduling:read"}),
    )


def _context(factory_id: str = "huaxing") -> ToolExecutionContext:
    return ToolExecutionContext(
        None,
        _user(factory_id=factory_id),
        "request-evidence",
        AIServerPageContext(
            verified_route_name="injection-scheduling-v2",
            verified_path="/modules/production/injection-scheduling",
            verified_factory_id=factory_id,
            verified_module_id="injection-scheduling",
            knowledge_id="injection-scheduling",
            allowed_tool_groups=("identity", "module_knowledge", "injection_scheduling"),
        ),
    )


def _reference(**overrides: object) -> AIEvidenceReferenceV1:
    values: dict[str, object] = {
        "evidence_id": "ev:1234567890abcdef",
        "source_level": AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE,
        "source_name": "injection_scheduling.get_plan_context",
        "factory_id": "huaxing",
        "as_of": datetime(2026, 8, 12, 2, tzinfo=UTC),
        "entity_type": "scheduling_plan",
        "entity_id": "plan-1",
        "entity_revision": 7,
        "content_hash": f"sha256:{'a' * 64}",
        "truncated": False,
        "cursor": None,
    }
    values.update(overrides)
    return AIEvidenceReferenceV1.model_validate(values)


def test_evidence_schema_requires_timezone_hash_factory_and_closed_fields() -> None:
    reference = _reference()

    assert reference.access_policy == "REAUTHORIZE_ON_OPEN"
    invalid = (
        {"as_of": "2026-08-12T10:00:00"},
        {"factory_id": "group"},
        {"content_hash": "sha256:not-a-hash"},
        {"entity_id": None},
        {"password": "must-not-enter-evidence"},
    )
    for patch in invalid:
        with pytest.raises(ValidationError):
            AIEvidenceReferenceV1.model_validate(
                {**reference.model_dump(mode="json"), **patch}
            )


def test_tool_evidence_hash_is_stable_and_summary_contains_no_sensitive_fields() -> None:
    registry = build_default_tool_registry()
    spec = registry.resolve("injection_scheduling.get_plan_context")
    assert spec is not None
    data = {
        "source_type": "FORMAL",
        "factory_id": "huaxing",
        "as_of": "2026-08-12T10:00:00+08:00",
        "entity_type": "scheduling_plan",
        "entity_id": "plan-1",
        "entity_revision": 7,
        "truncated": True,
        "cursor": "next-20",
        "password": "private-value-that-is-hashed-but-never-copied",
    }

    first = build_tool_evidence(
        spec=spec,
        request_id="request-1",
        call_id="call-1",
        data=data,
        factory_id="huaxing",
        truncated=True,
    )
    second = build_tool_evidence(
        spec=spec,
        request_id="request-1",
        call_id="call-1",
        data=data,
        factory_id="huaxing",
        truncated=True,
    )
    changed = build_tool_evidence(
        spec=spec,
        request_id="request-1",
        call_id="call-1",
        data={**data, "entity_revision": 8},
        factory_id="huaxing",
        truncated=True,
    )

    assert first == second
    assert first.content_hash != changed.content_hash
    assert first.cursor == "next-20"
    assert first.truncated is True
    serialized = json.dumps(first.model_dump(mode="json"))
    assert "password" not in serialized
    assert "private-value" not in serialized


def test_evidence_source_and_formal_factory_fail_closed() -> None:
    registry = build_default_tool_registry()
    spec = registry.resolve("injection_scheduling.get_plan_context")
    assert spec is not None
    with pytest.raises(EvidenceError, match="source level"):
        build_tool_evidence(
            spec=spec,
            request_id="request-invalid",
            call_id="call-invalid",
            data={"as_of": "2026-08-12T10:00:00+08:00"},
            factory_id="huaxing",
            truncated=False,
        )
    with pytest.raises(EvidenceError, match="factory"):
        build_tool_evidence(
            spec=spec,
            request_id="request-invalid",
            call_id="call-invalid",
            data={
                "source_type": "FORMAL",
                "as_of": "2026-08-12T10:00:00+08:00",
            },
            factory_id=None,
            truncated=False,
        )


def test_tool_executor_adds_evidence_only_when_both_nif_flags_are_enabled() -> None:
    registry = build_default_tool_registry()
    call = ProviderToolCall(
        call_id="call-identity-evidence",
        name="identity.get_current_context",
        arguments_json="{}",
    )
    context = ToolExecutionContext(None, _user(), "request-identity-evidence")

    disabled = asyncio.run(
        ToolExecutor(registry, Settings(_env_file=None)).execute(call, context)
    )
    enabled = asyncio.run(
        ToolExecutor(
            registry,
            Settings(
                _env_file=None,
                ai_nif_runtime_enabled=True,
                ai_evidence_v1_enabled=True,
            ),
        ).execute(call, context)
    )

    assert "evidence" not in json.loads(disabled.provider_output_json)
    payload = json.loads(enabled.provider_output_json)
    assert payload["evidence"][0]["source_level"] == (
        "AUTHENTICATED_SERVER_CONTEXT"
    )
    assert payload["evidence"][0]["source_name"] == "identity.get_current_context"


def test_evidence_open_reauthorizes_current_tool_and_factory_scope() -> None:
    registry = build_default_tool_registry()
    evidence = _reference()

    assert reauthorize_evidence_open(evidence, registry=registry, context=_context())
    assert not reauthorize_evidence_open(
        evidence,
        registry=registry,
        context=_context("huakang-b"),
    )
    assert not reauthorize_evidence_open(
        _reference(source_name="unknown.read"),
        registry=registry,
        context=_context(),
    )
