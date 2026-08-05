"""add plan-aware injection scheduling takeover contracts

Revision ID: 20260805_0054
Revises: 20260805_0053
Create Date: 2026-08-05
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic.util.exc import CommandError

from alembic import op

revision: str = "20260805_0054"
down_revision: str | Sequence[str] | None = "20260805_0053"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_columns() -> None:
    with op.batch_alter_table("injection_scheduling_plans") as batch_op:
        batch_op.add_column(
            sa.Column(
                "based_on_event_sequence",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(
            sa.Column(
                "based_on_report_watermark",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    task_columns = (
        sa.Column(
            "allocated_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "takeover_source_completed_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("origin", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("stable_order_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("stable_row_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_task_id", sa.String(96), nullable=True),
        sa.Column(
            "inherited_report_counter",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_at_clone",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "report_event_watermark",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("profile_id", sa.String(96), nullable=True),
        sa.Column("profile_revision", sa.Integer(), nullable=True),
    )
    with op.batch_alter_table("injection_scheduling_tasks") as batch_op:
        for column in task_columns:
            batch_op.add_column(column)
    for column in (
        "origin",
        "stable_order_key",
        "stable_row_key",
        "source_task_id",
        "profile_id",
    ):
        op.create_index(
            f"ix_injection_scheduling_tasks_{column}",
            "injection_scheduling_tasks",
            [column],
        )

    batch_columns = (
        sa.Column(
            "target_draft_plan_id", sa.String(96), nullable=False, server_default=""
        ),
        sa.Column(
            "target_draft_plan_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reference_published_plan_id",
            sa.String(96),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "reference_published_plan_revision",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "reference_published_event_sequence",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "order_task_revision_digest",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
        sa.Column(
            "action_fingerprint", sa.String(64), nullable=False, server_default=""
        ),
        sa.Column("rule_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "master_revision_digest",
            sa.String(64),
            nullable=False,
            server_default="",
        ),
    )
    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        for column in batch_columns:
            batch_op.add_column(column)
    for column in (
        "target_draft_plan_id",
        "reference_published_plan_id",
        "action_fingerprint",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_batches_{column}",
            "injection_scheduling_import_batches",
            [column],
        )


def _create_tables() -> None:
    op.create_table(
        "injection_scheduling_plan_order_states",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("stable_order_key", sa.String(64), nullable=False),
        sa.Column("order_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("delivery_start_date", sa.String(32), nullable=False, server_default=""),
        sa.Column("delivery_due_date", sa.String(32), nullable=False, server_default=""),
        sa.Column(
            "takeover_source_completed_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "report_increment_total",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "progress_adjustment_total",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "completed_quantity",
            sa.Numeric(14, 3),
            nullable=False,
            server_default="0",
        ),
        sa.Column("status", sa.String(32), nullable=False, server_default="BACKLOG"),
        sa.Column(
            "quantity_scope",
            sa.String(32),
            nullable=False,
            server_default="ORDER_CUMULATIVE",
        ),
        sa.Column("source_batch_id", sa.String(96), nullable=True),
        sa.Column("source_sheet_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("source_profile_id", sa.String(96), nullable=True),
        sa.Column("source_profile_revision", sa.Integer(), nullable=True),
        sa.Column("source_lineage_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False, server_default="system-migration"),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default="系统迁移"),
        sa.Column("updated_by", sa.String(64), nullable=False, server_default="system-migration"),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default="系统迁移"),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.Column("updated_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_plan_order_state_plan_factory",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            ["injection_scheduling_orders.id", "injection_scheduling_orders.factory_id"],
            name="fk_injection_scheduling_plan_order_state_order_factory",
        ),
        sa.UniqueConstraint(
            "plan_id", "order_id", name="uq_injection_scheduling_plan_order_state_plan_order"
        ),
        sa.UniqueConstraint(
            "plan_id",
            "stable_order_key",
            name="uq_injection_scheduling_plan_order_state_stable_key",
        ),
        sa.CheckConstraint(
            "order_quantity > 0 AND takeover_source_completed_quantity >= 0 "
            "AND report_increment_total >= 0 AND completed_quantity >= 0",
            name="ck_injection_scheduling_plan_order_state_quantities",
        ),
        sa.CheckConstraint(
            "status IN ('BACKLOG', 'SCHEDULED', 'COMPLETED', 'CANCELLED')",
            name="ck_injection_scheduling_plan_order_state_status",
        ),
        sa.CheckConstraint(
            "quantity_scope IN ('ORDER_CUMULATIVE', 'SPLIT_CUMULATIVE')",
            name="ck_injection_scheduling_plan_order_state_quantity_scope",
        ),
        sa.CheckConstraint("revision >= 1", name="ck_injection_scheduling_plan_order_state_revision"),
    )
    for columns in (("factory_id",), ("plan_id",), ("order_id",), ("stable_order_key",)):
        column = columns[0]
        op.create_index(
            f"ix_injection_scheduling_plan_order_states_{column}",
            "injection_scheduling_plan_order_states",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_plan_order_state_plan_status",
        "injection_scheduling_plan_order_states",
        ["plan_id", "status"],
    )

    op.create_table(
        "injection_scheduling_progress_adjustments",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("plan_id", sa.String(96), nullable=False),
        sa.Column("order_id", sa.String(96), nullable=False),
        sa.Column("task_id", sa.String(96), nullable=True),
        sa.Column("signed_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("before_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("after_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_batch_id", sa.String(96), nullable=True),
        sa.Column("source_sheet_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("adjusted_by", sa.String(64), nullable=False),
        sa.Column("adjusted_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["plan_id", "factory_id"],
            ["injection_scheduling_plans.id", "injection_scheduling_plans.factory_id"],
            name="fk_injection_scheduling_progress_adjustment_plan_factory",
        ),
        sa.ForeignKeyConstraint(
            ["order_id", "factory_id"],
            ["injection_scheduling_orders.id", "injection_scheduling_orders.factory_id"],
            name="fk_injection_scheduling_progress_adjustment_order_factory",
        ),
        sa.UniqueConstraint(
            "factory_id", "request_id", name="uq_injection_scheduling_progress_adjustment_request"
        ),
        sa.CheckConstraint(
            "signed_quantity <> 0",
            name="ck_injection_scheduling_progress_adjustment_nonzero",
        ),
        sa.CheckConstraint(
            "source_kind IN ('IMPORT_RECONCILIATION', 'MANUAL_CORRECTION', 'PUBLISH_REBASE')",
            name="ck_injection_scheduling_progress_adjustment_source_kind",
        ),
    )
    for column in ("factory_id", "plan_id", "order_id", "task_id", "source_batch_id", "request_id", "payload_hash"):
        op.create_index(
            f"ix_injection_scheduling_progress_adjustments_{column}",
            "injection_scheduling_progress_adjustments",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_progress_adjustment_plan_order_created",
        "injection_scheduling_progress_adjustments",
        ["plan_id", "order_id", "created_at"],
    )

    op.create_table(
        "injection_scheduling_import_actions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("action_type", sa.String(64), nullable=False),
        sa.Column("stable_order_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("stable_row_key", sa.String(64), nullable=False, server_default=""),
        sa.Column("source_sheet_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("source_row", sa.Integer(), nullable=True),
        sa.Column("target_order_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("target_task_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("requires_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("reason_code", sa.String(64), nullable=False, server_default=""),
        sa.Column("detail_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("action_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            ["injection_scheduling_import_batches.id", "injection_scheduling_import_batches.factory_id"],
            name="fk_injection_scheduling_import_action_batch_factory",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "batch_id", "action_sha256", name="uq_injection_scheduling_import_action_fingerprint"
        ),
    )
    for column in (
        "batch_id", "factory_id", "action_type", "stable_order_key", "stable_row_key",
        "source_row", "target_order_id", "target_task_id", "requires_publish", "action_sha256",
    ):
        op.create_index(
            f"ix_injection_scheduling_import_actions_{column}",
            "injection_scheduling_import_actions",
            [column],
        )
    op.create_index(
        "ix_injection_scheduling_import_action_batch_type_row",
        "injection_scheduling_import_actions",
        ["batch_id", "action_type", "source_row"],
    )

    op.create_table(
        "injection_scheduling_import_master_decisions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("business_key", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False, server_default="APPROVED"),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("decided_by", sa.String(64), nullable=False),
        sa.Column("decided_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(32), nullable=False),
        sa.ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            ["injection_scheduling_import_batches.id", "injection_scheduling_import_batches.factory_id"],
            name="fk_injection_scheduling_import_master_decision_batch_factory",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "batch_id", "entity_type", "business_key",
            name="uq_injection_scheduling_import_master_decision_key",
        ),
    )
    for column in ("batch_id", "factory_id", "entity_type", "business_key", "request_id", "decided_by"):
        op.create_index(
            f"ix_injection_scheduling_import_master_decisions_{column}",
            "injection_scheduling_import_master_decisions",
            [column],
        )


def _stable_key(row: sa.RowMapping) -> str:
    try:
        lineage = json.loads(row["lineage_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        lineage = {}
    existing = lineage.get("stable_order_key")
    if isinstance(existing, str) and existing:
        return existing
    payload = "|".join(
        str(row[key] or "")
        for key in ("factory_id", "order_no", "item_no", "mold_id", "product_name")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _backfill() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT DISTINCT p.id AS plan_id, p.factory_id, p.created_at,
                   o.id AS order_id, o.order_no, o.item_no, o.product_name,
                   o.mold_id, o.order_quantity, o.source_completed_quantity,
                   o.completed_quantity, o.delivery_start_date, o.delivery_due_date,
                   o.status, o.lineage_json
            FROM injection_scheduling_plans p
            JOIN injection_scheduling_tasks t
              ON t.plan_id = p.id AND t.factory_id = p.factory_id
            JOIN injection_scheduling_orders o
              ON o.id = t.order_id AND o.factory_id = t.factory_id
            ORDER BY p.id, o.id
            """
        )
    ).mappings()
    for index, row in enumerate(rows, start=1):
        report_total = connection.execute(
            sa.text(
                """
                SELECT COALESCE(SUM(r.normalized_increment_quantity), 0)
                FROM injection_scheduling_shift_reports r
                JOIN injection_scheduling_tasks t ON t.id = r.task_id
                WHERE t.plan_id = :plan_id AND r.order_id = :order_id
                """
            ),
            {"plan_id": row["plan_id"], "order_id": row["order_id"]},
        ).scalar_one()
        stable = _stable_key(row)
        takeover = row["source_completed_quantity"] or 0
        completed = takeover + report_total
        status = "COMPLETED" if completed >= row["order_quantity"] else row["status"]
        connection.execute(
            sa.text(
                """
                INSERT INTO injection_scheduling_plan_order_states (
                    id, factory_id, plan_id, order_id, stable_order_key,
                    order_quantity, delivery_start_date, delivery_due_date,
                    takeover_source_completed_quantity, report_increment_total,
                    progress_adjustment_total, completed_quantity, status,
                    quantity_scope, source_lineage_json, revision,
                    created_by, created_by_name, updated_by, updated_by_name,
                    created_at, updated_at
                ) VALUES (
                    :id, :factory_id, :plan_id, :order_id, :stable_order_key,
                    :order_quantity, :delivery_start_date, :delivery_due_date,
                    :takeover, :report_total, 0, :completed, :status,
                    'ORDER_CUMULATIVE', :lineage_json, 1,
                    'system-migration', '系统迁移', 'system-migration', '系统迁移',
                    :created_at, :created_at
                )
                """
            ),
            {
                "id": f"ispostate-migration-{index}",
                "factory_id": row["factory_id"],
                "plan_id": row["plan_id"],
                "order_id": row["order_id"],
                "stable_order_key": stable,
                "order_quantity": row["order_quantity"],
                "delivery_start_date": row["delivery_start_date"] or "",
                "delivery_due_date": row["delivery_due_date"] or "",
                "takeover": takeover,
                "report_total": report_total,
                "completed": completed,
                "status": status,
                "lineage_json": row["lineage_json"] or "{}",
                "created_at": row["created_at"],
            },
        )

    task_rows = connection.execute(
        sa.text(
            """
            SELECT t.id, t.plan_id, t.machine_id, t.source_sheet_name, t.source_row,
                   t.import_batch_id, o.factory_id, o.order_no, o.item_no,
                   o.product_name, o.mold_id, o.order_quantity,
                   o.source_completed_quantity, o.lineage_json,
                   COUNT(*) OVER (PARTITION BY t.plan_id, t.order_id) AS task_count
            FROM injection_scheduling_tasks t
            JOIN injection_scheduling_orders o
              ON o.id = t.order_id AND o.factory_id = t.factory_id
            """
        )
    ).mappings()
    for row in task_rows:
        stable_order = _stable_key(row)
        row_payload = "|".join(
            (
                stable_order,
                str(row["machine_id"] or ""),
                str(row["source_sheet_name"] or ""),
                str(row["source_row"] or ""),
            )
        )
        stable_row = hashlib.sha256(row_payload.encode("utf-8")).hexdigest()
        allocated = (
            max(row["order_quantity"] - row["source_completed_quantity"], 0)
            if row["task_count"] == 1
            else 0
        )
        connection.execute(
            sa.text(
                """
                UPDATE injection_scheduling_tasks
                SET allocated_quantity = :allocated,
                    takeover_source_completed_quantity = :takeover,
                    origin = :origin,
                    stable_order_key = :stable_order_key,
                    stable_row_key = :stable_row_key
                WHERE id = :task_id
                """
            ),
            {
                "allocated": allocated,
                "takeover": row["source_completed_quantity"] if row["task_count"] == 1 else 0,
                "origin": "excel_baseline" if row["import_batch_id"] else "manual",
                "stable_order_key": stable_order,
                "stable_row_key": stable_row,
                "task_id": row["id"],
            },
        )


