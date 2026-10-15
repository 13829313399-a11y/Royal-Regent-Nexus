from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CorrectedMaterial(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(min_length=1, max_length=128)
    specification: str = Field(min_length=1, max_length=255)
    dimension_unit: Literal['cm', 'inch', 'mm']


class MaterialCorrectionCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: str
    request_id: str = Field(min_length=16, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')
    expected_revision: int = Field(ge=1)
    issue_id: str
    order_line_id: str
    after: CorrectedMaterial
    reason: str = Field(default='填错了', max_length=1000)

    @field_validator('reason')
    @classmethod
    def default_empty_reason(cls, value: str) -> str:
        return value or '填错了'


class MaterialCorrectionAction(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    factory_id: str
    request_id: str = Field(min_length=16, max_length=96, pattern=r'^[A-Za-z0-9_-]+$')
    expected_revision: int = Field(ge=1)
    action: Literal['APPROVE', 'RETURN', 'WITHDRAW']
    note: str = Field(default='', max_length=1000)
    verified: bool = False
