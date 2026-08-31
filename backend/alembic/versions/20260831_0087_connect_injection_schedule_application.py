"""connect the injection schedule application contract

Revision ID: 20260831_0087
Revises: 20260830_0086
Create Date: 2026-08-31
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from alembic.util.exc import CommandError

revision: str = "20260831_0087"
down_revision: str | Sequence[str] | None = "20260830_0086"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "injection_scheduling:read",
        "查看注塑排产中枢",
        "查看授权厂区的注塑排产看板、订单和机模主数据",
        "read",
        "normal",
    ),
    (
        "injection_scheduling:edit",
        "编辑注塑排产",
        "维护授权厂区的订单、人工排程和班次执行数据",
        "operate",
        "normal",
    ),
    (
        "injection_scheduling:schedule",
        "应用注塑排产方案",
        "预览、确认或拒绝授权厂区的自动排程方案",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:admin",
        "管理注塑排产规则",
        "维护授权厂区的机模主数据、排程规则和共享视图",
        "operate",
        "high",
    ),
)

ROLE_IDS_BY_PERMISSION = {
    "injection_scheduling:read": (
        "position_general_manager",
        "position_production_manager",
        "position_production_supervisor",
        "position_production_clerk",
        "position_molding_manager",
        "position_molding_supervisor",
        "position_molding_clerk",
        "molding_clerk",
        "molding_supervisor",
        "manager",
        "admin",
    ),
    "injection_scheduling:edit": (
        "position_general_manager",
        "position_production_manager",
        "position_production_supervisor",
        "position_production_clerk",
        "position_molding_manager",
        "position_molding_supervisor",
        "position_molding_clerk",
        "molding_clerk",
        "molding_supervisor",
        "manager",
        "admin",
    ),
    "injection_scheduling:schedule": (
        "position_general_manager",
        "position_production_manager",
        "position_production_supervisor",
        "position_molding_manager",
        "position_molding_supervisor",
        "molding_supervisor",
        "manager",
        "admin",
    ),
    "injection_scheduling:admin": ("admin",),
}

EXTENDED_TABLES = (
    "injection_schedule_factory_settings",
    "injection_schedule_import_batches",
    "injection_schedule_order_demands",
    "injection_schedule_machines",
    "injection_schedule_molds",
    "injection_schedule_lines",
)


def _add_application_columns() -> None:
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column(
            "schedule_revision", sa.Integer(), nullable=False, server_default="1"
        ),
    )
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column(
            "schedule_horizon_days", sa.Integer(), nullable=False, server_default="14"
        ),
    )
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column("freeze_hours", sa.Integer(), nullable=False, server_default="12"),
    )
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column(
            "effective_hours_per_day",
            sa.Numeric(12, 6),
            nullable=False,
            server_default="24",
        ),
    )
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column(
            "scheduling_rule_config_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "injection_schedule_factory_settings",
        sa.Column(
            "color_rule_config_json",
            sa.Text(),
            nullable=False,
            server_default="{}",
        ),
    )

    op.add_column(
        "injection_schedule_import_batches",
        sa.Column(
            "document_type",
            sa.String(32),
            nullable=False,
            server_default="UNIFIED_TEMPLATE",
        ),
    )
    op.add_column(
        "injection_schedule_import_batches",
        sa.Column(
            "import_profile_code",
            sa.String(64),
            nullable=False,
            server_default="UNIFIED_TEMPLATE_V1",
        ),
    )
    op.add_column(
        "injection_schedule_import_batches",
        sa.Column(
            "header_payload_json", sa.Text(), nullable=False, server_default="{}"
        ),
    )
    op.create_index(
        "ix_injection_schedule_import_batch_factory_profile",
        "injection_schedule_import_batches",
        ["factory_id", "import_profile_code"],
    )

    order_columns = (
        sa.Column("demand_line_no", sa.String(64), nullable=False, server_default=""),
        sa.Column("business_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("total_sets", sa.Numeric(18, 6), nullable=True),
        sa.Column("pieces_per_shot", sa.Integer(), nullable=True),
        sa.Column("single_machine_factor", sa.Numeric(12, 6), nullable=True),
        sa.Column("single_color_factor", sa.Numeric(12, 6), nullable=True),
        sa.Column("mold_ratio", sa.Numeric(12, 6), nullable=True),
        sa.Column(
            "required_machine_a_label", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("required_machine_a_value", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "color_family", sa.String(32), nullable=False, server_default="UNKNOWN"
        ),
        sa.Column("color_lightness_rank", sa.Numeric(6, 2), nullable=True),
        sa.Column(
            "spray_required", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("material_weight_kg", sa.Numeric(18, 6), nullable=True),
        sa.Column(
            "delivery_location", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column("ordered_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("operator_name", sa.String(128), nullable=False, server_default=""),
        sa.Column(
            "data_completeness_status",
            sa.String(16),
            nullable=False,
            server_default="INCOMPLETE",
        ),
    )
    for column in order_columns:
        op.add_column("injection_schedule_order_demands", column)

    op.add_column(
        "injection_schedule_machines",
        sa.Column("machine_a_label", sa.String(64), nullable=False, server_default=""),
    )
    op.add_column(
        "injection_schedule_machines",
        sa.Column(
            "is_high_speed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "injection_schedule_machines",
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index(
        "ix_injection_schedule_machine_factory_display",
        "injection_schedule_machines",
        ["factory_id", "display_order", "machine_code"],
    )

    mold_columns = (
        sa.Column(
            "required_machine_a_label", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("pieces_per_shot", sa.Integer(), nullable=True),
        sa.Column("single_machine_factor", sa.Numeric(12, 6), nullable=True),
        sa.Column("single_color_factor", sa.Numeric(12, 6), nullable=True),
        sa.Column("mold_ratio", sa.Numeric(12, 6), nullable=True),
    )
    for column in mold_columns:
        op.add_column("injection_schedule_molds", column)

    line_columns = (
        sa.Column(
            "schedule_revision", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "schedule_source", sa.String(16), nullable=False, server_default="MANUAL"
        ),
        sa.Column(
            "actual_started_at", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column(
            "actual_finished_at", sa.String(40), nullable=False, server_default=""
        ),
        sa.Column(
            "assignment_reason_json", sa.Text(), nullable=False, server_default="{}"
        ),
        sa.Column(
            "manual_adjustment_reason", sa.Text(), nullable=False, server_default=""
        ),
    )
    for column in line_columns:
        op.add_column("injection_schedule_lines", column)
    op.create_index(
        "ix_injection_schedule_line_factory_revision",
        "injection_schedule_lines",
        ["factory_id", "schedule_revision"],
    )


def _backfill_business_keys() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, factory_id, source_row, order_no, product_code,
                   mold_code, color, material_name
            FROM injection_schedule_order_demands
            ORDER BY factory_id, id
            """
        )
    ).mappings()
    for row in rows:
        demand_line_no = str(row["source_row"] or row["id"])
        canonical = "\x1f".join(
            str(row[key] or "").strip()
            for key in (
                "factory_id",
                "order_no",
                "product_code",
                "mold_code",
                "color",
                "material_name",
            )
        )
        canonical = f"{canonical}\x1f{demand_line_no}"
        business_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        connection.execute(
            sa.text(
                """
                UPDATE injection_schedule_order_demands
                SET demand_line_no = :demand_line_no,
                    business_key = :business_key,
                    total_sets = COALESCE(total_sets, raw_total_sets, quantity_sets)
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "demand_line_no": demand_line_no,
                "business_key": business_key,
            },
        )


def _replace_order_business_index() -> None:
    op.drop_index(
        "uq_injection_schedule_order_demand_active_business_key",
        table_name="injection_schedule_order_demands",
    )
    op.create_index(
        "uq_injection_schedule_order_demand_active_business_key_v2",
        "injection_schedule_order_demands",
        ["factory_id", "business_key"],
        unique=True,
        sqlite_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
        postgresql_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
    )


def _create_machine_unavailable_windows() -> None:
    op.create_table(
        "injection_schedule_machine_unavailable_windows",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("start_at", sa.String(40), nullable=False),
        sa.Column("end_at", sa.String(40), nullable=False),
        sa.Column("window_type", sa.String(24), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_locked", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_schedule_machine_window_id_factory",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_schedule_machines.id",
                "injection_schedule_machines.factory_id",
            ],
            name="fk_injection_schedule_machine_window_machine_factory",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "start_at < end_at", name="ck_injection_schedule_machine_window_range"
        ),
        sa.CheckConstraint(
            "window_type IN ('MAINTENANCE', 'FAULT', 'POWER_OUTAGE', "
            "'MOLD_REPAIR', 'TEMPORARY_STOP')",
            name="ck_injection_schedule_machine_window_type",
        ),
        sa.CheckConstraint(
            "version >= 1", name="ck_injection_schedule_machine_window_version"
        ),
    )
    op.create_index(
        "ix_injection_schedule_machine_window_factory_range",
        "injection_schedule_machine_unavailable_windows",
        ["factory_id", "start_at", "end_at"],
    )
    op.create_index(
        "ix_injection_schedule_machine_window_machine_range",
        "injection_schedule_machine_unavailable_windows",
        ["factory_id", "machine_id", "start_at", "end_at"],
    )


def _seed_permissions() -> None:
    connection = op.get_bind()
    timestamp = "2026-08-31 00:00:00"
    affected_roles: set[str] = set()
    for sort_offset, (code, name, description, access_kind, risk_level) in enumerate(
        PERMISSIONS
    ):
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permissions (id, code, name, description)
                SELECT CAST(:id AS VARCHAR(96)), CAST(:code AS VARCHAR(128)),
                       CAST(:name AS VARCHAR(128)), CAST(:description AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM auth_permissions
                    WHERE code = CAST(:code AS VARCHAR(128))
                )
                """
            ),
            {
                "id": permission_id,
                "code": code,
                "name": name,
                "description": description,
            },
        )
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permission_metadata (
                    permission_id, module_code, action, risk_level,
                    access_kind, scope_type, status, sort_order,
                    created_at, updated_at
                )
                SELECT permission.id, 'injection_scheduling',
                       CAST(:action AS VARCHAR(64)), CAST(:risk_level AS VARCHAR(32)),
                       CAST(:access_kind AS VARCHAR(16)), 'factory_department',
                       'active', :sort_order, CAST(:timestamp AS VARCHAR(32)),
                       CAST(:timestamp AS VARCHAR(32))
                FROM auth_permissions permission
                WHERE permission.code = CAST(:code AS VARCHAR(128))
                  AND NOT EXISTS (
                    SELECT 1 FROM auth_permission_metadata metadata
                    WHERE metadata.permission_id = permission.id
                  )
                """
            ),
            {
                "code": code,
                "action": code.partition(":")[2],
                "risk_level": risk_level,
                "access_kind": access_kind,
                "sort_order": 1180 + sort_offset,
                "timestamp": timestamp,
            },
        )
        for role_id in ROLE_IDS_BY_PERMISSION[code]:
            affected_roles.add(role_id)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO auth_role_permissions (id, role_id, permission_id)
                    SELECT CAST(:binding_id AS VARCHAR(128)), role.id, permission.id
                    FROM auth_roles role
                    JOIN auth_permissions permission
                      ON permission.code = CAST(:code AS VARCHAR(128))
                    WHERE role.id = CAST(:role_id AS VARCHAR(96))
                      AND NOT EXISTS (
                        SELECT 1 FROM auth_role_permissions binding
                        WHERE binding.role_id = role.id
                          AND binding.permission_id = permission.id
                      )
                    """
                ),
                {
                    "binding_id": f"{role_id}:{permission_id}",
                    "role_id": role_id,
                    "code": code,
                },
            )

    for role_id in sorted(affected_roles):
        connection.execute(
            sa.text(
                """
                UPDATE auth_role_metadata
                SET version = version + 1,
                    updated_at = CAST(:timestamp AS VARCHAR(32))
                WHERE role_id = CAST(:role_id AS VARCHAR(96))
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )
        connection.execute(
            sa.text(
                """
                UPDATE auth_user_authorization_revisions
                SET revision = revision + 1,
                    updated_at = CAST(:timestamp AS VARCHAR(32))
                WHERE user_id IN (
                    SELECT user_id FROM auth_user_roles
                    WHERE role_id = CAST(:role_id AS VARCHAR(96))
                )
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )


def upgrade() -> None:
    _add_application_columns()
    _backfill_business_keys()
    _replace_order_business_index()
    _create_machine_unavailable_windows()
    _seed_permissions()


def _refuse_data_losing_downgrade() -> None:
    connection = op.get_bind()
    populated = [
        table_name
        for table_name in (
            *EXTENDED_TABLES,
            "injection_schedule_machine_unavailable_windows",
        )
        if connection.execute(sa.text(f'SELECT 1 FROM "{table_name}" LIMIT 1')).first()
        is not None
    ]
    if populated:
        raise CommandError(
            "20260831_0087 cannot be downgraded after injection scheduling "
            "application data exists in: "
            f"{', '.join(populated)}. Restore a verified pre-migration backup instead."
        )


def _remove_permissions() -> None:
    connection = op.get_bind()
    codes = tuple(item[0] for item in PERMISSIONS)
    for table_name in (
        "auth_user_permission_overrides",
        "auth_role_permissions",
        "auth_permission_metadata",
    ):
        connection.execute(
            sa.text(
                f"""
                DELETE FROM {table_name}
                WHERE permission_id IN (
                    SELECT id FROM auth_permissions WHERE code IN :codes
                )
                """
            ).bindparams(sa.bindparam("codes", expanding=True)),
            {"codes": codes},
        )
    connection.execute(
        sa.text("DELETE FROM auth_permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise CommandError(
            "20260831_0087 requires an online downgrade so it can protect business data"
        )
    _refuse_data_losing_downgrade()
    _remove_permissions()
    op.drop_table("injection_schedule_machine_unavailable_windows")

    op.drop_index(
        "ix_injection_schedule_line_factory_revision",
        table_name="injection_schedule_lines",
    )
    for column_name in (
        "manual_adjustment_reason",
        "assignment_reason_json",
        "actual_finished_at",
        "actual_started_at",
        "schedule_source",
        "schedule_revision",
    ):
        op.drop_column("injection_schedule_lines", column_name)

    for column_name in (
        "mold_ratio",
        "single_color_factor",
        "single_machine_factor",
        "pieces_per_shot",
        "required_machine_a_label",
    ):
        op.drop_column("injection_schedule_molds", column_name)

    op.drop_index(
        "ix_injection_schedule_machine_factory_display",
        table_name="injection_schedule_machines",
    )
    for column_name in ("display_order", "is_high_speed", "machine_a_label"):
        op.drop_column("injection_schedule_machines", column_name)

    op.drop_index(
        "uq_injection_schedule_order_demand_active_business_key_v2",
        table_name="injection_schedule_order_demands",
    )
    op.create_index(
        "uq_injection_schedule_order_demand_active_business_key",
        "injection_schedule_order_demands",
        ["factory_id", "order_no", "product_code", "mold_code"],
        unique=True,
        sqlite_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
        postgresql_where=sa.text("status NOT IN ('COMPLETED', 'CANCELLED')"),
    )
    for column_name in (
        "data_completeness_status",
        "operator_name",
        "ordered_by_name",
        "delivery_location",
        "material_weight_kg",
        "spray_required",
        "color_lightness_rank",
        "color_family",
        "required_machine_a_value",
        "required_machine_a_label",
        "mold_ratio",
        "single_color_factor",
        "single_machine_factor",
        "pieces_per_shot",
        "total_sets",
        "business_key",
        "demand_line_no",
    ):
        op.drop_column("injection_schedule_order_demands", column_name)

    op.drop_index(
        "ix_injection_schedule_import_batch_factory_profile",
        table_name="injection_schedule_import_batches",
    )
    for column_name in ("header_payload_json", "import_profile_code", "document_type"):
        op.drop_column("injection_schedule_import_batches", column_name)

    for column_name in (
        "color_rule_config_json",
        "scheduling_rule_config_json",
        "effective_hours_per_day",
        "freeze_hours",
        "schedule_horizon_days",
        "schedule_revision",
    ):
        op.drop_column("injection_schedule_factory_settings", column_name)
