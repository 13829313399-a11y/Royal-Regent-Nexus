"""Explicit paper calculation rules; absence preserves legacy packing semantics."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaperQuantityRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["PACKING", "PER_CARTON"] = "PACKING"
    carton_line_no: int | None = Field(default=None, ge=1, le=50)
    per_carton_quantity: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=4)
    manual_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)

    @model_validator(mode="after")
    def consistent_basis(self):
        if self.mode == "PER_CARTON":
            if self.carton_line_no is None or self.per_carton_quantity is None:
                raise ValueError("按箱配套须选择对应纸箱并填写每箱用量")
        elif self.carton_line_no is not None or self.per_carton_quantity is not None:
            raise ValueError("按装箱数计算不能同时填写配套纸箱或每箱用量")
        return self
