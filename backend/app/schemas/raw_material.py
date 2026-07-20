from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, field_validator

from app.services.auth import ALLOWED_FACTORY_IDS


def validate_raw_material_factory_id(value: str) -> str:
    normalized = value.strip()
    if normalized not in ALLOWED_FACTORY_IDS:
        raise ValueError("请选择有效实体厂区")
    return normalized


RawMaterialFactoryId = Annotated[str, AfterValidator(validate_raw_material_factory_id)]


class RawMaterialFields(BaseModel):
    material_name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=128)
    spec: str = Field(default="", max_length=255)
    unit: str = Field(min_length=1, max_length=64)
    supplier: str = Field(default="", max_length=255)
    safety_stock_kg: float | None = Field(default=None, ge=0)
    unit_price_hkd_per_lb: float | None = Field(default=None, gt=0)
    status: Literal["启用", "停用"] = "启用"
    notes: str = Field(default="", max_length=4000)

    @field_validator(
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


class RawMaterialCreateRequest(RawMaterialFields):
    factory_id: RawMaterialFactoryId = Field(min_length=1, max_length=64)


class RawMaterialUpdateRequest(RawMaterialFields):
    pass


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
    unit_price_hkd_per_lb: float | None = None
    status: Literal["启用", "停用"]
    notes: str
    created_by: str
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)
