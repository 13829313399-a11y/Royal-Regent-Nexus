from dataclasses import dataclass

from app.services.system_positions import SYSTEM_POSITION_DEFINITIONS


@dataclass(frozen=True)
class ScopePolicy:
    departments: tuple[str, ...] = ()
    requires_global_factory: bool = False
    guidance: str = ""


ENGINEERING_DEPARTMENTS = ("engineering",)
PRODUCTION_DEPARTMENTS = ("production", "molding")
WAREHOUSE_DEPARTMENTS = ("pmc-warehouse", "warehouse")
MANAGEMENT_DEPARTMENTS = ("management",)
INTERNAL_QUOTE_SECTION_DEPARTMENTS = {
    "sales": ("sales-business",),
    "engineering": ENGINEERING_DEPARTMENTS,
    "electronic": ("electronic",),
    "molding": PRODUCTION_DEPARTMENTS,
    "painting": ("production", "painting"),
    "slush": ("slush",),
    "sewing": ("sewing",),
    "hair": ("hair",),
    "assembly": ("assembly",),
}
INTERNAL_QUOTE_ALL_DEPARTMENTS = tuple(
    dict.fromkeys(
        department
        for departments in INTERNAL_QUOTE_SECTION_DEPARTMENTS.values()
        for department in departments
    )
)
SHARED_MOLDING_DEPARTMENTS = (
    *ENGINEERING_DEPARTMENTS,
    *PRODUCTION_DEPARTMENTS,
    *WAREHOUSE_DEPARTMENTS,
    *MANAGEMENT_DEPARTMENTS,
)
INJECTION_SCHEDULING_DEPARTMENTS = (
    *PRODUCTION_DEPARTMENTS,
    *WAREHOUSE_DEPARTMENTS,
    *MANAGEMENT_DEPARTMENTS,
)


MOLDING_PERMISSION_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    "molding_sample:read": ScopePolicy(
        SHARED_MOLDING_DEPARTMENTS,
        guidance="在工程、生产/啤机、PMC/仓库或管理范围生效",
    ),
    "molding_sample:export": ScopePolicy(
        SHARED_MOLDING_DEPARTMENTS,
        guidance="在啤办相关部门范围生效；跨厂只读仍禁止导出",
    ),
    "molding_sample:create": ScopePolicy(
        ENGINEERING_DEPARTMENTS,
        guidance="仅在工程部或全部部门范围生效",
    ),
    "molding_sample:edit_draft": ScopePolicy(
        (*ENGINEERING_DEPARTMENTS, *MANAGEMENT_DEPARTMENTS),
        guidance="仅在工程部、总务或全部部门范围生效",
    ),
    "molding_sample:delete_draft": ScopePolicy(
        (*ENGINEERING_DEPARTMENTS, *MANAGEMENT_DEPARTMENTS),
        guidance="仅在工程部、总务或全部部门范围生效",
    ),
    "molding_sample:supervisor_review": ScopePolicy(
        ENGINEERING_DEPARTMENTS,
        guidance="仅工程主管在工程部范围使用",
    ),
    "molding_sample:manager_review": ScopePolicy(
        MANAGEMENT_DEPARTMENTS,
        guidance="仅总务或全部部门范围生效",
    ),
    "molding_sample:dispatch": ScopePolicy(
        (*ENGINEERING_DEPARTMENTS, *MANAGEMENT_DEPARTMENTS),
        guidance="仅工程部、总务或全部部门范围可分派啤办生产任务",
    ),
    "molding_sample:raw_material_write": ScopePolicy(
        (*ENGINEERING_DEPARTMENTS, *WAREHOUSE_DEPARTMENTS),
        guidance="仅工程部、PMC/仓库或全部部门范围生效",
    ),
    "molding_sample:warehouse_requisition": ScopePolicy(
        WAREHOUSE_DEPARTMENTS,
        guidance="仅 PMC/仓库范围生效",
    ),
    "molding_sample:inventory_issue": ScopePolicy(
        WAREHOUSE_DEPARTMENTS,
        guidance="仅 PMC/仓库范围生效",
    ),
    "molding_sample:production_read": ScopePolicy(
        PRODUCTION_DEPARTMENTS,
        guidance="自定义角色仅生产部范围生效；系统内置职位由固定模板获得全厂生产任务只读",
    ),
    "molding_sample:production_start": ScopePolicy(
        PRODUCTION_DEPARTMENTS,
        guidance="仅生产部（啤喷装）范围生效",
    ),
    "molding_sample:production_fillback": ScopePolicy(
        PRODUCTION_DEPARTMENTS,
        guidance="仅生产部（啤喷装）范围生效",
    ),
    "molding_sample:production_complete": ScopePolicy(
        PRODUCTION_DEPARTMENTS,
        guidance="仅生产部（啤喷装）范围生效",
    ),
    "molding_sample:price_update": ScopePolicy(
        MANAGEMENT_DEPARTMENTS,
        guidance="仅总务或全部部门范围生效",
    ),
    "molding_sample:audit_read": ScopePolicy(
        MANAGEMENT_DEPARTMENTS,
        guidance="读取集团敏感操作审计，仅总务或全部部门范围生效",
    ),
    "molding_sample:notification_read": ScopePolicy(
        SHARED_MOLDING_DEPARTMENTS,
        guidance="按通知目标部门在对应范围生效",
    ),
    "molding_sample:cross_factory_read": ScopePolicy(
        ("*",),
        requires_global_factory=True,
        guidance="必须配置在全部厂区 / 全部部门范围；外厂仅查看且默认隐藏成本",
    ),
    "molding_sample:cross_factory_cost_read": ScopePolicy(
        ("*",),
        requires_global_factory=True,
        guidance="必须配置在全部厂区 / 全部部门范围，并同时拥有跨厂查看权限",
    ),
}

