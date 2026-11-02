from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_special_requests import Command
from app.schemas.carton_special_requests import Line
from decimal import Decimal
from datetime import date


class OrderRef(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    kind: Literal["PURCHASE", "SAMPLE", "WORKSHOP_MISC", "SUPPLIER_GIFT"]
    id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(default=0, ge=0)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    items: list[OrderRef] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        keys = [("PURCHASE" if item.kind == "PURCHASE" else "SPECIAL", item.id) for item in self.items]
        if len(keys) != len(set(keys)): raise ValueError("不能重复选择同一订单")
        return self


class BatchAction(Selection, Command):
    action: Literal["CONFIRM", "CANCEL", "DELETE"]
    reason: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def reason_required(self):
        if self.action != "CONFIRM" and len(self.reason) < 4: raise ValueError("请填写至少四字的操作原因")
        return self


class AppendLine(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    id: str = Field(min_length=1, max_length=96)
    additional_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class AppendItem(OrderRef):
    kind: Literal["PURCHASE", "SAMPLE", "WORKSHOP_MISC"]
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
    due_date: date | None = None
    lines: list[AppendLine] = Field(default_factory=list, max_length=50)
    new_lines: list[Line] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def valid_lines(self):
        if len({line.id for line in self.lines}) != len(self.lines):
            raise ValueError("纸品不能重复")
        if any(line.id for line in self.new_lines):
            raise ValueError("新增纸品不能指定原明细身份")
        if not any(line.additional_quantity > 0 for line in self.lines) and not self.new_lines:
            raise ValueError("每张订单须追加纸品数量")
        return self


class BatchAppend(Command):
    items: list[AppendItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique(self):
        keys = [("PURCHASE" if item.kind == "PURCHASE" else "SPECIAL", item.id) for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("不能重复选择同一订单")
        return self
