"""Independent product alternatives and customer-selected version history."""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0119"
down_revision = "20260922_0118"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("internal_quote_families",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("selected_quote_id", sa.String(64), nullable=False))
    op.create_index("ix_internal_quote_families_factory_id", "internal_quote_families", ["factory_id"])
    op.create_table("internal_quote_alternatives",
        sa.Column("quote_id", sa.String(64), sa.ForeignKey("internal_quotes.id"), primary_key=True),
        sa.Column("family_id", sa.String(64), sa.ForeignKey("internal_quote_families.id"), nullable=False),
        sa.Column("scenario_id", sa.String(64), nullable=False),
        sa.Column("scenario_name", sa.String(128), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_quote_id", sa.String(64), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False),
        sa.Column("issued_at", sa.String(32), nullable=False),
        sa.Column("reported_at", sa.String(32), nullable=False),
        sa.Column("archived", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("family_id", "scenario_id", "version_number", name="uq_quote_alternative_version"))
    op.create_index("ix_internal_quote_alternatives_family_id", "internal_quote_alternatives", ["family_id"])


def downgrade():
    op.drop_table("internal_quote_alternatives")
    op.drop_table("internal_quote_families")
