from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")


class InjectionSchedulingImportProfileOut(BaseModel):
    id: str
    profile_code: str
    profile_family: str
    revision: int
    lifecycle_revision: int
    name: str
    description: str
    status: Literal["PROFILE_DRAFT", "ACTIVE", "RETIRED"]
    factories: list[str]
    definition_sha256: str
    template_signature: str
    header_fingerprint: str
    renderer_code: str
    config: dict[str, Any]
    created_by: str
    created_by_name: str
    created_at: str
    reviewed_by: str
    reviewed_by_name: str
    reviewed_at: str
    retired_by: str
    retired_by_name: str
    retired_at: str


class InjectionSchedulingImportProfileListOut(BaseModel):
    factory_id: str
    items: list[InjectionSchedulingImportProfileOut]


class InjectionSchedulingImportProfileCreate(StrictProfileWrite):
    factory_id: str
    profile_family: str = Field(min_length=3, max_length=96)
    profile_code: str = Field(min_length=3, max_length=96)
    name: str = Field(min_length=2, max_length=128)
    description: str = Field(default="", max_length=1000)
    expected_family_revision: int = Field(ge=0)
    request_id: str = Field(min_length=8, max_length=128)
    config: dict[str, Any]

    @field_validator(
        "factory_id", "profile_family", "profile_code", "name", "request_id"
    )
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("字段不能为空")
        return value

    @field_validator("profile_family", "profile_code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,95}", value):
            raise ValueError(
                "Profile code/family 只能使用小写字母、数字、下划线或连字符"
            )
        return value


class InjectionSchedulingImportProfileTransition(StrictProfileWrite):
    factory_id: str
    expected_lifecycle_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=128)
    reason: str = Field(min_length=8, max_length=500)

    @field_validator("factory_id", "request_id", "reason")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        return value.strip()
