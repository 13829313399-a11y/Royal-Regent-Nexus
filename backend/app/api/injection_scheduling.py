from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling import (
    InjectionSchedulingMachineCreate,
    InjectionSchedulingMachineListOut,
    InjectionSchedulingMachineOut,
    InjectionSchedulingMachineUpdate,
    InjectionSchedulingMoldCreate,
    InjectionSchedulingMoldListOut,
    InjectionSchedulingMoldOut,
    InjectionSchedulingMoldUpdate,
    InjectionSchedulingRuleSetOut,
    InjectionSchedulingRuleSetUpdate,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    create_machine,
    create_mold,
    current_rule_set,
    list_machines,
    list_molds,
    machine_out,
    mold_out,
    require_injection_scheduling_factory,
    rule_set_out,
    update_machine,
    update_mold,
    update_rule_set,
)

router = APIRouter(
    prefix="/api/injection-scheduling",
    tags=["injection-scheduling"],
)


def _ensure_scheduling_permission(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(user, permission, factory_id, department)
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        permission,
        factory_id,
        SCHEDULING_DEPARTMENTS[0],
    )
    return factory_id


@router.get("/machines", response_model=InjectionSchedulingMachineListOut)
def get_machines(
    factory_id: str,
    search: str = Query(default="", max_length=128),
    status: str = Query(default="", max_length=32),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_scheduling_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return InjectionSchedulingMachineListOut(
        factory_id=factory_id,
        items=[
            machine_out(record)
            for record in list_machines(
                db,
                factory_id,
                search=search,
                status=status,
            )
        ],
    )


@router.post(
    "/machines",
    response_model=InjectionSchedulingMachineOut,
    status_code=201,
)
def post_machine(
    payload: InjectionSchedulingMachineCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:manage_master",
        payload.factory_id,
    )
    return machine_out(create_machine(db, payload, current_user))


@router.put(
    "/machines/{machine_id}",
    response_model=InjectionSchedulingMachineOut,
)
def put_machine(
    machine_id: str,
    payload: InjectionSchedulingMachineUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:manage_master",
        payload.factory_id,
    )
    return machine_out(update_machine(db, machine_id, payload, current_user))


@router.get("/molds", response_model=InjectionSchedulingMoldListOut)
def get_molds(
    factory_id: str,
    search: str = Query(default="", max_length=128),
    status: str = Query(default="", max_length=32),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_scheduling_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return InjectionSchedulingMoldListOut(
        factory_id=factory_id,
        items=[
            mold_out(record)
            for record in list_molds(
                db,
                factory_id,
                search=search,
                status=status,
            )
        ],
    )


@router.post(
    "/molds",
    response_model=InjectionSchedulingMoldOut,
    status_code=201,
)
def post_mold(
    payload: InjectionSchedulingMoldCreate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:manage_master",
        payload.factory_id,
    )
    return mold_out(create_mold(db, payload, current_user))


@router.put("/molds/{mold_id}", response_model=InjectionSchedulingMoldOut)
def put_mold(
    mold_id: str,
    payload: InjectionSchedulingMoldUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:manage_master",
        payload.factory_id,
    )
    return mold_out(update_mold(db, mold_id, payload, current_user))


@router.get("/rules/current", response_model=InjectionSchedulingRuleSetOut)
def get_current_rules(
    factory_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    factory_id = _ensure_scheduling_permission(
        db, current_user, "injection_scheduling:read", factory_id
    )
    return rule_set_out(current_rule_set(db, factory_id))


@router.put("/rules/current", response_model=InjectionSchedulingRuleSetOut)
def put_current_rules(
    payload: InjectionSchedulingRuleSetUpdate,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    _ensure_scheduling_permission(
        db,
        current_user,
        "injection_scheduling:manage_rules",
        payload.factory_id,
    )
    return rule_set_out(update_rule_set(db, payload, current_user))
