import json

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import (
    AuthPermission,
    AuthRegistrationRequest,
    AuthRole,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserRole,
    SystemNotification,
)
from app.schemas.system import (
    RegistrationApproveRequest,
    RegistrationRejectRequest,
    RegistrationRequestOut,
    RoleAssignmentRequest,
    RoleOut,
    SystemNotificationOut,
    SystemNotificationUpdateRequest,
    UserPasswordResetRequest,
    UserOut,
    UserRoleAssignmentOut,
    UserStatusUpdateRequest,
)
from app.services.auth import AuthContext, add_auth_audit, has_factory_scope, make_password_hash, now_text, validate_password_characters


def ensure_user_manage(db: Session, current_user: AuthContext) -> None:
    if "system:user_manage" in current_user.permissions:
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=current_user.username,
        user_id=current_user.id,
        detail="缺少权限：system:user_manage",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无系统用户管理权限")


def recommend_role_ids(registration_request: AuthRegistrationRequest) -> list[str]:
    position = registration_request.position.strip().lower()
    department = registration_request.department

    if "经理" in registration_request.position:
        return ["manager"]
    if "主管" in registration_request.position or "supervisor" in position:
        if department == "engineering":
            return ["engineering_supervisor"]
        if department == "sales-business":
            return ["sales_customer_supervisor"]

    department_defaults = {
        "engineering": "engineer",
        "pmc-warehouse": "carton_warehouse_keeper",
        "production": "molding_clerk",
        "qa": "qa_inspector",
        "sales-business": "sales_customer_owner",
    }
    role_id = department_defaults.get(department)
    return [role_id] if role_id else []


def list_roles(db: Session, current_user: AuthContext) -> list[RoleOut]:
    ensure_user_manage(db, current_user)
    roles = db.scalars(select(AuthRole).order_by(AuthRole.id)).all()
    return [role_to_out(role) for role in roles]


def list_registration_requests(
    db: Session,
    current_user: AuthContext,
    status: str = "pending",
) -> list[RegistrationRequestOut]:
    ensure_user_manage(db, current_user)
    query = select(AuthRegistrationRequest).order_by(AuthRegistrationRequest.created_at.desc())
    if status:
        query = query.where(AuthRegistrationRequest.status == status)

    return [registration_request_to_out(item) for item in db.scalars(query).all()]


def approve_registration_request(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: RegistrationApproveRequest,
    request: Request | None = None,
) -> RegistrationRequestOut:
    ensure_user_manage(db, current_user)
    registration_request = load_registration_request(db, request_id)
    if registration_request.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")
    if not payload.role_assignments:
        raise HTTPException(status_code=400, detail="请至少分配一个角色")

    user = db.get(AuthUser, registration_request.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="申请账号不存在")

    for assignment in payload.role_assignments:
        validate_role_assignment(db, assignment)

    for existing_user_role in db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all():
        db.delete(existing_user_role)

    for index, assignment in enumerate(payload.role_assignments, start=1):
        db.add(
            AuthUserRole(
                id=f"{user.id}:{assignment.role_id}:{assignment.factory_id}:{assignment.department}:{index}",
                user_id=user.id,
                role_id=assignment.role_id,
                factory_id=assignment.factory_id,
                department=assignment.department,
            )
        )

    now = now_text()
    user.status = "active"
    user.updated_at = now
    registration_request.status = "approved"
    registration_request.reviewer_user_id = current_user.id
    registration_request.review_comment = payload.review_comment.strip()
    registration_request.reviewed_at = now
    registration_request.updated_at = now
    mark_registration_notifications_handled(db, registration_request.id, now)
    add_auth_audit(
        db,
        "registration_approved",
        username=user.username,
        user_id=user.id,
        detail=f"审批通过；角色：{','.join(item.role_id for item in payload.role_assignments)}",
        request=request,
    )
    db.commit()
    return registration_request_to_out(registration_request)


def reject_registration_request(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: RegistrationRejectRequest,
    request: Request | None = None,
) -> RegistrationRequestOut:
    ensure_user_manage(db, current_user)
    registration_request = load_registration_request(db, request_id)
    if registration_request.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")
    if not payload.review_comment.strip():
        raise HTTPException(status_code=400, detail="请填写拒绝原因")

    user = db.get(AuthUser, registration_request.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="申请账号不存在")

    now = now_text()
    user.status = "rejected"
    user.updated_at = now
    registration_request.status = "rejected"
    registration_request.reviewer_user_id = current_user.id
    registration_request.review_comment = payload.review_comment.strip()
    registration_request.reviewed_at = now
    registration_request.updated_at = now
    mark_registration_notifications_handled(db, registration_request.id, now)
    add_auth_audit(
        db,
        "registration_rejected",
        username=user.username,
        user_id=user.id,
        detail=registration_request.review_comment,
        request=request,
    )
    db.commit()
    return registration_request_to_out(registration_request)


