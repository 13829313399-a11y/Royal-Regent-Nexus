"""Packed-goods weights per carton in kg; net excludes carton/cards, gross includes them.

Both fields are retained independently; blank historical values remain unknown.
"""
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class CartonPackingWeights(BaseModel):
    net_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    gross_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)

    @model_validator(mode="after")
    def validate_weights(self):
        if (self.net_weight_kg is not None and self.gross_weight_kg is not None
                and self.gross_weight_kg < self.net_weight_kg):
            raise ValueError("每箱毛重不能小于净重")
        return self
