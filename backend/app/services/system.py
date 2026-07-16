import json
import logging
import secrets

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import (
    AuthAuthorizationEvent,
    AuthPermission,
    AuthPermissionMetadata,
    AuthRegistrationRequest,
    AuthRole,
    AuthRoleBindingMetadata,
    AuthRoleMetadata,
    AuthRolePermission,
    AuthSession,
    AuthUser,
    AuthUserAuthorizationRevision,
    AuthUserPermissionOverride,
    AuthUserRole,
    EmployeeProfile,
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
from app.services.auth import (
    ALLOWED_DEPARTMENTS,
    ALLOWED_FACTORY_IDS,
    AuthContext,
    add_auth_audit,
    build_auth_context,
    can,
    make_password_hash,
    now_text,
    time_window_is_active,
    validate_password_characters,
)
from app.services.iam_scope import OWN_FACTORY_SCOPE
from app.services.permission_scope_policy import role_scope_policy, scope_is_applicable
from app.services.system_positions import (
    SPECIAL_SYSTEM_ROLE_CODES,
    SYSTEM_POSITION_DEFINITIONS,
    get_system_position,
    recommend_system_position_role_id,
)


logger = logging.getLogger(__name__)


def is_superadmin(current_user: AuthContext) -> bool:
    return any(
        grant.role_code == "admin"
        and grant.factory_id == "*"
        and grant.department in {"*", "system"}
        for grant in current_user.grants
    )


def ensure_user_manage(
    db: Session,
    current_user: AuthContext,
    factory_id: str | None = None,
    department: str | None = None,
) -> None:
    allowed = (
        can(current_user, "system:user_manage", factory_id, department)
        if factory_id
        else "system:user_manage" in current_user.permissions
    )
    if allowed:
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


def target_user_scopes(db: Session, user_id: str) -> set[tuple[str, str]]:
    scopes: set[tuple[str, str]] = set()
    profile = db.get(EmployeeProfile, user_id)
    if profile and profile.primary_factory_id and profile.primary_department:
        scopes.add((profile.primary_factory_id, profile.primary_department))
    bindings = db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user_id)).all()
    for binding in bindings:
        metadata = db.get(AuthRoleBindingMetadata, binding.id)
        if metadata and (
            metadata.state != "active"
            or not time_window_is_active(metadata.valid_from, metadata.valid_until)
        ):
            continue
        scopes.add((binding.factory_id, binding.department))
    return scopes


def can_manage_target_user(db: Session, current_user: AuthContext, user_id: str) -> bool:
    if is_superadmin(current_user):
        return True
    scopes = target_user_scopes(db, user_id)
    return bool(scopes) and all(
        can(current_user, "system:user_manage", factory_id, department)
        for factory_id, department in scopes
    )


def ensure_manage_target_user(db: Session, current_user: AuthContext, user_id: str) -> None:
    ensure_user_manage(db, current_user)
    if can_manage_target_user(db, current_user, user_id):
        return
    raise HTTPException(status_code=403, detail="只能管理授权范围内的用户")


def role_is_high_risk(db: Session, role_id: str) -> bool:
    role = db.get(AuthRole, role_id)
    if role is None:
        return True
    if role.code == "admin":
        return True
    role_metadata = db.get(AuthRoleMetadata, role_id)
    if (
        get_system_position(role_id) is not None
        and role_metadata is not None
        and role_metadata.scope_mode != OWN_FACTORY_SCOPE
    ):
        return True
    permission_ids = {
        item.permission_id
        for item in db.scalars(
            select(AuthRolePermission).where(AuthRolePermission.role_id == role_id)
        ).all()
    }
    if not permission_ids:
        return False
    metadata = {
        item.permission_id: item
        for item in db.scalars(
            select(AuthPermissionMetadata).where(AuthPermissionMetadata.permission_id.in_(permission_ids))
        ).all()
    }
    permissions = db.scalars(select(AuthPermission).where(AuthPermission.id.in_(permission_ids))).all()
    return any(
        permission.code.startswith("system:")
        or metadata.get(permission.id) is None
        or metadata[permission.id].risk_level == "high"
        for permission in permissions
    )