def list_users(db: Session, current_user: AuthContext, status: str = "") -> list[UserOut]:
    ensure_user_manage(db, current_user)
    query = select(AuthUser).order_by(AuthUser.created_at.desc(), AuthUser.username.asc())
    if status:
        query = query.where(AuthUser.status == status)
    return [user_to_out(db, user) for user in db.scalars(query).all()]


def read_user_avatar(db: Session, current_user: AuthContext, user_id: str) -> bytes:
    ensure_user_manage(db, current_user)
    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.avatar_png:
        raise HTTPException(status_code=404, detail="该用户尚未设置头像")
    return bytes(user.avatar_png)


def update_user_status(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: UserStatusUpdateRequest,
    request: Request | None = None,
) -> UserOut:
    ensure_user_manage(db, current_user)
    next_status = payload.status.strip()
    if next_status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="账号状态只能设置为 active 或 suspended")

    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    if next_status == "suspended" and user.status == "active" and user_has_permission(db, user.id, "system:user_manage"):
        active_admin_count = count_active_admins(db)
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="不能停用最后一个系统管理员")

    user.status = next_status
    user.updated_at = now_text()
    add_auth_audit(
        db,
        "user_status_updated",
        username=user.username,
        user_id=user.id,
        detail=f"账号状态改为：{next_status}",
        request=request,
    )
    db.commit()
    return user_to_out(db, user)


def reset_user_password(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: UserPasswordResetRequest,
    request: Request | None = None,
) -> UserOut:
    ensure_user_manage(db, current_user)
    temporary_password = payload.temporary_password.strip()
    if len(temporary_password) < 6:
        raise HTTPException(status_code=400, detail="临时密码至少需要 6 位")
    validate_password_characters(temporary_password)

    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")
    if user.status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="仅可重置正常或停用账号密码")

    now = now_text()
    salt, password_hash = make_password_hash(temporary_password)
    user.password_salt = salt
    user.password_hash = password_hash
    user.force_password_change = 1
    user.updated_at = now

    active_sessions = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user.id, AuthSession.status == "active")
    ).all()
    for session in active_sessions:
        session.status = "revoked"
        session.revoked_at = now

    notification_id = payload.notification_id.strip()
    if notification_id:
        notification = db.get(SystemNotification, notification_id)
        if notification is None:
            raise HTTPException(status_code=404, detail="通知不存在")
        if not can_access_notification(current_user, notification):
            raise HTTPException(status_code=403, detail="无权处理该通知")
        if notification.type != "password_reset":
            raise HTTPException(status_code=400, detail="该通知不是密码重置申请")
        notification.status = "handled"
        if not notification.read_at:
            notification.read_at = now
        notification.handled_at = now

    add_auth_audit(
        db,
        "password_reset_completed",
        username=user.username,
        user_id=user.id,
        detail=f"管理员 {current_user.username} 已重置临时密码",
        request=request,
    )
    db.commit()
    return user_to_out(db, user)


def list_system_notifications(db: Session, current_user: AuthContext) -> list[SystemNotificationOut]:
    notifications = db.scalars(select(SystemNotification).order_by(SystemNotification.created_at.desc())).all()
    return [
        notification_to_out(notification)
        for notification in notifications
        if can_access_notification(current_user, notification)
    ]


def update_system_notification(
    db: Session,
    current_user: AuthContext,
    notification_id: str,
    payload: SystemNotificationUpdateRequest,
) -> SystemNotificationOut:
    notification = db.get(SystemNotification, notification_id)
    if notification is None:
        raise HTTPException(status_code=404, detail="通知不存在")
    if not can_access_notification(current_user, notification):
        raise HTTPException(status_code=403, detail="无权处理该通知")

    status = payload.status.strip()
    if status not in {"read", "handled"}:
        raise HTTPException(status_code=400, detail="通知状态只能设置为 read 或 handled")

    now = now_text()
    notification.status = status
    if status in {"read", "handled"} and not notification.read_at:
        notification.read_at = now
    if status == "handled":
        notification.handled_at = now
    db.commit()
    return notification_to_out(notification)


def load_registration_request(db: Session, request_id: str) -> AuthRegistrationRequest:
    registration_request = db.get(AuthRegistrationRequest, request_id)
    if registration_request is None:
        raise HTTPException(status_code=404, detail="注册申请不存在")
    return registration_request


def validate_role_assignment(db: Session, assignment: RoleAssignmentRequest) -> None:
    role_id = assignment.role_id.strip()
    if not role_id or db.get(AuthRole, role_id) is None:
        raise HTTPException(status_code=400, detail=f"角色不存在：{role_id}")
    if not assignment.factory_id.strip():
        raise HTTPException(status_code=400, detail="请选择授权厂区")
    if not assignment.department.strip():
        raise HTTPException(status_code=400, detail="请选择授权部门")


