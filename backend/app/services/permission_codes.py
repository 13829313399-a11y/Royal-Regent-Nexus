"""Canonical application permission-code catalog.

This module intentionally has no database or authorization-service imports so
the fixed system-position catalog can depend on it without creating a cycle.
"""

UV_OPS_PERMISSION_CODES = tuple("uv_ops:" + action for action in (
    "read", "master_write", "plan_write", "production_write", "quality_write",
    "shift_write", "handover_write", "inventory_write", "cost_read", "cost_write",
    "payroll_read", "payroll_write", "agent_manage", "dispatch", "close_period",
    "import", "export", "audit_read",
))

CUTTING_OPS_PERMISSION_CODES = tuple("cutting_ops:" + action for action in (
    "read", "master_write", "bom_write", "bom_publish",
))

SPRAY_OPS_PERMISSION_CODES = tuple("spray_ops:" + action for action in (
    "read", "plan", "report", "quality", "stock_write", "procure", "master_write",
    "cost_read", "cost_write", "payroll_read", "payroll_write", "settle", "import", "export",
))

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
    "customer_price:settings_read",
    "customer_price:settings_manage",
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
    "customer_order:write",
    "customer_order:dispatch",
    "customer_order:shipment_confirm",
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
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

CARTON_SUPPLIER_PERMISSION_CODES = (
    "carton_supplier:read",
    "carton_supplier:edit",
    "carton_supplier:approve",
)

FABRIC_WAREHOUSE_PERMISSION_CODES = (
    "fabric_warehouse:read",
    "fabric_warehouse:import",
    "fabric_warehouse:receive",
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
    "system:feedback_manage",
    "system:user_manage",
    "system:role_manage",
    "system:access_manage",
    "system:access_request",
    "system:access_approve",
    "system:audit_read",
    "system:permission_catalog_read",
)

BUSINESS_PERMISSION_CODES = (
    *CUTTING_OPS_PERMISSION_CODES,
    *FABRIC_WAREHOUSE_PERMISSION_CODES,
    *UV_OPS_PERMISSION_CODES,
    *SPRAY_OPS_PERMISSION_CODES,
    *INJECTION_SCHEDULING_PERMISSION_CODES,
    *MOLDING_SAMPLE_PERMISSION_CODES,
    *CARTON_MARK_PERMISSION_CODES,
    *CARTON_PROCUREMENT_PERMISSION_CODES,
    *CARTON_SUPPLIER_PERMISSION_CODES,
    *CUSTOMER_PRICE_PERMISSION_CODES,
    *CUSTOMER_ORDER_PERMISSION_CODES,
    *THREE_D_PRINTING_PERMISSION_CODES,
    *QC_INSPECTION_PERMISSION_CODES,
    *INTERNAL_QUOTE_PERMISSION_CODES,
)

# Private employee submission and developer review are separate from business
# entitlements. Submission defaults to confirmed home-factory employees; its
# catalog entry supports independent disabling and explicit IAM denies.
MODULE_FEEDBACK_PERMISSION_CODES = ("module_feedback:submit", "module_feedback:manage")

APPLICATION_PERMISSION_CODES = tuple(
    dict.fromkeys((*BUSINESS_PERMISSION_CODES, *SYSTEM_MANAGEMENT_PERMISSION_CODES, *MODULE_FEEDBACK_PERMISSION_CODES))
)
