from pydantic import BaseModel, Field, field_validator


class CartonMarkAssetOrderOut(BaseModel):
    id: str
    order_no: str
    contract_no: str
    customer_name: str
    item_no: str


class CartonMarkAssetOut(BaseModel):
    id: str
    factory_id: str
    file_name: str
    kind: str
    photo_group_id: str | None = None
    size_bytes: int
    sha256: str
    contract_number: str
    bound_order_id: str | None
    recognition_source: str
    candidates: list[str]
    warning: str
    binding_status: str
    orders: list[CartonMarkAssetOrderOut]
    revision: int
    created_by_name: str
    created_at: str


class CartonMarkAssetBindingRequest(BaseModel):
    contract_number: str = Field(default="", max_length=128)
    order_id: str | None = Field(default=None, max_length=96)
    revision: int = Field(ge=1)


class CartonMarkAssetUploadResult(BaseModel):
    file_name: str
    status: str
    message: str = ""
    asset: CartonMarkAssetOut | None = None


class CartonMarkAssetReference(BaseModel):
    id: str = Field(min_length=1, max_length=96)
    revision: int = Field(ge=1)


class CartonMarkPhotoGroupMembers(BaseModel):
    assets: list[CartonMarkAssetReference] = Field(min_length=1, max_length=50)


class CartonMarkPhotoGroupRequest(CartonMarkPhotoGroupMembers):
    contract_number: str = Field(default="", max_length=128)
    order_id: str | None = Field(default=None, max_length=96)


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
    matched_page: int | None = Field(default=None, ge=1)
    page_count: int | None = Field(default=None, ge=1)
    match_confidence: float | None = Field(default=None, ge=0, le=1)
    requires_review: bool = False
    review_reason: str = ""


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


class CartonMarkDocumentTextItem(BaseModel):
    text: str
    location: str
    field_key: str = ""
    # Extraction-only metadata. Artwork text is retained for diagnostics but
    # does not become a PDF-only business-text difference.
    is_graphic_text: bool = Field(default=False, exclude=True)


class CartonMarkDocumentComparisonItem(BaseModel):
    status: str
    expected: str = ""
    actual: str = ""
    expected_location: str = ""
    actual_location: str = ""
    note: str = ""


class CartonMarkDocumentCheckSummary(BaseModel):
    overall_status: str
    pass_count: int
    changed_count: int
    missing_count: int
    unexpected_count: int
    review_count: int


class CartonMarkDocumentCheckResponse(BaseModel):
    excel_file_name: str
    pdf_file_name: str
    summary: CartonMarkDocumentCheckSummary
    excel_items: list[CartonMarkDocumentTextItem]
    pdf_items: list[CartonMarkDocumentTextItem]
    comparisons: list[CartonMarkDocumentComparisonItem]
    extraction: list[CartonMarkExtractionStatus]


class CartonMarkCustomerOptionOut(BaseModel):
    id: str
    name: str


class CartonMarkCustomerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if not normalized:
            raise ValueError("客户名称不能为空")
        return normalized


class CartonMarkCustomerUpdateRequest(CartonMarkCustomerCreateRequest):
    revision: int = Field(ge=1)


class CartonMarkCustomerOut(CartonMarkCustomerOptionOut):
    factory_id: str
    revision: int = Field(ge=1)
    created_by: str
    created_by_name: str
    created_at: str
    updated_by: str
    updated_by_name: str
    updated_at: str


class CartonMarkTemplateManualReleaseRequest(BaseModel):
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def normalize_reason(cls, value: str) -> str:
        normalized = " ".join(value.strip().split())
        if len(normalized) < 5:
            raise ValueError("人工放行理由至少需要 5 个字符")
        return normalized


class CartonMarkTemplateOut(BaseModel):
    id: str
    factory_id: str
    customer_name: str
    po: str
    item: str
    contract_number: str
    version: int = Field(ge=1)
    check_status: str
    check_result: CartonMarkDocumentCheckResponse
    excel_file_name: str
    excel_file_size: int = Field(gt=0)
    pdf_file_name: str
    pdf_file_size: int = Field(gt=0)
    created_at: str
    updated_at: str
    created_by_name: str
    qc_ready: bool
    manual_released: bool
    manual_release_reason: str
    manual_release_source_status: str
    manual_released_by_name: str
    manual_released_at: str
