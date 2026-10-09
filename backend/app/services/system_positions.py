import hashlib
import json
from dataclasses import dataclass

from app.services.iam_scope import (
    CROSS_FACTORY_OPERATE_SCOPE,
    CROSS_FACTORY_READ_SCOPE,
    OWN_FACTORY_SCOPE,
    VALID_SCOPE_MODES,
    ScopeMode,
)
from app.services.permission_codes import (
    APPLICATION_PERMISSION_CODES,
    FABRIC_WAREHOUSE_PERMISSION_CODES,
    SPRAY_OPS_PERMISSION_CODES,
    CUTTING_OPS_PERMISSION_CODES,
    UV_OPS_PERMISSION_CODES,
    BUSINESS_PERMISSION_CODES,
    CARTON_PROCUREMENT_PERMISSION_CODES,
    CARTON_SUPPLIER_PERMISSION_CODES,
    INJECTION_SCHEDULING_PERMISSION_CODES,
    INTERNAL_QUOTE_SELF_REVIEW_PERMISSION_CODE,
    QC_INSPECTION_PERMISSION_CODES,
    SYSTEM_MANAGEMENT_PERMISSION_CODES,
    THREE_D_PRINTING_PERMISSION_CODES,
)

SYSTEM_POSITION_DEFINITION_VERSION = "fixed-v33"
PRODUCTION_TASK_READ_PERMISSION_CODE = "molding_sample:production_read"
MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE = "molding_sample:dispatch"
MOLDING_SAMPLE_DISPATCH_POSITION_ROLE_IDS = frozenset(
    {
        "position_general_manager",
        "position_engineering_manager",
        "position_engineering_supervisor",
    }
)
PRODUCTION_TASK_OPERATE_PERMISSION_CODES = frozenset(
    {
        "molding_sample:production_start",
        "molding_sample:production_fillback",
        "molding_sample:production_complete",
    }
)
PRODUCTION_TASK_OPERATING_POSITION_ROLE_IDS = frozenset(
    {
        "position_general_manager",
        "position_molding_manager",
        "position_molding_supervisor",
        "position_molding_clerk",
    }
)
THREE_D_PRINTING_OPERATOR_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "three_d_printing:read",
    "three_d_printing:operate",
    "three_d_printing:image_upload",
    "three_d_printing:export",
)
THREE_D_PRINTING_SUPERVISOR_PERMISSION_CODES = (
    *THREE_D_PRINTING_OPERATOR_PERMISSION_CODES,
    "three_d_printing:audit_read",
)
CARTON_CUSTOMER_MANAGE_PERMISSION_CODE = "carton_procurement:customer_manage"
CARTON_ORDER_ADJUST_PERMISSION_CODE = "carton_procurement:order_adjust"
CARTON_MARK_CUSTOMER_MANAGE_PERMISSION_CODE = "carton_mark:customer_manage"
CARTON_MARK_TEMPLATE_RELEASE_PERMISSION_CODE = "carton_mark:template_release"
CARTON_QC_WORKSPACE_POSITION_ROLE_IDS = frozenset(
    {
        "position_carton_manager",
        "position_carton_supervisor",
    }
)
CARTON_QC_WORKSPACE_PERMISSION_CODES = frozenset(
    {
        "carton_mark:read",
        "carton_mark:photo_upload",
        "carton_mark:review",
    }
)
CARTON_OPERATION_PERMISSION_CODES = tuple(
    code
    for code in CARTON_PROCUREMENT_PERMISSION_CODES
    if code not in {
        CARTON_CUSTOMER_MANAGE_PERMISSION_CODE,
        "carton_procurement:master_manage",
        CARTON_ORDER_ADJUST_PERMISSION_CODE,
    }
)
QC_INSPECTION_OPERATOR_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "carton_mark:read",
    "carton_mark:photo_upload",
    "carton_mark:review",
    "qc_inspection:read",
    "qc_inspection:schedule_write",
    "qc_inspection:order_write",
    "qc_inspection:result_write",
    "qc_inspection:problem_write",
    "qc_inspection:report_export",
    "qc_inspection:report_rename_preview",
    "qc_inspection:report_rename_execute",
)
QC_INSPECTION_SUPERVISOR_PERMISSION_CODES = (
    *QC_INSPECTION_OPERATOR_PERMISSION_CODES,
    "qc_inspection:customer_manage",
    "qc_inspection:audit_read",
    "qc_inspection:factory_summary",
)

