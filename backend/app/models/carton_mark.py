from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class CartonMarkLayout(Base):
    """Immutable customer layout versions in the supplier's factory boundary."""
    __tablename__ = "carton_mark_layouts"
    __table_args__ = (
        ForeignKeyConstraint(["supplier_id", "factory_id"], ["carton_suppliers.id", "carton_suppliers.factory_id"], name="fk_mark_layout_supplier_factory"),
        UniqueConstraint("factory_id", "supplier_id", "customer_key", "version", name="uq_mark_layout_customer_version"),
        CheckConstraint("version >= 1 AND reference_size > 0", name="ck_mark_layout_version_size"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    supplier_id: Mapped[str] = mapped_column(String(96))
    customer_key: Mapped[str] = mapped_column(String(300))
    customer_name: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(128))
    version: Mapped[int] = mapped_column(Integer)
    config_json: Mapped[str] = mapped_column(Text)
    reference_name: Mapped[str] = mapped_column(String(255))
    reference_sha256: Mapped[str] = mapped_column(String(64))
    reference_size: Mapped[int] = mapped_column(Integer)
    reference_content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))


class CartonMarkAsset(Base):
    """Independent source files; storage does not constitute QC approval."""
    __tablename__ = "carton_mark_assets"
    __table_args__ = (
        Index("ix_carton_mark_asset_factory_sha", "factory_id", "sha256"),
        Index("uq_carton_mark_asset_id_factory", "id", "factory_id", unique=True),
        ForeignKeyConstraint(["bound_order_id", "factory_id"],
                             ["carton_orders.id", "carton_orders.factory_id"],
                             name="fk_carton_mark_asset_order_factory"),
        CheckConstraint("kind IN ('excel', 'pdf', 'image')", name="ck_carton_mark_asset_kind"),
        CheckConstraint("photo_group_id IS NULL OR kind = 'image'", name="ck_carton_mark_asset_photo_group"),
        CheckConstraint("revision >= 1 AND size_bytes > 0", name="ck_carton_mark_asset_size_revision"),
        Index("ix_carton_mark_asset_factory_contract", "factory_id", "contract_number"),
        Index("ix_carton_mark_asset_factory_photo_group", "factory_id", "photo_group_id"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    file_name: Mapped[str] = mapped_column(String(255))
    kind: Mapped[str] = mapped_column(String(16))
    photo_group_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    contract_number: Mapped[str] = mapped_column(String(128), default="")
    bound_order_id: Mapped[str | None] = mapped_column(String(96), ForeignKey("carton_orders.id", ondelete="SET NULL", name="fk_carton_mark_asset_order_delete"), nullable=True)
    recognition_source: Mapped[str] = mapped_column(String(32), default="")
    candidates_json: Mapped[str] = mapped_column(Text, default="[]")
    warning: Mapped[str] = mapped_column(String(500), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))
    order_bindings: Mapped[list["CartonMarkAssetOrderBinding"]] = relationship(
        lazy="selectin", cascade="all, delete-orphan", passive_deletes=True)


class CartonMarkAssetOrderBinding(Base):
    __tablename__ = "carton_mark_asset_order_bindings"
    __table_args__ = (
        ForeignKeyConstraint(["asset_id", "factory_id"], ["carton_mark_assets.id", "carton_mark_assets.factory_id"],
                             ondelete="CASCADE", name="fk_carton_mark_binding_asset_factory"),
        ForeignKeyConstraint(["order_id", "factory_id"], ["carton_orders.id", "carton_orders.factory_id"],
                             ondelete="CASCADE", name="fk_carton_mark_binding_order_factory"),
        Index("ix_carton_mark_binding_factory_order", "factory_id", "order_id"),
    )
    asset_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    order_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))


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


