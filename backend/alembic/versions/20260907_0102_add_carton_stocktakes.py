"""Persistent stocktake documents and immutable count evidence."""
import sqlalchemy as sa
from alembic import op

revision = "20260907_0102"
down_revision = "20260907_0101"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("carton_stocktakes",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *[sa.Column(name, sa.String(size), nullable=False) for name, size in (
            ("created_by", 64), ("created_by_name", 128), ("created_at", 40),
            ("submitted_by", 64), ("submitted_by_name", 128), ("submitted_at", 40),
            ("reviewed_by", 64), ("reviewed_by_name", 128), ("reviewed_at", 40))],
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("basis_token", sa.String(64), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_stocktake_factory"),
        sa.CheckConstraint("status IN ('DRAFT', 'SUBMITTED', 'POSTED', 'CANCELLED')", name="ck_carton_stocktake_status"),
        sa.CheckConstraint("revision >= 1", name="ck_carton_stocktake_revision"))
    op.create_index("ix_carton_stocktakes_factory_id", "carton_stocktakes", ["factory_id"])
    op.create_table("carton_stocktake_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("stocktake_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inventory_key", sa.String(1024), nullable=False),
        sa.Column("reference_movement_id", sa.String(96), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("initial_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("count_book_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("actual_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("difference", sa.Numeric(18, 4), nullable=True),
        sa.Column("location_revision", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("movement_id", sa.String(96), nullable=False),
        sa.ForeignKeyConstraint(["stocktake_id", "factory_id"], ["carton_stocktakes.id", "carton_stocktakes.factory_id"]),
        sa.UniqueConstraint("stocktake_id", "inventory_key", name="uq_carton_stocktake_line_key"),
        sa.CheckConstraint("actual_quantity IS NULL OR actual_quantity >= 0", name="ck_carton_stocktake_actual"))
    op.create_index("ix_carton_stocktake_lines_factory_id", "carton_stocktake_lines", ["factory_id"])
    op.create_index("ix_carton_stocktake_lines_stocktake_id", "carton_stocktake_lines", ["stocktake_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM carton_stocktakes")).scalar():
        raise RuntimeError("盘点证据已存在，禁止删除盘点表")
    op.drop_table("carton_stocktake_lines")
    op.drop_table("carton_stocktakes")
