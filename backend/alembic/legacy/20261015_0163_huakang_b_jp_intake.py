"""Huakang B JP enquiry intake, no formal order or production writes."""
from alembic import op
import sqlalchemy as sa

revision = "20261015_0163"
down_revision = "20261015_0162"
branch_labels = None
depends_on = None
NAMES = ("jp_intake_references", "jp_intake_reference_events", "jp_intake_counters", "jp_intake_exports", "jp_intake_export_identities")


def upgrade():
    # Freeze the schema here: future ORM changes must not rewrite this migration.
    op.create_table("jp_intake_references",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(24), primary_key=True),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("order_ledger_sources.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-b'"), sa.CheckConstraint("revision >= 1"))
    op.create_table("jp_intake_reference_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("order_ledger_sources.id"), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.UniqueConstraint("factory_id", "kind", "revision"), sa.CheckConstraint("factory_id = 'huakang-b'"))
    op.create_index("ix_jp_intake_reference_events_factory_id", "jp_intake_reference_events", ["factory_id"])
    op.create_table("jp_intake_counters",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("last_number", sa.Integer, nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-b'"),
        sa.CheckConstraint("last_number >= 0 AND last_number <= 99999"))
    op.create_table("jp_intake_exports",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("first_number", sa.Integer, nullable=False),
        sa.Column("last_number", sa.Integer, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("content", sa.LargeBinary, nullable=False),
        sa.UniqueConstraint("factory_id", "request_hash"), sa.CheckConstraint("factory_id = 'huakang-b'"))
    op.create_index("ix_jp_intake_exports_factory_id", "jp_intake_exports", ["factory_id"])
    op.create_index("ix_jp_intake_exports_created_at", "jp_intake_exports", ["created_at"])
    op.create_table("jp_intake_export_identities",
        sa.Column("factory_id", sa.String(64), primary_key=True),
        sa.Column("identity_key", sa.String(64), primary_key=True),
        sa.Column("export_id", sa.String(64), sa.ForeignKey("jp_intake_exports.id"), nullable=False),
        sa.CheckConstraint("factory_id = 'huakang-b'"))
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE FUNCTION jp_intake_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'JP intake evidence is immutable'; END; $$ LANGUAGE plpgsql")
    for name in ("jp_intake_reference_events", "jp_intake_exports", "jp_intake_export_identities"):
        if bind.dialect.name == "sqlite":
            for action in ("update", "delete"):
                op.execute(f"CREATE TRIGGER {name}_no_{action} BEFORE {action.upper()} ON {name} BEGIN SELECT RAISE(ABORT, 'JP intake evidence is immutable'); END")
        elif bind.dialect.name == "postgresql":
            op.execute(f"CREATE TRIGGER {name}_immutable BEFORE UPDATE OR DELETE ON {name} FOR EACH ROW EXECUTE FUNCTION jp_intake_immutable()")


def downgrade():
    bind = op.get_bind()
    if any(bind.scalar(sa.text(f"SELECT count(*) FROM {name}")) for name in NAMES):
        raise RuntimeError("JP references, reserved numbers and export evidence must be preserved; downgrade refused")
    for name in reversed(NAMES):
        op.drop_table(name)
    if bind.dialect.name == 'postgresql':
        op.execute('DROP FUNCTION jp_intake_immutable()')
