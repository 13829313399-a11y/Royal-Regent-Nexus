from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

Kind = Literal['RECEIPT', 'REQUEST', 'ISSUE', 'RETURN', 'TRANSFER', 'QUALITY', 'CORRECTION', 'TASK', 'PROCESS_SEND', 'PROCESS_RETURN', 'PACK_SEND', 'PACK_RECEIVE', 'LOCATION_BIND']


class Allocation(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    production_no: str = Field(min_length=1, max_length=128)
    quantity: str = Field(min_length=1, max_length=32)


class WarehouseDocumentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=0)
    kind: Kind
    business_date: date
    source_system: str = Field(default='MANUAL', min_length=1, max_length=64)
    source_no: str = Field(default='', max_length=128)
    source_line: str = Field(default='', max_length=128)
    source_version: str = Field(default='', max_length=128)
    item_code: str = Field(default='', max_length=128)
    item_name: str = Field(default='', max_length=255)
    unit: str = Field(default='', max_length=32)
    process_state: str = Field(default='', max_length=64)
    material_category: Literal['FABRIC', 'ACCESSORY', 'THREAD'] = 'FABRIC'
    location: str = Field(default='', max_length=128)
    location_id: str = Field(default='', max_length=64)
    confirmed: bool = False
    lot: str = Field(default='', max_length=128)
    roll_no: str = Field(default='', max_length=128)
    quantity: str = Field(default='', max_length=32)
    consumed_quantity: str = Field(default='', max_length=32)
    counterparty: str = Field(default='', max_length=255)
    production_no: str = Field(default='', max_length=128)
    purpose: str = Field(default='', max_length=255)
    due_date: date | None = None
    batch_id: str = Field(default='', max_length=64)
    original_id: str = Field(default='', max_length=64)
    task_id: str = Field(default='', max_length=64)
    quality_status: Literal['PENDING_INSPECTION', 'QUALIFIED', 'REJECTED', 'HOLD'] = 'PENDING_INSPECTION'
    responsible_person: str = Field(default='', max_length=128)
    reason: str = Field(default='', max_length=1000)
    allocations: list[Allocation] = Field(default_factory=list, max_length=100)


class WarehouseLocationSave(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    id: str = Field(default='', max_length=64)
    expected_revision: int = Field(ge=0)
    warehouse: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    status: Literal['ACTIVE', 'INACTIVE'] = 'ACTIVE'


class WarehouseIssueLine(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    batch_id: str = Field(min_length=1, max_length=64)
    quantity: str = Field(min_length=1, max_length=32)
    counterparty: str = Field(default='', max_length=255)


class WarehouseBulkIssue(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: Literal['huakang-c']
    request_id: UUID
    expected_revision: int = Field(ge=0)
    business_date: date
    counterparty: str = Field(min_length=1, max_length=255)
    reason: str = Field(default='', max_length=1000)
    items: list[WarehouseIssueLine] = Field(min_length=1, max_length=100)
