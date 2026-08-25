from decimal import Decimal, InvalidOperation
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


InitiatorDepartment = Literal["sales-business", "engineering"]
ReviewDecision = Literal["approve", "reject"]
InternalQuoteWorkflowMode = Literal["section_review", "whole_quote_review"]
InternalQuoteType = Literal["single", "series", "multi_region"]
InternalQuoteRegionCode = Literal["", "mainland", "indonesia"]
InternalQuoteImportType = Literal["mold", "hardware", "electronic", "molding", "painting", "slush", "sewing", "assembly"]
InternalQuoteSectionCode = Literal[
    "sales",
    "engineering",
    "electronic",
    "molding",
    "painting",
    "slush",
    "sewing",
    "hair",
    "assembly",
]
MANDATORY_SECTION_CODES = ("sales", "engineering", "assembly")
OPTIONAL_SECTION_CODES = ("electronic", "molding", "painting", "slush", "sewing", "hair")
SECTION_CODE_ORDER = (
    "engineering",
    "molding",
    "assembly",
    "painting",
    "electronic",
    "slush",
    "sewing",
    "hair",
    "sales",
)


def _normalize_section_codes(values: list[InternalQuoteSectionCode]) -> list[InternalQuoteSectionCode]:
    selected = set(values)
    return [code for code in SECTION_CODE_ORDER if code in selected]


def _validate_participating_sections(
    values: list[InternalQuoteSectionCode],
) -> list[InternalQuoteSectionCode]:
    missing = [code for code in MANDATORY_SECTION_CODES if code not in values]
    if missing:
        raise ValueError("业务部、工程部、装配部必须参与内部报价")
    return _normalize_section_codes(values)


def _positive_decimal_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name}必须是有效数字") from error
    if not parsed.is_finite() or parsed <= 0:
        raise ValueError(f"{field_name}必须大于 0")
    return format(parsed, "f")


def _nonnegative_decimal_text(value: str, field_name: str) -> str:
    normalized = value.strip()
    try:
        parsed = Decimal(normalized)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{field_name}必须是有效数字") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{field_name}不能小于 0")
    return format(parsed, "f")


class InternalQuoteProductCreateRequest(BaseModel):
    product_name: str = Field(min_length=1, max_length=255)
    qty: int = Field(gt=0)
    region_code: InternalQuoteRegionCode = ""

    @field_validator("product_name")
    @classmethod
    def strip_product_name(cls, value: str) -> str:
        return value.strip()


