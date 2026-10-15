"""Stable supplier identities and append-only link management; no old row guessing."""
from alembic import op
import sqlalchemy as sa

revision = '20261012_0156'
down_revision = '20261012_0155'
branch_labels = None
depends_on = None
NAMES = ('material_handover_supplier_bindings', 'material_handover_link_commands')


def upgrade():
    from app.models.material_handover import HandoverSupplierBinding, HandoverLinkCommand, HandoverIssuer, install_immutable_guards
    from app.models.fabric_master import FabricMasterRecord
    metadata = sa.MetaData()
    for model in (FabricMasterRecord, HandoverIssuer, HandoverSupplierBinding, HandoverLinkCommand):
        model.__table__.to_metadata(metadata)
    for name in NAMES:
        metadata.tables[name].create(op.get_bind())
    install_immutable_guards(op.get_bind(), NAMES)


def downgrade():
    for name in NAMES:
        if op.get_bind().scalar(sa.text(f'SELECT count(*) FROM {name}')):
            raise RuntimeError('Supplier identity and link evidence is retained; downgrade refused')
    for name in reversed(NAMES):
        op.drop_table(name)
