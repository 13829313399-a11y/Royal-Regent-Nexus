import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import (
    AuthAccessRequest,
    AuthAccessRequestItem,
    AuthAuthorizationEvent,
    AuthAuthorizationPreview,
    AuthPermission,
    AuthPermissionMetadata,
    AuthRegistrationRequest,
    AuthRole,
    AuthRoleBindingMetadata,
    AuthRoleMetadata,
    AuthRolePermission,
    AuthUser,
    AuthUserAuthorizationRevision,
    AuthUserPermissionOverride,
    AuthUserRole,
    EmployeeProfile,
)
from app.schemas.iam import (
    AccessCommitRequest,
    AccessCommitResponse,
    AccessDiffOut,
    AccessPreviewResponse,
    AccessRequestCreate,
    AccessRequestDecision,
    AccessRequestOut,
    AuditEventOut,
    EffectiveAccessOut,
    EmployeeProfileOut,
    ManageableScopeOut,
    ManageableScopesResponse,
    PermissionOut,
    PermissionOverrideOut,
    RoleAccessCommitResponse,
    RoleAccessOut,
    RoleAccessPreviewRequest,
    RoleAccessPreviewResponse,
    RoleBindingOut,
    RolePermissionDiffOut,
    RoleSummaryOut,
    SystemPositionPreviewRequest,
    SystemPositionPreviewResponse,
    UserAccessOut,
    UserAccessPreviewRequest,
    UserAccessUserOut,
    UserSearchOut,
)
from app.services.auth import (
    ALLOWED_FACTORY_IDS,
    AuthContext,
    add_auth_audit,
    build_auth_context,
    can,
    now_text,
)
from app.services.iam_scope import (
    CROSS_FACTORY_OPERATE_SCOPE,
    CROSS_FACTORY_READ_SCOPE,
    OWN_FACTORY_SCOPE,
    READ_ACCESS_KIND,
    VALID_ACCESS_KINDS,
    VALID_SCOPE_MODES,
    default_permission_access_kind,
    scope_mode_expands_access,
)
from app.services.permission_scope_policy import (
    ScopePolicy,
    permission_scope_policy,
    role_scope_policy,
    scope_is_applicable,
)
from app.services.system_positions import (
    SPECIAL_SYSTEM_ROLE_CODES,
    SYSTEM_POSITION_DEFINITIONS,
    SYSTEM_POSITION_DEFINITION_VERSION,
    get_system_position,
    recommend_system_position_role_id,
    system_position_definition_hash,
)


PREVIEW_TTL_MINUTES = 5
IAM_MANAGE_PERMISSIONS = {
    "system:access_manage",
}
AUDIT_READ_PERMISSIONS = {"system:audit_read"}
FACTORY_NAMES = {
    "*": "全部厂区",
    "huakang-a": "华康 A 厂",
    "huakang-b": "华康 B 厂",
    "huakang-c": "华康 C 厂",
    "huakang-d": "华康 D 厂",
    "huadeng": "华登厂",
    "huaxing": "华兴厂",
}
DEPARTMENT_NAMES = {
    "*": "全部部门",
    "system": "系统管理",
    "engineering": "工程部",
    "management": "总务",
    "molding": "啤机部（历史部门代码）",
    "pmc-warehouse": "PMC / 仓库",
    "production": "生产部（啤喷装）",
    "qa": "品质部",
    "sales-business": "营业部",
    "warehouse": "仓库（历史部门代码）",
}
MODULE_NAMES = {
    "uv_ops": "UV 打印管理（华康 A）",
    "injection_scheduling": "注塑排产中枢",
    "molding_sample": "啤办管理",
    "carton_mark": "箱唛管理",
    "customer_price": "客户报价",
    "internal_quote": "内部报价台",
    "system": "系统管理",
}


def list_permissions(db: Session, current_user: AuthContext, status: str = "active") -> list[PermissionOut]:
    _ensure_iam_manager(db, current_user)
    _ensure_permission_catalog_reader(db, current_user)
    if status not in {"active", "inactive", "all"}:
        raise HTTPException(status_code=400, detail="权限状态仅支持 active、inactive 或 all")
    permissions = list(db.scalars(select(AuthPermission).order_by(AuthPermission.code)).all())
    metadata = {
        item.permission_id: item
        for item in db.scalars(select(AuthPermissionMetadata)).all()
    }
    result = [_permission_out(permission, metadata.get(permission.id)) for permission in permissions]
    if status != "all":
        result = [item for item in result if item.status == status]
    return sorted(result, key=lambda item: (item.sort_order, item.module_code, item.action, item.code))


def get_manageable_scopes(db: Session, current_user: AuthContext) -> ManageableScopesResponse:
    is_super_admin = _is_superadmin(db, current_user.id)
    scopes = _manager_scopes(db, current_user.id)
    return ManageableScopesResponse(
        is_super_admin=is_super_admin,
        can_manage_role_templates=is_super_admin,
        can_review_access_requests=is_super_admin,
        scopes=[
            ManageableScopeOut(
                factory_id=factory_id,
                factory_name=FACTORY_NAMES.get(factory_id, factory_id),
                department=department,
                department_name=DEPARTMENT_NAMES.get(department, department),
            )
            for factory_id, department in scopes
        ],
    )


def get_user_access(db: Session, current_user: AuthContext, user_id: str) -> UserAccessOut:
    _ensure_can_view_user_access(db, current_user, user_id)
    user = _load_user(db, user_id)
    profile = db.get(EmployeeProfile, user_id)
    registration = _latest_registration(db, user_id)
    phone = profile.phone if profile else (registration.phone if registration else "")
    email = profile.email if profile else (registration.email if registration else "")
    role_bindings = _role_bindings_out(db, user_id)
    overrides = _overrides_out(db, user_id)
    effective_binding_ids = {binding.id for binding in _active_bindings(db, user_id)}
    lifecycle_bindings = _lifecycle_active_bindings(db, user_id)
    active_system_positions = sorted(
        [
            binding
            for binding in role_bindings
            if binding.id in effective_binding_ids and get_system_position(binding.role_id) is not None
        ],
        key=lambda binding: get_system_position(binding.role_id).sort_order,
    )
    system_position_binding = active_system_positions[0] if active_system_positions else None
    legacy_role_count = sum(
        1
        for binding in role_bindings
        if binding.id in effective_binding_ids
        and get_system_position(binding.role_id) is None
        and binding.role_code not in SPECIAL_SYSTEM_ROLE_CODES
    )
    kept_system_position_binding_id = system_position_binding.id if system_position_binding else ""
    roles_by_id = {
        item.id: item
        for item in db.scalars(
            select(AuthRole).where(
                AuthRole.id.in_({binding.role_id for binding in lifecycle_bindings})
            )
        ).all()
    } if lifecycle_bindings else {}
    cleanup_role_count = sum(
        1
        for binding in lifecycle_bindings
        if binding.id != kept_system_position_binding_id
        and (
            roles_by_id.get(binding.role_id) is None
            or roles_by_id[binding.role_id].code not in SPECIAL_SYSTEM_ROLE_CODES
        )
    )
    lifecycle_overrides = _lifecycle_active_overrides(db, user_id)
    return UserAccessOut(
        user=UserAccessUserOut(
            id=user.id,
            username=user.username,
            display_name=user.display_name,
            status=user.status,
            phone=phone,
            email=email,
        ),
        profile=_profile_out(profile),
        authorization_version=_get_revision(db, user_id),
        role_bindings=role_bindings,
        overrides=overrides,
        effective_access=_effective_access_out(db, user_id),
        system_position_role_id=system_position_binding.role_id if system_position_binding else "",
        system_position_role_name=system_position_binding.role_name if system_position_binding else "",
        recommended_system_position_role_id=(
            recommend_system_position_role_id(profile.position, profile.primary_department)
            if profile
            else ""
        ),
        legacy_role_count=legacy_role_count,
        active_override_count=len(_active_overrides(db, user_id)),
        cleanup_role_count=cleanup_role_count,
        cleanup_override_count=len(lifecycle_overrides),
    )


def preview_user_access(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: UserAccessPreviewRequest,
) -> AccessPreviewResponse:
    _ensure_iam_manager(db, current_user)
    _load_user(db, user_id)
    reason = _required_reason(payload.reason)
    current_revision = _get_revision(db, user_id, for_update=True)
    if payload.base_revision != current_revision:
        raise HTTPException(status_code=409, detail="用户权限已变化，请刷新后重新预览")

    binding_inputs = payload.role_bindings or payload.binding_changes
    override_inputs = payload.overrides or payload.override_changes
    if payload.draft is not None:
        binding_inputs = payload.draft.role_bindings
        override_inputs = payload.draft.overrides
    if not binding_inputs and not override_inputs:
        raise HTTPException(status_code=400, detail="没有需要提交的权限变更")

    operations = _normalize_user_operations(
        db,
        user_id,
        binding_inputs,
        override_inputs,
        payload.scope.factory_id if payload.scope else "",
        payload.scope.department if payload.scope else "",
    )
    actor_scopes = _manager_scopes(db, current_user.id)
    is_super_admin = _is_superadmin(db, current_user.id)
    cross_scope = any(
        not _scope_is_managed(actor_scopes, item["factory_id"], item["department"])
        for item in operations
    )
    high_risk = any(item["risk_level"] == "high" for item in operations)
    if not is_super_admin and not actor_scopes:
        raise HTTPException(status_code=403, detail="无权限管理用户授权")
    if not is_super_admin and (cross_scope or high_risk):
        raise HTTPException(
            status_code=403,
            detail="跨范围或高风险权限变更请由集团超级管理员直接操作",
        )

    diffs = _preview_user_diffs(db, user_id, operations)
    raw_token, expires_at = _store_preview(
        db,
        actor_user_id=current_user.id,
        target_type="user",
        target_id=user_id,
        base_revision=current_revision,
        payload={"reason": reason, "operations": operations},
        summary={
            "requires_approval": False,
            "high_risk": high_risk,
            "cross_scope": cross_scope,
        },
    )
    db.commit()
    return AccessPreviewResponse(
        preview_token=raw_token,
        expires_at=expires_at,
        base_revision=current_revision,
        requires_approval=False,
        high_risk=high_risk,
        diffs=diffs,
    )


def commit_user_access(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: AccessCommitRequest,
    request: Request | None = None,
) -> AccessCommitResponse:
    _require_writes_enabled()
    _ensure_iam_manager(db, current_user)
    preview, preview_payload, summary = _load_preview(
        db, payload.preview_token, current_user.id, "user", user_id
    )
    current_revision = _get_revision(db, user_id, for_update=True)
    if preview.base_revision != current_revision:
        raise HTTPException(status_code=409, detail="用户权限已变化，请重新预览")

    current_is_super_admin = _is_superadmin(db, current_user.id)
    current_scopes = _manager_scopes(db, current_user.id)
    currently_cross_scope = any(
        not _scope_is_managed(current_scopes, item["factory_id"], item["department"])
        for item in preview_payload["operations"]
    )
    if not current_is_super_admin and (
        bool(summary.get("high_risk")) or currently_cross_scope
    ):
        raise HTTPException(
            status_code=403,
            detail="跨范围或高风险权限变更请由集团超级管理员直接操作",
        )
    if summary.get("high_risk") and not payload.confirm_high_risk:
        raise HTTPException(status_code=400, detail="高风险权限变更需要二次确认")

    _apply_user_operations(
        db,
        actor_user_id=current_user.id,
        target_user_id=user_id,
        operations=preview_payload["operations"],
        reason=preview_payload["reason"],
        request=request,
    )
    revision = _increment_revision(db, user_id)
    preview.consumed_at = now_text()
    db.commit()
    return AccessCommitResponse(
        status="committed",
        authorization_version=revision,
        message="权限变更已生效",
    )


