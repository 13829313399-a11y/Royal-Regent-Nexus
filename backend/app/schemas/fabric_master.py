from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

MasterKind = Literal["MATERIAL", "SUPPLIER", "LOCATION", "UNIT"]


class MasterFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    category: Literal["", "FABRIC", "ACCESSORY", "THREAD"] = ""
    unit: str = Field(default="", max_length=32)
    old_code: str = Field(default="", max_length=128)
    spec: str = Field(default="", max_length=255)
    color: str = Field(default="", max_length=128)
    composition: str = Field(default="", max_length=255)
    contact: str = Field(default="", max_length=128)
    phone: str = Field(default="", max_length=64)
    warehouse: str = Field(default="", max_length=128)
    material_code: str = Field(default="", max_length=128)
    price_unit: str = Field(default="", max_length=32)
    ratio: str = Field(default="", max_length=32)
    evidence: str = Field(default="", max_length=1000)
    conditions: str = Field(default="", max_length=1000)
    effective_date: date | None = None
    note: str = Field(default="", max_length=2000)


class SaveMasterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: Literal["huakang-c"]
    request_id: UUID
    id: str | None = Field(default=None, max_length=64)
    expected_revision: int = Field(default=0, ge=0)
    kind: MasterKind
    code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    status: Literal["DRAFT", "ACTIVE", "INACTIVE"] = "DRAFT"
    data: MasterFields


class ResolveChaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: Literal["huakang-c"]
    request_id: UUID
    expected_source_revision: int = Field(ge=1)
    expected_receipt_count: int = Field(ge=0)
    expected_resolution_revision: int = Field(ge=0)
    starting_quantity: str = Field(min_length=1, max_length=32)
    evidence: str = Field(min_length=1, max_length=2000)
    confirmed_start: bool = False


class LocationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    warehouse: str = Field(min_length=1, max_length=128)
    bins: str = Field(min_length=1, max_length=16000)


class LocationPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    factory_id: Literal["huakang-c"]
    rows: list[LocationInput] = Field(min_length=1, max_length=1000)


class LocationApplyRequest(LocationPreviewRequest):
    request_id: UUID
    preview_token: str = Field(min_length=1, max_length=64)


class WarehouseRenameRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: Literal["huakang-c"]
    request_id: UUID
    warehouse: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    expected_group_token: str = Field(min_length=64, max_length=64)
