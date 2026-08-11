from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.scheduling import (
    InjectionSchedulingBacklogInput,
    InjectionSchedulingPlanContextInput,
)
from app.services.ai.serializers.scheduling import (
    serialize_backlog_page,
    serialize_plan_context,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS
from app.services.injection_scheduling_execution import (
    list_backlog_orders_page,
    read_ai_plan_context,
)


def get_plan_context(
    context: ToolExecutionContext,
    arguments: InjectionSchedulingPlanContextInput,
):
    if context.db is None:
        raise RuntimeError("a database session is required")
    return read_ai_plan_context(context.db, arguments.factory_id)


def get_backlog(
    context: ToolExecutionContext,
    arguments: InjectionSchedulingBacklogInput,
):
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_backlog_orders_page(
        context.db,
        arguments.factory_id,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def scheduling_tool_specs() -> tuple[ToolSpec, ...]:
    allowed_departments = frozenset(SCHEDULING_DEPARTMENTS)
    return (
        ToolSpec(
            name="injection_scheduling.get_plan_context",
            description=(
                "读取指定厂区的注塑执行 PUBLISHED 计划与规划 DRAFT 草案摘要。"
            ),
            input_model=InjectionSchedulingPlanContextInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=get_plan_context,
            serializer=serialize_plan_context,
            display_label="正在读取排产计划摘要",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=allowed_departments,
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=8,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
        ToolSpec(
            name="injection_scheduling.get_backlog",
            description=(
                "分页读取指定厂区字段最小化的注塑待排订单，并返回截断信息。"
            ),
            input_model=InjectionSchedulingBacklogInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=get_backlog,
            serializer=serialize_backlog_page,
            display_label="正在读取注塑待排订单",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=allowed_departments,
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=50,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
