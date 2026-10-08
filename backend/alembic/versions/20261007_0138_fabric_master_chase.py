"""Add confirmed fabric master data and audited starting chase quantities."""
from alembic import op
import sqlalchemy as sa

revision = "20261007_0138"
down_revision = "20261006_0137"
branch_labels = None
depends_on = None


def upgrade():
    # Additive migration: preserve all existing receipt/FK evidence without a table rebuild.
    op.add_column("fabric_receipts", sa.Column("baseline_known", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.create_table("fabric_master_records",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False), sa.Column("code", sa.String(128), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("data_json", sa.Text(), nullable=False), sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_fabric_master_factory"), sa.UniqueConstraint("factory_id", "kind", "code", name="uq_fabric_master_code"),
        sa.CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_master_factory"),
        sa.CheckConstraint("kind IN ('MATERIAL','SUPPLIER','LOCATION','UNIT')", name="ck_fabric_master_kind"),
        sa.CheckConstraint("status IN ('DRAFT','ACTIVE','INACTIVE')", name="ck_fabric_master_status"))
    op.create_table("fabric_master_changes",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False), sa.Column("record_id", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False), sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False), sa.Column("actor_name", sa.String(128), nullable=False), sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "request_id", name="uq_fabric_master_request"),
        sa.ForeignKeyConstraint(["record_id", "factory_id"], ["fabric_master_records.id", "fabric_master_records.factory_id"]))
    op.create_table("fabric_chase_resolutions",
        sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False), sa.Column("source_line_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("request_id", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("starting_quantity", sa.String(32), nullable=False), sa.Column("source_json", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False), sa.Column("cutoff_json", sa.Text(), nullable=False),
        sa.Column("actor_id", sa.String(64), nullable=False), sa.Column("actor_name", sa.String(128), nullable=False), sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "request_id", name="uq_fabric_chase_request"), sa.UniqueConstraint("source_line_id", "revision", name="uq_fabric_chase_revision"),
        sa.ForeignKeyConstraint(["source_line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
        sa.CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_chase_factory"), sa.CheckConstraint("CAST(starting_quantity AS NUMERIC) >= 0", name="ck_fabric_chase_quantity"))
    for name, columns in {"fabric_master_records": ("factory_id",), "fabric_master_changes": ("factory_id", "record_id"), "fabric_chase_resolutions": ("factory_id", "source_line_id")}.items():
        for column in columns:
            op.create_index(f"ix_{name}_{column}", name, [column])


def downgrade():
    bind = op.get_bind()
    for name in ("fabric_master_records", "fabric_master_changes", "fabric_chase_resolutions"):
        if bind.execute(sa.text(f"SELECT 1 FROM {name} LIMIT 1")).first():
            raise RuntimeError("已有布料资料或追货核对证据，禁止删除降级")
    if bind.execute(sa.text("SELECT 1 FROM fabric_receipts WHERE baseline_known IS FALSE LIMIT 1")).first():
        raise RuntimeError("已有数量未知的实际收料，旧版不能解释该状态，禁止降级")
    for name in ("fabric_master_changes", "fabric_chase_resolutions", "fabric_master_records"):
        op.drop_table(name)
    op.drop_column("fabric_receipts", "baseline_known")
