"""Shared price agreements, with no historical price backfill."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_0170"
down_revision = "20261019_0169"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("carton_price_reviews",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("receipt_line_id", sa.String(96), nullable=False, unique=True),
        sa.Column("source_kind", sa.String(16), nullable=False),
        sa.Column("shipment_id", sa.String(96), nullable=False),
        sa.Column("shipment_line_id", sa.String(96), nullable=False),
        sa.Column("original_unit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("proposed_unit_price", sa.Numeric(18, 6), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["receipt_line_id", "factory_id"], ["carton_receipt_lines.id", "carton_receipt_lines.factory_id"]),
        sa.ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]),
        sa.CheckConstraint("status IN ('PENDING','PROPOSED','CONFIRMED') AND revision >= 1", name="ck_carton_price_review_status"),
        sa.CheckConstraint("source_kind IN ('REGULAR','SPECIAL') AND (status = 'PENDING' OR proposed_unit_price IS NOT NULL)", name="ck_carton_price_review_source"),
        sa.CheckConstraint("original_unit_price >= 0 AND proposed_unit_price >= 0", name="ck_carton_price_review_price"))
    for column in ("factory_id", "supplier_id", "shipment_id"):
        op.create_index("ix_carton_price_reviews_" + column, "carton_price_reviews", [column])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM carton_price_reviews LIMIT 1")).first():
        raise RuntimeError("Refusing to erase carton price agreement evidence")
    op.drop_table("carton_price_reviews")
