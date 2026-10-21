from decimal import Decimal
from datetime import date
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=0)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    proposed_unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    free_confirmed: bool = False


class Action(Preview):
    request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    action: Literal["PROPOSE", "SUPPLIER_CONFIRM", "SUPPLIER_DISPUTE", "FINAL_CONFIRM", "WITHDRAW"]
    reason: str = Field(min_length=4, max_length=2000)
    document_no: str = Field(default="", max_length=128)
    document_date: date | None = None
    impact_fingerprint: str = Field(default="", max_length=64)
