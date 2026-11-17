"""Retire injection scheduling V3 and all earlier table families and its operational permissions.

Revision ID: 20261116_inj_retire
Revises: 20261107_0193

Requires a verified full database backup. Shared authorization audit snapshots
remain system history; account data and unrelated domain records are preserved.
"""

import json
import re

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError

revision = "20261116_inj_retire"
down_revision = "20261107_0193"
branch_labels = None
depends_on = None

TABLE_PREFIXES = ("injection_v3_", "injection_schedule_", "injection_scheduling_", "injection_ops_")
PERMISSION_PREFIXES = (
    "injection_schedule_center:",
    "injection_scheduling:",
    "production:injection_scheduling:",
    "injection_ops:",
)
GUARD_FUNCTIONS = (
    "injection_ops_immutable_event",
    "reject_injection_schedule_audit_mutation",
    "reject_injection_scheduling_audit_mutation",
    "reject_injection_scheduling_phase3_mutation",
    "guard_injection_scheduling_published_plan",
    "guard_injection_scheduling_published_task",
    "guard_injection_scheduling_phase4_import",
    "guard_injection_scheduling_published_task_lineage",
    "guard_injection_scheduling_phase2_append_only",
    "guard_injection_scheduling_takeover_baseline",
    "reject_inj_sched_export_audit_mutation",
    "reject_injection_schedule_audit_events_mutation_0085",
    "reject_is_calculation_mutation_0092",
    "reject_is_phase5_mutation_0093",
    "reject_is_version_mutation_0094",
    "reject_is_command_mutation_0094",
)


def _drop_order(inspector, table_names):
    sqlite = inspector.bind.dialect.name == "sqlite"
    normalize = str.casefold if sqlite else str
    targets = {name for name in table_names if normalize(name).startswith(TABLE_PREFIXES)}
    if not targets:
        return []
    canonical = {normalize(name): name for name in targets}
    foreign_keys = {
        name: {canonical[normalize(fk["referred_table"])] for fk in inspector.get_foreign_keys(name)
               if fk["referred_table"] and normalize(fk["referred_table"]) in canonical}
        for name in table_names
    }
    for name in sorted(set(table_names) - targets):
        if foreign_keys[name]:
            raise CommandError(f"Refusing injection purge: unrelated table {name} references {sorted(foreign_keys[name])}.")
    remaining = set(targets)
    order = []
    while remaining:
        parents = {parent for name in remaining for parent in foreign_keys[name] & remaining if parent != name}
        children = sorted(remaining - parents)
        if not children:
            raise CommandError("Refusing injection purge: cyclic table dependencies.")
        order.extend(children)
        remaining.difference_update(children)
    return order


def _view_preflight(connection, inspector, targets):
    sqlite = connection.dialect.name == "sqlite"
    views = inspector.get_view_names()
    owned = {name for name in views if (name.casefold() if sqlite else name).startswith(TABLE_PREFIXES)}
    identifiers = targets | owned
    if not identifiers:
        return []
    pattern = re.compile(r"(?<!\w)(?:" + "|".join(map(re.escape, identifiers)) + r")(?!\w)",
                         flags=re.IGNORECASE if sqlite else 0)
    definitions = {name: inspector.get_view_definition(name) or "" for name in views}
    for name in set(views) - owned:
        if pattern.search(definitions[name]):
            raise CommandError(f"Refusing injection purge: unrelated view {name} references retired data.")
    if sqlite:
        removed_owners = {name.casefold() for name in identifiers}
        for name, owner, sql in connection.exec_driver_sql(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'"
        ):
            if owner.casefold() not in removed_owners and pattern.search(sql or ""):
                raise CommandError(f"Refusing injection purge: unrelated trigger {name} references retired data.")
        return sorted(owned)

    # PostgreSQL requires dependent views to be removed before their sources.
    order = []
    while owned:
        parents = {other for name in owned for other in pattern.findall(definitions[name]) if other in owned and other != name}
        leaves = sorted(owned - parents)
        if not leaves:
            raise CommandError("Refusing injection purge: cyclic view dependencies.")
        order.extend(leaves)
        owned.difference_update(leaves)
    return order


def _preview_uses_retired_permission(payload, permission_ids):
    def matches(value):
        return isinstance(value, str) and (value in permission_ids or
            (value.startswith(PERMISSION_PREFIXES) and re.fullmatch(r"[\w:-]+", value) is not None))

    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except ValueError:
            return matches(payload)
    if isinstance(payload, str):
        return matches(payload)
    if not isinstance(payload, dict):
        return False
    codes = payload.get("permission_codes", [])
    operations = payload.get("operations", [])
    return ((isinstance(codes, list) and any(matches(code) for code in codes)) or
            (isinstance(operations, list) and any(
                isinstance(item, dict) and (matches(item.get("permission_code")) or matches(item.get("permission_id")))
                for item in operations
            )))


