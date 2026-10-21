"""Explicit per-paper marks and one original supplier delivery note."""
from alembic import op
import sqlalchemy as sa

revision = "20261019_0169"
down_revision = "20261019_0168"
branch_labels = None
depends_on = None


def immutable(name):
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"CREATE TRIGGER IF NOT EXISTS {name}_no_{action.lower()} BEFORE {action} ON {name} BEGIN SELECT RAISE(ABORT, 'Carton special evidence is immutable'); END")
    else:
        op.execute(f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION carton_special_immutable()")


def upgrade():
    op.add_column("carton_special_requests", sa.Column("origin", sa.String(24), nullable=False, server_default="INTERNAL"))
    for column in (
        sa.Column("mark_mode", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("mark_attachment_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("mark_asset_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("mark_asset_revision", sa.Integer(), nullable=False, server_default="0"),
    ): op.add_column("carton_special_lines", column)
    op.add_column("carton_special_attachments", sa.Column("line_id", sa.String(96), nullable=False, server_default=""))
    # Existing shipped evidence is unchanged. Pending legacy requests must now
    # explicitly select blank paper or a confirmed production file before shipping.
    connection = op.get_bind()
    old = next(item for item in sa.inspect(connection).get_unique_constraints("carton_special_shipments")
               if item["column_names"] == ["factory_id", "supplier_id", "delivery_note_no"])
    convention = {"uq": "uq_%(table_name)s_%(column_0_name)s"}
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
    with op.batch_alter_table("carton_special_shipments", naming_convention=convention) as batch:
        batch.drop_constraint(old["name"] or "uq_carton_special_shipments_factory_id", type_="unique")
        batch.create_unique_constraint("uq_special_shipment_note_request", ["factory_id", "supplier_id", "delivery_note_no", "request_id"])
    if connection.dialect.name == "sqlite":
        immutable("carton_special_shipments")
        if connection.exec_driver_sql("PRAGMA foreign_key_check").first():
            raise RuntimeError("Unified delivery migration encountered invalid source links")
        # SQLite retains deferred counters for the dropped table even though the
        # replacement has identical keys. Re-enable immediate checking only after
        # a complete check of the rebuilt graph has succeeded.
        connection.exec_driver_sql("PRAGMA defer_foreign_keys=OFF")
    op.create_table("carton_unified_deliveries",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("delivery_note_no", sa.String(128), nullable=False),
        sa.Column("delivery_date", sa.String(10), nullable=False),
        sa.Column("children_json", sa.Text(), nullable=False),
        sa.Column("request_key", sa.String(128), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "supplier_id", "delivery_note_no", name="uq_unified_delivery_note"),
        sa.UniqueConstraint("factory_id", "created_by", "request_key", name="uq_unified_delivery_request"),
        sa.ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"]))
    op.create_index("ix_carton_unified_deliveries_factory_id", "carton_unified_deliveries", ["factory_id"])
    immutable("carton_unified_deliveries")


def downgrade():
    raise RuntimeError("Confirmed production materials and unified delivery evidence must be preserved; restore a verified backup instead")