def mark_registration_notifications_handled(db: Session, registration_request_id: str, handled_at: str) -> None:
    notifications = db.scalars(
        select(SystemNotification).where(SystemNotification.type == "user_registration")
    ).all()
    for notification in notifications:
        payload = parse_payload(notification.payload_json)
        if payload.get("registration_request_id") == registration_request_id:
            notification.status = "handled"
            if not notification.read_at:
                notification.read_at = handled_at
            notification.handled_at = handled_at


def can_access_notification(current_user: AuthContext, notification: SystemNotification) -> bool:
    if notification.target_user_id and notification.target_user_id == current_user.id:
        return True
    if notification.target_permission and notification.target_permission in current_user.permissions:
        return not notification.target_factory_id or has_factory_scope(current_user, notification.target_factory_id)
    return False


def user_has_permission(db: Session, user_id: str, permission_code: str) -> bool:
    user_roles = db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user_id)).all()
    role_ids = [user_role.role_id for user_role in user_roles]
    if not role_ids:
        return False

    permission = db.scalar(select(AuthPermission).where(AuthPermission.code == permission_code))
    if permission is None:
        return False

    role_permission = db.scalar(
        select(AuthRolePermission).where(
            AuthRolePermission.role_id.in_(role_ids),
            AuthRolePermission.permission_id == permission.id,
        )
    )
    return role_permission is not None


def count_active_admins(db: Session) -> int:
    active_users = db.scalars(select(AuthUser).where(AuthUser.status == "active")).all()
    return sum(1 for user in active_users if user_has_permission(db, user.id, "system:user_manage"))


def role_to_out(role: AuthRole) -> RoleOut:
    return RoleOut(id=role.id, code=role.code, name=role.name, description=role.description)


def registration_request_to_out(registration_request: AuthRegistrationRequest) -> RegistrationRequestOut:
    return RegistrationRequestOut(
        id=registration_request.id,
        user_id=registration_request.user_id,
        username=registration_request.username,
        display_name=registration_request.display_name,
        phone=registration_request.phone,
        email=registration_request.email,
        factory_id=registration_request.factory_id,
        department=registration_request.department,
        position=registration_request.position,
        status=registration_request.status,
        reviewer_user_id=registration_request.reviewer_user_id,
        review_comment=registration_request.review_comment,
        submitted_at=registration_request.submitted_at,
        reviewed_at=registration_request.reviewed_at,
        created_at=registration_request.created_at,
        updated_at=registration_request.updated_at,
        recommended_role_ids=recommend_role_ids(registration_request),
    )


def user_to_out(db: Session, user: AuthUser) -> UserOut:
    user_roles = db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all()
    roles_by_id = {
        role.id: role
        for role in db.scalars(select(AuthRole).where(AuthRole.id.in_([item.role_id for item in user_roles]))).all()
    } if user_roles else {}
    phone, email = latest_registration_contact(db, user.id)
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        phone=phone,
        email=email,
        status=user.status,
        force_password_change=bool(user.force_password_change),
        last_login_at=user.last_login_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
        avatar_url=(
            f"/api/system/users/{user.id}/avatar?v={user.avatar_version}"
            if user.avatar_png and user.avatar_version
            else ""
        ),
        roles=[
            UserRoleAssignmentOut(
                id=user_role.id,
                role_id=user_role.role_id,
                role_name=roles_by_id[user_role.role_id].name if user_role.role_id in roles_by_id else user_role.role_id,
                role_code=roles_by_id[user_role.role_id].code if user_role.role_id in roles_by_id else user_role.role_id,
                factory_id=user_role.factory_id,
                department=user_role.department,
            )
            for user_role in user_roles
        ],
    )


def latest_registration_contact(db: Session, user_id: str) -> tuple[str, str]:
    registration_request = db.scalar(
        select(AuthRegistrationRequest)
        .where(AuthRegistrationRequest.user_id == user_id)
        .order_by(AuthRegistrationRequest.updated_at.desc(), AuthRegistrationRequest.created_at.desc())
    )
    if registration_request is None:
        return "", ""
    return registration_request.phone, registration_request.email


def notification_to_out(notification: SystemNotification) -> SystemNotificationOut:
    return SystemNotificationOut(
        id=notification.id,
        target_user_id=notification.target_user_id,
        target_permission=notification.target_permission,
        target_factory_id=notification.target_factory_id,
        type=notification.type,
        title=notification.title,
        message=notification.message,
        payload=parse_payload(notification.payload_json),
        status=notification.status,
        created_at=notification.created_at,
        read_at=notification.read_at,
        handled_at=notification.handled_at,
    )


def parse_payload(payload_json: str) -> dict[str, object]:
    try:
        payload = json.loads(payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
