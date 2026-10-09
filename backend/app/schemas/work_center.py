from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class UserStatePatch(BaseModel):
    following: bool | None = None
    model_config = ConfigDict(extra="forbid")
    observed_content_version: int | None = Field(default=None, ge=0)
    state_version: int | None = Field(default=None, ge=0)
    snoozed_until: datetime | None = None
    archived: bool | None = None
    pinned: bool | None = None


class BatchItem(UserStatePatch):
    id: str = Field(min_length=1, max_length=512)


class UserStateBatch(BaseModel):
    items: list[BatchItem] = Field(min_length=1, max_length=100)


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sound_enabled: bool | None = None
    toast_level: Literal["assigned", "all_tasks", "none"] | None = None
    version: int | None = Field(default=None, ge=0)
