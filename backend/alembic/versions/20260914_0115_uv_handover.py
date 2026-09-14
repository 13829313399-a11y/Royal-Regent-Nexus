"""UV handover comparison records; does not alter any PMC inventory table."""
from alembic import op
import sqlalchemy as sa

revision = "20260914_0115"
down_revision = "20260913_0114"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("uv_handovers",
        sa.Column("id", sa.String(64), primary_key=True, nullable=False),
        sa.Column("factory_id", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("business_date", sa.String(10), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("uv_products.id"), nullable=False),
        sa.Column("report_id", sa.String(64), sa.ForeignKey("uv_reports.id"), nullable=True),
        sa.Column("product_no", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("reported_qty", sa.Integer(), nullable=False),
        sa.Column("received_qty", sa.Integer(), nullable=False),
        sa.Column("difference_qty", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("receiver", sa.String(128), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.UniqueConstraint("factory_id", "report_id", name="uq_uv_handover_report"),
        sa.CheckConstraint("factory_id = 'huakang-a'", name="ck_uv_handover_factory"),
        sa.CheckConstraint("reported_qty >= 0 AND received_qty >= 0", name="ck_uv_handover_quantities"),
        sa.CheckConstraint("difference_qty = received_qty - reported_qty", name="ck_uv_handover_difference"),
        sa.CheckConstraint("state IN ('pending', 'reconciled', 'difference')", name="ck_uv_handover_state"),
    )
    op.create_index("ix_uv_handovers_factory_id", "uv_handovers", ["factory_id"])
    op.create_index("ix_uv_handovers_business_date", "uv_handovers", ["business_date"])
    op.create_index("ix_uv_handovers_product_id", "uv_handovers", ["product_id"])


def downgrade():
    op.drop_table("uv_handovers")