def preview_system_position(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: SystemPositionPreviewRequest,
) -> SystemPositionPreviewResponse:
    _ensure_iam_manager(db, current_user)
    user = _load_user(db, user_id)
    profile = db.get(EmployeeProfile, user_id)
    if profile is None or not profile.primary_factory_id or not profile.primary_department:
        raise HTTPException(status_code=400, detail="该用户尚未确认主组织资料")
    actor_scopes = _manager_scopes(db, current_user.id)
    is_super_admin = _is_superadmin(db, current_user.id)
    if not is_super_admin and not _scope_is_managed(
        actor_scopes,
        profile.primary_factory_id,
        profile.primary_department,
    ):
        raise HTTPException(
            status_code=403,
            detail="跨范围内置职位调整请由集团超级管理员直接操作",
        )

    current_revision = _get_revision(db, user_id, for_update=True)
    if payload.base_revision != current_revision:
        raise HTTPException(status_code=409, detail="用户权限已变化，请刷新后重新预览")

    role = _load_role(db, payload.system_position_role_id.strip())
    position = get_system_position(role.id)
    if position is None:
        raise HTTPException(status_code=400, detail="请选择系统内置权限职位")
    permission_department = position.department
    _ensure_scope_applicable(
        role_scope_policy(role.code),
        profile.primary_factory_id,
        permission_department,
        subject=f"内置权限职位 {role.name}",
    )
    role_metadata = _get_role_metadata(db, role.id)
    role_template_version = role_metadata.version if role_metadata else 1

    effective_bindings = _active_bindings(db, user_id)
    effective_binding_ids = {binding.id for binding in effective_bindings}
    lifecycle_bindings = _lifecycle_active_bindings(db, user_id)
    roles_by_id = {
        item.id: item
        for item in db.scalars(
            select(AuthRole).where(
                AuthRole.id.in_({binding.role_id for binding in lifecycle_bindings})
            )
        ).all()
    } if lifecycle_bindings else {}
    before_positions = sorted(
        [
            binding
            for binding in effective_bindings
            if get_system_position(binding.role_id) is not None
        ],
        key=lambda binding: get_system_position(binding.role_id).sort_order,
    )

    operations: list[dict[str, Any]] = []
    kept_selected = False
    for binding in lifecycle_bindings:
        bound_role = roles_by_id.get(binding.role_id)
        if bound_role and bound_role.code in SPECIAL_SYSTEM_ROLE_CODES:
            continue
        if (
            not kept_selected
            and binding.id in effective_binding_ids
            and binding.role_id == role.id
            and binding.factory_id == profile.primary_factory_id
            and binding.department == permission_department
        ):
            kept_selected = True
            continue
        operations.append(
            {
                "kind": "role_binding",
                "operation": "revoke",
                "binding_id": binding.id,
                "role_id": binding.role_id,
                "factory_id": binding.factory_id,
                "department": binding.department,
                "valid_until": "",
                "risk_level": "high" if _role_is_high_risk(db, bound_role or _load_role(db, binding.role_id)) else "normal",
            }
        )

    if not kept_selected:
        operations.append(
            {
                "kind": "role_binding",
                "operation": "add",
                "binding_id": "",
                "role_id": role.id,
                "factory_id": profile.primary_factory_id,
                "department": permission_department,
                "valid_until": "",
                "risk_level": "high" if _role_is_high_risk(db, role) else "normal",
            }
        )

    permission_by_id = {
        item.id: item
        for item in db.scalars(select(AuthPermission)).all()
    }
    lifecycle_overrides = _lifecycle_active_overrides(db, user_id)
    for override in lifecycle_overrides:
        permission = permission_by_id.get(override.permission_id)
        if permission is None:
            continue
        operations.append(
            {
                "kind": "permission_override",
                "operation": "set",
                "permission_id": permission.id,
                "permission_code": permission.code,
                "effect": "inherit",
                "factory_id": override.factory_id,
                "department": override.department,
                "valid_until": "",
                "risk_level": _permission_risk(db, permission),
            }
        )

    if not operations:
        raise HTTPException(status_code=400, detail="该用户已使用所选内置权限职位")

    reason = payload.reason.strip() or (
        f"系统清理内置权限职位历史授权，保留{position.department_name} · {role.name}"
        if kept_selected
        else f"系统调整内置权限职位为{position.department_name} · {role.name}"
    )

    cross_scope = any(
        not _scope_is_managed(actor_scopes, item["factory_id"], item["department"])
        for item in operations
    )
    high_risk = any(item["risk_level"] == "high" for item in operations)
    if not is_super_admin and not actor_scopes:
        raise HTTPException(status_code=403, detail="无权限管理用户授权")
    if not is_super_admin and (cross_scope or high_risk):
        raise HTTPException(
            status_code=403,
            detail="跨范围或高风险内置职位调整请由集团超级管理员直接操作",
        )

    diffs = _preview_user_diffs(db, user_id, operations, allow_empty=True)
    before_role_ids = [binding.role_id for binding in before_positions]
    before_role_names = [
        roles_by_id[binding.role_id].name
        if binding.role_id in roles_by_id
        else binding.role_id
        for binding in before_positions
    ]
    removed_role_count = sum(
        1
        for item in operations
        if item["kind"] == "role_binding" and item["operation"] == "revoke"
    )
    raw_token, expires_at = _store_preview(
        db,
        actor_user_id=current_user.id,
        target_type="system_position",
        target_id=user_id,
        base_revision=current_revision,
        payload={
            "reason": reason,
            "operations": operations,
            "system_position_role_id": role.id,
            "system_position_role_version": role_template_version,
            "profile_primary_factory_id": profile.primary_factory_id,
            "profile_primary_department": profile.primary_department,
            "system_position_department": permission_department,
        },
        summary={
            "requires_approval": False,
            "high_risk": high_risk,
            "cross_scope": cross_scope,
            "before_role_ids": before_role_ids,
            "before_role_names": before_role_names,
            "after_role_id": role.id,
            "after_role_name": role.name,
            "removed_role_count": removed_role_count,
            "removed_override_count": len(lifecycle_overrides),
        },
    )
    db.commit()
    return SystemPositionPreviewResponse(
        preview_token=raw_token,
        expires_at=expires_at,
        base_revision=current_revision,
        before_role_ids=before_role_ids,
        before_role_names=before_role_names,
        after_role_id=role.id,
        after_role_name=role.name,
        removed_role_count=removed_role_count,
        removed_override_count=len(lifecycle_overrides),
        requires_approval=False,
        high_risk=high_risk,
        diffs=diffs,
    )


def commit_system_position(
    db: Session,
    current_user: AuthContext,
    user_id: str,
    payload: AccessCommitRequest,
    request: Request | None = None,
) -> AccessCommitResponse:
    _require_writes_enabled()
    _ensure_iam_manager(db, current_user)
    preview, preview_payload, summary = _load_preview(
        db,
        payload.preview_token,
        current_user.id,
        "system_position",
        user_id,
    )
    role = _load_role(db, preview_payload.get("system_position_role_id", ""))
    system_position = get_system_position(role.id)
    if system_position is None:
        raise HTTPException(status_code=409, detail="内置权限职位目录已变化，请重新预览")
    role_metadata = _get_role_metadata(db, role.id, for_update=True)
    current_role_version = role_metadata.version if role_metadata else 1
    if preview_payload.get("system_position_role_version") != current_role_version:
        raise HTTPException(status_code=409, detail="内置权限职位模板已变化，请重新预览")
    profile = db.get(EmployeeProfile, user_id)
    if (
        profile is None
        or profile.primary_factory_id != preview_payload.get("profile_primary_factory_id")
        or profile.primary_department != preview_payload.get("profile_primary_department")
    ):
        raise HTTPException(status_code=409, detail="用户主组织已变化，请重新预览")
    if system_position.department != preview_payload.get("system_position_department"):
        raise HTTPException(status_code=409, detail="内置权限职位目录已变化，请重新预览")
    _ensure_scope_applicable(
        role_scope_policy(role.code),
        profile.primary_factory_id,
        system_position.department,
        subject=f"内置权限职位 {role.name}",
    )

    operations = preview_payload["operations"]
    current_high_risk = _operations_are_high_risk(db, operations)
    if current_high_risk != bool(summary.get("high_risk")):
        raise HTTPException(status_code=409, detail="权限风险等级已变化，请重新预览")
    current_revision = _get_revision(db, user_id, for_update=True)
    if preview.base_revision != current_revision:
        raise HTTPException(status_code=409, detail="用户权限已变化，请重新预览")
    current_is_super_admin = _is_superadmin(db, current_user.id)
    current_scopes = _manager_scopes(db, current_user.id)
    if not current_is_super_admin and not _scope_is_managed(
        current_scopes,
        profile.primary_factory_id,
        profile.primary_department,
    ):
        raise HTTPException(
            status_code=403,
            detail="跨范围内置职位调整请由集团超级管理员直接操作",
        )
    currently_cross_scope = any(
        not _scope_is_managed(current_scopes, item["factory_id"], item["department"])
        for item in operations
    )
    if not current_is_super_admin and (current_high_risk or currently_cross_scope):
        raise HTTPException(
            status_code=403,
            detail="跨范围或高风险内置职位调整请由集团超级管理员直接操作",
        )
    if current_high_risk and not payload.confirm_high_risk:
        raise HTTPException(status_code=400, detail="高风险内置职位变更需要二次确认")

    _apply_user_operations(
        db,
        actor_user_id=current_user.id,
        target_user_id=user_id,
        operations=operations,
        reason=preview_payload["reason"],
        request=request,
    )
    revision = _increment_revision(db, user_id)
    preview.consumed_at = now_text()
    target_user = _load_user(db, user_id)
    add_auth_audit(
        db,
        "system_position_changed",
        username=target_user.username,
        user_id=user_id,
        detail=(
            f"内置权限职位：{','.join(summary.get('before_role_names', [])) or '未归类'}"
            f" -> {summary.get('after_role_name', role.name)}；"
            f"清理旧角色 {summary.get('removed_role_count', 0)} 个、"
            f"用户级权限 {summary.get('removed_override_count', 0)} 项"
        ),
        request=request,
    )
    db.commit()
    return AccessCommitResponse(
        status="committed",
        authorization_version=revision,
        message="内置权限职位已更新并立即生效",
    )


