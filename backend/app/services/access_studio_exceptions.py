"""Personal exceptions are individual, named sources. Never replace a matching scope."""
from sqlalchemy import select
from app.models.auth import AuthPermission, AuthUserPermissionOverride, EmployeeProfile
from app.services import iam
from app.services.identity_policy import fail
from app.services.identity_resolver import instant, utc_now
from app.services.identity_sources import source_is_active


def plan_exceptions(db, actor, user, edits, scopes):
    if not (edits.add_overrides or edits.end_override_ids):
        return []
    # The legacy scope validator accepts local wall-clock timestamps.
    inputs = [item.model_copy(update={"valid_until": instant(item.valid_until).astimezone().strftime("%Y-%m-%d %H:%M:%S")})
              if item.valid_until else item for item in edits.add_overrides]
    additions = iam._normalize_user_operations(db, user.id, [], inputs, "", "")
    existing = list(db.scalars(select(AuthUserPermissionOverride).where(
        AuthUserPermissionOverride.user_id == user.id, AuthUserPermissionOverride.status == "active")))
    now = utc_now()
    profile = db.get(EmployeeProfile, user.id)
    current = {o.id: o for o in existing if (not o.valid_until or instant(o.valid_until) > now) and
               source_is_active(db, o, profile, max(now, instant(o.valid_from) or now))}
    operations = []
    for override_id in edits.end_override_ids:
        override = current.get(override_id)
        if not override:
            fail("SOURCE_CHANGED", "所选例外已结束或不属于该人员的当前雇佣周期")
        permission = db.get(AuthPermission, override.permission_id)
        operations.append(dict(kind="permission_override", operation="end", override_id=override.id,
            permission_id=permission.id, permission_code=permission.code, effect="inherit",
            factory_id=override.factory_id, department=override.department, risk_level=iam._permission_risk(db, permission)))
    for item in additions:
        if any((o.permission_id, o.effect, o.factory_id, o.department) ==
               (item["permission_id"], item["effect"], item["factory_id"], item["department"])
               and (not item["valid_until"] or not o.valid_from or instant(item["valid_until"]) > instant(o.valid_from))
               and o.id not in edits.end_override_ids for o in current.values()):
            fail("DUPLICATE_OVERRIDE", "此范围已有相同个人例外，请明确选择需要结束的来源", 422)
    operations.extend(additions)
    if not operations:
        return []
    iam._ensure_iam_manager(db, actor)
    is_admin = iam._is_superadmin(db, actor.id)
    iam._validate_supplier_material_operations(db, user.id, operations, is_admin)
    managed = iam._manager_scopes(db, actor.id)
    for item in operations:
        factory, department = item["factory_id"], item["department"]
        if not is_admin and (item["permission_code"].startswith("carton_supplier:")
                or item["risk_level"] == "high" or not iam._scope_is_managed(managed, factory, department)):
            fail("OUTSIDE_MANAGEABLE_SCOPE", "该个人例外须由覆盖对应范围的集团管理员办理", 403)
        scopes.append((factory, factory, department))
    return operations


def apply_exceptions(db, actor, row, plan, evidence):
    for index, item in enumerate(plan["dependencies"].get("exception_edits", [])):
        at = plan["effective"]
        if item["operation"] == "end":
            override = db.get(AuthUserPermissionOverride, item["override_id"])
            before = {"override_id": override.id, "valid_until": override.valid_until, "effect": override.effect}
            if override.valid_from and instant(override.valid_from) >= instant(at):
                override.status = "revoked"
            else:
                override.valid_until = at
            override.revoked_at, override.updated_at = at, at
            override.revoked_by_user_id, override.revoke_reason = actor.id, row.reason
            evidence.setdefault("ended_overrides", []).append({**before, "ended_at": at})
        else:
            override = AuthUserPermissionOverride(id=f"upo-{row.id}-{index}", user_id=row.target_user_id,
                permission_id=item["permission_id"], effect=item["effect"], factory_id=item["factory_id"],
                department=item["department"], valid_from=at, valid_until=item["valid_until"], status="active",
                employment_epoch=plan["profile"].employment_epoch, lifecycle_policy="independent",
                reason=row.reason, source_type="access_request", source_id=row.id, created_by_user_id=row.requester_user_id,
                approved_by_user_id=actor.id, created_at=at, updated_at=at)
            db.add(override)
            evidence.setdefault("added_overrides", []).append(override.id)
