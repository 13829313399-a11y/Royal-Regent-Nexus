import hashlib
import json
from dataclasses import dataclass

from app.services.iam_scope import (
    CROSS_FACTORY_OPERATE_SCOPE,
    CROSS_FACTORY_READ_SCOPE,
    OWN_FACTORY_SCOPE,
    ScopeMode,
    VALID_SCOPE_MODES,
)
from app.services.permission_codes import (
    APPLICATION_PERMISSION_CODES,
    BUSINESS_PERMISSION_CODES,
    SYSTEM_MANAGEMENT_PERMISSION_CODES,
)


SYSTEM_POSITION_DEFINITION_VERSION = "fixed-v2"


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
    "molding_sample:read",
    "molding_sample:cross_factory_read",
    "molding_sample:cross_factory_cost_read",
    "molding_sample:export",
    "molding_sample:create",
    "molding_sample:edit_draft",
    "molding_sample:delete_draft",
    "molding_sample:supervisor_review",
    "molding_sample:manager_review",
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
    "carton_mark:read",
    "carton_mark:template_upload",
    "carton_mark:photo_upload",
    "carton_mark:review",
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "injection_schedule:read",
    "injection_schedule:import",
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:header_edit",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:archive",
    "internal_quote:reference_manage",
    "internal_quote:export",
    "internal_quote:final_submit",
    "internal_quote:final_approve",
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
    "internal_quote:assembly_edit",
    "internal_quote:assembly_review",
)
GENERAL_MANAGER_PERMISSION_CODES = frozenset(_GENERAL_MANAGER_PERMISSION_CODE_LIST)
GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES: frozenset[str] = frozenset()

ENGINEER_PERMISSION_CODES = (
    "molding_sample:read",
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
    "internal_quote:reference_manage",
    "internal_quote:engineering_review",
)

SALES_SUPERVISOR_PERMISSION_CODES = (
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:header_edit",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:archive",
    "internal_quote:reference_manage",
    "internal_quote:export",
    "internal_quote:final_submit",
    "internal_quote:final_approve",
    "internal_quote:sales_edit",
    "internal_quote:sales_review",
)

SALES_BUSINESS_PERMISSION_CODES = (
    "customer_price:read",
    "customer_price:import_internal_quote",
    "customer_price:export_customer_quote",
    "customer_price:compare",
    "internal_quote:read",
    "internal_quote:create",
    "internal_quote:clone",
    "internal_quote:header_edit",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:export",
    "internal_quote:final_submit",
    "internal_quote:sales_edit",
)

PRODUCTION_SUPERVISOR_PERMISSION_CODES = (
    "molding_sample:read",
    "molding_sample:export",
    "molding_sample:production_read",
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:audit_read",
    "molding_sample:notification_read",
    "injection_schedule:read",
    "injection_schedule:import",
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:molding_edit",
    "internal_quote:molding_review",
)

PRODUCTION_CLERK_PERMISSION_CODES = (
    "molding_sample:read",
    "molding_sample:export",
    "molding_sample:production_read",
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:notification_read",
    "injection_schedule:read",
    "injection_schedule:import",
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "internal_quote:molding_edit",
)

# 啤机职位只操作“啤办生产任务单”。范围模式负责区分文员的
# “跨厂查看 / 本厂操作”和主管、经理的“跨厂操作”，避免把排产导入、
# 工程啤办导出或内部报价编辑一并扩大到外厂。
MOLDING_CLERK_PERMISSION_CODES = (
    "molding_sample:production_read",
    "molding_sample:production_start",
    "molding_sample:production_fillback",
    "molding_sample:production_complete",
    "molding_sample:notification_read",
)

MOLDING_SUPERVISOR_PERMISSION_CODES = MOLDING_CLERK_PERMISSION_CODES

WAREHOUSE_PERMISSION_CODES = (
    "molding_sample:read",
    "molding_sample:export",
    "molding_sample:raw_material_write",
    "molding_sample:warehouse_requisition",
    "molding_sample:inventory_issue",
    "molding_sample:notification_read",
)

