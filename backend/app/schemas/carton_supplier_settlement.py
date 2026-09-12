"""Supplier statements are procurement evidence, separate from inventory valuation."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.schemas.carton_procurement import _validate_iso_date


class StatementLine(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    source_key: str = Field(default="", max_length=128)
    document_no: str = Field(default="", max_length=128)
    quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    approved_return_unit_price: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=6)
    credit_document_no: str = Field(default="", max_length=128)
    credit_date: str | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("credit_date")
    @classmethod
    def valid_date(cls, value):
        return _validate_iso_date(value) if value else None


class SettlementSave(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    supplier_id: str | None = Field(default=None, max_length=96)
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    currency: str = Field(default="CNY", min_length=1, max_length=8)
    id: str | None = Field(default=None, max_length=96)
    expected_revision: int | None = Field(default=None, ge=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    statement_no: str = Field(default="", max_length=128)
    tax_basis: Literal["INCLUSIVE", "EXCLUSIVE"] = "INCLUSIVE"
    same_price_basis: bool = False
    lines: list[StatementLine] = Field(default_factory=list, max_length=2000)


class SettlementAction(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(default="", max_length=2000)


class AcceptanceDateUpdate(SettlementAction):
    acceptance_date: str

    @field_validator("acceptance_date")
    @classmethod
    def valid_date(cls, value):
        return _validate_iso_date(value)
