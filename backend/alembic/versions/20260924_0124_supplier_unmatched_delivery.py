"""Preserve vendor delivery rows without a formal order for warehouse review.

Revision ID: 20260924_0124
Revises: 20260924_0123
"""
import sqlalchemy as sa
from alembic import op

revision = "20260924_0124"
down_revision = "20260924_0123"
branch_labels = None
depends_on = None


def upgrade():
    if sa.inspect(op.get_bind()).has_table("carton_supplier_unmatched_lines"):
        columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("carton_supplier_unmatched_lines")}
        if columns != {"id", "shipment_id", "factory_id", "source_sheet", "source_row", "quantity", "snapshot_json"}:
            raise RuntimeError("现有无单送货表结构与迁移不符，请先核实历史数据")
        return  # Local databases may have applied this additive table before the unrelated branch merge.
    op.create_table(
        "carton_supplier_unmatched_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("shipment_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_sheet", sa.String(128), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["shipment_id", "factory_id"],
                                ["carton_supplier_shipments.id", "carton_supplier_shipments.factory_id"]),
        sa.UniqueConstraint("shipment_id", "source_sheet", "source_row", name="uq_carton_supplier_unmatched_source"),
        sa.CheckConstraint("quantity > 0 AND source_row >= 1", name="ck_carton_supplier_unmatched_quantity"),
    )
    op.create_index("ix_carton_supplier_unmatched_lines_shipment_id", "carton_supplier_unmatched_lines", ["shipment_id"])
    op.create_index("ix_carton_supplier_unmatched_lines_factory_id", "carton_supplier_unmatched_lines", ["factory_id"])


def downgrade():
    raise RuntimeError("无单送货明细是业务证据，禁止自动删除；请从已验证备份恢复")
