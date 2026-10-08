"""Private carton feedback, replies, screenshots and published feature updates."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0136"
down_revision = "20261005_0135"
branch_labels = None
depends_on = None


def col(name, kind, **kwargs):
    return sa.Column(name, kind, nullable=False, **kwargs)


def upgrade():
    op.create_table("carton_feedback",
        col("id", sa.String(96), primary_key=True), col("factory_id", sa.String(64)),
        col("author_id", sa.String(64)), col("author_name", sa.String(128)), col("title", sa.String(120)),
        col("description", sa.Text()), col("context_path", sa.String(512)), col("status", sa.String(16)),
        col("revision", sa.Integer()), col("request_key", sa.String(64)), col("payload_sha256", sa.String(64)),
        col("created_at", sa.String(40)), col("updated_at", sa.String(40)),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_feedback_id_factory"),
        sa.UniqueConstraint("factory_id", "author_id", "request_key", name="uq_carton_feedback_request"),
        sa.CheckConstraint("status IN ('OPEN','FIXED','DECLINED') AND revision >= 1", name="ck_carton_feedback_state"))
    op.create_index("ix_carton_feedback_factory_author", "carton_feedback", ["factory_id", "author_id", "created_at"])
    for table in ("carton_feedback_replies", "carton_feedback_images"):
        columns = [col("id", sa.String(96), primary_key=True), col("factory_id", sa.String(64)),
            col("feedback_id", sa.String(96)), col("created_at", sa.String(40))]
        if table.endswith("replies"):
            columns.extend([col("author_id", sa.String(64)), col("author_name", sa.String(128)),
                col("body", sa.Text()), col("status", sa.String(16)), col("revision", sa.Integer())])
        else:
            columns.extend([col("content", sa.LargeBinary()), col("ordinal", sa.Integer())])
        op.create_table(table, *columns, sa.ForeignKeyConstraint(["feedback_id", "factory_id"],
            ["carton_feedback.id", "carton_feedback.factory_id"], ondelete="RESTRICT"))
        op.create_index("ix_" + table + "_feedback_id", table, ["feedback_id"])
    op.create_table("carton_feature_updates", col("id", sa.String(96), primary_key=True),
        col("factory_id", sa.String(64)), col("title", sa.String(120)), col("body", sa.Text()),
        col("author_id", sa.String(64)), col("author_name", sa.String(128)), col("request_key", sa.String(64)), col("created_at", sa.String(40)),
        sa.UniqueConstraint("factory_id", "author_id", "request_key", name="uq_carton_feature_update_request"))
    op.create_index("ix_carton_feature_updates_factory_id", "carton_feature_updates", ["factory_id"])


def downgrade():
    tables = ("carton_feedback_images", "carton_feedback_replies", "carton_feature_updates", "carton_feedback")
    if any(op.get_bind().execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first() for table in tables):
        raise RuntimeError("已有反馈、截图或更新说明，禁止降级丢失资料")
    for table in tables:
        op.drop_table(table)
