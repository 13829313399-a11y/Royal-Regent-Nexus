"""add injection scheduling V2 phase 5 integrations and analytics

Revision ID: 20260804_0052
Revises: 20260804_0051
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260804_0052"
down_revision: str | Sequence[str] | None = "20260804_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "injection_scheduling_integration_cursors",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_key", sa.String(96), nullable=False),
        sa.Column("cursor_value", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("last_received_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("last_success_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("last_error", sa.Text(), nullable=False, server_default=""),
        sa.Column("event_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "source_type",
            "source_key",
            name="uq_injection_scheduling_integration_cursor_source",
        ),
        sa.CheckConstraint(
            "source_type IN ('ERP', 'DEVICE')",
            name="ck_injection_scheduling_integration_cursor_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'ERROR', 'NOT_CONFIGURED')",
            name="ck_injection_scheduling_integration_cursor_status",
        ),
        sa.CheckConstraint(
            "event_count >= 0 AND revision >= 1",
            name="ck_injection_scheduling_integration_cursor_counts",
        ),
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_factory_id",
        "injection_scheduling_integration_cursors",
        ["factory_id"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_source_type",
        "injection_scheduling_integration_cursors",
        ["source_type"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_source_key",
        "injection_scheduling_integration_cursors",
        ["source_key"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_status",
        "injection_scheduling_integration_cursors",
        ["status"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_updated_by",
        "injection_scheduling_integration_cursors",
        ["updated_by"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursors_updated_at",
        "injection_scheduling_integration_cursors",
        ["updated_at"],
    )
    op.create_index(
        "ix_injection_scheduling_integration_cursor_factory_type",
        "injection_scheduling_integration_cursors",
        ["factory_id", "source_type"],
    )

    op.create_table(
        "injection_scheduling_external_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_key", sa.String(96), nullable=False),
        sa.Column("external_event_id", sa.String(128), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("occurred_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="APPLIED"),
        sa.Column(
            "linked_entity_type", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("linked_entity_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("received_by", sa.String(64), nullable=False, server_default=""),
        sa.Column(
            "received_by_name", sa.String(128), nullable=False, server_default=""
        ),
        sa.Column("received_at", sa.String(32), nullable=False),
        sa.Column("applied_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("error_detail", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint(
            "factory_id",
            "source_type",
            "source_key",
            "external_event_id",
            name="uq_injection_scheduling_external_event_source_id",
        ),
        sa.CheckConstraint(
            "source_type IN ('ERP', 'DEVICE')",
            name="ck_injection_scheduling_external_event_source_type",
        ),
        sa.CheckConstraint(
            "status IN ('APPLIED', 'IGNORED', 'FAILED')",
            name="ck_injection_scheduling_external_event_status",
        ),
    )
    for column in (
        "factory_id",
        "source_type",
        "source_key",
        "external_event_id",
        "event_type",
        "occurred_at",
        "payload_hash",
        "status",
        "linked_entity_id",
        "request_id",
        "received_by",
        "received_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_external_events_{column}",
            "injection_scheduling_external_events",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_external_event_factory_received",
        "injection_scheduling_external_events",
        ["factory_id", "received_at"],
    )
    op.create_index(
        "ix_injection_scheduling_external_event_linked_entity",
        "injection_scheduling_external_events",
        ["factory_id", "linked_entity_type", "linked_entity_id"],
    )

    op.create_table(
        "injection_scheduling_cycle_observations",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("external_event_id", sa.String(96), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("machine_id", sa.String(96), nullable=False),
        sa.Column("mold_id", sa.String(96), nullable=False),
        sa.Column("observed_at", sa.String(32), nullable=False),
        sa.Column("cycle_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "units_per_cycle", sa.Numeric(12, 3), nullable=False, server_default="1"
        ),
        sa.Column(
            "produced_quantity", sa.Numeric(14, 3), nullable=False, server_default="0"
        ),
        sa.Column(
            "runtime_minutes", sa.Numeric(14, 3), nullable=False, server_default="0"
        ),
        sa.Column("source_key", sa.String(96), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "external_event_id",
            name="uq_injection_scheduling_cycle_observation_event",
        ),
        sa.ForeignKeyConstraint(
            ["task_id", "factory_id"],
            ["injection_scheduling_tasks.id", "injection_scheduling_tasks.factory_id"],
            name="fk_injection_scheduling_cycle_observation_task_factory",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            [
                "injection_scheduling_orders.id",
                "injection_scheduling_orders.factory_id",
            ],
            name="fk_injection_scheduling_cycle_observation_order_factory",
        ),
        sa.ForeignKeyConstraint(
            ["machine_id", "factory_id"],
            [
                "injection_scheduling_machines.id",
                "injection_scheduling_machines.factory_id",
            ],
            name="fk_injection_scheduling_cycle_observation_machine_factory",
        ),
        sa.ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_cycle_observation_mold_factory",
        ),
        sa.CheckConstraint(
            "cycle_seconds > 0 AND units_per_cycle > 0",
            name="ck_injection_scheduling_cycle_observation_cycle",
        ),
        sa.CheckConstraint(
            "produced_quantity >= 0 AND runtime_minutes >= 0",
            name="ck_injection_scheduling_cycle_observation_quantities",
        ),
    )
    for column in (
        "factory_id",
        "external_event_id",
        "task_id",
        "order_id",
        "machine_id",
        "mold_id",
        "observed_at",
        "source_key",
        "created_at",
    ):
        op.create_index(
            f"ix_injection_scheduling_cycle_observations_{column}",
            "injection_scheduling_cycle_observations",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_cycle_observation_factory_mold_time",
        "injection_scheduling_cycle_observations",
        ["factory_id", "mold_id", "observed_at"],
    )
    op.create_index(
        "ix_injection_scheduling_cycle_observation_factory_machine_time",
        "injection_scheduling_cycle_observations",
        ["factory_id", "machine_id", "observed_at"],
    )

    op.create_table(
        "injection_scheduling_speed_models",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("mold_id", sa.String(96), nullable=False),
        sa.Column("sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calibrated_cycle_seconds", sa.Numeric(12, 3), nullable=False),
        sa.Column(
            "units_per_cycle", sa.Numeric(12, 3), nullable=False, server_default="1"
        ),
        sa.Column("calibrated_units_per_hour", sa.Numeric(14, 3), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5), nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="INSUFFICIENT_DATA"
        ),
        sa.Column(
            "source_window_start", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column(
            "source_window_end", sa.String(32), nullable=False, server_default=""
        ),
        sa.Column("last_observed_at", sa.String(32), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default=""),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.UniqueConstraint(
            "factory_id",
            "mold_id",
            name="uq_injection_scheduling_speed_model_factory_mold",
        ),
        sa.ForeignKeyConstraint(
            ["mold_id", "factory_id"],
            ["injection_scheduling_molds.id", "injection_scheduling_molds.factory_id"],
            name="fk_injection_scheduling_speed_model_mold_factory",
        ),
        sa.CheckConstraint(
            "sample_count >= 0 AND revision >= 1",
            name="ck_injection_scheduling_speed_model_counts",
        ),
        sa.CheckConstraint(
            "calibrated_cycle_seconds > 0 AND units_per_cycle > 0 AND calibrated_units_per_hour > 0",
            name="ck_injection_scheduling_speed_model_values",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_injection_scheduling_speed_model_confidence",
        ),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'INSUFFICIENT_DATA')",
            name="ck_injection_scheduling_speed_model_status",
        ),
    )
    for column in ("factory_id", "mold_id", "updated_by", "updated_at"):
        op.create_index(
            f"ix_injection_scheduling_speed_models_{column}",
            "injection_scheduling_speed_models",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_speed_model_factory_status",
        "injection_scheduling_speed_models",
        ["factory_id", "status"],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in (
        "injection_scheduling_external_events",
        "injection_scheduling_cycle_observations",
        "injection_scheduling_speed_models",
        "injection_scheduling_integration_cursors",
    ):
        if connection.execute(
            sa.text(f"SELECT COUNT(*) FROM {table_name}")
        ).scalar_one():
            raise RuntimeError(
                "Phase 5 integration history exists; restore a verified pre-0052 backup instead of downgrading."
            )
    op.drop_table("injection_scheduling_speed_models")
    op.drop_table("injection_scheduling_cycle_observations")
    op.drop_table("injection_scheduling_external_events")
    op.drop_table("injection_scheduling_integration_cursors")
