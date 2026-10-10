"""Add fixed customer layout versions without modifying originals or QC evidence."""
from alembic import op
import sqlalchemy as sa

revision = "20261010_0154"
down_revision = "20261010_0153"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("carton_mark_layouts",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("customer_key", sa.String(300), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=False),
        sa.Column("reference_name", sa.String(255), nullable=False),
        sa.Column("reference_sha256", sa.String(64), nullable=False),
        sa.Column("reference_size", sa.Integer(), nullable=False),
        sa.Column("reference_content", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"], name="fk_mark_layout_supplier_factory"),
        sa.UniqueConstraint("factory_id", "supplier_id", "customer_key", "version", name="uq_mark_layout_customer_version"),
        sa.CheckConstraint("version >= 1 AND reference_size > 0", name="ck_mark_layout_version_size"))


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM carton_mark_layouts")):
        raise RuntimeError("Customer layout history is retained; downgrade would discard evidence")
    op.drop_table("carton_mark_layouts")
