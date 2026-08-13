from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIActionConfirmation(Base):
    __tablename__ = "ai_action_confirmations"
    __table_args__ = (
        CheckConstraint(
            "risk_level IN ('CONSEQUENTIAL_WRITE', 'HIGH_RISK_WRITE')",
            name="ck_ai_action_confirmation_risk",
        ),
        CheckConstraint(
            "status IN ('PENDING', 'CONFIRMED', 'EXECUTED', 'EXPIRED', "
            "'CANCELLED', 'STALE', 'FAILED')",
            name="ck_ai_action_confirmation_status",
        ),
        CheckConstraint(
            "lifecycle_status IN ('PROPOSED', 'WAITING_APPROVAL', 'APPROVED', 'REJECTED', "
            "'EXPIRED', 'CANCELLED', 'COMMITTING', 'VERIFYING', 'EXECUTED', "
            "'FAILED', 'STALE')",
            name="ck_ai_action_lifecycle_status",
        ),
        Index(
            "uq_ai_action_confirmation_request",
            "user_id",
            "tool_name",
            "request_id",
            unique=True,
        ),
        Index(
            "uq_ai_action_confirmation_execution_request",
            "execution_request_id",
            unique=True,
            sqlite_where=text("execution_request_id != ''"),
            postgresql_where=text("execution_request_id != ''"),
        ),
        Index(
            "ix_ai_action_confirmation_user_status_expiry",
            "user_id",
            "status",
            "expires_at",
        ),
        Index(
            "ix_ai_action_confirmation_entity",
            "factory_id",
            "entity_type",
            "entity_id",
        ),
        Index(
            "ix_ai_action_lifecycle_expiry",
            "lifecycle_status",
            "expires_at",
        ),
        Index(
            "uq_ai_action_approval_request",
            "approval_request_id",
            unique=True,
            sqlite_where=text("approval_request_id != ''"),
            postgresql_where=text("approval_request_id != ''"),
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), index=True
    )
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    risk_level: Mapped[str] = mapped_column(String(32))
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(96), index=True)
    entity_revision: Mapped[int] = mapped_column()
    args_hash: Mapped[str] = mapped_column(String(64), index=True)
    normalized_action_json: Mapped[str] = mapped_column(Text)
    request_id: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[str] = mapped_column(String(32), index=True)
    confirmed_at: Mapped[str] = mapped_column(String(32), default="")
    executed_at: Mapped[str] = mapped_column(String(32), default="")
    execution_request_id: Mapped[str] = mapped_column(String(128), default="")
    execution_result_json: Mapped[str] = mapped_column(Text, default="{}")
    failure_code: Mapped[str] = mapped_column(String(96), default="")
    gateway_contract_version: Mapped[str] = mapped_column(String(32), default="")
    action_type: Mapped[str] = mapped_column(String(96), default="")
    handler_version: Mapped[str] = mapped_column(String(32), default="")
    approval_policy_version: Mapped[str] = mapped_column(String(32), default="")
    lifecycle_status: Mapped[str] = mapped_column(
        String(32), default="WAITING_APPROVAL", index=True
    )
    waiting_approval_at: Mapped[str] = mapped_column(String(32), default="")
    approval_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    approval_request_id: Mapped[str] = mapped_column(String(128), default="")
    approval_args_hash: Mapped[str] = mapped_column(String(64), default="")
    approval_entity_revision: Mapped[int] = mapped_column(default=0)
    approval_expires_at: Mapped[str] = mapped_column(String(32), default="")
    rejected_at: Mapped[str] = mapped_column(String(32), default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    commit_started_at: Mapped[str] = mapped_column(String(32), default="")
    verification_started_at: Mapped[str] = mapped_column(String(32), default="")
    verified_at: Mapped[str] = mapped_column(String(32), default="")
    execution_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    domain_audit_id: Mapped[str] = mapped_column(String(128), default="")
    verification_result_json: Mapped[str] = mapped_column(Text, default="{}")
    compensation_json: Mapped[str] = mapped_column(Text, default="{}")
