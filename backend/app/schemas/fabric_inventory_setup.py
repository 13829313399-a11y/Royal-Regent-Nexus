from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class CountCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    batch_ids: list[str] = Field(min_length=1, max_length=500)
    reason: str = Field(min_length=1, max_length=1000)


class CountLine(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    batch_id: str = Field(min_length=1, max_length=64)
    actual: str = Field(default='', max_length=32)
    reason: str = Field(default='', max_length=1000)


class CountAction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=1)
    action: Literal['SAVE', 'REFRESH', 'POST', 'CANCEL']
    business_date: date
    confirmed: bool = False
    reason: str = Field(default='', max_length=1000)
    lines: list[CountLine] = Field(default_factory=list, max_length=500)
