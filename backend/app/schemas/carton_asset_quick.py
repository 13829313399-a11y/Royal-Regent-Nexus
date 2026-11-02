from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


class Target(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['REGULAR','SCHEDULE','SAMPLE','MISC']
    id: str = Field(min_length=1,max_length=96)
    sheet: str = Field(default='',max_length=128)
    row: int = Field(default=0,ge=0)
    fingerprint: str = Field(min_length=64,max_length=64)


class Upload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: str = Field(min_length=8,max_length=96,pattern=r'^[A-Za-z0-9_-]+$')
    owner_department: str | None = Field(default=None,max_length=64)
    purpose: Literal['MATERIAL','EVIDENCE'] = 'MATERIAL'
    title: str = Field(default='',max_length=200)
    text: str = Field(default='',max_length=20000)
    contract_number: str | None = Field(default=None,max_length=128)
    association: Literal['AUTO','MANUAL','NONE'] = 'AUTO'
    target_scope: Literal['ALL','PENDING_SCHEDULE'] = 'ALL'
    target: Target | None = None
    targets: list[Target] = Field(default_factory=list, max_length=100)
    shared_factory_ids: list[str] = Field(default_factory=list, max_length=20)
    status: Literal['DRAFT','PENDING','READY','HISTORY'] = 'PENDING'
    previous_asset_id: str = Field(default='',max_length=96)
    previous_revision: int | None = Field(default=None,ge=1)


class Associate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    target_scope: Literal['ALL','PENDING_SCHEDULE'] = 'ALL'
    request_id: str = Field(min_length=8,max_length=96,pattern=r'^[A-Za-z0-9_-]+$')
    target: Target | None = None
    targets: list[Target] = Field(default_factory=list, max_length=100)


class Classify(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8,max_length=96,pattern=r'^[A-Za-z0-9_-]+$')
    status: Literal['DRAFT','PENDING','READY','HISTORY']


class Sharing(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8,max_length=96,pattern=r'^[A-Za-z0-9_-]+$')
    shared_factory_ids: list[str] = Field(default_factory=list, max_length=20)
