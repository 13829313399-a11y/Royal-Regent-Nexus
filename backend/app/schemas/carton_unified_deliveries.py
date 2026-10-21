from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas import carton_special_requests as special, carton_supplier_portal as portal
from app.schemas.carton_procurement import CartonReceiptLineCreate


class WarehouseSpecial(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    lines: list[special.ManualReceiveLine] = Field(min_length=1, max_length=50)


class WarehouseReceive(special.Command):
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    acceptance_date: date
    split_confirmation: str = Field(default='', max_length=64)
    order_revisions: dict[str, int] = Field(default_factory=dict, max_length=200)
    formal_lines: list[CartonReceiptLineCreate] = Field(default_factory=list, max_length=200)
    special_requests: list[WarehouseSpecial] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def unique_sources(self):
        if not self.formal_lines and not self.special_requests:
            raise ValueError('请选择实际到货纸品')
        ids = [line.order_line_id for line in self.formal_lines]
        if any(line.source_type != 'FORMAL_ORDER' or not line.order_line_id or line.received_quantity <= 0 for line in self.formal_lines) or len(ids) != len(set(ids)):
            raise ValueError('正单收料来源无效或重复')
        if len({row.id for row in self.special_requests}) != len(self.special_requests):
            raise ValueError('样板或杂单不能重复')
        if len(ids) + sum(len(row.lines) for row in self.special_requests) > 200:
            raise ValueError('一次收料不能超过200行')
        return self


class SpecialDispatch(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    version_id: str = Field(min_length=1, max_length=96)
    lines: list[special.ShipLine] = Field(min_length=1, max_length=50)


class ExtraLine(special.Line):
    # Extra unprinted goods can be declared here. Printed extras must use an
    # ordinary special request with confirmed materials before dispatch.
    mark_mode: Literal["NONE"]
    unit_price: special.Decimal = Field(ge=0, max_digits=18, decimal_places=6)
    free_confirmed: bool = False
    purpose: str = Field(min_length=1, max_length=255)


class Dispatch(special.Command):
    delivery_note_no: str = Field(min_length=1, max_length=128)
    delivery_date: date
    formal_lines: list[portal.ShipLine] = Field(default_factory=list, max_length=200)
    special_requests: list[SpecialDispatch] = Field(default_factory=list, max_length=50)
    extra_lines: list[ExtraLine] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if not self.formal_lines and not self.special_requests and not self.extra_lines:
            raise ValueError("送货单至少需要一行纸品")
        if len({item.id for item in self.special_requests}) != len(self.special_requests):
            raise ValueError("同一送货单不能重复引用需求")
        if len(self.formal_lines) + sum(len(item.lines) for item in self.special_requests) + len(self.extra_lines) > 200:
            raise ValueError("送货单不能超过 200 行")
        supplied_lines = [*self.formal_lines, *(line for request in self.special_requests for line in request.lines)]
        if any(line.unit_price is None for line in supplied_lines):
            raise ValueError("请逐行填写供应商原送货单价，不能留空")
        return self


class FormalAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_revision: int = Field(ge=1)
    lines: list[portal.ReceiveLine] = Field(min_length=1, max_length=200)
    remaining_action: Literal["WAIT", "CLOSE"] = "WAIT"
    new_delivery_confirmation: bool = False
    correction_reason: str = Field(default="", max_length=1000)
    split_confirmation: str = Field(default="", max_length=64)


class SpecialAcceptance(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: str = Field(min_length=1, max_length=96)
    shipment_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    lines: list[special.ReceiveLine] = Field(min_length=1, max_length=50)
    received_kind: Literal["SAMPLE", "WORKSHOP_MISC"] | None = None
    workshop_id: str = Field(default="", max_length=96)
    requester_name: str = Field(default="", max_length=128)


class Receive(special.Command):
    acceptance_date: date
    formal: FormalAcceptance | None = None
    special: list[SpecialAcceptance] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique(self):
        if not self.formal and not self.special: raise ValueError("请选择本次实际核实的送货明细")
        if len({item.shipment_id for item in self.special}) != len(self.special):
            raise ValueError("同一收料操作不能重复引用送货明细")
        return self
