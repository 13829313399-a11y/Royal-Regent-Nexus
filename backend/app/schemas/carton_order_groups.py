"""Complete group conversion; incomplete drafts stay in the scoped browser draft."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.carton_procurement import CartonOrderCreate


class GroupOrder(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    row_id: str = Field(min_length=1, max_length=96)
    source: str = Field(default="", max_length=2000)
    order: CartonOrderCreate


class OrderGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=16, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=128)
    rows: list[GroupOrder] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def same_scope(self):
        if len({row.row_id for row in self.rows}) != len(self.rows):
            raise ValueError("合单组款式行编号不能重复")
        scopes = {(row.order.factory_id, row.order.customer_code.strip().upper(), row.order.supplier_id or "") for row in self.rows}
        if len(scopes) != 1 or next(iter(scopes))[0] != self.factory_id:
            raise ValueError("合单草稿必须属于同厂区、同客户、同供应商")
        if any(not row.order.customer_po.strip() for row in self.rows):
            raise ValueError("合单组每款必须明确客户 PO")
        return self
