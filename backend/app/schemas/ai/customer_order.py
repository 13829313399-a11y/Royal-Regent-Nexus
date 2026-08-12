from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

CUSTOMER_ORDER_AI_SAFE_AUDIT_FIELDS = frozenset(
    {
        "audit_id",
        "customer_code",
        "received_date",
        "preview_schema_version",
        "output_file_name",
        "output_template",
        "confirmed_issue_count",
        "manual_override_count",
        "created_at",
    }
)


class CustomerOrderCapabilitiesInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)


class CustomerOrderExportAuditListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    customer_code: str = Field(default="", max_length=64)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("customer_code")
    @classmethod
    def strip_customer_code(cls, value: str) -> str:
        return value.strip()


class AICustomerOrderCustomerCapability(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_code: str = Field(min_length=1, max_length=64)
    customer_name: str = Field(min_length=1, max_length=128)
    batch_preview_available: Literal[True] = True
    controlled_export_available: Literal[True] = True


class AICustomerOrderCapabilitiesData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["customer-order-capabilities-v1"] = (
        "customer-order-capabilities-v1"
    )
    result_type: Literal["customer_order.capabilities"] = (
        "customer_order.capabilities"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    authoritative_order_ledger: Literal[False] = False
    official_order_total_available: Literal[False] = False
    supported_operations: tuple[
        Literal["PREVIEW", "CONTROLLED_EXPORT", "EXPORT_AUDIT"], ...
    ] = ("PREVIEW", "CONTROLLED_EXPORT", "EXPORT_AUDIT")
    customers: list[AICustomerOrderCustomerCapability] = Field(max_length=20)


class AICustomerOrderExportAuditSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,95}$",
    )
    customer_code: str = Field(min_length=1, max_length=64)
    received_date: str = Field(max_length=32)
    preview_schema_version: str = Field(max_length=96)
    output_file_name: str = Field(max_length=255)
    output_template: str = Field(max_length=128)
    confirmed_issue_count: int = Field(ge=0)
    manual_override_count: int = Field(ge=0)
    created_at: str = Field(max_length=32)


class AICustomerOrderExportAuditListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["customer-order-export-audit-summary-v1"] = (
        "customer-order-export-audit-summary-v1"
    )
    result_type: Literal["customer_order.export_audit_summary_list"] = (
        "customer_order.export_audit_summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    audits: list[AICustomerOrderExportAuditSummary] = Field(max_length=20)
