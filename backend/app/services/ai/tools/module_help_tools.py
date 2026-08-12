from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel, StrictToolInput
from app.schemas.ai.context import AIServerPageContext
from app.services.ai.module_knowledge import module_knowledge_registry
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec


class ModuleGetHelpInput(StrictToolInput):
    pass


class ModuleHelpData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["VERSIONED_MODULE_KNOWLEDGE"]
    knowledge_id: str
    knowledge_version: str
    last_reviewed_at: str
    reviewed_against_commit: str
    route_names: list[str]
    module_name: str
    business_purpose: str
    authoritative_data_status: str
    required_permissions: list[str]
    normal_workflow: list[str]
    status_labels: dict[str, str]
    common_errors: list[str]
    prohibited_claims: list[str]
    source_files: list[str]
    help_markdown: str = Field(min_length=1, max_length=32_000)


def get_module_help(
    context: ToolExecutionContext,
    _arguments: ModuleGetHelpInput,
) -> ModuleHelpData:
    page_context = context.page_context
    if (
        not isinstance(page_context, AIServerPageContext)
        or "module_knowledge" not in page_context.allowed_tool_groups
    ):
        raise ValueError("verified module context is required")
    document = module_knowledge_registry.load(page_context.knowledge_id)
    metadata = document.metadata
    return ModuleHelpData(
        source_type="VERSIONED_MODULE_KNOWLEDGE",
        knowledge_id=metadata.knowledge_id,
        knowledge_version=metadata.knowledge_version,
        last_reviewed_at=metadata.last_reviewed_at,
        reviewed_against_commit=metadata.reviewed_against_commit,
        route_names=list(metadata.route_names),
        module_name=metadata.module_name,
        business_purpose=metadata.business_purpose,
        authoritative_data_status=metadata.authoritative_data_status,
        required_permissions=list(metadata.required_permissions),
        normal_workflow=list(metadata.normal_workflow),
        status_labels=dict(metadata.status_labels),
        common_errors=list(metadata.common_errors),
        prohibited_claims=list(metadata.prohibited_claims),
        source_files=list(metadata.source_files),
        help_markdown=document.body_markdown,
    )


def serialize_module_help(value: object) -> ModuleHelpData:
    if isinstance(value, ModuleHelpData):
        return value
    return ModuleHelpData.model_validate(value)


def module_help_tool_spec() -> ToolSpec:
    return ToolSpec(
        name="knowledge.get_module_help",
        description=(
            "读取当前服务端已验证页面对应的版本化模块帮助、状态定义、"
            "正式数据边界和禁止声明。"
        ),
        input_model=ModuleGetHelpInput,
        risk_level=AIToolRiskLevel.READ_ONLY,
        executor=get_module_help,
        serializer=serialize_module_help,
        display_label="正在读取当前模块帮助",
        tool_group="module_knowledge",
        max_result_rows=64,
        timeout_seconds=2,
        audit_policy=AIToolAuditPolicy.METADATA_ONLY,
    )
