"""Move the 3D printing domain from Huakang B to Huakang A.

Revision ID: 20260729_0041
Revises: 20260729_0040
"""

from collections.abc import Sequence

from alembic import context, op
from alembic.util import CommandError
import sqlalchemy as sa


revision: str = "20260729_0041"
down_revision: str | Sequence[str] | None = "20260729_0040"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


HUAKANG_A = "huakang-a"
HUAKANG_B = "huakang-b"
MIGRATION_TIMESTAMP = "2026-07-29 16:40:00"
THREE_D_ROLE_IDS = (
    "position_3d_operator",
    "position_3d_supervisor",
    "position_3d_manager",
)
DOMAIN_TABLES = (
    "three_d_printing_settings",
    "three_d_printing_materials",
    "three_d_printing_products",
    "three_d_printing_product_images",
    "three_d_printing_printers",
    "three_d_printing_day_statuses",
    "three_d_printing_production_records",
    "three_d_printing_inventory",
    "three_d_printing_inventory_movements",
    "three_d_printing_schedules",
    "three_d_printing_maintenance",
    "three_d_printing_edge_agents",
    "three_d_printing_printer_commands",
    "three_d_printing_audit_events",
    "three_d_printing_migration_runs",
)
POSTGRES_COMPOSITE_FOREIGN_KEYS = (
    (
        "fk_three_d_printing_image_product_factory",
        "three_d_printing_product_images",
        "three_d_printing_products",
        ("product_id", "factory_id"),
        ("id", "factory_id"),
        "CASCADE",
    ),
    (
        "fk_three_d_printing_movement_inventory_factory",
        "three_d_printing_inventory_movements",
        "three_d_printing_inventory",
        ("inventory_id", "factory_id"),
        ("id", "factory_id"),
        "RESTRICT",
    ),
    (
        "fk_three_d_printing_command_printer_factory",
        "three_d_printing_printer_commands",
        "three_d_printing_printers",
        ("printer_id", "factory_id"),
        ("id", "factory_id"),
        "RESTRICT",
    ),
)
SQLITE_OFFLINE_ERROR = (
    "20260729_0041 cannot run as SQLite offline SQL because the migration "
    "must inspect existing 3D printing data; run this revision in SQLite "
    "online mode"
)


def _drop_audit_immutability(connection) -> None:
    if connection.dialect.name == "postgresql":
        op.execute(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_update "
            "ON three_d_printing_audit_events"
        )
        op.execute(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_delete "
            "ON three_d_printing_audit_events"
        )
    elif connection.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_update")
        op.execute("DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_delete")