INTERNAL_QUOTE_PERMISSION_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    "internal_quote:read": ScopePolicy(INTERNAL_QUOTE_ALL_DEPARTMENTS),
    "internal_quote:create": ScopePolicy(("sales-business", "engineering")),
    "internal_quote:clone": ScopePolicy(("sales-business", "engineering")),
    "internal_quote:header_edit": ScopePolicy(("sales-business",)),
    "internal_quote:summary_read": ScopePolicy(INTERNAL_QUOTE_ALL_DEPARTMENTS),
    "internal_quote:timeline_read": ScopePolicy(INTERNAL_QUOTE_ALL_DEPARTMENTS),
    "internal_quote:archive": ScopePolicy(("sales-business",)),
    "internal_quote:baseline_read": ScopePolicy(("sales-business",)),
    "internal_quote:baseline_manage": ScopePolicy(("sales-business",)),
    "internal_quote:customer_manage": ScopePolicy(
        ("sales-business", "engineering"),
        guidance="仅本厂业务主管、业务经理、工程主管或工程经理可维护内部报价客户资料",
    ),
    "internal_quote:reference_manage": ScopePolicy(("sales-business", "engineering")),
    "internal_quote:export": ScopePolicy(("sales-business",)),
    "internal_quote:final_submit": ScopePolicy(("sales-business",)),
    "internal_quote:final_approve": ScopePolicy(("sales-business",)),
    "internal_quote:self_review": ScopePolicy(
        ("sales-business",),
        guidance="仅允许获授权业务人员审核本人创建且由本人负责的内部报价",
    ),
    "customer_price:read": ScopePolicy(("sales-business",)),
    "customer_price:import_internal_quote": ScopePolicy(("sales-business",)),
    "customer_price:export_customer_quote": ScopePolicy(("sales-business",)),
    "customer_price:compare": ScopePolicy(("sales-business",)),
    "customer_order:read": ScopePolicy(
        ("sales-business",),
        guidance="仅在业务部范围查看客户订单与排期数据",
    ),
    "customer_order:export": ScopePolicy(
        ("sales-business",),
        guidance="仅在业务部范围确认订单并导出客户排期",
    ),
    **{
        f"internal_quote:{section_code}_{action}": ScopePolicy(departments)
        for section_code, departments in INTERNAL_QUOTE_SECTION_DEPARTMENTS.items()
        for action in ("edit", "review")
    },
}

INJECTION_SCHEDULING_PERMISSION_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    permission_code: ScopePolicy(
        INJECTION_SCHEDULING_DEPARTMENTS,
        guidance="仅在注塑排产相关生产、PMC/仓库或管理范围生效",
    )
    for permission_code in (
        "injection_scheduling:read",
        "injection_scheduling:import",
        "injection_scheduling:edit",
        "injection_scheduling:report",
        "injection_scheduling:publish",
        "injection_scheduling:rollback",
        "injection_scheduling:manage_master",
        "injection_scheduling:manage_rules",
        "injection_scheduling:manage_import_profiles",
        "injection_scheduling:propose_import_profiles",
        "injection_scheduling:export",
        "shared_mold:read",
        "shared_mold:propose",
        "shared_mold:review",
        "shared_mold:manage",
        "shared_mold:approve",
        "factory_mold:manage",
        "factory_mold_asset:manage",
        "factory_mold_capability:manage",
        "shared_mold_price:read",
        "shared_mold_price:propose",
        "shared_mold_price:write",
        "shared_mold_price:approve",
        "shared_mold_price:manage",
    )
}

