from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.carton_procurement import _validate_business_identifier


class ContractMerge(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=16, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    contract_no: str = Field(min_length=1, max_length=128)
    expected_revisions: dict[str, int] = Field(min_length=2, max_length=50)
    reason: str = Field(min_length=4, max_length=500)

    @field_validator("contract_no")
    @classmethod
    def valid_contract(cls, value):
        return _validate_business_identifier(value, label="新合同号")

    @field_validator("expected_revisions")
    @classmethod
    def valid_orders(cls, values):
        if any(not key.strip() or len(key) > 64 or revision < 1 for key, revision in values.items()):
            raise ValueError("订单编号或版本无效")
        return values
