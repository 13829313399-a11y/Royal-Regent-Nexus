import json
from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth import (
    AuthAuthorizationEvent,
    AuthIamState,
    AuthPermission,
    AuthRole,
    AuthRoleBindingMetadata,
    AuthRoleMetadata,
    AuthRolePermission,
    AuthUserAuthorizationRevision,
    AuthUserRole,
)
from app.services.system_positions import (
    SYSTEM_POSITION_DEFINITIONS,
    SYSTEM_POSITION_DEFINITION_VERSION,
    system_position_catalog_hash,
    system_position_definition_hash,
    validate_system_position_definitions,
)


SYSTEM_POSITION_CATALOG_STATE_KEY = "system_position_catalog_definition_v1"
SYSTEM_POSITION_RECONCILE_ACTOR_ID = "system"


@dataclass(frozen=True)
class SystemPositionReconcileResult:
    changed_role_ids: tuple[str, ...]
    changed_user_ids: tuple[str, ...]
    catalog_hash: str


def _parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _binding_is_active(
    metadata: AuthRoleBindingMetadata | None,
    checked_at: datetime,
) -> bool:
    if metadata is None:
        return True
    if metadata.state != "active":
        return False
    valid_from = _parse_time(metadata.valid_from)
    valid_until = _parse_time(metadata.valid_until)
    if valid_from is not None and checked_at < valid_from:
        return False
    if valid_until is not None and checked_at >= valid_until:
        return False
    return True


def reconcile_system_position_catalog(
    db: Session,
    *,
    now: str | None = None,
) -> SystemPositionReconcileResult:
    """Project fixed system-position definitions into IAM tables atomically.

    The caller owns the outer transaction. A savepoint protects this complete
    projection if the caller catches an exception and continues using the same
    session.
    """

    timestamp = now or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with db.begin_nested():
        return _reconcile_system_position_catalog(db, timestamp)


