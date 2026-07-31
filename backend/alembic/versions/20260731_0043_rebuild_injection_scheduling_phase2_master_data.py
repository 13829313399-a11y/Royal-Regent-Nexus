"""rebuild injection scheduling phase 2 master data

Revision ID: 20260731_0043
Revises: 20260731_0042
Create Date: 2026-07-31
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260731_0043"
down_revision: str | Sequence[str] | None = "20260731_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "injection_scheduling:read",
        "查看注塑排产主数据",
        "查看授权厂区的注塑机台、模具与当前规则配置",
        "read",
        "normal",
    ),
    (
        "injection_scheduling:import",
        "导入注塑排产数据",
        "预览并确认授权厂区的注塑排产 Excel 导入",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:edit",
        "编辑注塑排产草案",
        "编辑授权厂区的注塑排产草案",
        "operate",
        "normal",
    ),
    (
        "injection_scheduling:report",
        "回报注塑生产进度",
        "提交授权厂区的注塑任务班次回报",
        "operate",
        "normal",
    ),
    (
        "injection_scheduling:publish",
        "发布注塑排产计划",
        "发布授权厂区的不可变注塑排产版本",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:rollback",
        "回滚注塑排产计划",
        "从授权厂区的历史版本创建新草案",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:manage_master",
        "维护注塑排产主数据",
        "维护授权厂区的机台与模具能力资料",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:manage_rules",
        "维护注塑排产规则",
        "维护授权厂区的硬约束与软评分规则版本",
        "operate",
        "high",
    ),
)

CLERK_ROLE_IDS = (
    "position_molding_clerk",
    "molding_clerk",
)
SUPERVISOR_ROLE_IDS = (
    "position_general_manager",
    "position_production_manager",
    "position_production_supervisor",
    "position_molding_manager",
    "position_molding_supervisor",
    "molding_supervisor",
    "manager",
)
ADMIN_ROLE_IDS = ("admin",)

FACTORY_IDS = (
    "huakang-a",
    "huakang-b",
    "huakang-c",
    "huakang-d",
    "huadeng",
    "huaxing",
)

DEFAULT_RULE_CONFIG = {
    "schema_version": "phase2-v1",
    "arm_coverage": {
        "none": ["none"],
        "single": ["none", "single"],
        "dual": ["none", "single", "dual"],
        "multi": ["none", "single", "dual", "multi"],
    },
    "required_dimension_fields": ["length_mm", "width_mm", "height_mm"],
    "process_rule_codes": [
        "pvc_screw",
        "pc_screw",
        "transparent_only",
        "no_core_pull",
        "high_pressure_limit",
        "two_color",
        "vertical",
        "semi_auto",
    ],
    "scoring_weights": {
        "delivery_urgency": 30,
        "business_priority": 20,
        "same_mold": 18,
        "same_material_color": 12,
        "machine_fit": 10,
        "queue_balance": 10,
    },
    "color_scale": [],
    "notes": "阶段2保守默认规则；缺失关键尺寸时必须人工复核。",
}


def _create_tables() -> None:
    op.create_table(
        "injection_scheduling_machines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("machine_code", sa.String(64), nullable=False),
        sa.Column("area", sa.String(128), nullable=False, server_default=""),
        sa.Column("position", sa.String(128), nullable=False, server_default=""),
        sa.Column("machine_class", sa.String(64), nullable=False, server_default=""),
        sa.Column("clamping_force_tons", sa.Numeric(12, 3), nullable=True),
        sa.Column("injection_capacity_g", sa.Numeric(12, 3), nullable=True),
        sa.Column("tie_bar_x_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("tie_bar_y_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("platen_x_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("platen_y_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("min_mold_thickness_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("max_mold_thickness_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("opening_stroke_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "machine_type", sa.String(64), nullable=False, server_default="standard"
        ),
        sa.Column(
            "robot_capabilities_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "fixture_capabilities_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "process_restrictions_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="available"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "machine_code",
            name="uq_injection_scheduling_machine_factory_code",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_machine_id_factory",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'running', 'maintenance', 'offline')",
            name="ck_injection_scheduling_machine_status",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_machine_revision",
        ),
    )
    for column in (
        "factory_id",
        "machine_code",
        "machine_class",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_machines_{column}",
            "injection_scheduling_machines",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_machine_factory_status_code",
        "injection_scheduling_machines",
        ["factory_id", "status", "machine_code"],
    )

    op.create_table(
        "injection_scheduling_molds",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_no", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("length_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("width_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("height_mm", sa.Numeric(12, 3), nullable=True),
        sa.Column("weight_kg", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "recommended_machine_class",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column("whole_shot_net_weight_g", sa.Numeric(12, 3), nullable=True),
        sa.Column("whole_shot_gross_weight_g", sa.Numeric(12, 3), nullable=True),
        sa.Column(
            "required_arm_type", sa.String(64), nullable=False, server_default="none"
        ),
        sa.Column(
            "required_fixture_type", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "material_code", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "material_name", sa.String(255), nullable=False, server_default=""
        ),
        sa.Column(
            "color_profile", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column(
            "process_requirements_json", sa.Text(), nullable=False, server_default="[]"
        ),
        sa.Column("copy_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "data_quality_status",
            sa.String(32),
            nullable=False,
            server_default="needs_review",
        ),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="available"
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "updated_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "mold_no",
            name="uq_injection_scheduling_mold_factory_no",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_mold_id_factory",
        ),
        sa.CheckConstraint(
            "status IN ('available', 'maintenance', 'not_arrived', "
            "'occupied', 'retired')",
            name="ck_injection_scheduling_mold_status",
        ),
        sa.CheckConstraint(
            "data_quality_status IN ('complete', 'needs_review')",
            name="ck_injection_scheduling_mold_data_quality",
        ),
        sa.CheckConstraint(
            "copy_count >= 1",
            name="ck_injection_scheduling_mold_copy_count",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_mold_revision",
        ),
    )
    for column in (
        "factory_id",
        "mold_no",
        "recommended_machine_class",
        "material_code",
        "data_quality_status",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_molds_{column}",
            "injection_scheduling_molds",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_mold_factory_status_no",
        "injection_scheduling_molds",
        ["factory_id", "status", "mold_no"],
    )

    op.create_table(
        "injection_scheduling_rule_sets",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "configured_max_utilization",
            sa.Numeric(6, 4),
            nullable=False,
            server_default="1.0",
        ),
        sa.Column(
            "allow_mold_rotation_90",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("config_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "created_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("superseded_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "factory_id",
            "revision",
            name="uq_injection_scheduling_rule_factory_revision",
        ),
        sa.UniqueConstraint(
            "id",
            "factory_id",
            name="uq_injection_scheduling_rule_id_factory",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'superseded')",
            name="ck_injection_scheduling_rule_status",
        ),
        sa.CheckConstraint(
            "configured_max_utilization > 0 AND configured_max_utilization <= 1",
            name="ck_injection_scheduling_rule_utilization",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="ck_injection_scheduling_rule_revision",
        ),
    )
    for column in ("factory_id", "status", "created_by", "created_at"):
        op.create_index(
            f"ix_injection_scheduling_rule_sets_{column}",
            "injection_scheduling_rule_sets",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_rule_factory_status_revision",
        "injection_scheduling_rule_sets",
        ["factory_id", "status", "revision"],
    )


def _role_ids_for_permission(code: str) -> tuple[str, ...]:
    if code.endswith((":manage_master", ":manage_rules")):
        return ADMIN_ROLE_IDS
    if code.endswith((":publish", ":rollback")):
        return (*SUPERVISOR_ROLE_IDS, *ADMIN_ROLE_IDS)
    return (*CLERK_ROLE_IDS, *SUPERVISOR_ROLE_IDS, *ADMIN_ROLE_IDS)


def _seed_permissions() -> None:
    connection = op.get_bind()
    timestamp = "2026-07-31 00:00:00"
    affected_roles: set[str] = set()
    for sort_offset, (code, name, description, access_kind, risk_level) in enumerate(
        PERMISSIONS
    ):
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permissions (id, code, name, description)
                SELECT
                    CAST(:id AS VARCHAR(96)),
                    CAST(:code AS VARCHAR(128)),
                    CAST(:name AS VARCHAR(128)),
                    CAST(:description AS TEXT)
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
                SELECT
                    permission.id,
                    'injection_scheduling',
                    CAST(:action AS VARCHAR(64)),
                    CAST(:risk_level AS VARCHAR(32)),
                    CAST(:access_kind AS VARCHAR(16)),
                    'factory_department',
                    'active',
                    :sort_order,
                    CAST(:timestamp AS VARCHAR(32)),
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
                "sort_order": 900 + sort_offset,
                "timestamp": timestamp,
            },
        )
        for role_id in _role_ids_for_permission(code):
            affected_roles.add(role_id)
            connection.execute(
                sa.text(
                    """
                    INSERT INTO auth_role_permissions (id, role_id, permission_id)
                    SELECT
                        CAST(:binding_id AS VARCHAR(128)),
                        role.id,
                        permission.id
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


