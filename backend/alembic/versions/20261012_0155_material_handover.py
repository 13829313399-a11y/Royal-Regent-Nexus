"""Add material document preparation, scoped issuer links and immutable evidence."""
from alembic import op
import sqlalchemy as sa

revision = '20261012_0155'
down_revision = '20261010_0154'
branch_labels = None
depends_on = None


def upgrade():
    # New domain only; no old warehouse, supplier or stock rows are modified.
    from app.models.material_handover import HandoverIssuer, HandoverDocument, HandoverSource, HandoverEvent, install_immutable_guards
    metadata = sa.MetaData()
    for model in (HandoverIssuer, HandoverDocument, HandoverSource, HandoverEvent):
        model.__table__.to_metadata(metadata)
    # Independent metadata excludes ORM fresh-test DDL hooks.
    for name in ('material_handover_issuers', 'material_handover_documents', 'material_handover_sources', 'material_handover_events'):
        metadata.tables[name].create(op.get_bind())
    install_immutable_guards(op.get_bind())


def downgrade():
    connection = op.get_bind()
    names = ('material_handover_events', 'material_handover_sources', 'material_handover_documents', 'material_handover_issuers')
    for name in names:
        if connection.scalar(sa.text(f'SELECT count(*) FROM {name}')):
            raise RuntimeError('Material handover evidence is retained; downgrade would discard documents or access history')
    for name in names:
        op.drop_table(name)
    if connection.dialect.name == 'postgresql':
        op.execute('DROP FUNCTION material_handover_immutable()')
