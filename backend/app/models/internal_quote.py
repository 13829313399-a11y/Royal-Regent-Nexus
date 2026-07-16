from sqlalchemy import Boolean, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
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
    workshop_name: Mapped[str] = mapped_column(String(128))
    quote_no: Mapped[str] = mapped_column(String(128), index=True)
    product_name: Mapped[str] = mapped_column(String(255))
    customer: Mapped[str] = mapped_column(String(128), index=True)
    qty: Mapped[int] = mapped_column(Integer)
    version_label: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    initiator_department: Mapped[str] = mapped_column(String(64), default="sales-business", index=True)
    business_owner_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    business_owner_name: Mapped[str] = mapped_column(String(128), default="")
    target_date: Mapped[str] = mapped_column(String(32), default="")
    remark: Mapped[str] = mapped_column(Text, default="")
    module_version: Mapped[str] = mapped_column(String(32), default="v2", index=True)
    reference_snapshot_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    formula_version: Mapped[str] = mapped_column(String(64), default="rr2-2026-v1", index=True)
    header_revision: Mapped[int] = mapped_column(Integer, default=1)
    cloned_from_quote_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    archived_by: Mapped[str] = mapped_column(String(64), default="")
    archived_at: Mapped[str] = mapped_column(String(32), default="")
    archive_reason: Mapped[str] = mapped_column(Text, default="")
    final_release_status: Mapped[str] = mapped_column(String(32), default="", index=True)
    final_submission_revision: Mapped[int] = mapped_column(Integer, default=0)
    final_submission_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    final_submitted_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    final_submitted_by_name: Mapped[str] = mapped_column(String(128), default="")
    final_submitted_at: Mapped[str] = mapped_column(String(32), default="")
    final_reviewed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    final_reviewed_by_name: Mapped[str] = mapped_column(String(128), default="")
    final_reviewed_at: Mapped[str] = mapped_column(String(32), default="")
    final_review_comment: Mapped[str] = mapped_column(Text, default="")
    final_release_revision: Mapped[int] = mapped_column(Integer, default=0)
    final_release_invalidated_at: Mapped[str] = mapped_column(String(32), default="")
    final_release_invalidation_reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))
    updated_at: Mapped[str] = mapped_column(String(32))


class InternalQuoteSection(Base):
    __tablename__ = "internal_quote_sections"
    __table_args__ = (
        UniqueConstraint("quote_id", "department", name="uq_internal_quote_sections_quote_department"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    department: Mapped[str] = mapped_column(String(64), index=True)
    department_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), index=True)
    payload_json: Mapped[str] = mapped_column(Text, default="{}")
    calculation_json: Mapped[str] = mapped_column(Text, default="{}")
    calculation_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    calculation_hash: Mapped[str] = mapped_column(String(64), default="")
    calculation_formula_version: Mapped[str] = mapped_column(String(64), default="")
    calculation_reference_snapshot_id: Mapped[str] = mapped_column(String(96), default="")
    calculated_at: Mapped[str] = mapped_column(String(32), default="")
    dependency_hash: Mapped[str] = mapped_column(String(64), default="")
    dependency_status: Mapped[str] = mapped_column(String(32), default="current", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
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
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    department: Mapped[str] = mapped_column(String(64), default="", index=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128))
    action: Mapped[str] = mapped_column(String(64), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    old_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(96), default="")
    ip_address: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(32), index=True)


class InternalQuoteSectionRevision(Base):
    __tablename__ = "internal_quote_section_revisions"
    __table_args__ = (
        UniqueConstraint(
            "section_id",
            "revision",
            name="uq_internal_quote_section_revisions_section_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quote_sections.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    department: Mapped[str] = mapped_column(String(64), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))
    payload_json: Mapped[str] = mapped_column(Text)
    calculation_json: Mapped[str] = mapped_column(Text)
    formula_version: Mapped[str] = mapped_column(String(64), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    reference_snapshot_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    dependency_hash: Mapped[str] = mapped_column(String(64), default="")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    reason: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))


class InternalQuoteReview(Base):
    __tablename__ = "internal_quote_reviews"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    section_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quote_sections.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    department: Mapped[str] = mapped_column(String(64), index=True)
    review_type: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(32), index=True)
    section_revision: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))


