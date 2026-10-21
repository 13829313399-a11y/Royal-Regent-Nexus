"""Join published JP and local cutting compatibility heads without data writes."""
from pathlib import Path
import runpy
from alembic import op

revision = '20261020_0168'
down_revision = ('20261017_0167', '20261019_0167')
branch_labels = None
depends_on = None


def upgrade():
    if op.get_context().as_sql:
        raise RuntimeError('0168 requires live schema validation; offline merge refused')
    preflight = runpy.run_path(str(Path(__file__).with_name(
        '20261017_0167_reconcile_cutting_jp_collision.py')))['preflight']
    if any(preflight(op.get_bind()).values()):
        raise RuntimeError('0168 requires complete cutting and JP evidence groups')


def downgrade():
    raise RuntimeError('Reconciled cutting and JP evidence cannot be deleted; use verified backup recovery')
