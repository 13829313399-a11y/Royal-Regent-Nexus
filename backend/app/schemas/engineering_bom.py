from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Qty = Annotated[Decimal, Field(ge=0, le=100000000, max_digits=24, decimal_places=12, allow_inf_nan=False)]


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Command(Strict):
    factory_id: Literal['huakang-c']
    operation_id: Annotated[str, StringConstraints(pattern=r'^[a-zA-Z0-9_-]{16,64}$')]
    expected_version: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)


class Material(Command):
    id: str = ''
    code: str = Field(default='', max_length=128)
    group: Annotated[str, StringConstraints(pattern=r'^0[1-4](?:-\d{2}){0,3}$')]
    name: str = Field(min_length=1, max_length=255)
    unit: Text
    department: Text
    specification: str = Field(default='', max_length=500)
    color: str = Field(default='', max_length=128)
    old_code: str = Field(default='', max_length=128)
    attribute: Literal['外购', '自制', '委外', '客供'] = '外购'
    warehouse_category: Literal['', 'FABRIC', 'ACCESSORY', 'THREAD'] = ''


class Node(Strict):
    key: Text
    parent: str = Field(default='', max_length=128)
    material_id: str = Field(default='', max_length=64)
    material_version: int = Field(default=0, ge=0)
    source_code: str = Field(default='', max_length=128)
    source_name: str = Field(default='', max_length=255)
    unit: str = Field(default='', max_length=128)
    numerator: Qty = Decimal(1)
    denominator: Qty = Decimal(1)
    process: str = Field(default='', max_length=128)
    exempt_loss: bool = False
    note: str = Field(default='', max_length=500)
    source: dict[str, str] = Field(default_factory=dict, max_length=20)
    review_required: bool = False
    review_note: str = Field(default='', max_length=500)


class BomData(Strict):
    item_no: Text
    name: str = Field(min_length=1, max_length=255)
    specification: str = Field(default='', max_length=500)
    nodes: list[Node] = Field(min_length=1, max_length=500)
    source_reference: str = Field(default='', max_length=500)
    source_sha256: Annotated[str, StringConstraints(pattern=r'^(?:[0-9a-f]{64})?$')] = ''


class SaveBom(Command):
    data: BomData
    copy_from: str = Field(default='', max_length=64)
    copy_version: int | None = Field(default=None, ge=1)