def _create_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table_name in (
            "injection_scheduling_progress_adjustments",
            "injection_scheduling_import_actions",
            "injection_scheduling_import_master_decisions",
        ):
            short = table_name.removeprefix("injection_scheduling_")
            for operation in ("UPDATE", "DELETE"):
                op.execute(
                    sa.text(
                        f"""
                        CREATE TRIGGER trg_injection_scheduling_{short}_no_{operation.lower()}
                        BEFORE {operation} ON {table_name}
                        BEGIN
                            SELECT RAISE(ABORT, '{table_name} is append-only');
                        END
                        """
                    )
                )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_takeover_baseline_immutable
                BEFORE UPDATE ON injection_scheduling_plan_order_states
                WHEN NEW.takeover_source_completed_quantity IS NOT OLD.takeover_source_completed_quantity
                BEGIN
                    SELECT RAISE(ABORT, 'takeover baseline is immutable');
                END
                """
            )
        )
    elif dialect == "postgresql":
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION guard_injection_scheduling_phase2_append_only()
                RETURNS trigger AS $$
                BEGIN
                    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        for table_name in (
            "injection_scheduling_progress_adjustments",
            "injection_scheduling_import_actions",
            "injection_scheduling_import_master_decisions",
        ):
            short = table_name.removeprefix("injection_scheduling_")
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER trg_injection_scheduling_{short}_append_only
                    BEFORE UPDATE OR DELETE ON {table_name}
                    FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_phase2_append_only()
                    """
                )
            )
        op.execute(
            sa.text(
                """
                CREATE OR REPLACE FUNCTION guard_injection_scheduling_takeover_baseline()
                RETURNS trigger AS $$
                BEGIN
                    IF NEW.takeover_source_completed_quantity IS DISTINCT FROM
                       OLD.takeover_source_completed_quantity THEN
                        RAISE EXCEPTION 'takeover baseline is immutable';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
                """
            )
        )
        op.execute(
            sa.text(
                """
                CREATE TRIGGER trg_injection_scheduling_takeover_baseline_immutable
                BEFORE UPDATE ON injection_scheduling_plan_order_states
                FOR EACH ROW EXECUTE FUNCTION guard_injection_scheduling_takeover_baseline()
                """
            )
        )


