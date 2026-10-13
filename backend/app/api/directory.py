from typing import Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.directory import (
    DirectoryHeartbeatResponse,
    DirectoryMembersResponse,
    DirectorySummaryResponse,
)
from app.services.auth import AuthContext, get_current_user
from app.services.internal_members import require_internal
from app.services.directory import (
    get_directory_summary,
    list_directory_members,
    read_directory_avatar,
    record_presence_heartbeat,
    directory_catalog,
    directory_member,
)

router = APIRouter(prefix="/api/directory", tags=["directory"])
AVATAR_CACHE_CONTROL = "private, max-age=86400, immutable"


def internal_viewer(user: AuthContext = Depends(get_current_user)):
    return require_internal(user)


@router.get("/summary", response_model=DirectorySummaryResponse)
def summary(
    db: Session = Depends(get_db),
    _current_user: AuthContext = Depends(internal_viewer),
):
    return get_directory_summary(db)


@router.get("/members", response_model=DirectoryMembersResponse)
def members(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=36, ge=1, le=50),
    q: str = Query(default="", max_length=64),
    presence: Literal["all", "online", "away", "offline"] = Query(default="all"),
    factory_id: str = Query(default="", max_length=64),
    department: str = Query(default="", max_length=64),
    org_unit_id: str = Query(default="", max_length=64),
    contacts_only: bool = False,
    db: Session = Depends(get_db),
    _current_user: AuthContext = Depends(internal_viewer),
):
    return list_directory_members(
        db,
        page=page,
        page_size=page_size,
        q=q,
        presence=presence,
        factory_id=factory_id,
        department=department,
        org_unit_id=org_unit_id,
        contacts_only=contacts_only,
        viewer=_current_user,
    )


@router.post("/presence/heartbeat", response_model=DirectoryHeartbeatResponse)
def heartbeat(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(internal_viewer),
):
    return record_presence_heartbeat(db, current_user)


@router.get("/members/{user_id}/avatar")
def member_avatar(
    user_id: str,
    if_none_match: str | None = Header(default=None),
    db: Session = Depends(get_db),
    _current_user: AuthContext = Depends(internal_viewer),
):
    content, etag = read_directory_avatar(db, user_id)
    headers = {
        "Cache-Control": AVATAR_CACHE_CONTROL,
        "ETag": etag,
    }
    validators = {
        item.strip() for item in (if_none_match or "").split(",") if item.strip()
    }
    if "*" in validators or etag in validators:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=content, media_type="image/png", headers=headers)


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), _current_user: AuthContext = Depends(internal_viewer)):
    return directory_catalog(db)


@router.get("/members/{user_id}")
def member(user_id: str, db: Session = Depends(get_db), current_user: AuthContext = Depends(internal_viewer)):
    return directory_member(db, current_user, user_id)
