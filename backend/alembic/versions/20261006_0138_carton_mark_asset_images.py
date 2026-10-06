"""Allow independently uploaded carton-mark photos while preserving originals."""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0138"
down_revision = "20261006_0137"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("carton_mark_assets") as batch:
        batch.drop_constraint("ck_carton_mark_asset_kind", type_="check")
        batch.create_check_constraint("ck_carton_mark_asset_kind", "kind IN ('excel', 'pdf', 'image')")


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM carton_mark_assets WHERE kind = 'image' LIMIT 1")).first():
        raise RuntimeError("箱唛资料库已有图片原文件，禁止降级丢失图片资料")
    with op.batch_alter_table("carton_mark_assets") as batch:
        batch.drop_constraint("ck_carton_mark_asset_kind", type_="check")
        batch.create_check_constraint("ck_carton_mark_asset_kind", "kind IN ('excel', 'pdf')")
