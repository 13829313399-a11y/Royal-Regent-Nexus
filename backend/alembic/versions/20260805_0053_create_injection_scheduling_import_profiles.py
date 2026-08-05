"""create versioned injection scheduling import profiles

Revision ID: 20260805_0053
Revises: 20260804_0052
Create Date: 2026-08-05
"""

import base64
import zlib
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260805_0053"
down_revision: str | Sequence[str] | None = "20260804_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "injection_scheduling:manage_import_profiles",
        "维护注塑排产导入模板",
        "新建、审核、激活、停用并绑定授权厂区的版本化导入 Profile",
        "operate",
        "high",
    ),
    (
        "injection_scheduling:export",
        "导出注塑排产计划",
        "导出授权厂区明确指定的注塑排产计划版本",
        "operate",
        "high",
    ),
)

EXPORT_ROLE_IDS = (
    "position_general_manager",
    "position_production_manager",
    "position_production_supervisor",
    "position_molding_manager",
    "position_molding_supervisor",
    "position_molding_clerk",
    "molding_clerk",
    "molding_supervisor",
    "manager",
    "admin",
)

# Deliberately excludes general-manager roles. The business contract requires an
# explicit grant instead of position-name inference for profile governance.
PROFILE_MANAGER_ROLE_IDS = (
    "position_molding_manager",
    "position_molding_supervisor",
    "molding_supervisor",
    "admin",
)

# Frozen compressed JSON snapshots keep this historical migration independent
# from later runtime Profile revisions.
BUILTIN_PROFILE_SEEDS = (
    {
        "id": "isprofile-huaxing-daily-v1",
        "profile_code": "huaxing_daily_plan_v1",
        "profile_family": "huaxing_daily_plan",
        "revision": 1,
        "name": "华兴啤机日排表 v1",
        "factory_id": "huaxing",
        "renderer_code": "huaxing_daily_plan_v1",
        "definition_sha256": "8c575c2a4fecb39e9b6797782f0bd1ea25c4f96af22f0dbcfc47b7a9d0834bef",
        "template_signature": "29dbac50ce1ab08502bedfe3d3158de87307e615662f97af975ef2c4486b2ec1",
        "header_fingerprint": "8b18b0efd610c574d05faa9b4a3736acd24706dc9bbda7dcec6ac1b4ce101b09",
        "config_zlib_b64": "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",
    },
    {
        "id": "isprofile-huakang-b-daily-v1",
        "profile_code": "huakang_b_daily_plan_v1",
        "profile_family": "huakang_b_daily_plan",
        "revision": 1,
        "name": "华康 B 啤机日排表 v1",
        "factory_id": "huakang-b",
        "renderer_code": "huakang_b_daily_plan_v1",
        "definition_sha256": "bcadd83bff6e4093958c29e5e2af277879915e2d6e23eb23a60583c69d4bd312",
        "template_signature": "8da8b00b2196152237bd32424fde195f34f83aff6ef673e5d156d45664ff7a3d",
        "header_fingerprint": "1c279393dcb9ff3e3a7f1b9f1c9b9f684cc50fe4408f4fc91f1893f2cb6a1264",
        "config_zlib_b64": "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",
    },
)


