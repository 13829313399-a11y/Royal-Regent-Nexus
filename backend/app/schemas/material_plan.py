from decimal import Decimal
from datetime import date
from typing import Literal
from pydantic import Field, StrictBool
from app.schemas.engineering_bom import Command, Strict, Text, Qty


class OrderReference(Strict):
    line_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)


class TrialInput(Strict):
    title: Text
    bom_id: str = Field(min_length=1, max_length=64)
    bom_version: int = Field(ge=1)
    quantity: Qty = Field(gt=0)
    loss_percent: Decimal = Field(default=Decimal(0), ge=0, le=100, max_digits=9, decimal_places=6, allow_inf_nan=False)
    loss_exemptions: dict[str, StrictBool] = Field(default_factory=dict, max_length=500)
    material_attributes: dict[str, Literal['外购', '自制', '委外', '客供']] = Field(default_factory=dict, max_length=500)
    reference: str = Field(default='', max_length=500)
    order: OrderReference | None = None


class TrialRequest(Command):
    data: TrialInput


class DatesRequest(Command):
    dates: dict[str, date | None] = Field(default_factory=dict, max_length=500)
