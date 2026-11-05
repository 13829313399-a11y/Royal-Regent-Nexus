"""Source-only identity for independent batch orders from a weekly schedule."""
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.carton_procurement import CartonScheduleOrderSource, CartonOrderLineCreate, _validate_iso_date


class SchedulePaperOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_no: int = Field(ge=1, le=50)
    manual_quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    net_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)
    gross_weight_kg: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=4)


class ScheduleOrderOverrides(CartonScheduleOrderSource):
    model_config = ConfigDict(extra="forbid")

    lines: list[SchedulePaperOverride] = Field(min_length=1, max_length=50)


class ScheduleBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_id: str = Field(min_length=1, max_length=64)
    request_id: str = Field(min_length=16, max_length=96, pattern=r"^[A-Za-z0-9_-]+$")
    sources: list[CartonScheduleOrderSource] = Field(min_length=1, max_length=100)
    planned_due_date: str
    lines: list[CartonOrderLineCreate] = Field(min_length=1, max_length=50)
    master_config_id: str = Field(default="", max_length=96)
    master_config_revision: int = Field(default=0, ge=0)
    note: str = Field(default="", max_length=4000)
    rush: bool = False
    rush_reason: str = Field(default="", max_length=255)
    order_overrides: list[ScheduleOrderOverrides] = Field(default_factory=list, max_length=100)

    @field_validator("planned_due_date")
    @classmethod
    def date_value(cls, value):
        return _validate_iso_date(value)

    @model_validator(mode="after")
    def unique_sources(self):
        keys = [(s.batch_id, s.source_sheet, s.source_row) for s in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("不能重复选择同一条排期")
        if any(line.required_quantity is not None or
               (line.quantity_rule and line.quantity_rule.manual_quantity is not None) for line in self.lines):
            raise ValueError("公共纸品不能提交手动需求数量，请在各订单的纸品中单独填写")
        seen = set()
        for override in self.order_overrides:
            key = (override.batch_id, override.source_sheet, override.source_row)
            if key not in keys or key in seen:
                raise ValueError("逐单设置必须对应所选排期，且不能重复同一条排期")
            seen.add(key)
            positions = [line.line_no for line in override.lines]
            if len(positions) != len(set(positions)) or any(n > len(self.lines) for n in positions):
                raise ValueError("逐单纸品设置不能重复，且必须对应当前有效纸品行")
        return self
