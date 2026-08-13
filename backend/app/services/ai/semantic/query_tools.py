from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.query_plan import SemanticSchedulingBacklogInput
from app.services.ai.serializers.scheduling import serialize_backlog_page
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS
from app.services.injection_scheduling_execution import query_backlog_orders_page


def query_scheduling_backlog(
    context: ToolExecutionContext,
    arguments: SemanticSchedulingBacklogInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return query_backlog_orders_page(
        context.db,
        arguments.factory_id,
        due_date_eq=arguments.due_date_eq,
        due_date_gte=arguments.due_date_gte,
        due_date_lte=arguments.due_date_lte,
        order_no=arguments.order_no,
        item_no=arguments.item_no,
        mold_no=arguments.mold_no,
        priority_code=arguments.priority_code,
        sort_direction=arguments.sort_direction.value,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def semantic_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="semantic.injection_scheduling.query_backlog",
            description=(
                "按经过 Semantic Gateway v1 校验的日期、订单号、料号和优先级"
                "读取单一厂区注塑待排订单。参数是闭集，不接受 SQL 或任意字段。"
            ),
            input_model=SemanticSchedulingBacklogInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=query_scheduling_backlog,
            serializer=serialize_backlog_page,
            display_label="正在执行受控注塑待排查询",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=frozenset(SCHEDULING_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
