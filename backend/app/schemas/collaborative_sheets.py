import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, field_validator


class RevisionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    principal_type: Literal["user", "department"]
    principal_id: str = Field(min_length=1, max_length=64)
    sheet: int = Field(ge=0, le=49)
    range: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]*(:[A-Z]{1,3}[1-9][0-9]*)?$")


class GrantsInput(RevisionInput):
    grants: list[Grant] = Field(max_length=200)


class StateInput(RevisionInput):
    status: Literal["open", "closed"]


class CellChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sheet: int = Field(ge=0, le=49)
    address: str = Field(pattern=r"^[A-Z]{1,3}[1-9][0-9]*$")
    value: StrictStr | StrictInt | StrictFloat | StrictBool | None

    @field_validator("value")
    @classmethod
    def safe_value(cls, value):
        if isinstance(value, str):
            if len(value.encode("utf-16-le")) // 2 > 2000 or any(ord(c) < 32 and c not in "\t\n\r" for c in value):
                raise ValueError("每格最多 2000 字符，不支持控制字符")
            if value.lstrip().startswith("="):
                raise ValueError("填写区不接受公式；原表公式保持只读")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                valid = math.isfinite(value) and abs(value) <= 1e100
            except OverflowError:
                valid = False
            if not valid:
                raise ValueError("数值超出支持范围")
        return value


class CellsInput(RevisionInput):
    changes: list[CellChange] = Field(min_length=1, max_length=500)
