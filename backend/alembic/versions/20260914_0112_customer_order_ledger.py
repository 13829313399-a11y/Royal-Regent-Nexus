"""Order ledger, immutable order versions, downstream inbox and shipment evidence."""
from alembic import op
import sqlalchemy as sa

revision = "20260914_0112"
down_revision = "20260912_0111"
branch_labels = None
depends_on = None

TABLES = (
    "order_ledger_lines", "order_ledger_versions", "order_ledger_sources",
    "order_ledger_line_sources", "order_ledger_dispatches", "order_ledger_shipments", "order_ledger_shipment_reversals",
    "order_ledger_identities",
)
IMMUTABLE = ("order_ledger_versions", "order_ledger_sources", "order_ledger_line_sources", "order_ledger_shipments", "order_ledger_shipment_reversals", "order_ledger_identities")


def col(name, type_=None, **kwargs):
    return sa.Column(name, type_ if type_ is not None else sa.String(64), nullable=False, **kwargs)


def upgrade():
    op.create_table(TABLES[0],
        col("id", primary_key=True), col("factory_id"), col("customer_code"), col("customer_name", sa.String(128)),
        col("identity_key"), col("reference_no", sa.String(255)), col("product_no", sa.String(255)),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True), col("shipped_quantity", sa.Numeric(18, 4)),
        col("status", sa.String(24)), col("version", sa.Integer()), col("revision", sa.Integer()),
        col("data", sa.JSON()), col("created_at", sa.String(32)), col("updated_at", sa.String(32)),
        sa.UniqueConstraint("factory_id", "customer_code", "identity_key", name="uq_order_ledger_identity"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_order_ledger_quantity"),
        sa.CheckConstraint("shipped_quantity >= 0 AND (quantity IS NULL OR shipped_quantity <= quantity)", name="ck_order_ledger_shipped"))
    op.create_table(TABLES[1],
        col("id", primary_key=True), col("line_id"), col("version", sa.Integer()), col("data", sa.JSON()),
        col("reason", sa.Text()), col("actor", sa.String(255)), col("created_at", sa.String(32)),
        sa.ForeignKeyConstraint(["line_id"], ["order_ledger_lines.id"]),
        sa.UniqueConstraint("line_id", "version", name="uq_order_ledger_version"))
    op.create_table(TABLES[2],
        col("id", primary_key=True), col("factory_id"), col("customer_code"), col("sha256"),
        col("file_name", sa.String(255)), col("kind", sa.String(24)), col("content", sa.LargeBinary()),
        sa.UniqueConstraint("factory_id", "customer_code", "sha256", "kind", name="uq_order_ledger_source"))
    op.create_table(TABLES[3], col("line_id", primary_key=True), col("source_id", primary_key=True),
        sa.ForeignKeyConstraint(["line_id"], ["order_ledger_lines.id"]),
        sa.ForeignKeyConstraint(["source_id"], ["order_ledger_sources.id"]))
    op.create_table(TABLES[4], col("id", primary_key=True), col("line_id"), col("factory_id"),
        col("recipient", sa.String(24)), col("version", sa.Integer()), col("snapshot", sa.JSON()),
        col("actor", sa.String(255)), col("created_at", sa.String(32)), col("received_at", sa.String(32)), col("received_by", sa.String(255)),
        sa.ForeignKeyConstraint(["line_id"], ["order_ledger_lines.id"]),
        sa.UniqueConstraint("line_id", "version", "recipient", name="uq_order_ledger_dispatch"))
    op.create_table(TABLES[5], col("id", primary_key=True), col("line_id"), col("factory_id"),
        col("idempotency_key", sa.String(96)), col("request_hash"), col("quantity", sa.Numeric(18, 4)),
        col("ship_date", sa.String(10)), col("document_no", sa.String(255)), col("note", sa.Text()),
        col("actor", sa.String(255)), col("created_at", sa.String(32)),
        sa.ForeignKeyConstraint(["line_id"], ["order_ledger_lines.id"]),
        sa.UniqueConstraint("factory_id", "idempotency_key", name="uq_order_ledger_shipment_key"),
        sa.CheckConstraint("quantity > 0", name="ck_order_ledger_shipment_quantity"))
    op.create_table(TABLES[6], col("shipment_id", primary_key=True), col("reason", sa.Text()),
        col("actor", sa.String(255)), col("created_at", sa.String(32)),
        sa.ForeignKeyConstraint(["shipment_id"], ["order_ledger_shipments.id"]))
    op.create_table(TABLES[7], col("factory_id", primary_key=True), col("customer_code", primary_key=True),
        col("identity_key", primary_key=True), col("line_id"), sa.ForeignKeyConstraint(["line_id"], ["order_ledger_lines.id"]))
    for table, columns in (
        (TABLES[0], ("factory_id", "customer_code")), (TABLES[1], ("line_id",)),
        (TABLES[2], ("factory_id",)), (TABLES[4], ("line_id", "factory_id", "recipient")),
        (TABLES[5], ("line_id", "factory_id")),
        (TABLES[7], ("line_id",)),
    ):
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table in IMMUTABLE:
            for action in ("UPDATE", "DELETE"):
                op.execute(f"CREATE TRIGGER {table}_{action.lower()}_guard BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Order evidence is immutable'); END")
        op.execute("CREATE TRIGGER order_ledger_dispatch_snapshot_guard BEFORE UPDATE OF line_id, factory_id, recipient, version, snapshot, actor, created_at ON order_ledger_dispatches BEGIN SELECT RAISE(ABORT, 'Dispatch evidence is immutable'); END")
        op.execute("CREATE TRIGGER order_ledger_dispatch_delete_guard BEFORE DELETE ON order_ledger_dispatches BEGIN SELECT RAISE(ABORT, 'Dispatch evidence is immutable'); END")
    elif dialect == "postgresql":
        op.execute("CREATE FUNCTION order_ledger_immutable_guard() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'Order evidence is immutable'; END; $$")
        for table in IMMUTABLE:
            op.execute(f"CREATE TRIGGER {table}_guard BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION order_ledger_immutable_guard()")
        op.execute("CREATE TRIGGER order_ledger_dispatch_snapshot_guard BEFORE UPDATE OF line_id, factory_id, recipient, version, snapshot, actor, created_at OR DELETE ON order_ledger_dispatches FOR EACH ROW EXECUTE FUNCTION order_ledger_immutable_guard()")


def downgrade():
    connection = op.get_bind()
    for table in TABLES:
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar_one():
            raise RuntimeError("订单台账已有业务数据，禁止降级丢失订单及走货证据；请先备份并制定恢复方案")
    for table in reversed(TABLES):
        op.drop_table(table)
    if connection.dialect.name == "postgresql":
        op.execute("DROP FUNCTION order_ledger_immutable_guard()")
