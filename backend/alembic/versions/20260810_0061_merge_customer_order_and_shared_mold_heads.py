"""reconcile the customer-order migration for existing shared-mold databases

Revision ID: 20260810_0061
Revises: 20260809_0060
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260810_0061"
down_revision: str | Sequence[str] | None = "20260809_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Backfill the reparented customer-order migration on already-upgraded local DBs."""
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = {
        column["name"]
        for column in inspector.get_columns("customer_order_export_audits")
    }
    check_constraints = {
        constraint.get("name")
        for constraint in inspector.get_check_constraints("customer_order_export_audits")
    }

    with op.batch_alter_table("customer_order_export_audits") as batch_op:
        if "manual_overrides_json" not in columns:
            batch_op.add_column(
                sa.Column(
                    "manual_overrides_json",
                    sa.Text(),
                    nullable=False,
                    server_default="[]",
                )
            )
        if "manual_override_count" not in columns:
            batch_op.add_column(
                sa.Column(
                    "manual_override_count",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                )
            )
        if "ck_customer_order_export_audit_manual_override_count" not in check_constraints:
            batch_op.create_check_constraint(
                "ck_customer_order_export_audit_manual_override_count",
                "manual_override_count >= 0",
            )


def downgrade() -> None:
    """Preflight protected evidence before earlier migrations remove any schema."""
    connection = op.get_bind()
    public_planning_state = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT COUNT(*) FROM injection_scheduling_upload_artifacts) AS artifacts,
                (SELECT COUNT(*) FROM injection_scheduling_export_audits) AS exports,
                (SELECT COUNT(*) FROM injection_scheduling_import_batches
                 WHERE preview_generation != 1) AS retried_batches,
                (SELECT COUNT(*) FROM injection_scheduling_plans
                 WHERE export_binding_source != 'LEGACY_UNKNOWN'
                    OR export_profile_id IS NOT NULL
                    OR calculation_version != '') AS bound_plans
            """
        )
    ).mappings().one()
    if any(public_planning_state.values()):
        raise RuntimeError(
            "20260807_0058 cannot be downgraded after upload artifacts, exports, "
            "plan bindings, or re-identified import generations exist; restore a "
            "verified pre-0058 backup."
        )

    rollout_state = connection.execute(
        sa.text(
            """
            SELECT
                (SELECT COUNT(*) FROM injection_scheduling_run_assignments
                 WHERE physical_mold_asset_id IS NOT NULL) AS assigned,
                (SELECT COUNT(*) FROM injection_scheduling_rollout_policies
                 WHERE revision <> 1 OR demand_mode <> 'MANUAL_CONFIRM'
                    OR master_data_mode <> 'PROPOSAL_ONLY'
                    OR business_contract_status <> 'UNSIGNED'
                    OR price_activation_enabled <> false
                    OR tentative_hold_ttl_minutes <> 30) AS changed_policies
            """
        )
    ).mappings().one()
    if any(rollout_state.values()):
        raise RuntimeError(
            "0060 已产生排程资产预占或 rollout policy 变更，拒绝丢失数据的降级"
        )

    override_count = connection.execute(
        sa.text(
            "SELECT COUNT(*) FROM customer_order_export_audits "
            "WHERE manual_override_count > 0"
        )
    ).scalar_one()
    if override_count:
        raise RuntimeError(
            "20260807_0059 cannot be downgraded after manual customer-order overrides exist; "
            "back up the audit evidence first"
        )