def create_access_request(
    db: Session,
    current_user: AuthContext,
    payload: AccessRequestCreate,
) -> AccessRequestOut:
    _require_writes_enabled()
    _ensure_iam_manager(db, current_user)
    preview, preview_payload, summary = _load_preview_any_user(db, payload.preview_token, current_user.id)
    if summary.get("high_risk") and not payload.confirm_high_risk:
        raise HTTPException(status_code=400, detail="高风险权限变更需要二次确认")
    if not summary.get("requires_approval"):
        raise HTTPException(status_code=400, detail="该变更可直接提交，无需创建审批申请")
    _ensure_access_requester(db, current_user, preview_payload["operations"])
    access_request = _create_access_request_from_preview(
        db, current_user.id, preview.target_id, preview, preview_payload
    )
    preview.consumed_at = now_text()
    db.commit()
    return _access_request_out(db, access_request)


def list_roles(db: Session, current_user: AuthContext) -> list[RoleSummaryOut]:
    _ensure_iam_manager(db, current_user)
    _ensure_permission_catalog_reader(db, current_user)
    roles = list(db.scalars(select(AuthRole).order_by(AuthRole.code)).all())
    return [_role_summary(db, role) for role in roles]


def list_system_positions(db: Session, current_user: AuthContext) -> list[RoleSummaryOut]:
    _ensure_iam_manager(db, current_user)
    _ensure_permission_catalog_reader(db, current_user)
    roles_by_id = {
        role.id: role
        for role in db.scalars(
            select(AuthRole).where(
                AuthRole.id.in_([item.role_id for item in SYSTEM_POSITION_DEFINITIONS])
            )
        ).all()
    }
    return [
        _role_summary(db, roles_by_id[item.role_id])
        for item in SYSTEM_POSITION_DEFINITIONS
        if item.role_id in roles_by_id
    ]


def get_role_access(db: Session, current_user: AuthContext, role_id: str) -> RoleAccessOut:
    _ensure_iam_manager(db, current_user)
    _ensure_permission_catalog_reader(db, current_user)
    role = _load_role(db, role_id)
    summary = _role_summary(db, role)
    return RoleAccessOut(**summary.model_dump(), permission_codes=_role_permission_codes(db, role.id))


def preview_role_access(
    db: Session,
    current_user: AuthContext,
    role_id: str,
    payload: RoleAccessPreviewRequest,
) -> RoleAccessPreviewResponse:
    _ensure_role_manager(db, current_user)
    role = _load_role(db, role_id)
    system_position = get_system_position(role.id)
    if system_position is not None:
        raise HTTPException(
            status_code=409,
            detail="系统内置职位由代码固定维护，不能在线修改",
        )
    metadata = _get_role_metadata(db, role.id, for_update=True)
    if metadata and metadata.protected:
        raise HTTPException(status_code=400, detail="受保护角色不能修改")
    version = metadata.version if metadata else 1
    if payload.base_version != version:
        raise HTTPException(status_code=409, detail="角色模板已变化，请刷新后重试")
    reason = _required_reason(payload.reason)
    desired_codes = sorted(set(payload.permission_codes))
    permissions = _permissions_by_code(db, desired_codes)
    if len(permissions) != len(desired_codes):
        missing = sorted(set(desired_codes) - set(permissions))
        raise HTTPException(status_code=400, detail=f"权限不存在：{','.join(missing)}")
    inactive = [code for code, permission in permissions.items() if _permission_status(db, permission) != "active"]
    if inactive:
        raise HTTPException(status_code=400, detail=f"权限已停用：{','.join(sorted(inactive))}")
    if system_position is None:
        _ensure_role_permissions_compatible(role, desired_codes)

    current_scope_mode = _role_scope_mode(metadata, system_position is not None)
    desired_scope_mode = payload.scope_mode or current_scope_mode
    if system_position is None and desired_scope_mode != OWN_FACTORY_SCOPE:
        raise HTTPException(status_code=400, detail="只有系统内置职位可以配置跨厂范围")

    current_codes = set(_role_permission_codes(db, role.id))
    desired_set = set(desired_codes)
    changed_codes = sorted(current_codes ^ desired_set)
    diffs = [
        RolePermissionDiffOut(
            permission_code=code,
            before=code in current_codes,
            after=code in desired_set,
            risk_level=_permission_risk(db, permissions.get(code) or _permission_by_code(db, code)),
        )
        for code in changed_codes
    ]
    if (
        not diffs
        and desired_scope_mode == current_scope_mode
        and payload.name in {None, role.name}
        and payload.description in {None, role.description}
    ):
        raise HTTPException(status_code=400, detail="角色模板没有变化")
    high_risk = (
        any(item.risk_level == "high" for item in diffs)
        or scope_mode_expands_access(current_scope_mode, desired_scope_mode)
        or _cross_scope_permission_additions_are_high_risk(
            db,
            current_codes,
            desired_set,
            desired_scope_mode,
            permissions,
        )
    )
    active_binding_ids = _active_role_binding_ids(db, role.id)
    raw_token, expires_at = _store_preview(
        db,
        actor_user_id=current_user.id,
        target_type="role",
        target_id=role.id,
        base_revision=version,
        payload={
            "reason": reason,
            "permission_codes": desired_codes,
            "permission_security": _permission_security_snapshot(db, permissions),
            "scope_mode": desired_scope_mode,
            "name": payload.name,
            "description": payload.description,
            "active_binding_ids": active_binding_ids,
        },
        summary={"high_risk": high_risk},
    )
    db.commit()
    return RoleAccessPreviewResponse(
        preview_token=raw_token,
        expires_at=expires_at,
        base_version=version,
        affected_user_count=len(active_binding_ids),
        diffs=diffs,
        high_risk=high_risk,
        before_scope_mode=current_scope_mode,
        after_scope_mode=desired_scope_mode,
    )


def commit_role_access(
    db: Session,
    current_user: AuthContext,
    role_id: str,
    payload: AccessCommitRequest,
    request: Request | None = None,
) -> RoleAccessCommitResponse:
    _ensure_role_manager(db, current_user)
    role = _load_role(db, role_id)
    if get_system_position(role.id) is not None:
        raise HTTPException(
            status_code=409,
            detail="系统内置职位由代码固定维护，不能在线修改",
        )
    _require_writes_enabled()
    preview, preview_payload, summary = _load_preview(
        db, payload.preview_token, current_user.id, "role", role_id
    )
    metadata = _get_role_metadata(db, role.id, for_update=True)
    version = metadata.version if metadata else 1
    if preview.base_revision != version:
        raise HTTPException(status_code=409, detail="角色模板已变化，请重新预览")
    if metadata and metadata.protected:
        raise HTTPException(status_code=400, detail="受保护角色不能修改")
    system_position = get_system_position(role.id)
    current_scope_mode = _role_scope_mode(metadata, system_position is not None)
    desired_scope_mode = preview_payload.get("scope_mode", current_scope_mode)
    if desired_scope_mode not in VALID_SCOPE_MODES:
        raise HTTPException(status_code=409, detail="内置职位范围配置已变化，请重新预览")
    if system_position is None and desired_scope_mode != OWN_FACTORY_SCOPE:
        raise HTTPException(status_code=409, detail="只有系统内置职位可以配置跨厂范围")
    if _active_role_binding_ids(db, role.id) != preview_payload.get("active_binding_ids"):
        raise HTTPException(status_code=409, detail="绑定用户已变化，请重新预览")

    desired_codes = preview_payload["permission_codes"]
    permissions = _permissions_by_code(db, desired_codes)
    if len(permissions) != len(desired_codes):
        raise HTTPException(status_code=409, detail="权限目录已变化，请重新预览")
    if _permission_security_snapshot(db, permissions) != preview_payload.get("permission_security"):
        raise HTTPException(status_code=409, detail="权限状态、风险或访问类型已变化，请重新预览")
    if system_position is None:
        _ensure_role_permissions_compatible(role, desired_codes)
    before_codes = _role_permission_codes(db, role.id)
    changed_codes = sorted(set(before_codes) ^ set(desired_codes))
    current_high_risk = (
        any(
            _permission_risk(db, permissions.get(code) or _permission_by_code(db, code)) == "high"
            for code in changed_codes
        )
        or scope_mode_expands_access(current_scope_mode, desired_scope_mode)
        or _cross_scope_permission_additions_are_high_risk(
            db,
            set(before_codes),
            set(desired_codes),
            desired_scope_mode,
            permissions,
        )
    )
    if current_high_risk != bool(summary.get("high_risk")):
        raise HTTPException(status_code=409, detail="角色模板风险已变化，请重新预览")
    if current_high_risk and not payload.confirm_high_risk:
        raise HTTPException(status_code=400, detail="高风险角色模板变更需要二次确认")
    existing = list(db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id == role.id)).all())
    desired_ids = {permission.id for permission in permissions.values()}
    for item in existing:
        if item.permission_id not in desired_ids:
            db.delete(item)
    existing_ids = {item.permission_id for item in existing}
    for permission in permissions.values():
        if permission.id not in existing_ids:
            db.add(
                AuthRolePermission(
                    id=f"{role.id}:{permission.id}",
                    role_id=role.id,
                    permission_id=permission.id,
                )
            )
    if preview_payload.get("name") is not None:
        role.name = preview_payload["name"].strip()
    if preview_payload.get("description") is not None:
        role.description = preview_payload["description"].strip()
    metadata = _ensure_role_metadata(db, role.id)
    metadata.version = version + 1
    metadata.scope_mode = desired_scope_mode
    metadata.updated_at = now_text()
    metadata.updated_by_user_id = current_user.id
    for user_id in sorted(_active_role_user_ids(db, role.id)):
        _increment_revision(db, user_id)
    _add_event(
        db,
        actor_user_id=current_user.id,
        event_type="role_template_updated",
        target_type="role",
        target_id=role.id,
        reason=preview_payload["reason"],
        before={"permission_codes": before_codes, "scope_mode": current_scope_mode},
        after={"permission_codes": desired_codes, "scope_mode": desired_scope_mode},
        request=request,
    )
    preview.consumed_at = now_text()
    db.commit()
    return RoleAccessCommitResponse(
        authorization_version=metadata.version,
        message="角色模板变更已生效",
    )


def list_access_requests(
    db: Session,
    current_user: AuthContext,
    status: str = "",
) -> list[AccessRequestOut]:
    _ensure_iam_manager(db, current_user)
    query = select(AuthAccessRequest).order_by(AuthAccessRequest.created_at.desc())
    if status:
        query = query.where(AuthAccessRequest.status == status)
    if not _is_superadmin(db, current_user.id):
        query = query.where(AuthAccessRequest.requester_user_id == current_user.id)
    return [_access_request_out(db, item) for item in db.scalars(query).all()]


