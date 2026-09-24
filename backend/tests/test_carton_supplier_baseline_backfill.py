"""Regression coverage for supplier visibility of pre-existing confirmed orders."""

import importlib.util
import json
from pathlib import Path

import sqlalchemy as sa


MIGRATION = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "20260923_0121_backfill_supplier_order_baselines.py"


def test_backfill_is_idempotent_and_never_resends_cancelled_or_existing_issues():
    spec = importlib.util.spec_from_file_location("supplier_backfill_0121", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine("sqlite://")
    with engine.begin() as connection:
        connection.exec_driver_sql("""CREATE TABLE carton_orders (
            id TEXT PRIMARY KEY, factory_id TEXT, order_no TEXT, customer_code TEXT, customer_name TEXT,
            supplier_id TEXT, supplier_name_snapshot TEXT, contract_no TEXT, customer_po TEXT,
            item_no TEXT, product_name TEXT, quantity_basis TEXT, product_order_quantity NUMERIC,
            order_date TEXT, customer_due_date TEXT, safety_lead_days INTEGER, due_date TEXT,
            status TEXT, note TEXT, revision INTEGER)""")
        connection.exec_driver_sql("""CREATE TABLE carton_order_lines (
            id TEXT PRIMARY KEY, factory_id TEXT, order_id TEXT, line_no INTEGER, packaging_type TEXT,
            paper_quality TEXT, specification TEXT, dimension_unit TEXT, usage_quantity NUMERIC,
            required_quantity NUMERIC, unit TEXT, unit_price NUMERIC, currency TEXT,
            price_source TEXT, note TEXT)""")
        connection.exec_driver_sql("""CREATE TABLE carton_purchase_order_issues (
            id TEXT PRIMARY KEY, factory_id TEXT, order_id TEXT, order_no TEXT,
            document_no TEXT, document_type TEXT, issue_sequence INTEGER, source_order_revision INTEGER,
            before_product_quantity NUMERIC, after_product_quantity NUMERIC, product_quantity_delta NUMERIC,
            snapshot_json TEXT, generated_by TEXT, generated_by_name TEXT, generated_at TEXT,
            UNIQUE(order_id, issue_sequence), UNIQUE(factory_id, document_no))""")
        connection.exec_driver_sql("""CREATE TABLE carton_audit_events (
            id TEXT PRIMARY KEY, factory_id TEXT, event_type TEXT, entity_type TEXT, entity_id TEXT,
            detail_json TEXT, actor_user_id TEXT, actor_name TEXT, created_at TEXT)""")
        for order_id, status, basis, product_quantity in (
            ("new", "PENDING_SUPPLIER", "CALCULATED", 100),
            ("old", "COMPLETED", "EXPLICIT", None),
            ("cancelled", "CANCELLED", "CALCULATED", 100),
            ("issued", "PENDING_SUPPLIER", "CALCULATED", 100),
        ):
            connection.execute(sa.text("""INSERT INTO carton_orders VALUES (
                :id, 'huaxing', :order_no, 'C', 'Customer', 'SUP', 'Supplier', 'CONTRACT', '',
                'ITEM', 'Product', :basis, :quantity, '2026-09-23', NULL, 3, '2026-10-01',
                :status, '', 2)"""), {"id": order_id, "order_no": f"CT-{order_id}",
                       "basis": basis, "quantity": product_quantity, "status": status})
            connection.execute(sa.text("""INSERT INTO carton_order_lines VALUES (
                :id, 'huaxing', :order_id, 1, '外箱', 'A33', '30×20×10', 'cm',
                :usage, 10, '个', 2, 'CNY', 'manual', '')"""),
                {"id": f"line-{order_id}", "order_id": order_id,
                 "usage": None if basis == "EXPLICIT" else 10})
        connection.exec_driver_sql("""INSERT INTO carton_purchase_order_issues
            (id, factory_id, order_id, order_no, document_no, document_type, issue_sequence)
            VALUES ('existing', 'huaxing', 'issued', 'CT-issued', 'CT-issued-P00', 'INITIAL', 1)""")
        assert module.backfill(connection) == 2
        assert module.backfill(connection) == 0
        rows = connection.execute(sa.text("""SELECT order_id, document_type, snapshot_json
            FROM carton_purchase_order_issues WHERE document_type = 'LEGACY_BASELINE'
            ORDER BY order_id""")).all()
        assert [row[0] for row in rows] == ["new", "old"]
        assert all(json.loads(row[2])["lines"][0]["line_no"] == 1 for row in rows)
        assert json.loads(rows[1][2])["after_product_quantity"] is None
        assert connection.scalar(sa.text("SELECT COUNT(*) FROM carton_audit_events")) == 2
