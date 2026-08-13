from __future__ import annotations

from app.schemas.ai import AIToolAuditPolicy, AIToolRiskLevel
from app.schemas.ai.raw_material import (
    RawMaterialInventorySummaryListInput,
    RawMaterialMasterSummaryListInput,
)
from app.services.ai.raw_material_read import (
    list_raw_material_ai_inventory_summaries,
    list_raw_material_ai_master_summaries,
)
from app.services.ai.serializers.raw_material import (
    serialize_raw_material_inventory_page,
    serialize_raw_material_master_page,
)
from app.services.ai.tool_executor import ToolExecutionContext
from app.services.ai.tool_registry import ToolSpec
from app.services.business_authz import (
    SHARED_MOLDING_DEPARTMENTS,
    WAREHOUSE_DEPARTMENTS,
)


def list_master_page(
    context: ToolExecutionContext,
    arguments: RawMaterialMasterSummaryListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_raw_material_ai_master_summaries(
        context.db,
        arguments.factory_id,
        status=arguments.status,
        keyword=arguments.keyword,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def list_inventory_page(
    context: ToolExecutionContext,
    arguments: RawMaterialInventorySummaryListInput,
) -> object:
    if context.db is None:
        raise RuntimeError("a database session is required")
    return list_raw_material_ai_inventory_summaries(
        context.db,
        arguments.factory_id,
        material=arguments.material,
        only_available=arguments.only_available,
        limit=arguments.limit,
        offset=arguments.offset,
    )


def raw_material_tool_specs() -> tuple[ToolSpec, ...]:
    return (
        ToolSpec(
            name="raw_material.list_master_summaries",
            description=(
                "分页查询全厂共享原料主数据的最小摘要。只返回物料编号、名称、"
                "类别、规格、单位、安全库存阈值、状态和更新时间；不返回供应商、"
                "价格、备注、创建人或变更审计。"
            ),
            input_model=RawMaterialMasterSummaryListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_master_page,
            serializer=serialize_raw_material_master_page,
            display_label="正在读取原料主数据摘要",
            tool_group="raw_material",
            required_permission="molding_sample:read",
            allowed_departments=frozenset(SHARED_MOLDING_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
        ToolSpec(
            name="raw_material.list_inventory_summaries",
            description=(
                "分页查询当前已验证厂区的原料库存批次摘要。只返回原料、批次、"
                "库位、初始/可用重量和更新时间；不返回单价、金额、领料人、"
                "流水原因、关联单据或审计内容。"
            ),
            input_model=RawMaterialInventorySummaryListInput,
            risk_level=AIToolRiskLevel.READ_ONLY,
            executor=list_inventory_page,
            serializer=serialize_raw_material_inventory_page,
            display_label="正在读取原料库存摘要",
            tool_group="raw_material",
            required_permission="molding_sample:inventory_issue",
            allowed_departments=frozenset(WAREHOUSE_DEPARTMENTS),
            factory_argument="factory_id",
            requires_db=True,
            max_result_rows=20,
            timeout_seconds=10,
            audit_policy=AIToolAuditPolicy.METADATA_ONLY,
        ),
    )
