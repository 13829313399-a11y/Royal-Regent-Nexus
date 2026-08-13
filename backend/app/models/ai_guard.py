from sqlalchemy import BigInteger, Boolean, CheckConstraint, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class AIGuardLease(Base):
    __tablename__ = "ai_guard_leases"
    __table_args__ = (
        CheckConstraint(
            "reservation_tokens >= 0", name="ck_ai_guard_lease_reservation"
        ),
        CheckConstraint(
            "reported_tokens >= 0", name="ck_ai_guard_lease_reported"
        ),
        Index(
            "ix_ai_guard_lease_user_expiry",
            "user_id",
            "expires_at",
        ),
        Index(
            "ix_ai_guard_lease_instance_expiry",
            "instance_id",
            "expires_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lease_token: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    instance_id: Mapped[str] = mapped_column(String(128), index=True)
    reservation_tokens: Mapped[int] = mapped_column(BigInteger)
    budget_day: Mapped[str] = mapped_column(String(10), index=True)
    expires_at: Mapped[str] = mapped_column(String(40), index=True)
    provider_started: Mapped[bool] = mapped_column(Boolean, default=False)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    reported_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    created_at: Mapped[str] = mapped_column(String(40), index=True)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)


class AIGuardRequestEvent(Base):
    __tablename__ = "ai_guard_request_events"
    __table_args__ = (
        Index(
            "ix_ai_guard_request_user_created",
            "user_id",
            "created_at",
        ),
        Index("ix_ai_guard_request_expiry", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(128), index=True)
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    instance_id: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[str] = mapped_column(String(40))
    expires_at: Mapped[str] = mapped_column(String(40))


class AIGuardDailyBudget(Base):
    __tablename__ = "ai_guard_daily_budgets"
    __table_args__ = (
        CheckConstraint("used_tokens >= 0", name="ck_ai_guard_budget_used"),
        CheckConstraint(
            "reserved_tokens >= 0", name="ck_ai_guard_budget_reserved"
        ),
        Index("ix_ai_guard_budget_day", "budget_day"),
    )

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    budget_day: Mapped[str] = mapped_column(String(10), primary_key=True)
    used_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[str] = mapped_column(String(40), index=True)


class AIGuardDisableState(Base):
    __tablename__ = "ai_guard_disable_states"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('GLOBAL', 'FACTORY', 'USER')",
            name="ck_ai_guard_disable_scope",
        ),
        Index("ix_ai_guard_disable_active", "disabled", "expires_at"),
    )

    scope_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    disabled: Mapped[bool] = mapped_column(Boolean, default=True)
    reason_code: Mapped[str] = mapped_column(String(96), default="")
    expires_at: Mapped[str] = mapped_column(String(40), default="")
    updated_by_instance: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[str] = mapped_column(String(40), index=True)