def _install_audit_immutability(connection) -> None:
    if connection.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION reject_three_d_printing_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '3D printing audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_update
            BEFORE UPDATE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_delete
            BEFORE DELETE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
    elif connection.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_update
            BEFORE UPDATE ON three_d_printing_audit_events
            BEGIN
                SELECT RAISE(ABORT, '3D printing audit events are immutable');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_delete
            BEFORE DELETE ON three_d_printing_audit_events
            BEGIN
                SELECT RAISE(ABORT, '3D printing audit events are immutable');
            END
            """
        )


def _drop_postgres_foreign_keys(connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    for name, source_table, _, _, _, _ in POSTGRES_COMPOSITE_FOREIGN_KEYS:
        op.drop_constraint(name, source_table, type_="foreignkey")


def _create_postgres_foreign_keys(connection) -> None:
    if connection.dialect.name != "postgresql":
        return
    for (
        name,
        source_table,
        referent_table,
        local_columns,
        remote_columns,
        ondelete,
    ) in POSTGRES_COMPOSITE_FOREIGN_KEYS:
        op.create_foreign_key(
            name,
            source_table,
            referent_table,
            list(local_columns),
            list(remote_columns),
            ondelete=ondelete,
        )


def _count_domain_rows(connection, factory_id: str) -> int:
    return sum(
        int(
            connection.execute(
                sa.text(
                    f"SELECT COUNT(*) FROM {table_name} "
                    "WHERE factory_id = :factory_id"
                ),
                {"factory_id": factory_id},
            ).scalar_one()
        )
        for table_name in DOMAIN_TABLES
    )


def _ensure_unmixed_domain(connection, source: str, target: str) -> None:
    source_count = _count_domain_rows(connection, source)
    target_count = _count_domain_rows(connection, target)
    if source_count and target_count:
        raise RuntimeError(
            "3D printing factory reassignment refused: both source and target "
            f"contain domain rows ({source}={source_count}, {target}={target_count}). "
            "Back up the database and resolve the mixed scope explicitly."
        )


def _move_iam_scope(connection, source: str, target: str) -> None:
    role_placeholders = ", ".join(f"'{role_id}'" for role_id in THREE_D_ROLE_IDS)
    connection.execute(
        sa.text(
            f"""
            UPDATE auth_user_roles
            SET factory_id = :target
            WHERE factory_id = :source
              AND department = 'three-d-printing'
              AND role_id IN ({role_placeholders})
            """
        ),
        {"source": source, "target": target},
    )
    connection.execute(
        sa.text(
            """
            UPDATE employee_profiles
            SET primary_factory_id = :target, updated_at = :timestamp
            WHERE primary_factory_id = :source
              AND primary_department = 'three-d-printing'
            """
        ),
        {
            "source": source,
            "target": target,
            "timestamp": MIGRATION_TIMESTAMP,
        },
    )
    connection.execute(
        sa.text(
            """
            UPDATE auth_registration_requests
            SET factory_id = :target, updated_at = :timestamp
            WHERE factory_id = :source
              AND department = 'three-d-printing'
            """
        ),
        {
            "source": source,
            "target": target,
            "timestamp": MIGRATION_TIMESTAMP,
        },
    )
    for table_name in (
        "auth_user_permission_overrides",
        "auth_access_request_items",
    ):
        connection.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET factory_id = :target
                WHERE factory_id = :source
                  AND permission_id IN (
                      SELECT id
                      FROM auth_permissions
                      WHERE code LIKE 'three_d_printing:%'
                  )
                """
            ),
            {"source": source, "target": target},
        )
    connection.execute(
        sa.text(
            """
            UPDATE system_notifications
            SET target_factory_id = :target
            WHERE target_factory_id = :source
              AND (
                  target_permission LIKE 'three_d_printing:%'
                  OR target_department = 'three-d-printing'
              )
            """
        ),
        {"source": source, "target": target},
    )
    connection.execute(
        sa.text(
            f"""
            UPDATE auth_user_authorization_revisions
            SET revision = revision + 1, updated_at = :timestamp
            WHERE user_id IN (
                SELECT user_id
                FROM auth_user_roles
                WHERE factory_id = :target
                  AND department = 'three-d-printing'
                  AND role_id IN ({role_placeholders})
            )
            """
        ),
        {"target": target, "timestamp": MIGRATION_TIMESTAMP},
    )


def _replace_factory_labels(connection, source: str, target: str) -> None:
    source_label = "华康B" if source == HUAKANG_B else "华康A"
    target_label = "华康A" if target == HUAKANG_A else "华康B"
    connection.execute(
        sa.text(
            """
            UPDATE auth_permissions
            SET description = replace(description, :source_label, :target_label)
            WHERE code LIKE 'three_d_printing:%'
            """
        ),
        {"source_label": source_label, "target_label": target_label},
    )
    connection.execute(
        sa.text(
            """
            UPDATE auth_roles
            SET description = replace(description, :source_label, :target_label)
            WHERE id IN (
                'position_3d_operator',
                'position_3d_supervisor',
                'position_3d_manager'
            )
            """
        ),
        {"source_label": source_label, "target_label": target_label},
    )


def _move_domain(connection, source: str, target: str) -> None:
    _ensure_unmixed_domain(connection, source, target)
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA defer_foreign_keys = ON")

    _drop_audit_immutability(connection)
    _drop_postgres_foreign_keys(connection)

    connection.execute(
        sa.text(
            """
            UPDATE three_d_printing_edge_agents
            SET agent_key = replace(agent_key, :source, :target),
                name = replace(name, :source_label, :target_label)
            WHERE factory_id = :source
            """
        ),
        {
            "source": source,
            "target": target,
            "source_label": "华康B" if source == HUAKANG_B else "华康A",
            "target_label": "华康A" if target == HUAKANG_A else "华康B",
        },
    )
    for table_name in DOMAIN_TABLES:
        connection.execute(
            sa.text(
                f"UPDATE {table_name} SET factory_id = :target "
                "WHERE factory_id = :source"
            ),
            {"source": source, "target": target},
        )

    _move_iam_scope(connection, source, target)
    _replace_factory_labels(connection, source, target)

    connection.execute(
        sa.text(
            """
            INSERT INTO three_d_printing_audit_events (
                id, factory_id, entity_type, entity_id, action, detail_json,
                actor_id, actor_name, actor_type, request_id, created_at
            )
            SELECT
                '3daudit-factory-reassignment-0041', :target, 'migration',
                '20260729_0041', 'factory_reassigned', :detail_json,
                'system-migration', '数据库迁移', 'system', '', :timestamp
            WHERE NOT EXISTS (
                SELECT 1
                FROM three_d_printing_audit_events
                WHERE id = '3daudit-factory-reassignment-0041'
            )
            """
        ),
        {
            "target": target,
            "detail_json": (
                '{"revision":"20260729_0041",'
                f'"sourceFactory":"{source}","targetFactory":"{target}"'
                "}"
            ),
            "timestamp": MIGRATION_TIMESTAMP,
        },
    )

    _create_postgres_foreign_keys(connection)
    if connection.dialect.name == "sqlite":
        violations = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise RuntimeError(
                "3D printing factory reassignment produced foreign-key violations: "
                f"{violations[:10]}"
            )
    _install_audit_immutability(connection)


