from pydantic import BaseModel


class CustomerOrderIssueOut(BaseModel):
    severity: str
    code: str
    field: str
    message: str
    can_skip: bool
    skip_key: str
    skip_label: str


class CustomerOrderLineOut(BaseModel):
    id: str
    status: str
    status_label: str
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
    summary: CustomerOrderImportSummaryOut
    rows: list[CustomerOrderLineOut]
    warnings: list[str]
