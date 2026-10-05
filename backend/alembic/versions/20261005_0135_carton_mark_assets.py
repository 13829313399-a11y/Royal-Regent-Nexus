"""Store independent carton-mark source files and optional contract associations."""
from alembic import op
import sqlalchemy as sa
import hashlib
import json
import unicodedata
from uuid import uuid4

revision = "20261005_0135"
down_revision = "20261005_0134"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("carton_mark_assets",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("contract_number", sa.String(128), nullable=False),
        sa.Column("bound_order_id", sa.String(96), sa.ForeignKey("carton_orders.id", ondelete="SET NULL", name="fk_carton_mark_asset_order_delete"), nullable=True),
        sa.Column("recognition_source", sa.String(32), nullable=False),
        sa.Column("candidates_json", sa.Text(), nullable=False),
        sa.Column("warning", sa.String(500), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "sha256", name="uq_carton_mark_asset_factory_sha"),
        sa.ForeignKeyConstraint(["bound_order_id", "factory_id"],
            ["carton_orders.id", "carton_orders.factory_id"], name="fk_carton_mark_asset_order_factory"),
        sa.CheckConstraint("kind IN ('excel', 'pdf')", name="ck_carton_mark_asset_kind"),
        sa.CheckConstraint("revision >= 1 AND size_bytes > 0", name="ck_carton_mark_asset_size_revision"))
    op.create_index("ix_carton_mark_asset_factory_contract", "carton_mark_assets", ["factory_id", "contract_number"])
    # Bring already-uploaded original files into the repository without changing
    # their template checks, approval evidence or historical metadata.
    connection = op.get_bind()
    grouped = {}
    for row in connection.execute(sa.text("""
        SELECT d.factory_id, d.file_name, d.kind, d.content_type, d.content,
               t.contract_number, t.created_by, t.created_by_name, t.created_at
        FROM carton_mark_documents d JOIN carton_mark_templates t
          ON t.id = d.template_id AND t.factory_id = d.factory_id
        WHERE t.is_archived = false ORDER BY t.created_at, t.id
    """)).mappings():
        digest = hashlib.sha256(row["content"]).hexdigest()
        key = (row["factory_id"], digest)
        group = grouped.setdefault(key, {"row": row, "contracts": {}})
        contract = row["contract_number"].strip()
        if contract:
            normalized = " ".join(unicodedata.normalize("NFKC", contract).split()).casefold()
            group["contracts"][normalized] = contract
    table = sa.table("carton_mark_assets", *[
        sa.column(name) for name in ("id", "factory_id", "file_name", "kind", "content_type", "size_bytes",
        "sha256", "content", "contract_number", "bound_order_id", "recognition_source", "candidates_json",
        "warning", "revision", "is_archived", "created_by", "created_by_name", "created_at", "updated_at")])
    for (factory, digest), group in grouped.items():
        row = group["row"]
        candidates = sorted(group["contracts"].values())
        connection.execute(table.insert().values(id=f"CMA-{uuid4().hex}", factory_id=factory,
            file_name=row["file_name"], kind="pdf" if row["kind"] == "print_pdf" else "excel",
            content_type=row["content_type"], size_bytes=len(row["content"]), sha256=digest, content=row["content"],
            contract_number=candidates[0] if len(candidates) == 1 else "", bound_order_id=None,
            recognition_source="template", candidates_json=json.dumps(candidates),
            warning="历史资料对应多个合同号，请手工确认。" if len(candidates) > 1 else "",
            revision=1, is_archived=False, created_by=row["created_by"], created_by_name=row["created_by_name"],
            created_at=row["created_at"], updated_at=row["created_at"]))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM carton_mark_assets LIMIT 1")).first():
        raise RuntimeError("箱唛资料仓库已有原文件，禁止降级丢失资料")
    op.drop_table("carton_mark_assets")
