from typing import Literal
from pydantic import BaseModel, Field, model_validator

Audience = Literal['sales', 'warehouse', 'supplier']
Party = Literal['SALES', 'WAREHOUSE', 'SUPPLIER']
Mode = Literal['UNDECIDED', 'INTERNAL', 'CUSTOMER']


class Target(BaseModel):
    kind: Literal['LEDGER', 'SCHEDULE', 'PURCHASE']
    id: str = Field(min_length=1, max_length=128)
    sheet: str = Field(default='', max_length=128)
    row: int = Field(default=0, ge=0)


class Contract(BaseModel):
    customer_id: str = Field(min_length=1, max_length=96)
    contract_no: str = Field(min_length=1, max_length=255)
    item_no: str = Field(default='', max_length=255)
    po: str = Field(default='', max_length=255)


class Create(BaseModel):
    target: Target | None = None
    contract: Contract | None = None
    request_id: str = Field(min_length=8, max_length=96)

    @model_validator(mode='after')
    def one_source(self):
        if (self.target is None) == (self.contract is None):
            raise ValueError('请选择真实订单或填写客户和合同，两者只能选一项')
        return self


class Mapping(BaseModel):
    target: Target
    folder_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)


class Statuses(BaseModel):
    targets: list[Target] = Field(max_length=100)


class Command(BaseModel):
    authority_id: str = Field(default='', max_length=96)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)
    action: Literal['CLAIM', 'RULE', 'HANDOFF', 'REQUEST_CHANGES', 'APPROVE', 'COMMENT']
    mode: Mode = 'UNDECIDED'
    next_party: Party = 'WAREHOUSE'
    supplier_id: str = Field(default='', max_length=96)
    note: str = Field(default='', max_length=10000)
    version_ids: list[str] = Field(default_factory=list, max_length=100)
    save_customer_default: bool = False
    default_revision: int = Field(default=0, ge=0)


class Version(BaseModel):
    authority_id: str = Field(default='', max_length=96)
    revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)
    title: str = Field(default='', max_length=255)
    text: str = Field(default='', max_length=10000)
    role: Literal['ORIGINAL', 'WORKING', 'PROOF', 'EVIDENCE'] = 'WORKING'
    previous_id: str = Field(default='', max_length=96)


class ReferenceTarget(BaseModel):
    context_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)


class SharedUpload(Version):
    targets: list[ReferenceTarget] = Field(min_length=1, max_length=100)


class ReferenceCreate(BaseModel):
    source_context_id: str = Field(min_length=1, max_length=96)
    version_id: str = Field(min_length=1, max_length=96)
    targets: list[ReferenceTarget] = Field(min_length=1, max_length=100)
    request_id: str = Field(min_length=8, max_length=96)


class ReferenceRemove(BaseModel):
    revision: int = Field(ge=1)
    reference_revision: int = Field(ge=1)
    request_id: str = Field(min_length=8, max_length=96)


class ApprovalTarget(BaseModel):
    model_config = {'extra': 'forbid'}
    context_id: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)
    version_ids: list[str] = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=10000)


class BatchApproval(BaseModel):
    model_config = {'extra': 'forbid'}
    request_id: str = Field(min_length=8, max_length=96)
    targets: list[ApprovalTarget] = Field(min_length=1, max_length=100)
