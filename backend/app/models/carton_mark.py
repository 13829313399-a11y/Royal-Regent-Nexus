from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CartonMarkCustomer(Base):
    __tablename__ = "carton_mark_customers"
    __table_args__ = (
        UniqueConstraint(
            "factory_id",
            "normalized_name",
            name="uq_carton_mark_customer_factory_name",
        ),
        Index(
            "ix_carton_mark_customer_factory_name",
            "factory_id",
            "normalized_name",
        ),
        CheckConstraint("revision >= 1", name="ck_carton_mark_customer_revision"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    normalized_name: Mapped[str] = mapped_column(String(128))
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), index=True)
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_by: Mapped[str] = mapped_column(String(64), index=True)
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_at: Mapped[str] = mapped_column(String(40))


class CartonMarkTemplate(Base):
    __tablename__ = "carton_mark_templates"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_carton_mark_template_id_factory"),
        UniqueConstraint(
            "factory_id",
            "document_fingerprint",
            name="uq_carton_mark_template_factory_documents",
        ),
        UniqueConstraint(
            "factory_id",
            "business_key_sha256",
            "version",
            name="uq_carton_mark_template_business_version",
        ),
        CheckConstraint("version >= 1", name="ck_carton_mark_template_version"),
        CheckConstraint(
            "check_status IN ('核对通过', '发现差异', '需复核')",
            name="ck_carton_mark_template_check_status",
        ),
        Index(
            "ix_carton_mark_template_factory_active_created",
            "factory_id",
            "is_archived",
            "created_at",
        ),
        Index(
            "ix_carton_mark_template_factory_customer_item",
            "factory_id",
            "customer_name",
            "item",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    customer_name: Mapped[str] = mapped_column(String(255))
    po: Mapped[str] = mapped_column(String(128), default="")
    item: Mapped[str] = mapped_column(String(128))
    contract_number: Mapped[str] = mapped_column(String(128))
    business_key_sha256: Mapped[str] = mapped_column(String(64))
    document_fingerprint: Mapped[str] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, default=1)
    check_status: Mapped[str] = mapped_column(String(16))
    check_result_json: Mapped[str] = mapped_column(Text)
    excel_sha256: Mapped[str] = mapped_column(String(64))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    manual_release_reason: Mapped[str] = mapped_column(Text, default="")
    manual_release_source_status: Mapped[str] = mapped_column(String(16), default="")
    manual_released_by: Mapped[str] = mapped_column(String(64), default="")
    manual_released_by_name: Mapped[str] = mapped_column(String(128), default="")
    manual_released_at: Mapped[str] = mapped_column(String(40), default="")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    archived_by: Mapped[str] = mapped_column(String(64), default="")
    archived_by_name: Mapped[str] = mapped_column(String(128), default="")
    archived_at: Mapped[str] = mapped_column(String(40), default="")


class CartonMarkDocument(Base):
    __tablename__ = "carton_mark_documents"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "kind", name="uq_carton_mark_document_template_kind"
        ),
        ForeignKeyConstraint(
            ["template_id", "factory_id"],
            ["carton_mark_templates.id", "carton_mark_templates.factory_id"],
            name="fk_carton_mark_document_template_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "kind IN ('source_excel', 'print_pdf')",
            name="ck_carton_mark_document_kind",
        ),
        CheckConstraint("size_bytes > 0", name="ck_carton_mark_document_size"),
        Index(
            "ix_carton_mark_document_factory_template",
            "factory_id",
            "template_id",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    template_id: Mapped[str] = mapped_column(String(96))
    factory_id: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[str] = mapped_column(String(40))
