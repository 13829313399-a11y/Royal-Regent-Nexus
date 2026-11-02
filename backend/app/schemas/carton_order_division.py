"""Split ordinary purchase demand without a separate print approval workflow."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.carton_print_split import PrintPaper


class DivisionTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    contract_no: str = Field(min_length=1, max_length=128)
    customer_po: str = Field(default="", max_length=128)
    product_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    due_date: date
    lines: list[PrintPaper] = Field(min_length=1, max_length=50)


class OrderDivisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
    legacy_splits: dict[str, int] = Field(default_factory=dict, max_length=20)
    targets: list[DivisionTarget] = Field(min_length=1, max_length=20)