def _reconcile_system_position_catalog(
    db: Session,
    timestamp: str,
) -> SystemPositionReconcileResult:
    validate_system_position_definitions()

    state = db.get(AuthIamState, SYSTEM_POSITION_CATALOG_STATE_KEY)
    applied_state: dict[str, object] = {}
    if state is not None and state.value_json:
        try:
            decoded_state = json.loads(state.value_json)
            if isinstance(decoded_state, dict):
                applied_state = decoded_state
        except (TypeError, ValueError):
            # A corrupt or legacy state value must fail safe by treating every
            # definition as unapplied. The exact catalog projection below will
            # repair the state and produce version/audit changes.
            applied_state = {}
    raw_role_hashes = applied_state.get("role_hashes", {})
    applied_role_hashes = (
        {
            str(role_id): str(definition_hash)
            for role_id, definition_hash in raw_role_hashes.items()
            if isinstance(role_id, str) and isinstance(definition_hash, str)
        }
        if isinstance(raw_role_hashes, dict)
        else {}
    )
    applied_definition_version = str(
        applied_state.get("definition_version", "")
    )

    permission_rows = list(
        db.scalars(select(AuthPermission).order_by(AuthPermission.code)).all()
    )
    permissions_by_code = {item.code: item for item in permission_rows}
    permissions_by_id = {item.id: item for item in permission_rows}
    referenced_codes = {
        code
        for definition in SYSTEM_POSITION_DEFINITIONS
        for code in definition.permission_codes
    }
    missing_codes = sorted(referenced_codes - set(permissions_by_code))
    if missing_codes:
        raise RuntimeError(
            "系统内置职位同步失败，权限目录缺少：" + ",".join(missing_codes)
        )

    changed_role_ids: set[str] = set()
    role_before_after: dict[str, tuple[dict[str, object], dict[str, object]]] = {}

    for definition in SYSTEM_POSITION_DEFINITIONS:
        definition_hash = system_position_definition_hash(definition)
        previous_definition_hash = applied_role_hashes.get(definition.role_id, "")
        definition_changed = previous_definition_hash != definition_hash
        role = db.get(AuthRole, definition.role_id)
        role_created = role is None
        if role is None:
            role = AuthRole(
                id=definition.role_id,
                code=definition.role_id,
                name=definition.name,
                description=definition.description,
            )
            db.add(role)
            db.flush()

        metadata = db.get(AuthRoleMetadata, definition.role_id)
        metadata_created = metadata is None
        before_scope_mode = metadata.scope_mode if metadata else ""
        before_version = metadata.version if metadata else 0
        before_protected = bool(metadata.protected) if metadata else False

        existing_links = list(
            db.scalars(
                select(AuthRolePermission).where(
                    AuthRolePermission.role_id == definition.role_id
                )
            ).all()
        )
        before_permission_codes = sorted(
            {
                permissions_by_id[item.permission_id].code
                for item in existing_links
                if item.permission_id in permissions_by_id
            }
        )
        before = {
            "code": role.code if not role_created else "",
            "name": role.name if not role_created else "",
            "description": role.description if not role_created else "",
            "permission_codes": before_permission_codes,
            "scope_mode": before_scope_mode,
            "protected": before_protected,
            "version": before_version,
            "definition_version": applied_definition_version,
            "definition_hash": previous_definition_hash,
        }

        # Some code-owned fields (department labels, ordering and definition
        # version) are intentionally derived rather than persisted on AuthRole.
        # Their stable hash still represents a real template change and must
        # invalidate previews, refresh bound sessions and leave an audit trail.
        role_changed = role_created or definition_changed
        if role.code != definition.role_id:
            role.code = definition.role_id
            role_changed = True
        if role.name != definition.name:
            role.name = definition.name
            role_changed = True
        if role.description != definition.description:
            role.description = definition.description
            role_changed = True

        desired_permission_ids = {
            permissions_by_code[code].id for code in definition.permission_codes
        }
        links_by_permission_id: dict[str, list[AuthRolePermission]] = {}
        for link in existing_links:
            links_by_permission_id.setdefault(link.permission_id, []).append(link)

        for permission_id, links in links_by_permission_id.items():
            if permission_id not in desired_permission_ids:
                for link in links:
                    db.delete(link)
                role_changed = True
                continue
            for duplicate_link in links[1:]:
                db.delete(duplicate_link)
                role_changed = True

        existing_permission_ids = set(links_by_permission_id)
        for permission_code in definition.permission_codes:
            permission = permissions_by_code[permission_code]
            if permission.id in existing_permission_ids:
                continue
            db.add(
                AuthRolePermission(
                    id=f"{definition.role_id}:{permission.id}",
                    role_id=definition.role_id,
                    permission_id=permission.id,
                )
            )
            role_changed = True

        if metadata is None:
            metadata = AuthRoleMetadata(
                role_id=definition.role_id,
                version=1,
                protected=0,
                scope_mode=definition.scope_mode,
                created_at=timestamp,
                updated_at=timestamp,
                updated_by_user_id=SYSTEM_POSITION_RECONCILE_ACTOR_ID,
            )
            db.add(metadata)
            role_changed = True
        else:
            if metadata.scope_mode != definition.scope_mode:
                metadata.scope_mode = definition.scope_mode
                role_changed = True
            if metadata.protected:
                metadata.protected = 0
                role_changed = True

        if role_changed:
            if role_created and metadata_created and not previous_definition_hash:
                # Brand-new catalog rows start at version 1.
                metadata.version = 1
            else:
                # Existing roles without metadata were previously exposed as
                # version 1 by the API. Start at 2 so historical previews cannot
                # survive metadata repair or a reconstructed role row.
                metadata.version = max(before_version, 1) + 1
            metadata.updated_at = timestamp
            metadata.updated_by_user_id = SYSTEM_POSITION_RECONCILE_ACTOR_ID
            changed_role_ids.add(definition.role_id)
            after = {
                "code": definition.role_id,
                "name": definition.name,
                "description": definition.description,
                "permission_codes": sorted(definition.permission_codes),
                "scope_mode": definition.scope_mode,
                "protected": False,
                "version": metadata.version,
                "definition_version": SYSTEM_POSITION_DEFINITION_VERSION,
                "definition_hash": definition_hash,
            }
            role_before_after[definition.role_id] = (before, after)

    changed_user_ids: set[str] = set()
    if changed_role_ids:
        bindings = list(
            db.scalars(
                select(AuthUserRole).where(
                    AuthUserRole.role_id.in_(sorted(changed_role_ids))
                )
            ).all()
        )
        binding_ids = [item.id for item in bindings]
        binding_metadata_by_id = {
            item.user_role_id: item
            for item in (
                db.scalars(
                    select(AuthRoleBindingMetadata).where(
                        AuthRoleBindingMetadata.user_role_id.in_(binding_ids)
                    )
                ).all()
                if binding_ids
                else []
            )
        }
        checked_at = _parse_time(timestamp) or datetime.now()
        changed_user_ids = {
            binding.user_id
            for binding in bindings
            if _binding_is_active(
                binding_metadata_by_id.get(binding.id),
                checked_at,
            )
        }
        for user_id in sorted(changed_user_ids):
            revision = db.get(AuthUserAuthorizationRevision, user_id)
            if revision is None:
                db.add(
                    AuthUserAuthorizationRevision(
                        user_id=user_id,
                        revision=1,
                        updated_at=timestamp,
                    )
                )
            else:
                revision.revision += 1
                revision.updated_at = timestamp

        for role_id in sorted(changed_role_ids):
            before, after = role_before_after[role_id]
            db.add(
                AuthAuthorizationEvent(
                    id=f"authz-event-{uuid4().hex}",
                    actor_user_id=SYSTEM_POSITION_RECONCILE_ACTOR_ID,
                    target_user_id="",
                    event_type="system_position_reconciled",
                    target_type="role",
                    target_id=role_id,
                    permission_id="",
                    effect="",
                    factory_id="",
                    department="",
                    before_json=json.dumps(
                        before,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    after_json=json.dumps(
                        after,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    reason="系统内置职位按代码固定定义自动同步",
                    ip_address="",
                    user_agent="",
                    access_request_id="",
                    created_at=timestamp,
                )
            )

    catalog_hash = system_position_catalog_hash()
    state_value = json.dumps(
        {
            "definition_version": SYSTEM_POSITION_DEFINITION_VERSION,
            "catalog_hash": catalog_hash,
            "role_hashes": {
                item.role_id: system_position_definition_hash(item)
                for item in SYSTEM_POSITION_DEFINITIONS
            },
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    if state is None:
        db.add(
            AuthIamState(
                key=SYSTEM_POSITION_CATALOG_STATE_KEY,
                value_json=state_value,
                updated_at=timestamp,
            )
        )
    elif state.value_json != state_value:
        state.value_json = state_value
        state.updated_at = timestamp

    db.flush()
    return SystemPositionReconcileResult(
        changed_role_ids=tuple(sorted(changed_role_ids)),
        changed_user_ids=tuple(sorted(changed_user_ids)),
        catalog_hash=catalog_hash,
    )
