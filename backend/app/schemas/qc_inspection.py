from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


QcOrderStatus = Literal["SCHEDULED", "IN_PROGRESS", "COMPLETED", "CANCELLED"]
QcInspectionResult = Literal[
    "PENDING",
    "PASS",
    "FAIL",
    "REJECTED",
    "CONDITIONAL_PASS",
    "CANCELLED",
]
QcProblemStatus = Literal[
    "DRAFT", "OPEN", "IN_PROGRESS", "RESOLVED", "CLOSED", "CANCELLED"
]
QcReportType = Literal[
    "CUSTOMER_SUMMARY",
    "WEEKLY_STATISTICS",
    "HUAXING_CUSTOMER_WEEKLY_DETAIL",
    "HUAXING_WEEKLY_AGGREGATE",
    "GROUP_SUMMARY",
    "WEEKLY_INSPECTION_SCHEDULE",
    "DAILY_INSPECTION_LEDGER",
    "WEEKLY_PROBLEM_DETAIL",
    "WEEKLY_RETURN_SUMMARY",
    "INSPECTION_PASS_RATE",
    "ANNUAL_INSPECTION_STATISTICS",
    "PRODUCT_QUALITY_LEDGER",
    "INSPECTION_DOCUMENT_INDEX",
    "ORDER_INSPECTION_REPORT",
]
QcReportStatus = Literal["GENERATED", "FAILED"]
QcScheduleDecisionAction = Literal["UPDATE", "KEEP", "CREATE", "SKIP"]
QcInspectionEventType = Literal[
    "CUSTOMER", "THIRD_PARTY", "LINE", "SELF", "REINSPECTION", "SAMPLE"
]
QcDocumentStatus = Literal["DRAFT", "FINAL", "REVISED"]
QcDefectSeverity = Literal["CRITICAL", "MAJOR", "MINOR", "OBSERVATION"]
QcTestResult = Literal["PENDING", "PASS", "FAIL", "NA"]
QcDispositionType = Literal[
    "RETURN", "REWORK", "AOD", "CONCESSION_ACCEPTED", "ON_HOLD", "NO_ACTION"
]
QcReportPeriodMode = Literal["WEEK", "MONTH", "YEAR", "EVENT"]


def _strip(value: str) -> str:
    return value.strip()


