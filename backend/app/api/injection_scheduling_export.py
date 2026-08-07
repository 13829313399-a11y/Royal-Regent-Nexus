from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.injection_scheduling_export import InjectionSchedulingExportRequest
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
from app.services.injection_scheduling_export import export_plan_workbook

router = APIRouter(prefix="/api/injection-scheduling", tags=["injection-scheduling"])


def _ensure_export_permission(
    db: Session,
    user: AuthContext,
    factory_id: str,
) -> str:
    factory_id = require_injection_scheduling_factory(factory_id)
    if any(
        has_permission_in_scope(
            user,
            "injection_scheduling:export",
            factory_id,
            department,
        )
        for department in SCHEDULING_DEPARTMENTS
    ):
        return factory_id
    ensure_permission_in_scope(
        db,
        user,
        "injection_scheduling:export",
        factory_id,
        SCHEDULING_DEPARTMENTS[0],
    )
    return factory_id


@router.post("/plans/{plan_id}/exports")
def post_plan_export(
    plan_id: str,
    payload: InjectionSchedulingExportRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[AuthContext, Depends(get_current_user)],
):
    _ensure_export_permission(db, current_user, payload.factory_id)
    result = export_plan_workbook(
        db,
        plan_id=plan_id,
        payload=payload,
        user=current_user,
    )
    return Response(
        content=result.content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{result.file_name}"; '
                f"filename*=UTF-8''{quote(result.file_name)}"
            ),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Export-Audit-ID": result.audit_id,
            "X-Export-SHA256": result.file_sha256,
            "X-Export-Mode": result.export_mode,
            "X-Export-Profile-ID": result.profile_id or "",
            "X-Export-Profile-Revision": str(result.profile_revision),
            "X-Export-Renderer": result.renderer_code,
            "X-Export-Signing-Key-ID": result.signing_key_id,
            "X-Idempotent-Replay": str(result.idempotent_replay).lower(),
        },
    )
