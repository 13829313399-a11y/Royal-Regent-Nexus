from sqlalchemy import ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class InternalQuote(Base):
    __tablename__ = "internal_quotes"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "workshop_code",
            "quote_no",
            "version_label",
            name="uq_internal_quotes_factory_workshop_no_version",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    workshop_code: Mapped[str] = mapped_column(String(64), index=True)
    workshop_name: Mapped[str] = mapped_column(String(128), default="")
    quote_no: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255), default="")
    customer: Mapped[str] = mapped_column(String(128), default="", index=True)
    qty: Mapped[int] = mapped_column(Integer, default=0)
    version_label: Mapped[str] = mapped_column(String(64), default="V1")
    status: Mapped[str] = mapped_column(String(32), default="drafting", index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteSection(Base):
    __tablename__ = "internal_quote_sections"
    __table_args__ = (
        UniqueConstraint("quote_id", "department", name="uq_internal_quote_sections_quote_department"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    department: Mapped[str] = mapped_column(String(64), index=True)
    department_name: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    calculation_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    filled_by: Mapped[str] = mapped_column(String(128), default="")
    filled_at: Mapped[str] = mapped_column(String(32), default="")
    submitted_by: Mapped[str] = mapped_column(String(128), default="")
    submitted_by_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    submitted_at: Mapped[str] = mapped_column(String(32), default="")
    reviewed_by: Mapped[str] = mapped_column(String(128), default="")
    reviewed_at: Mapped[str] = mapped_column(String(32), default="")
    review_comment: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteAuditLog(Base):
    __tablename__ = "internal_quote_audit_logs"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteImportBatch(Base):
    __tablename__ = "internal_quote_import_batches"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32), index=True)
    target_department: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255), default="")
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="previewed", index=True)
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), default="")
    confirmed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    confirmed_by_name: Mapped[str] = mapped_column(String(128), default="")
    confirmed_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteAttachment(Base):
    __tablename__ = "internal_quote_attachments"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    uploaded_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    uploaded_by_name: Mapped[str] = mapped_column(String(128), default="")
    uploaded_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteExportFile(Base):
    __tablename__ = "internal_quote_export_files"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"),
        index=True,
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    section_revisions_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="current", index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    exported_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    exported_by_name: Mapped[str] = mapped_column(String(128), default="")
    exported_at: Mapped[str] = mapped_column(String(32), default="")
    superseded_at: Mapped[str] = mapped_column(String(32), default="")
