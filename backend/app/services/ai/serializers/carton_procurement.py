from __future__ import annotations

from app.schemas.ai.carton_procurement import (
    AICartonProcurementSummaryItem,
    AICartonProcurementSummaryListData,
)
from app.services.ai.carton_procurement_read import (
    CartonProcurementAISummaryPage,
)


def serialize_carton_procurement_summary_page(
    value: object,
) -> AICartonProcurementSummaryListData:
    if not isinstance(value, CartonProcurementAISummaryPage):
        raise TypeError("carton procurement serializer received an unsupported value")
    return AICartonProcurementSummaryListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        orders=[
            AICartonProcurementSummaryItem(
                order_id=item.order_id,
                order_no=item.order_no,
                customer_name=item.customer_name,
                contract_no=item.contract_no,
                item_no=item.item_no,
                product_name=item.product_name,
                order_date=item.order_date,
                due_date=item.due_date,
                status=item.status,
                revision=item.revision,
                updated_at=item.updated_at,
            )
            for item in value.items
        ],
    )
