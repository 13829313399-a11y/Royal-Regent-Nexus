"""generalize the existing AI confirmation into the sole Action Gateway

Revision ID: 20260813_0074
Revises: 20260813_0073
Create Date: 2026-08-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260813_0074"
down_revision: str | Sequence[str] | None = "20260813_0073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_NEW_COLUMNS = (
    "gateway_contract_version",
    "action_type",
    "handler_version",
    "approval_policy_version",
    "lifecycle_status",
    "waiting_approval_at",
    "approval_user_id",
    "approval_request_id",
    "approval_args_hash",
    "approval_entity_revision",
    "approval_expires_at",
    "rejected_at",
    "rejection_reason",
    "commit_started_at",
    "verification_started_at",
    "verified_at",
    "execution_user_id",
    "domain_audit_id",
    "verification_result_json",
    "compensation_json",
)
_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "%(constraint_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "ai_action_confirmations",
        recreate="auto",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(
            sa.Column(
                "gateway_contract_version",
                sa.String(32),
                nullable=False,
                server_default="legacy-confirmation-v1",
            )
        )
        batch.add_column(
            sa.Column("action_type", sa.String(96), nullable=False, server_default="")
        )
        batch.add_column(
            sa.Column(
                "handler_version", sa.String(32), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "approval_policy_version",
                sa.String(32),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(32),
                nullable=False,
                server_default="WAITING_APPROVAL",
            )
        )
        batch.add_column(
            sa.Column(
                "waiting_approval_at",
                sa.String(32),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "approval_user_id",
                sa.String(64),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "approval_request_id",
                sa.String(128),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "approval_args_hash",
                sa.String(64),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "approval_entity_revision",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column(
                "approval_expires_at",
                sa.String(32),
                nullable=False,
                server_default="",
            )
        )
        for name in (
            "rejected_at",
            "commit_started_at",
            "verification_started_at",
            "verified_at",
        ):
            batch.add_column(
                sa.Column(name, sa.String(32), nullable=False, server_default="")
            )
        batch.add_column(
            sa.Column(
                "rejection_reason", sa.Text(), nullable=False, server_default=""
            )
        )
        batch.add_column(
            sa.Column(
                "execution_user_id",
                sa.String(64),
                nullable=True,
            )
        )
        batch.add_column(
            sa.Column(
                "domain_audit_id",
                sa.String(128),
                nullable=False,
                server_default="",
            )
        )
        batch.add_column(
            sa.Column(
                "verification_result_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.add_column(
            sa.Column(
                "compensation_json",
                sa.Text(),
                nullable=False,
                server_default="{}",
            )
        )
        batch.create_check_constraint(
            "ck_ai_action_lifecycle_status",
            "lifecycle_status IN ('PROPOSED', 'WAITING_APPROVAL', 'APPROVED', 'REJECTED', "
            "'EXPIRED', 'CANCELLED', 'COMMITTING', 'VERIFYING', 'EXECUTED', "
            "'FAILED', 'STALE')",
        )
        batch.create_foreign_key(
            "fk_ai_action_approval_user",
            "auth_users",
            ["approval_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.create_foreign_key(
            "fk_ai_action_execution_user",
            "auth_users",
            ["execution_user_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE ai_action_confirmations SET "
            "action_type = 'APPLY_INJECTION_AUTO_SCHEDULE_RUN', "
            "handler_version = 'legacy-confirmation-v1', "
            "approval_policy_version = 'legacy-confirmation-v1', "
            "waiting_approval_at = created_at, "
            "lifecycle_status = CASE status "
            "WHEN 'PENDING' THEN 'WAITING_APPROVAL' "
            "WHEN 'CONFIRMED' THEN 'APPROVED' "
            "ELSE status END, "
            "approval_user_id = CASE WHEN status IN ('CONFIRMED', 'EXECUTED') "
            "THEN user_id ELSE NULL END, "
            "approval_request_id = CASE WHEN status IN ('CONFIRMED', 'EXECUTED') "
            "THEN 'legacy-confirm-' || id ELSE '' END, "
            "approval_args_hash = CASE WHEN status IN ('CONFIRMED', 'EXECUTED') "
            "THEN args_hash ELSE '' END, "
            "approval_entity_revision = CASE WHEN status IN ('CONFIRMED', 'EXECUTED') "
            "THEN entity_revision ELSE 0 END, "
            "approval_expires_at = CASE WHEN status IN ('CONFIRMED', 'EXECUTED') "
            "THEN expires_at ELSE '' END, "
            "execution_user_id = CASE WHEN status = 'EXECUTED' THEN user_id ELSE NULL END"
        )
    )
    op.create_index(
        "ix_ai_action_confirmations_lifecycle_status",
        "ai_action_confirmations",
        ["lifecycle_status"],
    )
    op.create_index(
        "ix_ai_action_confirmations_approval_user_id",
        "ai_action_confirmations",
        ["approval_user_id"],
    )
    op.create_index(
        "ix_ai_action_confirmations_execution_user_id",
        "ai_action_confirmations",
        ["execution_user_id"],
    )
    op.create_index(
        "ix_ai_action_lifecycle_expiry",
        "ai_action_confirmations",
        ["lifecycle_status", "expires_at"],
    )
    op.create_index(
        "uq_ai_action_approval_request",
        "ai_action_confirmations",
        ["approval_request_id"],
        unique=True,
        sqlite_where=sa.text("approval_request_id != ''"),
        postgresql_where=sa.text("approval_request_id != ''"),
    )


def downgrade() -> None:
    context = op.get_context()
    if context.as_sql:
        raise RuntimeError(
            "Offline downgrade is blocked because Action Gateway evidence cannot be inspected."
        )
    connection = op.get_bind()
    protected = int(
        connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM ai_action_confirmations WHERE "
                "gateway_contract_version = 'action-gateway-v1' OR "
                "domain_audit_id != '' OR verification_result_json != '{}'"
            )
        ).scalar_one()
    )
    if protected:
        raise RuntimeError(
            "Refusing to downgrade 20260813_0074 while Action Gateway "
            f"approval or verification evidence exists: {protected}"
        )
    for name in (
        "uq_ai_action_approval_request",
        "ix_ai_action_lifecycle_expiry",
        "ix_ai_action_confirmations_execution_user_id",
        "ix_ai_action_confirmations_approval_user_id",
        "ix_ai_action_confirmations_lifecycle_status",
    ):
        op.drop_index(name, table_name="ai_action_confirmations")
    with op.batch_alter_table(
        "ai_action_confirmations",
        recreate="auto",
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint("ck_ai_action_lifecycle_status", type_="check")
        for name in reversed(_NEW_COLUMNS):
            batch.drop_column(name)
