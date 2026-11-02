"""Version-bound supplier acknowledgements; reading is never an agreement."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class SupplierChangeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    source_kind: Literal["REGULAR", "REPLENISHMENT", "SPECIAL", "PRINT"]
    source_id: str = Field(min_length=1, max_length=96)
    expected_revision: int = Field(ge=1)
    action: Literal["READ", "ACCEPT", "DISPUTE", "ACK_CANCEL"]
    promised_date: date | None = None
    reason: str = Field(default="", max_length=1000)
    request_id: str = Field(default="", max_length=96, pattern=r"^[A-Za-z0-9_-]*$")
    produced_quantities: dict[str, Decimal] = Field(default_factory=dict, max_length=50)
