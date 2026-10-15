from typing import Literal
from pydantic import BaseModel, Field, field_validator
from app.schemas.internal_quote import InternalQuoteSectionCode


class AlternativeCopyRequest(BaseModel):
    revision: int = Field(ge=1)
    family_revision: int = Field(ge=0)
    kind: Literal["scenario", "version"]
    name: str = Field(default="", max_length=128)
    change_note: str = Field(min_length=1, max_length=2000)
    copy_departments: list[InternalQuoteSectionCode] | None = Field(default=None, min_length=1, max_length=9)

    @field_validator("copy_departments")
    @classmethod
    def unique_departments(cls, value):
        if value is not None and len(value) != len(set(value)):
            raise ValueError("复制部门不能重复")
        return value

    @field_validator("name", "change_note")
    @classmethod
    def trim(cls, value):
        return value.strip()


class SeriesExportProduct(BaseModel):
    quote_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)


class SeriesExportRequest(BaseModel):
    products: list[SeriesExportProduct] = Field(min_length=2, max_length=20)


class AlternativeExportRequest(BaseModel):
    versions: list[SeriesExportProduct] = Field(min_length=2, max_length=20)


class AlternativeSelectionRequest(BaseModel):
    family_revision: int = Field(ge=0)
    selected_quote_id: str = Field(default="", max_length=64)
    reason: str = Field(min_length=1, max_length=2000)


class AlternativeArchiveRequest(BaseModel):
    family_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=2000)
    archived: bool


class AlternativeSyncTarget(BaseModel):
    quote_id: str = Field(min_length=1, max_length=64)
    revision: int = Field(ge=1)
    create_version: bool = False


class AlternativeSyncRequest(BaseModel):
    revision: int = Field(ge=1)
    family_revision: int = Field(ge=0)
    blocks: list[str] = Field(min_length=1, max_length=20)
    targets: list[AlternativeSyncTarget] = Field(min_length=1, max_length=10)
    reason: str = Field(min_length=1, max_length=1000)
    preview_token: str = Field(default="", max_length=64)
