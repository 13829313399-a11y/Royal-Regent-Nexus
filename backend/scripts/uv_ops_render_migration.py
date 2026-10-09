"""Developer-only generator: empty in-memory DB, never configured business DB.

The output is a frozen Alembic revision. Review before using in any environment.
"""
import os
os.environ["DATABASE_URL"] = "sqlite://"
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine, MetaData
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code
from app.models import uv_operations as m

target = Path(__file__).resolve().parents[1]/"alembic/versions/20260923_0121_uv_ops.py"
refresh='--refresh-uncommitted-draft' in sys.argv
previous=target.read_text(encoding='utf-8') if target.exists() else None
if previous and refresh:
    import subprocess
    tracked=subprocess.run(['git','ls-files','--error-unmatch',str(target.relative_to(target.parents[3]))],cwd=target.parents[3],capture_output=True)
    if tracked.returncode==0:
        raise SystemExit('Committed/tracked revision must never be regenerated')
if target.exists() and not refresh:
    raise SystemExit("Revision already exists; do not silently regenerate a frozen revision")
metadata = MetaData()
for table in m.Base.metadata.sorted_tables:
    if table.name.startswith("uv_ops_"):
        table.to_metadata(metadata)
with create_engine("sqlite://").connect() as connection:
    operations = produce_migrations(MigrationContext.configure(connection), metadata).upgrade_ops
    rendered = render_python_code(operations)
prefix = '''"""New A-factory UV domain; no legacy UV table or grant reuse.

Revision ID: 20260923_0121
Revises: 20260922_0120
"""
from alembic import op
import sqlalchemy as sa

revision = "20260923_0121"
down_revision = "20260922_0120"
branch_labels = None
depends_on = None


def upgrade():
'''
suffix = '''
    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    settings = sa.table("uv_ops_settings", sa.column("id"), sa.column("factory_id"), sa.column("version"), sa.column("created_at"), sa.column("updated_at"), sa.column("created_by"), sa.column("timezone"), sa.column("currency"), sa.column("stale_seconds"), sa.column("data_mode"))
    op.bulk_insert(settings, [dict(id="huakang-a", factory_id="huakang-a", version=1, created_at=now, updated_at=now, created_by="migration", timezone="Asia/Shanghai", currency="CNY", stale_seconds=120, data_mode="live")])


def downgrade():
    raise RuntimeError("UV business/evidence data is retained. Disable UV_OPS_ENABLED and use a reviewed forward migration; destructive downgrade is intentionally unsupported.")
'''
if previous and refresh:
    suffix=previous[previous.index('\n    from datetime import UTC, datetime'):]
target.write_text(prefix+rendered+suffix, encoding="utf-8")
print(f"Frozen draft: {target.name}; {len(metadata.tables)} domain tables; no database upgraded")
