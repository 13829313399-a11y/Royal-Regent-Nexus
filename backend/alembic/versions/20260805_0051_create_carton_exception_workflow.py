"""create carton import exception workflow

Revision ID: 20260805_0051
Revises: 20260805_0050
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0051"
down_revision: str | Sequence[str] | None = "20260805_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSION_CODE = "carton_procurement:exception_manage"
FULL_ACCESS_ROLES = (
    "admin",
    "manager",
    "warehouse_keeper",
    "carton_warehouse_keeper",
    "position_general_manager",
    "position_warehouse_manager",
    "position_warehouse_supervisor",
    "position_warehouse_keeper",
    "position_carton_manager",
    "position_carton_supervisor",
    "position_carton_warehouse_keeper",
)


def _seed_permission() -> None:
    connection = op.get_bind()
    permission_id = f"perm-{PERMISSION_CODE.replace(':', '-')}"
    connection.execute(
        sa.text(
            "INSERT INTO auth_permissions (id, code, name, description) "
            "SELECT :id, :code, :code, '' "
            "WHERE NOT EXISTS (SELECT 1 FROM auth_permissions WHERE code = :code)"
        ),
        {"id": permission_id, "code": PERMISSION_CODE},
    )
    for role_id in FULL_ACCESS_ROLES:
        connection.execute(
            sa.text(
                "INSERT INTO auth_role_permissions (id, role_id, permission_id) "
                "SELECT :id, :role_id, :permission_id "
                "WHERE EXISTS (SELECT 1 FROM auth_roles WHERE id = :role_id) "
                "AND NOT EXISTS ("
                "SELECT 1 FROM auth_role_permissions "
                "WHERE role_id = :role_id AND permission_id = :permission_id"
                ")"
            ),
            {
                "id": f"{role_id}:{permission_id}",
                "role_id": role_id,
                "permission_id": permission_id,
            },
        )


def upgrade() -> None:
    op.create_table(
        "carton_exceptions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("exception_no", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(96), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("customer_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("contract_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("item_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("owner_department", sa.String(128), nullable=False, server_default="纸箱下单"),
        sa.Column("status", sa.String(24), nullable=False, server_default="OPEN"),
        sa.Column("resolution_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("resolved_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("resolved_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("resolved_at", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("factory_id", "exception_no", name="uq_carton_exception_factory_no"),
        sa.CheckConstraint("severity IN ('LOW', 'MEDIUM', 'HIGH')", name="ck_carton_exception_severity"),
        sa.CheckConstraint(
            "status IN ('OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED')",
            name="ck_carton_exception_status",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_carton_exception_revision"),
    )
    for column in (
        "factory_id",
        "exception_no",
        "source_type",
        "source_id",
        "category",
        "severity",
        "customer_code",
        "customer_name",
        "contract_no",
        "item_no",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
        "resolved_by",
        "resolved_at",
    ):
        op.create_index(f"ix_carton_exceptions_{column}", "carton_exceptions", [column])
    op.create_index(
        "ix_carton_exception_factory_status",
        "carton_exceptions",
        ["factory_id", "status", "severity"],
    )
    op.create_index(
        "ix_carton_exception_source",
        "carton_exceptions",
        ["factory_id", "source_type", "source_id"],
    )
    _seed_permission()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM carton_exceptions")).scalar_one():
        raise RuntimeError(
            "20260805_0051 cannot be downgraded after carton exceptions exist; "
            "resolve and archive the exception ledger first"
        )
    op.drop_table("carton_exceptions")
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
