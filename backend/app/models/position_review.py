"""Declarations are workflow records, never authorization sources."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class PositionReview(Base):
    __tablename__ = "position_reviews"
    __table_args__ = (
        CheckConstraint("status IN ('pending','returned','applied','withdrawn','invalidated')", name="ck_position_review_status"),
        CheckConstraint("origin IN ('employee','admin')", name="ck_position_review_origin"),
        Index("uq_position_review_open", "user_id", "employment_epoch", unique=True,
              sqlite_where=text("status IN ('pending','returned')"), postgresql_where=text("status IN ('pending','returned')")),
        Index("ix_position_review_queue", "status", "created_at", "id"),
        Index("ix_position_review_person", "user_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    employment_epoch: Mapped[int] = mapped_column(Integer)
    origin: Mapped[str] = mapped_column(String(16))
    initiator_user_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    declared_snapshot_json: Mapped[str] = mapped_column(Text)
    base_official_snapshot_json: Mapped[str] = mapped_column(Text, default="null")
    base_identity_version: Mapped[int] = mapped_column(Integer, default=0)
    base_authorization_version: Mapped[int] = mapped_column(Integer, default=0)
    confirmed_snapshot_json: Mapped[str] = mapped_column(Text, default="null")
    decision: Mapped[str] = mapped_column(String(32), default="")
    reviewer_user_id: Mapped[str | None] = mapped_column(ForeignKey("auth_users.id"), nullable=True)
    review_comment: Mapped[str] = mapped_column(Text, default="")
    decision_at: Mapped[str] = mapped_column(String(32), default="")
    applied_identity_change_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    receipt_command_id: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))
    last_submitted_at: Mapped[str] = mapped_column(String(32))


class PositionReviewEvent(Base):
    __tablename__ = "position_review_events"
    __table_args__ = (Index("ix_position_review_event_history", "review_id", "revision"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("position_reviews.id"))
    revision: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("auth_users.id"))
    event_type: Mapped[str] = mapped_column(String(32))
    before_json: Mapped[str] = mapped_column(Text, default="null")
    after_json: Mapped[str] = mapped_column(Text)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32))
