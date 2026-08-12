from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.scheduling_advisor import (
    AIInjectionSchedulingComparisonData,
    AIInjectionSchedulingPreviewData,
    InjectionSchedulingPreviewComparisonInput,
    InjectionSchedulingPreviewIntentInput,
)
from app.services.ai.scheduling_advisor import compare_previews, generate_preview
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS


def generate_scheduling_preview(
    context: ToolExecutionContext,
    arguments: InjectionSchedulingPreviewIntentInput,
) -> AIInjectionSchedulingPreviewData:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return generate_preview(context.db, arguments, context.user, context)


def compare_scheduling_previews(
    context: ToolExecutionContext,
    arguments: InjectionSchedulingPreviewComparisonInput,
) -> AIInjectionSchedulingComparisonData:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return compare_previews(context.db, arguments)


def _preview_serializer(value: object) -> AIInjectionSchedulingPreviewData:
    if not isinstance(value, AIInjectionSchedulingPreviewData):
        raise TypeError("scheduling preview serializer received an unsupported value")
    return value


def _comparison_serializer(value: object) -> AIInjectionSchedulingComparisonData:
    if not isinstance(value, AIInjectionSchedulingComparisonData):
        raise TypeError("scheduling comparison serializer received an unsupported value")
    return value


def scheduling_advisor_tool_specs() -> tuple[ToolSpec, ...]:
    departments = frozenset(SCHEDULING_DEPARTMENTS)
    return (
        ToolSpec(
            name="injection_scheduling.generate_preview",
            description=(
                "把受支持的排产目标映射为现有 Scheduler 参数并持久化 PREVIEW Run。"
                "只生成候选方案，不生成最终机台分配、不 Apply、不 Publish；非法目标或"
                "约束由闭合 SchedulingIntent 拒绝。若要基于同一快照生成对比方案，"
                "传入 compare_with_run_id。"
            ),
            input_model=InjectionSchedulingPreviewIntentInput,
            risk_level=AIToolRiskLevel.PREVIEW_WITH_AUDIT,
            executor=generate_scheduling_preview,
            serializer=_preview_serializer,
            display_label="正在生成候选排产方案（尚未应用）",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:edit",
            allowed_departments=departments,
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=4,
            timeout_seconds=35,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
        ToolSpec(
            name="injection_scheduling.compare_previews",
            description=(
                "比较 2 至 4 个已持久化 PREVIEW Run 的服务器权威指标。"
                "不会 Apply、Publish 或修改正式计划任务。"
            ),
            input_model=InjectionSchedulingPreviewComparisonInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=compare_scheduling_previews,
            serializer=_comparison_serializer,
            display_label="正在比较候选排产方案",
            tool_group="injection_scheduling",
            required_permission="injection_scheduling:read",
            allowed_departments=departments,
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=4,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
