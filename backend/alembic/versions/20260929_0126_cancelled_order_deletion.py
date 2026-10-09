"""Remove cancelled orders from the ledger while preserving business references."""
import sqlalchemy as sa
from alembic import op

revision = "20260929_0126"
down_revision = "20260926_0125"
branch_labels = None
depends_on = None


def upgrade():
    # Native ADD COLUMN preserves SQLite children and existing snapshots.
    op.add_column("carton_orders", sa.Column("deleted_at", sa.String(40), nullable=True))


def downgrade():
    raise RuntimeError("Removing deletion markers would restore deleted orders; restore a verified backup instead")
