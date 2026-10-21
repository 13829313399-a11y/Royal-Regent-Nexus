"""Append-only receipts and financial evidence for one actual return movement."""
from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class ReturnAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    action: Literal["ENROLL", "RECEIVE", "DISPUTE", "PROPOSE_CREDIT", "CONFIRM_CREDIT",
        "DECLARE_REFUND", "CONFIRM_REFUND", "VOID", "RECONFIRM_DATE", "CONFIRM_DATE"]
    target_event_id: str = Field(default="", max_length=96)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    receipt_date: date | None = None
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    credit_date: date | None = None
    kind: Literal["CASH", "OFFSET"] | None = None
    amount: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=2)
    refund_date: date | None = None
    document_no: str = Field(default="", max_length=128)
    confirmation_reference: str = Field(default="", max_length=128)
    reason: str = Field(default="", max_length=2000)
