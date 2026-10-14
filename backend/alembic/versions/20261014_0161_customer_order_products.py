"""Add scoped product rules and immutable evidence; no order/inventory changes."""
from alembic import op
import sqlalchemy as sa
revision = "20261014_0161"
down_revision = "20261013_0160"
branch_labels = depends_on = None
NAMES = ("customer_order_product_catalogs", "customer_order_product_changes", "customer_order_product_export_evidence")


def scope():
    return [sa.Column("factory_id", sa.String(64), nullable=False), sa.Column("customer_code", sa.String(64), nullable=False),
            sa.CheckConstraint("factory_id = 'huaxing' AND customer_code = 'dickie'")]


def upgrade():
    op.create_table(NAMES[0], *scope(), sa.Column("revision", sa.Integer, nullable=False), sa.Column("products", sa.JSON, nullable=False),
        sa.PrimaryKeyConstraint("factory_id", "customer_code"))
    op.create_table(NAMES[1], *scope(), sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("revision", sa.Integer, nullable=False), sa.Column("product_key", sa.String(80), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False), sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON, nullable=False), sa.UniqueConstraint("factory_id", "customer_code", "revision"))
    op.create_table(NAMES[2], *scope(), sa.Column("audit_id", sa.String(96), primary_key=True), sa.Column("data", sa.JSON, nullable=False))
    op.create_index('ix_order_product_history', NAMES[1], ['factory_id', 'customer_code', 'product_key', 'revision'])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION customer_order_product_evidence_guard() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Product rule evidence is immutable'; END; $$ LANGUAGE plpgsql")
    for name in NAMES[1:]:
        if bind.dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION customer_order_product_evidence_guard()")
        elif bind.dialect.name == "sqlite":
            for action in ("update", "delete"):
                op.execute(f"CREATE TRIGGER {name}_no_{action} BEFORE {action.upper()} ON {name} BEGIN SELECT RAISE(ABORT, 'Product rule evidence is immutable'); END")


def downgrade():
    bind = op.get_bind()
    if any(bind.scalar(sa.text(f"SELECT count(*) FROM {name}")) for name in NAMES):
        raise RuntimeError("Retained product rules/evidence prevent destructive downgrade")
    for name in reversed(NAMES):
        op.drop_table(name)
    if bind.dialect.name == "postgresql":
        op.execute("DROP FUNCTION customer_order_product_evidence_guard()")
