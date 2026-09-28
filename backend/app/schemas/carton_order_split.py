"""Internal allocations retain the original supplier order and receipt evidence."""
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class SplitPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)


class SplitPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    location_id: str = Field(min_length=1, max_length=96)
    expected_position_revision: int = Field(ge=1)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)


class SplitLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: str = Field(min_length=1, max_length=96)
    pending_quantity: Decimal = Field(default=Decimal(0), ge=0, max_digits=18, decimal_places=4)
    stock: list[SplitPosition] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_positions(self):
        if len({part.location_id for part in self.stock}) != len(self.stock):
            raise ValueError("同一纸品的仓位不能重复")
        return self


class SplitTarget(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    contract_no: str = Field(min_length=1, max_length=128)
    customer_po: str = Field(default="", max_length=128)
    product_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=6)
    lines: list[SplitLine] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("拆分纸品不能重复")
        if not any(line.pending_quantity or line.stock for line in self.lines):
            raise ValueError("至少填写一项待到或库存拆分数量")
        return self


class SplitCreate(SplitPayload):
    request_id: str = Field(min_length=8, max_length=128)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
    targets: list[SplitTarget] = Field(min_length=1, max_length=20)


class SplitAction(SplitPayload):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)


class SplitReceiptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_line_id: str = Field(min_length=1, max_length=96)
    effective_quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)


class SplitReceiptPreview(SplitPayload):
    lines: list[SplitReceiptLine] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def unique_lines(self):
        if len({line.order_line_id for line in self.lines}) != len(self.lines):
            raise ValueError("收货预览纸品不能重复")
        return self
