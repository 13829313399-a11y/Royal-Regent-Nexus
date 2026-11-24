from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


Process = Literal['捆条', '贴合', '电绣', '丝印']
Identifier = Annotated[str, Field(min_length=1, max_length=64)]
Reference = Annotated[str, Field(min_length=1, max_length=128)]
Quantity = Annotated[str, Field(max_length=19, pattern=r'^(?:[1-9][0-9]{0,11}(?:\.[0-9]{1,6})?|0\.0*[1-9][0-9]*)$')]


class Fields(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Command(Fields):
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=0)


class Processor(Command):
    id: Identifier | None = None
    code: Reference
    name: Reference
    processes: list[Process] = Field(min_length=1, max_length=4)
    contact: str = Field(default='', max_length=128)
    phone: str = Field(default='', max_length=64)
    active: bool = True


class PlanLine(Fields):
    id: Identifier
    quantity: Quantity


class Order(Command):
    process: Process
    processor_id: Identifier
    business_date: date
    due_date: date
    source_no: str = Field(default='', max_length=128)
    previous_order_id: Identifier | None = None
    inputs: list[PlanLine] = Field(max_length=100)
    outputs: list[PlanLine] = Field(min_length=1, max_length=100)

    @model_validator(mode='after')
    def distinct_lines(self):
        for group in (self.inputs, self.outputs):
            if len({line.id for line in group}) != len(group):
                raise ValueError('请合并相同的原料批次或计划产物')
        return self


class Action(Command):
    kind: Literal['SELECT', 'SEND', 'SIGN', 'DELIVER', 'RECEIVE', 'DELIVER_AND_RECEIVE', 'ISSUE', 'VOID', 'SOURCE']
    target_id: Identifier
    business_date: date
    quantity: Quantity | None = None
    received_quantity: Quantity | None = None
    voucher: str = Field(default='', max_length=128)
    location_id: str = Field(default='', max_length=64)
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    recipient: str = Field(default='', max_length=128)
    destination: str = Field(default='', max_length=128)
    reason: str = Field(default='', max_length=255)

    @model_validator(mode='after')
    def check_received_quantity(self):
        if self.kind == 'DELIVER_AND_RECEIVE' and self.received_quantity is None:
            raise ValueError('请填写本次实收数量')
        if self.kind != 'DELIVER_AND_RECEIVE' and self.received_quantity is not None:
            raise ValueError('仅在同时登记送达和点收时单独填写实收数量')
        return self