class InternalQuoteCreateRequest(BaseModel):
    factory_id: str = Field(min_length=1, max_length=64)
    workshop_code: str = Field(default="huaxing-workshop", min_length=1, max_length=64)
    workshop_name: str = Field(default="华兴", min_length=1, max_length=128)
    quote_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(min_length=1, max_length=255)
    customer: str = Field(min_length=1, max_length=128)
    qty: int = Field(gt=0)
    version_label: str = Field(default="V1", min_length=1, max_length=64)
    initiator_department: InitiatorDepartment
    business_owner_id: str = Field(min_length=1, max_length=64)
    business_owner_name: str = Field(min_length=1, max_length=128)
    target_customer_price: str = Field(default="无", min_length=1, max_length=128)
    target_date: str = Field(default="", max_length=32)
    remark: str = Field(default="", max_length=4000)
    workflow_mode: InternalQuoteWorkflowMode = "section_review"
    quote_type: InternalQuoteType = "single"
    products: list[InternalQuoteProductCreateRequest] = Field(default_factory=list, max_length=20)
    pricing_components: list[str] = Field(default_factory=list, max_length=50)
    participating_sections: list[InternalQuoteSectionCode] = Field(
        default_factory=lambda: [
            code for code in SECTION_CODE_ORDER if code in MANDATORY_SECTION_CODES
        ]
    )

    @field_validator(
        "factory_id",
        "workshop_code",
        "workshop_name",
        "quote_no",
        "product_name",
        "customer",
        "version_label",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("target_customer_price")
    @classmethod
    def validate_target_customer_price(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("客人目标价不能为空，客人未提供时请填写‘无’")
        return normalized

    @field_validator("participating_sections")
    @classmethod
    def validate_participating_sections(
        cls, values: list[InternalQuoteSectionCode]
    ) -> list[InternalQuoteSectionCode]:
        return _validate_participating_sections(values)

    @model_validator(mode="after")
    def validate_products(self):
        products = self.products or [
            InternalQuoteProductCreateRequest(
                product_name=self.product_name,
                qty=self.qty,
            )
        ]
        if len(products) > 20:
            raise ValueError("一批内部报价最多包含 20 款产品")
        if self.quote_type == "single" and len(products) != 1:
            raise ValueError("单款报价只能包含 1 款产品")
        if self.quote_type == "multi_region" and len(products) < 2:
            raise ValueError("多地区报价至少需要大陆价和印尼价两款")
        normalized_factory = "".join(character for character in self.factory_id.lower() if character.isalnum())
        normalized_customer = "".join(character for character in self.customer.lower() if character.isalnum())
        is_justplay = normalized_factory == "huakangb" and normalized_customer == "justplay"
        component_names = [name.strip() for name in self.pricing_components if name.strip()]
        if len(component_names) != len({name.casefold() for name in component_names}):
            raise ValueError("JustPlay 分项名称不能重复")
        if any(len(name) > 64 for name in component_names):
            raise ValueError("JustPlay 分项名称不能超过 64 个字符")
        if is_justplay and not component_names:
            raise ValueError("华康B JustPlay 报价至少要建立一个分项")
        if not is_justplay and component_names:
            raise ValueError("只有华康B JustPlay 报价可以在建单时建立分项")
        self.pricing_components = component_names
        self.products = products
        return self


class InternalQuoteBatchCopyRequest(BaseModel):
    revision: int = Field(ge=1)


class InternalQuoteBusinessOwnerOut(BaseModel):
    id: str
    username: str
    display_name: str


class InternalQuoteCustomerCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip()


class InternalQuoteCustomerUpdateRequest(InternalQuoteCustomerCreateRequest):
    revision: int = Field(ge=1)


class InternalQuoteCustomerOut(BaseModel):
    id: str
    factory_id: str
    name: str
    revision: int
    created_by: str
    created_by_name: str
    created_at: str
    updated_by: str
    updated_by_name: str
    updated_at: str


class InternalQuoteDashboardTotalsOut(BaseModel):
    total: int
    in_progress: int
    completed: int
    canceled: int


class InternalQuoteDashboardStatusOut(BaseModel):
    key: Literal["in_progress", "completed", "canceled"]
    label: str
    count: int
    percentage: float


class InternalQuoteDashboardCustomerCountOut(BaseModel):
    customer: str
    count: int
    percentage: float


class InternalQuoteDashboardProgressOut(BaseModel):
    quote_id: str
    quote_no: str
    product_name: str
    customer: str
    status: str
    approved_sections: int
    required_sections: int
    percentage: float
    updated_at: str


class InternalQuoteDashboardSpeedOut(BaseModel):
    customer: str
    completed_count: int
    average_hours: float
    average_days: float
    fastest_hours: float
    slowest_hours: float


class InternalQuoteDashboardOut(BaseModel):
    factory_id: str
    period: Literal["week", "month", "year"]
    period_label: str
    period_start: str
    period_end: str
    totals: InternalQuoteDashboardTotalsOut
    status_distribution: list[InternalQuoteDashboardStatusOut]
    customer_quote_counts: list[InternalQuoteDashboardCustomerCountOut]
    progress_items: list[InternalQuoteDashboardProgressOut]
    customer_speed: list[InternalQuoteDashboardSpeedOut]


class InternalQuoteMaterialBaselineRow(BaseModel):
    material: str = Field(min_length=1, max_length=64)
    grade: str = Field(min_length=1, max_length=128)
    price_hkd_lb: str = Field(min_length=1, max_length=32)

    @field_validator("material", "grade")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("price_hkd_lb")
    @classmethod
    def validate_price(cls, value: str) -> str:
        return _positive_decimal_text(value, "材料价")


class InternalQuoteMachineBaselineRow(BaseModel):
    machine_range: str = Field(min_length=1, max_length=64)
    machine: str = Field(min_length=1, max_length=128)
    shift_price_hkd: str = Field(min_length=1, max_length=32)

    @field_validator("machine_range", "machine")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("shift_price_hkd")
    @classmethod
    def validate_price(cls, value: str) -> str:
        return _positive_decimal_text(value, "机型价")


class InternalQuoteFreightBaselineRow(BaseModel):
    route_key: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    route_name: str = Field(min_length=1, max_length=128)
    capacity_key: str = Field(min_length=1, max_length=128)
    freight_hkd: str
    lifting_hkd: str = "0"

    @field_validator("route_key", "route_name", "capacity_key")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("freight_hkd", "lifting_hkd")
    @classmethod
    def validate_cost(cls, value: str, info) -> str:
        label = "吊柜费" if info.field_name == "lifting_hkd" else "运费"
        return _nonnegative_decimal_text(value, label)


class InternalQuotePricingBaselineUpdateRequest(BaseModel):
    revision: int = Field(ge=0)
    workshop_name: str = Field(default="华兴", min_length=1, max_length=128)
    material_prices: list[InternalQuoteMaterialBaselineRow] = Field(min_length=1, max_length=200)
    machine_prices: list[InternalQuoteMachineBaselineRow] = Field(min_length=1, max_length=100)
    freight_routes: list[InternalQuoteFreightBaselineRow] | None = Field(default=None, min_length=1, max_length=50)

    @field_validator("workshop_name")
    @classmethod
    def strip_workshop_name(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_unique_rows(self):
        material_keys = [
            (row.material.casefold(), row.grade.casefold()) for row in self.material_prices
        ]
        if len(material_keys) != len(set(material_keys)):
            raise ValueError("初始材料价存在重复的材质和料型")
        machine_ranges = [row.machine_range.casefold() for row in self.machine_prices]
        if len(machine_ranges) != len(set(machine_ranges)):
            raise ValueError("初始机型价存在重复的机型范围")
        if self.freight_routes is not None:
            reserved_keys = {"enabled", "cap_10t", "cap_5t", "cap_40", "cap_20"}
            route_keys = [row.route_key.lower() for row in self.freight_routes]
            route_names = [row.route_name.casefold() for row in self.freight_routes]
            if any(key in reserved_keys for key in route_keys):
                raise ValueError("运输方案标识不能使用系统保留字段")
            if len(route_keys) != len(set(route_keys)):
                raise ValueError("运输方案标识不能重复")
            if len(route_names) != len(set(route_names)):
                raise ValueError("运输方案名称不能重复")
        return self


class InternalQuotePricingBaselineOut(BaseModel):
    factory_id: str
    workshop_code: str
    workshop_name: str
    revision: int
    source_type: Literal["default", "custom"]
    material_prices: list[InternalQuoteMaterialBaselineRow]
    machine_prices: list[InternalQuoteMachineBaselineRow]
    freight_routes: list[InternalQuoteFreightBaselineRow]
    updated_by: str
    updated_by_name: str
    updated_at: str


class InternalQuoteCloneRequest(BaseModel):
    quote_no: str = Field(min_length=1, max_length=128)
    version_label: str = Field(min_length=1, max_length=64)
    business_owner_id: str = Field(min_length=1, max_length=64)
    business_owner_name: str = Field(min_length=1, max_length=128)
    target_customer_price: str | None = Field(default=None, min_length=1, max_length=128)
    target_date: str = Field(default="", max_length=32)
    remark: str | None = Field(default=None, max_length=4000)
    workflow_mode: InternalQuoteWorkflowMode | None = None
    participating_sections: list[InternalQuoteSectionCode] | None = None

    @field_validator(
        "quote_no",
        "version_label",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("target_customer_price")
    @classmethod
    def validate_target_customer_price(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("客人目标价不能为空，客人未提供时请填写‘无’")
        return normalized

    @field_validator("participating_sections")
    @classmethod
    def validate_participating_sections(
        cls, values: list[InternalQuoteSectionCode] | None
    ) -> list[InternalQuoteSectionCode] | None:
        return _validate_participating_sections(values) if values is not None else None


class InternalQuoteHeaderUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    product_name: str | None = Field(default=None, min_length=1, max_length=255)
    customer: str | None = Field(default=None, min_length=1, max_length=128)
    qty: int | None = Field(default=None, gt=0)
    business_owner_id: str | None = Field(default=None, min_length=1, max_length=64)
    business_owner_name: str | None = Field(default=None, min_length=1, max_length=128)
    target_customer_price: str | None = Field(default=None, min_length=1, max_length=128)
    target_date: str | None = Field(default=None, max_length=32)
    remark: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "product_name",
        "customer",
        "business_owner_id",
        "business_owner_name",
        "target_date",
        "remark",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("target_customer_price")
    @classmethod
    def validate_target_customer_price(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("客人目标价不能为空，客人未提供时请填写‘无’")
        return normalized

    @model_validator(mode="after")
    def require_change(self):
        fields = self.model_dump(exclude={"revision"}, exclude_none=True)
        if not fields:
            raise ValueError("至少提交一个需要修改的字段")
        if (self.business_owner_id is None) != (self.business_owner_name is None):
            raise ValueError("业务负责人编号和姓名必须同时提交")
        return self


class InternalQuoteParticipationUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    add_sections: list[InternalQuoteSectionCode] = Field(min_length=1)

    @field_validator("add_sections")
    @classmethod
    def validate_add_sections(
        cls, values: list[InternalQuoteSectionCode]
    ) -> list[InternalQuoteSectionCode]:
        invalid = [code for code in values if code not in OPTIONAL_SECTION_CODES]
        if invalid:
            raise ValueError("只能追加电子部、啤机部、喷油部、搪胶部或车缝部")
        return _normalize_section_codes(values)


class InternalQuoteParticipationRemoveRequest(BaseModel):
    revision: int = Field(ge=1)
    remove_sections: list[InternalQuoteSectionCode] = Field(min_length=1)

    @field_validator("remove_sections")
    @classmethod
    def validate_remove_sections(
        cls, values: list[InternalQuoteSectionCode]
    ) -> list[InternalQuoteSectionCode]:
        invalid = [code for code in values if code not in OPTIONAL_SECTION_CODES]
        if invalid:
            raise ValueError("业务部、工程部和装配部为固定参与部门，不能移除")
        return _normalize_section_codes(values)


class InternalQuoteSectionSaveRequest(BaseModel):
    revision: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteSectionPreviewRequest(BaseModel):
    revision: int = Field(ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class InternalQuoteSectionPreviewOut(BaseModel):
    quote_id: str
    section_code: InternalQuoteSectionCode
    section_revision: int
    calculation_status: str
    calculation: dict[str, Any]
    warnings: list[dict[str, Any]]
    saved_factory_price_hkd: str
    preview_factory_price_hkd: str
    delta_hkd: str
    components_hkd: dict[str, str]
    formula_version: str
    reference_snapshot_id: str
    generated_at: str


class InternalQuoteRevisionRequest(BaseModel):
    revision: int = Field(ge=1)


class InternalQuoteReviewRequest(InternalQuoteRevisionRequest):
    decision: ReviewDecision
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == "reject" and not self.reason:
            raise ValueError("退回时必须填写原因")
        return self


class InternalQuoteFinalReviewRequest(InternalQuoteRevisionRequest):
    decision: ReviewDecision
    reason: str = Field(default="", max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def require_rejection_reason(self):
        if self.decision == "reject" and not self.reason:
            raise ValueError("最终放行退回时必须填写原因")
        return self


class InternalQuoteReasonRequest(InternalQuoteRevisionRequest):
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteArchiveRequest(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteReferenceSyncRequest(BaseModel):
    revision: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason")
    @classmethod
    def strip_reason(cls, value: str) -> str:
        return value.strip()


class InternalQuoteReferenceFxUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    rmb_hkd: str = Field(min_length=1, max_length=32)
    hkd_usd: str = Field(min_length=1, max_length=32)

    @field_validator("rmb_hkd", "hkd_usd")
    @classmethod
    def validate_fx(cls, value: str, info) -> str:
        label = "RMB→HKD 汇率" if info.field_name == "rmb_hkd" else "HKD→USD 汇率"
        normalized = _positive_decimal_text(value, label)
        parsed = Decimal(normalized).normalize()
        if parsed > Decimal("1000"):
            raise ValueError(f"{label}不能大于 1000")
        if parsed.as_tuple().exponent < -2:
            raise ValueError(f"{label}最多保留 2 位小数")
        return format(parsed, "f")


class InternalQuoteReferenceMaterialsUpdateRequest(BaseModel):
    revision: int = Field(ge=1)
    material_prices: list[InternalQuoteMaterialBaselineRow] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_unique_rows(self):
        material_keys = [
            (row.material.casefold(), row.grade.casefold()) for row in self.material_prices
        ]
        if len(material_keys) != len(set(material_keys)):
            raise ValueError("本报价专用料价存在重复的材质和料型")
        return self


class InternalQuoteSectionOut(BaseModel):
    id: str
    department: str
    department_name: str
    status: str
    payload: dict[str, Any]
    calculation: dict[str, Any]
    calculation_status: str
    calculation_hash: str
    calculation_formula_version: str
    calculation_reference_snapshot_id: str
    calculated_at: str
    dependency_hash: str
    dependency_status: str
    revision: int
    is_required: bool
    filled_by: str
    filled_at: str
    submitted_by: str
    submitted_by_id: str
    submitted_at: str
    reviewed_by: str
    reviewed_at: str
    review_comment: str
    updated_at: str


class InternalQuoteOut(BaseModel):
    id: str
    factory_id: str
    workshop_code: str
    workshop_name: str
    quote_no: str
    product_name: str
    quote_type: str
    batch_id: str
    batch_quote_no: str
    batch_position: int
    batch_size: int
    baseline_quote_id: str
    region_code: str
    customer: str
    qty: int
    version_label: str
    status: str
    initiator_department: str
    business_owner_id: str
    business_owner_name: str
    target_customer_price: str
    target_date: str
    remark: str
    module_version: str
    reference_snapshot_id: str
    formula_version: str
    header_revision: int
    cloned_from_quote_id: str
    archived_by: str
    archived_at: str
    archive_reason: str
    final_release_status: str
    final_submission_revision: int
    final_submission_manifest: dict[str, Any]
    final_submitted_by: str
    final_submitted_by_name: str
    final_submitted_at: str
    final_reviewed_by: str
    final_reviewed_by_name: str
    final_reviewed_at: str
    final_review_comment: str
    final_release_revision: int
    final_release_invalidated_at: str
    final_release_invalidation_reason: str
    created_by: str
    created_by_name: str
    created_at: str
    updated_at: str
    sections: list[InternalQuoteSectionOut] = Field(default_factory=list)


class InternalQuoteProductImageOut(BaseModel):
    id: str
    file_name: str
    content_type: str
    size_bytes: int
    uploaded_by_name: str
    uploaded_at: str


class InternalQuoteBatchProductOut(BaseModel):
    quote_id: str
    quote_no: str
    product_name: str
    qty: int
    position: int
    batch_size: int
    quote_type: str
    region_code: str
    status: str
    header_revision: int
    is_baseline: bool
    differs_from_baseline: bool
    different_header_fields: list[str] = Field(default_factory=list)
    different_sections: list[str] = Field(default_factory=list)
    different_section_details: dict[str, list[str]] = Field(default_factory=dict)
    main_image: InternalQuoteProductImageOut | None = None


class InternalQuotePageOut(BaseModel):
    items: list[InternalQuoteOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    customers: list[str] = Field(default_factory=list)


class InternalQuoteRevisionOut(BaseModel):
    id: str
    revision: int
    status: str
    payload: dict[str, Any]
    calculation: dict[str, Any]
    formula_version: str
    input_hash: str
    reference_snapshot_id: str
    dependency_hash: str
    warnings: list[dict[str, Any]]
    reason: str
    created_by: str
    created_by_name: str
    created_at: str


class InternalQuoteAuditOut(BaseModel):
    id: str
    department: str
    actor_id: str
    actor_name: str
    action: str
    detail: str
    old_revision: int | None
    new_revision: int | None
    reason: str
    created_at: str


class InternalQuoteTimelineOut(BaseModel):
    business_events: list[InternalQuoteAuditOut]
    view_records: list[InternalQuoteAuditOut]


class InternalQuoteReferenceSetOut(BaseModel):
    id: str
    quote_id: str
    factory_id: str
    version_label: str
    formula_version: str
    source_type: str
    source_revision: int
    snapshot: dict[str, Any]
    sha256: str
    is_current: bool
    created_by: str
    created_by_name: str
    created_at: str
    superseded_at: str


class InternalQuoteImportConfirmRequest(BaseModel):
    revision: int = Field(ge=1)
    # Kept for backward compatibility with older clients. Internal quote
    # imports now always replace the data region owned by their template.
    mode: Literal["append", "replace"] = "replace"


class InternalQuoteImportPreviewOut(BaseModel):
    batch_id: str
    quote_id: str
    import_type: InternalQuoteImportType
    target_department: str
    source_file_name: str
    source_sha256: str
    source_size_bytes: int
    preview_schema_version: str
    target_revision: int
    sheet_name: str
    header_row: int
    row_count: int
    payload_fragment: dict[str, Any]
    diff_summary: dict[str, Any]
    warnings: list[str]
    status: str
    created_by_name: str
    created_at: str
    confirm_mode: str = ""
    confirmed_revision: int = 0
    confirmed_by_name: str = ""
    confirmed_at: str = ""


class InternalQuoteImportConfirmOut(BaseModel):
    batch: InternalQuoteImportPreviewOut
    section: InternalQuoteSectionOut


class InternalQuoteAttachmentOut(BaseModel):
    id: str
    quote_id: str
    department: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    uploaded_by: str
    uploaded_by_name: str
    uploaded_at: str
    is_import_source: bool = False
    import_batch_id: str = ""
    import_type: str = ""


class InternalQuoteAttachmentPreviewSheetOut(BaseModel):
    name: str
    rows: list[list[Any]]
    total_rows: int
    total_columns: int
    truncated: bool = False


class InternalQuoteAttachmentContentPreviewOut(BaseModel):
    file_name: str
    kind: str
    sheets: list[InternalQuoteAttachmentPreviewSheetOut] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class InternalQuoteExportFileOut(BaseModel):
    id: str
    quote_id: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    section_revisions: dict[str, int]
    status: str
    template_version: str
    formula_version: str
    reference_snapshot_id: str
    header_revision: int
    release_stage: str
    export_manifest: dict[str, Any]
    exported_by: str
    exported_by_name: str
    exported_at: str
    superseded_at: str


class InternalQuoteFinalReviewOut(BaseModel):
    id: str
    quote_id: str
    submission_revision: int
    decision: str
    header_revision: int
    section_revisions: dict[str, int]
    release_manifest: dict[str, Any]
    release_manifest_sha256: str
    submitted_by: str
    submitted_by_name: str
    submitted_at: str
    actor_id: str
    actor_name: str
    reason: str
    created_at: str


class InternalQuoteFinalReleaseOut(BaseModel):
    quote: InternalQuoteOut
    review: InternalQuoteFinalReviewOut | None = None
    export: InternalQuoteExportFileOut | None = None


class InternalQuoteVersionCandidateOut(BaseModel):
    id: str
    quote_no: str
    version_label: str
    product_name: str
    customer: str
    status: str
    final_release_status: str
    final_release_revision: int
    updated_at: str


class InternalQuoteFieldChangeOut(BaseModel):
    path: str
    before: Any = None
    after: Any = None


class InternalQuoteSectionComparisonOut(BaseModel):
    section_code: str
    section_name: str
    before_status: str
    after_status: str
    before_revision: int
    after_revision: int
    before_total_hkd: str
    after_total_hkd: str
    delta_hkd: str
    payload_changes: list[InternalQuoteFieldChangeOut]


class InternalQuoteVersionComparisonOut(BaseModel):
    base: InternalQuoteVersionCandidateOut
    target: InternalQuoteVersionCandidateOut
    header_changes: list[InternalQuoteFieldChangeOut]
    sections: list[InternalQuoteSectionComparisonOut]
    total_before_hkd: str
    total_after_hkd: str
    total_delta_hkd: str


class InternalQuoteArtifactConsumeRequest(BaseModel):
    consumer_reference: str = Field(default="", max_length=128)

    @field_validator("consumer_reference")
    @classmethod
    def strip_reference(cls, value: str) -> str:
        return value.strip()


class InternalQuoteArtifactHandoffOut(BaseModel):
    id: str
    quote_id: str
    export_id: str
    factory_id: str
    customer: str
    quote_no: str
    version_label: str
    release_revision: int
    status: str
    artifact_manifest: dict[str, Any]
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_by: str
    created_by_name: str
    created_at: str
    consumed_by: str
    consumed_by_name: str
    consumed_at: str
    consumer_reference: str
    revoked_at: str
    revoke_reason: str
