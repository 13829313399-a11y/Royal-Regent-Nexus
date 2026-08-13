from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.carton_procurement import CartonProcurementSummaryListInput
from app.services.ai.carton_procurement_read import (
    list_carton_procurement_ai_summaries,
)
from app.services.ai.serializers.carton_procurement import (
    serialize_carton_procurement_summary_page,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.carton_procurement import CARTON_DEPARTMENTS


def list_summary_page(
    context: ToolExecutionContext,
    arguments: CartonProcurementSummaryListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_carton_procurement_ai_summaries(
        context.db,
        arguments.factory_id,
        status=arguments.status,
        keyword=arguments.keyword,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def carton_procurement_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="carton_procurement.list_summaries",
            description=(
                "分页查询当前已验证厂区的纸箱采购订单最小化摘要。仅返回订单号、"
                "客户、合同、货号、产品、订单/交期、状态、版本和更新时间；不返回"
                "供应商、数量、单价、金额、币种、明细、备注、收料、库存或结账数据。"
            ),
            input_model=CartonProcurementSummaryListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_summary_page,
            serializer=serialize_carton_procurement_summary_page,
            display_label="正在读取纸箱采购摘要",
            tool_group="carton_procurement",
            required_permission="carton_procurement:read",
            allowed_departments=frozenset(CARTON_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
