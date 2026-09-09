"""Supplier statement snapshots and explicit receipt acceptance dates."""
import sqlalchemy as sa
from alembic import op

revision = "20260909_0105"
down_revision = "20260908_0104"
branch_labels = None
depends_on = None


def upgrade():
    # Legacy confirmation time is not proof of physical receipt; never backfill it.
    op.add_column("carton_receipts", sa.Column("acceptance_date", sa.String(10), nullable=True))
    op.create_table("carton_supplier_settlements",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("sources_json", sa.Text(), nullable=False),
        sa.Column("statement_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.String(40), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False),
        sa.Column("reopen_reason", sa.Text(), nullable=False),
        sa.UniqueConstraint("factory_id", "supplier_id", "period", "currency", "version", name="uq_carton_supplier_settlement_version"),
        sa.CheckConstraint("status IN ('DRAFT', 'CONFIRMED', 'SUPERSEDED')", name="ck_carton_supplier_settlement_status"),
        sa.CheckConstraint("revision >= 1 AND version >= 1", name="ck_carton_supplier_settlement_revision"))
    for name in ("factory_id", "supplier_id", "period"):
        op.create_index(f"ix_carton_supplier_settlements_{name}", "carton_supplier_settlements", [name])


def downgrade():
    raise RuntimeError("供应商对账版本和验收日期属于业务证据，禁止自动降级删除；请使用已验证备份恢复")
