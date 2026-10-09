from decimal import Decimal
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Code = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6, allow_inf_nan=False)]
Kind = Literal['material', 'resource', 'bom']


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Material(Strict):
    name: Text
    category: Literal['fabric', 'accessory']
    unit: Text
    specification: Annotated[str, Field(max_length=200)] = ''
    color: Annotated[str, Field(max_length=120)] = ''
    source_reference: Text


class Resource(Strict):
    name: Text
    execution: Literal['internal', 'outsourced']
    process: Literal['cutting'] = 'cutting'
    contact: Annotated[str, Field(max_length=120)] = ''
    source_reference: Text


class Part(Strict):
    code: Code
    name: Text
    pieces_per_set: Annotated[int, Field(strict=True, ge=1, le=100000)]


class Requirement(Strict):
    material_id: Text
    material_version: Annotated[int, Field(strict=True, ge=1)]
    part_codes: Annotated[list[Code], Field(min_length=1, max_length=200)]
    quantity_per_set: Quantity
    unit: Text
    required_for_cutting: bool
    stage: Text
    note: Annotated[str, Field(max_length=300)] = ''


class Bom(Strict):
    name: Text
    item_no: Code
    style: Text
    color: Text
    source_reference: Text
    parts: Annotated[list[Part], Field(min_length=1, max_length=200)]
    requirements: Annotated[list[Requirement], Field(min_length=1, max_length=300)]

    @model_validator(mode='after')
    def consistent_parts(self):
        codes = [p.code for p in self.parts]
        if len(set(codes)) != len(codes):
            raise ValueError('部件编码不能重复')
        for row in self.requirements:
            if len(set(row.part_codes)) != len(row.part_codes) or not set(row.part_codes) <= set(codes):
                raise ValueError('物料适用部件必须来自当前 BOM，且不能重复')
        return self


class Command(Strict):
    factory_id: Literal['huakang-c']
    operation_id: Annotated[str, StringConstraints(pattern=r'^[A-Za-z0-9_-]{16,64}$')]
    expected_version: Annotated[int, Field(strict=True, ge=0)]
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Save(Command):
    kind: Kind
    code: Code
    data: dict


class StateChange(Command):
    status: Literal['active', 'inactive', 'published']


DATA_MODELS = {'material': Material, 'resource': Resource, 'bom': Bom}
