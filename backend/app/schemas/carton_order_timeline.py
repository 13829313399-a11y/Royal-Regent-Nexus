from typing import Literal

from pydantic import BaseModel


class CartonOrderTimelineEvent(BaseModel):
    id: str
    occurred_at: str
    event_type: str
    event_label: str
    order_id: str | None = None
    inventory_key: str | None = None
    customer_code: str = ""
    customer_name: str = ""
    contract_no: str = ""
    item_no: str = ""
    product_name: str = ""
    document_no: str = ""
    material_label: str = ""
    quantity_change: str | None = None
    quantity_before: str | None = None
    quantity_after: str | None = None
    unit: str = ""
    quantity_basis: Literal["ORDER_PRODUCT", "INVENTORY", "NONE"] = "NONE"
    reason: str = ""
    actor_name: str = ""
    description: str = ""


class CartonOrderTimelineOut(BaseModel):
    events: list[CartonOrderTimelineEvent]
    total: int