def _purge_permissions(connection, table_names):
    metadata = sa.MetaData()

    def table(name):
        if name not in table_names:
            return None
        return sa.Table(name, metadata, autoload_with=connection)

    permissions = table("auth_permissions")
    permission_ids = [] if permissions is None else list(connection.scalars(
        sa.select(permissions.c.id).where(sa.or_(
            *(permissions.c.code.startswith(prefix, autoescape=True)
              for prefix in PERMISSION_PREFIXES)
        ))
    ))
    role_grants = table("auth_role_permissions")
    overrides = table("auth_user_permission_overrides")
    user_roles = table("auth_user_roles")
    role_ids = set()
    user_ids = set()
    if permission_ids and role_grants is not None:
        role_ids.update(connection.scalars(sa.select(role_grants.c.role_id).where(
            role_grants.c.permission_id.in_(permission_ids)
        )))
    if role_ids and user_roles is not None:
        user_ids.update(connection.scalars(sa.select(user_roles.c.user_id).where(
            user_roles.c.role_id.in_(role_ids)
        )))
    if permission_ids and overrides is not None:
        user_ids.update(connection.scalars(sa.select(overrides.c.user_id).where(
            overrides.c.permission_id.in_(permission_ids)
        )))

    request_items = table("auth_access_request_items")
    requests = table("auth_access_requests")
    affected_requests = []
    if permission_ids and request_items is not None:
        affected_requests = list(connection.scalars(sa.select(request_items.c.request_id).where(
            request_items.c.permission_id.in_(permission_ids)
        )))
    if permission_ids:
        for name in (
            "auth_access_request_items",
            "auth_user_permission_overrides",
            "auth_role_permissions",
            "auth_permission_metadata",
        ):
            item = table(name)
            if item is not None:
                connection.execute(item.delete().where(item.c.permission_id.in_(permission_ids)))
        connection.execute(permissions.delete().where(permissions.c.id.in_(permission_ids)))

    if affected_requests and requests is not None:
        # A mixed request keeps its unrelated items and remains reviewable.
        connection.execute(requests.update().where(
            requests.c.id.in_(affected_requests),
            requests.c.status == "pending",
            ~sa.exists(sa.select(request_items.c.id).where(request_items.c.request_id == requests.c.id)),
        ).values(
            status="rejected",
            decision_comment="注塑排产模块及数据已清理，相关权限申请已关闭",
            decided_at=sa.func.current_timestamp(),
            updated_at=sa.func.current_timestamp(),
        ))

    previews = table("auth_authorization_previews")
    if previews is not None:
        ids = set(permission_ids)
        affected = [ident for ident, payload in connection.execute(sa.select(previews.c.id, previews.c.payload_json))
                    if _preview_uses_retired_permission(payload, ids)]
        for offset in range(0, len(affected), 500):
            connection.execute(previews.delete().where(previews.c.id.in_(affected[offset:offset + 500])))
    state = table("auth_iam_state")
    if state is not None:
        connection.execute(state.delete().where(sa.or_(
            *(state.c.key.startswith(marker, autoescape=True)
              for marker in (*TABLE_PREFIXES, *PERMISSION_PREFIXES))
        )))
    roles = table("auth_role_metadata")
    if role_ids and roles is not None:
        connection.execute(roles.update().where(roles.c.role_id.in_(role_ids)).values(
            version=roles.c.version + 1, updated_at=sa.func.current_timestamp(),
        ))
    revisions = table("auth_user_authorization_revisions")
    if user_ids and revisions is not None:
        connection.execute(revisions.update().where(revisions.c.user_id.in_(user_ids)).values(
            revision=revisions.c.revision + 1, updated_at=sa.func.current_timestamp(),
        ))


def upgrade():
    if context.is_offline_mode():
        raise CommandError("Injection data purge requires online dependency inspection and a verified backup.")
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        # pysqlite otherwise autocommits DDL before its first DML statement.
        if not connection.connection.driver_connection.in_transaction:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    inspector = sa.inspect(connection)
    table_names = inspector.get_table_names()
    order = _drop_order(inspector, table_names)
    views = _view_preflight(connection, inspector, set(order))
    _purge_permissions(connection, table_names)
    for name in views:
        quoted = connection.dialect.identifier_preparer.quote(name)
        connection.exec_driver_sql(f"DROP VIEW {quoted}")
    for name in order:
        op.drop_table(name)
    if connection.dialect.name == "postgresql":
        for name in GUARD_FUNCTIONS:
            # Never CASCADE into an unrelated object.
            op.execute(sa.text(f'DROP FUNCTION IF EXISTS "{name}"()'))


def downgrade():
    raise CommandError(
        "20261116_inj_retire permanently removes retired injection-scheduling data. "
        "Restore a verified pre-purge backup; a downgrade cannot recreate business records."
    )