def _validate_optional_date(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期必须使用 YYYY-MM-DD 格式") from exc
    return value


class QcMutationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")


class QcCustomerConfigCreate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    customer_code: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=255)
    is_caixing: bool = False
    default_inspection_agency: str = Field(default="", max_length=255)
    default_account_manager: str = Field(default="", max_length=128)

    @field_validator(
        "factory_id",
        "customer_code",
        "customer_name",
        "default_inspection_agency",
        "default_account_manager",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class QcCustomerConfigUpdate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    is_caixing: bool | None = None
    default_inspection_agency: str | None = Field(default=None, max_length=255)
    default_account_manager: str | None = Field(default=None, max_length=128)
    status: Literal["ACTIVE", "INACTIVE"] | None = None

    @field_validator(
        "factory_id",
        "customer_name",
        "default_inspection_agency",
        "default_account_manager",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @model_validator(mode="after")
    def validate_change(self):
        if not any(
            getattr(self, field) is not None
            for field in (
                "customer_name",
                "is_caixing",
                "default_inspection_agency",
                "default_account_manager",
                "status",
            )
        ):
            raise ValueError("至少需要提交一项客户配置变更")
        return self


class QcCustomerConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    customer_code: str
    customer_name: str
    is_caixing: bool
    default_inspection_agency: str
    default_account_manager: str
    status: Literal["ACTIVE", "INACTIVE"]
    revision: int
    created_by: str
    updated_by: str
    created_at: str
    updated_at: str


class QcOrderCreate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    week_key: str = Field(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
    customer_name: str = Field(min_length=1, max_length=255)
    sales_contract_no: str = Field(min_length=1, max_length=128)
    customer_item_no: str = Field(min_length=1, max_length=128)
    customer_po_no: str = Field(min_length=1, max_length=128)
    product_name: str = Field(default="", max_length=255)
    quantity: Decimal = Field(gt=0, max_digits=18, decimal_places=4)
    packing: str = Field(default="", max_length=255)
    carton_count: str = Field(default="", max_length=64)
    report_status: str = Field(default="", max_length=128)
    production_department: str = Field(default="", max_length=128)
    export_country_code: str = Field(default="", max_length=16)
    shipment_date: str = ""
    planned_inspection_date: str = ""
    inspection_agency: str = Field(default="", max_length=255)
    account_manager: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=4000)

    @field_validator(
        "factory_id",
        "customer_name",
        "sales_contract_no",
        "customer_item_no",
        "customer_po_no",
        "product_name",
        "packing",
        "carton_count",
        "report_status",
        "production_department",
        "inspection_agency",
        "account_manager",
        "note",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("export_country_code")
    @classmethod
    def normalize_country_code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("shipment_date", "planned_inspection_date")
    @classmethod
    def validate_dates(cls, value: str) -> str:
        return _validate_optional_date(value)


class QcOrderUpdate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=500)
    week_key: str | None = Field(
        default=None,
        pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$",
    )
    customer_name: str | None = Field(default=None, min_length=1, max_length=255)
    sales_contract_no: str | None = Field(default=None, min_length=1, max_length=128)
    customer_item_no: str | None = Field(default=None, min_length=1, max_length=128)
    customer_po_no: str | None = Field(default=None, min_length=1, max_length=128)
    product_name: str | None = Field(default=None, max_length=255)
    quantity: Decimal | None = Field(default=None, gt=0, max_digits=18, decimal_places=4)
    packing: str | None = Field(default=None, max_length=255)
    carton_count: str | None = Field(default=None, max_length=64)
    report_status: str | None = Field(default=None, max_length=128)
    production_department: str | None = Field(default=None, max_length=128)
    export_country_code: str | None = Field(default=None, max_length=16)
    shipment_date: str | None = None
    planned_inspection_date: str | None = None
    actual_inspection_date: str | None = None
    inspection_result: QcInspectionResult | None = None
    inspection_agency: str | None = Field(default=None, max_length=255)
    account_manager: str | None = Field(default=None, max_length=128)
    manual_has_problem: bool | None = None
    note: str | None = Field(default=None, max_length=4000)

    @field_validator(
        "factory_id",
        "reason",
        "customer_name",
        "sales_contract_no",
        "customer_item_no",
        "customer_po_no",
        "product_name",
        "packing",
        "carton_count",
        "report_status",
        "production_department",
        "inspection_agency",
        "account_manager",
        "note",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @field_validator("export_country_code")
    @classmethod
    def normalize_optional_country_code(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @field_validator("shipment_date", "planned_inspection_date", "actual_inspection_date")
    @classmethod
    def validate_optional_dates(cls, value: str | None) -> str | None:
        return _validate_optional_date(value) if value is not None else None

    @model_validator(mode="after")
    def validate_change(self):
        excluded = {"factory_id", "expected_revision", "request_id", "reason"}
        if not any(value is not None for key, value in self.model_dump().items() if key not in excluded):
            raise ValueError("至少需要提交一项验货主单变更")
        return self


class QcOrderOut(BaseModel):
    id: str
    factory_id: str
    inspection_no: str
    source_type: Literal["SCHEDULE_IMPORT", "MANUAL"]
    source_import_row_id: str
    week_key: str
    customer_name: str
    sales_contract_no: str
    customer_item_no: str
    customer_po_no: str
    product_name: str
    quantity: Decimal
    packing: str
    carton_count: str
    report_status: str
    production_department: str
    export_country_code: str
    shipment_date: str
    planned_inspection_date: str
    actual_inspection_date: str
    inspection_result: QcInspectionResult
    inspection_agency: str
    account_manager: str
    status: QcOrderStatus
    manual_has_problem: bool
    note: str
    problem_count: int = 0
    has_problem: bool = False
    problem_summary: str = ""
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class QcOrderListOut(BaseModel):
    factory_id: str
    week: str
    total: int
    items: list[QcOrderOut]


class QcInspectionLineInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_po_no: str = Field(min_length=1, max_length=128)
    release_no: str = Field(default="", max_length=128)
    customer_item_no: str = Field(min_length=1, max_length=128)
    internal_item_no: str = Field(default="", max_length=128)
    batch_no: str = Field(default="", max_length=128)
    date_code: str = Field(default="", max_length=128)
    product_name: str = Field(default="", max_length=255)
    order_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    inspected_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    packing: str = Field(default="", max_length=255)
    carton_count: str = Field(default="", max_length=64)
    upc_ean: str = Field(default="", max_length=64)

    @field_validator("*")
    @classmethod
    def strip_string_values(cls, value):
        return value.strip() if isinstance(value, str) else value


class QcInspectionLineOut(QcInspectionLineInput):
    id: str
    line_no: int


class QcInspectionDefectInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_line_id: str = Field(default="", max_length=96)
    category: str = Field(default="", max_length=128)
    severity: QcDefectSeverity = "OBSERVATION"
    quantity: int = Field(default=1, ge=0)
    defect_location: str = Field(default="", max_length=255)
    description: str = Field(min_length=1, max_length=8000)
    production_department: str = Field(default="", max_length=128)
    photo_reference: str = Field(default="", max_length=512)

    @field_validator("event_line_id", "category", "defect_location", "description", "production_department", "photo_reference")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class QcInspectionDefectOut(QcInspectionDefectInput):
    id: str


class QcInspectionTestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    test_item: str = Field(min_length=1, max_length=255)
    method_standard: str = Field(default="", max_length=255)
    specification: str = Field(default="", max_length=255)
    measured_value: str = Field(default="", max_length=255)
    unit: str = Field(default="", max_length=32)
    sample_size: int = Field(default=0, ge=0)
    result: QcTestResult = "PENDING"
    operator_name: str = Field(default="", max_length=128)
    reviewer_name: str = Field(default="", max_length=128)

    @field_validator("test_item", "method_standard", "specification", "measured_value", "unit", "operator_name", "reviewer_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class QcInspectionTestOut(QcInspectionTestInput):
    id: str


class QcInspectionDispositionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    disposition_type: QcDispositionType
    return_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    rework_quantity: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=4)
    reason: str = Field(default="", max_length=4000)
    approved_by: str = Field(default="", max_length=128)
    approved_date: str = ""
    verification_result: str = Field(default="", max_length=4000)

    @field_validator("reason", "approved_by", "verification_result")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("approved_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_optional_date(value)

    @model_validator(mode="after")
    def validate_approval(self):
        if self.disposition_type in {"AOD", "CONCESSION_ACCEPTED"} and (
            not self.approved_by or not self.approved_date
        ):
            raise ValueError("AOD 或让步接收必须填写批准人和批准日期")
        return self


class QcInspectionDispositionOut(QcInspectionDispositionInput):
    id: str


class QcInspectionEventCreate(QcMutationRequest):
    expected_pending_order_revision: int | None = Field(default=None, ge=1)
    factory_id: str = Field(min_length=1, max_length=64)
    inspection_order_id: str = Field(min_length=1, max_length=96)
    event_type: QcInspectionEventType = "CUSTOMER"
    actual_inspection_date: str
    inspector_name: str = Field(default="", max_length=128)
    inspection_agency: str = Field(default="", max_length=255)
    inspection_location: str = Field(default="", max_length=255)
    sampling_standard: str = Field(default="ANSI/ASQ Z1.4", max_length=128)
    inspection_level: str = Field(default="II", max_length=64)
    aql_critical: str = Field(default="0", max_length=32)
    aql_major: str = Field(default="2.5", max_length=32)
    aql_minor: str = Field(default="4.0", max_length=32)
    lot_size: int = Field(default=0, ge=0)
    sample_size: int = Field(default=0, ge=0)
    critical_defect_count: int = Field(default=0, ge=0)
    major_defect_count: int = Field(default=0, ge=0)
    minor_defect_count: int = Field(default=0, ge=0)
    inspection_result: QcInspectionResult = "PENDING"
    document_status: QcDocumentStatus = "DRAFT"
    manual_has_problem: bool = False
    report_number: str = Field(default="", max_length=128)
    note: str = Field(default="", max_length=8000)
    lines: list[QcInspectionLineInput] = Field(min_length=1, max_length=200)
    defects: list[QcInspectionDefectInput] = Field(default_factory=list, max_length=500)
    tests: list[QcInspectionTestInput] = Field(default_factory=list, max_length=500)
    dispositions: list[QcInspectionDispositionInput] = Field(default_factory=list, max_length=100)

    @field_validator("actual_inspection_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        value = _validate_optional_date(value)
        if not value:
            raise ValueError("验货日期不能为空")
        return value

    @field_validator("factory_id", "inspection_order_id", "inspector_name", "inspection_agency", "inspection_location", "sampling_standard", "inspection_level", "aql_critical", "aql_major", "aql_minor", "report_number", "note")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_business_rules(self):
        defect_counts = {
            "CRITICAL": sum(item.quantity for item in self.defects if item.severity == "CRITICAL"),
            "MAJOR": sum(item.quantity for item in self.defects if item.severity == "MAJOR"),
            "MINOR": sum(item.quantity for item in self.defects if item.severity == "MINOR"),
        }
        declared = {
            "CRITICAL": self.critical_defect_count,
            "MAJOR": self.major_defect_count,
            "MINOR": self.minor_defect_count,
        }
        if defect_counts != declared:
            raise ValueError("缺陷汇总数量必须与缺陷明细中的致命/主要/次要数量一致")
        if self.inspection_result == "PASS" and any(
            item.disposition_type == "RETURN" for item in self.dispositions
        ):
            raise ValueError("验货通过时不能同时登记退货处置")
        return self


class QcInspectionEventUpdate(QcInspectionEventCreate):
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=500)


class QcInspectionEventOut(BaseModel):
    id: str
    factory_id: str
    inspection_order_id: str
    attempt_no: int
    event_type: QcInspectionEventType
    actual_inspection_date: str
    inspector_name: str
    inspection_agency: str
    inspection_location: str
    sampling_standard: str
    inspection_level: str
    aql_critical: str
    aql_major: str
    aql_minor: str
    lot_size: int
    sample_size: int
    critical_defect_count: int
    major_defect_count: int
    minor_defect_count: int
    inspection_result: QcInspectionResult
    document_status: QcDocumentStatus
    manual_has_problem: bool
    report_number: str
    note: str
    lines: list[QcInspectionLineOut] = Field(default_factory=list)
    defects: list[QcInspectionDefectOut] = Field(default_factory=list)
    tests: list[QcInspectionTestOut] = Field(default_factory=list)
    dispositions: list[QcInspectionDispositionOut] = Field(default_factory=list)
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class QcInspectionEventListOut(BaseModel):
    factory_id: str
    inspection_order_id: str
    total: int
    items: list[QcInspectionEventOut]


class QcProblemCreate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    inspection_order_id: str = Field(min_length=1, max_length=96)
    status: QcProblemStatus = "DRAFT"
    category: str = Field(default="", max_length=128)
    description: str = Field(default="", max_length=8000)
    return_reason: str = Field(default="", max_length=4000)
    corrective_action: str = Field(default="", max_length=8000)
    resolution: str = Field(default="", max_length=8000)
    primary_responsible_person: str = Field(default="", max_length=128)
    secondary_responsible_person: str = Field(default="", max_length=128)
    reported_date: str = ""

    @field_validator(
        "factory_id",
        "inspection_order_id",
        "category",
        "description",
        "return_reason",
        "corrective_action",
        "resolution",
        "primary_responsible_person",
        "secondary_responsible_person",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("reported_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_optional_date(value)

    @model_validator(mode="after")
    def validate_open_problem(self):
        if self.status not in {"DRAFT", "CANCELLED"} and not self.description:
            raise ValueError("非草稿问题必须填写问题描述")
        return self


class QcProblemUpdate(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    reason: str = Field(min_length=2, max_length=500)
    status: QcProblemStatus | None = None
    category: str | None = Field(default=None, max_length=128)
    description: str | None = Field(default=None, max_length=8000)
    return_reason: str | None = Field(default=None, max_length=4000)
    corrective_action: str | None = Field(default=None, max_length=8000)
    resolution: str | None = Field(default=None, max_length=8000)
    primary_responsible_person: str | None = Field(default=None, max_length=128)
    secondary_responsible_person: str | None = Field(default=None, max_length=128)
    reported_date: str | None = None

    @field_validator(
        "factory_id",
        "reason",
        "category",
        "description",
        "return_reason",
        "corrective_action",
        "resolution",
        "primary_responsible_person",
        "secondary_responsible_person",
    )
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        return _strip(value) if value is not None else None

    @field_validator("reported_date")
    @classmethod
    def validate_optional_date(cls, value: str | None) -> str | None:
        return _validate_optional_date(value) if value is not None else None

    @model_validator(mode="after")
    def validate_change(self):
        excluded = {"factory_id", "expected_revision", "request_id", "reason"}
        if not any(value is not None for key, value in self.model_dump().items() if key not in excluded):
            raise ValueError("至少需要提交一项问题变更")
        return self


class QcProblemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    problem_no: str
    inspection_order_id: str
    source_type: Literal["AUTO_RESULT", "MANUAL"]
    source_key: str
    status: QcProblemStatus
    category: str
    description: str
    return_reason: str
    corrective_action: str
    resolution: str
    primary_responsible_person: str
    secondary_responsible_person: str
    reported_date: str
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class QcProblemListOut(BaseModel):
    factory_id: str
    week: str
    total: int
    items: list[QcProblemOut]


class QcScheduleRowOut(BaseModel):
    id: str
    factory_id: str
    batch_id: str
    source_row_no: int
    source_sheet_name: str = ""
    customer_name: str
    sales_contract_no: str
    customer_item_no: str
    customer_po_no: str
    product_name: str
    quantity: Decimal | None
    packing: str
    carton_count: str
    report_status: str
    production_department: str
    export_country_code: str
    shipment_date: str
    planned_inspection_date: str
    inspection_agency: str
    account_manager: str
    match_status: Literal["NEW", "EXACT", "MULTIPLE_MATCHES", "INVALID"]
    candidate_order_ids: list[str]
    candidate_order_revisions: dict[str, int]
    candidate_orders: list[dict[str, object]]
    changes: list[dict[str, object]]
    validation_errors: list[str]
    decision_status: Literal["PENDING", "UPDATE", "KEEP", "CREATE", "SKIP", "UNCHANGED"]
    linked_order_id: str


class QcScheduleBatchOut(BaseModel):
    id: str
    factory_id: str
    week_key: str
    source_file_name: str
    source_file_sha256: str
    source_size_bytes: int
    parser_version: str
    status: Literal["PREVIEW", "PARTIALLY_CONFIRMED", "CONFIRMED", "REJECTED"]
    row_count: int
    blocking_count: int
    summary: dict[str, object]
    revision: int
    created_at: str
    updated_at: str
    rows: list[QcScheduleRowOut]


class QcScheduleDecisionIn(BaseModel):
    row_id: str = Field(min_length=1, max_length=96)
    action: QcScheduleDecisionAction
    target_order_id: str = Field(default="", max_length=96)
    reason: str = Field(default="", max_length=500)

    @field_validator("row_id", "target_order_id", "reason")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class QcScheduleConfirmRequest(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)
    decisions: list[QcScheduleDecisionIn] = Field(min_length=1, max_length=1000)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_unique_rows(self):
        row_ids = [item.row_id for item in self.decisions]
        if len(row_ids) != len(set(row_ids)):
            raise ValueError("同一确认请求不能重复提交同一导入行")
        return self


class QcReportGenerateRequest(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    week_key: str = Field(pattern=r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$")
    report_type: QcReportType
    is_formal_snapshot: bool = False
    period_mode: QcReportPeriodMode = "WEEK"
    period_key: str = Field(default="", max_length=16)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_period(self):
        period_key = self.period_key.strip() or self.week_key
        patterns = {
            "WEEK": r"^\d{4}-W(?:0[1-9]|[1-4]\d|5[0-3])$",
            "MONTH": r"^\d{4}-(?:0[1-9]|1[0-2])$",
            "YEAR": r"^\d{4}$",
            "EVENT": r"^[A-Za-z0-9._-]{1,16}$",
        }
        import re

        if not re.fullmatch(patterns[self.period_mode], period_key):
            raise ValueError("统计周期格式与周期类型不匹配")
        self.period_key = period_key
        return self


class QcOrderReportGenerateRequest(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    inspection_event_id: str = Field(min_length=1, max_length=96)


class QcReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    week_key: str
    period_mode: QcReportPeriodMode
    period_key: str
    metric_version: str
    inspection_order_id: str
    inspection_event_id: str
    report_type: QcReportType
    status: QcReportStatus
    is_formal_snapshot: bool
    snapshot_revision: int
    source_revision_sha256: str
    artifact_file_name: str
    artifact_media_type: str
    artifact_sha256: str
    artifact_size_bytes: int
    generation_summary: dict[str, object] = Field(default_factory=dict)
    error_message: str
    requested_by: str
    requested_by_name: str
    created_at: str


class QcReportListOut(BaseModel):
    factory_id: str
    week: str
    total: int
    items: list[QcReportOut]


class QcRenameSourceMeta(BaseModel):
    file_id: str = Field(min_length=1, max_length=96)
    source_file_name: str = Field(min_length=1, max_length=255)
    sequence: int | None = Field(default=None, ge=1)

    @field_validator("file_id", "source_file_name")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)


class QcRenameGroupMeta(BaseModel):
    group_id: str = Field(min_length=1, max_length=128)
    is_caixing: bool = False
    item_number: str = Field(min_length=1, max_length=128)
    customer_po_no: str = Field(min_length=1, max_length=128)
    actual_inspection_date: str
    export_country: str = Field(default="", max_length=16)
    report_number: str = Field(default="", max_length=128)
    quantity: str = Field(default="", max_length=64)
    files: list[QcRenameSourceMeta] = Field(min_length=1, max_length=25)

    @field_validator(
        "group_id",
        "item_number",
        "customer_po_no",
        "export_country",
        "report_number",
        "quantity",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return _strip(value)

    @field_validator("actual_inspection_date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        return _validate_optional_date(value)

    @model_validator(mode="after")
    def validate_kind_fields(self):
        if self.is_caixing and (not self.report_number or not self.quantity):
            raise ValueError("彩星报告组必须填写报告号和数量")
        if not self.is_caixing and not self.export_country:
            raise ValueError("非彩星报告组必须填写出口国")
        file_ids = [item.file_id for item in self.files]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("同一报告组不能重复引用上传文件")
        source_names = [item.source_file_name.casefold() for item in self.files]
        if len(source_names) != len(set(source_names)):
            raise ValueError("同一报告组的源文件名不能大小写不敏感重复")
        return self


class QcRenamePreviewMeta(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    groups: list[QcRenameGroupMeta] = Field(min_length=1, max_length=100)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return _strip(value)

    @model_validator(mode="after")
    def validate_unique_groups_and_files(self):
        group_ids = [item.group_id.casefold() for item in self.groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("同一批次的报告组 ID 不能重复")
        file_ids = [file.file_id for group in self.groups for file in group.files]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("同一个上传文件不能归入多个报告组")
        return self


class QcRenameExecuteRequest(QcMutationRequest):
    factory_id: str = Field(min_length=1, max_length=64)
    expected_revision: int = Field(ge=1)

    @field_validator("factory_id")
    @classmethod
    def strip_factory(cls, value: str) -> str:
        return _strip(value)


class QcRenameIssueOut(BaseModel):
    code: str
    message: str
    source_file_name: str | None = None


class QcRenameFileOut(BaseModel):
    source_file_name: str
    target_file_name: str
    source_sha256: str
    size_bytes: int


class QcRenameGroupOut(BaseModel):
    group_id: str
    success: bool
    base_name: str | None
    files: list[QcRenameFileOut]
    issues: list[QcRenameIssueOut]


class QcRenameBatchOut(BaseModel):
    id: str
    factory_id: str
    status: Literal["PREVIEWED", "EXECUTED"]
    rule_version: str
    fingerprint: str
    group_count: int
    source_file_count: int
    source_size_bytes: int
    successful_group_count: int
    failed_group_count: int
    revision: int
    archive_file_name: str
    archive_sha256: str
    archive_size_bytes: int
    created_at: str
    executed_at: str
    groups: list[QcRenameGroupOut]


class QcAuditEventOut(BaseModel):
    id: str
    factory_id: str
    event_type: str
    entity_type: str
    entity_id: str
    before: dict[str, object]
    after: dict[str, object]
    reason: str
    request_id: str
    actor_user_id: str
    actor_name: str
    created_at: str


class QcWorkspaceSummaryOut(BaseModel):
    total_orders: int
    pending_orders: int
    completed_orders: int
    problem_orders: int


class QcWorkspaceOut(BaseModel):
    factory_id: str
    week: str
    summary: QcWorkspaceSummaryOut
    orders: list[QcOrderOut]
    problems: list[QcProblemOut]
    imports: list[QcScheduleBatchOut]
    reports: list[QcReportOut]
