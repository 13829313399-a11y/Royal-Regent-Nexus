"""Join carton collaboration and cutting/JP readiness without changing data."""

revision = "20261020_0171"
down_revision = ("20261019_0170", "20261020_0168")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    raise RuntimeError("Merged carton and cutting evidence must be preserved; use a forward migration")
