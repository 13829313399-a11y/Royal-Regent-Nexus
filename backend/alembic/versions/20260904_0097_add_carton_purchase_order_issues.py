"""Add immutable carton supplier purchase-order issues.

Revision ID: 20260904_0097
Revises: 20260904_0096
"""

from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op


revision = "20260904_0097"
down_revision = "20260904_0096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "carton_purchase_order_issues",
        sa.Column("id", sa.String(length=96), primary_key=True),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=96), nullable=False),
        sa.Column("order_no", sa.String(length=64), nullable=False),
        sa.Column("document_no", sa.String(length=96), nullable=False),
        sa.Column("document_type", sa.String(length=24), nullable=False),
        sa.Column("issue_sequence", sa.Integer(), nullable=False),
        sa.Column("source_order_revision", sa.Integer(), nullable=False),
        sa.Column("before_product_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("after_product_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("product_quantity_delta", sa.Numeric(18, 6), nullable=False),
        sa.Column("snapshot_json", sa.Text(), nullable=False),
        sa.Column("generated_by", sa.String(length=64), nullable=False),
        sa.Column("generated_by_name", sa.String(length=128), nullable=False, server_default=""),
        sa.Column("generated_at", sa.String(length=40), nullable=False),
        sa.CheckConstraint("issue_sequence >= 0", name="ck_carton_po_issue_sequence"),
        sa.CheckConstraint(
            "document_type IN ('LEGACY_BASELINE', 'INITIAL', 'APPEND', 'REDUCE', 'ADJUSTMENT')",
            name="ck_carton_po_issue_document_type",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            ["carton_orders.id", "carton_orders.factory_id"],
            name="fk_carton_po_issue_order_factory",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("factory_id", "document_no", name="uq_carton_po_issue_factory_document"),
        sa.UniqueConstraint("order_id", "issue_sequence", name="uq_carton_po_issue_order_sequence"),
    )
    op.create_index(
        "ix_carton_po_issue_factory_order",
        "carton_purchase_order_issues",
        ["factory_id", "order_id", "issue_sequence"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_factory_id",
        "carton_purchase_order_issues",
        ["factory_id"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_order_id",
        "carton_purchase_order_issues",
        ["order_id"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_order_no",
        "carton_purchase_order_issues",
        ["order_no"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_document_no",
        "carton_purchase_order_issues",
        ["document_no"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_document_type",
        "carton_purchase_order_issues",
        ["document_type"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_generated_by",
        "carton_purchase_order_issues",
        ["generated_by"],
    )
    op.create_index(
        "ix_carton_purchase_order_issues_generated_at",
        "carton_purchase_order_issues",
        ["generated_at"],
    )

    connection = op.get_bind()
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    orders = connection.execute(
        sa.text(
            """
            SELECT id, factory_id, order_no, customer_code, customer_name,
                   supplier_id, supplier_name_snapshot, contract_no, item_no,
                   product_name, product_order_quantity, order_date, due_date,
                   status, note, revision
            FROM carton_orders
            WHERE status IN ('PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED')
            """
        )
    ).mappings().all()
    for order in orders:
        lines = connection.execute(
            sa.text(
                """
                SELECT id, line_no, packaging_type, paper_quality, specification,
                       dimension_unit, usage_quantity, required_quantity, unit,
                       unit_price, currency, price_source, note
                FROM carton_order_lines
                WHERE order_id = :order_id
                ORDER BY line_no
                """
            ),
            {"order_id": order["id"]},
        ).mappings().all()
        snapshot = {
            "order": {key: str(value) if value is not None else "" for key, value in order.items()},
            "before_product_quantity": str(order["product_order_quantity"]),
            "after_product_quantity": str(order["product_order_quantity"]),
            "product_quantity_delta": "0",
            "before_due_date": order["due_date"],
            "after_due_date": order["due_date"],
            "lines": [
                {
                    **{key: str(value) if value is not None else "" for key, value in line.items()},
                    "before_required_quantity": str(line["required_quantity"]),
                    "after_required_quantity": str(line["required_quantity"]),
                    "required_quantity_delta": "0",
                }
                for line in lines
            ],
        }
        connection.execute(
            sa.text(
                """
                INSERT INTO carton_purchase_order_issues (
                    id, factory_id, order_id, order_no, document_no, document_type,
                    issue_sequence, source_order_revision, before_product_quantity,
                    after_product_quantity, product_quantity_delta, snapshot_json,
                    generated_by, generated_by_name, generated_at
                ) VALUES (
                    :id, :factory_id, :order_id, :order_no, :document_no,
                    'LEGACY_BASELINE', 0, :source_order_revision,
                    :product_quantity, :product_quantity, 0, :snapshot_json,
                    'system', '系统迁移', :generated_at
                )
                """
            ),
            {
                "id": f"CPOI-{uuid4().hex}",
                "factory_id": order["factory_id"],
                "order_id": order["id"],
                "order_no": order["order_no"],
                "document_no": f"{order['order_no']}-BASE",
                "source_order_revision": order["revision"],
                "product_quantity": order["product_order_quantity"],
                "snapshot_json": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
                "generated_at": timestamp,
            },
        )


def downgrade() -> None:
    connection = op.get_bind()
    formal_issue_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM carton_purchase_order_issues
            WHERE document_type <> 'LEGACY_BASELINE'
            """
        )
    ).scalar_one()
    if formal_issue_count:
        raise RuntimeError(
            "cannot downgrade carton purchase-order issues after formal supplier documents exist; "
            "export and preserve immutable issue history before any manual recovery"
        )
    op.drop_index("ix_carton_purchase_order_issues_generated_at", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_generated_by", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_document_type", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_document_no", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_order_no", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_order_id", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_purchase_order_issues_factory_id", table_name="carton_purchase_order_issues")
    op.drop_index("ix_carton_po_issue_factory_order", table_name="carton_purchase_order_issues")
    op.drop_table("carton_purchase_order_issues")
