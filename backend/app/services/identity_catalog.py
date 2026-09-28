from sqlalchemy import select
from app.models.auth import AuthIamState
from app.models.identity import IamOrgDepartment, IamOrgUnit
from app.services.identity_resolver import stamp

FACTORIES = {"huakang-a": "华康A", "huakang-b": "华康B", "huakang-c": "华康C", "huakang-d": "华康D", "huaxing": "华兴", "huadeng": "华登"}
DEPARTMENTS = {"assembly": "装配部", "electronic": "电子部", "engineering": "工程部", "management": "总务",
               "molding": "啤机部", "painting": "喷油部", "pmc-warehouse": "PMC仓库", "production": "生产部",
               "qa": "QA部", "qc": "QC部", "carton": "纸箱部", "sales-business": "业务部", "sewing": "车缝部",
               "hair": "植发部", "slush": "搪胶部", "three-d-printing": "3D打印部", "warehouse": "仓管部"}


def seed_identity_catalog(db):
    # Never update existing statuses/revisions; startup cannot reactivate a node.
    if db.get(AuthIamState, "identity_mutation_lock") is None:
        db.add(AuthIamState(key="identity_mutation_lock", value_json="{}", updated_at=stamp()))
    if db.get(IamOrgUnit, "group") is None:
        db.add(IamOrgUnit(id="group", name="集团", kind="group"))
        db.flush()
    for key, name in {**FACTORIES, "group-management": "集团总务"}.items():
        if db.get(IamOrgUnit, key) is None:
            db.add(IamOrgUnit(id=key, name=name, kind="factory" if key in FACTORIES else "functional_unit",
                             parent_id="group", legacy_factory_id=key if key in FACTORIES else ""))
            db.flush()
        for department in DEPARTMENTS if key in FACTORIES else ["management"]:
            if db.get(IamOrgDepartment, (key, department)) is None:
                db.add(IamOrgDepartment(org_unit_id=key, department_code=department))
    db.flush()


def catalog(db):
    from app.core.config import settings
    return {"organizations": [{"id": o.id, "name": o.name, "kind": o.kind, "parent_id": o.parent_id,
                                "factory_id": o.legacy_factory_id, "status": o.status, "revision": o.revision,
                                "departments": [{"code": d.department_code, "name": DEPARTMENTS.get(d.department_code, d.department_code),
                                                 "revision": d.revision} for d in db.scalars(select(IamOrgDepartment).where(
                                                     IamOrgDepartment.org_unit_id == o.id, IamOrgDepartment.status == "active"))]}
                               for o in db.scalars(select(IamOrgUnit).order_by(IamOrgUnit.id))],
            "writes_enabled": settings.iam_identity_writes_enabled and settings.authz_writes_enabled and settings.authz_mode == "enforce",
            "scheduling_enabled": settings.iam_identity_scheduling_enabled, "authz_mode": settings.authz_mode}