@dataclass(frozen=True)
class SystemPositionDefinition:
    role_id: str
    name: str
    department: str
    department_name: str
    sort_order: int
    description: str
    scope_mode: ScopeMode = OWN_FACTORY_SCOPE
    permission_codes: tuple[str, ...] = ()


_GENERAL_MANAGER_PERMISSION_CODE_LIST = (
    *INJECTION_SCHEDULING_PERMISSION_CODES,
    "molding_sample:read",
    "molding_sample:cross_factory_read",
    "molding_sample:cross_factory_cost_read",
    "molding_sample:export",
    "molding_sample:create",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:supervisor_review",
    "molding_sample:manager_review",
    MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE,
    "molding_sample:raw_material_write",
    "molding_sample:warehouse_requisition",
    "molding_sample:inventory_issue",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:price_update",
    "molding_sample:audit_read",
    "molding_sample:notification_read",
    "carton_mark:read",
    "carton_mark:template_upload",
    CARTON_MARK_TEMPLATE_RELEASE_PERMISSION_CODE,
    CARTON_MARK_CUSTOMER_MANAGE_PERMISSION_CODE,
    "carton_mark:photo_upload",
    "carton_mark:review",
    *CARTON_PROCUREMENT_PERMISSION_CODES,
    *FABRIC_WAREHOUSE_PERMISSION_CODES,
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "customer_order:read",
    "customer_order:export",
    "customer_order:duplicate_confirm",
    "customer_order:audit_read",
    "customer_order:write",
    "customer_order:dispatch",
    "customer_order:shipment_confirm",
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
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
    "internal_quote:sales_edit",
    "internal_quote:sales_review",
    "internal_quote:engineering_edit",
    "internal_quote:engineering_review",
    "internal_quote:electronic_edit",
    "internal_quote:electronic_review",
    "internal_quote:molding_edit",
    "internal_quote:molding_review",
    "internal_quote:painting_edit",
    "internal_quote:painting_review",
    "internal_quote:slush_edit",
    "internal_quote:slush_review",
    "internal_quote:sewing_edit",
    "internal_quote:sewing_review",
    "internal_quote:hair_edit",
    "internal_quote:hair_review",
    "internal_quote:assembly_edit",
    "internal_quote:assembly_review",
)
GENERAL_MANAGER_PERMISSION_CODES = frozenset(_GENERAL_MANAGER_PERMISSION_CODE_LIST)
GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES: frozenset[str] = frozenset(
    (
        *UV_OPS_PERMISSION_CODES,
        *SPRAY_OPS_PERMISSION_CODES,
        *CUTTING_OPS_PERMISSION_CODES,
        "customer_price:settings_read",
        "customer_price:settings_manage",
        *THREE_D_PRINTING_PERMISSION_CODES,
        *QC_INSPECTION_PERMISSION_CODES,
        *CARTON_SUPPLIER_PERMISSION_CODES,
    )
)

ENGINEER_PERMISSION_CODES = (
    "molding_sample:read",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:export",
    "molding_sample:create",
    "molding_sample:raw_material_write",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:notification_read",
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:engineering_edit",
)

ENGINEERING_SUPERVISOR_PERMISSION_CODES = (
    *ENGINEER_PERMISSION_CODES,
    "molding_sample:supervisor_review",
    MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE,
    "internal_quote:customer_manage",
    "internal_quote:reference_manage",
    "internal_quote:engineering_review",
)

