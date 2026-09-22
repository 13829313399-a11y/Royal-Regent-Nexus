import math
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StrictFloat, StrictInt, field_validator


def _finite(value):
    # FastAPI's default validation response cannot JSON-encode NaN/Infinity in
    # an error's raw input. Return a safe error before that serialization path.
    if isinstance(value, float) and not math.isfinite(value):
        raise HTTPException(422, "报价参数和材料价格必须为有限数值")
    return value


Number = Annotated[StrictFloat | StrictInt, BeforeValidator(_finite), Field(allow_inf_nan=False)]


class StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomerPriceMaterial(StrictPayload):
    material: str = Field(min_length=1, max_length=128)
    price: Annotated[Number, Field(ge=0)]
    currency: Literal["HKD", "USD"]
    unit: Literal["kg", "lb"]

    @field_validator("material")
    @classmethod
    def clean_material(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("胶料名称不能为空")
        return value


class CustomerPriceSettingsRevision(StrictPayload):
    revision: Annotated[StrictInt, Field(ge=0)]


class CustomerPriceSettingsUpdate(CustomerPriceSettingsRevision):
    materials: list[CustomerPriceMaterial] = Field(max_length=500)
    rates: dict[str, Number]
    texts: dict[str, str]

    @field_validator("materials")
    @classmethod
    def unique_materials(cls, rows):
        identifiers = [row.material.casefold() for row in rows]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("胶料名称不能重复")
        return rows


class CustomerPriceSettingsOut(CustomerPriceSettingsUpdate):
    factory_id: str
    customer_id: str
    updated_at: str
    updated_by_name: str
    rate_definitions: dict[str, "CustomerPriceRateDefinition"]
    text_definitions: dict[str, "CustomerPriceTextDefinition"]


class CustomerPriceRateDefinition(StrictPayload):
    label: str
    kind: Literal["multiplier", "rate", "price", "exchange"]
    description: str | None = None


class CustomerPriceTextDefinition(StrictPayload):
    label: str


class CustomerPriceSettingsSnapshotOut(CustomerPriceSettingsOut):
    snapshot_id: str
