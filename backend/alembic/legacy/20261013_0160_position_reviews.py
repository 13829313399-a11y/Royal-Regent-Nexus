"""Add self-service position declarations without changing existing grants."""
from alembic import op
import sqlalchemy as sa

revision = "20261013_0160"
down_revision = "20261012_0159"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("position_reviews",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("employment_epoch", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("initiator_user_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("declared_snapshot_json", sa.Text(), nullable=False),
        sa.Column("base_official_snapshot_json", sa.Text(), nullable=False),
        sa.Column("base_identity_version", sa.Integer(), nullable=False),
        sa.Column("base_authorization_version", sa.Integer(), nullable=False),
        sa.Column("confirmed_snapshot_json", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("reviewer_user_id", sa.String(64), sa.ForeignKey("auth_users.id")),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("decision_at", sa.String(32), nullable=False),
        sa.Column("applied_identity_change_ids_json", sa.Text(), nullable=False),
        sa.Column("receipt_command_id", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.Column("last_submitted_at", sa.String(32), nullable=False),
        sa.CheckConstraint("status IN ('pending','returned','applied','withdrawn','invalidated')", name="ck_position_review_status"),
        sa.CheckConstraint("origin IN ('employee','admin')", name="ck_position_review_origin"))
    predicate = sa.text("status IN ('pending','returned')")
    op.create_index("uq_position_review_open", "position_reviews", ["user_id", "employment_epoch"], unique=True,
                    postgresql_where=predicate, sqlite_where=predicate)
    op.create_index("ix_position_review_queue", "position_reviews", ["status", "created_at", "id"])
    op.create_index("ix_position_review_person", "position_reviews", ["user_id", "created_at"])
    op.create_table("position_review_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("review_id", sa.String(96), sa.ForeignKey("position_reviews.id"), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(64), sa.ForeignKey("auth_users.id"), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False),
        sa.Column("after_json", sa.Text(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False))
    op.create_index("ix_position_review_event_history", "position_review_events", ["review_id", "revision"])


def downgrade():
    bind = op.get_bind()
    if any(bind.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first()
           for table in ("position_reviews", "position_review_events")):
        raise RuntimeError("Position review history exists; keep the compatible backend and disable the new UI instead.")
    op.drop_table("position_review_events")
    op.drop_table("position_reviews")
