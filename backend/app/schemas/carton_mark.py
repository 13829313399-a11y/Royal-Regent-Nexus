from pydantic import BaseModel, Field


class CartonMarkExtractedField(BaseModel):
    key: str
    label: str
    value: str
    confidence: float = Field(ge=0, le=1)
    source: str


class CartonMarkComparisonItem(BaseModel):
    side: str
    field_key: str
    label: str
    comparison_scope: str = "right_value"
    expected: str
    actual: str
    status: str
    confidence: float = Field(ge=0, le=1)
    note: str = ""


class CartonMarkExtractionStatus(BaseModel):
    source: str
    ok: bool
    engine: str
    message: str = ""
    raw_text: str = ""


class CartonMarkAutoCheckSummary(BaseModel):
    overall_status: str
    pass_count: int
    mismatch_count: int
    missing_count: int
    review_count: int


class CartonMarkAutoCheckResponse(BaseModel):
    summary: CartonMarkAutoCheckSummary
    template_fields: list[CartonMarkExtractedField]
    front_template_fields: list[CartonMarkExtractedField] = Field(default_factory=list)
    side_template_fields: list[CartonMarkExtractedField] = Field(default_factory=list)
    front_photo_fields: list[CartonMarkExtractedField]
    side_photo_fields: list[CartonMarkExtractedField]
    comparisons: list[CartonMarkComparisonItem]
    extraction: list[CartonMarkExtractionStatus]


class CartonMarkBatchCheckItem(BaseModel):
    side: str
    file_name: str
    file_index: int = Field(ge=0)
    result: CartonMarkAutoCheckResponse


class CartonMarkBatchCheckResponse(BaseModel):
    summary: CartonMarkAutoCheckSummary
    items: list[CartonMarkBatchCheckItem]
