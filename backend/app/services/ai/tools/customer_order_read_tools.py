from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.customer_order import (
    CustomerOrderCapabilitiesInput,
    CustomerOrderExportAuditListInput,
)
from app.services.ai.customer_order_read import (
    get_customer_order_ai_capabilities,
    list_customer_order_ai_export_audits,
)
from app.services.ai.serializers.customer_order import (
    serialize_customer_order_capabilities,
    serialize_customer_order_export_audits,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec

SALES_DEPARTMENTS = ("sales-business",)


def get_capabilities(
    _context: ToolExecutionContext,
    arguments: CustomerOrderCapabilitiesInput,
) -> object:
    return get_customer_order_ai_capabilities(arguments.factory_id)


def list_export_audits(
    context: ToolExecutionContext,
    arguments: CustomerOrderExportAuditListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_customer_order_ai_export_audits(
        context.db,
        arguments.factory_id,
        customer_code=arguments.customer_code,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def customer_order_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="customer_order.get_capabilities",
            description=(
                "读取当前已验证厂区的客户订单预览、受控导出及导出审计能力。"
                "只返回支持的客户映射和能力边界；当前没有权威订单总台账，"
                "不得回答官方订单总数。"
            ),
            input_model=CustomerOrderCapabilitiesInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=get_capabilities,
            serializer=serialize_customer_order_capabilities,
            display_label="正在读取客户订单能力边界",
            tool_group="customer_order",
            required_permission="customer_order:read",
            allowed_departments=frozenset(SALES_DEPARTMENTS),
            factory_argument="factory_id",
            max_result_rows=20,
            timeout_seconds=5,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
        ToolSpec(
            name="customer_order.list_export_audits",
            description=(
                "分页查询当前已验证厂区的客户订单导出审计最小摘要。"
                "不返回操作者身份、文件哈希、源文件列表、确认原因或人工修改明细，"
                "也不把审计记录数量解释为订单总数。"
            ),
            input_model=CustomerOrderExportAuditListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_export_audits,
            serializer=serialize_customer_order_export_audits,
            display_label="正在读取客户订单导出审计摘要",
            tool_group="customer_order",
            required_permission="customer_order:audit_read",
            allowed_departments=frozenset(SALES_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
