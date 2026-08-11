from __future__ import annotations

from app.schemas.ai.scheduling import (
    AIEntityLink,
    AIInjectionSchedulingBacklogData,
    AIInjectionSchedulingBacklogItem,
    AIInjectionSchedulingPlanContextData,
    AIInjectionSchedulingPlanSummary,
)
from app.services.injection_scheduling_execution import (
    InjectionSchedulingAIBacklogPage,
    InjectionSchedulingAIPlanContext,
    InjectionSchedulingAIPlanSummary,
)

_PRIORITY_LABELS = {
    "NORMAL": "普通",
    "URGENT": "加急",
    "CRITICAL": "特急",
}
_MOLD_ENRICHMENT_LABELS = {
    "MATCHED": "共享资料已补齐",
    "PENDING": "模具资料待补齐",
    "AMBIGUOUS": "模具匹配有歧义",
    "LEGACY_LINKED": "旧模具已关联",
}
_PLAN_STATUS_LABELS = {
    "PUBLISHED": "执行中的已发布计划",
    "DRAFT": "规划中的草案",
}
_SOURCE_SCOPE_LABELS = {
    "PLANNING_DRAFT": "规划草案待排池",
    "GLOBAL_BACKLOG": "全局待排池",
}


def serialize_plan_context(
    value: object,
) -> AIInjectionSchedulingPlanContextData:
    if not isinstance(value, InjectionSchedulingAIPlanContext):
        raise TypeError("plan context serializer received an unsupported value")
    return AIInjectionSchedulingPlanContextData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        execution_published=_plan_summary(value.execution_published),
        planning_draft=_plan_summary(value.planning_draft),
        polling_revision=value.polling_revision,
        entity_links=[_scheduling_link(value.factory_id)],
    )


def serialize_backlog_page(value: object) -> AIInjectionSchedulingBacklogData:
    if not isinstance(value, InjectionSchedulingAIBacklogPage):
        raise TypeError("backlog serializer received an unsupported value")
    return AIInjectionSchedulingBacklogData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        source_scope=value.source_scope,
        source_business_label=_SOURCE_SCOPE_LABELS[value.source_scope],
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=value.returned,
        truncated=value.truncated,
        items=[
            AIInjectionSchedulingBacklogItem(
                order_id=item.order_id,
                order_no=item.order_no,
                item_no=item.item_no,
                product_name=item.product_name,
                mold_no=item.mold_no,
                priority_code=item.priority_code,
                priority_business_label=_PRIORITY_LABELS[item.priority_code],
                delivery_due_date=item.delivery_due_date,
                order_quantity=item.order_quantity,
                outstanding_quantity=item.outstanding_quantity,
                mold_enrichment_status=item.mold_enrichment_status,
                mold_enrichment_business_label=_MOLD_ENRICHMENT_LABELS.get(
                    item.mold_enrichment_status,
                    "模具状态待确认",
                ),
                source_type=item.source_type,
            )
            for item in value.items
        ],
        entity_links=[_scheduling_link(value.factory_id)],
    )


def _plan_summary(
    value: InjectionSchedulingAIPlanSummary | None,
) -> AIInjectionSchedulingPlanSummary | None:
    if value is None:
        return None
    return AIInjectionSchedulingPlanSummary(
        plan_id=value.plan_id,
        business_date=value.business_date,
        status_code=value.status,
        business_label=_PLAN_STATUS_LABELS[value.status],
        revision=value.revision,
        task_count=value.task_count,
        running_count=value.running_count,
    )


def _scheduling_link(factory_id: str) -> AIEntityLink:
    return AIEntityLink(
        label="打开注塑排产中枢",
        route="/modules/production/injection-scheduling",
        query={"factory": factory_id},
    )
