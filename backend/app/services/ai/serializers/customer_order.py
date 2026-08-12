from __future__ import annotations

from app.schemas.ai.customer_order import (
    AICustomerOrderCapabilitiesData,
    AICustomerOrderCustomerCapability,
    AICustomerOrderExportAuditListData,
    AICustomerOrderExportAuditSummary,
)
from app.services.ai.customer_order_read import (
    CustomerOrderAICapabilities,
    CustomerOrderAIExportAuditPage,
)


def serialize_customer_order_capabilities(
    value: object,
) -> AICustomerOrderCapabilitiesData:
    if not isinstance(value, CustomerOrderAICapabilities):
        raise TypeError("customer order capability serializer received an unsupported value")
    return AICustomerOrderCapabilitiesData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        customers=[
            AICustomerOrderCustomerCapability(
                customer_code=item.customer_code,
                customer_name=item.customer_name,
            )
            for item in value.customers
        ],
    )


def serialize_customer_order_export_audits(
    value: object,
) -> AICustomerOrderExportAuditListData:
    if not isinstance(value, CustomerOrderAIExportAuditPage):
        raise TypeError("customer order audit serializer received an unsupported value")
    return AICustomerOrderExportAuditListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        audits=[
            AICustomerOrderExportAuditSummary(
                audit_id=item.audit_id,
                customer_code=item.customer_code,
                received_date=item.received_date,
                preview_schema_version=item.preview_schema_version,
                output_file_name=item.output_file_name,
                output_template=item.output_template,
                confirmed_issue_count=item.confirmed_issue_count,
                manual_override_count=item.manual_override_count,
                created_at=item.created_at,
            )
            for item in value.items
        ],
    )
