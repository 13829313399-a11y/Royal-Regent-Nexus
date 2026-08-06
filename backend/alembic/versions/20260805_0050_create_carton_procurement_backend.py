"""create carton procurement order, receipt, inventory and closing backend

Revision ID: 20260805_0050
Revises: 20260804_0049
Create Date: 2026-08-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260805_0050"
down_revision: str | Sequence[str] | None = "20260804_0049"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSION_CODES = (
    "carton_procurement:read",
    "carton_procurement:order_write",
    "carton_procurement:receipt_write",
    "carton_procurement:inventory_write",
    "carton_procurement:closing_manage",
    "carton_procurement:import",
)
FULL_ACCESS_ROLES = (
    "admin",
    "manager",
    "warehouse_keeper",
    "carton_warehouse_keeper",
    "position_general_manager",
    "position_warehouse_manager",
    "position_warehouse_supervisor",
    "position_warehouse_keeper",
    "position_carton_manager",
    "position_carton_supervisor",
    "position_carton_warehouse_keeper",
)


def _seed_permissions() -> None:
    connection = op.get_bind()
    for code in PERMISSION_CODES:
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text(
                """
                INSERT INTO auth_permissions (id, code, name, description)
                SELECT
                    CAST(:id AS VARCHAR(96)),
                    CAST(:code AS VARCHAR(128)),
                    CAST(:name AS VARCHAR(128)),
                    CAST(:description AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM auth_permissions
                    WHERE code = CAST(:code AS VARCHAR(128))
                )
                """
            ),
            {"id": permission_id, "code": code, "name": code, "description": ""},
        )
        for role_id in FULL_ACCESS_ROLES:
            link_id = f"{role_id}:{permission_id}"
            connection.execute(
                sa.text(
                    """
                    INSERT INTO auth_role_permissions (id, role_id, permission_id)
                    SELECT
                        CAST(:id AS VARCHAR(128)),
                        CAST(:role_id AS VARCHAR(96)),
                        CAST(:permission_id AS VARCHAR(96))
                    WHERE EXISTS (
                        SELECT 1 FROM auth_roles
                        WHERE id = CAST(:role_id AS VARCHAR(96))
                    )
                    AND NOT EXISTS (
                        SELECT 1 FROM auth_role_permissions
                        WHERE role_id = CAST(:role_id AS VARCHAR(96))
                          AND permission_id = CAST(:permission_id AS VARCHAR(96))
                    )
                    """
                ),
                {"id": link_id, "role_id": role_id, "permission_id": permission_id},
            )


def upgrade() -> None:
    op.create_table(
        "carton_suppliers",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("supplier_code", sa.String(64), nullable=False),
        sa.Column("supplier_name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "supplier_code", name="uq_carton_supplier_factory_code"),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_supplier_id_factory"),
    )
    op.create_index("ix_carton_suppliers_factory_id", "carton_suppliers", ["factory_id"])
    op.create_index("ix_carton_suppliers_supplier_code", "carton_suppliers", ["supplier_code"])
    op.create_index("ix_carton_suppliers_status", "carton_suppliers", ["status"])

    op.create_table(
        "carton_orders",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("order_no", sa.String(64), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("supplier_name_snapshot", sa.String(255), nullable=False),
        sa.Column("contract_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("product_order_quantity", sa.Numeric(18, 6), nullable=False),
        sa.Column("order_date", sa.String(10), nullable=False),
        sa.Column("due_date", sa.String(10), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "order_no", name="uq_carton_order_factory_no"),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_order_id_factory"),
        sa.CheckConstraint("product_order_quantity > 0", name="ck_carton_order_product_quantity"),
        sa.CheckConstraint("revision >= 1", name="ck_carton_order_revision"),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'PENDING_SUPPLIER', 'CONFIRMED', "
            "'PARTIALLY_RECEIVED', 'COMPLETED', 'CANCELLED')",
            name="ck_carton_order_status",
        ),
    )
    for column in ("factory_id", "order_no", "customer_code", "customer_name", "supplier_id", "contract_no", "item_no", "order_date", "due_date", "status", "created_by", "updated_by", "created_at", "updated_at"):
        op.create_index(f"ix_carton_orders_{column}", "carton_orders", [column])
    op.create_index("ix_carton_order_factory_customer_due", "carton_orders", ["factory_id", "customer_code", "due_date"])
    op.create_index("ix_carton_order_factory_contract_item", "carton_orders", ["factory_id", "contract_no", "item_no"])

    op.create_table(
        "carton_order_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("contract_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False),
        sa.Column("packaging_type", sa.String(64), nullable=False),
        sa.Column("paper_quality", sa.String(128), nullable=False),
        sa.Column("specification", sa.String(255), nullable=False),
        sa.Column("dimension_unit", sa.String(16), nullable=False, server_default=""),
        sa.Column("usage_quantity", sa.Numeric(18, 8), nullable=False),
        sa.Column("required_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("price_source", sa.String(128), nullable=False, server_default="manual"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_order_line_id_factory"),
        sa.UniqueConstraint("order_id", "line_no", name="uq_carton_order_line_order_no"),
        sa.ForeignKeyConstraint(["order_id", "factory_id"], ["carton_orders.id", "carton_orders.factory_id"], name="fk_carton_order_line_order_factory", ondelete="CASCADE"),
        sa.CheckConstraint("line_no >= 1", name="ck_carton_order_line_no"),
        sa.CheckConstraint("usage_quantity > 0", name="ck_carton_order_line_usage"),
        sa.CheckConstraint("required_quantity > 0", name="ck_carton_order_line_required"),
        sa.CheckConstraint("unit_price >= 0", name="ck_carton_order_line_unit_price"),
    )
    for column in ("factory_id", "order_id", "customer_code", "contract_no", "item_no", "packaging_type", "paper_quality", "specification"):
        op.create_index(f"ix_carton_order_lines_{column}", "carton_order_lines", [column])
    op.create_index("ix_carton_order_line_factory_item", "carton_order_lines", ["factory_id", "item_no"])
    op.create_index("ix_carton_order_line_inventory_key", "carton_order_lines", ["factory_id", "customer_code", "packaging_type", "paper_quality", "specification"])

    op.create_table(
        "carton_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("import_type", sa.String(32), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="REQUIRES_REVIEW"),
        sa.Column("parse_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("imported_by", sa.String(64), nullable=False),
        sa.Column("imported_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "import_type", "source_sha256", name="uq_carton_import_factory_type_hash"),
        sa.CheckConstraint("import_type IN ('DELIVERY_NOTE', 'WEEKLY_SCHEDULE')", name="ck_carton_import_type"),
        sa.CheckConstraint("status IN ('REQUIRES_REVIEW', 'CONFIRMED', 'REJECTED')", name="ck_carton_import_status"),
    )
    for column in ("factory_id", "import_type", "source_sha256", "status", "imported_by", "created_at"):
        op.create_index(f"ix_carton_import_batches_{column}", "carton_import_batches", [column])

    op.create_table(
        "carton_receipts",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("receipt_no", sa.String(64), nullable=False),
        sa.Column("delivery_note_no", sa.String(128), nullable=False),
        sa.Column("delivery_date", sa.String(10), nullable=False),
        sa.Column("supplier_id", sa.String(96), nullable=False),
        sa.Column("supplier_name_snapshot", sa.String(255), nullable=False),
        sa.Column("import_batch_id", sa.String(96), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.Column("confirmed_at", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_receipt_id_factory"),
        sa.UniqueConstraint("factory_id", "supplier_id", "delivery_note_no", name="uq_carton_receipt_delivery_note"),
        sa.CheckConstraint("status IN ('DRAFT', 'PENDING_CONFIRMATION', 'POSTED', 'REVERSED')", name="ck_carton_receipt_status"),
        sa.CheckConstraint("revision >= 1", name="ck_carton_receipt_revision"),
    )
    for column in ("factory_id", "receipt_no", "delivery_note_no", "delivery_date", "supplier_id", "import_batch_id", "status", "created_by", "confirmed_by", "created_at", "updated_at", "confirmed_at"):
        op.create_index(f"ix_carton_receipts_{column}", "carton_receipts", [column])
    op.create_index("ix_carton_receipt_factory_delivery_date", "carton_receipts", ["factory_id", "delivery_date"])

    op.create_table(
        "carton_receipt_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("receipt_id", sa.String(96), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("order_line_id", sa.String(96), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("contract_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False),
        sa.Column("packaging_type", sa.String(64), nullable=False),
        sa.Column("paper_quality", sa.String(128), nullable=False),
        sa.Column("specification", sa.String(255), nullable=False),
        sa.Column("delivered_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("received_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("damaged_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("rejected_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("unusable_quantity", sa.Numeric(18, 4), nullable=False, server_default="0"),
        sa.Column("effective_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("location", sa.String(128), nullable=False, server_default=""),
        sa.Column("feedback_note", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_receipt_line_id_factory"),
        sa.UniqueConstraint("receipt_id", "line_no", name="uq_carton_receipt_line_receipt_no"),
        sa.ForeignKeyConstraint(["receipt_id", "factory_id"], ["carton_receipts.id", "carton_receipts.factory_id"], name="fk_carton_receipt_line_receipt_factory", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_line_id", "factory_id"], ["carton_order_lines.id", "carton_order_lines.factory_id"], name="fk_carton_receipt_line_order_line_factory"),
        sa.CheckConstraint("line_no >= 1", name="ck_carton_receipt_line_no"),
        sa.CheckConstraint("delivered_quantity >= 0 AND received_quantity >= 0 AND damaged_quantity >= 0 AND rejected_quantity >= 0 AND unusable_quantity >= 0", name="ck_carton_receipt_line_quantities"),
        sa.CheckConstraint("effective_quantity >= 0", name="ck_carton_receipt_line_effective"),
        sa.CheckConstraint("unit_price >= 0", name="ck_carton_receipt_line_price"),
    )
    for column in ("factory_id", "receipt_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification"):
        op.create_index(f"ix_carton_receipt_lines_{column}", "carton_receipt_lines", [column])

    op.create_table(
        "carton_inventory_movements",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("order_line_id", sa.String(96), nullable=True),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("contract_no", sa.String(128), nullable=False),
        sa.Column("item_no", sa.String(128), nullable=False),
        sa.Column("packaging_type", sa.String(64), nullable=False),
        sa.Column("paper_quality", sa.String(128), nullable=False),
        sa.Column("specification", sa.String(255), nullable=False),
        sa.Column("movement_type", sa.String(32), nullable=False),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False, server_default="0"),
        sa.Column("currency", sa.String(8), nullable=False, server_default="CNY"),
        sa.Column("location", sa.String(128), nullable=False, server_default=""),
        sa.Column("document_no", sa.String(128), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(96), nullable=False),
        sa.Column("source_line_id", sa.String(96), nullable=False),
        sa.Column("reversal_of_movement_id", sa.String(96), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_carton_movement_id_factory"),
        sa.UniqueConstraint("factory_id", "source_type", "source_line_id", name="uq_carton_movement_source_line"),
        sa.CheckConstraint("movement_type IN ('INBOUND', 'OUTBOUND', 'ADJUSTMENT', 'REVERSAL')", name="ck_carton_movement_type"),
        sa.CheckConstraint("quantity <> 0", name="ck_carton_movement_quantity"),
        sa.CheckConstraint("unit_price >= 0", name="ck_carton_movement_price"),
    )
    for column in ("factory_id", "order_line_id", "customer_code", "customer_name", "contract_no", "item_no", "packaging_type", "paper_quality", "specification", "movement_type", "document_no", "source_type", "source_id", "source_line_id", "reversal_of_movement_id", "actor_user_id", "occurred_at"):
        op.create_index(f"ix_carton_inventory_movements_{column}", "carton_inventory_movements", [column])
    op.create_index("uq_carton_movement_one_reversal", "carton_inventory_movements", ["reversal_of_movement_id"], unique=True, sqlite_where=sa.text("reversal_of_movement_id IS NOT NULL"), postgresql_where=sa.text("reversal_of_movement_id IS NOT NULL"))
    op.create_index("ix_carton_movement_inventory_key_time", "carton_inventory_movements", ["factory_id", "customer_code", "item_no", "packaging_type", "occurred_at"])

    op.create_table(
        "carton_closings",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("period", sa.String(7), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("opening_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("inbound_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("outbound_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("adjustment_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("ending_quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("ending_amount", sa.Numeric(18, 4), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("generated_by", sa.String(64), nullable=False),
        sa.Column("generated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("generated_at", sa.String(40), nullable=False),
        sa.Column("confirmed_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("confirmed_at", sa.String(40), nullable=False, server_default=""),
        sa.Column("locked_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("locked_at", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("factory_id", "period", "customer_code", name="uq_carton_closing_factory_period_customer"),
        sa.CheckConstraint("status IN ('DRAFT', 'PENDING', 'CONFIRMED', 'LOCKED')", name="ck_carton_closing_status"),
        sa.CheckConstraint("revision >= 1", name="ck_carton_closing_revision"),
    )
    for column in ("factory_id", "period", "customer_code", "status", "generated_by", "generated_at"):
        op.create_index(f"ix_carton_closings_{column}", "carton_closings", [column])
    op.create_index("ix_carton_closing_factory_period_status", "carton_closings", ["factory_id", "period", "status"])

    op.create_table(
        "carton_audit_events",
        sa.Column("sequence", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("id", sa.String(96), nullable=False, unique=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    for column in ("factory_id", "event_type", "entity_type", "entity_id", "actor_user_id", "created_at"):
        op.create_index(f"ix_carton_audit_events_{column}", "carton_audit_events", [column])
    op.create_index("ix_carton_audit_factory_sequence", "carton_audit_events", ["factory_id", "sequence"])
    op.create_index("ix_carton_audit_entity", "carton_audit_events", ["factory_id", "entity_type", "entity_id"])

    _seed_permissions()


def downgrade() -> None:
    connection = op.get_bind()
    protected_tables = (
        "carton_orders",
        "carton_receipts",
        "carton_inventory_movements",
        "carton_closings",
        "carton_import_batches",
        "carton_audit_events",
    )
    populated = [
        table_name
        for table_name in protected_tables
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "20260805_0050 cannot be downgraded after carton procurement data exists; "
            "back up and archive the carton ledger first: " + ",".join(populated)
        )
    for table_name in (
        "carton_audit_events",
        "carton_closings",
        "carton_inventory_movements",
        "carton_receipt_lines",
        "carton_receipts",
        "carton_import_batches",
        "carton_order_lines",
        "carton_orders",
        "carton_suppliers",
    ):
        op.drop_table(table_name)
    for code in PERMISSION_CODES:
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text("DELETE FROM auth_role_permissions WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM auth_permission_metadata WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM auth_permissions WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )
