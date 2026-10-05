"""Personal work centre projection and state (additive; preserves legacy tables)."""
from alembic import op
import sqlalchemy as sa

revision = "20260928_0126"
down_revision = "20260926_0125"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("molding_sample_problems", sa.Column("responsibility_revision", sa.Integer, nullable=False, server_default="1"))
    op.create_table("work_center_entries",
        sa.Column("id", sa.String(512), primary_key=True),
        sa.Column("canonical_key", sa.String(512), nullable=False, unique=True),
        sa.Column("module", sa.String(40), nullable=False), sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False), sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("lifecycle", sa.String(24)), sa.Column("content_version", sa.Integer, nullable=False),
        sa.Column("attention_version", sa.Integer, nullable=False), sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolution_reason", sa.String(255), nullable=False), sa.Column("evidence", sa.JSON, nullable=False))
    op.create_index("ix_wc_source", "work_center_entries", ["module", "entity_id"])
    op.create_index("ix_wc_scope", "work_center_entries", ["factory_id", "kind", "lifecycle", "opened_at", "id"])
    op.create_table("work_center_events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("entry_id", sa.String(512), sa.ForeignKey("work_center_entries.id"), nullable=False),
        sa.Column("source_event_key", sa.String(128), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_kind", sa.String(32), nullable=False), sa.Column("safe_summary", sa.String(255), nullable=False),
        sa.UniqueConstraint("entry_id", "source_event_key", name="uq_wc_event_source"))
    op.create_index("ix_wc_event_page", "work_center_events", ["entry_id", "occurred_at", "id"])
    op.create_table("work_center_user_states",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("auth_users.id"), primary_key=True),
        sa.Column("employment_epoch", sa.Integer, primary_key=True), sa.Column("entry_id", sa.String(512), primary_key=True),
        sa.Column("read_version", sa.Integer, nullable=False), sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("snoozed_until", sa.DateTime(timezone=True)), sa.Column("snoozed_attention_version", sa.Integer, nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True)), sa.Column("pinned_at", sa.DateTime(timezone=True)),
        sa.Column("state_version", sa.Integer, nullable=False), sa.Column("following", sa.Boolean, nullable=False, server_default=sa.true()))
    op.create_table("work_center_preferences",
        sa.Column("user_id", sa.String(64), sa.ForeignKey("auth_users.id"), primary_key=True),
        sa.Column("values", sa.JSON, nullable=False), sa.Column("version", sa.Integer, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))


def downgrade():
    # Retain personal reading evidence unless explicitly exported and cleared.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM work_center_user_states")) or bind.scalar(sa.text("SELECT count(*) FROM work_center_preferences")):
        raise RuntimeError("Export personal work-centre state before schema downgrade; prefer UI rollback with tables retained")
    for table in ("work_center_preferences", "work_center_user_states", "work_center_events", "work_center_entries"):
        op.drop_table(table)
    op.drop_column("molding_sample_problems", "responsibility_revision")
