from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.internal_quote import InternalQuoteSummaryListInput
from app.services.ai.internal_quote_read import list_internal_quote_ai_summaries
from app.services.ai.serializers.internal_quote import (
    serialize_internal_quote_summary_page,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.internal_quote import ALL_QUOTE_DEPARTMENTS


def list_summary_page(
    context: ToolExecutionContext,
    arguments: InternalQuoteSummaryListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_internal_quote_ai_summaries(
        context.db,
        arguments.factory_id,
        status=arguments.status,
        keyword=arguments.keyword,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def internal_quote_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="internal_quote.list_summaries",
            description=(
                "分页查询当前已验证厂区的内部报价字段最小化摘要。仅返回报价编号、"
                "客户、状态、当前环节、版本和更新时间；不返回成本、价格、数量、"
                "备注、分段明细、附件或审批内容。"
            ),
            input_model=InternalQuoteSummaryListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_summary_page,
            serializer=serialize_internal_quote_summary_page,
            display_label="正在读取内部报价摘要",
            tool_group="internal_quote",
            required_permission="internal_quote:read",
            allowed_departments=frozenset(ALL_QUOTE_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
