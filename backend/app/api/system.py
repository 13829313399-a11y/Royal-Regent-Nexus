from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.core.time import parse_business_timestamp
from app.db import get_db
from app.schemas.system import (
    RegistrationApproveRequest,
    RegistrationRejectRequest,
    RegistrationRequestOut,
    RoleOut,
    SystemNotificationOut,
    SystemNotificationUpdateRequest,
    UserPasswordResetRequest,
    UserOut,
    UserStatusUpdateRequest,
)
from app.services.auth import AuthContext, get_current_user
from app.services.system import (
    approve_registration_request,
    list_registration_requests,
    list_roles,
    list_system_positions,
    list_system_notifications,
    list_users,
    read_user_avatar,
    reject_registration_request,
    reset_user_password,
    update_system_notification,
    update_user_status,
)

router = APIRouter(prefix="/api/system")


@router.get("/notifications", response_model=list[SystemNotificationOut])
def notifications(
    changed_after: str | None = Query(default=None, max_length=64),
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    normalized_changed_after = None
    if changed_after:
        parsed_changed_after = parse_business_timestamp(changed_after)
        if parsed_changed_after is None:
            raise HTTPException(status_code=422, detail="通知增量游标格式无效")
        normalized_changed_after = parsed_changed_after.strftime("%Y-%m-%d %H:%M:%S")

    return list_system_notifications(db, current_user, changed_after=normalized_changed_after)


@router.patch("/notifications/{notification_id}", response_model=SystemNotificationOut)
def update_notification(
    notification_id: str,
    payload: SystemNotificationUpdateRequest,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_system_notification(db, current_user, notification_id, payload)


@router.get("/registration-requests", response_model=list[RegistrationRequestOut])
def registration_requests(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_registration_requests(db, current_user, status=status)


@router.post("/registration-requests/{request_id}/approve", response_model=RegistrationRequestOut)
def approve_registration(
    request_id: str,
    payload: RegistrationApproveRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return approve_registration_request(db, current_user, request_id, payload, request=request)


@router.post("/registration-requests/{request_id}/reject", response_model=RegistrationRequestOut)
def reject_registration(
    request_id: str,
    payload: RegistrationRejectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return reject_registration_request(db, current_user, request_id, payload, request=request)


@router.get("/users", response_model=list[UserOut])
def users(
    status: str = "",
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_users(db, current_user, status=status)


@router.get("/users/{user_id}/avatar")
def user_avatar(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return Response(
        content=read_user_avatar(db, current_user, user_id),
        media_type="image/png",
        headers={"Cache-Control": "private, no-store"},
    )


@router.patch("/users/{user_id}/status", response_model=UserOut)
def patch_user_status(
    user_id: str,
    payload: UserStatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return update_user_status(db, current_user, user_id, payload, request=request)


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: str,
    payload: UserPasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return reset_user_password(db, current_user, user_id, payload, request=request)


@router.get("/roles", response_model=list[RoleOut])
def roles(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_roles(db, current_user)


@router.get("/positions", response_model=list[RoleOut])
def system_positions(
    db: Session = Depends(get_db),
    current_user: AuthContext = Depends(get_current_user),
):
    return list_system_positions(db, current_user)
