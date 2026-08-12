from __future__ import annotations

from app.schemas.ai.raw_material import (
    AIRawMaterialInventorySummaryItem,
    AIRawMaterialInventorySummaryListData,
    AIRawMaterialMasterSummaryItem,
    AIRawMaterialMasterSummaryListData,
)
from app.services.ai.raw_material_read import (
    RawMaterialAIInventoryPage,
    RawMaterialAIMasterPage,
)


def serialize_raw_material_master_page(
    value: object,
) -> AIRawMaterialMasterSummaryListData:
    if not isinstance(value, RawMaterialAIMasterPage):
        raise TypeError("raw material master serializer received an unsupported value")
    return AIRawMaterialMasterSummaryListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        materials=[
            AIRawMaterialMasterSummaryItem(
                material_id=item.material_id,
                material_code=item.material_code,
                material_name=item.material_name,
                category=item.category,
                spec=item.spec,
                unit=item.unit,
                safety_stock_kg=item.safety_stock_kg,
                status=item.status,
                updated_at=item.updated_at,
            )
            for item in value.items
        ],
    )


def serialize_raw_material_inventory_page(
    value: object,
) -> AIRawMaterialInventorySummaryListData:
    if not isinstance(value, RawMaterialAIInventoryPage):
        raise TypeError("raw material inventory serializer received an unsupported value")
    return AIRawMaterialInventorySummaryListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        batches=[
            AIRawMaterialInventorySummaryItem(
                batch_id=item.batch_id,
                material_name=item.material_name,
                batch_no=item.batch_no,
                location=item.location,
                initial_weight_kg=item.initial_weight_kg,
                available_weight_kg=item.available_weight_kg,
                updated_at=item.updated_at,
            )
            for item in value.items
        ],
    )
