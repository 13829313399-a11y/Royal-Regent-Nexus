from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(default="", max_length=1000)


class Propose(Command):
    proposed_unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    free_confirmed: bool = False

    @model_validator(mode="after")
    def explicit_price(self):
        if len(self.reason) < 4:
            raise ValueError("核价或更正须填写至少四字原因")
        if self.proposed_unit_price == 0 and not self.free_confirmed:
            raise ValueError("零单价须明确确认免费")
        if self.free_confirmed and self.proposed_unit_price != 0:
            raise ValueError("免费只适用于零单价")
        return self


class Decide(Command):
    decision: Literal["CONFIRM", "REJECT"]
