from pydantic import BaseModel, Field


class RriInvoiceDocument(BaseModel):
    input_slot: str = ""
    invoice_no: str = ""
    po_no: str = ""
    date: str = ""
    line_count: int = Field(ge=0)
    declared_total_hkd: float | None = None


class RriInvoiceHeaderCheck(BaseModel):
    field: str
    customer_value: str
    supplier_value: str
    status: str
    note: str = ""


class RriInvoiceLineCheck(BaseModel):
    customer_sku: str
    supplier_sku: str = ""
    description: str
    quantity: int
    customer_unit_price_hkd: float
    expected_supplier_unit_price_hkd: float
    supplier_unit_price_hkd: float | None = None
    customer_amount_hkd: float
    expected_supplier_amount_hkd: float
    supplier_amount_hkd: float | None = None
    price_status: str = "not_available"
    amount_status: str = "not_available"
    status: str
    note: str = ""


class RriInvoiceReconciliationSummary(BaseModel):
    customer_line_count: int = Field(ge=0)
    supplier_line_count: int = Field(ge=0)
    matched_line_count: int = Field(ge=0)
    mismatch_line_count: int = Field(ge=0)
    missing_supplier_line_count: int = Field(ge=0)
    unexpected_supplier_line_count: int = Field(ge=0)
    expected_supplier_total_hkd: float
    supplier_declared_total_hkd: float | None = None
    supplier_total_difference_hkd: float | None = None
    status: str


class RriInvoiceReconciliationResponse(BaseModel):
    customer_profile_code: str
    customer_name: str
    factor: float
    rounding_rule: str
    customer_invoice: RriInvoiceDocument
    supplier_invoice: RriInvoiceDocument
    header_checks: list[RriInvoiceHeaderCheck]
    line_checks: list[RriInvoiceLineCheck]
    summary: RriInvoiceReconciliationSummary
