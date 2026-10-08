"""Add independent purchase-source evidence, without opening or inventory entries."""
from alembic import op
import sqlalchemy as sa

revision = "20261005_0131"
down_revision = "20260929_0130"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("fabric_procurement_state",
                    sa.Column("factory_id", sa.String(64), primary_key=True), sa.Column("revision", sa.Integer(), nullable=False))
    op.create_table("fabric_procurement_lines",
                    sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
                    sa.Column("identity_key", sa.String(64), nullable=False), sa.Column("ordinal", sa.Integer(), nullable=False),
                    sa.Column("status", sa.String(16), nullable=False), sa.Column("order_no", sa.String(128), nullable=False),
                    sa.Column("supplier", sa.String(255), nullable=False), sa.Column("material_code", sa.String(128), nullable=False),
                    sa.Column("production_no", sa.String(255), nullable=False), sa.Column("payload_json", sa.Text(), nullable=False),
                    sa.Column("revision", sa.Integer(), nullable=False), sa.Column("updated_at", sa.String(40), nullable=False),
                    sa.UniqueConstraint("factory_id", "identity_key", "ordinal", name="uq_fabric_purchase_source"),
                    sa.UniqueConstraint("id", "factory_id", name="uq_fabric_purchase_factory"),
                    sa.CheckConstraint("factory_id = 'huakang-c'", name="ck_fabric_purchase_factory"))
    for column in ("factory_id", "identity_key", "status", "order_no", "material_code"):
        op.create_index("ix_fabric_procurement_lines_" + column, "fabric_procurement_lines", [column])
    op.create_table("fabric_procurement_imports",
                    sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
                    sa.Column("request_id", sa.String(64), nullable=False), sa.Column("request_hash", sa.String(64), nullable=False),
                    sa.Column("source_name", sa.String(255), nullable=False), sa.Column("actor_id", sa.String(64), nullable=False),
                    sa.Column("actor_name", sa.String(128), nullable=False), sa.Column("occurred_at", sa.String(40), nullable=False),
                    sa.Column("result_json", sa.Text(), nullable=False),
                    sa.UniqueConstraint("factory_id", "request_id", name="uq_fabric_import_request"),
                    sa.UniqueConstraint("id", "factory_id", name="uq_fabric_import_factory"))
    op.create_index("ix_fabric_procurement_imports_factory_id", "fabric_procurement_imports", ["factory_id"])
    op.create_table("fabric_procurement_evidence",
                    sa.Column("id", sa.String(64), primary_key=True), sa.Column("factory_id", sa.String(64), nullable=False),
                    sa.Column("line_id", sa.String(64), nullable=False), sa.Column("import_id", sa.String(64), nullable=False),
                    sa.Column("sheet", sa.String(128), nullable=False), sa.Column("row_number", sa.Integer(), nullable=False),
                    sa.Column("before_json", sa.Text(), nullable=False), sa.Column("after_json", sa.Text(), nullable=False),
                    sa.Column("raw_json", sa.Text(), nullable=False),
                    sa.ForeignKeyConstraint(["line_id", "factory_id"], ["fabric_procurement_lines.id", "fabric_procurement_lines.factory_id"]),
                    sa.ForeignKeyConstraint(["import_id", "factory_id"], ["fabric_procurement_imports.id", "fabric_procurement_imports.factory_id"]))
    for column in ("line_id", "import_id"):
        op.create_index("ix_fabric_procurement_evidence_" + column, "fabric_procurement_evidence", [column])
    op.execute("INSERT INTO fabric_procurement_state (factory_id, revision) VALUES ('huakang-c', 0)")


def downgrade():
    # Never drop source lineage after any import, including an unchanged retry batch.
    if not op.get_context().as_sql:
        for table in ("fabric_procurement_lines", "fabric_procurement_imports", "fabric_procurement_evidence"):
            if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM " + table)).scalar():
                raise RuntimeError("已有布料仓采购来源证据，禁止删除；请保留数据库并恢复代码")
    else:
        raise RuntimeError("布料仓来源降级需在线检查，不支持离线删除")
    for table in ("fabric_procurement_evidence", "fabric_procurement_imports", "fabric_procurement_lines", "fabric_procurement_state"):
        op.drop_table(table)
