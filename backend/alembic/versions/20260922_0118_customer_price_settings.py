"""Factory/customer pricing inputs and immutable conversion snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "20260922_0118"
down_revision = "20260917_0117"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_price_settings",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("customer_id", sa.String(64), primary_key=True),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False),
    )
    op.create_table(
        "customer_price_settings_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("customer_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
    )
    op.create_index("ix_customer_price_settings_snapshots_factory_id", "customer_price_settings_snapshots", ["factory_id"])
    if op.get_bind().dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            op.execute(f"""CREATE TRIGGER customer_price_snapshot_no_{action.lower()}
                BEFORE {action} ON customer_price_settings_snapshots
                BEGIN SELECT RAISE(ABORT, 'customer pricing snapshot is immutable'); END""")
    elif op.get_bind().dialect.name == "postgresql":
        op.execute("""CREATE FUNCTION customer_price_snapshot_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'customer pricing snapshot is immutable'; END;
            $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER customer_price_snapshot_immutable
            BEFORE UPDATE OR DELETE ON customer_price_settings_snapshots
            FOR EACH ROW EXECUTE FUNCTION customer_price_snapshot_immutable()""")


def downgrade():
    # A downgrade must not silently destroy commercial lineage.
    if op.get_bind().execute(sa.text("SELECT 1 FROM customer_price_settings_snapshots LIMIT 1")).first():
        raise RuntimeError("Cannot discard customer pricing snapshots")
    if op.get_bind().execute(sa.text("SELECT 1 FROM customer_price_settings LIMIT 1")).first():
        raise RuntimeError("Cannot discard maintained customer pricing settings")
    op.drop_table("customer_price_settings_snapshots")
    op.drop_table("customer_price_settings")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION customer_price_snapshot_immutable()")
