from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import (
    AIServerPageContext,
    AIToolAuditPolicy,
    AIToolRiskLevel,
    StrictToolInput,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.auth import ALLOWED_FACTORY_IDS

_FACTORY_NAMES = {
    "huakang-a": "华康A",
    "huakang-b": "华康B",
    "huakang-c": "华康C",
    "huakang-d": "华康D",
    "huadeng": "华登",
    "huaxing": "华兴",
}
_MODULE_NAMES = {
    "injection-scheduling": "注塑排产中枢",
    "internal-quote": "内部报价台",
}


class IdentityGetCurrentContextInput(StrictToolInput):
    pass


class IdentityScopeSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    display_name: str


class IdentityCurrentContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    current_factory: IdentityScopeSummary | None = None
    current_module: IdentityScopeSummary | None = None
    available_tool_groups: list[str] = Field(default_factory=list)


def get_current_context(
    context: ToolExecutionContext,
    _arguments: IdentityGetCurrentContextInput,
) -> IdentityCurrentContextData:
    factory_id = _current_factory_id(context)
    module_id = _verified_page_value(context.page_context, "verified_module_id")
    return IdentityCurrentContextData(
        display_name=context.user.display_name,
        current_factory=(
            IdentityScopeSummary(
                id=factory_id,
                display_name=_FACTORY_NAMES[factory_id],
            )
            if factory_id is not None
            else None
        ),
        current_module=(
            IdentityScopeSummary(
                id=module_id,
                display_name=_MODULE_NAMES[module_id],
            )
            if isinstance(module_id, str) and module_id in _MODULE_NAMES
            else None
        ),
        available_tool_groups=list(context.tool_groups),
    )


def serialize_current_context(value: object) -> IdentityCurrentContextData:
    if isinstance(value, IdentityCurrentContextData):
        return value
    return IdentityCurrentContextData.model_validate(value)


def identity_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="identity.get_current_context",
        description="读取当前登录用户经过服务端验证的最小页面身份上下文。",
        input_model=IdentityGetCurrentContextInput,
        risk_level=AIToolRiskLevel.READ_ONLY,
        executor=get_current_context,
        serializer=serialize_current_context,
        display_label="正在确认当前页面身份",
        tool_group="identity",
        max_result_rows=8,
        timeout_seconds=2,
        audit_policy=AIToolAuditPolicy.METADATA_ONLY,
    )


def _current_factory_id(context: ToolExecutionContext) -> str | None:
    if isinstance(context.page_context, AIServerPageContext):
        page_factory = context.page_context.verified_factory_id
        return page_factory if page_factory in ALLOWED_FACTORY_IDS else None
    profile = context.user.profile
    if profile and profile.primary_factory_id in ALLOWED_FACTORY_IDS:
        return profile.primary_factory_id
    concrete_scopes = sorted(
        factory_id
        for factory_id in context.user.factory_scopes
        if factory_id in ALLOWED_FACTORY_IDS
    )
    return concrete_scopes[0] if len(concrete_scopes) == 1 else None


def _verified_page_value(page_context: object | None, name: str) -> object | None:
    if not isinstance(page_context, AIServerPageContext):
        return None
    return getattr(page_context, name, None)
