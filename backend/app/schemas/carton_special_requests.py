from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_procurement import CartonLocationAllocation


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(default=0, ge=0)


class Delete(Command):
    reason: str = Field(min_length=4, max_length=1000)


class Line(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(default="", max_length=96)
    item_no: str = Field(default="", max_length=128)
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(min_length=1, max_length=128)
    specification: str = Field(min_length=1, max_length=255)
    dimension_unit: Literal["cm", "in"]
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit: str = Field(default="个", min_length=1, max_length=32)
    mark_mode: Literal["EXISTING", "UPLOAD", "NONE", "PENDING"] = "PENDING"


class Create(Command):
    kind: Literal["SAMPLE", "WORKSHOP_MISC", "SUPPLIER_GIFT"] = "SAMPLE"
    title: str = Field(default="", max_length=255)
    requester_name: str = Field(default="", max_length=128)
    customer_code: str = Field(default="", max_length=64)
    workshop_id: str = Field(default="", max_length=96)
    purpose: str = Field(default="", max_length=2000)
    required_date: date
    lines: list[Line] = Field(min_length=1, max_length=50)


class QuoteLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1, max_length=96)
    unit_price: Decimal = Field(ge=0, max_digits=18, decimal_places=6)


class Adjust(Create):
    reason: str = Field(min_length=4, max_length=1000)


class Quote(Command):
    version_id: str = Field(min_length=1, max_length=96)
    pricing_kind: Literal["FREE", "CHARGEABLE"]
    promised_date: date
    lines: list[QuoteLine] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def prices(self):
        if len({line.line_id for line in self.lines}) != len(self.lines):
            raise ValueError("报价明细不能重复")
        if any((line.unit_price != 0 if self.pricing_kind == "FREE" else line.unit_price <= 0) for line in self.lines):
            raise ValueError("免费须为零单价，收费须为正单价")
        return self


class Approve(Command):
    quote_version_id: str = Field(min_length=1, max_length=96)


class ShipLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: str = Field(min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    free_confirmed: bool = False


class Ship(Command):
    version_id: str = Field(min_length=1, max_length=96)
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    lines: list[ShipLine] = Field(min_length=1, max_length=50)


class ReceiveLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipment_line_id: str = Field(min_length=1, max_length=96)
    received_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    damaged_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    rejected_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    unusable_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    location_allocations: list[CartonLocationAllocation] = Field(default_factory=list, max_length=100)
    price_action: Literal["MATCH", "PENDING", "PROPOSE", "FREE"] = "MATCH"
    price_reason: str = Field(default="", max_length=1000)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    zero_price_kind: Literal["FREE", "PENDING"] | None = None

    @model_validator(mode="after")
    def quantities(self):
        effective = self.received_quantity - self.damaged_quantity - self.rejected_quantity - self.unusable_quantity
        if effective < 0:
            raise ValueError("破损、拒收和不可用数量之和不能大于实收数量")
        if effective > 0 and not self.location_allocations:
            raise ValueError("有效入库数量须分配实际仓位")
        if effective == 0 and self.location_allocations:
            raise ValueError("全部拒收或不可用纸品不能分配入库仓位")
        return self


class Receive(Command):
    acceptance_date: date
    lines: list[ReceiveLine] = Field(min_length=1, max_length=50)
    received_kind: Literal["SAMPLE", "WORKSHOP_MISC"] | None = None
    workshop_id: str = Field(default="", max_length=96)
    requester_name: str = Field(default="", max_length=128)


class ManualReceiveLine(ReceiveLine):
    shipment_line_id: str = ""
    line_id: str = Field(min_length=1, max_length=96)


class ManualReceive(Command):
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    acceptance_date: date
    lines: list[ManualReceiveLine] = Field(min_length=1, max_length=50)


class MarkSet(Command):
    mark_mode: Literal["EXISTING", "UPLOAD", "NONE", "PENDING"]
    asset_id: str = Field(default="", max_length=96)
    asset_revision: int = Field(default=0, ge=0)
    attachment_id: str = Field(default="", max_length=96)


class Message(Command):
    body: str = Field(min_length=1, max_length=4000)
