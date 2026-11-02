from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class FileOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    mode: Literal["REGULAR", "SPECIAL"]
    sheet: str = Field(default="", max_length=128)
    header_row: int | None = Field(default=None, ge=1, le=50)
    mapping: dict[str, int] | None = None


class ImportRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_row: int = Field(ge=2, le=551)
    data: dict[str, str]

    @field_validator("data")
    @classmethod
    def bounded(cls, data):
        if len(data) > 32 or any(len(key) > 64 or len(value) > 2000 for key, value in data.items()):
            raise ValueError("导入字段过长")
        return {key: value.strip() for key, value in data.items()}


class Preview(FileOptions):
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: list[ImportRow] = Field(min_length=1, max_length=500)


class Confirm(Preview):
    request_id: str = Field(min_length=16, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    selected_groups: list[str] = Field(min_length=1, max_length=100)
    preview_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