SALES_SUPERVISOR_PERMISSION_CODES = (
    "customer_price:settings_read",
    "customer_price:settings_manage",
    "customer_order:write",
    "customer_order:dispatch",
    "customer_order:shipment_confirm",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "customer_order:read",
    "customer_order:export",
    "customer_order:duplicate_confirm",
    "customer_order:audit_read",
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
    "internal_quote:sales_edit",
    "internal_quote:sales_review",
)

SALES_BUSINESS_PERMISSION_CODES = (
    "customer_price:settings_read",
    "customer_order:write",
    "customer_order:dispatch",
    "customer_order:shipment_confirm",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "customer_order:read",
    "customer_order:export",
    "customer_order:duplicate_confirm",
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:header_edit",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:baseline_read",
    "internal_quote:export",
    "internal_quote:final_submit",
    "internal_quote:sales_edit",
)

PRODUCTION_SUPERVISOR_PERMISSION_CODES = (
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
    *INJECTION_SCHEDULING_PERMISSION_CODES,
    "molding_sample:read",
    "molding_sample:export",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:audit_read",
    "molding_sample:notification_read",
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:molding_edit",
    "internal_quote:molding_review",
    *THREE_D_PRINTING_SUPERVISOR_PERMISSION_CODES[1:],
)

PRODUCTION_MANAGER_PERMISSION_CODES = tuple(
    permission
    for permission in PRODUCTION_SUPERVISOR_PERMISSION_CODES
    if not permission.startswith("three_d_printing:")
)

PRODUCTION_CLERK_PERMISSION_CODES = (
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
    *INJECTION_SCHEDULING_PERMISSION_CODES[:3],
    "molding_sample:read",
    "molding_sample:export",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:notification_read",
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:molding_edit",
)

PAINTING_CLERK_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:painting_edit",
)

PAINTING_SUPERVISOR_PERMISSION_CODES = (
    *PAINTING_CLERK_PERMISSION_CODES,
    "internal_quote:painting_review",
)

# 啤机职位可跨厂只读查看正式工程啤办看板与明细，并操作
# 啤办生产任务和注塑排产。范围模式负责区分文员的“跨厂查看 / 本厂操作”
# 和主管、经理的“跨厂操作”，且不授予工程开单、编辑、审核、删除或导出。
MOLDING_CLERK_PERMISSION_CODES = (
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
    *INJECTION_SCHEDULING_PERMISSION_CODES[:3],
    "molding_sample:read",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:notification_read",
)

MOLDING_SUPERVISOR_PERMISSION_CODES = (
    *MOLDING_CLERK_PERMISSION_CODES,
    "injection_scheduling:master_write",
)

WAREHOUSE_PERMISSION_CODES = (
    *FABRIC_WAREHOUSE_PERMISSION_CODES,
    "carton_mark:read",
    "carton_mark:template_upload",
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
    "molding_sample:read",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "molding_sample:export",
    "molding_sample:raw_material_write",
    "molding_sample:warehouse_requisition",
    "molding_sample:inventory_issue",
    "molding_sample:notification_read",
    "carton_procurement:master_manage",
    *CARTON_OPERATION_PERMISSION_CODES,
)

QA_INSPECTOR_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "carton_mark:read",
    "carton_mark:photo_upload",
    "carton_mark:review",
)
QA_CLERK_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "carton_mark:read",
    "carton_mark:photo_upload",
)
CARTON_WAREHOUSE_PERMISSION_CODES = (
    "customer_order:inbox_read",
    "customer_order:inbox_receive",
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "carton_mark:read",
    "carton_mark:template_upload",
    "carton_procurement:master_manage",
    *CARTON_OPERATION_PERMISSION_CODES,
)
CARTON_SUPERVISOR_PERMISSION_CODES = (
    *CARTON_WAREHOUSE_PERMISSION_CODES,
    CARTON_ORDER_ADJUST_PERMISSION_CODE,
    CARTON_CUSTOMER_MANAGE_PERMISSION_CODE,
    CARTON_MARK_CUSTOMER_MANAGE_PERMISSION_CODE,
    CARTON_MARK_TEMPLATE_RELEASE_PERMISSION_CODE,
    "carton_mark:photo_upload",
    "carton_mark:review",
)
CARTON_EXTERNAL_PERMISSION_CODES = (
    PRODUCTION_TASK_READ_PERMISSION_CODE,
    "carton_mark:read",
)