def lock_role_metadata(db: Session, role_ids: list[str]) -> None:
    normalized_role_ids = sorted({role_id.strip() for role_id in role_ids if role_id.strip()})
    if not normalized_role_ids:
        return
    # Role-template writes take the same lock before changing permission rows.
    # A deterministic order also prevents multi-role registration approvals from
    # deadlocking with one another.
    locked_metadata = db.scalars(role_metadata_for_update_statement(normalized_role_ids)).all()
    if len(locked_metadata) != len(normalized_role_ids):
        raise HTTPException(
            status_code=409,
            detail="角色权限模板元数据缺失，请重启服务完成初始化后重试",
        )


def role_metadata_for_update_statement(role_ids: list[str]):
    return (
        select(AuthRoleMetadata)
        .where(AuthRoleMetadata.role_id.in_(role_ids))
        .order_by(AuthRoleMetadata.role_id)
        .with_for_update()
    )


def lock_authorization_revision(
    db: Session,
    user_id: str,
) -> AuthUserAuthorizationRevision:
    revision = db.scalar(authorization_revision_for_update_statement(user_id))
    if revision is None:
        # Startup seeding and registration both create this sidecar. Failing
        # closed avoids racing another transaction that might also try to create
        # the same primary-key row without holding a lock.
        raise HTTPException(
            status_code=409,
            detail="用户授权版本元数据缺失，请重启服务完成初始化后重试",
        )
    return revision


def authorization_revision_for_update_statement(user_id: str):
    return (
        select(AuthUserAuthorizationRevision)
        .where(AuthUserAuthorizationRevision.user_id == user_id)
        .with_for_update()
    )


def increment_authorization_revision(
    revision: AuthUserAuthorizationRevision,
    now: str,
) -> int:
    revision.revision += 1
    revision.updated_at = now
    return revision.revision


def recommend_role_ids(registration_request: AuthRegistrationRequest) -> list[str]:
    role_id = recommend_system_position_role_id(
        registration_request.position,
        registration_request.department,
    )
    return [role_id] if role_id else []


def list_roles(db: Session, current_user: AuthContext) -> list[RoleOut]:
    ensure_user_manage(db, current_user)
    roles = db.scalars(select(AuthRole).order_by(AuthRole.id)).all()
    return [role_to_out(db, role) for role in roles]


def list_system_positions(db: Session, current_user: AuthContext) -> list[RoleOut]:
    ensure_user_manage(db, current_user)
    roles_by_id = {
        role.id: role
        for role in db.scalars(
            select(AuthRole).where(
                AuthRole.id.in_([item.role_id for item in SYSTEM_POSITION_DEFINITIONS])
            )
        ).all()
    }
    return [
        role_to_out(db, roles_by_id[item.role_id])
        for item in SYSTEM_POSITION_DEFINITIONS
        if item.role_id in roles_by_id
    ]


def list_registration_requests(
    db: Session,
    current_user: AuthContext,
    status: str = "pending",
) -> list[RegistrationRequestOut]:
    ensure_user_manage(db, current_user)
    query = select(AuthRegistrationRequest).order_by(AuthRegistrationRequest.created_at.desc())
    if status:
        query = query.where(AuthRegistrationRequest.status == status)

    return [
        registration_request_to_out(item)
        for item in db.scalars(query).all()
        if is_superadmin(current_user)
        or can(current_user, "system:user_manage", item.factory_id, item.department)
    ]


