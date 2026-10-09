"""Private module feedback and immutable conversation evidence."""
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, JSON, LargeBinary, String, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class FeedbackTicket(Base):
    __tablename__ = "module_feedback_tickets"
    __table_args__ = (
        UniqueConstraint("factory_id", "author_id", "client_request_id", name="uq_feedback_create_request"),
        CheckConstraint("revision >= 1", name="ck_feedback_revision"),
        CheckConstraint("status IN ('submitted','needs_info','in_progress','awaiting_verification','resolved')", name="ck_feedback_status"),
        Index("ix_feedback_scope", "factory_id", "module", "author_id"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    module: Mapped[str] = mapped_column(String(64))
    author_id: Mapped[str] = mapped_column(String(64))
    author_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(32))
    emoji: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32))
    assigned_name: Mapped[str] = mapped_column(String(128))
    context: Mapped[dict] = mapped_column(JSON)
    requested_materials: Mapped[list] = mapped_column(JSON)
    provided_materials: Mapped[list] = mapped_column(JSON)
    release_note: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    client_request_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class FeedbackMessage(Base):
    __tablename__ = "module_feedback_messages"
    __table_args__ = (
        UniqueConstraint("ticket_id", "revision", name="uq_feedback_message_revision"),
        UniqueConstraint("ticket_id", "actor_id", "client_request_id", name="uq_feedback_message_request"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("module_feedback_tickets.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    actor_kind: Mapped[str] = mapped_column(String(16))
    body: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(32))
    requested_materials: Mapped[list] = mapped_column(JSON)
    provided_materials: Mapped[list] = mapped_column(JSON)
    release_note: Mapped[str] = mapped_column(Text)
    revision: Mapped[int] = mapped_column(Integer)
    client_request_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(32))


class FeedbackAttachment(Base):
    __tablename__ = "module_feedback_attachments"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    message_id: Mapped[str] = mapped_column(ForeignKey("module_feedback_messages.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(128))
    size: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class FeedbackReadReceipt(Base):
    __tablename__ = "module_feedback_reads"
    __table_args__ = (CheckConstraint("through_revision >= 0", name="ck_feedback_read_revision"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ticket_id: Mapped[str] = mapped_column(ForeignKey("module_feedback_tickets.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    through_revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(32))


def _immutable(*_args):
    raise ValueError("Feedback conversation evidence is append-only")


def _create_evidence_guards(table, connection, **_kwargs):
    # Fresh development/test databases created with metadata deserve the same
    # protection as databases upgraded by Alembic.
    if connection.dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            connection.execute(text(f"CREATE TRIGGER {table.name}_no_{action.lower()} BEFORE {action} ON {table.name} "
                                    "BEGIN SELECT RAISE(ABORT, 'feedback evidence is append-only'); END"))
    elif connection.dialect.name == "postgresql":
        connection.execute(text("""CREATE OR REPLACE FUNCTION module_feedback_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'feedback evidence is append-only'; END; $$ LANGUAGE plpgsql"""))
        connection.execute(text(f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
                                "FOR EACH ROW EXECUTE FUNCTION module_feedback_immutable()"))


for _model in (FeedbackMessage, FeedbackAttachment, FeedbackReadReceipt):
    event.listen(_model, "before_update", _immutable)
    event.listen(_model, "before_delete", _immutable)
    event.listen(_model.__table__, "after_create", _create_evidence_guards)
