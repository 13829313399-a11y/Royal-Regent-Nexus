from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Operation = Literal["word_to_pdf", "pdf_to_word", "word_to_excel", "excel_to_word", "pdf_to_excel", "excel_to_pdf", "pdf_split"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversionOptions(StrictModel):
    page_selection: str = Field(default="all", max_length=2000)
    ai_mode: Literal["auto", "off"] = "auto"
    output_name: str | None = Field(default=None, max_length=180)
    include_notes_sheet: bool = True
    word_mode: Literal["tables", "structure"] = "tables"
    include_headers_footers: bool = False
    merge_continuation_tables: bool = False
    sheets: list[str] = Field(default_factory=list, max_length=100)
    range: str | None = Field(default=None, max_length=128)
    include_hidden: bool = False
    formula_mode: Literal["display", "formula"] = "display"
    paper: Literal["original", "A4", "A3"] = "original"
    orientation: Literal["auto", "portrait", "landscape"] = "auto"
    print_mode: Literal["original", "fit_width", "selection"] = "original"
    layout_mode: Literal["editable", "layout"] = "editable"
    preserve_merges: bool = True
    numeric_locale: Literal["preserve_ambiguous", "dot_decimal", "comma_decimal"] = "preserve_ambiguous"
    table_scope: Literal["all"] = "all"
    split_mode: Literal["groups", "each", "every_n", "extract", "double", "crop"] = "groups"
    groups: str = Field(default="", max_length=4000)
    every_n: int = Field(default=1, ge=1, le=1000)
    duplicate_policy: Literal["keep", "deduplicate"] = "keep"
    axis: Literal["x", "y"] = "y"
    page_index: int = Field(default=0, ge=0)
    cuts_pt: list[float] = Field(default_factory=list, max_length=500)

    @field_validator("cuts_pt")
    @classmethod
    def finite_cuts(cls, value):
        import math
        if any(not math.isfinite(cut) or cut <= 0 for cut in value):
            raise ValueError("切线必须是有限正数")
        if value != sorted(set(value)):
            raise ValueError("切线必须严格递增且不能重复")
        return value


COMMON = {"page_selection", "ai_mode", "output_name"}
OPTION_KEYS = {
    "word_to_pdf": COMMON,
    "word_to_excel": COMMON | {"include_notes_sheet", "word_mode", "include_headers_footers", "merge_continuation_tables"},
    "excel_to_word": COMMON | {"sheets", "range", "include_hidden", "formula_mode", "paper", "orientation"},
    "excel_to_pdf": COMMON | {"sheets", "range", "include_hidden", "formula_mode", "paper", "orientation", "print_mode"},
    "pdf_to_word": COMMON | {"layout_mode"},
    "pdf_to_excel": COMMON | {"merge_continuation_tables", "preserve_merges", "include_notes_sheet", "numeric_locale", "table_scope"},
    "pdf_split": {"output_name", "page_selection", "split_mode", "groups", "every_n", "duplicate_policy", "axis", "page_index", "cuts_pt"},
}


class CreateJob(StrictModel):
    source_id: str = Field(min_length=1, max_length=64)
    operation: Operation
    options: ConversionOptions = Field(default_factory=ConversionOptions)
    client_request_id: str = Field(min_length=1, max_length=96)
    batch_id: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def valid_operation_options(self):
        unknown = self.options.model_fields_set - OPTION_KEYS[self.operation]
        if unknown:
            raise ValueError("当前转换不支持选项：" + ", ".join(sorted(unknown)))
        return self


class Correction(StrictModel):
    target_id: str = Field(min_length=1, max_length=256)
    new_value: str = Field(max_length=32000)
    reason: str = Field(default="", max_length=1000)


class Region(StrictModel):
    page_index: int = Field(ge=0)
    bbox_pt: list[float] = Field(min_length=4, max_length=4)

    @field_validator("bbox_pt")
    @classmethod
    def valid_box(cls, value):
        import math
        if any(not math.isfinite(v) for v in value) or value[0] < 0 or value[1] < 0 or value[2] <= value[0] or value[3] <= value[1]:
            raise ValueError("区域坐标无效")
        return value


class ReviseJob(StrictModel):
    base_revision: int = Field(ge=1)
    corrections: list[Correction] = Field(default_factory=list, max_length=1000)
    region: Region | None = None
    options: ConversionOptions | None = None

    @model_validator(mode="after")
    def nonempty(self):
        if not self.corrections and self.region is None and self.options is None:
            raise ValueError("请提供需要修正的内容、区域或分页设置")
        return self


class PasswordInput(StrictModel):
    password: str = Field(min_length=1, max_length=512, repr=False)


class PackageInput(StrictModel):
    artifact_ids: list[str] = Field(min_length=1, max_length=100)
    client_request_id: str = Field(min_length=1, max_length=96)
