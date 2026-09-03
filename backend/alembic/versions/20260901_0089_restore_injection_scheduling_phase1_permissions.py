"""restore the Phase 1 injection-scheduling permission contract

Revision ID: 20260901_0089
Revises: 20260901_0088
Create Date: 2026-09-01
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic.util.exc import CommandError

from alembic import op

revision: str = "20260901_0089"
down_revision: str | Sequence[str] | None = "20260901_0088"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    (
        "production:injection_scheduling:view",
        "查看注塑排产中枢",
        "查看授权厂区的注塑排产工作台和保留数据状态",
        "view",
        "read",
        "normal",
    ),
    (
        "production:injection_scheduling:edit",
        "编辑注塑排产",
        "维护授权厂区的计划、任务、机器状态、导入和规则建议",
        "edit",
        "operate",
        "normal",
    ),
    (
        "production:injection_scheduling:publish",
        "发布注塑排产",
        "校验、发布、撤回或执行授权厂区的高风险排产覆盖",
        "publish",
        "operate",
        "high",
    ),
    (
        "production:injection_scheduling:shift_report",
        "注塑班次报数",
        "填写或修改授权厂区尚未结算的白夜班报数",
        "shift_report",
        "operate",
        "normal",
    ),
)

VIEW_AND_OPERATE_ROLE_IDS = (
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
)
PUBLISH_ROLE_IDS = (
    "position_general_manager",
    "position_production_manager",
    "position_production_supervisor",
    "position_molding_manager",
    "position_molding_supervisor",
    "molding_supervisor",
    "manager",
    "admin",
)
ROLE_IDS_BY_PERMISSION = {
    "production:injection_scheduling:view": VIEW_AND_OPERATE_ROLE_IDS,
    "production:injection_scheduling:edit": VIEW_AND_OPERATE_ROLE_IDS,
    "production:injection_scheduling:publish": PUBLISH_ROLE_IDS,
    "production:injection_scheduling:shift_report": VIEW_AND_OPERATE_ROLE_IDS,
}


def _permission_id(code: str) -> str:
    return f"perm-{code.replace(':', '-')}"


def upgrade() -> None:
    connection = op.get_bind()
    timestamp = "2026-09-01 00:00:00"
    affected_roles: set[str] = set()

    for sort_offset, (
        code,
        name,
        description,
        action,
        access_kind,
        risk_level,
    ) in enumerate(PERMISSIONS):
        permission_id = _permission_id(code)
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
                       CAST(:action AS VARCHAR(64)),
                       CAST(:risk_level AS VARCHAR(32)),
                       CAST(:access_kind AS VARCHAR(16)),
                       'factory_department', 'active', :sort_order,
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
                "action": action,
                "risk_level": risk_level,
                "access_kind": access_kind,
                "sort_order": 1190 + sort_offset,
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
                    WHERE role.id = CAST(:role_id AS VARCHAR(64))
                      AND NOT EXISTS (
                        SELECT 1 FROM auth_role_permissions binding
                        WHERE binding.role_id = role.id
                          AND binding.permission_id = permission.id
                      )
                    """
                ),
                {
                    "binding_id": f"phase1:{role_id}:{permission_id}",
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
                WHERE role_id = CAST(:role_id AS VARCHAR(64))
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
                    WHERE role_id = CAST(:role_id AS VARCHAR(64))
                )
                """
            ),
            {"role_id": role_id, "timestamp": timestamp},
        )


def _refuse_config_losing_downgrade() -> None:
    connection = op.get_bind()
    codes = tuple(item[0] for item in PERMISSIONS)
    permission_ids = tuple(_permission_id(code) for code in codes)
    unexpected_bindings = connection.execute(
        sa.text(
            """
            SELECT role_id, permission_id
            FROM auth_role_permissions
            WHERE permission_id IN :permission_ids
              AND id NOT LIKE 'phase1:%'
            LIMIT 1
            """
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"permission_ids": permission_ids},
    ).first()
    configured_override = connection.execute(
        sa.text(
            """
            SELECT id FROM auth_user_permission_overrides
            WHERE permission_id IN :permission_ids
            LIMIT 1
            """
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"permission_ids": permission_ids},
    ).first()
    referenced_request = connection.execute(
        sa.text(
            """
            SELECT id FROM auth_access_request_items
            WHERE permission_id IN :permission_ids
            LIMIT 1
            """
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"permission_ids": permission_ids},
    ).first()
    if unexpected_bindings or configured_override or referenced_request:
        raise CommandError(
            "20260901_0089 cannot be downgraded after the Phase 1 permissions "
            "have custom role, user-override or access-request state"
        )


def downgrade() -> None:
    if op.get_context().as_sql:
        raise CommandError(
            "20260901_0089 requires an online downgrade so authorization "
            "state can be protected"
        )
    _refuse_config_losing_downgrade()
    connection = op.get_bind()
    codes = tuple(item[0] for item in PERMISSIONS)
    permission_ids = tuple(_permission_id(code) for code in codes)
    connection.execute(
        sa.text(
            "DELETE FROM auth_role_permissions WHERE permission_id IN :permission_ids"
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"permission_ids": permission_ids},
    )
    connection.execute(
        sa.text(
            "DELETE FROM auth_permission_metadata "
            "WHERE permission_id IN :permission_ids"
        ).bindparams(sa.bindparam("permission_ids", expanding=True)),
        {"permission_ids": permission_ids},
    )
    connection.execute(
        sa.text("DELETE FROM auth_permissions WHERE code IN :codes").bindparams(
            sa.bindparam("codes", expanding=True)
        ),
        {"codes": codes},
    )
