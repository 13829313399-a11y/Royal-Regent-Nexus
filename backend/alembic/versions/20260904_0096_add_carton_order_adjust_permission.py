"""Add supervisor-only carton order adjustment permission.

Revision ID: 20260904_0096
Revises: 20260903_0095
"""

import sqlalchemy as sa
from alembic import op


revision = "20260904_0096"
down_revision = "20260903_0095"
branch_labels = None
depends_on = None

PERMISSION_CODE = "carton_procurement:order_adjust"
SUPERVISOR_ROLE_IDS = (
    "admin",
    "manager",
    "position_general_manager",
    "position_carton_manager",
    "position_carton_supervisor",
)


def upgrade() -> None:
    connection = op.get_bind()
    permission_id = f"perm-{PERMISSION_CODE.replace(':', '-')}"
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
            "code": PERMISSION_CODE,
            "name": "主管调整已提交纸箱订单",
            "description": "允许在尚无收料单和库存流水时追加、减单或整单退单",
        },
    )
    for role_id in SUPERVISOR_ROLE_IDS:
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_role_permissions (id, role_id, permission_id)
                SELECT
                    CAST(:id AS VARCHAR(128)),
                    CAST(:role_id AS VARCHAR(96)),
                    CAST(:permission_id AS VARCHAR(96))
                WHERE EXISTS (
                    SELECT 1 FROM auth_roles
                    WHERE id = CAST(:role_id AS VARCHAR(96))
                )
                AND NOT EXISTS (
                    SELECT 1 FROM auth_role_permissions
                    WHERE role_id = CAST(:role_id AS VARCHAR(96))
                      AND permission_id = CAST(:permission_id AS VARCHAR(96))
                )
                """
            ),
            {
                "id": f"{role_id}:{permission_id}",
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    permission_id = f"perm-{PERMISSION_CODE.replace(':', '-')}"
    connection.execute(
        sa.text("DELETE FROM auth_role_permissions WHERE permission_id = :permission_id"),
        {"permission_id": permission_id},
    )
    connection.execute(
        sa.text("DELETE FROM auth_permission_metadata WHERE permission_id = :permission_id"),
        {"permission_id": permission_id},
    )
    connection.execute(
        sa.text("DELETE FROM auth_permissions WHERE id = :permission_id"),
        {"permission_id": permission_id},
    )
