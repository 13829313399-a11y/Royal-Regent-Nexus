"""add IAM position scope modes and permission access kinds

Revision ID: 20260717_0024
Revises: 20260716_0023
Create Date: 2026-07-17 10:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260717_0024"
down_revision: Union[str, None] = "20260716_0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


READ_PERMISSION_CODES = (
    "molding_sample:read",
    "molding_sample:cross_factory_read",
    "molding_sample:cross_factory_cost_read",
    "molding_sample:production_read",
    "molding_sample:audit_read",
    "molding_sample:notification_read",
    "carton_mark:read",
    "customer_price:read",
    "customer_price:compare",
    "injection_schedule:read",
    "internal_quote:read",
    "internal_quote:summary_read",
    "internal_quote:timeline_read",
    "system:audit_read",
    "system:permission_catalog_read",
)


def upgrade() -> None:
    op.add_column(
        "auth_permission_metadata",
        sa.Column(
            "access_kind",
            sa.String(length=16),
            nullable=False,
            server_default="operate",
        ),
    )
    op.create_index(
        "ix_auth_permission_metadata_access_kind",
        "auth_permission_metadata",
        ["access_kind"],
    )
    for permission_code in READ_PERMISSION_CODES:
        op.execute(
            sa.text(
                "UPDATE auth_permission_metadata "
                "SET access_kind = 'read' "
                "WHERE permission_id = ("
                "SELECT id FROM auth_permissions WHERE code = :permission_code"
                ")"
            ).bindparams(permission_code=permission_code)
        )

    op.add_column(
        "auth_role_metadata",
        sa.Column(
            "scope_mode",
            sa.String(length=32),
            nullable=False,
            server_default="own_factory",
        ),
    )
    op.create_index(
        "ix_auth_role_metadata_scope_mode",
        "auth_role_metadata",
        ["scope_mode"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_role_metadata_scope_mode", table_name="auth_role_metadata")
    op.drop_column("auth_role_metadata", "scope_mode")
    op.drop_index("ix_auth_permission_metadata_access_kind", table_name="auth_permission_metadata")
    op.drop_column("auth_permission_metadata", "access_kind")
