from __future__ import annotations

from pydantic import Field

from app.core.time import business_now
from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel, StrictToolInput
from app.schemas.ai.context import AIServerPageContext
from app.services.ai.knowledge.contracts import KnowledgeSearchResult
from app.services.ai.knowledge.retriever import KnowledgeRetriever
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec


class KnowledgeSearchInput(StrictToolInput):
    query: str = Field(default="", max_length=200)
    max_results: int = Field(default=3, ge=1, le=5)


def search_module_knowledge(
    context: ToolExecutionContext,
    arguments: KnowledgeSearchInput,
) -> KnowledgeSearchResult:
    page = context.page_context
    if (
        not isinstance(page, AIServerPageContext)
        or "module_knowledge" not in page.allowed_tool_groups
    ):
        raise ValueError("verified module Knowledge context is required")
    return KnowledgeRetriever().search(
        arguments.query,
        knowledge_ids=(page.knowledge_id,),
        user_role_codes=tuple(context.user.role_codes),
        factory_id=page.verified_factory_id,
        pilot=True,
        on_date=business_now().date(),
        max_hits=arguments.max_results,
    )


def serialize_knowledge_search(value: object) -> KnowledgeSearchResult:
    if isinstance(value, KnowledgeSearchResult):
        return value
    return KnowledgeSearchResult.model_validate(value)


def knowledge_hub_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="knowledge.search_module",
            description=(
                "在当前服务端验证模块的 Owner 审核 Git 知识中执行受控精确/关键词"
                "检索。每个命中都带文档、段落和版本 Citation；无结果时明确返回"
                "缺少证据。实时业务事实仍必须使用正式领域 Tool。"
            ),
            input_model=KnowledgeSearchInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=search_module_knowledge,
            serializer=serialize_knowledge_search,
            display_label="正在检索当前模块知识",
            tool_group="module_knowledge",
            max_result_rows=5,
            timeout_seconds=2,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
