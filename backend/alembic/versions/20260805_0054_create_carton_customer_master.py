"""create factory-scoped carton customer master

Revision ID: 20260805_0054
Revises: 20260805_0053
Create Date: 2026-08-05
"""

from collections.abc import Sequence
from datetime import datetime, timezone
import hashlib

import sqlalchemy as sa
from alembic import op


revision: str = "20260805_0054"
down_revision: str | Sequence[str] | None = "20260805_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSION_CODE = "carton_procurement:customer_manage"
CUSTOMER_MANAGEMENT_ROLES = (
    "admin",
    "position_general_manager",
    "position_carton_manager",
    "position_carton_supervisor",
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
    for role_id in CUSTOMER_MANAGEMENT_ROLES:
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


def _backfill_order_customers() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT factory_id, customer_code, MAX(customer_name) AS customer_name "
            "FROM carton_orders "
            "GROUP BY factory_id, customer_code"
        )
    ).mappings().all()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for row in rows:
        key = f"{row['factory_id']}:{row['customer_code']}"
        customer_id = f"CCU-MIG-{hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]}"
        connection.execute(
            sa.text(
                "INSERT INTO carton_customers ("
                "id, factory_id, customer_code, customer_name, country_region, "
                "contact_name, contact_phone, note, status, revision, "
                "created_by, created_by_name, updated_by, updated_by_name, created_at, updated_at"
                ") SELECT "
                ":id, :factory_id, :customer_code, :customer_name, '', '', '', "
                "'由历史纸箱订单自动建立', 'ACTIVE', 1, "
                "'migration', '数据库升级', 'migration', '数据库升级', :created_at, :updated_at "
                "WHERE NOT EXISTS ("
                "SELECT 1 FROM carton_customers "
                "WHERE factory_id = :factory_id AND customer_code = :customer_code"
                ")"
            ),
            {
                "id": customer_id,
                "factory_id": row["factory_id"],
                "customer_code": str(row["customer_code"]).strip().upper(),
                "customer_name": row["customer_name"],
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )


def upgrade() -> None:
    op.create_table(
        "carton_customers",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("country_region", sa.String(128), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("contact_phone", sa.String(64), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "customer_code", name="uq_carton_customer_factory_code"),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_customer_id_factory"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_carton_customer_status"),
        sa.CheckConstraint("revision >= 1", name="ck_carton_customer_revision"),
    )
    for column in (
        "factory_id",
        "customer_code",
        "customer_name",
        "status",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    ):
        op.create_index(f"ix_carton_customers_{column}", "carton_customers", [column])
    op.create_index(
        "ix_carton_customer_factory_status_name",
        "carton_customers",
        ["factory_id", "status", "customer_name"],
    )
    _backfill_order_customers()
    _seed_permission()


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM carton_customers")).scalar_one():
        raise RuntimeError(
            "20260805_0054 cannot be downgraded after carton customer data exists; "
            "back up the factory customer master first"
        )
    op.drop_table("carton_customers")
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
