from collections.abc import Iterable
from dataclasses import replace
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.auth import (
    AuthContext,
    add_auth_audit,
    authorization_decision,
    can,
    legacy_has_permission_in_scope,
    system_position_grant_department_matches,
    system_position_grant_scope_source,
)


ENGINEERING_DEPARTMENTS = ("engineering",)
PRODUCTION_DEPARTMENTS = ("production", "molding")
WAREHOUSE_DEPARTMENTS = ("pmc-warehouse", "warehouse")
MANAGEMENT_DEPARTMENTS = ("management",)
SHARED_MOLDING_DEPARTMENTS = (
    *ENGINEERING_DEPARTMENTS,
    *PRODUCTION_DEPARTMENTS,
    *WAREHOUSE_DEPARTMENTS,
    *MANAGEMENT_DEPARTMENTS,
)
CROSS_FACTORY_DEPARTMENTS = ("*", *SHARED_MOLDING_DEPARTMENTS)

MOLDING_CROSS_FACTORY_READ_PERMISSION = "molding_sample:cross_factory_read"
MOLDING_CROSS_FACTORY_COST_PERMISSION = "molding_sample:cross_factory_cost_read"
logger = logging.getLogger(__name__)


def is_wildcard_super_admin(user: AuthContext) -> bool:
    return any(
        grant.role_code == "admin"
        and grant.factory_id == "*"
        and grant.department in {"*", "system"}
        for grant in user.grants
    )


def is_local_factory(user: AuthContext, factory_id: str) -> bool:
    if is_wildcard_super_admin(user):
        return True

    primary_factory_id = user.profile.primary_factory_id.strip() if user.profile else ""
    if primary_factory_id:
        return primary_factory_id == factory_id

    # Historical users without a confirmed employee profile keep their exact
    # factory binding as a compatibility fallback. Wildcard bindings are not
    # treated as a normal local organization unless they are the protected
    # wildcard administrator handled above.
    return any(grant.factory_id == factory_id for grant in user.grants)


def ensure_molding_local_write(db: Session, user: AuthContext, factory_id: str) -> None:
    read_source = molding_read_access(user, factory_id)
    if read_source in {"local", "cross_operate"}:
        return

    reason = (
        f"本厂啤办单未获本地读取授权，禁止写入：{factory_id}"
        if is_local_factory(user, factory_id)
        else f"未配置跨厂操作范围，禁止写入外厂啤办单：{factory_id}"
    )
    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=reason,
    )
    db.commit()
    raise HTTPException(status_code=403, detail="啤办单仅允许查看，不能写入")


def canonical_permission_for_departments(
    user: AuthContext,
    permission: str,
    factory_id: str,
    departments: Iterable[str],
) -> bool:
    normalized_departments = tuple(dict.fromkeys(departments))
    if permission in {
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
        MOLDING_CROSS_FACTORY_COST_PERMISSION,
    }:
        return can(user, permission, factory_id, None)
    return any(can(user, permission, factory_id, department) for department in normalized_departments)


def has_permission_for_departments(
    user: AuthContext,
    permission: str,
    factory_id: str,
    departments: Iterable[str],
) -> bool:
    normalized_departments = tuple(dict.fromkeys(departments))
    canonical_result = canonical_permission_for_departments(
        user,
        permission,
        factory_id,
        normalized_departments,
    )
    # A wildcard super-admin is authorized canonically even when the protected
    # admin role template does not persist every newly introduced permission.
    # Do not let the legacy compatibility fallback downgrade that decision.
    if canonical_result and is_wildcard_super_admin(user):
        return True
    if settings.authz_mode == "enforce":
        return canonical_result

    # Existing business endpoints historically checked only the factory. Keep
    # that behavior in legacy/shadow so a safe rollout does not silently remove
    # access before department mappings have been compared and approved.
    # The warehouse manager's newly expanded scope must retain its PMC inbox
    # and notification boundaries even before enforcement is enabled. Filter
    # only that position; other independent grants keep legacy behavior.
    legacy_user = replace(user, grants=tuple(
        grant for grant in user.grants
        if grant.role_id != "position_warehouse_manager"
        or not grant.unrestricted_department
        or any(
            system_position_grant_department_matches(grant, permission, department)
            for department in normalized_departments
        )
    ))
    legacy_result = legacy_has_permission_in_scope(legacy_user, permission, factory_id, None)
    if settings.authz_mode == "shadow" and legacy_result != canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s permission=%s scope=%s/%s legacy=%s canonical=%s",
            user.id,
            permission,
            factory_id,
            "|".join(normalized_departments),
            legacy_result,
            canonical_result,
        )
    return legacy_result


