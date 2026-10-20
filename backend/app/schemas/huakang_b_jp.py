from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class QuantitySelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(min_length=64, max_length=64)
    table_index: int = Field(ge=0, le=199)
    column_index: int = Field(ge=0, le=99)


class RowOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=64, max_length=64)
    field: Literal["customer", "customer_po", "qty", "pkg", "ship_date", "cutoff_date",
                   "country", "note", "carton_t", "price_t", "factory_price_t"]
    value: str = Field(max_length=1000)
