"""Group original carton-mark photos without changing their bytes or identity."""
from alembic import op
import sqlalchemy as sa

revision = "20261006_0139"
down_revision = "20261006_0138"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("carton_mark_assets") as batch:
        batch.add_column(sa.Column("photo_group_id", sa.String(96), nullable=True))
        batch.create_check_constraint("ck_carton_mark_asset_photo_group", "photo_group_id IS NULL OR kind = 'image'")
        batch.create_index("ix_carton_mark_asset_factory_photo_group", ["factory_id", "photo_group_id"])


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM carton_mark_assets WHERE photo_group_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("箱唛资料已有照片组，请先解除分组，禁止降级丢失分组信息")
    with op.batch_alter_table("carton_mark_assets") as batch:
        batch.drop_index("ix_carton_mark_asset_factory_photo_group")
        batch.drop_constraint("ck_carton_mark_asset_photo_group", type_="check")
        batch.drop_column("photo_group_id")
