from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class QcCustomerConfig(Base):
    __tablename__ = "qc_customer_configs"
    __table_args__ = (
        UniqueConstraint(
            "factory_id", "customer_code", name="uq_qc_customer_config_factory_code"
        ),
        UniqueConstraint("id", "factory_id", name="uq_qc_customer_config_id_factory"),
        CheckConstraint("revision >= 1", name="ck_qc_customer_config_revision"),
        CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_qc_customer_config_status"),
        Index(
            "ix_qc_customer_config_factory_name",
            "factory_id",
            "customer_name",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    customer_code: Mapped[str] = mapped_column(String(64))
    customer_name: Mapped[str] = mapped_column(String(255))
    is_caixing: Mapped[bool] = mapped_column(Boolean, default=False)
    default_inspection_agency: Mapped[str] = mapped_column(String(255), default="")
    default_account_manager: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(16), default="ACTIVE")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    updated_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcScheduleImportBatch(Base):
    __tablename__ = "qc_schedule_import_batches"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_schedule_batch_id_factory"),
        UniqueConstraint(
            "factory_id",
            "preview_user_id",
            "preview_request_id",
            name="uq_qc_schedule_batch_preview_request",
        ),
        CheckConstraint(
            "status IN ('PREVIEW', 'PARTIALLY_CONFIRMED', 'CONFIRMED', 'REJECTED')",
            name="ck_qc_schedule_batch_status",
        ),
        CheckConstraint(
            "revision >= 1 AND source_size_bytes > 0 AND row_count >= 0 "
            "AND blocking_count >= 0",
            name="ck_qc_schedule_batch_counts",
        ),
        Index(
            "ix_qc_schedule_batch_factory_week_created",
            "factory_id",
            "week_key",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    week_key: Mapped[str] = mapped_column(String(10))
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_file_sha256: Mapped[str] = mapped_column(String(64))
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    parser_version: Mapped[str] = mapped_column(String(64), default="qc-schedule-v1")
    status: Mapped[str] = mapped_column(String(32), default="PREVIEW")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    blocking_count: Mapped[int] = mapped_column(Integer, default=0)
    summary_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    preview_user_id: Mapped[str] = mapped_column(String(64))
    preview_request_id: Mapped[str] = mapped_column(String(128))
    preview_payload_sha256: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcScheduleImportRow(Base):
    __tablename__ = "qc_schedule_import_rows"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_schedule_row_id_factory"),
        UniqueConstraint("batch_id", "source_row_no", name="uq_qc_schedule_row_batch_no"),
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            ["qc_schedule_import_batches.id", "qc_schedule_import_batches.factory_id"],
            name="fk_qc_schedule_row_batch_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint("source_row_no >= 1", name="ck_qc_schedule_row_no"),
        CheckConstraint(
            "match_status IN ('NEW', 'EXACT', 'MULTIPLE_MATCHES', 'INVALID')",
            name="ck_qc_schedule_row_match_status",
        ),
        CheckConstraint(
            "decision_status IN ('PENDING', 'UPDATE', 'KEEP', 'CREATE', 'SKIP', 'UNCHANGED')",
            name="ck_qc_schedule_row_decision_status",
        ),
        Index(
            "ix_qc_schedule_row_candidate_key",
            "factory_id",
            "sales_contract_no",
            "customer_item_no",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(96))
    source_row_no: Mapped[int] = mapped_column(Integer)
    customer_name: Mapped[str] = mapped_column(String(255), default="")
    sales_contract_no: Mapped[str] = mapped_column(String(128), default="")
    customer_item_no: Mapped[str] = mapped_column(String(128), default="")
    customer_po_no: Mapped[str] = mapped_column(String(128), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    packing: Mapped[str] = mapped_column(String(255), default="")
    carton_count: Mapped[str] = mapped_column(String(64), default="")
    report_status: Mapped[str] = mapped_column(String(128), default="")
    production_department: Mapped[str] = mapped_column(String(128), default="")
    export_country_code: Mapped[str] = mapped_column(String(16), default="")
    shipment_date: Mapped[str] = mapped_column(String(10), default="")
    planned_inspection_date: Mapped[str] = mapped_column(String(10), default="")
    inspection_agency: Mapped[str] = mapped_column(String(255), default="")
    account_manager: Mapped[str] = mapped_column(String(128), default="")
    match_status: Mapped[str] = mapped_column(String(32))
    candidate_order_ids_json: Mapped[str] = mapped_column(Text, default="[]")
    candidate_order_revisions_json: Mapped[str] = mapped_column(Text, default="{}")
    changes_json: Mapped[str] = mapped_column(Text, default="[]")
    validation_errors_json: Mapped[str] = mapped_column(Text, default="[]")
    decision_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    linked_order_id: Mapped[str] = mapped_column(String(96), default="")
    raw_json: Mapped[str] = mapped_column(Text, default="{}")


class QcInspectionOrder(Base):
    __tablename__ = "qc_inspection_orders"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_inspection_order_id_factory"),
        UniqueConstraint(
            "factory_id", "inspection_no", name="uq_qc_inspection_order_factory_no"
        ),
        CheckConstraint("length(trim(customer_po_no)) > 0", name="ck_qc_inspection_order_po"),
        CheckConstraint("quantity > 0", name="ck_qc_inspection_order_quantity"),
        CheckConstraint("revision >= 1", name="ck_qc_inspection_order_revision"),
        CheckConstraint(
            "source_type IN ('SCHEDULE_IMPORT', 'MANUAL')",
            name="ck_qc_inspection_order_source_type",
        ),
        CheckConstraint(
            "status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')",
            name="ck_qc_inspection_order_status",
        ),
        CheckConstraint(
            "inspection_result IN ('PENDING', 'PASS', 'FAIL', 'REJECTED', "
            "'CONDITIONAL_PASS', 'CANCELLED')",
            name="ck_qc_inspection_order_result",
        ),
        Index(
            "ix_qc_inspection_order_candidate_match",
            "factory_id",
            "sales_contract_no",
            "customer_item_no",
        ),
        Index(
            "ix_qc_inspection_order_factory_week_date",
            "factory_id",
            "week_key",
            "planned_inspection_date",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_no: Mapped[str] = mapped_column(String(64))
    source_type: Mapped[str] = mapped_column(String(32))
    source_import_row_id: Mapped[str] = mapped_column(String(96), default="")
    week_key: Mapped[str] = mapped_column(String(10))
    customer_name: Mapped[str] = mapped_column(String(255))
    sales_contract_no: Mapped[str] = mapped_column(String(128))
    customer_item_no: Mapped[str] = mapped_column(String(128))
    customer_po_no: Mapped[str] = mapped_column(String(128))
    product_name: Mapped[str] = mapped_column(String(255), default="")
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    packing: Mapped[str] = mapped_column(String(255), default="")
    carton_count: Mapped[str] = mapped_column(String(64), default="")
    report_status: Mapped[str] = mapped_column(String(128), default="")
    production_department: Mapped[str] = mapped_column(String(128), default="")
    export_country_code: Mapped[str] = mapped_column(String(16), default="")
    shipment_date: Mapped[str] = mapped_column(String(10), default="")
    planned_inspection_date: Mapped[str] = mapped_column(String(10), default="")
    actual_inspection_date: Mapped[str] = mapped_column(String(10), default="")
    inspection_result: Mapped[str] = mapped_column(String(32), default="PENDING")
    inspection_agency: Mapped[str] = mapped_column(String(255), default="")
    account_manager: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="SCHEDULED")
    manual_has_problem: Mapped[bool] = mapped_column(Boolean, default=False)
    note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcInspectionEvent(Base):
    __tablename__ = "qc_inspection_events"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_event_id_factory"),
        UniqueConstraint(
            "inspection_order_id",
            "attempt_no",
            name="uq_qc_event_order_attempt",
        ),
        ForeignKeyConstraint(
            ["inspection_order_id", "factory_id"],
            ["qc_inspection_orders.id", "qc_inspection_orders.factory_id"],
            name="fk_qc_event_order_factory",
            ondelete="RESTRICT",
        ),
        CheckConstraint("attempt_no >= 1", name="ck_qc_event_attempt"),
        CheckConstraint("revision >= 1", name="ck_qc_event_revision"),
        CheckConstraint(
            "event_type IN ('CUSTOMER', 'THIRD_PARTY', 'LINE', 'SELF', "
            "'REINSPECTION', 'SAMPLE')",
            name="ck_qc_event_type",
        ),
        CheckConstraint(
            "inspection_result IN ('PENDING', 'PASS', 'FAIL', 'REJECTED', "
            "'CONDITIONAL_PASS', 'CANCELLED')",
            name="ck_qc_event_result",
        ),
        CheckConstraint(
            "document_status IN ('DRAFT', 'FINAL', 'REVISED')",
            name="ck_qc_event_document_status",
        ),
        CheckConstraint(
            "lot_size >= 0 AND sample_size >= 0 AND critical_defect_count >= 0 "
            "AND major_defect_count >= 0 AND minor_defect_count >= 0",
            name="ck_qc_event_counts",
        ),
        Index(
            "ix_qc_event_factory_date_result",
            "factory_id",
            "actual_inspection_date",
            "inspection_result",
        ),
        Index(
            "ix_qc_event_order_created",
            "inspection_order_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_order_id: Mapped[str] = mapped_column(String(96))
    attempt_no: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(32), default="CUSTOMER")
    actual_inspection_date: Mapped[str] = mapped_column(String(10))
    inspector_name: Mapped[str] = mapped_column(String(128), default="")
    inspection_agency: Mapped[str] = mapped_column(String(255), default="")
    inspection_location: Mapped[str] = mapped_column(String(255), default="")
    sampling_standard: Mapped[str] = mapped_column(String(128), default="")
    inspection_level: Mapped[str] = mapped_column(String(64), default="")
    aql_critical: Mapped[str] = mapped_column(String(32), default="")
    aql_major: Mapped[str] = mapped_column(String(32), default="")
    aql_minor: Mapped[str] = mapped_column(String(32), default="")
    lot_size: Mapped[int] = mapped_column(Integer, default=0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    critical_defect_count: Mapped[int] = mapped_column(Integer, default=0)
    major_defect_count: Mapped[int] = mapped_column(Integer, default=0)
    minor_defect_count: Mapped[int] = mapped_column(Integer, default=0)
    inspection_result: Mapped[str] = mapped_column(String(32), default="PENDING")
    document_status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    manual_has_problem: Mapped[bool] = mapped_column(Boolean, default=False)
    report_number: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcInspectionEventLine(Base):
    __tablename__ = "qc_inspection_event_lines"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_event_line_id_factory"),
        UniqueConstraint("inspection_event_id", "line_no", name="uq_qc_event_line_no"),
        ForeignKeyConstraint(
            ["inspection_event_id", "factory_id"],
            ["qc_inspection_events.id", "qc_inspection_events.factory_id"],
            name="fk_qc_event_line_event_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint("line_no >= 1", name="ck_qc_event_line_no"),
        CheckConstraint(
            "(order_quantity IS NULL OR order_quantity >= 0) AND "
            "(inspected_quantity IS NULL OR inspected_quantity >= 0)",
            name="ck_qc_event_line_quantities",
        ),
        Index("ix_qc_event_line_event", "inspection_event_id", "line_no"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_event_id: Mapped[str] = mapped_column(String(96))
    line_no: Mapped[int] = mapped_column(Integer)
    customer_po_no: Mapped[str] = mapped_column(String(128))
    release_no: Mapped[str] = mapped_column(String(128), default="")
    customer_item_no: Mapped[str] = mapped_column(String(128))
    internal_item_no: Mapped[str] = mapped_column(String(128), default="")
    batch_no: Mapped[str] = mapped_column(String(128), default="")
    date_code: Mapped[str] = mapped_column(String(128), default="")
    product_name: Mapped[str] = mapped_column(String(255), default="")
    order_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    inspected_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    packing: Mapped[str] = mapped_column(String(255), default="")
    carton_count: Mapped[str] = mapped_column(String(64), default="")
    upc_ean: Mapped[str] = mapped_column(String(64), default="")


class QcInspectionDefect(Base):
    __tablename__ = "qc_inspection_defects"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_defect_id_factory"),
        ForeignKeyConstraint(
            ["inspection_event_id", "factory_id"],
            ["qc_inspection_events.id", "qc_inspection_events.factory_id"],
            name="fk_qc_defect_event_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity >= 0", name="ck_qc_defect_quantity"),
        CheckConstraint(
            "severity IN ('CRITICAL', 'MAJOR', 'MINOR', 'OBSERVATION')",
            name="ck_qc_defect_severity",
        ),
        Index("ix_qc_defect_event_severity", "inspection_event_id", "severity"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_event_id: Mapped[str] = mapped_column(String(96))
    event_line_id: Mapped[str] = mapped_column(String(96), default="")
    category: Mapped[str] = mapped_column(String(128), default="")
    severity: Mapped[str] = mapped_column(String(32), default="OBSERVATION")
    quantity: Mapped[int] = mapped_column(Integer, default=0)
    defect_location: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text)
    production_department: Mapped[str] = mapped_column(String(128), default="")
    photo_reference: Mapped[str] = mapped_column(String(512), default="")


class QcInspectionTestResult(Base):
    __tablename__ = "qc_inspection_test_results"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_test_result_id_factory"),
        ForeignKeyConstraint(
            ["inspection_event_id", "factory_id"],
            ["qc_inspection_events.id", "qc_inspection_events.factory_id"],
            name="fk_qc_test_result_event_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "result IN ('PENDING', 'PASS', 'FAIL', 'NA')",
            name="ck_qc_test_result_result",
        ),
        CheckConstraint("sample_size >= 0", name="ck_qc_test_result_sample_size"),
        Index("ix_qc_test_result_event", "inspection_event_id", "test_item"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_event_id: Mapped[str] = mapped_column(String(96))
    test_item: Mapped[str] = mapped_column(String(255))
    method_standard: Mapped[str] = mapped_column(String(255), default="")
    specification: Mapped[str] = mapped_column(String(255), default="")
    measured_value: Mapped[str] = mapped_column(String(255), default="")
    unit: Mapped[str] = mapped_column(String(32), default="")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    result: Mapped[str] = mapped_column(String(16), default="PENDING")
    operator_name: Mapped[str] = mapped_column(String(128), default="")
    reviewer_name: Mapped[str] = mapped_column(String(128), default="")


class QcInspectionDisposition(Base):
    __tablename__ = "qc_inspection_dispositions"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_disposition_id_factory"),
        ForeignKeyConstraint(
            ["inspection_event_id", "factory_id"],
            ["qc_inspection_events.id", "qc_inspection_events.factory_id"],
            name="fk_qc_disposition_event_factory",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "disposition_type IN ('RETURN', 'REWORK', 'AOD', "
            "'CONCESSION_ACCEPTED', 'ON_HOLD', 'NO_ACTION')",
            name="ck_qc_disposition_type",
        ),
        CheckConstraint(
            "(return_quantity IS NULL OR return_quantity >= 0) AND "
            "(rework_quantity IS NULL OR rework_quantity >= 0)",
            name="ck_qc_disposition_quantities",
        ),
        Index(
            "ix_qc_disposition_event_type",
            "inspection_event_id",
            "disposition_type",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_event_id: Mapped[str] = mapped_column(String(96))
    disposition_type: Mapped[str] = mapped_column(String(32))
    return_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    rework_quantity: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    approved_by: Mapped[str] = mapped_column(String(128), default="")
    approved_date: Mapped[str] = mapped_column(String(10), default="")
    verification_result: Mapped[str] = mapped_column(Text, default="")


class QcInspectionReportPackage(Base):
    __tablename__ = "qc_inspection_report_packages"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_package_id_factory"),
        UniqueConstraint("factory_id", "package_no", name="uq_qc_package_factory_no"),
        ForeignKeyConstraint(
            ["inspection_event_id", "factory_id"],
            ["qc_inspection_events.id", "qc_inspection_events.factory_id"],
            name="fk_qc_package_event_factory",
            ondelete="RESTRICT",
        ),
        CheckConstraint("revision >= 1", name="ck_qc_package_revision"),
        CheckConstraint(
            "document_status IN ('DRAFT', 'FINAL', 'REVISED')",
            name="ck_qc_package_document_status",
        ),
        Index("ix_qc_package_event", "inspection_event_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    inspection_event_id: Mapped[str] = mapped_column(String(96))
    package_no: Mapped[str] = mapped_column(String(64))
    report_type: Mapped[str] = mapped_column(String(64), default="INTERNAL")
    external_report_no: Mapped[str] = mapped_column(String(128), default="")
    external_inspection_no: Mapped[str] = mapped_column(String(128), default="")
    issuing_organization: Mapped[str] = mapped_column(String(255), default="")
    document_status: Mapped[str] = mapped_column(String(16), default="DRAFT")
    issued_date: Mapped[str] = mapped_column(String(10), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcInspectionReportDocument(Base):
    __tablename__ = "qc_inspection_report_documents"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_document_id_factory"),
        ForeignKeyConstraint(
            ["package_id", "factory_id"],
            ["qc_inspection_report_packages.id", "qc_inspection_report_packages.factory_id"],
            name="fk_qc_document_package_factory",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes >= 0", name="ck_qc_document_size"),
        Index("ix_qc_document_package", "package_id", "created_at"),
        Index("ix_qc_document_sha256", "sha256"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    package_id: Mapped[str] = mapped_column(String(96))
    document_role: Mapped[str] = mapped_column(String(64), default="ATTACHMENT")
    original_file_name: Mapped[str] = mapped_column(String(255))
    original_relative_path: Mapped[str] = mapped_column(String(1024), default="")
    media_type: Mapped[str] = mapped_column(String(128), default="")
    extension: Mapped[str] = mapped_column(String(16), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str] = mapped_column(String(64))
    source_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[str] = mapped_column(String(40))


class QcInspectionProblem(Base):
    __tablename__ = "qc_inspection_problems"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_problem_id_factory"),
        UniqueConstraint("factory_id", "problem_no", name="uq_qc_problem_factory_no"),
        ForeignKeyConstraint(
            ["inspection_order_id", "factory_id"],
            ["qc_inspection_orders.id", "qc_inspection_orders.factory_id"],
            name="fk_qc_problem_order_factory",
            ondelete="RESTRICT",
        ),
        Index(
            "uq_qc_problem_auto_source",
            "inspection_order_id",
            "source_key",
            unique=True,
            sqlite_where=text("source_key != ''"),
            postgresql_where=text("source_key != ''"),
        ),
        CheckConstraint("revision >= 1", name="ck_qc_problem_revision"),
        CheckConstraint(
            "source_type IN ('AUTO_RESULT', 'MANUAL')",
            name="ck_qc_problem_source_type",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')",
            name="ck_qc_problem_status",
        ),
        Index("ix_qc_problem_factory_status", "factory_id", "status", "reported_date"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    problem_no: Mapped[str] = mapped_column(String(64))
    inspection_order_id: Mapped[str] = mapped_column(String(96))
    source_type: Mapped[str] = mapped_column(String(32), default="MANUAL")
    source_key: Mapped[str] = mapped_column(String(128), default="")
    status: Mapped[str] = mapped_column(String(32), default="DRAFT")
    category: Mapped[str] = mapped_column(String(128), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    return_reason: Mapped[str] = mapped_column(Text, default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    resolution: Mapped[str] = mapped_column(Text, default="")
    primary_responsible_person: Mapped[str] = mapped_column(String(128), default="")
    secondary_responsible_person: Mapped[str] = mapped_column(String(128), default="")
    reported_date: Mapped[str] = mapped_column(String(10), default="")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64))
    created_by_name: Mapped[str] = mapped_column(String(128), default="")
    updated_by: Mapped[str] = mapped_column(String(64))
    updated_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))
    updated_at: Mapped[str] = mapped_column(String(40))

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcScheduleChangeDecision(Base):
    __tablename__ = "qc_schedule_change_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            ["qc_schedule_import_batches.id", "qc_schedule_import_batches.factory_id"],
            name="fk_qc_schedule_decision_batch_factory",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["row_id", "factory_id"],
            ["qc_schedule_import_rows.id", "qc_schedule_import_rows.factory_id"],
            name="fk_qc_schedule_decision_row_factory",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "factory_id", "actor_user_id", "request_id", "row_id",
            name="uq_qc_schedule_decision_request_row",
        ),
        CheckConstraint(
            "action IN ('UPDATE', 'KEEP', 'CREATE', 'SKIP')",
            name="ck_qc_schedule_decision_action",
        ),
        Index("ix_qc_schedule_decision_batch_created", "batch_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(96))
    row_id: Mapped[str] = mapped_column(String(96))
    action: Mapped[str] = mapped_column(String(16))
    target_order_id: Mapped[str] = mapped_column(String(96), default="")
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")
    actor_user_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    request_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[str] = mapped_column(String(40))


class QcInspectionReport(Base):
    __tablename__ = "qc_inspection_reports"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_report_id_factory"),
        UniqueConstraint(
            "factory_id",
            "week_key",
            "report_type",
            "snapshot_revision",
            name="uq_qc_report_scope_snapshot_revision",
        ),
        CheckConstraint(
            "report_type IN ('CUSTOMER_SUMMARY', 'WEEKLY_STATISTICS', "
            "'HUAXING_CUSTOMER_WEEKLY_DETAIL', 'HUAXING_WEEKLY_AGGREGATE', "
            "'GROUP_SUMMARY', 'WEEKLY_INSPECTION_SCHEDULE', "
            "'DAILY_INSPECTION_LEDGER', 'WEEKLY_PROBLEM_DETAIL', "
            "'WEEKLY_RETURN_SUMMARY', 'INSPECTION_PASS_RATE', "
            "'ANNUAL_INSPECTION_STATISTICS', 'PRODUCT_QUALITY_LEDGER', "
            "'INSPECTION_DOCUMENT_INDEX', 'ORDER_INSPECTION_REPORT')",
            name="ck_qc_report_type",
        ),
        CheckConstraint("status IN ('GENERATED', 'FAILED')", name="ck_qc_report_status"),
        CheckConstraint(
            "snapshot_revision >= 1 AND artifact_size_bytes >= 0",
            name="ck_qc_report_counts",
        ),
        Index(
            "ix_qc_report_scope_week_type",
            "factory_id",
            "week_key",
            "report_type",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    week_key: Mapped[str] = mapped_column(String(10))
    period_mode: Mapped[str] = mapped_column(String(16), default="WEEK")
    period_key: Mapped[str] = mapped_column(String(16), default="")
    metric_version: Mapped[str] = mapped_column(String(32), default="qc-metrics-v1")
    inspection_order_id: Mapped[str] = mapped_column(String(96), default="")
    inspection_event_id: Mapped[str] = mapped_column(String(96), default="")
    report_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    is_formal_snapshot: Mapped[bool] = mapped_column(Boolean, default=False)
    snapshot_revision: Mapped[int] = mapped_column(Integer, default=1)
    source_revision_sha256: Mapped[str] = mapped_column(String(64))
    artifact_file_name: Mapped[str] = mapped_column(String(255), default="")
    artifact_media_type: Mapped[str] = mapped_column(String(128), default="")
    artifact_sha256: Mapped[str] = mapped_column(String(64), default="")
    artifact_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    artifact_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    generation_summary_json: Mapped[str] = mapped_column(Text, default="{}")
    error_message: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(64))
    requested_by_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))


class QcReportRenameBatch(Base):
    __tablename__ = "qc_report_rename_batches"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_rename_batch_id_factory"),
        UniqueConstraint(
            "factory_id", "preview_user_id", "preview_request_id",
            name="uq_qc_rename_preview_request",
        ),
        Index(
            "uq_qc_rename_execute_request",
            "factory_id",
            "execute_user_id",
            "execute_request_id",
            unique=True,
            sqlite_where=text("execute_request_id != ''"),
            postgresql_where=text("execute_request_id != ''"),
        ),
        CheckConstraint(
            "status IN ('PREVIEWED', 'EXECUTED')",
            name="ck_qc_rename_batch_status",
        ),
        CheckConstraint(
            "revision >= 1 AND group_count >= 1 AND source_file_count >= 1 "
            "AND source_size_bytes > 0",
            name="ck_qc_rename_batch_counts",
        ),
        Index("ix_qc_rename_batch_factory_created", "factory_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="PREVIEWED")
    rule_version: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    group_count: Mapped[int] = mapped_column(Integer)
    source_file_count: Mapped[int] = mapped_column(Integer)
    source_size_bytes: Mapped[int] = mapped_column(Integer)
    successful_group_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_group_count: Mapped[int] = mapped_column(Integer, default=0)
    preview_json: Mapped[str] = mapped_column(Text, default="{}")
    revision: Mapped[int] = mapped_column(Integer, default=1)
    preview_user_id: Mapped[str] = mapped_column(String(64))
    preview_request_id: Mapped[str] = mapped_column(String(128))
    preview_payload_sha256: Mapped[str] = mapped_column(String(64))
    execute_user_id: Mapped[str] = mapped_column(String(64), default="")
    execute_request_id: Mapped[str] = mapped_column(String(128), default="")
    archive_file_name: Mapped[str] = mapped_column(String(255), default="")
    archive_sha256: Mapped[str] = mapped_column(String(64), default="")
    archive_size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    archive_bytes: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    created_at: Mapped[str] = mapped_column(String(40))
    executed_at: Mapped[str] = mapped_column(String(40), default="")

    __mapper_args__ = {"version_id_col": revision, "version_id_generator": False}


class QcReportRenameGroup(Base):
    __tablename__ = "qc_report_rename_groups"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_rename_group_id_factory"),
        ForeignKeyConstraint(
            ["batch_id", "factory_id"],
            ["qc_report_rename_batches.id", "qc_report_rename_batches.factory_id"],
            name="fk_qc_rename_group_batch_factory",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("batch_id", "client_group_id", name="uq_qc_rename_group_client_id"),
        CheckConstraint("status IN ('READY', 'BLOCKED')", name="ck_qc_rename_group_status"),
        Index("ix_qc_rename_group_batch_status", "batch_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[str] = mapped_column(String(96))
    client_group_id: Mapped[str] = mapped_column(String(128))
    is_caixing: Mapped[bool] = mapped_column(Boolean, default=False)
    export_country: Mapped[str] = mapped_column(String(16), default="")
    report_number: Mapped[str] = mapped_column(String(128), default="")
    item_number: Mapped[str] = mapped_column(String(128))
    customer_po_no: Mapped[str] = mapped_column(String(128))
    quantity: Mapped[str] = mapped_column(String(64), default="")
    actual_inspection_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(16))
    base_name: Mapped[str] = mapped_column(String(255), default="")
    issues_json: Mapped[str] = mapped_column(Text, default="[]")


class QcReportRenameSourceFile(Base):
    __tablename__ = "qc_report_rename_source_files"
    __table_args__ = (
        UniqueConstraint("id", "factory_id", name="uq_qc_rename_source_id_factory"),
        ForeignKeyConstraint(
            ["group_id", "factory_id"],
            ["qc_report_rename_groups.id", "qc_report_rename_groups.factory_id"],
            name="fk_qc_rename_source_group_factory",
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0", name="ck_qc_rename_source_size"),
        Index("ix_qc_rename_source_group", "group_id", "sequence"),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    group_id: Mapped[str] = mapped_column(String(96))
    source_file_name: Mapped[str] = mapped_column(String(255))
    source_sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_bytes: Mapped[bytes] = mapped_column(LargeBinary)
    target_file_name: Mapped[str] = mapped_column(String(255), default="")


class QcInspectionAuditEvent(Base):
    __tablename__ = "qc_inspection_audit_events"
    __table_args__ = (
        Index(
            "ix_qc_inspection_audit_factory_entity",
            "factory_id",
            "entity_type",
            "entity_id",
            "created_at",
        ),
        Index(
            "ix_qc_inspection_audit_factory_event",
            "factory_id",
            "event_type",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(96))
    before_json: Mapped[str] = mapped_column(Text, default="{}")
    after_json: Mapped[str] = mapped_column(Text, default="{}")
    reason: Mapped[str] = mapped_column(Text, default="")
    request_id: Mapped[str] = mapped_column(String(128))
    actor_user_id: Mapped[str] = mapped_column(String(64))
    actor_name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[str] = mapped_column(String(40))


class QcInspectionIdempotencyRecord(Base):
    __tablename__ = "qc_inspection_idempotency_records"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "operation", "request_id",
            name="uq_qc_inspection_idempotency_request",
        ),
        CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_qc_idempotency_status"),
        Index(
            "ix_qc_idempotency_factory_created",
            "factory_id",
            "created_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(96), primary_key=True)
    factory_id: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(128))
    payload_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="COMPLETED")
    response_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[str] = mapped_column(String(40))
