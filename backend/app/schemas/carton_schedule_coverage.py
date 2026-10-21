from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class MissingReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=8, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    expected_revision: int = Field(ge=1)
    source_fingerprint: str = Field(min_length=64, max_length=64)
    decision: Literal["KEEP_REQUIRED", "SOURCE_OMISSION", "NO_LONGER_REQUIRED", "REOPEN"]
    reason: str = Field(min_length=4, max_length=2000)
