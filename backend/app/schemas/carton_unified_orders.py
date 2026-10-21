from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_special_requests import Command


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
