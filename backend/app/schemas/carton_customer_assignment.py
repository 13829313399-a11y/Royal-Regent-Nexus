from pydantic import BaseModel, ConfigDict, Field


class CartonCustomerAssignmentSave(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    user_ids: list[str] = Field(max_length=100)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)
