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
