from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_procurement import CartonLocationAllocation

class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)

class MemberSave(Payload):
    username: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    reason: str = Field(min_length=4, max_length=1000)

class CommitmentSave(Payload):
    issue_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=0)
    promised_date: date

class ShipLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: str = Field(min_length=1, max_length=96)
    issue_id: str = Field(min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)

class ShipmentCreate(Payload):
    request_id: str = Field(min_length=8, max_length=128)
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    lines: list[ShipLine] = Field(min_length=1, max_length=200)
    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("同一发货单不能重复引用同一纸品明细")
        return self

class ReceiveLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    shipment_line_id: str = Field(min_length=1, max_length=96)
    received_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unusable_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    paper_quality: str = Field(default="", max_length=128)
    specification: str = Field(default="", max_length=255)
    location_allocations: list[CartonLocationAllocation] = Field(default_factory=list, max_length=100)
    difference_reason: str = Field(default="", max_length=1000)

class ShipmentReceive(Payload):
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    acceptance_date: date
    lines: list[ReceiveLine] = Field(min_length=1, max_length=200)
