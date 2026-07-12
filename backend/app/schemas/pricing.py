from typing import Literal

from pydantic import BaseModel, Field, field_validator


class PricingLine(BaseModel):
    sku: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=255)
    qty: float = Field(gt=0)
    unit_price: float = Field(ge=0)
    product_line: str = Field(default="", max_length=128)

    @field_validator("sku", "description", "product_line")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class DiscountRule(BaseModel):
    id: str
    label: str = ""
    product_line: str = ""
    kind: Literal["percent", "fixed", "markup"]
    value: float = Field(ge=0)
    min_qty: float | None = Field(default=None, ge=0)


class RebateTier(BaseModel):
    threshold: float = Field(ge=0)
    rate: float = Field(ge=0, le=100)


class PricingContext(BaseModel):
    customer_id: str
    customer_name: str
    currency: str
    rules: list[DiscountRule]
    rebate_tiers: list[RebateTier]
    tax_rate: float = Field(ge=0, le=100)


class PricingLineResult(PricingLine):
    gross: float
    after_discount: float
    applied_rules: list[str]


class RebateResult(BaseModel):
    amount: float
    tier: RebateTier | None = None


class TaxResult(BaseModel):
    amount: float
    rate: float


class PricingResult(BaseModel):
    lines: list[PricingLineResult]
    subtotal: float
    rebate: RebateResult
    tax: TaxResult
    total: float
    currency: str


class PricingQuoteCreate(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    project_name: str = Field(min_length=1, max_length=255)
    lines: list[PricingLine] = Field(min_length=1, max_length=200)
    local_result: PricingResult

    @field_validator("factory_id", "customer_id", "project_name")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()


class PricingInputOut(BaseModel):
    customer_id: str
    lines: list[PricingLine]


class PricingQuoteOut(BaseModel):
    id: str
    factory_id: str
    customer_id: str
    customer_name: str
    project_name: str
    status: str
    input: PricingInputOut
    context: PricingContext
    result: PricingResult
    created_by: str
    created_at: str
