from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import business_now
from app.models.customer_order import CustomerOrderExportAudit
from app.services.customer_order_huadeng import HUADENG_CUSTOMER_MAPPINGS
from app.services.customer_order_huakang_a import HUAKANG_A_CUSTOMER_MAPPINGS
from app.services.customer_order_huakang_c import HUAKANG_C_CUSTOMER_MAPPINGS
from app.services.customer_order_huaxing import HUAXING_CUSTOMER_MAPPINGS

_LEGACY_CUSTOMERS = {
    "buzzbee": "BuzzBee",
    "dickie": "Dickie",
    "caixing": "彩星",
}


@dataclass(frozen=True, slots=True)
class CustomerOrderAICapability:
    customer_code: str
    customer_name: str


@dataclass(frozen=True, slots=True)
class CustomerOrderAICapabilities:
    factory_id: str
    as_of: str
    customers: tuple[CustomerOrderAICapability, ...]


@dataclass(frozen=True, slots=True)
class CustomerOrderAIExportAuditRow:
    audit_id: str
    customer_code: str
    received_date: str
    preview_schema_version: str
    output_file_name: str
    output_template: str
    confirmed_issue_count: int
    manual_override_count: int
    created_at: str


@dataclass(frozen=True, slots=True)
class CustomerOrderAIExportAuditPage:
    factory_id: str
    as_of: str
    limit: int
    offset: int
    truncated: bool
    items: tuple[CustomerOrderAIExportAuditRow, ...]


def _customer_capabilities(factory_id: str) -> tuple[CustomerOrderAICapability, ...]:
    if factory_id == "huaxing":
        names = {
            **_LEGACY_CUSTOMERS,
            **{code: spec.name for code, spec in HUAXING_CUSTOMER_MAPPINGS.items()},
        }
    elif factory_id == "huadeng":
        names = {code: spec.name for code, spec in HUADENG_CUSTOMER_MAPPINGS.items()}
    elif factory_id == "huakang-a":
        names = {code: spec.name for code, spec in HUAKANG_A_CUSTOMER_MAPPINGS.items()}
    elif factory_id == "huakang-c":
        names = {code: spec.name for code, spec in HUAKANG_C_CUSTOMER_MAPPINGS.items()}
    else:
        names = {}
    return tuple(
        CustomerOrderAICapability(customer_code=code, customer_name=name)
        for code, name in sorted(names.items())
    )


def get_customer_order_ai_capabilities(
    factory_id: str,
) -> CustomerOrderAICapabilities:
    return CustomerOrderAICapabilities(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        customers=_customer_capabilities(factory_id),
    )


def list_customer_order_ai_export_audits(
    db: Session,
    factory_id: str,
    *,
    customer_code: str = "",
    limit: int = 10,
    offset: int = 0,
) -> CustomerOrderAIExportAuditPage:
    scope = select(
        CustomerOrderExportAudit.id.label("audit_id"),
        CustomerOrderExportAudit.customer_code.label("customer_code"),
        CustomerOrderExportAudit.received_date.label("received_date"),
        CustomerOrderExportAudit.preview_schema_version.label(
            "preview_schema_version"
        ),
        CustomerOrderExportAudit.output_file_name.label("output_file_name"),
        CustomerOrderExportAudit.output_template.label("output_template"),
        CustomerOrderExportAudit.confirmed_issue_count.label(
            "confirmed_issue_count"
        ),
        CustomerOrderExportAudit.manual_override_count.label(
            "manual_override_count"
        ),
        CustomerOrderExportAudit.created_at.label("created_at"),
    ).where(CustomerOrderExportAudit.factory_id == factory_id)
    normalized_customer_code = customer_code.strip()
    if normalized_customer_code:
        scope = scope.where(
            CustomerOrderExportAudit.customer_code == normalized_customer_code
        )
    page = (
        scope.order_by(
            CustomerOrderExportAudit.created_at.desc(),
            CustomerOrderExportAudit.id.desc(),
        )
        .limit(limit + 1)
        .offset(offset)
        .cte("ai_customer_order_export_audit_page")
    )
    results = db.execute(select(page)).mappings().all()
    truncated = len(results) > limit
    items = tuple(
        CustomerOrderAIExportAuditRow(
            audit_id=str(row["audit_id"]),
            customer_code=str(row["customer_code"] or ""),
            received_date=str(row["received_date"] or ""),
            preview_schema_version=str(row["preview_schema_version"] or ""),
            output_file_name=str(row["output_file_name"] or ""),
            output_template=str(row["output_template"] or ""),
            confirmed_issue_count=int(row["confirmed_issue_count"] or 0),
            manual_override_count=int(row["manual_override_count"] or 0),
            created_at=str(row["created_at"] or ""),
        )
        for row in results[:limit]
    )
    return CustomerOrderAIExportAuditPage(
        factory_id=factory_id,
        as_of=business_now().isoformat(timespec="seconds"),
        limit=limit,
        offset=offset,
        truncated=truncated,
        items=items,
    )
