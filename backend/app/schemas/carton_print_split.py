"""Versioned print-change proposals; quantities never represent stock transfers."""
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class PrintPaper(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: str = Field(min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class PrintTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    contract_no: str = Field(min_length=1, max_length=128)
    customer_po: str = Field(default="", max_length=128)
    product_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    due_date: date
    asset_ids: list[str] = Field(default_factory=list, max_length=20)
    lines: list[PrintPaper] = Field(min_length=1, max_length=50)


class PrintSplitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
    # True preserves the contract of existing different-print proposals.
    print_changed: bool = True
    legacy_splits: dict[str, int] = Field(default_factory=dict, max_length=20)
    original_asset_ids: list[str] = Field(default_factory=list, max_length=20)
    targets: list[PrintTarget] = Field(min_length=1, max_length=20)


class PrintSplitAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
