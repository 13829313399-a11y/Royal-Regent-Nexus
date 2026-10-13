"""Private source workbooks, explicitly shared fill ranges and append-only history."""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, JSON, String, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CollaborativeSheet(Base):
    __tablename__ = "collaborative_sheets"
    __table_args__ = (
        CheckConstraint("status IN ('draft','open','closed')", name="ck_collaborative_sheet_status"),
        CheckConstraint("revision >= 1", name="ck_collaborative_sheet_revision"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), index=True)
    owner_name: Mapped[str] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(String(160))
    original_name: Mapped[str] = mapped_column(String(240))
    format: Mapped[str] = mapped_column(String(8))
    storage_key: Mapped[str] = mapped_column(String(400))
    source_sha256: Mapped[str] = mapped_column(String(64))
    byte_size: Mapped[int] = mapped_column(Integer)
    manifest: Mapped[dict] = mapped_column(JSON)
    overrides: Mapped[dict] = mapped_column(JSON)
    grants: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16))
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class CollaborativeSheetEvent(Base):
    __tablename__ = "collaborative_sheet_events"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("collaborative_sheets.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[str] = mapped_column(String(32))


class CollaborativeSheetSubmission(Base):
    __tablename__ = "collaborative_sheet_submissions"
    task_id: Mapped[str] = mapped_column(ForeignKey("collaborative_sheets.id"), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[str] = mapped_column(String(32))


def _immutable(*_args):
    raise ValueError("Collaborative sheet history is append-only")


def _create_history_guards(table, connection, **_kwargs):
    if connection.dialect.name == "sqlite":
        for action in ("UPDATE", "DELETE"):
            connection.execute(text(f"CREATE TRIGGER {table.name}_no_{action.lower()} BEFORE {action} ON {table.name} "
                                    "BEGIN SELECT RAISE(ABORT, 'collaborative sheet history is append-only'); END"))
    elif connection.dialect.name == "postgresql":
        connection.execute(text("""CREATE OR REPLACE FUNCTION collaborative_sheet_history_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'collaborative sheet history is append-only'; END; $$ LANGUAGE plpgsql"""))
        connection.execute(text(f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
                                "FOR EACH ROW EXECUTE FUNCTION collaborative_sheet_history_immutable()"))


event.listen(CollaborativeSheetEvent, "before_update", _immutable)
event.listen(CollaborativeSheetEvent, "before_delete", _immutable)
event.listen(CollaborativeSheetEvent.__table__, "after_create", _create_history_guards)
