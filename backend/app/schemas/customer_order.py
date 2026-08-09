from pydantic import BaseModel


class CustomerOrderIssueOut(BaseModel):
    severity: str
    code: str
    field: str
    message: str
    can_skip: bool
    skip_key: str
    skip_label: str
    can_edit: bool = False
    edit_field: str = ""
    edit_label: str = ""
    edit_input_type: str = "text"


class CustomerOrderLineOut(BaseModel):
    id: str
    status: str
    status_label: str
    row_role: str = "detail"
    parent_product_no: str = ""
    received_date: str
    po_no: str
    contract_no: str
    customer_country: str
    customer_name: str
    country: str
    product_no: str
    product_name_zh: str
    product_name_en: str
    quantity: str
    units_per_carton: str
    carton_count: str
    standard: str
    unit_price_hkd: str
    amount_hkd: str
    packaging: str
    line_q: str
    customer_q: str
    requested_ship_date: str
    input_template: str
    target_template: str
    item_sheet_name: str
    source_po_file_name: str
    lineage: dict[str, str]
    issues: list[CustomerOrderIssueOut]


class CustomerOrderImportSummaryOut(BaseModel):
    total: int
    valid: int
    warning: int
    blocked: int


class CustomerOrderImportPreviewOut(BaseModel):
    preview_schema_version: str
    customer_code: str
    factory_id: str
    po_file_name: str
    po_file_names: list[str]
    po_file_count: int
    schedule_file_name: str
    source_po_sha256: str
    source_po_sha256s: list[str]
    source_schedule_sha256: str
    input_template: str
    target_template: str
    output_file_name: str
    duplicate_confirmation_enabled: bool = False
    duplicate_confirmation_authorized: bool = False
    confirmation_count: int = 0
    preview_fingerprint: str
    summary: CustomerOrderImportSummaryOut
    rows: list[CustomerOrderLineOut]
    warnings: list[str]


class CustomerOrderExportAuditOut(BaseModel):
    id: str
    actor_user_id: str | None
    actor_username: str
    actor_display_name: str
    factory_id: str
    customer_code: str
    received_date: str
    preview_schema_version: str
    preview_fingerprint: str
    po_file_names: list[str]
    source_po_sha256s: list[str]
    schedule_file_name: str
    source_schedule_sha256: str
    output_file_name: str
    output_sha256: str
    output_template: str
    confirmed_issue_keys: list[str]
    confirmed_issue_count: int
    manual_overrides: list[dict[str, str]]
    manual_override_count: int
    confirmation_reason: str
    created_at: str
