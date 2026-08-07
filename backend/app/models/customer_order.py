from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CustomerOrderExportAudit(Base):
    """Immutable evidence for a generated customer schedule export."""

    __tablename__ = "customer_order_export_audits"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("auth_users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_username: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_display_name: Mapped[str] = mapped_column(String(128), default="")
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_code: Mapped[str] = mapped_column(String(64), index=True)
    received_date: Mapped[str] = mapped_column(String(32), default="", index=True)
    preview_schema_version: Mapped[str] = mapped_column(String(96), default="")
    preview_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    po_file_names_json: Mapped[str] = mapped_column(Text, default="[]")
    source_po_sha256s_json: Mapped[str] = mapped_column(Text, default="[]")
    schedule_file_name: Mapped[str] = mapped_column(String(255), default="")
    source_schedule_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    output_file_name: Mapped[str] = mapped_column(String(255), default="")
    output_sha256: Mapped[str] = mapped_column(String(64), index=True)
    output_template: Mapped[str] = mapped_column(String(128), default="")
    confirmed_issue_keys_json: Mapped[str] = mapped_column(Text, default="[]")
    confirmed_issue_count: Mapped[int] = mapped_column(Integer, default=0)
    manual_overrides_json: Mapped[str] = mapped_column(Text, default="[]")
    manual_override_count: Mapped[int] = mapped_column(Integer, default=0)
    confirmation_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)