def approve_access_request(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: AccessRequestDecision,
    request: Request | None = None,
) -> AccessRequestOut:
    _require_writes_enabled()
    _ensure_access_reviewer(db, current_user)
    reason = _required_reason(payload.reason)
    access_request = _load_access_request(db, request_id)
    if access_request.status != "pending":
        raise HTTPException(status_code=400, detail="该权限申请已处理")
    operations = [_operation_from_request_item(item) for item in _request_items(db, access_request.id)]
    if _system_position_request_has_drift(
        db,
        access_request.target_user_id,
        operations,
    ):
        access_request.status = "expired"
        access_request.decision_by_user_id = current_user.id
        access_request.decision_comment = "内置权限职位模板或风险等级已变化，请重新预览并提交"
        access_request.decided_at = now_text()
        access_request.updated_at = now_text()
        db.commit()
        raise HTTPException(status_code=409, detail="内置权限职位已变化，该申请已失效")
    current_revision = _get_revision(db, access_request.target_user_id, for_update=True)
    if current_revision != access_request.base_revision:
        access_request.status = "expired"
        access_request.decision_by_user_id = current_user.id
        access_request.decision_comment = "目标用户权限版本已变化，请重新预览并提交"
        access_request.decided_at = now_text()
        access_request.updated_at = now_text()
        db.commit()
        raise HTTPException(status_code=409, detail="目标用户权限已变化，该申请已失效")
    _apply_user_operations(
        db,
        actor_user_id=current_user.id,
        target_user_id=access_request.target_user_id,
        operations=operations,
        reason=access_request.reason,
        request=request,
        access_request_id=access_request.id,
    )
    _increment_revision(db, access_request.target_user_id)
    access_request.status = "approved"
    access_request.decision_by_user_id = current_user.id
    access_request.decision_comment = reason
    access_request.decided_at = now_text()
    access_request.updated_at = now_text()
    _add_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=access_request.target_user_id,
        event_type="access_request_approved",
        target_type="access_request",
        target_id=access_request.id,
        reason=reason,
        access_request_id=access_request.id,
        request=request,
    )
    db.commit()
    return _access_request_out(db, access_request)


def reject_access_request(
    db: Session,
    current_user: AuthContext,
    request_id: str,
    payload: AccessRequestDecision,
    request: Request | None = None,
) -> AccessRequestOut:
    _require_writes_enabled()
    _ensure_access_reviewer(db, current_user)
    reason = _required_reason(payload.reason)
    access_request = _load_access_request(db, request_id)
    if access_request.status != "pending":
        raise HTTPException(status_code=400, detail="该权限申请已处理")
    access_request.status = "rejected"
    access_request.decision_by_user_id = current_user.id
    access_request.decision_comment = reason
    access_request.decided_at = now_text()
    access_request.updated_at = now_text()
    _add_event(
        db,
        actor_user_id=current_user.id,
        target_user_id=access_request.target_user_id,
        event_type="access_request_rejected",
        target_type="access_request",
        target_id=access_request.id,
        reason=reason,
        access_request_id=access_request.id,
        request=request,
    )
    db.commit()
    return _access_request_out(db, access_request)


def list_audit_events(
    db: Session,
    current_user: AuthContext,
    actor_user_id: str = "",
    target_user_id: str = "",
    module_code: str = "",
    factory_id: str = "",
    department: str = "",
    date_from: str = "",
    date_to: str = "",
    limit: int = 100,
) -> list[AuditEventOut]:
    _ensure_audit_reader(db, current_user)
    query = select(AuthAuthorizationEvent).order_by(AuthAuthorizationEvent.created_at.desc()).limit(min(max(limit, 1), 500))
    if actor_user_id:
        query = query.where(AuthAuthorizationEvent.actor_user_id == actor_user_id)
    if target_user_id:
        query = query.where(AuthAuthorizationEvent.target_user_id == target_user_id)
    if factory_id:
        query = query.where(AuthAuthorizationEvent.factory_id == factory_id)
    if department:
        query = query.where(AuthAuthorizationEvent.department == department)
    if date_from:
        query = query.where(AuthAuthorizationEvent.created_at >= date_from)
    if date_to:
        query = query.where(AuthAuthorizationEvent.created_at <= date_to)
    events = list(db.scalars(query).all())
    if module_code:
        permission_ids = {
            item.permission_id
            for item in db.scalars(
                select(AuthPermissionMetadata).where(AuthPermissionMetadata.module_code == module_code)
            ).all()
        }
        events = [event for event in events if event.permission_id in permission_ids]
    if not _is_superadmin(db, current_user.id):
        events = [
            event for event in events
            if _scope_is_managed(_manager_scopes(db, current_user.id), event.factory_id, event.department)
        ]
    return [_audit_event_out(db, event) for event in events]


def search_users(
    db: Session,
    current_user: AuthContext,
    query_text: str = "",
    status: str = "",
    limit: int = 50,
) -> list[UserSearchOut]:
    _ensure_iam_manager(db, current_user)
    query = select(AuthUser).order_by(AuthUser.display_name, AuthUser.username).limit(min(max(limit, 1), 100))
    if query_text.strip():
        pattern = f"%{query_text.strip()}%"
        query = query.where((AuthUser.username.ilike(pattern)) | (AuthUser.display_name.ilike(pattern)))
    if status:
        query = query.where(AuthUser.status == status)
    scopes = _manager_scopes(db, current_user.id)
    is_super_admin = _is_superadmin(db, current_user.id)
    result: list[UserSearchOut] = []
    for user in db.scalars(query).all():
        profile = db.get(EmployeeProfile, user.id)
        factory_id = profile.primary_factory_id if profile else ""
        department = profile.primary_department if profile else ""
        full = is_super_admin or _scope_is_managed(scopes, factory_id, department) or _user_has_managed_binding(
            db, user.id, scopes
        )
        result.append(
            UserSearchOut(
                id=user.id,
                username=user.username,
                display_name=user.display_name,
                status=user.status if full else "",
                primary_factory_id=factory_id,
                primary_department=department,
                position=(profile.position if profile and full else ""),
                manageable=full,
            )
        )
    return result


def _permission_out(permission: AuthPermission, metadata: AuthPermissionMetadata | None) -> PermissionOut:
    module_code, action = _split_permission_code(permission.code)
    module_code = metadata.module_code if metadata else module_code
    action = metadata.action if metadata else action
    scope_policy = permission_scope_policy(permission.code)
    return PermissionOut(
        code=permission.code,
        name=permission.name,
        description=permission.description,
        module_code=module_code,
        module_name=MODULE_NAMES.get(module_code, module_code),
        action=action,
        risk_level=metadata.risk_level if metadata else _infer_risk(permission.code, action),
        access_kind=(
            metadata.access_kind
            if metadata and metadata.access_kind in VALID_ACCESS_KINDS
            else default_permission_access_kind(permission.code)
        ),
        scope_type=(
            "department"
            if metadata and metadata.scope_type == "factory_department"
            else (metadata.scope_type if metadata else "department")
        ),
        status=metadata.status if metadata else "active",
        sort_order=metadata.sort_order if metadata else 0,
        applicable_departments=list(scope_policy.departments),
        requires_global_factory=scope_policy.requires_global_factory,
        scope_guidance=scope_policy.guidance,
    )


def _profile_out(profile: EmployeeProfile | None) -> EmployeeProfileOut | None:
    if profile is None:
        return None
    return EmployeeProfileOut(
        primary_factory_id=profile.primary_factory_id,
        primary_department=profile.primary_department,
        position=profile.position,
        confirmation_status=profile.confirmation_status,
    )


def _role_bindings_out(db: Session, user_id: str) -> list[RoleBindingOut]:
    bindings = list(db.scalars(select(AuthUserRole).where(AuthUserRole.user_id == user_id).order_by(AuthUserRole.id)).all())
    role_ids = {item.role_id for item in bindings}
    roles = {
        item.id: item for item in db.scalars(select(AuthRole).where(AuthRole.id.in_(role_ids))).all()
    } if role_ids else {}
    metadata = {
        item.user_role_id: item
        for item in db.scalars(
            select(AuthRoleBindingMetadata).where(
                AuthRoleBindingMetadata.user_role_id.in_([item.id for item in bindings])
            )
        ).all()
    } if bindings else {}
    result = []
    for binding in bindings:
        role = roles.get(binding.role_id)
        meta = metadata.get(binding.id)
        result.append(
            RoleBindingOut(
                id=binding.id,
                role_id=binding.role_id,
                role_code=role.code if role else binding.role_id,
                role_name=role.name if role else binding.role_id,
                factory_id=binding.factory_id,
                department=binding.department,
                state=meta.state if meta else "active",
                source_type=meta.source_type if meta else "legacy_import",
                valid_from=meta.valid_from if meta else "",
                valid_until=meta.valid_until if meta else "",
                reason=meta.reason if meta else "",
            )
        )
    return result


def _overrides_out(db: Session, user_id: str) -> list[PermissionOverrideOut]:
    overrides = list(
        db.scalars(
            select(AuthUserPermissionOverride)
            .where(AuthUserPermissionOverride.user_id == user_id)
            .order_by(AuthUserPermissionOverride.created_at.desc())
        ).all()
    )
    permission_ids = {item.permission_id for item in overrides}
    permissions = {
        item.id: item for item in db.scalars(select(AuthPermission).where(AuthPermission.id.in_(permission_ids))).all()
    } if permission_ids else {}
    return [
        PermissionOverrideOut(
            id=item.id,
            permission_id=item.permission_id,
            permission_code=permissions[item.permission_id].code if item.permission_id in permissions else item.permission_id,
            effect=item.effect,
            factory_id=item.factory_id,
            department=item.department,
            state=item.status,
            valid_from=item.valid_from,
            valid_until=item.valid_until,
            reason=item.reason,
        )
        for item in overrides
    ]


def _effective_access_out(db: Session, user_id: str) -> list[EffectiveAccessOut]:
    keys: set[tuple[str, str, str]] = set()
    permission_by_id = {item.id: item for item in db.scalars(select(AuthPermission)).all()}
    bindings = _active_bindings(db, user_id)
    for binding in bindings:
        for role_permission in db.scalars(
            select(AuthRolePermission).where(AuthRolePermission.role_id == binding.role_id)
        ).all():
            permission = permission_by_id.get(role_permission.permission_id)
            if permission:
                keys.add((permission.code, binding.factory_id, binding.department))
    for override in _active_overrides(db, user_id):
        permission = permission_by_id.get(override.permission_id)
        if permission:
            keys.add((permission.code, override.factory_id, override.department))
    if _is_superadmin(db, user_id):
        keys.update((item.code, "*", "*") for item in permission_by_id.values())
    result = []
    for permission_code, factory_id, department in sorted(keys):
        effect, source_type, source_id, source_name = _resolve_access(
            db, user_id, permission_code, factory_id, department
        )
        result.append(
            EffectiveAccessOut(
                permission_code=permission_code,
                factory_id=factory_id,
                department=department,
                effect=effect,
                allowed=effect == "allow",
                source_type=source_type,
                source_ids=[source_id] if source_id else [],
                source_name=source_name,
            )
        )
    return result


