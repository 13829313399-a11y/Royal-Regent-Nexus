"""Phase 3 evidence staging and searchable task pool; preserve retained rows."""

import unicodedata

import sqlalchemy as sa
from alembic.util import CommandError

from alembic import op

revision = "20260902_0091"
down_revision = "20260902_0090"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "injection_schedule_import_rows",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("source_payload_json", sa.Text(), nullable=False),
        sa.Column("preview_payload_json", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            [
                "injection_schedule_import_batches.id",
                "injection_schedule_import_batches.factory_id",
            ],
            name="fk_is_import_rows_batch_factory",
        ),
        sa.UniqueConstraint(
            "factory_id", "batch_id", "source_row", name="uq_is_import_rows_source"
        ),
        sa.CheckConstraint("source_row > 0", name="ck_is_import_rows_positive"),
    )
    table = "injection_schedule_order_demands"
    for column in ("order_no", "product_code", "mold_code"):
        op.add_column(
            table,
            sa.Column(
                f"normalized_{column}",
                sa.String(128),
                nullable=False,
                server_default="",
            ),
        )
        op.create_index(
            f"ix_is_demand_factory_norm_{column}",
            table,
            ["factory_id", f"normalized_{column}", "id"],
        )
    op.add_column(
        table, sa.Column("import_baseline_completed", sa.Numeric(18, 6), nullable=True)
    )
    op.add_column(
        table,
        sa.Column(
            "source_snapshot_fingerprint",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "source_machine_code", sa.String(128), nullable=False, server_default=""
        ),
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.text(f"SELECT id, order_no, product_code, mold_code FROM {table}")
        )
        .mappings()
        .all()
    )
    for row in rows:
        values = {
            f"normalized_{k}": "".join(
                unicodedata.normalize("NFKC", row[k]).upper().split()
            )
            for k in ("order_no", "product_code", "mold_code")
        }
        connection.execute(
            sa.text(
                f"UPDATE {table} SET normalized_order_no=:normalized_order_no, normalized_product_code=:normalized_product_code, normalized_mold_code=:normalized_mold_code WHERE id=:id"
            ),
            {**values, "id": row["id"]},
        )
    op.create_index("ix_is_task_factory_id", table, ["factory_id", "id"])
    op.create_index(
        "ix_is_line_factory_demand_latest",
        "injection_schedule_lines",
        ["factory_id", "order_demand_id", "created_at", "id"],
    )


def downgrade():
    raise CommandError("Phase 3 来源证据不可删除；请使用已验证的迁移前备份恢复。")
