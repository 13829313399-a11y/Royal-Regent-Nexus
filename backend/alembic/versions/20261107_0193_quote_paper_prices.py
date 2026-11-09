"""Add optional factory paper-price catalogue; preserve legacy quotation factors."""
from alembic import op
import sqlalchemy as sa
revision = '20261107_0193'
down_revision = '20261104_0192'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('internal_quote_pricing_baselines', sa.Column('paper_prices_json', sa.Text(), nullable=False, server_default='[]'))

def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT count(*) FROM internal_quote_pricing_baselines WHERE paper_prices_json <> '[]'")).scalar():
        raise RuntimeError('纸材目录已有数据，禁止删除；回退程序时应保留此列。')
    with op.batch_alter_table('internal_quote_pricing_baselines') as batch:
        batch.drop_column('paper_prices_json')
