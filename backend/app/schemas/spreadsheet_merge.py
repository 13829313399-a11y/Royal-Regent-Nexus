"""Request-local spreadsheet conversion contracts; no business writes or file IDs."""
import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr, model_validator

Cell = StrictStr | StrictInt | StrictFloat | StrictBool | None


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MergeTable(StrictModel):
    name: str = Field(min_length=1, max_length=255)
    header_row: int = Field(default=1, ge=1, le=1048576)
    headers: list[str] = Field(min_length=1, max_length=256)
    rows: list[list[Cell]] = Field(default_factory=list, max_length=5000)

    @model_validator(mode="after")
    def bounded_cells(self):
        def invalid_text(value):
            return any(ord(c) < 32 and c not in "\t\r\n" for c in value)
        if invalid_text(self.name):
            raise ValueError("来源名称包含无效控制字符")
        if any(not h.strip() or len(h) > 255 or invalid_text(h) for h in self.headers):
            raise ValueError("列名不能为空且最多 255 字")
        if sum(len(row) for row in self.rows) > 250000:
            raise ValueError("每次最多处理 250000 个单元格")
        for row in self.rows:
            if len(row) > len(self.headers):
                raise ValueError("数据行不能超出表头列数")
            for value in row:
                if isinstance(value, str) and (len(value) > 32767 or invalid_text(value)):
                    raise ValueError("单元格文本过长或包含无效控制字符")
                if isinstance(value, float) and not math.isfinite(value):
                    raise ValueError("数值必须有限")
        return self


class ColumnMapping(StrictModel):
    source: int = Field(ge=0, le=255)
    target: int = Field(ge=0, le=255)


class MergeRequest(StrictModel):
    primary: MergeTable
    secondary: MergeTable
    audit_tables: list[MergeTable] = Field(default_factory=list, max_length=50)
    mapping: list[ColumnMapping] = Field(default_factory=list, max_length=256)
    key_columns: list[int] = Field(default_factory=list, max_length=256)
    remarks_column: int | None = Field(default=None, ge=0, le=255)
    extra_columns_to_remarks: list[int] = Field(default_factory=list, max_length=256)
    resolutions: dict[str, Literal["primary", "secondary"]] = Field(default_factory=dict, max_length=250000)
    profile: Literal["generic", "carton-packaging"] = "generic"
    template_id: Literal["carton-packaging", "carton-paper-options", "carton-locations", "carton-history-orders", "carton-opening-inventory", "carton-weekly-schedule"] | None = None
    factory_id: str | None = Field(default=None, max_length=64)
    batch_size: int | None = Field(default=None, ge=1, le=1000)

    @model_validator(mode="after")
    def references(self):
        tables = [self.primary, self.secondary, *self.audit_tables]
        if sum(len(row) for table in tables for row in table.rows) > 250000:
            raise ValueError("数据与审计原表合计最多 250000 个单元格")
        if sum(len(table.rows) for table in tables) > 10000:
            raise ValueError("数据与审计原表合计最多 10000 行")
        if any(m.source >= len(self.secondary.headers) or m.target >= len(self.primary.headers) for m in self.mapping):
            raise ValueError("字段映射列超出范围")
        if len({m.source for m in self.mapping}) != len(self.mapping) or len({m.target for m in self.mapping}) != len(self.mapping):
            raise ValueError("同一来源列或目标列只能映射一次")
        if len(set(self.key_columns)) != len(self.key_columns) or any(k < 0 or k >= len(self.primary.headers) for k in self.key_columns):
            raise ValueError("匹配键列无效或重复")
        if not set(self.key_columns).issubset({m.target for m in self.mapping}):
            raise ValueError("每个匹配键必须设置副表字段映射")
        if self.remarks_column is not None and self.remarks_column >= len(self.primary.headers):
            raise ValueError("备注列超出主表范围")
        if len(set(self.extra_columns_to_remarks)) != len(self.extra_columns_to_remarks) or any(c < 0 or c >= len(self.secondary.headers) or c in {m.source for m in self.mapping} for c in self.extra_columns_to_remarks):
            raise ValueError("备注附加列必须是未映射的有效副表列")
        if self.extra_columns_to_remarks and self.remarks_column is None:
            raise ValueError("请指定附加内容的备注目标列")
        return self
