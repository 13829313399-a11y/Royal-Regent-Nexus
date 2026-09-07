"""Typed 3D operations resources for planning, spools and internal requests."""

import sqlalchemy as sa
from alembic import op

revision = "20260904_0099"
down_revision = "20260904_0098"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "three_d_printing_operations_items",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("resource_key", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(96), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-a'", name="ck_3d_ops_factory"),
        sa.CheckConstraint(
            "kind IN ('spool','request','file_alias','profile','file','run_evidence')",
            name="ck_3d_ops_kind",
        ),
        sa.CheckConstraint("length(data_json) <= 16384", name="ck_3d_ops_payload"),
        sa.UniqueConstraint(
            "factory_id", "kind", "resource_key", name="uq_3d_ops_resource"
        ),
    )
    op.create_index(
        "ix_three_d_printing_operations_items_factory_id",
        "three_d_printing_operations_items",
        ["factory_id"],
    )
    op.create_index(
        "ix_three_d_printing_operations_items_kind",
        "three_d_printing_operations_items",
        ["kind"],
    )


def downgrade():
    raise RuntimeError(
        "Preserve operations data; restore a verified backup instead of destructive downgrade"
    )
