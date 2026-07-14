from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RawMaterialCreateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    material_code: str = Field(min_length=1, max_length=128)
    material_name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    spec: str = Field(default="", max_length=255)
    unit: str = Field(min_length=1, max_length=64)
    supplier: str = Field(default="", max_length=255)
    safety_stock_kg: float | None = Field(default=None, ge=0)
    status: Literal["启用", "停用"] = "启用"
    notes: str = Field(default="", max_length=4000)

    @field_validator(
        "factory_id",
        "material_code",
        "material_name",
        "category",
        "spec",
        "unit",
        "supplier",
        "notes",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class RawMaterialOut(BaseModel):
    id: str
    factory_id: str
    material_code: str
    material_name: str
    category: str
    spec: str
    unit: str
    supplier: str
    safety_stock_kg: float | None
    status: Literal["启用", "停用"]
    notes: str
    created_by: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)
