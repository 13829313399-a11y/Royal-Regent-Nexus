from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PaperConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    packaging_type: str = Field(min_length=1, max_length=64)
    paper_quality: str = Field(default="", max_length=128)
    specification: str = Field(default="", max_length=255)
    dimension_unit: str = Field(default="", max_length=16)
    unit: str = Field(min_length=1, max_length=32)
    usage_quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=8)


class NumberRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    mode: Literal["AUTO", "OFF", "WARN", "BLOCK"] = "AUTO"
    prefix: str = Field(default="", max_length=32)
    min_length: int = Field(default=0, ge=0, le=128)
    max_length: int = Field(default=128, ge=1, le=128)
    characters: Literal["ANY", "DIGITS", "ALNUM_DASH"] = "ANY"
    templates: list[str] = Field(default_factory=list, max_length=20)
    frozen: bool = False
    reset: bool = False
    sample_text: str = Field(default="", max_length=12000)
    source: Literal["NONE", "MANUAL", "HISTORY"] = "NONE"
    sample_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def bounds(self):
        from app.services.carton_number_templates import parse_template
        for template in self.templates:
            parse_template(template)
        if self.frozen and not self.templates:
            raise ValueError("固定格式至少需要一条样式")
        if self.templates and not self.frozen:
            raise ValueError("编号样式须保存为固定格式")
        if self.min_length > self.max_length:
            raise ValueError("最小长度不能大于最大长度")
        return self


class MasterData(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    product_name: str = Field(default="", max_length=255)
    packing_name: str = Field(default="", max_length=80)
    lines: list[PaperConfiguration] = Field(default_factory=list, max_length=50)
    item_nos: list[str] = Field(default_factory=list, max_length=1000)
    note: str = Field(default="", max_length=1000)
    lead_days: int | None = Field(default=None, ge=0, le=365)
    production_days: int | None = Field(default=None, ge=0, le=365)
    customer_days: int | None = Field(default=None, ge=0, le=730)
    customer_days_disabled: bool = False
    customer_po_rule: NumberRule = Field(default_factory=NumberRule)
    contract_rule: NumberRule = Field(default_factory=NumberRule)
    item_rule: NumberRule = Field(default_factory=NumberRule)
    warehouses: list[str] = Field(default_factory=list, max_length=100)
    paper_types: list[str] = Field(default_factory=list, max_length=200)
    paper_qualities: list[str] = Field(default_factory=list, max_length=500)
    specifications: list[str] = Field(default_factory=list, max_length=1000)

    hidden_paper_types: list[str] = Field(default_factory=list, max_length=200)
    hidden_paper_qualities: list[str] = Field(default_factory=list, max_length=500)
    hidden_specifications: list[str] = Field(default_factory=list, max_length=1000)

    @model_validator(mode="after")
    def paper_options(self):
        for key, limit in (("paper_types", 64), ("paper_qualities", 128), ("specifications", 255), ("hidden_paper_types", 64), ("hidden_paper_qualities", 128), ("hidden_specifications", 255)):
            values = getattr(self, key)
            if any(not value.strip() or len(value.strip()) > limit for value in values):
                raise ValueError(f"纸品选项不能为空且不能超过 {limit} 字")
            setattr(self, key, list(dict.fromkeys(value.strip() for value in values)))
        return self


class MasterSave(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    kind: Literal["CONFIG", "CONTRACT", "RULE", "WORKSHOP", "ACCESS"]
    customer_code: str = Field(default="", max_length=64)
    code: str = Field(default="", max_length=128)
    data: MasterData
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
    preferred: bool = False
    expected_revision: int = Field(default=0, ge=0)
    reason: str = Field(min_length=4, max_length=500)


class MasterImportResult(BaseModel):
    factory_id: str
    kind: Literal["paper-options", "configurations", "locations"]
    fingerprint: str
    master_revision: str
    preview_token: str
    added: int
    skipped: int
    errors: list[str]
    details: list[str]


class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    warehouse: str = Field(min_length=1, max_length=64)
    bin_code: str = Field(default="", max_length=64)
    status: Literal["ACTIVE", "INACTIVE"]
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=4, max_length=500)


class WarehouseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    warehouse: str = Field(min_length=1, max_length=64)
    bin_code: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=4, max_length=500)


class WarehouseRename(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    warehouse: str = Field(min_length=1, max_length=64)
    new_name: str = Field(min_length=1, max_length=64)
    expected_locations: dict[str, int] = Field(min_length=1)
    reason: str = Field(min_length=4, max_length=500)


class WarehouseDelete(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    factory_id: str = Field(min_length=1, max_length=64)
    warehouse: str = Field(min_length=1, max_length=64)
    expected_locations: dict[str, int] = Field(min_length=1)
    reason: str = Field(min_length=4, max_length=500)