def _normalize_user_operations(
    db: Session,
    user_id: str,
    binding_inputs: list[Any],
    override_inputs: list[Any],
    default_factory_id: str,
    default_department: str,
) -> list[dict[str, Any]]:
    operations: list[dict[str, Any]] = []
    for item in binding_inputs:
        operation = item.operation
        binding = db.get(AuthUserRole, item.binding_id) if item.binding_id else None
        if operation in {"update", "revoke"}:
            if binding is None or binding.user_id != user_id:
                raise HTTPException(status_code=404, detail="角色授权记录不存在")
        role_id = (item.role_id or (binding.role_id if binding else "")).strip()
        role = db.get(AuthRole, role_id) if role_id else None
        if operation != "revoke" and role is None:
            raise HTTPException(status_code=400, detail=f"角色不存在：{role_id}")
        factory_id = (item.factory_id or default_factory_id or (binding.factory_id if binding else "")).strip()
        department = (item.department or default_department or (binding.department if binding else "")).strip()
        _validate_scope(factory_id, department)
        if operation != "revoke":
            _ensure_scope_applicable(
                role_scope_policy(role.code),
                factory_id,
                department,
                subject=f"角色 {role.name}",
            )
        valid_until = _validate_valid_until(item.valid_until or "")
        risk_level = "high" if _role_is_high_risk(db, role or _load_role(db, binding.role_id)) else "normal"
        operations.append(
            {
                "kind": "role_binding",
                "operation": operation,
                "binding_id": binding.id if binding else "",
                "role_id": role_id,
                "factory_id": factory_id,
                "department": department,
                "valid_until": valid_until,
                "risk_level": risk_level,
            }
        )
    seen_overrides: set[tuple[str, str, str]] = set()
    for item in override_inputs:
        code = item.permission_code.strip()
        permission = _permission_by_code(db, code)
        if permission is None:
            raise HTTPException(status_code=400, detail=f"权限不存在：{code}")
        if _permission_status(db, permission) != "active":
            raise HTTPException(status_code=400, detail=f"权限已停用：{code}")
        factory_id = (item.factory_id or default_factory_id).strip()
        department = (item.department or default_department).strip()
        _validate_scope(factory_id, department)
        if item.effect in {"allow", "deny"}:
            _ensure_scope_applicable(
                permission_scope_policy(code),
                factory_id,
                department,
                subject=f"权限 {permission.name or code}",
            )
        key = (code, factory_id, department)
        if key in seen_overrides:
            raise HTTPException(status_code=400, detail=f"权限变更重复：{code}@{factory_id}/{department}")
        seen_overrides.add(key)
        operations.append(
            {
                "kind": "permission_override",
                "operation": "set",
                "permission_id": permission.id,
                "permission_code": code,
                "effect": item.effect,
                "factory_id": factory_id,
                "department": department,
                "valid_until": _validate_valid_until(item.valid_until or ""),
                "risk_level": _permission_risk(db, permission),
            }
        )
    return operations


def _preview_user_diffs(
    db: Session,
    user_id: str,
    operations: list[dict[str, Any]],
    *,
    allow_empty: bool = False,
) -> list[AccessDiffOut]:
    excluded_bindings: set[str] = set()
    added_bindings: list[dict[str, str]] = []
    override_changes: dict[tuple[str, str, str], str] = {}
    impacted: set[tuple[str, str, str]] = set()
    for operation in operations:
        if operation["kind"] == "role_binding":
            if operation["binding_id"]:
                old = db.get(AuthUserRole, operation["binding_id"])
                excluded_bindings.add(operation["binding_id"])
                if old:
                    for code in _role_permission_codes(db, old.role_id):
                        impacted.add((code, old.factory_id, old.department))
            if operation["operation"] != "revoke":
                added_bindings.append(operation)
                for code in _role_permission_codes(db, operation["role_id"]):
                    impacted.add((code, operation["factory_id"], operation["department"]))
        else:
            key = (operation["permission_code"], operation["factory_id"], operation["department"])
            impacted.add(key)
            override_changes[key] = operation["effect"]
    diffs: list[AccessDiffOut] = []
    for code, factory_id, department in sorted(impacted):
        before, before_source, *_ = _resolve_access(db, user_id, code, factory_id, department)
        after, after_source, *_ = _resolve_access(
            db,
            user_id,
            code,
            factory_id,
            department,
            excluded_binding_ids=excluded_bindings,
            added_bindings=added_bindings,
            override_changes=override_changes,
        )
        if before == after and before_source == after_source:
            continue
        permission = _permission_by_code(db, code)
        diffs.append(
            AccessDiffOut(
                permission_code=code,
                factory_id=factory_id,
                department=department,
                before=before,
                after=after,
                before_source=before_source,
                after_source=after_source,
                risk_level=_permission_risk(db, permission),
            )
        )
    if not diffs and not allow_empty:
        raise HTTPException(status_code=400, detail="提交内容不会改变最终权限")
    return diffs


def _resolve_access(
    db: Session,
    user_id: str,
    permission_code: str,
    factory_id: str,
    department: str,
    *,
    excluded_binding_ids: set[str] | None = None,
    added_bindings: list[dict[str, str]] | None = None,
    override_changes: dict[tuple[str, str, str], str] | None = None,
) -> tuple[str, str, str, str]:
    excluded_binding_ids = excluded_binding_ids or set()
    added_bindings = added_bindings or []
    override_changes = override_changes or {}
    if _is_superadmin(db, user_id, excluded_binding_ids=excluded_binding_ids, added_bindings=added_bindings):
        return "allow", "superadmin", "", "集团超级管理员"
    key = (permission_code, factory_id, department)
    permission = _permission_by_code(db, permission_code)
    matching_override_effects: list[tuple[str, str]] = []
    if permission:
        for item in _active_overrides(db, user_id):
            if item.permission_id != permission.id:
                continue
            changed_key = (permission_code, item.factory_id, item.department)
            if changed_key in override_changes:
                continue
            if _scope_matches(item.factory_id, item.department, factory_id, department):
                matching_override_effects.append((item.effect, item.id))
    draft_effect = override_changes.get(key)
    if draft_effect in {"allow", "deny"}:
        matching_override_effects.append((draft_effect, "preview"))
    if matching_override_effects:
        for effect in ("deny", "allow"):
            source_id = next(
                (candidate_id for candidate_effect, candidate_id in matching_override_effects if candidate_effect == effect),
                "",
            )
            if source_id:
                return effect, "user_override", source_id, "用户级覆盖"
    role_ids_with_permission = _role_ids_for_permission(db, permission_code)
    for binding in _active_bindings(db, user_id):
        if binding.id in excluded_binding_ids:
            continue
        if binding.role_id in role_ids_with_permission and _scope_matches(
            binding.factory_id, binding.department, factory_id, department
        ):
            role = db.get(AuthRole, binding.role_id)
            return "allow", "role", binding.id, role.name if role else binding.role_id
    for binding in added_bindings:
        if binding["role_id"] in role_ids_with_permission and _scope_matches(
            binding["factory_id"], binding["department"], factory_id, department
        ):
            role = db.get(AuthRole, binding["role_id"])
            return "allow", "role", "preview", role.name if role else binding["role_id"]
    return "none", "default", "", "默认拒绝"


def _apply_user_operations(
    db: Session,
    actor_user_id: str,
    target_user_id: str,
    operations: list[dict[str, Any]],
    reason: str,
    request: Request | None = None,
    access_request_id: str = "",
) -> None:
    for operation in operations:
        if operation["kind"] == "role_binding":
            _apply_role_binding_operation(
                db, actor_user_id, target_user_id, operation, reason, request, access_request_id
            )
        else:
            _apply_override_operation(
                db, actor_user_id, target_user_id, operation, reason, request, access_request_id
            )


def _apply_role_binding_operation(
    db: Session,
    actor_user_id: str,
    target_user_id: str,
    operation: dict[str, Any],
    reason: str,
    request: Request | None,
    access_request_id: str,
) -> None:
    now = now_text()
    old_binding = db.get(AuthUserRole, operation["binding_id"]) if operation["binding_id"] else None
    if operation["operation"] in {"update", "revoke"} and (
        old_binding is None or old_binding.user_id != target_user_id
    ):
        raise HTTPException(status_code=409, detail="角色授权记录已变化，请重新预览")
    if old_binding and _binding_is_superadmin(db, old_binding) and operation["operation"] in {"update", "revoke"}:
        if _count_active_superadmins(db) <= 1:
            raise HTTPException(status_code=400, detail="不能撤销或变更最后一个集团超级管理员")
    before = _binding_dict(old_binding) if old_binding else {}
    if operation["operation"] == "revoke":
        metadata = _ensure_binding_metadata(db, old_binding.id)
        metadata.state = "revoked"
        metadata.revoked_by_user_id = actor_user_id
        metadata.revoked_at = now
        metadata.revoke_reason = reason
        metadata.updated_at = now
        target_id = old_binding.id
        after = {**before, "state": "revoked"}
    else:
        if old_binding:
            metadata = _ensure_binding_metadata(db, old_binding.id)
            metadata.state = "revoked"
            metadata.revoked_by_user_id = actor_user_id
            metadata.revoked_at = now
            metadata.revoke_reason = "由新的角色授权记录替代"
            metadata.updated_at = now
        new_binding = AuthUserRole(
            id=f"urb-{uuid4().hex}",
            user_id=target_user_id,
            role_id=operation["role_id"],
            factory_id=operation["factory_id"],
            department=operation["department"],
        )
        db.add(new_binding)
        db.flush()
        db.add(
            AuthRoleBindingMetadata(
                user_role_id=new_binding.id,
                state="active",
                source_type="manual",
                source_id=access_request_id,
                valid_from=now,
                valid_until=operation["valid_until"],
                reason=reason,
                created_by_user_id=actor_user_id,
                approved_by_user_id=actor_user_id,
                revoked_by_user_id="",
                revoked_at="",
                revoke_reason="",
                version=1,
                created_at=now,
                updated_at=now,
            )
        )
        target_id = new_binding.id
        after = _binding_dict(new_binding) | {"state": "active", "valid_until": operation["valid_until"]}
    _add_event(
        db,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        event_type=f"role_binding_{operation['operation']}",
        target_type="role_binding",
        target_id=target_id,
        factory_id=operation["factory_id"],
        department=operation["department"],
        reason=reason,
        before=before,
        after=after,
        access_request_id=access_request_id,
        request=request,
    )


def _apply_override_operation(
    db: Session,
    actor_user_id: str,
    target_user_id: str,
    operation: dict[str, Any],
    reason: str,
    request: Request | None,
    access_request_id: str,
) -> None:
    now = now_text()
    existing = [
        item for item in _lifecycle_active_overrides(db, target_user_id)
        if item.permission_id == operation["permission_id"]
        and item.factory_id == operation["factory_id"]
        and item.department == operation["department"]
    ]
    before = [_override_dict(item) for item in existing]
    if operation["effect"] == "deny" and operation["permission_code"].startswith("system:"):
        if _is_superadmin(db, target_user_id) and _count_active_superadmins(db) <= 1:
            raise HTTPException(status_code=400, detail="不能禁止最后一个集团超级管理员的系统管理权限")
    for item in existing:
        item.status = "revoked"
        item.revoked_by_user_id = actor_user_id
        item.revoked_at = now
        item.revoke_reason = reason
        item.updated_at = now
    new_override = None
    if operation["effect"] != "inherit":
        new_override = AuthUserPermissionOverride(
            id=f"upo-{uuid4().hex}",
            user_id=target_user_id,
            permission_id=operation["permission_id"],
            effect=operation["effect"],
            factory_id=operation["factory_id"],
            department=operation["department"],
            status="active",
            valid_from=now,
            valid_until=operation["valid_until"],
            reason=reason,
            source_type="manual" if not access_request_id else "access_request",
            source_id=access_request_id,
            created_by_user_id=actor_user_id,
            approved_by_user_id=actor_user_id,
            revoked_by_user_id="",
            revoked_at="",
            revoke_reason="",
            created_at=now,
            updated_at=now,
        )
        db.add(new_override)
    _add_event(
        db,
        actor_user_id=actor_user_id,
        target_user_id=target_user_id,
        event_type="permission_override_removed" if operation["effect"] == "inherit" else "permission_override_set",
        target_type="permission_override",
        target_id=new_override.id if new_override else (existing[0].id if existing else ""),
        permission_id=operation["permission_id"],
        effect=operation["effect"],
        factory_id=operation["factory_id"],
        department=operation["department"],
        reason=reason,
        before={"items": before},
        after=_override_dict(new_override) if new_override else {},
        access_request_id=access_request_id,
        request=request,
    )