QC_INSPECTION_PERMISSION_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    permission_code: ScopePolicy(
        ("qc",),
        guidance="仅在 QC 部和当前厂区范围生效",
    )
    for permission_code in (
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
    )
}
QC_INSPECTION_PERMISSION_SCOPE_POLICIES["qc_inspection:group_summary"] = ScopePolicy(
    ("*",),
    requires_global_factory=True,
    guidance="集团汇总必须单独绑定到全部厂区 / 全部部门范围",
)

CARTON_MARK_PERMISSION_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    "carton_mark:read": ScopePolicy(
        (*WAREHOUSE_DEPARTMENTS, "carton", "qa", "qc"),
        guidance="纸箱部维护源文件；QA 旧入口和 QC 现场核验入口可按本厂查看",
    ),
    "carton_mark:template_upload": ScopePolicy(
        (*WAREHOUSE_DEPARTMENTS, "carton"),
        guidance="仅纸箱部或 PMC/仓管范围可上传 Excel、打印 PDF 并核对",
    ),
    "carton_mark:photo_upload": ScopePolicy(
        ("qa", "qc"),
        guidance="QA 旧入口和 QC 部可上传现场箱唛照片",
    ),
    "carton_mark:review": ScopePolicy(
        ("qa", "qc"),
        guidance="QA 旧入口和 QC 部可复核打印 PDF 与现场照片",
    ),
}

ROLE_SCOPE_POLICIES: dict[str, ScopePolicy] = {
    "admin": ScopePolicy(
        ("*",),
        requires_global_factory=True,
        guidance="受保护的集团超级管理员角色必须绑定到全部厂区 / 全部部门",
    ),
    "group_molding_readonly": ScopePolicy(
        ("*",),
        requires_global_factory=True,
        guidance="必须绑定到全部厂区 / 全部部门，外厂只读且默认隐藏成本",
    ),
    "engineer": ScopePolicy(ENGINEERING_DEPARTMENTS, guidance="仅适用于工程部范围"),
    "engineering_supervisor": ScopePolicy(
        ENGINEERING_DEPARTMENTS, guidance="仅适用于工程部范围"
    ),
    "manager": ScopePolicy(MANAGEMENT_DEPARTMENTS, guidance="仅适用于总务范围"),
    "warehouse_keeper": ScopePolicy(
        WAREHOUSE_DEPARTMENTS, guidance="仅适用于 PMC/仓库范围"
    ),
    "carton_warehouse_keeper": ScopePolicy(
        WAREHOUSE_DEPARTMENTS, guidance="仅适用于 PMC/仓库范围"
    ),
    "qa_inspector": ScopePolicy(("qa",), guidance="仅适用于品质部范围"),
    "molding_clerk": ScopePolicy(
        PRODUCTION_DEPARTMENTS, guidance="仅适用于生产部（啤喷装）范围"
    ),
    "molding_production_observer": ScopePolicy(
        PRODUCTION_DEPARTMENTS,
        guidance="仅适用于生产部（啤喷装）范围，只读查看生产任务和进度",
    ),
    "molding_operator": ScopePolicy(
        PRODUCTION_DEPARTMENTS, guidance="仅适用于生产部（啤喷装）范围"
    ),
    "molding_supervisor": ScopePolicy(
        PRODUCTION_DEPARTMENTS, guidance="仅适用于生产部（啤喷装）范围"
    ),
    "sales_customer_owner": ScopePolicy(
        ("sales-business",), guidance="仅适用于营业部范围"
    ),
    "sales_customer_supervisor": ScopePolicy(
        ("sales-business",), guidance="仅适用于营业部范围"
    ),
}

ROLE_SCOPE_POLICIES.update(
    {
        item.role_id: ScopePolicy(
            (item.department,),
            guidance=f"仅适用于{item.department_name}范围",
        )
        for item in SYSTEM_POSITION_DEFINITIONS
    }
)


def permission_scope_policy(permission_code: str) -> ScopePolicy:
    return MOLDING_PERMISSION_SCOPE_POLICIES.get(
        permission_code,
        INJECTION_SCHEDULING_PERMISSION_SCOPE_POLICIES.get(
            permission_code,
            QC_INSPECTION_PERMISSION_SCOPE_POLICIES.get(
                permission_code,
                CARTON_MARK_PERMISSION_SCOPE_POLICIES.get(
                    permission_code,
                    INTERNAL_QUOTE_PERMISSION_SCOPE_POLICIES.get(
                        permission_code,
                        ScopePolicy(),
                    ),
                ),
            ),
        ),
    )


def role_scope_policy(role_code: str) -> ScopePolicy:
    return ROLE_SCOPE_POLICIES.get(role_code, ScopePolicy())


def scope_is_applicable(policy: ScopePolicy, factory_id: str, department: str) -> bool:
    if policy.requires_global_factory and (factory_id != "*" or department != "*"):
        return False
    if not policy.departments or department == "*":
        return True
    return department in policy.departments