QA_INSPECTOR_PERMISSION_CODES = (
    "carton_mark:read",
    "carton_mark:photo_upload",
    "carton_mark:review",
)
QA_CLERK_PERMISSION_CODES = (
    "carton_mark:read",
    "carton_mark:photo_upload",
)
CARTON_WAREHOUSE_PERMISSION_CODES = (
    "carton_mark:read",
    "carton_mark:template_upload",
)
CARTON_EXTERNAL_PERMISSION_CODES = ("carton_mark:read",)


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
        description="跨厂查看工程数据；本厂开单、维护、原料管理与主管审核",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=ENGINEERING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_engineering_supervisor",
        name="主管",
        department="engineering",
        department_name="工程部",
        sort_order=210,
        description="跨厂查看工程数据；本厂开单、维护、原料管理与审核驳回",
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
        description="业务报价与客户协同管理",
        permission_codes=SALES_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_sales_supervisor",
        name="主管",
        department="sales-business",
        department_name="业务部",
        sort_order=310,
        description="业务报价复核与客户协同",
        permission_codes=SALES_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_sales_business",
        name="业务",
        department="sales-business",
        department_name="业务部",
        sort_order=320,
        description="客户报价转换和内部报价协同",
        permission_codes=SALES_BUSINESS_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_manager",
        name="生产经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=400,
        description="生产任务统筹与啤机排产管理",
        permission_codes=PRODUCTION_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_supervisor",
        name="生产主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=410,
        description="生产任务管理与回填协同",
        permission_codes=PRODUCTION_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_production_clerk",
        name="生产文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=420,
        description="生产任务接收和资料回填",
        permission_codes=PRODUCTION_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_painting_manager",
        name="喷油经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=430,
        description="喷油业务管理；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_painting_supervisor",
        name="喷油主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=440,
        description="喷油现场管理；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_painting_clerk",
        name="喷油文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=450,
        description="喷油资料协同；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_molding_manager",
        name="啤机经理",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=460,
        description="跨厂查看并操作啤办生产任务；暂与啤机主管权限一致",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=MOLDING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_molding_supervisor",
        name="啤机主管",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=470,
        description="跨厂查看并操作啤办生产任务",
        scope_mode=CROSS_FACTORY_OPERATE_SCOPE,
        permission_codes=MOLDING_SUPERVISOR_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_molding_clerk",
        name="啤机文员",
        department="production",
        department_name="生产部（啤喷装）",
        sort_order=480,
        description="跨厂查看啤办生产任务；仅操作本厂任务，通知仅限本厂",
        scope_mode=CROSS_FACTORY_READ_SCOPE,
        permission_codes=MOLDING_CLERK_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_warehouse_manager",
        name="经理",
        department="pmc-warehouse",
        department_name="仓库",
        sort_order=500,
        description="仓库领料、发料与库存管理",
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
        description="QC 检验管理；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_qc_supervisor",
        name="主管",
        department="qc",
        department_name="QC部",
        sort_order=710,
        description="QC 检验管理；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_qc_inspector",
        name="QC检验员",
        department="qc",
        department_name="QC部",
        sort_order=720,
        description="QC 检验执行；对应模块尚未完善，当前不授予业务权限",
    ),
    SystemPositionDefinition(
        role_id="position_carton_manager",
        name="经理",
        department="carton",
        department_name="纸箱部",
        sort_order=800,
        description="纸箱箱唛模板与仓务管理",
        permission_codes=CARTON_WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_carton_supervisor",
        name="主管",
        department="carton",
        department_name="纸箱部",
        sort_order=810,
        description="纸箱箱唛模板与仓务管理",
        permission_codes=CARTON_WAREHOUSE_PERMISSION_CODES,
    ),
    SystemPositionDefinition(
        role_id="position_carton_warehouse_keeper",
        name="纸箱仓管",
        department="carton",
        department_name="纸箱部",
        sort_order=820,
        description="纸箱箱唛 PDF 模板维护",
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

    all_business_codes = set(BUSINESS_PERMISSION_CODES)
    decided_general_manager_codes = (
        GENERAL_MANAGER_PERMISSION_CODES
        | GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES
    )
    if GENERAL_MANAGER_PERMISSION_CODES & GENERAL_MANAGER_EXCLUDED_BUSINESS_PERMISSION_CODES:
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
    ):
        raise RuntimeError("工程师、主管、经理的审核继承关系无效")

    molding_clerk = definitions_by_id["position_molding_clerk"]
    molding_supervisor = definitions_by_id["position_molding_supervisor"]
    molding_manager = definitions_by_id["position_molding_manager"]
    if not (
        molding_clerk.scope_mode == CROSS_FACTORY_READ_SCOPE
        and molding_clerk.permission_codes == MOLDING_CLERK_PERMISSION_CODES
        and molding_supervisor.scope_mode == CROSS_FACTORY_OPERATE_SCOPE
        and molding_manager.scope_mode == CROSS_FACTORY_OPERATE_SCOPE
        and molding_supervisor.permission_codes == MOLDING_CLERK_PERMISSION_CODES
        and molding_manager.permission_codes == MOLDING_CLERK_PERMISSION_CODES
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
        raise RuntimeError("仓库内置职位必须可维护本厂原料资料")


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
