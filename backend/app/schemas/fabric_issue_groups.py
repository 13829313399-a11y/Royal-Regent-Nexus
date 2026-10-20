from datetime import date
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class GroupSave(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=0)
    group_id: str = Field(default='', max_length=64)
    order_no: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    request_ids: list[str] = Field(min_length=2, max_length=100)


class GroupPreview(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    group_id: str = Field(min_length=1, max_length=64)
    business_date: date


class GroupIssueLine(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    original_id: str = Field(min_length=1, max_length=64)
    batch_id: str = Field(min_length=1, max_length=64)
    quantity: str = Field(min_length=1, max_length=32)


class GroupIssue(GroupPreview):
    request_id: UUID
    expected_revision: int = Field(ge=0)
    token: str = Field(min_length=64, max_length=64)
    confirmed: bool = False
    reason: str = Field(default='', max_length=1000)
    items: list[GroupIssueLine] = Field(min_length=1, max_length=500)


class SaveRecovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['group']
    body: GroupSave


class IssueRecovery(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['issue']
    body: GroupIssue


GroupRecovery = Annotated[SaveRecovery | IssueRecovery, Field(discriminator='kind')]
