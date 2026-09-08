from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StocktakeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    factory_id: str = Field(min_length=1, max_length=64)
    reference_movement_ids: list[str] = Field(default_factory=list, max_length=500)
    position_keys: list[str] = Field(default_factory=list, max_length=500)


class StocktakeCount(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id: str
    actual_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    reason: str = Field(default="", max_length=1000)


class StocktakeAction(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    action: Literal["SAVE", "SUBMIT", "APPROVE", "RETURN", "CANCEL"]
    ledger_token: str = Field(default="", max_length=64)
    cutoff_acknowledged: bool = False
    lines: list[StocktakeCount] = Field(default_factory=list, max_length=500)
    reason: str = Field(default="", max_length=1000)