def upgrade() -> None:
    _add_columns()
    _create_tables()
    _backfill()
    _create_guards()


def _drop_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table_name in (
            "progress_adjustments",
            "import_actions",
            "import_master_decisions",
        ):
            for operation in ("update", "delete"):
                op.execute(
                    sa.text(
                        f"DROP TRIGGER IF EXISTS trg_injection_scheduling_{table_name}_no_{operation}"
                    )
                )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_injection_scheduling_takeover_baseline_immutable"
            )
        )
    elif dialect == "postgresql":
        for table_name in (
            "progress_adjustments",
            "import_actions",
            "import_master_decisions",
        ):
            op.execute(
                sa.text(
                    f"DROP TRIGGER IF EXISTS trg_injection_scheduling_{table_name}_append_only "
                    f"ON injection_scheduling_{table_name}"
                )
            )
        op.execute(
            sa.text(
                "DROP TRIGGER IF EXISTS trg_injection_scheduling_takeover_baseline_immutable "
                "ON injection_scheduling_plan_order_states"
            )
        )
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_injection_scheduling_phase2_append_only()"))
        op.execute(sa.text("DROP FUNCTION IF EXISTS guard_injection_scheduling_takeover_baseline()"))


def downgrade() -> None:
    connection = op.get_bind()
    migration_context = op.get_context()
    destination_revision = str(
        migration_context.opts.get("destination_rev") or ""
    )
    destination_script = None
    if migration_context.script is not None and destination_revision:
        try:
            destination_script = migration_context.script.get_revision(
                destination_revision
            )
        except CommandError:  # pragma: no cover - defensive for relative CLI targets
            destination_script = None
    stops_at_profile_revision = (
        destination_script is not None
        and destination_script.revision == down_revision
    )
    if not stops_at_profile_revision:
        profile_state = connection.execute(
            sa.text(
                """
                SELECT
                    (SELECT COUNT(*) FROM injection_scheduling_import_profiles
                     WHERE id NOT IN (
                         'isprofile-huaxing-daily-v1',
                         'isprofile-huakang-b-daily-v1'
                     )) AS custom_profiles,
                    (SELECT COUNT(*) FROM injection_scheduling_import_profiles
                     WHERE lifecycle_revision != 1 OR status != 'ACTIVE') AS changed_profiles,
                    (SELECT COUNT(*)
                     FROM injection_scheduling_import_profile_factories) AS binding_count,
                    (SELECT COUNT(*) FROM injection_scheduling_import_batches
                     WHERE profile_id IS NOT NULL) AS referenced_batches
                """
            )
        ).mappings().one()
        if (
            profile_state["custom_profiles"]
            or profile_state["changed_profiles"]
            or profile_state["binding_count"] != 2
            or profile_state["referenced_batches"]
        ):
            raise RuntimeError(
                "20260805_0054 cannot be downgraded past 20260805_0053 after "
                "Profile lifecycle, binding, custom revision, or referenced ImportBatch "
                "data exists; restore a verified pre-0053 backup instead."
            )
    populated = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT COUNT(*) FROM injection_scheduling_progress_adjustments) AS adjustments,
                (SELECT COUNT(*) FROM injection_scheduling_import_actions) AS actions,
                (SELECT COUNT(*) FROM injection_scheduling_import_master_decisions) AS decisions,
                (SELECT COUNT(*) FROM injection_scheduling_plan_order_states
                 WHERE source_batch_id IS NOT NULL OR revision > 1) AS takeover_states,
                (SELECT COUNT(*) FROM injection_scheduling_tasks
                 WHERE source_task_id IS NOT NULL OR profile_id IS NOT NULL
                    OR origin IN ('excel_baseline', 'successor_clone')) AS lineage_tasks
            """
        )
    ).mappings().one()
    if any(populated.values()):
        raise RuntimeError(
            "20260805_0054 cannot be downgraded after takeover, reconciliation, "
            "progress, or successor lineage data exists; restore a verified pre-0054 backup instead."
        )
    _drop_guards()
    op.drop_table("injection_scheduling_import_master_decisions")
    op.drop_table("injection_scheduling_import_actions")
    op.drop_table("injection_scheduling_progress_adjustments")
    op.drop_table("injection_scheduling_plan_order_states")
    for column in (
        "action_fingerprint",
        "reference_published_plan_id",
        "target_draft_plan_id",
    ):
        op.drop_index(
            f"ix_injection_scheduling_import_batches_{column}",
            table_name="injection_scheduling_import_batches",
        )
    with op.batch_alter_table("injection_scheduling_import_batches") as batch_op:
        for column in (
            "master_revision_digest",
            "rule_revision",
            "action_fingerprint",
            "order_task_revision_digest",
            "reference_published_event_sequence",
            "reference_published_plan_revision",
            "reference_published_plan_id",
            "target_draft_plan_revision",
            "target_draft_plan_id",
        ):
            batch_op.drop_column(column)
    for column in (
        "profile_id",
        "source_task_id",
        "stable_row_key",
        "stable_order_key",
        "origin",
    ):
        op.drop_index(
            f"ix_injection_scheduling_tasks_{column}",
            table_name="injection_scheduling_tasks",
        )
    with op.batch_alter_table("injection_scheduling_tasks") as batch_op:
        for column in (
            "profile_revision",
            "profile_id",
            "report_event_watermark",
            "completed_at_clone",
            "inherited_report_counter",
            "source_task_id",
            "stable_row_key",
            "stable_order_key",
            "origin",
            "takeover_source_completed_quantity",
            "allocated_quantity",
        ):
            batch_op.drop_column(column)
    with op.batch_alter_table("injection_scheduling_plans") as batch_op:
        batch_op.drop_column("based_on_report_watermark")
        batch_op.drop_column("based_on_event_sequence")