def ensure_permission_for_departments(
    db: Session,
    user: AuthContext,
    permission: str,
    factory_id: str,
    departments: Iterable[str],
) -> None:
    normalized_departments = tuple(dict.fromkeys(departments))
    if has_permission_for_departments(user, permission, factory_id, normalized_departments):
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=(
            f"缺少授权范围内权限：{permission}@{factory_id}/"
            f"{'|'.join(normalized_departments) or '*'}"
        ),
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无授权范围内操作权限")


def canonical_molding_read_access(user: AuthContext, factory_id: str) -> str | None:
    if canonical_local_molding_read_access(user, factory_id):
        return "local"
    cross_sources: list[str] = []
    for permission, departments in (
        ("molding_sample:read", SHARED_MOLDING_DEPARTMENTS),
        ("molding_sample:production_read", PRODUCTION_DEPARTMENTS),
    ):
        for department in departments:
            allowed, source_type, _, _ = authorization_decision(
                user,
                permission,
                factory_id,
                department,
            )
            if allowed:
                cross_sources.append(source_type)
    if "role_binding_cross_operate" in cross_sources:
        return "cross_operate"
    if cross_sources:
        return "cross"
    allowed, source_type, _, _ = authorization_decision(
        user,
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
        factory_id,
        None,
    )
    if allowed:
        return "cross_operate" if source_type == "role_binding_cross_operate" else "cross"
    return None


def legacy_molding_read_access(user: AuthContext, factory_id: str) -> str | None:
    if legacy_local_molding_read_access(user, factory_id):
        return "local"
    for permission in (
        "molding_sample:read",
        "molding_sample:production_read",
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
    ):
        if not legacy_has_permission_in_scope(user, permission, factory_id, None):
            continue
        if any(
            permission in grant.permissions
            and system_position_grant_scope_source(grant, permission, factory_id)
            == "cross_operate"
            for grant in user.grants
        ):
            return "cross_operate"
        return "cross"
    return None


def canonical_local_molding_read_access(user: AuthContext, factory_id: str) -> bool:
    return is_local_factory(user, factory_id) and (
        canonical_permission_for_departments(
            user,
            "molding_sample:read",
            factory_id,
            SHARED_MOLDING_DEPARTMENTS,
        )
        or canonical_permission_for_departments(
            user,
            "molding_sample:production_read",
            factory_id,
            PRODUCTION_DEPARTMENTS,
        )
    )


def legacy_local_molding_read_access(user: AuthContext, factory_id: str) -> bool:
    return is_local_factory(user, factory_id) and (
        legacy_has_permission_in_scope(user, "molding_sample:read", factory_id, None)
        or legacy_has_permission_in_scope(user, "molding_sample:production_read", factory_id, None)
    )


def local_molding_read_access(user: AuthContext, factory_id: str) -> bool:
    canonical_result = canonical_local_molding_read_access(user, factory_id)
    if settings.authz_mode == "enforce":
        return canonical_result

    legacy_result = legacy_local_molding_read_access(user, factory_id)
    if settings.authz_mode == "shadow" and legacy_result != canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s resource=molding_sample_local_read scope=%s legacy=%s canonical=%s",
            user.id,
            factory_id,
            legacy_result,
            canonical_result,
        )
    return legacy_result


def molding_read_access(user: AuthContext, factory_id: str) -> str | None:
    canonical_result = canonical_molding_read_access(user, factory_id)
    if settings.authz_mode == "enforce":
        return canonical_result

    legacy_result = legacy_molding_read_access(user, factory_id)
    if settings.authz_mode == "shadow" and legacy_result != canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s resource=molding_sample scope=%s legacy_source=%s canonical_source=%s",
            user.id,
            factory_id,
            legacy_result or "deny",
            canonical_result or "deny",
        )
    return legacy_result


def ensure_molding_read(db: Session, user: AuthContext, factory_id: str) -> str:
    read_source = molding_read_access(user, factory_id)
    if read_source is not None:
        return read_source

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"缺少啤办单读取权限：{factory_id}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="无该厂区啤办单查看权限")


def has_general_molding_read_access(user: AuthContext, factory_id: str) -> bool:
    """Return whether the user may browse engineering-stage molding records."""
    return has_permission_for_departments(
        user,
        "molding_sample:read",
        factory_id,
        SHARED_MOLDING_DEPARTMENTS,
    ) or has_permission_for_departments(
        user,
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    )


def ensure_general_molding_read(db: Session, user: AuthContext, factory_id: str) -> None:
    ensure_molding_read(db, user, factory_id)
    if has_general_molding_read_access(user, factory_id):
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"仅获生产任务只读权限，禁止读取工程阶段啤办单：{factory_id}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="当前账号仅可查看正式生产任务")


def can_view_molding_cost(user: AuthContext, factory_id: str, read_source: str | None = None) -> bool:
    source = read_source or molding_read_access(user, factory_id)
    if source == "local":
        return True
    if source not in {"cross", "cross_operate"}:
        return False
    return has_permission_for_departments(
        user,
        MOLDING_CROSS_FACTORY_COST_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    )
