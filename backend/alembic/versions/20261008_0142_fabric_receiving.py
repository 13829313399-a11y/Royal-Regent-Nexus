"""Add physical fabric receipts, batches and inbound stock without historical posting."""
from alembic import op
import sqlalchemy as sa

revision = "20261008_0142"
down_revision = "20261006_0139"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("fabric_receipts",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_line_id", sa.String(64), nullable=False), sa.Column("source_revision", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("delivery_reference", sa.String(128), nullable=False), sa.Column("receipt_date", sa.String(10), nullable=False),
        sa.Column("accounting_month", sa.String(7), nullable=False), sa.Column("quantity", sa.String(32), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False), sa.Column("prior_received_quantity", sa.String(32), nullable=False),
        sa.Column("source_json", sa.Text(), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False), sa.Column("actor_name", sa.String(128), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_fabric_receipt_factory"),
        sa.UniqueConstraint("factory_id", "request_id", name="uq_fabric_receipt_request"),
        sa.UniqueConstraint("factory_id", "source_line_id", "delivery_reference", name="uq_fabric_receipt_delivery"),
        sa.ForeignKeyConstraint(["source_line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
        sa.CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_receipt_factory"),
        sa.CheckConstraint("CAST(quantity AS NUMERIC) > 0", name="ck_fabric_receipt_quantity"))
    op.create_table("fabric_stock_batches",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.String(64), nullable=False), sa.Column("location", sa.String(128), nullable=False),
        sa.Column("dye_lot", sa.String(128), nullable=False), sa.Column("roll_no", sa.String(128), nullable=False),
        sa.Column("material_category", sa.String(16), nullable=False), sa.Column("quality_status", sa.String(32), nullable=False),
        sa.UniqueConstraint("id", "receipt_id", "factory_id", name="uq_fabric_batch_receipt_factory"),
        sa.ForeignKeyConstraint(["receipt_id", "factory_id"], ["fabric_receipts.id", "fabric_receipts.factory_id"]),
        sa.CheckConstraint("quality_status = 'PENDING_INSPECTION'", name="ck_fabric_batch_quality"))
    op.create_table("fabric_inventory_movements",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.String(64), nullable=False), sa.Column("batch_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("quantity", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(["batch_id", "receipt_id", "factory_id"], ["fabric_stock_batches.id", "fabric_stock_batches.receipt_id", "fabric_stock_batches.factory_id"]),
        sa.UniqueConstraint("batch_id", "kind", name="uq_fabric_batch_inbound"),
        sa.CheckConstraint("kind = 'RECEIPT'", name="ck_fabric_movement_kind"),
        sa.CheckConstraint("CAST(quantity AS NUMERIC) > 0", name="ck_fabric_movement_quantity"))
    for name, columns in {
        "fabric_receipts": ("factory_id", "source_line_id", "receipt_date"),
        "fabric_stock_batches": ("factory_id", "receipt_id"),
        "fabric_inventory_movements": ("factory_id", "receipt_id", "batch_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{name}_{column}", name, [column])


def downgrade():
    bind = op.get_bind()
    for name in ("fabric_receipts", "fabric_stock_batches", "fabric_inventory_movements"):
        if bind.execute(sa.text(f"SELECT 1 FROM {name} LIMIT 1")).first():
            raise RuntimeError("已有真实布料收料或库存证据，禁止降级删除")
    for name in ("fabric_inventory_movements", "fabric_stock_batches", "fabric_receipts"):
        op.drop_table(name)