class CartonMarkQcRecord(Base):
    """Frozen identity of one site-photo check; later decisions are appended."""
    __tablename__ = "carton_mark_qc_records"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_mark_qc_record_factory"),
        UniqueConstraint("factory_id", "created_by", "request_id", "slot", name="uq_mark_qc_submission"),
        ForeignKeyConstraint(["template_id", "factory_id"],
                             ["carton_mark_templates.id", "carton_mark_templates.factory_id"],
                             name="fk_mark_qc_template_factory"),
        ForeignKeyConstraint(["corrects_record_id", "factory_id"],
                             ["carton_mark_qc_records.id", "carton_mark_qc_records.factory_id"],
                             name="fk_mark_qc_correction_factory"),
        CheckConstraint("slot >= 0 AND template_version >= 1", name="ck_mark_qc_version_slot"),
        Index("ix_mark_qc_factory_created", "factory_id", "created_at", "id"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    template_id: Mapped[str] = mapped_column(String(96))
    template_version: Mapped[int] = mapped_column(Integer)
    template_snapshot_json: Mapped[str] = mapped_column(Text)
    customer_name: Mapped[str] = mapped_column(String(255))
    po: Mapped[str] = mapped_column(String(128))
    item: Mapped[str] = mapped_column(String(128))
    contract_number: Mapped[str] = mapped_column(String(128))
    pdf_sha256: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))
    slot: Mapped[int] = mapped_column(Integer)
    corrects_record_id: Mapped[str | None] = mapped_column(String(96), nullable=True)
    note: Mapped[str] = mapped_column(String(1000), default="")
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))


class CartonMarkQcPhoto(Base):
    __tablename__ = "carton_mark_qc_photos"
    __table_args__ = (
        ForeignKeyConstraint(["record_id", "factory_id"],
                             ["carton_mark_qc_records.id", "carton_mark_qc_records.factory_id"],
                             name="fk_mark_qc_photo_factory"),
        UniqueConstraint("record_id", "side", name="uq_mark_qc_photo_side"),
        CheckConstraint("side IN ('front', 'side') AND size_bytes > 0", name="ck_mark_qc_photo"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    side: Mapped[str] = mapped_column(String(16))
    file_name: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)


class CartonMarkQcEvent(Base):
    __tablename__ = "carton_mark_qc_events"
    __table_args__ = (
        ForeignKeyConstraint(["record_id", "factory_id"],
                             ["carton_mark_qc_records.id", "carton_mark_qc_records.factory_id"],
                             name="fk_mark_qc_event_factory"),
        UniqueConstraint("record_id", "revision", name="uq_mark_qc_event_revision"),
        UniqueConstraint("record_id", "actor_id", "request_id", name="uq_mark_qc_event_request"),
        CheckConstraint("revision >= 1", name="ck_mark_qc_event_revision"),
        CheckConstraint("kind IN ('AUTO_CHECK', 'REVIEW', 'VOID')", name="ck_mark_qc_event_kind"),
        CheckConstraint("status IN ('待复核', '核对通过', '发现异常', '已作废')", name="ck_mark_qc_event_status"),
    )
    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    record_id: Mapped[str] = mapped_column(String(96), index=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(24))
    status: Mapped[str] = mapped_column(String(16))
    result_json: Mapped[str] = mapped_column(Text, default="")
    error: Mapped[str] = mapped_column(String(1000), default="")
    note: Mapped[str] = mapped_column(String(1000), default="")
    actor_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))
    request_id: Mapped[str] = mapped_column(String(96))
    request_hash: Mapped[str] = mapped_column(String(64))


def _qc_evidence_guards(table, connection, **_kwargs):
    from sqlalchemy import text
    if connection.dialect.name == "sqlite":
        for action in ("update", "delete"):
            connection.execute(text(f"CREATE TRIGGER {table.name}_no_{action} BEFORE {action.upper()} ON {table.name} "
                                    "BEGIN SELECT RAISE(ABORT, 'QC evidence is append-only'); END"))
    elif connection.dialect.name == "postgresql":
        connection.execute(text("CREATE OR REPLACE FUNCTION carton_mark_qc_immutable() RETURNS trigger AS $$ "
                                "BEGIN RAISE EXCEPTION 'QC evidence is append-only'; END; $$ LANGUAGE plpgsql"))
        connection.execute(text(f"CREATE TRIGGER {table.name}_immutable BEFORE UPDATE OR DELETE ON {table.name} "
                                "FOR EACH ROW EXECUTE FUNCTION carton_mark_qc_immutable()"))


for _qc_model in (CartonMarkQcRecord, CartonMarkQcPhoto, CartonMarkQcEvent):
    event.listen(_qc_model.__table__, "after_create", _qc_evidence_guards)
