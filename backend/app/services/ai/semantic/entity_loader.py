from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.injection_scheduling_execution import InjectionSchedulingOrder
from app.models.internal_quote import InternalQuote
from app.schemas.ai.context import AISelectedEntityInput, AIServerSelectedEntity
from app.services.auth import AuthContext, authorization_decision
from app.services.injection_scheduling import SCHEDULING_DEPARTMENTS
from app.services.internal_quote import ALL_QUOTE_DEPARTMENTS


class AISelectedEntityValidationError(ValueError):
    pass


def _require_permission(
    user: AuthContext,
    permission: str,
    factory_id: str,
    departments: tuple[str, ...],
) -> None:
    if not any(
        authorization_decision(user, permission, factory_id, department)[0]
        for department in departments
    ):
        raise AISelectedEntityValidationError("selected entity is unauthorized")


def _load_scheduling_order(
    db: Session,
    selected: AISelectedEntityInput,
    user: AuthContext,
    factory_id: str,
) -> AIServerSelectedEntity:
    row = db.execute(
        select(
            InjectionSchedulingOrder.id,
            InjectionSchedulingOrder.factory_id,
            InjectionSchedulingOrder.revision,
            InjectionSchedulingOrder.order_no,
            InjectionSchedulingOrder.item_no,
        ).where(InjectionSchedulingOrder.id == selected.id)
    ).mappings().one_or_none()
    if (
        row is None
        or str(row["factory_id"]) != factory_id
        or int(row["revision"]) != selected.revision
    ):
        raise AISelectedEntityValidationError("selected entity is missing or stale")
    _require_permission(
        user,
        "injection_scheduling:read",
        factory_id,
        tuple(SCHEDULING_DEPARTMENTS),
    )
    item_no = str(row["item_no"] or "").strip()
    label = str(row["order_no"] or selected.id)
    if item_no:
        label = f"{label} / {item_no}"
    return AIServerSelectedEntity(
        type="scheduling_backlog_order",
        id=str(row["id"]),
        revision=int(row["revision"]),
        display_label=label,
    )


def _load_internal_quote(
    db: Session,
    selected: AISelectedEntityInput,
    user: AuthContext,
    factory_id: str,
) -> AIServerSelectedEntity:
    row = db.execute(
        select(
            InternalQuote.id,
            InternalQuote.factory_id,
            InternalQuote.header_revision,
            InternalQuote.quote_no,
        ).where(InternalQuote.id == selected.id)
    ).mappings().one_or_none()
    if (
        row is None
        or str(row["factory_id"]) != factory_id
        or int(row["header_revision"]) != selected.revision
    ):
        raise AISelectedEntityValidationError("selected entity is missing or stale")
    _require_permission(
        user,
        "internal_quote:read",
        factory_id,
        tuple(ALL_QUOTE_DEPARTMENTS),
    )
    return AIServerSelectedEntity(
        type="internal_quote",
        id=str(row["id"]),
        revision=int(row["header_revision"]),
        display_label=str(row["quote_no"] or selected.id),
    )


def load_selected_entity(
    db: Session,
    selected: AISelectedEntityInput,
    *,
    user: AuthContext,
    verified_factory_id: str,
    verified_module_id: str,
) -> AIServerSelectedEntity:
    if (
        selected.type == "scheduling_backlog_order"
        and verified_module_id == "injection-scheduling"
    ):
        return _load_scheduling_order(db, selected, user, verified_factory_id)
    if selected.type == "internal_quote" and verified_module_id == "internal-quote":
        return _load_internal_quote(db, selected, user, verified_factory_id)
    raise AISelectedEntityValidationError("selected entity type does not match page")
