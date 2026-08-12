from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel

from app.schemas.ai import AIServerPageContext, AIToolAuditPolicy, AIToolRiskLevel
from app.services.ai.providers import ProviderToolDefinition
from app.services.auth import ALLOWED_FACTORY_IDS, authorization_decision

if TYPE_CHECKING:
    from app.services.ai.tool_executor import ToolExecutionContext


ToolCallable = Callable[["ToolExecutionContext", BaseModel], object]
ToolSerializer = Callable[[object], object]

_TOOL_NAME_PATTERN = re.compile(
    r"[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+"
)


class ToolAccessContext(Protocol):
    user: object
    page_context: object | None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    risk_level: AIToolRiskLevel
    executor: ToolCallable
    serializer: ToolSerializer
    display_label: str
    tool_group: str
    required_permission: str | None = None
    allowed_departments: frozenset[str] = frozenset()
    factory_argument: str | None = None
    requires_db: bool = False
    max_result_rows: int = 50
    timeout_seconds: float = 10
    audit_policy: AIToolAuditPolicy = AIToolAuditPolicy.METADATA_ONLY

    def __post_init__(self) -> None:
        if not _TOOL_NAME_PATTERN.fullmatch(self.name):
            raise ValueError(f"invalid tool name: {self.name!r}")
        if not self.description.strip() or not self.display_label.strip():
            raise ValueError("tool description and display label are required")
        if not self.tool_group.strip():
            raise ValueError("tool group is required")
        if not isinstance(self.input_model, type) or not issubclass(
            self.input_model, BaseModel
        ):
            raise TypeError("input_model must be a Pydantic model class")
        if self.input_model.model_config.get("extra") != "forbid":
            raise ValueError("tool input models must set extra='forbid'")
        schema = self.input_model.model_json_schema()
        if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
            raise ValueError("tool input JSON Schema must be a closed object")
        if not callable(self.executor) or not callable(self.serializer):
            raise TypeError("tool executor and serializer must be callable")
        if self.factory_argument and self.factory_argument not in self.input_model.model_fields:
            raise ValueError("factory_argument must name an input model field")
        if self.required_permission and self.factory_argument is None:
            raise ValueError("permissioned tools must declare a factory_argument")
        if self.required_permission and not self.allowed_departments:
            raise ValueError("permissioned tools must declare allowed_departments")
        if self.max_result_rows <= 0 or self.timeout_seconds <= 0:
            raise ValueError("tool result and timeout limits must be positive")

    def provider_definition(self) -> ProviderToolDefinition:
        return ProviderToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_model.model_json_schema(),
        )


class ToolRegistry:
    def __init__(self, specs: Iterable[ToolSpec] = ()) -> None:
        items = tuple(specs)
        by_name = {item.name: item for item in items}
        if len(by_name) != len(items):
            raise ValueError("tool names must be unique")
        self._specs = tuple(sorted(items, key=lambda item: item.name))
        self._by_name = by_name

    @property
    def specs(self) -> tuple[ToolSpec, ...]:
        return self._specs

    def resolve(self, name: str) -> ToolSpec | None:
        return self._by_name.get(name)

    def provider_definitions(
        self,
        context: ToolAccessContext,
    ) -> tuple[ProviderToolDefinition, ...]:
        return tuple(
            spec.provider_definition()
            for spec in self._specs
            if self.is_available(spec, context)
        )

    def available_tool_groups(self, context: ToolAccessContext) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    spec.tool_group
                    for spec in self._specs
                    if self.is_available(spec, context)
                }
            )
        )

    def is_in_request_scope(
        self,
        spec: ToolSpec,
        context: ToolAccessContext,
    ) -> bool:
        if self._by_name.get(spec.name) is not spec:
            return False
        page_context = context.page_context
        if not isinstance(page_context, AIServerPageContext):
            return spec.tool_group == "identity" and spec.required_permission is None
        return spec.tool_group in page_context.allowed_tool_groups

    def is_available(self, spec: ToolSpec, context: ToolAccessContext) -> bool:
        if spec.risk_level != AIToolRiskLevel.READ_ONLY:
            return False
        if not self.is_in_request_scope(spec, context):
            return False
        if spec.required_permission is None:
            return True

        page_context = context.page_context
        assert isinstance(page_context, AIServerPageContext)
        page_factory = page_context.verified_factory_id
        if page_factory is None or page_factory not in ALLOWED_FACTORY_IDS:
            return False
        return any(
            authorization_decision(
                context.user,
                spec.required_permission,
                page_factory,
                department,
            )[0]
            for department in spec.allowed_departments
        )


def build_default_tool_registry() -> ToolRegistry:
    from app.services.ai.tools.identity_tools import identity_tool_spec
    from app.services.ai.tools.internal_quote_read_tools import (
        internal_quote_tool_specs,
    )
    from app.services.ai.tools.module_help_tools import module_help_tool_spec
    from app.services.ai.tools.scheduling_read_tools import scheduling_tool_specs

    return ToolRegistry(
        (
            identity_tool_spec(),
            module_help_tool_spec(),
            *internal_quote_tool_specs(),
            *scheduling_tool_specs(),
        )
    )
