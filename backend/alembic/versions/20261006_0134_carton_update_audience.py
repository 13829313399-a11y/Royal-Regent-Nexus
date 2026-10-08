"""Keep employee update notes private when enabling the supplier feedback portal."""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0134"
down_revision = "20261005_0133"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("carton_feature_updates", sa.Column("audience", sa.String(16),
        nullable=False, server_default="INTERNAL"))


def downgrade():
    if op.get_bind().execute(sa.text(
            "SELECT 1 FROM carton_feature_updates WHERE audience <> 'INTERNAL' LIMIT 1")).first():
        raise RuntimeError("已有供应商更新说明，禁止降级丢失发布对象")
    with op.batch_alter_table("carton_feature_updates") as batch:
        batch.drop_column("audience")
