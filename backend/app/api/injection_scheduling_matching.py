from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_matching import (
    InjectionSchedulingMatchEvaluate,
    InjectionSchedulingMatchEvaluationOut,
    InjectionSchedulingSuggestionConfirm,
    InjectionSchedulingSuggestionOut,
)
from app.services.auth import (
    AuthContext,
    ensure_permission_in_scope,
    get_current_user,
    has_permission_in_scope,
)
from app.services.injection_scheduling import (
    SCHEDULING_DEPARTMENTS,
    require_injection_scheduling_factory,
)
from app.services.injection_scheduling_matching import (
    confirm_suggestion,
    evaluate_order_matches,
)

router = APIRouter(
    prefix="/api/injection-scheduling",
    tags=["injection-scheduling"],
)

DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _ensure_permission(
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


@router.post(
    "/matches/evaluate",
    response_model=InjectionSchedulingMatchEvaluationOut,
)
def post_match_evaluate(
    payload: InjectionSchedulingMatchEvaluate,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db,
        current_user,
        "injection_scheduling:read",
        payload.factory_id,
    )
    return evaluate_order_matches(
        db,
        factory_id=factory_id,
        order_id=payload.order_id,
        machine_ids=payload.machine_ids,
        allow_scheduled=payload.allow_scheduled,
    )


@router.post(
    "/plans/{plan_id}/suggest",
    response_model=InjectionSchedulingSuggestionOut,
)
def post_confirm_suggestion(
    plan_id: str,
    payload: InjectionSchedulingSuggestionConfirm,
    db: DbSession,
    current_user: CurrentUser,
):
    factory_id = _ensure_permission(
        db,
        current_user,
        "injection_scheduling:edit",
        payload.factory_id,
    )
    evaluation = evaluate_order_matches(
        db,
        factory_id=factory_id,
        order_id=payload.order_id,
        machine_ids=[payload.machine_id],
    )
    match = evaluation.results[0]
    if match.decision == "REVIEW_REQUIRED":
        _ensure_permission(
            db,
            current_user,
            "injection_scheduling:publish",
            factory_id,
        )
    plan, audit_sequence = confirm_suggestion(
        db,
        plan_id=plan_id,
        payload=payload,
        match=match,
        user=current_user,
    )
    return InjectionSchedulingSuggestionOut(
        plan=plan,
        match=match,
        audit_sequence=audit_sequence,
    )
