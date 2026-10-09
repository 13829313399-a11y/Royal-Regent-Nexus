from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class RevisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class ReasonIn(RevisionIn):
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("reason")
    @classmethod
    def meaningful_reason(cls, value: str) -> str:
        if len(value.strip()) < 4:
            raise ValueError("请填写至少 4 个字的原因")
        return value.strip()


class RestoreIn(ReasonIn):
    confirmed: StrictBool
    notify_recipients: StrictBool = False


class AmendIn(ReasonIn):
    quantity: str = Field(max_length=32)
    requested_ship_date: str = Field(max_length=10)
    note: str = Field(default="", max_length=2000)

    @field_validator("requested_ship_date")
    @classmethod
    def valid_date(cls, value: str) -> str:
        return date.fromisoformat(value).isoformat() if value else ""


class DispatchIn(RevisionIn):
    recipients: list[Literal["pmc", "warehouse", "injection"]] = Field(min_length=1, max_length=3)


class ShipmentIn(RevisionIn):
    idempotency_key: str = Field(min_length=8, max_length=96)
    quantity: str = Field(max_length=32)
    ship_date: date
    document_no: str = Field(min_length=1, max_length=255)
    note: str = Field(default="", max_length=2000)

    @field_validator("document_no")
    @classmethod
    def nonempty_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请填写出货单号")
        return value.strip()


class HistorySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=64)
    status: Literal["active", "cancelled"]
    opening_shipped_quantity: str = Field(min_length=1, max_length=32)


class HistoryOpeningIn(ReasonIn):
    opening_shipped_quantity: str = Field(min_length=1, max_length=32)
