from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from pydantic import Field, StringConstraints
from app.schemas.engineering_bom import Command, Strict

Quantity = Annotated[int, Field(strict=True, gt=0, le=1000000000)]
Money = Annotated[Decimal, Field(ge=0, le=1000000000, max_digits=16, decimal_places=6, allow_inf_nan=False)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class PurchaseLine(Strict):
    source_key: str = Field(min_length=1, max_length=64)
    quantity: Quantity | None = None
    purchase_unit: Short = ''
    unit_price: Money | None = None


class PurchaseData(Strict):
    demand_id: str = Field(min_length=1, max_length=64)
    demand_version: int = Field(ge=1)
    supplier_reference: Short = ''
    currency: Annotated[str, StringConstraints(pattern=r'^(?:[A-Z]{3})?$')] = ''
    tax_rate: Annotated[Decimal, Field(ge=0, le=100, max_digits=9, decimal_places=6, allow_inf_nan=False)] | None = None
    delivery_date: date | None = None
    delivery_location: Short = ''
    payment_terms: Short = ''
    lines: list[PurchaseLine] = Field(default_factory=list, max_length=500)


class SavePurchase(Command):
    data: PurchaseData


class ChangePurchase(Command):
    kind: Literal['QUANTITY', 'CANCEL']
    quantities: dict[str, Quantity] = Field(default_factory=dict, max_length=500)


class ReplacementPurchase(Command):
    demand_version: int = Field(ge=1)
