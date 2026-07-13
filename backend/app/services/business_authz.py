from collections.abc import Iterable
import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.auth import AuthContext, add_auth_audit, can, legacy_has_permission_in_scope


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
    canonical_result = is_local_factory(user, factory_id)
    if settings.authz_mode == "shadow" and not canonical_result:
        logger.warning(
            "authz shadow mismatch user=%s resource=molding_sample_write scope=%s legacy=True canonical=False",
            user.id,
            factory_id,
        )
    if settings.authz_mode != "enforce" or canonical_result:
        return

    add_auth_audit(
        db,
        "permission_denied",
        username=user.username,
        user_id=user.id,
        detail=f"外厂啤办单只允许查看，禁止写入：{factory_id}",
    )
    db.commit()
    raise HTTPException(status_code=403, detail="其他厂区啤办单仅允许查看")


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
    if (
        permission.startswith("molding_sample:")
        and not is_local_factory(user, factory_id)
    ):
        return False
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
    if settings.authz_mode == "enforce":
        return canonical_result

    # Existing business endpoints historically checked only the factory. Keep
    # that behavior in legacy/shadow so a safe rollout does not silently remove
    # access before department mappings have been compared and approved.
    legacy_result = legacy_has_permission_in_scope(user, permission, factory_id, None)
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
    if is_local_factory(user, factory_id):
        if canonical_permission_for_departments(
            user,
            "molding_sample:read",
            factory_id,
            SHARED_MOLDING_DEPARTMENTS,
        ) or canonical_permission_for_departments(
            user,
            "molding_sample:production_read",
            factory_id,
            PRODUCTION_DEPARTMENTS,
        ):
            return "local"
    if canonical_permission_for_departments(
        user,
        MOLDING_CROSS_FACTORY_READ_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    ):
        return "cross"
    return None


def legacy_molding_read_access(user: AuthContext, factory_id: str) -> str | None:
    if legacy_has_permission_in_scope(user, "molding_sample:read", factory_id, None):
        return "local"
    if legacy_has_permission_in_scope(user, MOLDING_CROSS_FACTORY_READ_PERMISSION, factory_id, None):
        return "cross"
    return None


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


def can_view_molding_cost(user: AuthContext, factory_id: str, read_source: str | None = None) -> bool:
    source = read_source or molding_read_access(user, factory_id)
    if source == "local":
        return True
    if source != "cross":
        return False
    return has_permission_for_departments(
        user,
        MOLDING_CROSS_FACTORY_COST_PERMISSION,
        factory_id,
        CROSS_FACTORY_DEPARTMENTS,
    )