def _create_tables() -> None:
    op.create_table(
        "injection_scheduling_import_profiles",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("profile_code", sa.String(96), nullable=False),
        sa.Column("profile_family", sa.String(96), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "lifecycle_revision", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="PROFILE_DRAFT"
        ),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("definition_sha256", sa.String(64), nullable=False),
        sa.Column(
            "template_signature", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column(
            "header_fingerprint", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("renderer_code", sa.String(96), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("reviewed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "reviewed_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("reviewed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("retired_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("retired_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("retired_at", sa.String(32), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "profile_family",
            "revision",
            name="uq_injection_scheduling_import_profile_family_revision",
        ),
        sa.UniqueConstraint(
            "profile_code", name="uq_injection_scheduling_import_profile_code"
        ),
        sa.CheckConstraint(
            "status IN ('PROFILE_DRAFT', 'ACTIVE', 'RETIRED')",
            name="ck_injection_scheduling_import_profile_status",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND lifecycle_revision >= 1",
            name="ck_injection_scheduling_import_profile_revisions",
        ),
    )
    for column in (
        "profile_code",
        "profile_family",
        "status",
        "definition_sha256",
        "template_signature",
        "header_fingerprint",
        "created_by",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_profiles_{column}",
            "injection_scheduling_import_profiles",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_import_profile_family_status_revision",
        "injection_scheduling_import_profiles",
        ["profile_family", "status", "revision"],
    )

    op.create_table(
        "injection_scheduling_import_profile_factories",
        sa.Column("id", sa.String(128), primary_key=True),
        sa.Column("profile_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["injection_scheduling_import_profiles.id"],
            name="fk_injection_scheduling_import_profile_factory_profile",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "profile_id",
            "factory_id",
            name="uq_injection_scheduling_import_profile_factory",
        ),
    )
    for column in ("profile_id", "factory_id", "created_by", "created_at"):
        op.create_index(
            f"ix_injection_scheduling_import_profile_factories_{column}",
            "injection_scheduling_import_profile_factories",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_import_profile_factory_scope",
        "injection_scheduling_import_profile_factories",
        ["factory_id", "profile_id"],
    )

    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column("profile_id", sa.String(96), nullable=True),
    )
    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column("profile_revision", sa.Integer(), nullable=True),
    )
    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column(
            "profile_definition_sha256",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column(
            "template_signature", sa.String(64), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column(
            "mapping_fingerprint", sa.String(64), nullable=False, server_default=""
        ),
    )
    op.add_column(
        "injection_scheduling_import_batches",
        sa.Column(
            "batch_state",
            sa.String(32),
            nullable=False,
            server_default="LEGACY_PREVIEW",
        ),
    )
    for column in (
        "profile_id",
        "template_signature",
        "mapping_fingerprint",
        "batch_state",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_batches_{column}",
            "injection_scheduling_import_batches",
            [column],
        )


def _seed_permissions() -> None:
    connection = op.get_bind()
    timestamp = "2026-08-05 00:00:00"
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
                    permission_id, module_code, action, risk_level, access_kind,
                    scope_type, status, sort_order, created_at, updated_at
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
                "sort_order": 908 + sort_offset,
                "timestamp": timestamp,
            },
        )
        role_ids = (
            PROFILE_MANAGER_ROLE_IDS
            if code.endswith("manage_import_profiles")
            else EXPORT_ROLE_IDS
        )
        for role_id in role_ids:
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


def _seed_builtin_profiles() -> None:
    connection = op.get_bind()
    timestamp = "2026-08-05T00:00:00+08:00"
    for profile in BUILTIN_PROFILE_SEEDS:
        config_json = zlib.decompress(
            base64.b64decode(profile["config_zlib_b64"])
        ).decode("utf-8")
        connection.execute(
            sa.text(
                """
                INSERT INTO injection_scheduling_import_profiles (
                    id, profile_code, profile_family, revision, lifecycle_revision,
                    name, description, status, config_json, definition_sha256,
                    template_signature, header_fingerprint, renderer_code,
                    created_by, created_by_name, created_at,
                    reviewed_by, reviewed_by_name, reviewed_at,
                    retired_by, retired_by_name, retired_at
                ) VALUES (
                    :id, :profile_code, :profile_family, :revision, 1,
                    :name, :description, 'ACTIVE', :config_json, :definition_sha256,
                    :template_signature, :header_fingerprint, :renderer_code,
                    'system-seed', '系统初始化', :timestamp,
                    'system-seed', '系统初始化', :timestamp, '', '', ''
                )
                """
            ),
            {
                "id": profile["id"],
                "profile_code": profile["profile_code"],
                "profile_family": profile["profile_family"],
                "revision": profile["revision"],
                "name": profile["name"],
                "description": "系统内置且经过样本契约验证的注塑排产导入 Profile",
                "config_json": config_json,
                "definition_sha256": profile["definition_sha256"],
                "template_signature": profile["template_signature"],
                "header_fingerprint": profile["header_fingerprint"],
                "renderer_code": profile["renderer_code"],
                "timestamp": timestamp,
            },
        )
        factory_id = profile["factory_id"]
        connection.execute(
            sa.text(
                """
                INSERT INTO injection_scheduling_import_profile_factories (
                    id, profile_id, factory_id, created_by, created_by_name, created_at
                ) VALUES (
                    :id, :profile_id, :factory_id,
                    'system-seed', '系统初始化', :timestamp
                )
                """
            ),
            {
                "id": f"{profile['id']}:{factory_id}",
                "profile_id": profile["id"],
                "factory_id": factory_id,
                "timestamp": timestamp,
            },
        )


def upgrade() -> None:
    _create_tables()
    _seed_permissions()
    _seed_builtin_profiles()


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
    populated = (
        connection.execute(
            sa.text(
                """
            SELECT
                (
                    SELECT COUNT(*) FROM injection_scheduling_import_profiles
                    WHERE id NOT IN (
                        'isprofile-huaxing-daily-v1',
                        'isprofile-huakang-b-daily-v1'
                    )
                ) AS custom_profiles,
                (
                    SELECT COUNT(*) FROM injection_scheduling_import_profiles
                    WHERE lifecycle_revision != 1 OR status != 'ACTIVE'
                ) AS changed_profiles,
                (
                    SELECT COUNT(*)
                    FROM injection_scheduling_import_profile_factories
                ) AS binding_count,
                (
                    SELECT COUNT(*) FROM injection_scheduling_import_batches
                    WHERE profile_id IS NOT NULL
                ) AS referenced_batches
            """
            )
        )
        .mappings()
        .one()
    )
    if (
        populated["custom_profiles"]
        or populated["changed_profiles"]
        or populated["binding_count"] != 2
        or populated["referenced_batches"]
    ):
        raise RuntimeError(
            "20260805_0053 cannot be downgraded after Profile lifecycle, binding, "
            "custom revision, or referenced ImportBatch data exists; "
            "restore a verified pre-0053 backup instead."
        )
    _remove_permissions()
    for column in (
        "batch_state",
        "mapping_fingerprint",
        "template_signature",
        "profile_id",
    ):
        op.drop_index(
            f"ix_injection_scheduling_import_batches_{column}",
            table_name="injection_scheduling_import_batches",
        )
    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        batch_op.drop_column("batch_state")
        batch_op.drop_column("mapping_fingerprint")
        batch_op.drop_column("template_signature")
        batch_op.drop_column("profile_definition_sha256")
        batch_op.drop_column("profile_revision")
        batch_op.drop_column("profile_id")
    op.drop_table("injection_scheduling_import_profile_factories")
    op.drop_table("injection_scheduling_import_profiles")
