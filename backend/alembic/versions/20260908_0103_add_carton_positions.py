"""Physical location subledger and explicit issue purpose; preserve old quantity/cost evidence."""
import hashlib
import sqlalchemy as sa
from alembic import op, context

revision = "20260908_0103"
down_revision = "20260907_0102"
branch_labels = None
depends_on = None


def upgrade():
    if context.is_offline_mode():
        raise RuntimeError("20260908_0103 requires an online migration to verify and allocate existing inventory")
    op.add_column("carton_receipt_lines", sa.Column("location_allocations_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("carton_inventory_movements", sa.Column("issue_kind", sa.String(24), nullable=False, server_default="UNKNOWN"))
    op.create_table("carton_locations",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("warehouse", sa.String(64), nullable=False),
        sa.Column("bin_code", sa.String(64), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_location_factory"),
        sa.UniqueConstraint("factory_id", "warehouse", "bin_code", name="uq_carton_location_name"))
    op.create_index("ix_carton_locations_factory_id", "carton_locations", ["factory_id"])
    op.create_table("carton_position_entries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inventory_key", sa.String(1024), nullable=False),
        sa.Column("location_id", sa.String(96), nullable=False),
        sa.Column("movement_id", sa.String(96), nullable=True),
        sa.Column("transfer_id", sa.String(96), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["location_id", "factory_id"], ["carton_locations.id", "carton_locations.factory_id"]),
        sa.ForeignKeyConstraint(["movement_id", "factory_id"], ["carton_inventory_movements.id", "carton_inventory_movements.factory_id"]),
        sa.UniqueConstraint("movement_id", "location_id", name="uq_carton_movement_position"))
    op.create_index("ix_carton_position_entries_factory_id", "carton_position_entries", ["factory_id"])
    op.create_index("ix_carton_position_entries_movement_id", "carton_position_entries", ["movement_id"])
    connection = op.get_bind()
    # Only establish an unverified allocation. Old location text is NOT a physical history.
    for factory in connection.execute(sa.text("SELECT DISTINCT factory_id FROM carton_inventory_movements")).scalars():
        identifier = "CL-UNKNOWN-" + hashlib.sha256(factory.encode()).hexdigest()[:32]
        connection.execute(sa.text("INSERT INTO carton_locations (id,factory_id,warehouse,bin_code) VALUES (:id,:factory,'待核仓位','')"),
                           {"id": identifier, "factory": factory})
        rows = connection.execute(sa.text("SELECT * FROM carton_inventory_movements WHERE factory_id=:factory ORDER BY occurred_at,id"), {"factory": factory}).mappings()
        for row in rows:
            key = row["order_line_id"] or "|".join(row[name] for name in ("customer_code", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "unit"))
            connection.execute(sa.text("""INSERT INTO carton_position_entries
                (factory_id,inventory_key,location_id,movement_id,transfer_id,quantity,occurred_at)
                VALUES (:factory,:key,:location,:movement,'',:quantity,:at)"""),
                {"factory": factory, "key": key, "location": identifier, "movement": row["id"], "quantity": row["quantity"], "at": row["occurred_at"]})


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM carton_position_entries")).scalar():
        raise RuntimeError("仓位分账证据已存在，禁止删除；请保留数据库备份")
    op.drop_table("carton_position_entries")
    op.drop_table("carton_locations")
    op.drop_column("carton_inventory_movements", "issue_kind")
    op.drop_column("carton_receipt_lines", "location_allocations_json")
