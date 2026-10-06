from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base


class CartonFeedback(Base):
    __tablename__ = "carton_feedback"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_feedback_id_factory"),
        UniqueConstraint("factory_id", "author_id", "request_key", name="uq_carton_feedback_request"),
        CheckConstraint("status IN ('OPEN','FIXED','DECLINED') AND revision >= 1", name="ck_carton_feedback_state"),
        Index("ix_carton_feedback_factory_author", "factory_id", "author_id", "created_at"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    context_path: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="OPEN")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    request_key: Mapped[str] = mapped_column(String(64))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))


class CartonFeedbackReply(Base):
    __tablename__ = "carton_feedback_replies"
    __table_args__ = (ForeignKeyConstraint(["feedback_id", "factory_id"], ["carton_feedback.id", "carton_feedback.factory_id"], ondelete="RESTRICT"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    feedback_id: Mapped[str] = mapped_column(String(96), index=True)
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(128))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class CartonFeedbackImage(Base):
    __tablename__ = "carton_feedback_images"
    __table_args__ = (ForeignKeyConstraint(["feedback_id", "factory_id"], ["carton_feedback.id", "carton_feedback.factory_id"], ondelete="RESTRICT"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    feedback_id: Mapped[str] = mapped_column(String(96), index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(40))


class CartonFeatureUpdate(Base):
    __tablename__ = "carton_feature_updates"
    __table_args__ = (UniqueConstraint("factory_id", "author_id", "request_key", name="uq_carton_feature_update_request"),)
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    audience: Mapped[str] = mapped_column(String(16), default="INTERNAL", server_default="INTERNAL")
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(128))
    request_key: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
