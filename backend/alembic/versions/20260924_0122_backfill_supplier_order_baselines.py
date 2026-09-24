"""Make previously confirmed carton orders visible to their supplier without reissuing demand.

Revision ID: 20260923_0121
Revises: 20260923_0120
"""

import json
from datetime import datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op


revision = "20260924_0122"
down_revision = ("20260923_0120", "20260923_0121")
branch_labels = None
depends_on = None


def backfill(connection) -> int:
    orders = connection.execute(sa.text("""
        SELECT o.id, o.factory_id, o.order_no, o.customer_code, o.customer_name,
               o.supplier_id, o.supplier_name_snapshot, o.contract_no, o.customer_po,
               o.item_no, o.product_name, o.quantity_basis, o.product_order_quantity,
               o.order_date, o.customer_due_date, o.safety_lead_days, o.due_date,
               o.status, o.note, o.revision
        FROM carton_orders AS o
        WHERE o.status IN ('PENDING_SUPPLIER', 'PARTIALLY_RECEIVED', 'COMPLETED')
          AND NOT EXISTS (
              SELECT 1 FROM carton_purchase_order_issues AS i
              WHERE i.order_id = o.id AND i.factory_id = o.factory_id
          )
        ORDER BY o.factory_id, o.order_no
    """)).mappings().all()
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    for order in orders:
        lines = connection.execute(sa.text("""
            SELECT id, line_no, packaging_type, paper_quality, specification,
                   dimension_unit, usage_quantity, required_quantity, unit,
                   unit_price, currency, price_source, note
            FROM carton_order_lines
            WHERE order_id = :order_id AND factory_id = :factory_id
            ORDER BY line_no
        """), {"order_id": order["id"], "factory_id": order["factory_id"]}).mappings().all()
        if not lines:
            raise RuntimeError(f"confirmed carton order has no paper lines: {order['order_no']}")
        product_quantity = str(order["product_order_quantity"]) if order["product_order_quantity"] is not None else None
        snapshot = {
            "order": {key: str(value) if value is not None else "" for key, value in order.items()},
            "before_product_quantity": product_quantity,
            "after_product_quantity": product_quantity,
            "quantity_basis": order["quantity_basis"],
            "product_quantity_delta": "0" if product_quantity is not None else None,
            "before_due_date": order["due_date"],
            "after_due_date": order["due_date"],
            "lines": [{
                **{key: str(value) if value is not None else "" for key, value in line.items()
                   if key not in {"line_no", "usage_quantity", "unit_price", "required_quantity"}},
                "line_no": line["line_no"],
                "usage_quantity": str(line["usage_quantity"]) if line["usage_quantity"] is not None else None,
                "unit_price": str(line["unit_price"]),
                "before_required_quantity": str(line["required_quantity"]),
                "after_required_quantity": str(line["required_quantity"]),
                "required_quantity_delta": "0",
            } for line in lines],
        }
        issue_id = f"CPOI-{uuid4().hex}"
        document_no = f"{order['order_no']}-BASE"
        connection.execute(sa.text("""
            INSERT INTO carton_purchase_order_issues (
                id, factory_id, order_id, order_no, document_no, document_type,
                issue_sequence, source_order_revision, before_product_quantity,
                after_product_quantity, product_quantity_delta, snapshot_json,
                generated_by, generated_by_name, generated_at
            ) VALUES (
                :id, :factory_id, :order_id, :order_no, :document_no,
                'LEGACY_BASELINE', 0, :revision, :product_quantity,
                :product_quantity, :product_delta, :snapshot_json,
                'system', '历史订单补录', :generated_at
            )
        """), {
            "id": issue_id, "factory_id": order["factory_id"], "order_id": order["id"],
            "order_no": order["order_no"], "document_no": document_no,
            "revision": order["revision"], "product_quantity": order["product_order_quantity"],
            "product_delta": 0 if product_quantity is not None else None,
            "snapshot_json": json.dumps(snapshot, ensure_ascii=False, sort_keys=True),
            "generated_at": timestamp,
        })
        connection.execute(sa.text("""
            INSERT INTO carton_audit_events (
                id, factory_id, event_type, entity_type, entity_id, detail_json,
                actor_user_id, actor_name, created_at
            ) VALUES (
                :id, :factory_id, 'PURCHASE_ORDER_BASELINE_BACKFILLED',
                'carton_order', :order_id, :detail_json,
                'system', '系统', :created_at
            )
        """), {
            "id": f"CTA-{uuid4().hex}", "factory_id": order["factory_id"],
            "order_id": order["id"],
            "detail_json": json.dumps({"order_no": order["order_no"], "document_no": document_no,
                                       "reason": "此前已确认订单补建历史基线，不重复发行首次采购单"}, ensure_ascii=False),
            "created_at": timestamp,
        })
    return len(orders)


def upgrade() -> None:
    backfill(op.get_bind())


def downgrade() -> None:
    raise RuntimeError("supplier-visible historical baselines are immutable; restore a verified backup instead")
