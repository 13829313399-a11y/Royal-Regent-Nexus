"""Purge retired injection-scheduling data and its operational permissions.

Revision ID: 20260903_0095
Revises: 20260902_0094

Requires a verified full database backup. Shared authorization audit snapshots
remain system history; account data and unrelated domain records are preserved.
"""

import re

import sqlalchemy as sa
from alembic import context, op
from alembic.util import CommandError

revision = "20260903_0095"
down_revision = "20260902_0094"
branch_labels = None
depends_on = None

TABLE_PREFIXES = ("injection_schedule_", "injection_scheduling_")
PERMISSION_PREFIXES = (
    "injection_schedule_center:",
    "injection_scheduling:",
    "production:injection_scheduling:",
)
REFERENCE_MARKERS = ("injection_schedule_", "injection_scheduling", "injection-scheduling")
GUARD_FUNCTIONS = (
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
    targets = {name for name in table_names if name.startswith(TABLE_PREFIXES)}
    foreign_keys = {name: inspector.get_foreign_keys(name) for name in table_names}
    for name in sorted(set(table_names) - targets):
        for fk in foreign_keys[name]:
            if fk["referred_table"] in targets:
                raise CommandError(
                    f"Refusing injection purge: unrelated table {name} references "
                    f"{fk['referred_table']}; review this dependency first."
                )
    remaining = set(targets)
    order = []
    while remaining:
        parents = {
            fk["referred_table"]
            for name in remaining
            for fk in foreign_keys[name]
            if fk["referred_table"] in remaining and fk["referred_table"] != name
        }
        children = sorted(remaining - parents)
        if not children:
            raise CommandError("Refusing injection purge: cyclic table dependencies.")
        order.extend(children)
        remaining.difference_update(children)
    return order


def _view_preflight(connection, inspector, targets):
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(n) for n in targets) + r")(?![\w])") if targets else None
    owned_views = []
    for name in inspector.get_view_names():
        if name.startswith(TABLE_PREFIXES):
            owned_views.append(name)
        elif pattern and pattern.search(inspector.get_view_definition(name) or ""):
            raise CommandError(f"Refusing injection purge: unrelated view {name} references retired data.")
    if connection.dialect.name == "sqlite" and pattern:
        for name, owner, sql in connection.exec_driver_sql(
            "SELECT name, tbl_name, sql FROM sqlite_master WHERE type='trigger'"
        ):
            if owner not in targets and pattern.search(sql or ""):
                raise CommandError(f"Refusing injection purge: unrelated trigger {name} references retired data.")
    return owned_views


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
        connection.execute(previews.delete().where(sa.or_(
            *(previews.c.payload_json.contains(marker, autoescape=True)
              for marker in REFERENCE_MARKERS)
        )))
    state = table("auth_iam_state")
    if state is not None:
        connection.execute(state.delete().where(sa.or_(
            *(state.c.key.startswith(marker, autoescape=True)
              for marker in (*TABLE_PREFIXES, "production:injection_scheduling:"))
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
        "20260903_0095 permanently removes retired injection-scheduling data. "
        "Restore a verified pre-purge backup; a downgrade cannot recreate business records."
    )