class InternalQuoteReferenceSet(Base):
    __tablename__ = "internal_quote_reference_sets"
    __table_args__ = (
        UniqueConstraint(
            "quote_id",
            "source_revision",
            name="uq_internal_quote_reference_sets_quote_revision",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    version_label: Mapped[str] = mapped_column(String(64))
    formula_version: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(32))
    source_revision: Mapped[int] = mapped_column(Integer)
    snapshot_json: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))
    superseded_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteImportBatch(Base):
    __tablename__ = "internal_quote_import_batches"

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    import_type: Mapped[str] = mapped_column(String(32), index=True)
    target_department: Mapped[str] = mapped_column(String(64), index=True)
    source_file_name: Mapped[str] = mapped_column(String(255), default="")
    source_sha256: Mapped[str] = mapped_column(String(64), index=True)
    source_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="previewed", index=True)
    preview_schema_version: Mapped[str] = mapped_column(String(32), default="p3-v1")
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    target_revision: Mapped[int] = mapped_column(Integer, default=0)
    confirm_mode: Mapped[str] = mapped_column(String(16), default="")
    confirmed_revision: Mapped[int] = mapped_column(Integer, default=0)
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
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
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
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    content_type: Mapped[str] = mapped_column(String(128), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    section_revisions_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(32), default="current", index=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    template_version: Mapped[str] = mapped_column(String(64), default="internal-quote-p3-v1")
    formula_version: Mapped[str] = mapped_column(String(64), default="")
    reference_snapshot_id: Mapped[str] = mapped_column(String(96), default="", index=True)
    header_revision: Mapped[int] = mapped_column(Integer, default=0)
    release_stage: Mapped[str] = mapped_column(String(32), default="p3_section_approved")
    export_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    exported_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    exported_by_name: Mapped[str] = mapped_column(String(128), default="")
    exported_at: Mapped[str] = mapped_column(String(32), default="")
    superseded_at: Mapped[str] = mapped_column(String(32), default="")


class InternalQuoteFinalReview(Base):
    __tablename__ = "internal_quote_final_reviews"
    __table_args__ = (
        UniqueConstraint(
            "quote_id",
            "submission_revision",
            name="uq_internal_quote_final_reviews_quote_submission",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    submission_revision: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(32), index=True)
    header_revision: Mapped[int] = mapped_column(Integer)
    section_revisions_json: Mapped[str] = mapped_column(Text)
    release_manifest_json: Mapped[str] = mapped_column(Text)
    release_manifest_sha256: Mapped[str] = mapped_column(String(64))
    submitted_by: Mapped[str] = mapped_column(String(64))
    submitted_by_name: Mapped[str] = mapped_column(String(128))
    submitted_at: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_name: Mapped[str] = mapped_column(String(128))
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[str] = mapped_column(String(32))


class InternalQuoteArtifactHandoff(Base):
    __tablename__ = "internal_quote_artifact_handoffs"
    __table_args__ = (
        UniqueConstraint(
            "export_id",
            name="uq_internal_quote_artifact_handoffs_export",
        ),
        UniqueConstraint(
            "quote_id",
            "release_revision",
            name="uq_internal_quote_artifact_handoffs_quote_release",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    quote_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quotes.id", ondelete="CASCADE"), index=True
    )
    export_id: Mapped[str] = mapped_column(
        ForeignKey("internal_quote_export_files.id", ondelete="CASCADE"), index=True
    )
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    customer: Mapped[str] = mapped_column(String(128), index=True)
    quote_no: Mapped[str] = mapped_column(String(128))
    version_label: Mapped[str] = mapped_column(String(64))
    release_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    artifact_manifest_json: Mapped[str] = mapped_column(Text, default="{}")
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(32))
    consumed_by: Mapped[str] = mapped_column(String(64), default="", index=True)
    consumed_by_name: Mapped[str] = mapped_column(String(128), default="")
    consumed_at: Mapped[str] = mapped_column(String(32), default="")
    consumer_reference: Mapped[str] = mapped_column(String(128), default="")
    revoked_at: Mapped[str] = mapped_column(String(32), default="")
    revoke_reason: Mapped[str] = mapped_column(Text, default="")
