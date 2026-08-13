from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

RAW_MATERIAL_AI_SAFE_MASTER_FIELDS = frozenset(
    {
        "material_id",
        "material_code",
        "material_name",
        "category",
        "spec",
        "unit",
        "safety_stock_kg",
        "status",
        "updated_at",
    }
)
RAW_MATERIAL_AI_SAFE_INVENTORY_FIELDS = frozenset(
    {
        "batch_id",
        "material_name",
        "batch_no",
        "location",
        "initial_weight_kg",
        "available_weight_kg",
        "updated_at",
    }
)


class RawMaterialMasterSummaryListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    status: Literal["", "启用", "停用"] = ""
    keyword: str = Field(default="", max_length=64)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, value: str) -> str:
        return value.strip()


class RawMaterialInventorySummaryListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    material: str = Field(default="", max_length=128)
    only_available: bool = False
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("material")
    @classmethod
    def strip_material(cls, value: str) -> str:
        return value.strip()


class AIRawMaterialMasterSummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
    material_code: str = Field(min_length=1, max_length=128)
    material_name: str = Field(max_length=255)
    category: str = Field(max_length=128)
    spec: str = Field(max_length=255)
    unit: str = Field(max_length=64)
    safety_stock_kg: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    status: Literal["启用", "停用"]
    updated_at: str = Field(max_length=32)


class AIRawMaterialMasterSummaryListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw-material-master-summary-v1"] = (
        "raw-material-master-summary-v1"
    )
    result_type: Literal["raw_material.master_summary_list"] = (
        "raw_material.master_summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    catalog_scope: Literal["ALL_FACTORIES"] = "ALL_FACTORIES"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    materials: list[AIRawMaterialMasterSummaryItem] = Field(max_length=20)


class AIRawMaterialInventorySummaryItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$",
    )
    material_name: str = Field(max_length=255)
    batch_no: str = Field(max_length=128)
    location: str = Field(max_length=128)
    initial_weight_kg: float = Field(ge=0, allow_inf_nan=False)
    available_weight_kg: float = Field(ge=0, allow_inf_nan=False)
    updated_at: str = Field(max_length=32)


class AIRawMaterialInventorySummaryListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["raw-material-inventory-summary-v1"] = (
        "raw-material-inventory-summary-v1"
    )
    result_type: Literal["raw_material.inventory_summary_list"] = (
        "raw_material.inventory_summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    batches: list[AIRawMaterialInventorySummaryItem] = Field(max_length=20)
