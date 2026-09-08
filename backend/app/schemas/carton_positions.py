from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class LocationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    factory_id: str
    warehouse: str = Field(min_length=1, max_length=64)
    bin_code: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="新增仓库仓位", min_length=4, max_length=500)


class PositionTransfer(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    factory_id: str
    request_id: str = Field(min_length=16, max_length=96)
    position_key: str = Field(min_length=1, max_length=1400)
    expected_position_revision: int = Field(ge=0)
    location_id: str = Field(min_length=1, max_length=96)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    note: str = Field(default="", max_length=2000)
