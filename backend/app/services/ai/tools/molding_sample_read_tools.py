from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.molding_sample import MoldingSampleSummaryListInput
from app.services.ai.molding_sample_read import list_molding_sample_ai_summaries
from app.services.ai.serializers.molding_sample import (
    serialize_molding_sample_summary_page,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.business_authz import SHARED_MOLDING_DEPARTMENTS


def list_summary_page(
    context: ToolExecutionContext,
    arguments: MoldingSampleSummaryListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_molding_sample_ai_summaries(
        context.db,
        arguments.factory_id,
        status=arguments.status,
        keyword=arguments.keyword,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def molding_sample_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="molding_sample.list_summaries",
            description=(
                "分页查询当前已验证厂区的啤办任务字段最小化摘要。仅返回任务标识、"
                "单号、产品、客户、状态、阶段、日期、生产厂区和更新时间；不返回"
                "原料、数量、重量、成本、备注、原因、负责人、报告或附件。"
            ),
            input_model=MoldingSampleSummaryListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_summary_page,
            serializer=serialize_molding_sample_summary_page,
            display_label="正在读取啤办任务摘要",
            tool_group="molding_sample",
            required_permission="molding_sample:read",
            allowed_departments=frozenset(SHARED_MOLDING_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
