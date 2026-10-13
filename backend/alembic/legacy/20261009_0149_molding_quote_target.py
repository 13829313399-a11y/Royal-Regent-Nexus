"""Store the quoted daily shot target independently from trial quantity."""

from alembic import op
import sqlalchemy as sa

revision = "20261009_0149"
down_revision = "20261009_0148"
branch_labels = None
depends_on = None


def upgrade():
    # Local SQLite's legacy compatibility path may have added this nullable field.
    columns = sa.inspect(op.get_bind()).get_columns("molding_sample_items")
    if not any(column["name"] == "quote_target_daily_qty" for column in columns):
        op.add_column("molding_sample_items", sa.Column("quote_target_daily_qty", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("molding_sample_items", "quote_target_daily_qty")
