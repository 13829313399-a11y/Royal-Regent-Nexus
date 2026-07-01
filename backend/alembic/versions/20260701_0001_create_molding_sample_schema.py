"""create molding sample schema

Revision ID: 20260701_0001
Revises:
Create Date: 2026-07-01 21:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260701_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "molding_sample_orders",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("factory_id", sa.String(length=64), nullable=False),
        sa.Column("order_number", sa.String(length=128), nullable=False),
        sa.Column("doc_number", sa.String(length=128), nullable=False),
        sa.Column("product_name", sa.String(length=255), nullable=False),
        sa.Column("client_name", sa.String(length=255), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("order_type", sa.String(length=20), nullable=False),
        sa.Column("workshop", sa.String(length=64), nullable=False),
        sa.Column("send_to", sa.String(length=64), nullable=False),
        sa.Column("supervisor", sa.String(length=128), nullable=False),
        sa.Column("eng_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reject_reason", sa.Text(), nullable=False),
        sa.Column("completed_date", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_orders_factory_id", "molding_sample_orders", ["factory_id"])
    op.create_index("ix_molding_sample_orders_status", "molding_sample_orders", ["status"])

    op.create_table(
        "molding_sample_items",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("mold_id", sa.String(length=128), nullable=False),
        sa.Column("mold_name", sa.String(length=255), nullable=False),
        sa.Column("machine_type", sa.String(length=64), nullable=False),
        sa.Column("material", sa.String(length=255), nullable=False),
        sa.Column("color", sa.String(length=255), nullable=False),
        sa.Column("pigment_no", sa.String(length=128), nullable=False),
        sa.Column("quantity", sa.String(length=64), nullable=False),
        sa.Column("shoot_qty", sa.Integer(), nullable=False),
        sa.Column("gross_weight_g", sa.Float(), nullable=True),
        sa.Column("required_material_kg", sa.Float(), nullable=True),
        sa.Column("mold_return_time", sa.String(length=32), nullable=False),
        sa.Column("completion_time", sa.String(length=32), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("receipt_no", sa.String(length=128), nullable=False),
        sa.Column("collected_weight_kg", sa.Float(), nullable=True),
        sa.Column("actual_weight_kg", sa.Float(), nullable=True),
        sa.Column("actual_amount_hkd", sa.Float(), nullable=True),
        sa.Column("injection_cost", sa.Float(), nullable=True),
        sa.Column("injection_cost_hkd", sa.Float(), nullable=True),
        sa.Column("exchange_rate_at_save", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_items_order_id", "molding_sample_items", ["order_id"])

    op.create_table(
        "molding_sample_audit_logs",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("from_status", sa.String(length=32), nullable=False),
        sa.Column("to_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_audit_logs_order_id", "molding_sample_audit_logs", ["order_id"])

    op.create_table(
        "molding_sample_material_prices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("material", sa.String(length=255), nullable=False),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_molding_sample_material_prices_material",
        "molding_sample_material_prices",
        ["material"],
        unique=True,
    )

    op.create_table(
        "molding_sample_settings",
        sa.Column("key", sa.String(length=128), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )

    op.create_table(
        "molding_sample_auth_pins",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("pin_salt", sa.String(length=64), nullable=False),
        sa.Column("pin_hash", sa.String(length=128), nullable=False),
        sa.Column("must_change", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_auth_pins_name", "molding_sample_auth_pins", ["name"])
    op.create_index("ix_molding_sample_auth_pins_role", "molding_sample_auth_pins", ["role"])

    op.create_table(
        "molding_sample_pin_attempts",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_pin_attempts_name", "molding_sample_pin_attempts", ["name"])
    op.create_index("ix_molding_sample_pin_attempts_role", "molding_sample_pin_attempts", ["role"])

    op.create_table(
        "molding_sample_sensitive_audit_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_name", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_sensitive_audit_logs_action", "molding_sample_sensitive_audit_logs", ["action"])
    op.create_index(
        "ix_molding_sample_sensitive_audit_logs_target_name",
        "molding_sample_sensitive_audit_logs",
        ["target_name"],
    )
    op.create_index(
        "ix_molding_sample_sensitive_audit_logs_target_type",
        "molding_sample_sensitive_audit_logs",
        ["target_type"],
    )

    op.create_table(
        "molding_sample_requisitions",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("req_number", sa.String(length=32), nullable=False),
        sa.Column("date", sa.String(length=20), nullable=False),
        sa.Column("order_id", sa.String(length=64), nullable=False),
        sa.Column("order_number", sa.String(length=128), nullable=False),
        sa.Column("material", sa.String(length=255), nullable=False),
        sa.Column("requested_weight_kg", sa.Float(), nullable=False),
        sa.Column("applicant", sa.String(length=128), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("inventory_batch_id", sa.String(length=96), nullable=False),
        sa.Column("inventory_batch_no", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("issued_at", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["molding_sample_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_requisitions_date", "molding_sample_requisitions", ["date"])
    op.create_index("ix_molding_sample_requisitions_order_id", "molding_sample_requisitions", ["order_id"])
    op.create_index("ix_molding_sample_requisitions_req_number", "molding_sample_requisitions", ["req_number"], unique=True)
    op.create_index("ix_molding_sample_requisitions_status", "molding_sample_requisitions", ["status"])

    op.create_table(
        "molding_sample_inventory_batches",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("material", sa.String(length=255), nullable=False),
        sa.Column("batch_no", sa.String(length=128), nullable=False),
        sa.Column("location", sa.String(length=128), nullable=False),
        sa.Column("initial_weight_kg", sa.Float(), nullable=False),
        sa.Column("available_weight_kg", sa.Float(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.Column("updated_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_inventory_batches_batch_no", "molding_sample_inventory_batches", ["batch_no"])
    op.create_index("ix_molding_sample_inventory_batches_material", "molding_sample_inventory_batches", ["material"])

    op.create_table(
        "molding_sample_inventory_movements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("batch_id", sa.String(length=96), nullable=False),
        sa.Column("batch_no", sa.String(length=128), nullable=False),
        sa.Column("requisition_id", sa.String(length=96), nullable=False),
        sa.Column("req_number", sa.String(length=32), nullable=False),
        sa.Column("material", sa.String(length=255), nullable=False),
        sa.Column("movement_type", sa.String(length=64), nullable=False),
        sa.Column("quantity_kg", sa.Float(), nullable=False),
        sa.Column("before_weight_kg", sa.Float(), nullable=False),
        sa.Column("after_weight_kg", sa.Float(), nullable=False),
        sa.Column("actor_name", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_molding_sample_inventory_movements_batch_id", "molding_sample_inventory_movements", ["batch_id"])
    op.create_index("ix_molding_sample_inventory_movements_batch_no", "molding_sample_inventory_movements", ["batch_no"])
    op.create_index("ix_molding_sample_inventory_movements_material", "molding_sample_inventory_movements", ["material"])
    op.create_index("ix_molding_sample_inventory_movements_movement_type", "molding_sample_inventory_movements", ["movement_type"])
    op.create_index("ix_molding_sample_inventory_movements_req_number", "molding_sample_inventory_movements", ["req_number"])
    op.create_index("ix_molding_sample_inventory_movements_requisition_id", "molding_sample_inventory_movements", ["requisition_id"])


def downgrade() -> None:
    op.drop_index("ix_molding_sample_inventory_movements_requisition_id", table_name="molding_sample_inventory_movements")
    op.drop_index("ix_molding_sample_inventory_movements_req_number", table_name="molding_sample_inventory_movements")
    op.drop_index("ix_molding_sample_inventory_movements_movement_type", table_name="molding_sample_inventory_movements")
    op.drop_index("ix_molding_sample_inventory_movements_material", table_name="molding_sample_inventory_movements")
    op.drop_index("ix_molding_sample_inventory_movements_batch_no", table_name="molding_sample_inventory_movements")
    op.drop_index("ix_molding_sample_inventory_movements_batch_id", table_name="molding_sample_inventory_movements")
    op.drop_table("molding_sample_inventory_movements")

    op.drop_index("ix_molding_sample_inventory_batches_material", table_name="molding_sample_inventory_batches")
    op.drop_index("ix_molding_sample_inventory_batches_batch_no", table_name="molding_sample_inventory_batches")
    op.drop_table("molding_sample_inventory_batches")

    op.drop_index("ix_molding_sample_requisitions_status", table_name="molding_sample_requisitions")
    op.drop_index("ix_molding_sample_requisitions_req_number", table_name="molding_sample_requisitions")
    op.drop_index("ix_molding_sample_requisitions_order_id", table_name="molding_sample_requisitions")
    op.drop_index("ix_molding_sample_requisitions_date", table_name="molding_sample_requisitions")
    op.drop_table("molding_sample_requisitions")

    op.drop_index("ix_molding_sample_sensitive_audit_logs_target_type", table_name="molding_sample_sensitive_audit_logs")
    op.drop_index("ix_molding_sample_sensitive_audit_logs_target_name", table_name="molding_sample_sensitive_audit_logs")
    op.drop_index("ix_molding_sample_sensitive_audit_logs_action", table_name="molding_sample_sensitive_audit_logs")
    op.drop_table("molding_sample_sensitive_audit_logs")

    op.drop_index("ix_molding_sample_pin_attempts_role", table_name="molding_sample_pin_attempts")
    op.drop_index("ix_molding_sample_pin_attempts_name", table_name="molding_sample_pin_attempts")
    op.drop_table("molding_sample_pin_attempts")

    op.drop_index("ix_molding_sample_auth_pins_role", table_name="molding_sample_auth_pins")
    op.drop_index("ix_molding_sample_auth_pins_name", table_name="molding_sample_auth_pins")
    op.drop_table("molding_sample_auth_pins")

    op.drop_table("molding_sample_settings")

    op.drop_index("ix_molding_sample_material_prices_material", table_name="molding_sample_material_prices")
    op.drop_table("molding_sample_material_prices")

    op.drop_index("ix_molding_sample_audit_logs_order_id", table_name="molding_sample_audit_logs")
    op.drop_table("molding_sample_audit_logs")

    op.drop_index("ix_molding_sample_items_order_id", table_name="molding_sample_items")
    op.drop_table("molding_sample_items")

    op.drop_index("ix_molding_sample_orders_status", table_name="molding_sample_orders")
    op.drop_index("ix_molding_sample_orders_factory_id", table_name="molding_sample_orders")
    op.drop_table("molding_sample_orders")
