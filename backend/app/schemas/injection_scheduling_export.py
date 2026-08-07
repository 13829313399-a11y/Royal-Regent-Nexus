from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InjectionSchedulingExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_id: str
    expected_plan_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    export_mode: Literal["SOURCE_COMPATIBLE", "SYSTEM_STANDARD"]
    profile_id: str | None = Field(default=None, max_length=96)
    profile_revision: int | None = Field(default=None, ge=1)

    @field_validator("factory_id", "request_id")
    @classmethod
    def strip_export_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("profile_id")
    @classmethod
    def strip_profile_id(cls, value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_profile_pair(self):
        if (self.profile_id is None) != (self.profile_revision is None):
            raise ValueError("profile_id 和 profile_revision 必须同时提供")
        if self.export_mode == "SOURCE_COMPATIBLE" and self.profile_id is None:
            raise ValueError("source-compatible 导出必须显式提供 Profile revision")
        if self.export_mode == "SYSTEM_STANDARD" and self.profile_id is not None:
            raise ValueError("system-standard 导出不接受来源 Profile 覆盖")
        return self


class InjectionSchedulingExportMetadata(BaseModel):
    audit_id: str
    file_name: str
    file_sha256: str
    size_bytes: int
    export_mode: str
    profile_id: str | None
    profile_revision: int
    renderer_code: str
    signing_key_id: str
