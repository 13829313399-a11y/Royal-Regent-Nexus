from __future__ import annotations

from app.schemas.ai.molding_sample import (
    AIMoldingSampleSummaryItem,
    AIMoldingSampleSummaryListData,
)
from app.services.ai.molding_sample_read import MoldingSampleAISummaryPage


def serialize_molding_sample_summary_page(
    value: object,
) -> AIMoldingSampleSummaryListData:
    if not isinstance(value, MoldingSampleAISummaryPage):
        raise TypeError("molding sample serializer received an unsupported value")
    return AIMoldingSampleSummaryListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        orders=[
            AIMoldingSampleSummaryItem(
                order_id=item.order_id,
                order_number=item.order_number,
                product_name=item.product_name,
                client_name=item.client_name,
                status=item.status,
                stage=item.stage,
                order_date=item.order_date,
                production_factory_id=item.production_factory_id,
                updated_at=item.updated_at,
            )
            for item in value.items
        ],
    )
