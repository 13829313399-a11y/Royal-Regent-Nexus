"""Canonical application permission-code catalog.

This module intentionally has no database or authorization-service imports so
the fixed system-position catalog can depend on it without creating a cycle.
"""

UV_PRINTING_PERMISSION_CODES = tuple("uv_printing:" + action for action in (
    "read", "report", "quality", "master_write", "shift_write", "ink_write",
    "cost_read", "cost_write", "payroll_read", "payroll_write", "import", "export", "close",
))

SPRAY_PRODUCTION_PERMISSION_CODES = tuple(
    "spray_production:" + action for action in (
        "read", "order_write", "plan", "report", "quality", "logistics", "cost_read",
        "cost_write", "settlement", "master_write", "import", "export",
    )
)

INJECTION_SCHEDULING_PERMISSION_CODES = (
    "injection_scheduling:read",
    "injection_scheduling:plan",
    "injection_scheduling:report",
    "injection_scheduling:master_write",
)

MOLDING_SAMPLE_PERMISSION_CODES = (
    "molding_sample:read",
    "molding_sample:cross_factory_read",
    "molding_sample:cross_factory_cost_read",
    "molding_sample:export",
    "molding_sample:create",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:supervisor_review",
    "molding_sample:manager_review",
    "molding_sample:dispatch",
    "molding_sample:raw_material_write",
    "molding_sample:warehouse_requisition",
    "molding_sample:inventory_issue",
    "molding_sample:production_read",
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:price_update",
    "molding_sample:audit_read",
    "molding_sample:notification_read",
)

CARTON_MARK_PERMISSION_CODES = (
    "carton_mark:read",
    "carton_mark:template_upload",
    "carton_mark:template_release",
    "carton_mark:customer_manage",
    "carton_mark:photo_upload",
    "carton_mark:review",
)

CUSTOMER_PRICE_PERMISSION_CODES = (
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
)

CUSTOMER_ORDER_PERMISSION_CODES = (
    "customer_order:read",
    "customer_order:export",
    "customer_order:duplicate_confirm",
    "customer_order:audit_read",
)

CARTON_PROCUREMENT_PERMISSION_CODES = (
    "carton_procurement:read",
    "carton_procurement:order_write",
    "carton_procurement:order_adjust",
    "carton_procurement:receipt_write",
    "carton_procurement:inventory_write",
    "carton_procurement:closing_manage",
    "carton_procurement:import",
    "carton_procurement:exception_manage",
    "carton_procurement:customer_manage",
    "carton_procurement:master_manage",
)

THREE_D_PRINTING_PERMISSION_CODES = (
    "three_d_printing:read",
    "three_d_printing:operate",
    "three_d_printing:image_upload",
    "three_d_printing:export",
    "three_d_printing:printer_control",
    "three_d_printing:audit_read",
)

QC_INSPECTION_PERMISSION_CODES = (
    "qc_inspection:read",
    "qc_inspection:schedule_write",
    "qc_inspection:order_write",
    "qc_inspection:result_write",
    "qc_inspection:problem_write",
    "qc_inspection:report_export",
    "qc_inspection:report_rename_preview",
    "qc_inspection:report_rename_execute",
    "qc_inspection:customer_manage",
    "qc_inspection:audit_read",
    "qc_inspection:factory_summary",
    "qc_inspection:group_summary",
)

INTERNAL_QUOTE_SECTION_CODES = (
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

INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE = "internal_quote:self_review"

INTERNAL_QUOTE_PERMISSION_CODES = (
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:header_edit",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:archive",
    "internal_quote:baseline_read",
    "internal_quote:baseline_manage",
    "internal_quote:customer_manage",
    "internal_quote:reference_manage",
    "internal_quote:export",
    "internal_quote:final_submit",
    "internal_quote:final_approve",
    INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE,
    *(
        permission_code
        for section_code in INTERNAL_QUOTE_SECTION_CODES
        for permission_code in (
            f"internal_quote:{section_code}_edit",
            f"internal_quote:{section_code}_review",
        )
    ),
)

SYSTEM_MANAGEMENT_PERMISSION_CODES = (
    "system:user_manage",
    "system:role_manage",
    "system:access_manage",
    "system:access_request",
    "system:access_approve",
    "system:audit_read",
    "system:permission_catalog_read",
)

BUSINESS_PERMISSION_CODES = (
    *UV_PRINTING_PERMISSION_CODES,
    *SPRAY_PRODUCTION_PERMISSION_CODES,
    *INJECTION_SCHEDULING_PERMISSION_CODES,
    *MOLDING_SAMPLE_PERMISSION_CODES,
    *CARTON_MARK_PERMISSION_CODES,
    *CARTON_PROCUREMENT_PERMISSION_CODES,
    *CUSTOMER_PRICE_PERMISSION_CODES,
    *CUSTOMER_ORDER_PERMISSION_CODES,
    *THREE_D_PRINTING_PERMISSION_CODES,
    *QC_INSPECTION_PERMISSION_CODES,
    *INTERNAL_QUOTE_PERMISSION_CODES,
)

APPLICATION_PERMISSION_CODES = tuple(
    dict.fromkeys((*BUSINESS_PERMISSION_CODES, *SYSTEM_MANAGEMENT_PERMISSION_CODES))
)
