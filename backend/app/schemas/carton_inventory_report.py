from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from app.schemas.carton_procurement import CartonMovementType


class CartonInventoryReportRow(BaseModel):
    business_date: str
    customer_code: str
    customer_name: str
    unit: str
    opening_quantity: Decimal
    inbound_quantity: Decimal
    outbound_quantity: Decimal
    adjustment_quantity: Decimal
    ending_quantity: Decimal
    document_count: int
    line_count: int


class CartonInventoryReportMovement(BaseModel):
    id: str
    business_date: str
    occurred_at: str
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    packaging_type: str
    paper_quality: str
    specification: str
    unit: str
    document_no: str
    movement_type: CartonMovementType
    quantity: Decimal
    source_type: str
    reason: str
    location: str
    actor_name: str
    reversal_of_movement_id: str | None
    flow_category: Literal["INBOUND", "OUTBOUND", "ADJUSTMENT"]
    flow_quantity: Decimal


class CartonInventoryOrderReportRow(BaseModel):
    current_usage_quantity: Decimal = Decimal(0)
    current_usage_status: str = "NOT_RECEIVED"
    current_usage_label: str = "未入库"
    current_positions: list[dict] = []
    key: str
    order_id: str | None
    order_line_id: str | None
    order_date: str
    customer_code: str
    customer_name: str
    contract_no: str
    item_no: str
    product_name: str
    packaging_type: str
    paper_quality: str
    specification: str
    unit: str
    opening_quantity: Decimal
    inbound_quantity: Decimal
    outbound_quantity: Decimal
    adjustment_quantity: Decimal
    ending_quantity: Decimal
    document_count: int
    line_count: int
    last_movement_at: str


class CartonInventoryReportOut(BaseModel):
    factory_id: str
    date_from: str
    date_to: str
    rows: list[CartonInventoryReportRow]
    order_rows: list[CartonInventoryOrderReportRow]
    movements: list[CartonInventoryReportMovement]
