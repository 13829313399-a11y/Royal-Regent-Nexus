from datetime import datetime
from typing import Literal
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db import get_db
from app.api.position_reviews import PositionRoute
from app.services.auth import AuthContext, get_current_user
from app.services import iam_workspace as workspace

router = APIRouter(prefix="/api/iam/workspace", route_class=PositionRoute)


@router.get("/tasks")
def tasks(page: int = Query(1, ge=1), page_size: int = Query(30, ge=1, le=100), q: str = Query("", max_length=128),
          kind: Literal["", "position-registration", "position", "registration", "password-reset", "identity-change"] = "",
          state: Literal["", "open", "actionable", "blocked", "waiting_employee", "scheduled", "closed"] = "open",
          org_unit_id: str = Query("", max_length=64), target_user_id: str = Query("", max_length=64),
          from_at: datetime | None = None, to_at: datetime | None = None,
          db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workspace.tasks(db, user, page=page, page_size=page_size, q=q, kind=kind, state=state,
        org_unit_id=org_unit_id, target_user_id=target_user_id, from_at=from_at, to_at=to_at)


@router.get("/password-resets/{request_id}")
def password_detail(request_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    return workspace.password_detail(db, user, request_id)


@router.get("/identity-changes/{request_id}")
def identity_detail(request_id: str, db: Session = Depends(get_db), user: AuthContext = Depends(get_current_user)):
    from app.services.identity_policy import fail
    from app.services.identity_resolver import utc_now
    from app.services.identity_changes import load_change, result_out
    if "system:user_manage" not in user.permissions:
        fail("FORBIDDEN", "无权查看高级任职资料", 403)
    if not any(r["source_id"] == request_id for r in workspace.Projection(db, user, utc_now()).changes()):
        fail("OUTSIDE_MANAGEABLE_SCOPE", "记录不存在或超出完整管理范围", 403)
    return result_out(load_change(db, request_id))
