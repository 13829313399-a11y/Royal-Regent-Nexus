from datetime import date
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class AllocationTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    target_kind: Literal["OPENING", "SETTLEMENT", "FEE"]
    target_id: str = Field(min_length=1, max_length=160)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class PayablesAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    supplier_id: str | None = Field(default=None, max_length=96)
    currency: str = Field(default="CNY", min_length=1, max_length=8)
    request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=0)
    source_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    action: Literal["PROPOSE_OPENING", "REVIEW_OPENING", "CONFIRM_OPENING", "PROPOSE_FEE", "REVISE_FEE", "VOID_FEE",
        "REVIEW_FEE", "CONFIRM_FEE", "RECORD_PAYMENT", "RECEIVE_PAYMENT", "DECLARE_PAYMENT_RETURN", "CONFIRM_PAYMENT_RETURN",
        "REQUEST_VOID", "REVIEW_VOID", "CONFIRM_VOID", "ALLOCATE", "DEALLOCATE"]
    target_id: str = Field(default="", max_length=160)
    reason: str = Field(min_length=4, max_length=2000)
    direction: Literal["PAYABLE", "CREDIT", "ADD_PAYABLE", "DEDUCT_PAYABLE"] | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    cutoff_date: date | None = None
    acknowledge_unknown_sources: bool = False
    fee_date: date | None = None
    payment_date: date | None = None
    return_date: date | None = None
    category: Literal["FREIGHT", "DISCOUNT", "TAX", "ROUNDING", "OTHER"] | None = None
    document_no: str = Field(default="", max_length=128)
    bank_reference: str = Field(default="", max_length=128)
    confirmation_reference: str = Field(default="", max_length=128)
    correction_reference: str = Field(default="", max_length=128)
    related_settlement_id: str = Field(default="", max_length=96)
    parent_payment_id: str = Field(default="", max_length=96)
    decision: Literal["CONFIRMED", "DISPUTED"] | None = None
    source_kind: Literal["PAYMENT", "CREDIT"] | None = None
    source_id: str = Field(default="", max_length=160)
    targets: list[AllocationTarget] = Field(default_factory=list, max_length=100)
    allocation_ids: list[str] = Field(default_factory=list, max_length=100)