SYSTEM_POSITION_DEFINITIONS: tuple[SystemPositionDefinition, ...] = (
    SystemPositionDefinition(
        role_id="position_general_manager",
        name="总经理",
        department="management",
        department_name="总务",
        sort_order=100,
        description="集团全业务管理；跨厂、跨部门执行业务操作，不包含账号与权限管理",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=_GENERAL_MANAGER_PERMISSION_CODE_LIST,
    ),
    SystemPositionDefinition(
        role_id="position_engineering_manager",
        name="经理",
        department="engineering",
        department_name="工程部",
        sort_order=200,
        description="跨厂查看工程数据；本厂开单、维护、原料管理、主管审核与生产任务分派",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=ENGINEERING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_engineering_supervisor",
        name="主管",
        department="engineering",
        department_name="工程部",
        sort_order=210,
        description="跨厂查看工程数据；本厂开单、维护、原料管理、审核驳回与生产任务分派",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=ENGINEERING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_engineering_engineer",
        name="工程师",
        department="engineering",
        department_name="工程部",
        sort_order=220,
        description="跨厂查看工程数据；本厂开单、草稿维护和原料管理，不含审核权",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=ENGINEER_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_sales_manager",
        name="经理",
        department="sales-business",
        department_name="业务部",
        sort_order=300,
        description="跨厂查看业务数据；仅在本厂业务部管理报价、复核与最终放行",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=SALES_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_sales_supervisor",
        name="主管",
        department="sales-business",
        department_name="业务部",
        sort_order=310,
        description="跨厂查看业务数据；仅在本厂业务部复核报价、审核与最终放行",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=SALES_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_sales_business",
        name="业务",
        department="sales-business",
        department_name="业务部",
        sort_order=320,
        description="跨厂查看业务数据；仅在本厂业务部维护客户转换与内部报价",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=SALES_BUSINESS_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_manager",
        name="生产经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=400,
        description="全厂只读查看啤办生产任务；参与本厂报价协同，维护本厂注塑排产、报工与主数据",
        permission_codes=PRODUCTION_MANAGER_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_supervisor",
        name="生产主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=410,
        description="全厂只读查看啤办生产任务；参与本厂报价协同，维护本厂注塑排产、报工与主数据",
        permission_codes=PRODUCTION_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_clerk",
        name="生产文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=420,
        description="全厂只读查看啤办生产任务；参与本厂报价协同，维护本厂注塑计划与报工",
        permission_codes=PRODUCTION_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_3d_manager",
        name="3D打印经理",
        department="three-d-printing",
        department_name="3D打印部",
        sort_order=490,
        description="维护华康A 3D打印业务资料、库存、排期、报表与审计，不含远程控制",
        permission_codes=THREE_D_PRINTING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_3d_supervisor",
        name="3D打印主管",
        department="three-d-printing",
        department_name="3D打印部",
        sort_order=491,
        description="维护华康A 3D打印业务资料、库存、排期、报表与审计，不含远程控制",
        permission_codes=THREE_D_PRINTING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_3d_operator",
        name="3D打印操作员",
        department="three-d-printing",
        department_name="3D打印部",
        sort_order=492,
        description="维护华康A 3D打印业务资料、库存、排期和报表，不含远程控制",
        permission_codes=THREE_D_PRINTING_OPERATOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_painting_manager",
        name="喷油经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=430,
        description="全厂只读查看啤办生产任务；本厂填写并复核喷油报价",
        permission_codes=PAINTING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_painting_supervisor",
        name="喷油主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=440,
        description="全厂只读查看啤办生产任务；本厂填写并复核喷油报价",
        permission_codes=PAINTING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_painting_clerk",
        name="喷油文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=450,
        description="全厂只读查看啤办生产任务；本厂填写喷油报价，不含复核权",
        permission_codes=PAINTING_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_molding_manager",
        name="啤机经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=460,
        description="跨厂只读查看工程啤办；跨厂操作生产任务、注塑排产、报工与主数据，暂与啤机主管一致",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=MOLDING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_molding_supervisor",
        name="啤机主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=470,
        description="跨厂只读查看工程啤办；跨厂操作生产任务、注塑排产、报工与主数据",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=MOLDING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_molding_clerk",
        name="啤机文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=480,
        description="跨厂只读查看工程啤办、生产任务与注塑排产；仅操作本厂任务、注塑计划与报工，通知仅限本厂",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=MOLDING_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_warehouse_manager",
        name="经理",
        department="pmc-warehouse",
        department_name="仓库",
        sort_order=500,
        description="跨厂操作 PMC 仓库领料、发料、原料与纸箱库存及下游订单收件箱",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_warehouse_supervisor",
        name="主管",
        department="pmc-warehouse",
        department_name="仓库",
        sort_order=510,
        description="仓库领料、发料与库存管理",
        permission_codes=WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_warehouse_keeper",
        name="仓管",
        department="pmc-warehouse",
        department_name="仓库",
        sort_order=520,
        description="仓库领料、发料与库存管理",
        permission_codes=WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qa_manager",
        name="经理",
        department="qa",
        department_name="QA部",
        sort_order=600,
        description="QA 箱唛检验管理与复核",
        permission_codes=QA_INSPECTOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qa_supervisor",
        name="主管",
        department="qa",
        department_name="QA部",
        sort_order=610,
        description="QA 箱唛检验管理与复核",
        permission_codes=QA_INSPECTOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qa_clerk",
        name="文员",
        department="qa",
        department_name="QA部",
        sort_order=620,
        description="QA 箱唛资料查看与实拍上传",
        permission_codes=QA_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qc_manager",
        name="经理",
        department="qc",
        department_name="QC部",
        sort_order=700,
        description="维护本厂 QC 验货运营、客户配置、正式汇总与审计",
        permission_codes=QC_INSPECTION_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qc_supervisor",
        name="主管",
        department="qc",
        department_name="QC部",
        sort_order=710,
        description="维护本厂 QC 验货运营、客户配置、正式汇总与审计",
        permission_codes=QC_INSPECTION_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_qc_inspector",
        name="QC检验员",
        department="qc",
        department_name="QC部",
        sort_order=720,
        description="维护本厂排期、临时单、验货结果、问题、报表和报告改名",
        permission_codes=QC_INSPECTION_OPERATOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_carton_manager",
        name="经理",
        department="carton",
        department_name="纸箱部",
        sort_order=800,
        description="跨厂操作纸箱箱唛模板、采购仓务与客户主数据，并执行 QC 箱唛核验",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=CARTON_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_carton_supervisor",
        name="主管",
        department="carton",
        department_name="纸箱部",
        sort_order=810,
        description="维护本厂纸箱箱唛模板、采购仓务与客户主数据，并执行 QC 箱唛核验",
        permission_codes=CARTON_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_carton_warehouse_keeper",
        name="纸箱仓管",
        department="carton",
        department_name="纸箱部",
        sort_order=820,
        description="纸箱箱唛 Excel、打印 PDF 与文字核对维护",
        permission_codes=CARTON_WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_external_carton_warehouse_keeper",
        name="外部纸箱仓管",
        department="carton",
        department_name="纸箱部",
        sort_order=830,
        description="外部纸箱仓务与箱唛查看",
        permission_codes=CARTON_EXTERNAL_PERMISSION_CODES,
    ),
)