def _offline_postgresql_preflight(source: str, target: str) -> None:
    table_names = ", ".join(f"'{table_name}'" for table_name in DOMAIN_TABLES)
    op.execute(
        sa.text(
            f"""
            LOCK TABLE {", ".join(DOMAIN_TABLES)}
            IN ACCESS EXCLUSIVE MODE
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            DO $migration$
            DECLARE
                domain_table TEXT;
                row_count BIGINT;
                source_count BIGINT := 0;
                target_count BIGINT := 0;
            BEGIN
                FOREACH domain_table IN ARRAY ARRAY[{table_names}]
                LOOP
                    EXECUTE format(
                        'SELECT COUNT(*) FROM %I WHERE factory_id = $1',
                        domain_table
                    )
                    INTO row_count
                    USING '{source}';
                    source_count := source_count + row_count;

                    EXECUTE format(
                        'SELECT COUNT(*) FROM %I WHERE factory_id = $1',
                        domain_table
                    )
                    INTO row_count
                    USING '{target}';
                    target_count := target_count + row_count;
                END LOOP;

                IF source_count > 0 AND target_count > 0 THEN
                    RAISE EXCEPTION
                        '3D printing factory reassignment refused: both source '
                        'and target contain domain rows (%=%, %=%).',
                        '{source}', source_count, '{target}', target_count;
                END IF;
            END
            $migration$
            """
        )
    )