def _store_preview(
    db: Session,
    actor_user_id: str,
    target_type: str,
    target_id: str,
    base_revision: int,
    payload: dict[str, Any],
    summary: dict[str, Any],
) -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now()
    expires_at = (now + timedelta(minutes=PREVIEW_TTL_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    db.add(
        AuthAuthorizationPreview(
            id=f"preview-{uuid4().hex}",
            token_hash=_token_hash(raw_token),
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            base_revision=base_revision,
            payload_json=json.dumps(payload, ensure_ascii=False, sort_keys=True),
            summary_json=json.dumps(summary, ensure_ascii=False, sort_keys=True),
            expires_at=expires_at,
            consumed_at="",
            created_at=now.strftime("%Y-%m-%d %H:%M:%S"),
        )
    )
    return raw_token, expires_at


def _load_preview(
    db: Session,
    raw_token: str,
    actor_user_id: str,
    target_type: str,
    target_id: str,
) -> tuple[AuthAuthorizationPreview, dict[str, Any], dict[str, Any]]:
    preview = db.scalar(
        select(AuthAuthorizationPreview)
        .where(AuthAuthorizationPreview.token_hash == _token_hash(raw_token))
        .with_for_update()
    )
    if preview is None or preview.actor_user_id != actor_user_id:
        raise HTTPException(status_code=404, detail="预览令牌不存在")
    if preview.target_type != target_type or preview.target_id != target_id:
        raise HTTPException(status_code=400, detail="预览令牌与提交目标不匹配")
    _validate_preview_active(preview)
    return preview, _json_object(preview.payload_json), _json_object(preview.summary_json)


def _load_preview_any_user(
    db: Session,
    raw_token: str,
    actor_user_id: str,
) -> tuple[AuthAuthorizationPreview, dict[str, Any], dict[str, Any]]:
    preview = db.scalar(
        select(AuthAuthorizationPreview)
        .where(AuthAuthorizationPreview.token_hash == _token_hash(raw_token))
        .with_for_update()
    )
    if preview is None or preview.actor_user_id != actor_user_id or preview.target_type != "user":
        raise HTTPException(status_code=404, detail="预览令牌不存在")
    _validate_preview_active(preview)
    return preview, _json_object(preview.payload_json), _json_object(preview.summary_json)


def _validate_preview_active(preview: AuthAuthorizationPreview) -> None:
    if preview.consumed_at:
        raise HTTPException(status_code=409, detail="预览令牌已使用")
    expires_at = _parse_time(preview.expires_at)
    if expires_at is None or expires_at <= datetime.now():
        raise HTTPException(status_code=410, detail="预览令牌已过期，请重新预览")


def _create_access_request_from_preview(
    db: Session,
    requester_user_id: str,
    target_user_id: str,
    preview: AuthAuthorizationPreview,
    payload: dict[str, Any],
) -> AuthAccessRequest:
    now = now_text()
    access_request = AuthAccessRequest(
        id=f"access-request-{uuid4().hex}",
        requester_user_id=requester_user_id,
        target_user_id=target_user_id,
        status="pending",
        reason=payload["reason"],
        base_revision=preview.base_revision,
        decision_by_user_id="",
        decision_comment="",
        submitted_at=now,
        decided_at="",
        created_at=now,
        updated_at=now,
    )
    db.add(access_request)
    db.flush()
    preview_summary = _json_object(preview.summary_json)
    system_position_context = {}
    if payload.get("system_position_role_id"):
        system_position_context = {
            "system_position_role_id": payload["system_position_role_id"],
            "system_position_role_version": payload.get("system_position_role_version", 1),
            "system_position_preview_high_risk": bool(preview_summary.get("high_risk")),
            "profile_primary_factory_id": payload.get("profile_primary_factory_id", ""),
            "profile_primary_department": payload.get("profile_primary_department", ""),
            "system_position_department": payload.get("system_position_department", ""),
        }
    for index, operation in enumerate(payload["operations"], start=1):
        stored_operation = {**operation, **system_position_context}
        db.add(
            AuthAccessRequestItem(
                id=f"{access_request.id}:item:{index}",
                request_id=access_request.id,
                operation=operation["operation"],
                target_type=operation["kind"],
                target_id=operation.get("binding_id", ""),
                role_id=operation.get("role_id", ""),
                permission_id=operation.get("permission_id", ""),
                effect=operation.get("effect", ""),
                factory_id=operation["factory_id"],
                department=operation["department"],
                valid_from="",
                valid_until=operation.get("valid_until", ""),
                payload_json=json.dumps(stored_operation, ensure_ascii=False, sort_keys=True),
                created_at=now,
            )
        )
    _add_event(
        db,
        actor_user_id=requester_user_id,
        target_user_id=target_user_id,
        event_type="access_request_submitted",
        target_type="access_request",
        target_id=access_request.id,
        reason=payload["reason"],
        access_request_id=access_request.id,
    )
    return access_request


def _access_request_out(db: Session, item: AuthAccessRequest) -> AccessRequestOut:
    requester = db.get(AuthUser, item.requester_user_id)
    target = db.get(AuthUser, item.target_user_id)
    request_items = _request_items(db, item.id)
    changes = []
    high_risk = False
    for request_item in request_items:
        risk = _request_item_risk(db, request_item)
        high_risk = high_risk or risk == "high"
        operation = _operation_from_request_item(request_item)
        if request_item.permission_id:
            permission = db.get(AuthPermission, request_item.permission_id)
            if permission:
                changes.append(
                    {
                        "permission_code": permission.code,
                        "effect": request_item.effect or "inherit",
                        "factory_id": request_item.factory_id,
                        "department": request_item.department,
                        "valid_until": request_item.valid_until or None,
                    }
                )
            continue
        for code in _role_permission_codes(db, request_item.role_id):
            changes.append(
                {
                    "permission_code": code,
                    "effect": "inherit" if request_item.operation == "revoke" else "allow",
                    "factory_id": request_item.factory_id,
                    "department": request_item.department,
                    "valid_until": operation.get("valid_until") or None,
                }
            )
    return AccessRequestOut(
        id=item.id,
        requester_user_id=item.requester_user_id,
        requester_name=requester.display_name if requester else item.requester_user_id,
        target_user_id=item.target_user_id,
        target_user_name=target.display_name if target else item.target_user_id,
        base_revision=item.base_revision,
        reason=item.reason,
        status="invalidated" if item.status == "expired" else item.status,
        review_reason=item.decision_comment,
        high_risk=high_risk,
        created_at=item.created_at,
        reviewed_at=item.decided_at,
        changes=changes,
    )


def _operation_from_request_item(item: AuthAccessRequestItem) -> dict[str, Any]:
    payload = _json_object(item.payload_json)
    if payload:
        return payload
    return {
        "kind": item.target_type,
        "operation": item.operation,
        "binding_id": item.target_id,
        "role_id": item.role_id,
        "permission_id": item.permission_id,
        "permission_code": "",
        "effect": item.effect,
        "factory_id": item.factory_id,
        "department": item.department,
        "valid_until": item.valid_until,
        "risk_level": _request_item_risk(None, item),
    }


def _audit_event_out(db: Session, event: AuthAuthorizationEvent) -> AuditEventOut:
    permission = db.get(AuthPermission, event.permission_id) if event.permission_id else None
    actor = db.get(AuthUser, event.actor_user_id) if event.actor_user_id else None
    target = db.get(AuthUser, event.target_user_id) if event.target_user_id else None
    return AuditEventOut(
        id=event.id,
        event_type=event.event_type,
        actor_user_id=event.actor_user_id,
        actor_name=actor.display_name if actor else event.actor_user_id,
        target_user_id=event.target_user_id,
        target_user_name=target.display_name if target else event.target_user_id,
        permission_code=permission.code if permission else "",
        factory_id=event.factory_id,
        department=event.department,
        reason=event.reason,
        before_value=_json_object(event.before_json),
        after_value=_json_object(event.after_json),
        request_id=event.access_request_id,
        ip_address=event.ip_address,
        created_at=event.created_at,
    )


def _add_event(
    db: Session,
    actor_user_id: str,
    event_type: str,
    target_type: str,
    target_id: str,
    *,
    target_user_id: str = "",
    permission_id: str = "",
    effect: str = "",
    factory_id: str = "",
    department: str = "",
    reason: str = "",
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    access_request_id: str = "",
    request: Request | None = None,
) -> None:
    db.add(
        AuthAuthorizationEvent(
            id=f"authz-event-{uuid4().hex}",
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            event_type=event_type,
            target_type=target_type,
            target_id=target_id,
            permission_id=permission_id,
            effect=effect,
            factory_id=factory_id,
            department=department,
            before_json=json.dumps(before or {}, ensure_ascii=False, sort_keys=True),
            after_json=json.dumps(after or {}, ensure_ascii=False, sort_keys=True),
            reason=reason,
            ip_address=request.client.host if request and request.client else "",
            user_agent=request.headers.get("user-agent", "") if request else "",
            access_request_id=access_request_id,
            created_at=now_text(),
        )
    )


def _ensure_iam_manager(db: Session, user: AuthContext) -> None:
    if _is_superadmin(db, user.id) or _manager_scopes(db, user.id):
        return
    raise HTTPException(status_code=403, detail="无权限管理用户授权")


def _ensure_can_view_user_access(db: Session, user: AuthContext, target_user_id: str) -> None:
    _ensure_iam_manager(db, user)
    if _is_superadmin(db, user.id):
        return
    profile = db.get(EmployeeProfile, target_user_id)
    scopes = _manager_scopes(db, user.id)
    if profile and _scope_is_managed(scopes, profile.primary_factory_id, profile.primary_department):
        return
    if _user_has_managed_binding(db, target_user_id, scopes):
        return
    raise HTTPException(status_code=403, detail="只能查看管理范围内的完整权限")


def _ensure_role_manager(db: Session, user: AuthContext) -> None:
    if _is_superadmin(db, user.id) and can(user, "system:role_manage", "*", "*"):
        return
    raise HTTPException(status_code=403, detail="只有集团超级管理员可以修改角色模板")


def _ensure_access_reviewer(db: Session, user: AuthContext) -> None:
    if _is_superadmin(db, user.id) and can(user, "system:access_approve", "*", "*"):
        return
    raise HTTPException(status_code=403, detail="只有集团超级管理员可以审批权限申请")


def _ensure_audit_reader(db: Session, user: AuthContext) -> None:
    if _is_superadmin(db, user.id) or any(
        _has_scoped_permission(db, user.id, code) for code in AUDIT_READ_PERMISSIONS
    ):
        return
    raise HTTPException(status_code=403, detail="无权限查看授权审计")


def _ensure_permission_catalog_reader(db: Session, user: AuthContext) -> None:
    if _is_superadmin(db, user.id) or _has_scoped_permission(
        db,
        user.id,
        "system:permission_catalog_read",
    ):
        return
    raise HTTPException(status_code=403, detail="无权限查看权限目录")


def _ensure_access_requester(
    db: Session,
    user: AuthContext,
    operations: list[dict[str, Any]],
) -> None:
    if _is_superadmin(db, user.id):
        return
    if operations and _has_scoped_permission(db, user.id, "system:access_request"):
        return
    raise HTTPException(status_code=403, detail="无权限提交该范围的权限申请")


def _manager_scopes(db: Session, user_id: str) -> list[tuple[str, str]]:
    if _is_superadmin(db, user_id):
        return [("*", "*")]
    user = db.get(AuthUser, user_id)
    if user is None or user.status != "active":
        return []
    context = build_auth_context(db, user)
    scopes = _permission_candidate_scopes(db, user_id, IAM_MANAGE_PERMISSIONS)
    return sorted(
        (factory_id, department)
        for factory_id, department in scopes
        if any(can(context, code, factory_id, department) for code in IAM_MANAGE_PERMISSIONS)
    )


def _has_scoped_permission(db: Session, user_id: str, permission_code: str) -> bool:
    user = db.get(AuthUser, user_id)
    if user is None or user.status != "active":
        return False
    context = build_auth_context(db, user)
    return any(
        can(context, permission_code, factory_id, department)
        for factory_id, department in _permission_candidate_scopes(db, user_id, {permission_code})
    )


def _permission_candidate_scopes(
    db: Session,
    user_id: str,
    permission_codes: set[str],
) -> set[tuple[str, str]]:
    role_ids: set[str] = set()
    for code in permission_codes:
        role_ids.update(_role_ids_for_permission(db, code))
    scopes: set[tuple[str, str]] = set()
    for binding in _active_bindings(db, user_id):
        if binding.role_id not in role_ids:
            continue
        system_position = get_system_position(binding.role_id)
        if system_position is None:
            scopes.add((binding.factory_id, binding.department))
            continue

        matching_permission_codes = (
            set(_role_permission_codes(db, binding.role_id)) & permission_codes
        )
        if not matching_permission_codes:
            continue
        metadata = _get_role_metadata(db, binding.role_id)
        scope_mode = _role_scope_mode(metadata, True)

        # Built-in positions are department-independent inside their concrete
        # home factory. A wildcard own-factory binding has no safe anchor and
        # therefore contributes no candidate scope.
        if binding.factory_id != "*":
            scopes.add((binding.factory_id, "*"))

        expands_cross_factory = scope_mode == CROSS_FACTORY_OPERATE_SCOPE or (
            scope_mode == CROSS_FACTORY_READ_SCOPE
            and any(
                _permission_access_kind(db, _permission_by_code(db, code))
                == READ_ACCESS_KIND
                for code in matching_permission_codes
            )
        )
        if expands_cross_factory:
            scopes.update((factory_id, "*") for factory_id in ALLOWED_FACTORY_IDS)
    permission_ids = {
        permission.id
        for permission in db.scalars(
            select(AuthPermission).where(AuthPermission.code.in_(permission_codes))
        ).all()
    }
    scopes.update(
        (item.factory_id, item.department)
        for item in _active_overrides(db, user_id)
        if item.permission_id in permission_ids
    )
    return scopes


def _is_superadmin(
    db: Session,
    user_id: str,
    *,
    excluded_binding_ids: set[str] | None = None,
    added_bindings: list[dict[str, str]] | None = None,
) -> bool:
    excluded_binding_ids = excluded_binding_ids or set()
    roles = {item.id: item for item in db.scalars(select(AuthRole)).all()}
    for binding in _active_bindings(db, user_id):
        role = roles.get(binding.role_id)
        if binding.id not in excluded_binding_ids and role and role.code == "admin" and binding.factory_id == "*" and binding.department in {"*", "system"}:
            return True
    for binding in added_bindings or []:
        role = roles.get(binding["role_id"])
        if role and role.code == "admin" and binding["factory_id"] == "*" and binding["department"] in {"*", "system"}:
            return True
    return False


def _binding_is_superadmin(db: Session, binding: AuthUserRole) -> bool:
    role = db.get(AuthRole, binding.role_id)
    return bool(role and role.code == "admin" and binding.factory_id == "*" and binding.department in {"*", "system"})


def _count_active_superadmins(db: Session) -> int:
    active_user_ids = {
        item.id for item in db.scalars(select(AuthUser).where(AuthUser.status == "active")).all()
    }
    return len({
        binding.user_id
        for binding in _active_bindings(db)
        if binding.user_id in active_user_ids and _binding_is_superadmin(db, binding)
    })


def _active_bindings(db: Session, user_id: str = "") -> list[AuthUserRole]:
    query = select(AuthUserRole)
    if user_id:
        query = query.where(AuthUserRole.user_id == user_id)
    bindings = list(db.scalars(query).all())
    if not bindings:
        return []
    metadata = {
        item.user_role_id: item
        for item in db.scalars(
            select(AuthRoleBindingMetadata).where(
                AuthRoleBindingMetadata.user_role_id.in_([item.id for item in bindings])
            )
        ).all()
    }
    return [
        binding for binding in bindings
        if _metadata_is_effective(metadata.get(binding.id), state_attribute="state")
    ]


def _lifecycle_active_bindings(db: Session, user_id: str = "") -> list[AuthUserRole]:
    query = select(AuthUserRole)
    if user_id:
        query = query.where(AuthUserRole.user_id == user_id)
    bindings = list(db.scalars(query).all())
    if not bindings:
        return []
    metadata = {
        item.user_role_id: item
        for item in db.scalars(
            select(AuthRoleBindingMetadata).where(
                AuthRoleBindingMetadata.user_role_id.in_([item.id for item in bindings])
            )
        ).all()
    }
    return [
        binding
        for binding in bindings
        if metadata.get(binding.id) is None or metadata[binding.id].state == "active"
    ]


def _active_overrides(db: Session, user_id: str) -> list[AuthUserPermissionOverride]:
    overrides = list(
        db.scalars(
            select(AuthUserPermissionOverride).where(AuthUserPermissionOverride.user_id == user_id)
        ).all()
    )
    return [item for item in overrides if _metadata_is_effective(item, state_attribute="status")]


def _lifecycle_active_overrides(db: Session, user_id: str) -> list[AuthUserPermissionOverride]:
    return list(
        db.scalars(
            select(AuthUserPermissionOverride).where(
                AuthUserPermissionOverride.user_id == user_id,
                AuthUserPermissionOverride.status == "active",
            )
        ).all()
    )


def _metadata_is_effective(item: Any | None, state_attribute: str) -> bool:
    if item is None:
        return True
    if getattr(item, state_attribute, "active") != "active":
        return False
    now = datetime.now()
    valid_from = _parse_time(getattr(item, "valid_from", ""))
    valid_until = _parse_time(getattr(item, "valid_until", ""))
    return not (valid_from and valid_from > now) and not (valid_until and valid_until <= now)


def _scope_matches(binding_factory: str, binding_department: str, factory_id: str, department: str) -> bool:
    return binding_factory in {"*", factory_id} and binding_department in {"*", department}


def _scope_is_managed(scopes: list[tuple[str, str]], factory_id: str, department: str) -> bool:
    if not factory_id or not department:
        return False
    return any(_scope_matches(scope_factory, scope_department, factory_id, department) for scope_factory, scope_department in scopes)


def _user_has_managed_binding(db: Session, user_id: str, scopes: list[tuple[str, str]]) -> bool:
    return any(_scope_is_managed(scopes, item.factory_id, item.department) for item in _active_bindings(db, user_id))


def _role_ids_for_permission(db: Session, permission_code: str) -> set[str]:
    permission = _permission_by_code(db, permission_code)
    if permission is None:
        return set()
    return {
        item.role_id
        for item in db.scalars(
            select(AuthRolePermission).where(AuthRolePermission.permission_id == permission.id)
        ).all()
    }


def _role_permission_codes(db: Session, role_id: str) -> list[str]:
    links = list(db.scalars(select(AuthRolePermission).where(AuthRolePermission.role_id == role_id)).all())
    permission_ids = {item.permission_id for item in links}
    if not permission_ids:
        return []
    return sorted(
        item.code for item in db.scalars(select(AuthPermission).where(AuthPermission.id.in_(permission_ids))).all()
    )


def _role_summary(db: Session, role: AuthRole) -> RoleSummaryOut:
    metadata = _get_role_metadata(db, role.id)
    scope_policy = role_scope_policy(role.code)
    system_position = get_system_position(role.id)
    return RoleSummaryOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        version=metadata.version if metadata else 1,
        is_protected=bool(metadata.protected) if metadata else role.code == "admin",
        binding_count=_active_role_binding_count(db, role.id),
        permission_count=len(_role_permission_codes(db, role.id)),
        scope_mode=_role_scope_mode(metadata, system_position is not None),
        applicable_departments=list(scope_policy.departments),
        requires_global_factory=scope_policy.requires_global_factory,
        scope_guidance=scope_policy.guidance,
        is_system_position=system_position is not None,
        is_editable=system_position is None and not (
            bool(metadata.protected) if metadata else role.code == "admin"
        ),
        source="code" if system_position else "database",
        scope_mode_locked=system_position is not None,
        definition_version=(
            SYSTEM_POSITION_DEFINITION_VERSION if system_position else ""
        ),
        definition_hash=(
            system_position_definition_hash(system_position)
            if system_position
            else ""
        ),
        position_department=system_position.department if system_position else "",
        position_department_name=system_position.department_name if system_position else "",
        position_sort_order=system_position.sort_order if system_position else 0,
    )


def _active_role_binding_count(db: Session, role_id: str) -> int:
    return sum(1 for item in _active_bindings(db) if item.role_id == role_id)


def _active_role_binding_ids(db: Session, role_id: str) -> list[str]:
    return sorted(item.id for item in _active_bindings(db) if item.role_id == role_id)


def _active_role_user_ids(db: Session, role_id: str) -> set[str]:
    return {item.user_id for item in _active_bindings(db) if item.role_id == role_id}


def _get_revision(db: Session, user_id: str, *, for_update: bool = False) -> int:
    if for_update:
        item = db.scalar(
            select(AuthUserAuthorizationRevision)
            .where(AuthUserAuthorizationRevision.user_id == user_id)
            .with_for_update()
        )
        if item is None:
            raise HTTPException(
                status_code=409,
                detail="用户授权版本元数据缺失，请重启服务完成初始化后重试",
            )
    else:
        item = db.get(AuthUserAuthorizationRevision, user_id)
    return item.revision if item else 0


def _increment_revision(db: Session, user_id: str) -> int:
    item = db.scalar(
        select(AuthUserAuthorizationRevision)
        .where(AuthUserAuthorizationRevision.user_id == user_id)
        .with_for_update()
    )
    now = now_text()
    if item is None:
        raise HTTPException(
            status_code=409,
            detail="用户授权版本元数据缺失，请重启服务完成初始化后重试",
        )
    item.revision += 1
    item.updated_at = now
    db.flush()
    return item.revision


def _get_role_metadata(
    db: Session,
    role_id: str,
    *,
    for_update: bool = False,
) -> AuthRoleMetadata | None:
    if for_update:
        metadata = db.scalar(
            select(AuthRoleMetadata)
            .where(AuthRoleMetadata.role_id == role_id)
            .with_for_update()
        )
        if metadata is None:
            raise HTTPException(
                status_code=409,
                detail="角色权限模板元数据缺失，请重启服务完成初始化后重试",
            )
        return metadata
    return db.get(AuthRoleMetadata, role_id)


def _ensure_role_metadata(db: Session, role_id: str) -> AuthRoleMetadata:
    item = db.get(AuthRoleMetadata, role_id)
    if item is None:
        now = now_text()
        item = AuthRoleMetadata(
            role_id=role_id,
            version=1,
            protected=0,
            scope_mode=OWN_FACTORY_SCOPE,
            created_at=now,
            updated_at=now,
            updated_by_user_id="",
        )
        db.add(item)
        db.flush()
    return item


def _ensure_binding_metadata(db: Session, user_role_id: str) -> AuthRoleBindingMetadata:
    item = db.get(AuthRoleBindingMetadata, user_role_id)
    if item is None:
        now = now_text()
        item = AuthRoleBindingMetadata(
            user_role_id=user_role_id,
            state="active",
            source_type="legacy_import",
            source_id="",
            valid_from="",
            valid_until="",
            reason="旧系统授权迁移",
            created_by_user_id="",
            approved_by_user_id="",
            revoked_by_user_id="",
            revoked_at="",
            revoke_reason="",
            version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(item)
        db.flush()
    return item


def _permission_by_code(db: Session | None, code: str) -> AuthPermission | None:
    if db is None or not code:
        return None
    return db.scalar(select(AuthPermission).where(AuthPermission.code == code))


def _permissions_by_code(db: Session, codes: list[str]) -> dict[str, AuthPermission]:
    if not codes:
        return {}
    return {
        item.code: item for item in db.scalars(select(AuthPermission).where(AuthPermission.code.in_(codes))).all()
    }


def _permission_status(db: Session, permission: AuthPermission) -> str:
    metadata = db.get(AuthPermissionMetadata, permission.id)
    return metadata.status if metadata else "active"


def _permission_access_kind(db: Session, permission: AuthPermission) -> str:
    metadata = db.get(AuthPermissionMetadata, permission.id)
    if metadata and metadata.access_kind in VALID_ACCESS_KINDS:
        return metadata.access_kind
    return default_permission_access_kind(permission.code)


def _permission_security_snapshot(
    db: Session,
    permissions: dict[str, AuthPermission],
) -> dict[str, dict[str, str]]:
    return {
        code: {
            "status": _permission_status(db, permission),
            "risk_level": _permission_risk(db, permission),
            "access_kind": _permission_access_kind(db, permission),
        }
        for code, permission in sorted(permissions.items())
    }


def _cross_scope_permission_additions_are_high_risk(
    db: Session,
    current_codes: set[str],
    desired_codes: set[str],
    desired_scope_mode: str,
    permissions: dict[str, AuthPermission],
) -> bool:
    added_codes = desired_codes - current_codes
    if not added_codes:
        return False
    if desired_scope_mode == CROSS_FACTORY_OPERATE_SCOPE:
        return True
    if desired_scope_mode != CROSS_FACTORY_READ_SCOPE:
        return False
    return any(
        _permission_access_kind(db, permissions[code]) == READ_ACCESS_KIND
        for code in added_codes
    )


def _role_scope_mode(
    metadata: AuthRoleMetadata | None,
    is_system_position: bool,
) -> str:
    if not is_system_position or metadata is None:
        return OWN_FACTORY_SCOPE
    return metadata.scope_mode if metadata.scope_mode in VALID_SCOPE_MODES else OWN_FACTORY_SCOPE


def _permission_risk(db: Session | None, permission: AuthPermission | None) -> str:
    if permission is None:
        return "high"
    if db is not None:
        metadata = db.get(AuthPermissionMetadata, permission.id)
        if metadata:
            return metadata.risk_level
    _, action = _split_permission_code(permission.code)
    return _infer_risk(permission.code, action)


def _role_is_high_risk(db: Session, role: AuthRole) -> bool:
    metadata = _get_role_metadata(db, role.id)
    if get_system_position(role.id) is not None and _role_scope_mode(metadata, True) != OWN_FACTORY_SCOPE:
        return True
    return role.code == "admin" or any(
        _permission_risk(db, _permission_by_code(db, code)) == "high"
        for code in _role_permission_codes(db, role.id)
    )


def _operations_are_high_risk(db: Session, operations: list[dict[str, Any]]) -> bool:
    for operation in operations:
        if operation.get("kind") == "role_binding":
            role = db.get(AuthRole, operation.get("role_id", ""))
            if role is None or _role_is_high_risk(db, role):
                return True
            continue
        permission = db.get(AuthPermission, operation.get("permission_id", ""))
        if _permission_risk(db, permission) == "high":
            return True
    return False


def _system_position_request_has_drift(
    db: Session,
    target_user_id: str,
    operations: list[dict[str, Any]],
) -> bool:
    context = next(
        (item for item in operations if item.get("system_position_role_id")),
        None,
    )
    if context is None:
        return False
    role = db.get(AuthRole, context["system_position_role_id"])
    system_position = get_system_position(role.id) if role else None
    if role is None or system_position is None:
        return True
    metadata = _get_role_metadata(db, role.id, for_update=True)
    current_version = metadata.version if metadata else 1
    if context.get("system_position_role_version") != current_version:
        return True
    profile = db.get(EmployeeProfile, target_user_id)
    if (
        profile is None
        or profile.primary_factory_id != context.get("profile_primary_factory_id")
        or profile.primary_department != context.get("profile_primary_department")
        or system_position.department != context.get("system_position_department")
    ):
        return True
    return _operations_are_high_risk(db, operations) != bool(
        context.get("system_position_preview_high_risk")
    )


def _request_item_risk(db: Session | None, item: AuthAccessRequestItem) -> str:
    if item.permission_id and db is not None:
        return _permission_risk(db, db.get(AuthPermission, item.permission_id))
    if item.role_id and db is not None:
        role = db.get(AuthRole, item.role_id)
        return "high" if role and _role_is_high_risk(db, role) else "normal"
    return "high"


def _infer_risk(permission_code: str, action: str) -> str:
    high_risk_actions = {"delete", "approve", "export", "manage"}
    tokens = set(action.replace("-", "_").split("_"))
    if permission_code.startswith("system:") or tokens & high_risk_actions or "review" in tokens:
        return "high"
    return "normal"


def _split_permission_code(code: str) -> tuple[str, str]:
    module_code, separator, action = code.partition(":")
    return module_code, action if separator else "manage"


def _validate_scope(factory_id: str, department: str) -> None:
    if not factory_id:
        raise HTTPException(status_code=400, detail="请选择授权厂区")
    if not department:
        raise HTTPException(status_code=400, detail="请选择授权部门")


def _ensure_scope_applicable(
    policy: ScopePolicy,
    factory_id: str,
    department: str,
    *,
    subject: str,
) -> None:
    if scope_is_applicable(policy, factory_id, department):
        return
    guidance = f"；{policy.guidance}" if policy.guidance else ""
    raise HTTPException(
        status_code=400,
        detail=f"{subject} 在当前范围不生效：{factory_id}/{department}{guidance}",
    )


def _ensure_role_permissions_compatible(role: AuthRole, permission_codes: list[str]) -> None:
    role_policy = role_scope_policy(role.code)
    if not role_policy.departments and not role_policy.requires_global_factory:
        return

    incompatible: list[str] = []
    for code in permission_codes:
        permission_policy = permission_scope_policy(code)
        if not permission_policy.departments and not permission_policy.requires_global_factory:
            continue
        if permission_policy.requires_global_factory and not role_policy.requires_global_factory:
            incompatible.append(code)
            continue
        if (
            role_policy.departments
            and permission_policy.departments
            and "*" not in role_policy.departments
            and "*" not in permission_policy.departments
            and not set(role_policy.departments).intersection(permission_policy.departments)
        ):
            incompatible.append(code)

    if incompatible:
        guidance = role_policy.guidance or "角色适用范围与权限适用范围不一致"
        raise HTTPException(
            status_code=400,
            detail=f"角色模板包含范围不相容的权限：{','.join(sorted(incompatible))}；{guidance}",
        )


def _validate_valid_until(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    parsed = _parse_time(value)
    if parsed is None:
        raise HTTPException(status_code=400, detail="授权到期时间格式无效")
    if parsed <= datetime.now():
        raise HTTPException(status_code=400, detail="授权到期时间必须晚于当前时间")
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _required_reason(value: str) -> str:
    reason = value.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="请填写权限变更原因")
    return reason


def _require_writes_enabled() -> None:
    if getattr(settings, "authz_mode", "legacy") != "enforce" or not bool(
        getattr(settings, "authz_writes_enabled", False)
    ):
        raise HTTPException(status_code=503, detail="IAM 权限写入当前未启用")


def _load_user(db: Session, user_id: str) -> AuthUser:
    user = db.get(AuthUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _load_role(db: Session, role_id: str) -> AuthRole:
    role = db.get(AuthRole, role_id)
    if role is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    return role


def _load_access_request(db: Session, request_id: str) -> AuthAccessRequest:
    item = db.scalar(
        select(AuthAccessRequest)
        .where(AuthAccessRequest.id == request_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="权限申请不存在")
    return item


def _request_items(db: Session, request_id: str) -> list[AuthAccessRequestItem]:
    return list(
        db.scalars(
            select(AuthAccessRequestItem)
            .where(AuthAccessRequestItem.request_id == request_id)
            .order_by(AuthAccessRequestItem.created_at, AuthAccessRequestItem.id)
        ).all()
    )


def _latest_registration(db: Session, user_id: str) -> AuthRegistrationRequest | None:
    return db.scalar(
        select(AuthRegistrationRequest)
        .where(AuthRegistrationRequest.user_id == user_id)
        .order_by(AuthRegistrationRequest.updated_at.desc(), AuthRegistrationRequest.created_at.desc())
    )


def _binding_dict(binding: AuthUserRole | None) -> dict[str, Any]:
    if binding is None:
        return {}
    return {
        "id": binding.id,
        "user_id": binding.user_id,
        "role_id": binding.role_id,
        "factory_id": binding.factory_id,
        "department": binding.department,
    }


def _override_dict(item: AuthUserPermissionOverride | None) -> dict[str, Any]:
    if item is None:
        return {}
    return {
        "id": item.id,
        "permission_id": item.permission_id,
        "effect": item.effect,
        "factory_id": item.factory_id,
        "department": item.department,
        "status": item.status,
        "valid_until": item.valid_until,
    }


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