SYSTEM_POSITION_BY_ROLE_ID = {
    item.role_id: item for item in SYSTEM_POSITION_DEFINITIONS
}

SYSTEM_POSITION_DEPARTMENT_NAMES = {
    item.department: item.department_name for item in SYSTEM_POSITION_DEFINITIONS
}

SPECIAL_SYSTEM_ROLE_CODES = {
    "admin",
    "factory_permission_admin",
    "department_permission_admin",
}


def system_position_definition_hash(definition: SystemPositionDefinition) -> str:
    payload = {
        "definition_version": SYSTEM_POSITION_DEFINITION_VERSION,
        "role_id": definition.role_id,
        "name": definition.name,
        "department": definition.department,
        "department_name": definition.department_name,
        "sort_order": definition.sort_order,
        "description": definition.description,
        "scope_mode": definition.scope_mode,
        "permission_codes": sorted(definition.permission_codes),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def system_position_catalog_hash() -> str:
    encoded = "\n".join(
        system_position_definition_hash(item)
        for item in sorted(
            SYSTEM_POSITION_DEFINITIONS,
            key=lambda definition: definition.role_id,
        )
    ).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def validate_system_position_definitions() -> None:
    role_ids = [item.role_id for item in SYSTEM_POSITION_DEFINITIONS]
    if len(role_ids) != len(set(role_ids)):
        raise RuntimeError("系统内置职位 role_id 存在重复")

    department_names = [
        (item.department, item.name) for item in SYSTEM_POSITION_DEFINITIONS
    ]
    if len(department_names) != len(set(department_names)):
        raise RuntimeError("同一部门存在重复的系统内置职位名称")

    registered_codes = set(APPLICATION_PERMISSION_CODES)
    for item in SYSTEM_POSITION_DEFINITIONS:
        if item.scope_mode not in VALID_SCOPE_MODES:
            raise RuntimeError(
                f"系统内置职位 {item.role_id} 的 scope_mode 无效：{item.scope_mode}"
            )
        if len(item.permission_codes) != len(set(item.permission_codes)):
            raise RuntimeError(
                f"系统内置职位 {item.role_id} 的 permission_codes 存在重复"
            )
        unknown_codes = sorted(set(item.permission_codes) - registered_codes)
        if unknown_codes:
            raise RuntimeError(
                f"系统内置职位 {item.role_id} 引用了未注册权限：{','.join(unknown_codes)}"
            )

    if not all(
        PRODUCTION_TASK_READ_PERMISSION_CODE in item.permission_codes
        for item in SYSTEM_POSITION_DEFINITIONS
    ):
        raise RuntimeError("全部系统内置职位都必须可全厂只读查看啤办生产任务")

    production_task_operating_role_ids = {
        item.role_id
        for item in SYSTEM_POSITION_DEFINITIONS
        if PRODUCTION_TASK_OPERATE_PERMISSION_CODES & set(item.permission_codes)
    }
    if (
        production_task_operating_role_ids
        != PRODUCTION_TASK_OPERATING_POSITION_ROLE_IDS
    ):
        raise RuntimeError("啤办生产任务操作权限只能授予总经理和啤机职位")

    dispatch_role_ids = {
        item.role_id
        for item in SYSTEM_POSITION_DEFINITIONS
        if MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE in item.permission_codes
    }
    if dispatch_role_ids != MOLDING_SAMPLE_DISPATCH_POSITION_ROLE_IDS:
        raise RuntimeError("啤办生产任务分派权限只能授予总经理、工程经理和工程主管")

    all_business_codes = set(BUSINESS_PERMISSION_CODES)
    decided_general_manager_codes = (
        GENERAL_MANAGER_PERMISSION_CODES
        | GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
    )
    if (
        GENERAL_MANAGER_PERMISSION_CODES
        & GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
    ):
        raise RuntimeError("总经理允许与排除的业务权限不能重叠")
    if decided_general_manager_codes != all_business_codes:
        undecided = sorted(all_business_codes - decided_general_manager_codes)
        obsolete = sorted(decided_general_manager_codes - all_business_codes)
        raise RuntimeError(
            "总经理业务权限决策不完整："
            f"未决={','.join(undecided) or '无'}；"
            f"已失效={','.join(obsolete) or '无'}"
        )
    if GENERAL_MANAGER_PERMISSION_CODES & set(SYSTEM_MANAGEMENT_PERMISSION_CODES):
        raise RuntimeError("总经理不能包含任何 system:* 权限")

    definitions_by_id = {
        definition.role_id: definition for definition in SYSTEM_POSITION_DEFINITIONS
    }
    engineer = definitions_by_id["position_engineering_engineer"]
    engineering_supervisor = definitions_by_id["position_engineering_supervisor"]
    engineering_manager = definitions_by_id["position_engineering_manager"]
    if not all(
        definition.scope_mode == CROSS_FACTORY_READ_SCOPE
        and "molding_sample:raw_material_write" in definition.permission_codes
        for definition in (engineer, engineering_supervisor, engineering_manager)
    ):
        raise RuntimeError("工程部内置职位必须跨厂查看并可维护本厂原料资料")
    if not (
        set(engineer.permission_codes) < set(engineering_supervisor.permission_codes)
        and engineering_manager.permission_codes
        == engineering_supervisor.permission_codes
        and "molding_sample:supervisor_review" not in engineer.permission_codes
        and "molding_sample:manager_review" not in engineer.permission_codes
        and MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE not in engineer.permission_codes
        and MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE
        in engineering_supervisor.permission_codes
        and MOLDING_SAMPLE_DISPATCH_PERMISSION_CODE
        in engineering_manager.permission_codes
    ):
        raise RuntimeError("工程师、主管、经理的审核与分派继承关系无效")

    sales_business = definitions_by_id["position_sales_business"]
    sales_supervisor = definitions_by_id["position_sales_supervisor"]
    sales_manager = definitions_by_id["position_sales_manager"]
    if not all(
        definition.scope_mode == CROSS_FACTORY_READ_SCOPE
        for definition in (sales_business, sales_supervisor, sales_manager)
    ):
        raise RuntimeError("业务部内置职位必须跨厂查看、本厂操作")
    if not (
        set(sales_business.permission_codes) < set(sales_supervisor.permission_codes)
        and sales_manager.permission_codes == sales_supervisor.permission_codes
    ):
        raise RuntimeError("业务、主管、经理的审核继承关系无效")

    molding_clerk = definitions_by_id["position_molding_clerk"]
    molding_supervisor = definitions_by_id["position_molding_supervisor"]
    molding_manager = definitions_by_id["position_molding_manager"]
    if not (
        molding_clerk.scope_mode == CROSS_FACTORY_READ_SCOPE
        and molding_clerk.permission_codes == MOLDING_CLERK_PERMISSION_CODES
        and molding_supervisor.scope_mode == CROSS_FACTORY_OPERATE_SCOPE
        and molding_manager.scope_mode == CROSS_FACTORY_OPERATE_SCOPE
        and molding_supervisor.permission_codes == MOLDING_SUPERVISOR_PERMISSION_CODES
        and molding_manager.permission_codes == MOLDING_SUPERVISOR_PERMISSION_CODES
    ):
        raise RuntimeError("啤机文员、主管、经理的生产任务权限关系无效")

    warehouse_positions = (
        definitions_by_id["position_warehouse_manager"],
        definitions_by_id["position_warehouse_supervisor"],
        definitions_by_id["position_warehouse_keeper"],
    )
    if not all(
        "molding_sample:raw_material_write" in definition.permission_codes
        for definition in warehouse_positions
    ):
        raise RuntimeError("仓库内置职位必须可维护原料资料")
    if not all(
        definition.permission_codes == WAREHOUSE_PERMISSION_CODES
        and definition.scope_mode == (
            CROSS_FACTORY_OPERATE_SCOPE
            if definition.role_id == "position_warehouse_manager"
            else OWN_FACTORY_SCOPE
        )
        for definition in warehouse_positions
    ):
        raise RuntimeError("仓库经理必须跨厂操作，主管和仓管保留本厂仓库权限")

    qc_inspector = definitions_by_id["position_qc_inspector"]
    qc_supervisor = definitions_by_id["position_qc_supervisor"]
    qc_manager = definitions_by_id["position_qc_manager"]
    if not (
        qc_inspector.scope_mode == OWN_FACTORY_SCOPE
        and qc_supervisor.scope_mode == OWN_FACTORY_SCOPE
        and qc_manager.scope_mode == OWN_FACTORY_SCOPE
        and qc_inspector.permission_codes == QC_INSPECTION_OPERATOR_PERMISSION_CODES
        and qc_supervisor.permission_codes == QC_INSPECTION_SUPERVISOR_PERMISSION_CODES
        and qc_manager.permission_codes == QC_INSPECTION_SUPERVISOR_PERMISSION_CODES
        and set(qc_inspector.permission_codes) < set(qc_supervisor.permission_codes)
        and "qc_inspection:group_summary" not in qc_manager.permission_codes
    ):
        raise RuntimeError("QC 检验员、主管和经理的本厂权限关系无效")


validate_system_position_definitions()


def get_system_position(role_id: str) -> SystemPositionDefinition | None:
    return SYSTEM_POSITION_BY_ROLE_ID.get(role_id)


def is_system_position(role_id: str) -> bool:
    return role_id in SYSTEM_POSITION_BY_ROLE_ID


def recommend_system_position_role_id(position: str, department: str) -> str:
    normalized = position.strip().lower()
    is_manager = "经理" in position or "manager" in normalized
    is_supervisor = "主管" in position or "supervisor" in normalized

    if department == "management":
        return "position_general_manager"
    if department == "engineering":
        return (
            "position_engineering_manager"
            if is_manager
            else "position_engineering_supervisor"
            if is_supervisor
            else "position_engineering_engineer"
        )
    if department == "sales-business":
        return (
            "position_sales_manager"
            if is_manager
            else "position_sales_supervisor"
            if is_supervisor
            else "position_sales_business"
        )
    if department == "production":
        prefix = (
            "painting"
            if "喷油" in position
            else "molding"
            if "啤机" in position
            else "production"
        )
        suffix = "manager" if is_manager else "supervisor" if is_supervisor else "clerk"
        return f"position_{prefix}_{suffix}"
    if department == "three-d-printing":
        return (
            "position_3d_manager"
            if is_manager
            else "position_3d_supervisor"
            if is_supervisor
            else "position_3d_operator"
        )
    if department == "pmc-warehouse":
        return (
            "position_warehouse_manager"
            if is_manager
            else "position_warehouse_supervisor"
            if is_supervisor
            else "position_warehouse_keeper"
        )
    if department == "qa":
        return (
            "position_qa_manager"
            if is_manager
            else "position_qa_supervisor"
            if is_supervisor
            else "position_qa_clerk"
        )
    if department == "qc":
        return (
            "position_qc_manager"
            if is_manager
            else "position_qc_supervisor"
            if is_supervisor
            else "position_qc_inspector"
        )
    if department == "carton":
        if "外部" in position:
            return "position_external_carton_warehouse_keeper"
        return (
            "position_carton_manager"
            if is_manager
            else "position_carton_supervisor"
            if is_supervisor
            else "position_carton_warehouse_keeper"
        )
    return ""
