"""Add carton planning/rush columns after the published Indonesia option chain.

The locally applied carton 0173 is frozen in legacy/. Its identifier collided
with the published Indonesia 0173, so it must never enter the canonical graph.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261022_0175'
down_revision = '20261022_0174'
branch_labels = None
depends_on = None


def columns():
    return [
        sa.Column('plan_date_manual', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rush', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('rush_reason', sa.String(255), nullable=False, server_default=''),
        sa.Column('rush_at', sa.String(40), nullable=True),
        sa.Column('rush_by', sa.String(64), nullable=True),
        sa.Column('rush_ack_at', sa.String(40), nullable=True),
        sa.Column('rush_ack_by', sa.String(64), nullable=True),
    ]


def validate_rush_schema(bind):
    actual = {column['name']: column for column in sa.inspect(bind).get_columns('carton_orders')}
    for expected in columns():
        value = actual.get(expected.name)
        if value is None or value['nullable'] != expected.nullable or str(value['type']) != str(expected.type):
            raise RuntimeError(f'Carton rush schema mismatch: {expected.name}; inspect before migration')


def upgrade():
    if not op.get_context().as_sql:
        actual = {column['name'] for column in sa.inspect(op.get_bind()).get_columns('carton_orders')}
        present = actual & {column.name for column in columns()}
        if present:
            # Explicitly repaired legacy stores can adopt only the complete schema.
            # This does not reinterpret or stamp their ambiguous version record.
            validate_rush_schema(op.get_bind())
            return
    for column in columns():
        op.add_column('carton_orders', column)


def downgrade():
    raise RuntimeError('Carton planning and rush evidence must be preserved; use a forward migration')