def _seed_default_rules() -> None:
    connection = op.get_bind()
    timestamp = "2026-07-31T00:00:00+08:00"
    config_json = json.dumps(
        DEFAULT_RULE_CONFIG,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    for factory_id in FACTORY_IDS:
        connection.execute(
            sa.text(
                """
                INSERT INTO injection_scheduling_rule_sets (
                    id, factory_id, revision, status,
                    configured_max_utilization, allow_mold_rotation_90,
                    config_json, created_by, created_by_name,
                    created_at, superseded_at
                )
                SELECT
                    CAST(:id AS VARCHAR(96)),
                    CAST(:factory_id AS VARCHAR(64)),
                    1,
                    'active',
                    1.0,
                    :allow_rotation,
                    CAST(:config_json AS TEXT),
                    'system-seed',
                    '系统初始化',
                    CAST(:timestamp AS VARCHAR(32)),
                    ''
                WHERE NOT EXISTS (
                    SELECT 1 FROM injection_scheduling_rule_sets
                    WHERE factory_id = CAST(:factory_id AS VARCHAR(64))
                )
                """
            ),
            {
                "id": f"isrules-default-{factory_id}",
                "factory_id": factory_id,
                "allow_rotation": False,
                "config_json": config_json,
                "timestamp": timestamp,
            },
        )


def upgrade() -> None:
    _create_tables()
    _seed_permissions()
    _seed_default_rules()


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
    connection = op.get_bind()
    populated = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT COUNT(*) FROM injection_scheduling_machines) AS machines,
                (SELECT COUNT(*) FROM injection_scheduling_molds) AS molds,
                (
                    SELECT COUNT(*) FROM injection_scheduling_rule_sets
                    WHERE id NOT LIKE 'isrules-default-%'
                ) AS custom_rules
            """
        )
    ).mappings().one()
    if any(populated.values()):
        raise RuntimeError(
            "20260731_0043 cannot be downgraded after injection scheduling "
            "master data or custom rules exist; back up the domain first."
        )

    _remove_permissions()
    op.drop_table("injection_scheduling_rule_sets")
    op.drop_table("injection_scheduling_molds")
    op.drop_table("injection_scheduling_machines")