def _offline_postgresql_move_iam_scope(source: str, target: str) -> None:
    role_placeholders = ", ".join(f"'{role_id}'" for role_id in THREE_D_ROLE_IDS)
    op.execute(
        sa.text(
            f"""
            UPDATE auth_user_roles
            SET factory_id = '{target}'
            WHERE factory_id = '{source}'
              AND department = 'three-d-printing'
              AND role_id IN ({role_placeholders})
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE employee_profiles
            SET primary_factory_id = '{target}',
                updated_at = '{MIGRATION_TIMESTAMP}'
            WHERE primary_factory_id = '{source}'
              AND primary_department = 'three-d-printing'
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE auth_registration_requests
            SET factory_id = '{target}', updated_at = '{MIGRATION_TIMESTAMP}'
            WHERE factory_id = '{source}'
              AND department = 'three-d-printing'
            """
        )
    )
    for table_name in (
        "auth_user_permission_overrides",
        "auth_access_request_items",
    ):
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET factory_id = '{target}'
                WHERE factory_id = '{source}'
                  AND permission_id IN (
                      SELECT id
                      FROM auth_permissions
                      WHERE code LIKE 'three_d_printing:%'
                  )
                """
            )
        )
    op.execute(
        sa.text(
            f"""
            UPDATE system_notifications
            SET target_factory_id = '{target}'
            WHERE target_factory_id = '{source}'
              AND (
                  target_permission LIKE 'three_d_printing:%'
                  OR target_department = 'three-d-printing'
              )
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE auth_user_authorization_revisions
            SET revision = revision + 1,
                updated_at = '{MIGRATION_TIMESTAMP}'
            WHERE user_id IN (
                SELECT user_id
                FROM auth_user_roles
                WHERE factory_id = '{target}'
                  AND department = 'three-d-printing'
                  AND role_id IN ({role_placeholders})
            )
            """
        )
    )


def _offline_postgresql_replace_factory_labels(
    source: str,
    target: str,
) -> None:
    source_label = "华康B" if source == HUAKANG_B else "华康A"
    target_label = "华康A" if target == HUAKANG_A else "华康B"
    op.execute(
        sa.text(
            f"""
            UPDATE auth_permissions
            SET description = replace(
                description, '{source_label}', '{target_label}'
            )
            WHERE code LIKE 'three_d_printing:%'
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            UPDATE auth_roles
            SET description = replace(
                description, '{source_label}', '{target_label}'
            )
            WHERE id IN (
                'position_3d_operator',
                'position_3d_supervisor',
                'position_3d_manager'
            )
            """
        )
    )


def _offline_postgresql_move_domain(source: str, target: str) -> None:
    _offline_postgresql_preflight(source, target)
    source_label = "华康B" if source == HUAKANG_B else "华康A"
    target_label = "华康A" if target == HUAKANG_A else "华康B"

    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_update "
            "ON three_d_printing_audit_events"
        )
    )
    op.execute(
        sa.text(
            "DROP TRIGGER IF EXISTS trg_three_d_printing_audit_no_delete "
            "ON three_d_printing_audit_events"
        )
    )
    for name, source_table, _, _, _, _ in POSTGRES_COMPOSITE_FOREIGN_KEYS:
        op.drop_constraint(name, source_table, type_="foreignkey")

    op.execute(
        sa.text(
            f"""
            UPDATE three_d_printing_edge_agents
            SET agent_key = replace(agent_key, '{source}', '{target}'),
                name = replace(name, '{source_label}', '{target_label}')
            WHERE factory_id = '{source}'
            """
        )
    )
    for table_name in DOMAIN_TABLES:
        op.execute(
            sa.text(
                f"""
                UPDATE {table_name}
                SET factory_id = '{target}'
                WHERE factory_id = '{source}'
                """
            )
        )

    _offline_postgresql_move_iam_scope(source, target)
    _offline_postgresql_replace_factory_labels(source, target)
    detail_json = (
        '{"revision":"20260729_0041",'
        f'"sourceFactory":"{source}","targetFactory":"{target}"'
        "}"
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO three_d_printing_audit_events (
                id, factory_id, entity_type, entity_id, action, detail_json,
                actor_id, actor_name, actor_type, request_id, created_at
            )
            SELECT
                '3daudit-factory-reassignment-0041', '{target}', 'migration',
                '20260729_0041', 'factory_reassigned', '{detail_json}',
                'system-migration', '数据库迁移', 'system', '',
                '{MIGRATION_TIMESTAMP}'
            WHERE NOT EXISTS (
                SELECT 1
                FROM three_d_printing_audit_events
                WHERE id = '3daudit-factory-reassignment-0041'
            )
            """
        )
    )

    for (
        name,
        source_table,
        referent_table,
        local_columns,
        remote_columns,
        ondelete,
    ) in POSTGRES_COMPOSITE_FOREIGN_KEYS:
        op.create_foreign_key(
            name,
            source_table,
            referent_table,
            list(local_columns),
            list(remote_columns),
            ondelete=ondelete,
        )
    op.execute(
        sa.text(
            """
            CREATE OR REPLACE FUNCTION reject_three_d_printing_audit_mutation()
            RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION '3D printing audit events are immutable';
            END;
            $$ LANGUAGE plpgsql
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_update
            BEFORE UPDATE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
    )
    op.execute(
        sa.text(
            """
            CREATE TRIGGER trg_three_d_printing_audit_no_delete
            BEFORE DELETE ON three_d_printing_audit_events
            FOR EACH ROW EXECUTE FUNCTION reject_three_d_printing_audit_mutation()
            """
        )
    )


def upgrade() -> None:
    if context.is_offline_mode():
        if context.get_context().dialect.name != "postgresql":
            raise CommandError(SQLITE_OFFLINE_ERROR)
        _offline_postgresql_move_domain(HUAKANG_B, HUAKANG_A)
        return
    _move_domain(op.get_bind(), HUAKANG_B, HUAKANG_A)


def downgrade() -> None:
    if context.is_offline_mode():
        if context.get_context().dialect.name != "postgresql":
            raise CommandError(SQLITE_OFFLINE_ERROR)
        op.execute(
            sa.text(
                f"""
                DO $migration$
                BEGIN
                    IF EXISTS (
                        SELECT 1
                        FROM three_d_printing_migration_runs
                        WHERE factory_id = '{HUAKANG_A}'
                        UNION ALL
                        SELECT 1
                        FROM three_d_printing_production_records
                        WHERE factory_id = '{HUAKANG_A}'
                    ) THEN
                        RAISE EXCEPTION
                            '20260729_0041 downgrade is blocked after Huakang A '
                            'historical migration or production records exist; '
                            'restore a verified backup.';
                    END IF;
                END
                $migration$
                """
            )
        )
        _offline_postgresql_move_domain(HUAKANG_A, HUAKANG_B)
        return
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            """
            SELECT 1
            FROM three_d_printing_migration_runs
            WHERE factory_id = :factory_id
            UNION ALL
            SELECT 1
            FROM three_d_printing_production_records
            WHERE factory_id = :factory_id
            LIMIT 1
            """
        ),
        {"factory_id": HUAKANG_A},
    ).first()
    if populated is not None:
        raise RuntimeError(
            "20260729_0041 downgrade is blocked after Huakang A historical "
            "migration or production records exist; restore a verified backup."
        )
    _move_domain(connection, HUAKANG_A, HUAKANG_B)
