from dataclasses import dataclass


@dataclass(frozen=True)
class SystemPositionDefinition:
    role_id: str
    name: str
    department: str
    department_name: str
    sort_order: int
    description: str
    permission_profile: str = ""


SYSTEM_POSITION_DEFINITIONS: tuple[SystemPositionDefinition, ...] = (
    SystemPositionDefinition(
        "position_general_manager",
        "总经理",
        "management",
        "总务",
        100,
        "集团或厂区经营管理；当前先继承已实现的经理审批能力，后续按模块继续完善",
        "manager",
    ),
    SystemPositionDefinition(
        "position_engineering_manager",
        "经理",
        "engineering",
        "工程部",
        200,
        "工程部管理与审核；权限以后统一在该内置职位模板维护",
        "engineering_supervisor",
    ),
    SystemPositionDefinition(
        "position_engineering_supervisor",
        "主管",
        "engineering",
        "工程部",
        210,
        "工程主管审核与工程资料协同",
        "engineering_supervisor",
    ),
    SystemPositionDefinition(
        "position_engineering_engineer",
        "工程师",
        "engineering",
        "工程部",
        220,
        "工程开单、草稿维护和工程通知",
        "engineer",
    ),
    SystemPositionDefinition(
        "position_sales_manager",
        "经理",
        "sales-business",
        "业务部",
        300,
        "业务报价与客户协同管理",
        "sales_customer_supervisor",
    ),
    SystemPositionDefinition(
        "position_sales_supervisor",
        "主管",
        "sales-business",
        "业务部",
        310,
        "业务报价复核与客户协同",
        "sales_customer_supervisor",
    ),
    SystemPositionDefinition(
        "position_sales_business",
        "业务",
        "sales-business",
        "业务部",
        320,
        "客户报价转换和内部报价协同",
        "sales_customer_owner",
    ),
    SystemPositionDefinition(
        "position_production_manager",
        "生产经理",
        "production",
        "生产部（啤喷装）",
        400,
        "生产任务统筹；后续按生产模块继续完善",
        "molding_supervisor",
    ),
    SystemPositionDefinition(
        "position_production_supervisor",
        "生产主管",
        "production",
        "生产部（啤喷装）",
        410,
        "生产任务管理与回填协同",
        "molding_supervisor",
    ),
    SystemPositionDefinition(
        "position_production_clerk",
        "生产文员",
        "production",
        "生产部（啤喷装）",
        420,
        "生产任务接收和资料回填",
        "molding_clerk",
    ),
    SystemPositionDefinition(
        "position_painting_manager",
        "喷油经理",
        "production",
        "生产部（啤喷装）",
        430,
        "喷油业务管理；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_painting_supervisor",
        "喷油主管",
        "production",
        "生产部（啤喷装）",
        440,
        "喷油现场管理；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_painting_clerk",
        "喷油文员",
        "production",
        "生产部（啤喷装）",
        450,
        "喷油资料协同；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_molding_manager",
        "啤机经理",
        "production",
        "生产部（啤喷装）",
        460,
        "啤机生产任务统筹和排产管理",
        "molding_supervisor",
    ),
    SystemPositionDefinition(
        "position_molding_supervisor",
        "啤机主管",
        "production",
        "生产部（啤喷装）",
        470,
        "啤机生产任务管理和排产导入",
        "molding_supervisor",
    ),
    SystemPositionDefinition(
        "position_molding_clerk",
        "啤机文员",
        "production",
        "生产部（啤喷装）",
        480,
        "啤办任务接收、开始、生产回填和完成",
        "molding_clerk",
    ),
    SystemPositionDefinition(
        "position_warehouse_manager",
        "经理",
        "pmc-warehouse",
        "仓库",
        500,
        "仓库领料、发料与库存管理",
        "warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_warehouse_supervisor",
        "主管",
        "pmc-warehouse",
        "仓库",
        510,
        "仓库领料、发料与库存管理",
        "warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_warehouse_keeper",
        "仓管",
        "pmc-warehouse",
        "仓库",
        520,
        "仓库领料、发料与库存管理",
        "warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_qa_manager",
        "经理",
        "qa",
        "QA部",
        600,
        "QA 箱唛检验管理与复核",
        "qa_inspector",
    ),
    SystemPositionDefinition(
        "position_qa_supervisor",
        "主管",
        "qa",
        "QA部",
        610,
        "QA 箱唛检验管理与复核",
        "qa_inspector",
    ),
    SystemPositionDefinition(
        "position_qa_clerk",
        "文员",
        "qa",
        "QA部",
        620,
        "QA 箱唛资料查看与实拍上传",
        "qa_clerk",
    ),
    SystemPositionDefinition(
        "position_qc_manager",
        "经理",
        "qc",
        "QC部",
        700,
        "QC 检验管理；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_qc_supervisor",
        "主管",
        "qc",
        "QC部",
        710,
        "QC 检验管理；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_qc_inspector",
        "QC检验员",
        "qc",
        "QC部",
        720,
        "QC 检验执行；对应模块尚未完善，当前默认不授予业务权限",
    ),
    SystemPositionDefinition(
        "position_carton_manager",
        "经理",
        "carton",
        "纸箱部",
        800,
        "纸箱箱唛模板与仓务管理",
        "carton_warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_carton_supervisor",
        "主管",
        "carton",
        "纸箱部",
        810,
        "纸箱箱唛模板与仓务管理",
        "carton_warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_carton_warehouse_keeper",
        "纸箱仓管",
        "carton",
        "纸箱部",
        820,
        "纸箱箱唛 PDF 模板维护",
        "carton_warehouse_keeper",
    ),
    SystemPositionDefinition(
        "position_external_carton_warehouse_keeper",
        "外部纸箱仓管",
        "carton",
        "纸箱部",
        830,
        "外部纸箱仓务与箱唛查看",
        "carton_external",
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
        prefix = "painting" if "喷油" in position else "molding" if "啤机" in position else "production"
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
