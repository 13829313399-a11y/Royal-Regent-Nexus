"""Let an observation-only printer connection write production records.

Recording a finished print and controlling the device are separate concerns, so an
enabled record flag is added next to the connection owner instead of forcing a
cloud-connector handover. Existing connections are enabled: the old standalone writer
is no longer the record source, and retroactive creation is prevented by the
reconciliation start date rather than by the owner.
"""
from alembic import op
import sqlalchemy as sa

revision = "20260917_0117"
down_revision = "20260914_0116"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "three_d_printing_printer_connections",
        sa.Column(
            "record_reconcile_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade():
    op.drop_column("three_d_printing_printer_connections", "record_reconcile_enabled")