def approve_registration_request(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: RegistrationApproveRequest,
    request: Request | None = None,
) -> RegistrationRequestOut:
    if payload.system_position_role_id.strip() or payload.profile is not None:
        return approve_registration_with_system_position(
            db,
            current_user,
            request_id,
            payload,
            request=request,
        )

    ensure_user_manage(db, current_user)
    registration_request = load_registration_request(db, request_id)
    ensure_user_manage(
        db,
        current_user,
        registration_request.factory_id,
        registration_request.department,
    )
    if registration_request.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")
    original_position = registration_request.position.strip()
    approved_position = (payload.position if payload.position is not None else original_position).strip()
    if not approved_position:
        raise HTTPException(status_code=400, detail="请输入职位")
    if len(approved_position) > 128:
        raise HTTPException(status_code=400, detail="职位不能超过 128 个字符")
    if not payload.role_assignments:
        raise HTTPException(status_code=400, detail="请至少分配一个角色")

    role_assignments = expand_registration_role_assignments(
        db,
        current_user,
        payload.role_assignments,
    )

    user = db.get(AuthUser, registration_request.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="申请账号不存在")
    now = now_text()

    lock_role_metadata(db, [assignment.role_id for assignment in role_assignments])
    authorization_revision = lock_authorization_revision(db, user.id)

    for assignment in role_assignments:
        validate_role_assignment(db, assignment)
        if not is_superadmin(current_user):
            if not can(
                current_user,
                "system:user_manage",
                assignment.factory_id.strip(),
                assignment.department.strip(),
            ):
                raise HTTPException(status_code=403, detail="跨范围角色授权请由集团超级管理员直接操作")
            if role_is_high_risk(db, assignment.role_id.strip()):
                raise HTTPException(status_code=403, detail="管理员或高风险角色请由集团超级管理员直接操作")
        validate_role_assignment_scope(db, assignment)

    existing_user_roles = list(
        db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all()
    )
    active_assignment_keys: set[tuple[str, str, str]] = set()
    for existing_user_role in existing_user_roles:
        metadata = db.get(AuthRoleBindingMetadata, existing_user_role.id)
        if metadata is None or metadata.state == "active":
            active_assignment_keys.add(
                (
                    existing_user_role.role_id,
                    existing_user_role.factory_id,
                    existing_user_role.department,
                )
            )

    added_binding_ids: list[str] = []
    for assignment in role_assignments:
        assignment_key = (
            assignment.role_id.strip(),
            assignment.factory_id.strip(),
            assignment.department.strip(),
        )
        if assignment_key in active_assignment_keys:
            continue

        user_role_id = f"user-role-{secrets.token_hex(16)}"
        db.add(
            AuthUserRole(
                id=user_role_id,
                user_id=user.id,
                role_id=assignment_key[0],
                factory_id=assignment_key[1],
                department=assignment_key[2],
            )
        )
        # PostgreSQL enforces the metadata foreign key during flush. Persist the
        # parent binding inside the current transaction before adding sidecar
        # metadata; a later failure still rolls the whole approval back.
        db.flush()
        db.add(
            AuthRoleBindingMetadata(
                user_role_id=user_role_id,
                state="active",
                source_type="registration_default",
                source_id=registration_request.id,
                valid_from=now,
                valid_until="",
                reason=payload.review_comment.strip() or "注册审批默认授权",
                created_by_user_id=current_user.id,
                approved_by_user_id=current_user.id,
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        added_binding_ids.append(user_role_id)
        active_assignment_keys.add(assignment_key)

        db.add(
            AuthAuthorizationEvent(
                id=f"auth-event-{secrets.token_hex(16)}",
                actor_user_id=current_user.id,
                target_user_id=user.id,
                event_type="role_binding_add",
                target_type="role_binding",
                target_id=user_role_id,
                permission_id="",
                effect="allow",
                factory_id=assignment_key[1],
                department=assignment_key[2],
                before_json="{}",
                after_json=json.dumps(
                    {
                        "role_id": assignment_key[0],
                        "factory_id": assignment_key[1],
                        "department": assignment_key[2],
                        "source_type": "registration_default",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                reason=payload.review_comment.strip() or "注册审批默认授权",
                ip_address=request.client.host if request and request.client else "",
                user_agent=request.headers.get("user-agent", "") if request else "",
                access_request_id="",
                created_at=now,
            )
        )

    profile = db.get(EmployeeProfile, user.id)
    if profile is None:
        profile = EmployeeProfile(user_id=user.id, created_at=now)
        db.add(profile)
    profile.primary_factory_id = registration_request.factory_id
    profile.primary_department = registration_request.department
    registration_request.position = approved_position
    profile.position = approved_position
    profile.phone = registration_request.phone
    profile.email = registration_request.email
    profile.confirmation_status = "confirmed"
    profile.source_registration_request_id = registration_request.id
    profile.updated_at = now

    user.status = "active"
    user.updated_at = now
    registration_request.status = "approved"
    registration_request.reviewer_user_id = current_user.id
    registration_request.review_comment = payload.review_comment.strip()
    registration_request.reviewed_at = now
    registration_request.updated_at = now
    if added_binding_ids:
        increment_authorization_revision(authorization_revision, now)
    mark_registration_notifications_handled(db, registration_request.id, now)
    add_auth_audit(
        db,
        "registration_approved",
        username=user.username,
        user_id=user.id,
        detail=(
            "审批通过；"
            f"职位：{original_position}"
            f"{' -> ' + approved_position if approved_position != original_position else ''}；"
            f"角色：{','.join(item.role_id for item in role_assignments)}"
        ),
        request=request,
    )
    db.commit()
    return registration_request_to_out(registration_request)


def approve_registration_with_system_position(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: RegistrationApproveRequest,
    request: Request | None = None,
) -> RegistrationRequestOut:
    ensure_user_manage(db, current_user)
    registration_request = load_registration_request(db, request_id)
    ensure_user_manage(
        db,
        current_user,
        registration_request.factory_id,
        registration_request.department,
    )
    if registration_request.status != "pending":
        raise HTTPException(status_code=400, detail="该申请已处理")
    if payload.profile is None:
        raise HTTPException(status_code=400, detail="请核对注册资料")

    display_name = payload.profile.display_name.strip()
    phone = payload.profile.phone.strip()
    email = payload.profile.email.strip()
    factory_id = payload.profile.factory_id.strip()
    department = payload.profile.department.strip()
    position = payload.profile.position.strip()
    role_id = payload.system_position_role_id.strip()

    if not display_name:
        raise HTTPException(status_code=400, detail="请输入姓名")
    if not phone and not email:
        raise HTTPException(status_code=400, detail="手机或邮箱至少填写一项")
    if factory_id not in ALLOWED_FACTORY_IDS:
        raise HTTPException(status_code=400, detail="请选择有效厂区")
    if department not in ALLOWED_DEPARTMENTS:
        raise HTTPException(status_code=400, detail="请选择有效部门")
    if not position:
        raise HTTPException(status_code=400, detail="请输入职位")
    if len(position) > 128:
        raise HTTPException(status_code=400, detail="职位不能超过 128 个字符")

    ensure_user_manage(db, current_user, factory_id, department)
    system_position = get_system_position(role_id)
    role = db.get(AuthRole, role_id)
    if system_position is None or role is None:
        raise HTTPException(status_code=400, detail="请选择系统内置权限职位")
    permission_department = system_position.department
    if permission_department != department:
        ensure_user_manage(db, current_user, factory_id, permission_department)
    assignment = RoleAssignmentRequest(
        role_id=role.id,
        factory_id=factory_id,
        department=permission_department,
    )
    validate_role_assignment_scope(db, assignment)

    user = db.get(AuthUser, registration_request.user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="申请账号不存在")

    now = now_text()
    lock_role_metadata(db, [role.id])
    authorization_revision = lock_authorization_revision(db, user.id)
    if not is_superadmin(current_user) and role_is_high_risk(db, role.id):
        raise HTTPException(status_code=403, detail="高风险内置职位请由集团超级管理员审批")

    original_profile = {
        "display_name": registration_request.display_name,
        "phone": registration_request.phone,
        "email": registration_request.email,
        "factory_id": registration_request.factory_id,
        "department": registration_request.department,
        "position": registration_request.position,
    }
    roles_by_id = {
        item.id: item
        for item in db.scalars(select(AuthRole)).all()
    }
    existing_bindings = list(
        db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all()
    )
    for binding in existing_bindings:
        metadata = db.get(AuthRoleBindingMetadata, binding.id)
        if metadata is not None and metadata.state != "active":
            continue
        bound_role = roles_by_id.get(binding.role_id)
        if bound_role and bound_role.code in SPECIAL_SYSTEM_ROLE_CODES:
            continue
        if metadata is None:
            metadata = AuthRoleBindingMetadata(
                user_role_id=binding.id,
                state="active",
                source_type="legacy_import",
                source_id="",
                valid_from="",
                valid_until="",
                reason="",
                created_at=now,
                updated_at=now,
            )
            db.add(metadata)
        metadata.state = "revoked"
        metadata.revoked_by_user_id = current_user.id
        metadata.revoked_at = now
        metadata.revoke_reason = "注册审批统一归类到内置权限职位"
        metadata.updated_at = now
        db.add(
            AuthAuthorizationEvent(
                id=f"auth-event-{secrets.token_hex(16)}",
                actor_user_id=current_user.id,
                target_user_id=user.id,
                event_type="role_binding_revoke",
                target_type="role_binding",
                target_id=binding.id,
                permission_id="",
                effect="",
                factory_id=binding.factory_id,
                department=binding.department,
                before_json=json.dumps(
                    {
                        "role_id": binding.role_id,
                        "factory_id": binding.factory_id,
                        "department": binding.department,
                        "state": "active",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                after_json=json.dumps({"state": "revoked"}, ensure_ascii=False, sort_keys=True),
                reason=payload.review_comment.strip() or "注册审批统一归类到内置权限职位",
                ip_address=request.client.host if request and request.client else "",
                user_agent=request.headers.get("user-agent", "") if request else "",
                access_request_id="",
                created_at=now,
            )
        )

    active_overrides = list(
        db.scalars(
            select(AuthUserPermissionOverride).where(
                AuthUserPermissionOverride.user_id == user.id,
                AuthUserPermissionOverride.status == "active",
            )
        ).all()
    )
    for override in active_overrides:
        override.status = "revoked"
        override.revoked_by_user_id = current_user.id
        override.revoked_at = now
        override.revoke_reason = "注册审批统一归类到内置权限职位"
        override.updated_at = now
        db.add(
            AuthAuthorizationEvent(
                id=f"auth-event-{secrets.token_hex(16)}",
                actor_user_id=current_user.id,
                target_user_id=user.id,
                event_type="permission_override_removed",
                target_type="permission_override",
                target_id=override.id,
                permission_id=override.permission_id,
                effect="inherit",
                factory_id=override.factory_id,
                department=override.department,
                before_json=json.dumps({"effect": override.effect}, ensure_ascii=False, sort_keys=True),
                after_json="{}",
                reason=payload.review_comment.strip() or "注册审批统一归类到内置权限职位",
                ip_address=request.client.host if request and request.client else "",
                user_agent=request.headers.get("user-agent", "") if request else "",
                access_request_id="",
                created_at=now,
            )
        )

    user_role_id = f"user-role-{secrets.token_hex(16)}"
    db.add(
        AuthUserRole(
            id=user_role_id,
            user_id=user.id,
            role_id=role.id,
            factory_id=factory_id,
            department=permission_department,
        )
    )
    db.flush()
    db.add(
        AuthRoleBindingMetadata(
            user_role_id=user_role_id,
            state="active",
            source_type="system_position",
            source_id=registration_request.id,
            valid_from=now,
            valid_until="",
            reason=payload.review_comment.strip() or "注册审批分配内置权限职位",
            created_by_user_id=current_user.id,
            approved_by_user_id=current_user.id,
            version=1,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AuthAuthorizationEvent(
            id=f"auth-event-{secrets.token_hex(16)}",
            actor_user_id=current_user.id,
            target_user_id=user.id,
            event_type="system_position_assign",
            target_type="role_binding",
            target_id=user_role_id,
            permission_id="",
            effect="allow",
            factory_id=factory_id,
            department=permission_department,
            before_json="{}",
            after_json=json.dumps(
                {
                    "role_id": role.id,
                    "role_name": role.name,
                    "factory_id": factory_id,
                    "department": permission_department,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            reason=payload.review_comment.strip() or "注册审批分配内置权限职位",
            ip_address=request.client.host if request and request.client else "",
            user_agent=request.headers.get("user-agent", "") if request else "",
            access_request_id="",
            created_at=now,
        )
    )

    profile = db.get(EmployeeProfile, user.id)
    if profile is None:
        profile = EmployeeProfile(user_id=user.id, created_at=now)
        db.add(profile)
    profile.primary_factory_id = factory_id
    profile.primary_department = department
    profile.position = position
    profile.phone = phone
    profile.email = email
    profile.confirmation_status = "confirmed"
    profile.source_registration_request_id = registration_request.id
    profile.updated_at = now

    user.display_name = display_name
    user.status = "active"
    user.updated_at = now
    registration_request.display_name = display_name
    registration_request.phone = phone
    registration_request.email = email
    registration_request.factory_id = factory_id
    registration_request.department = department
    registration_request.position = position
    registration_request.status = "approved"
    registration_request.reviewer_user_id = current_user.id
    registration_request.review_comment = payload.review_comment.strip()
    registration_request.reviewed_at = now
    registration_request.updated_at = now
    increment_authorization_revision(authorization_revision, now)
    mark_registration_notifications_handled(db, registration_request.id, now)
    add_auth_audit(
        db,
        "registration_approved",
        username=user.username,
        user_id=user.id,
        detail=(
            "审批通过；"
            f"资料：{json.dumps(original_profile, ensure_ascii=False, sort_keys=True)} -> "
            f"{json.dumps({'display_name': display_name, 'phone': phone, 'email': email, 'factory_id': factory_id, 'department': department, 'position': position}, ensure_ascii=False, sort_keys=True)}；"
            f"内置权限职位：{role.name}({role.id})"
        ),
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
    ensure_user_manage(
        db,
        current_user,
        registration_request.factory_id,
        registration_request.department,
    )
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
    return [
        user_to_out(db, user)
        for user in db.scalars(query).all()
        if can_manage_target_user(db, current_user, user.id)
    ]


def read_user_avatar(db: Session, current_user: AuthContext, user_id: str) -> bytes:
    ensure_manage_target_user(db, current_user, user_id)
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
    ensure_manage_target_user(db, current_user, user_id)
    next_status = payload.status.strip()
    if next_status not in {"active", "suspended"}:
        raise HTTPException(status_code=400, detail="账号状态只能设置为 active 或 suspended")

    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="账号不存在")

    if next_status == "suspended" and user.status == "active" and user_is_superadmin(db, user.id):
        active_admin_count = count_active_superadmins(db)
        if active_admin_count <= 1:
            raise HTTPException(status_code=400, detail="不能停用最后一个集团超级管理员")

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
    ensure_manage_target_user(db, current_user, user_id)
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
        if not can_access_notification(db, current_user, notification):
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
        if can_access_notification(db, current_user, notification)
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
    if not can_access_notification(db, current_user, notification):
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
    registration_request = db.scalar(registration_request_for_update_statement(request_id))
    if registration_request is None:
        raise HTTPException(status_code=404, detail="注册申请不存在")
    return registration_request


def registration_request_for_update_statement(request_id: str):
    return (
        select(AuthRegistrationRequest)
        .where(AuthRegistrationRequest.id == request_id)
        .with_for_update()
    )


def validate_role_assignment(db: Session, assignment: RoleAssignmentRequest) -> None:
    role_id = assignment.role_id.strip()
    if not role_id or db.get(AuthRole, role_id) is None:
        raise HTTPException(status_code=400, detail=f"角色不存在：{role_id}")
    if not assignment.factory_id.strip():
        raise HTTPException(status_code=400, detail="请选择授权厂区")
    if not assignment.department.strip():
        raise HTTPException(status_code=400, detail="请选择授权部门")


def validate_role_assignment_scope(db: Session, assignment: RoleAssignmentRequest) -> None:
    role = db.get(AuthRole, assignment.role_id.strip())
    if role is None:
        return
    policy = role_scope_policy(role.code)
    factory_id = assignment.factory_id.strip()
    department = assignment.department.strip()
    if scope_is_applicable(policy, factory_id, department):
        return
    guidance = policy.guidance or "该角色不适用于所选厂区和部门范围"
    raise HTTPException(
        status_code=400,
        detail=f"角色在当前范围不生效：{role.name}@{factory_id}/{department}；{guidance}",
    )


def expand_registration_role_assignments(
    db: Session,
    current_user: AuthContext,
    assignments: list[RoleAssignmentRequest],
) -> list[RoleAssignmentRequest]:
    """Apply the documented default engineer bundle without replacing existing grants."""
    expanded: list[RoleAssignmentRequest] = []
    seen: set[tuple[str, str, str]] = set()

    def append(assignment: RoleAssignmentRequest) -> None:
        key = (
            assignment.role_id.strip(),
            assignment.factory_id.strip(),
            assignment.department.strip(),
        )
        if key in seen:
            return
        seen.add(key)
        expanded.append(
            RoleAssignmentRequest(
                role_id=key[0],
                factory_id=key[1],
                department=key[2],
            )
        )

    for assignment in assignments:
        append(assignment)
        role = db.get(AuthRole, assignment.role_id.strip())
        if role is None or role.code != "engineer":
            continue
        if not is_superadmin(current_user):
            raise HTTPException(
                status_code=403,
                detail="工程师默认组合包含集团跨厂只读权限，请由集团超级管理员直接操作",
            )
        companion_roles = {
            "molding_production_observer": (
                assignment.factory_id.strip(),
                "production",
            ),
            "group_molding_readonly": ("*", "*"),
        }
        for role_code, (factory_id, department) in companion_roles.items():
            companion = db.scalar(select(AuthRole).where(AuthRole.code == role_code))
            if companion is None:
                raise HTTPException(
                    status_code=500,
                    detail=f"工程师默认授权角色尚未初始化：{role_code}",
                )
            append(
                RoleAssignmentRequest(
                    role_id=companion.id,
                    factory_id=factory_id,
                    department=department,
                )
            )

    return expanded


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


def notification_target_scope(
    db: Session,
    notification: SystemNotification,
) -> tuple[str, str] | None:
    target_factory_id = notification.target_factory_id.strip()
    target_department = notification.target_department.strip()
    payload = parse_payload(notification.payload_json)

    if notification.type == "password_reset":
        matched_user_id = str(payload.get("matched_user_id") or "").strip()
        if not matched_user_id:
            return None
        profile = db.get(EmployeeProfile, matched_user_id)
        if profile and profile.primary_factory_id and profile.primary_department:
            return profile.primary_factory_id, profile.primary_department
        if target_factory_id and target_department:
            return target_factory_id, target_department
        return None

    if target_factory_id and target_department:
        return target_factory_id, target_department

    if notification.type == "user_registration":
        registration_request_id = str(payload.get("registration_request_id") or "").strip()
        registration_request = (
            db.get(AuthRegistrationRequest, registration_request_id)
            if registration_request_id
            else None
        )
        if (
            registration_request
            and registration_request.factory_id
            and registration_request.department
        ):
            return registration_request.factory_id, registration_request.department

    return None


def can_access_notification(
    db: Session,
    current_user: AuthContext,
    notification: SystemNotification,
) -> bool:
    if notification.target_user_id and notification.target_user_id == current_user.id:
        return True
    if not notification.target_permission:
        return False
    if is_superadmin(current_user):
        return True

    target_scope = notification_target_scope(db, notification)
    payload = parse_payload(notification.payload_json)
    unmatched_password_reset = False
    if notification.type == "password_reset":
        matched_user_id = str(payload.get("matched_user_id") or "").strip()
        unmatched_password_reset = not matched_user_id or target_scope is None or target_scope[0] == "*"

    canonical_result = bool(target_scope) and not unmatched_password_reset and can(
        current_user,
        notification.target_permission,
        target_scope[0],
        target_scope[1],
    )
    if settings.authz_mode == "enforce":
        return canonical_result

    legacy_factory_id = notification.target_factory_id.strip()
    if not legacy_factory_id and target_scope:
        legacy_factory_id = target_scope[0]
    legacy_result = (
        can(current_user, notification.target_permission, legacy_factory_id)
        if legacy_factory_id and legacy_factory_id != "*"
        else notification.target_permission in current_user.permissions
    )
    if settings.authz_mode == "shadow" and legacy_result != canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s permission=%s notification=%s type=%s scope=%s/%s legacy=%s canonical=%s",
            current_user.id,
            notification.target_permission,
            notification.id,
            notification.type,
            target_scope[0] if target_scope else (legacy_factory_id or "*"),
            target_scope[1] if target_scope else "*",
            legacy_result,
            canonical_result,
        )
    return legacy_result


def user_has_permission(db: Session, user_id: str, permission_code: str) -> bool:
    user = db.get(AuthUser, user_id)
    if user is None or user.status != "active":
        return False
    return permission_code in build_auth_context(db, user).permissions


def count_active_admins(db: Session) -> int:
    return count_active_superadmins(db)


def user_is_superadmin(db: Session, user_id: str) -> bool:
    user = db.get(AuthUser, user_id)
    if user is None or user.status != "active":
        return False
    return is_superadmin(build_auth_context(db, user))


def count_active_superadmins(db: Session) -> int:
    active_users = db.scalars(select(AuthUser).where(AuthUser.status == "active")).all()
    return sum(1 for user in active_users if user_is_superadmin(db, user.id))


def role_to_out(db: Session, role: AuthRole) -> RoleOut:
    policy = role_scope_policy(role.code)
    position = get_system_position(role.id)
    permission_count = len(
        db.scalars(
            select(AuthRolePermission).where(AuthRolePermission.role_id == role.id)
        ).all()
    )
    return RoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        applicable_departments=list(policy.departments),
        requires_global_factory=policy.requires_global_factory,
        scope_guidance=policy.guidance,
        is_system_position=position is not None,
        position_department=position.department if position else "",
        position_department_name=position.department_name if position else "",
        position_sort_order=position.sort_order if position else 0,
        permission_count=permission_count,
    )


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
    all_user_roles = db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user.id)).all()
    user_roles = []
    for user_role in all_user_roles:
        metadata = db.get(AuthRoleBindingMetadata, user_role.id)
        if metadata and (
            metadata.state != "active"
            or not time_window_is_active(metadata.valid_from, metadata.valid_until)
        ):
            continue
        user_roles.append(user_role)
    roles_by_id = {
        role.id: role
        for role in db.scalars(select(AuthRole).where(AuthRole.id.in_([item.role_id for item in user_roles]))).all()
    } if user_roles else {}
    phone, email = latest_registration_contact(db, user.id)
    profile = db.get(EmployeeProfile, user.id)
    system_position_roles = sorted(
        [
            roles_by_id[item.role_id]
            for item in user_roles
            if item.role_id in roles_by_id and get_system_position(item.role_id) is not None
        ],
        key=lambda item: get_system_position(item.id).sort_order,
    )
    system_position_role = system_position_roles[0] if system_position_roles else None
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
        primary_factory_id=profile.primary_factory_id if profile else "",
        primary_department=profile.primary_department if profile else "",
        position=profile.position if profile else "",
        system_position_role_id=system_position_role.id if system_position_role else "",
        system_position_role_name=system_position_role.name if system_position_role else "",
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
        target_department=notification.target_department,
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
