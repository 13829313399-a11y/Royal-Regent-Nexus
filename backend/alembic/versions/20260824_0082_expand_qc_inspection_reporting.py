"""expand QC inspection events and report outputs

Revision ID: 20260824_0082
Revises: 20260820_0081
Create Date: 2026-08-24
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260824_0082"
down_revision: str | Sequence[str] | None = "20260821_0082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


REPORT_TYPES = (
    "'CUSTOMER_SUMMARY', 'WEEKLY_STATISTICS', "
    "'HUAXING_CUSTOMER_WEEKLY_DETAIL', 'HUAXING_WEEKLY_AGGREGATE', "
    "'GROUP_SUMMARY', 'WEEKLY_INSPECTION_SCHEDULE', "
    "'DAILY_INSPECTION_LEDGER', 'WEEKLY_PROBLEM_DETAIL', "
    "'WEEKLY_RETURN_SUMMARY', 'INSPECTION_PASS_RATE', "
    "'ANNUAL_INSPECTION_STATISTICS', 'PRODUCT_QUALITY_LEDGER', "
    "'INSPECTION_DOCUMENT_INDEX', 'ORDER_INSPECTION_REPORT'"
)


def upgrade() -> None:
    op.create_table(
        "qc_inspection_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_order_id", sa.String(96), nullable=False),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(32), nullable=False, server_default="CUSTOMER"),
        sa.Column("actual_inspection_date", sa.String(10), nullable=False),
        sa.Column("inspector_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("inspection_agency", sa.String(255), nullable=False, server_default=""),
        sa.Column("inspection_location", sa.String(255), nullable=False, server_default=""),
        sa.Column("sampling_standard", sa.String(128), nullable=False, server_default=""),
        sa.Column("inspection_level", sa.String(64), nullable=False, server_default=""),
        sa.Column("aql_critical", sa.String(32), nullable=False, server_default=""),
        sa.Column("aql_major", sa.String(32), nullable=False, server_default=""),
        sa.Column("aql_minor", sa.String(32), nullable=False, server_default=""),
        sa.Column("lot_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_defect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("major_defect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("minor_defect_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inspection_result", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("document_status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("manual_has_problem", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("report_number", sa.String(128), nullable=False, server_default=""),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_event_id_factory"),
        sa.UniqueConstraint("inspection_order_id", "attempt_no", name="uq_qc_event_order_attempt"),
        sa.ForeignKeyConstraint(["inspection_order_id", "factory_id"], ["qc_inspection_orders.id", "qc_inspection_orders.factory_id"], name="fk_qc_event_order_factory", ondelete="RESTRICT"),
        sa.CheckConstraint("attempt_no >= 1", name="ck_qc_event_attempt"),
        sa.CheckConstraint("revision >= 1", name="ck_qc_event_revision"),
        sa.CheckConstraint("event_type IN ('CUSTOMER', 'THIRD_PARTY', 'LINE', 'SELF', 'REINSPECTION', 'SAMPLE')", name="ck_qc_event_type"),
        sa.CheckConstraint("inspection_result IN ('PENDING', 'PASS', 'FAIL', 'REJECTED', 'CONDITIONAL_PASS', 'CANCELLED')", name="ck_qc_event_result"),
        sa.CheckConstraint("document_status IN ('DRAFT', 'FINAL', 'REVISED')", name="ck_qc_event_document_status"),
        sa.CheckConstraint("lot_size >= 0 AND sample_size >= 0 AND critical_defect_count >= 0 AND major_defect_count >= 0 AND minor_defect_count >= 0", name="ck_qc_event_counts"),
    )
    op.create_index("ix_qc_event_factory_date_result", "qc_inspection_events", ["factory_id", "actual_inspection_date", "inspection_result"])
    op.create_index("ix_qc_event_order_created", "qc_inspection_events", ["inspection_order_id", "created_at"])

    op.create_table(
        "qc_inspection_event_lines",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_event_id", sa.String(96), nullable=False),
        sa.Column("line_no", sa.Integer(), nullable=False),
        sa.Column("customer_po_no", sa.String(128), nullable=False),
        sa.Column("release_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("customer_item_no", sa.String(128), nullable=False),
        sa.Column("internal_item_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("batch_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("date_code", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("order_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("inspected_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("packing", sa.String(255), nullable=False, server_default=""),
        sa.Column("carton_count", sa.String(64), nullable=False, server_default=""),
        sa.Column("upc_ean", sa.String(64), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_event_line_id_factory"),
        sa.UniqueConstraint("inspection_event_id", "line_no", name="uq_qc_event_line_no"),
        sa.ForeignKeyConstraint(["inspection_event_id", "factory_id"], ["qc_inspection_events.id", "qc_inspection_events.factory_id"], name="fk_qc_event_line_event_factory", ondelete="CASCADE"),
        sa.CheckConstraint("line_no >= 1", name="ck_qc_event_line_no"),
        sa.CheckConstraint("(order_quantity IS NULL OR order_quantity >= 0) AND (inspected_quantity IS NULL OR inspected_quantity >= 0)", name="ck_qc_event_line_quantities"),
    )
    op.create_index("ix_qc_event_line_event", "qc_inspection_event_lines", ["inspection_event_id", "line_no"])

    op.create_table(
        "qc_inspection_defects",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_event_id", sa.String(96), nullable=False),
        sa.Column("event_line_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("category", sa.String(128), nullable=False, server_default=""),
        sa.Column("severity", sa.String(32), nullable=False, server_default="OBSERVATION"),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("defect_location", sa.String(255), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("production_department", sa.String(128), nullable=False, server_default=""),
        sa.Column("photo_reference", sa.String(512), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_defect_id_factory"),
        sa.ForeignKeyConstraint(["inspection_event_id", "factory_id"], ["qc_inspection_events.id", "qc_inspection_events.factory_id"], name="fk_qc_defect_event_factory", ondelete="CASCADE"),
        sa.CheckConstraint("quantity >= 0", name="ck_qc_defect_quantity"),
        sa.CheckConstraint("severity IN ('CRITICAL', 'MAJOR', 'MINOR', 'OBSERVATION')", name="ck_qc_defect_severity"),
    )
    op.create_index("ix_qc_defect_event_severity", "qc_inspection_defects", ["inspection_event_id", "severity"])

    op.create_table(
        "qc_inspection_test_results",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_event_id", sa.String(96), nullable=False),
        sa.Column("test_item", sa.String(255), nullable=False),
        sa.Column("method_standard", sa.String(255), nullable=False, server_default=""),
        sa.Column("specification", sa.String(255), nullable=False, server_default=""),
        sa.Column("measured_value", sa.String(255), nullable=False, server_default=""),
        sa.Column("unit", sa.String(32), nullable=False, server_default=""),
        sa.Column("sample_size", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("operator_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("reviewer_name", sa.String(128), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_test_result_id_factory"),
        sa.ForeignKeyConstraint(["inspection_event_id", "factory_id"], ["qc_inspection_events.id", "qc_inspection_events.factory_id"], name="fk_qc_test_result_event_factory", ondelete="CASCADE"),
        sa.CheckConstraint("result IN ('PENDING', 'PASS', 'FAIL', 'NA')", name="ck_qc_test_result_result"),
        sa.CheckConstraint("sample_size >= 0", name="ck_qc_test_result_sample_size"),
    )
    op.create_index("ix_qc_test_result_event", "qc_inspection_test_results", ["inspection_event_id", "test_item"])

    op.create_table(
        "qc_inspection_dispositions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_event_id", sa.String(96), nullable=False),
        sa.Column("disposition_type", sa.String(32), nullable=False),
        sa.Column("return_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("rework_quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("approved_by", sa.String(128), nullable=False, server_default=""),
        sa.Column("approved_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("verification_result", sa.Text(), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_disposition_id_factory"),
        sa.ForeignKeyConstraint(["inspection_event_id", "factory_id"], ["qc_inspection_events.id", "qc_inspection_events.factory_id"], name="fk_qc_disposition_event_factory", ondelete="CASCADE"),
        sa.CheckConstraint("disposition_type IN ('RETURN', 'REWORK', 'AOD', 'CONCESSION_ACCEPTED', 'ON_HOLD', 'NO_ACTION')", name="ck_qc_disposition_type"),
        sa.CheckConstraint("(return_quantity IS NULL OR return_quantity >= 0) AND (rework_quantity IS NULL OR rework_quantity >= 0)", name="ck_qc_disposition_quantities"),
    )
    op.create_index("ix_qc_disposition_event_type", "qc_inspection_dispositions", ["inspection_event_id", "disposition_type"])

    op.create_table(
        "qc_inspection_report_packages",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_event_id", sa.String(96), nullable=False),
        sa.Column("package_no", sa.String(64), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False, server_default="INTERNAL"),
        sa.Column("external_report_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("external_inspection_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("issuing_organization", sa.String(255), nullable=False, server_default=""),
        sa.Column("document_status", sa.String(16), nullable=False, server_default="DRAFT"),
        sa.Column("issued_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_package_id_factory"),
        sa.UniqueConstraint("factory_id", "package_no", name="uq_qc_package_factory_no"),
        sa.ForeignKeyConstraint(["inspection_event_id", "factory_id"], ["qc_inspection_events.id", "qc_inspection_events.factory_id"], name="fk_qc_package_event_factory", ondelete="RESTRICT"),
        sa.CheckConstraint("revision >= 1", name="ck_qc_package_revision"),
        sa.CheckConstraint("document_status IN ('DRAFT', 'FINAL', 'REVISED')", name="ck_qc_package_document_status"),
    )
    op.create_index("ix_qc_package_event", "qc_inspection_report_packages", ["inspection_event_id", "created_at"])

    op.create_table(
        "qc_inspection_report_documents",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("package_id", sa.String(96), nullable=False),
        sa.Column("document_role", sa.String(64), nullable=False, server_default="ATTACHMENT"),
        sa.Column("original_file_name", sa.String(255), nullable=False),
        sa.Column("original_relative_path", sa.String(1024), nullable=False, server_default=""),
        sa.Column("media_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("extension", sa.String(16), nullable=False, server_default=""),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("source_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_document_id_factory"),
        sa.ForeignKeyConstraint(["package_id", "factory_id"], ["qc_inspection_report_packages.id", "qc_inspection_report_packages.factory_id"], name="fk_qc_document_package_factory", ondelete="RESTRICT"),
        sa.CheckConstraint("size_bytes >= 0", name="ck_qc_document_size"),
    )
    op.create_index("ix_qc_document_package", "qc_inspection_report_documents", ["package_id", "created_at"])
    op.create_index("ix_qc_document_sha256", "qc_inspection_report_documents", ["sha256"])

    with op.batch_alter_table("qc_inspection_reports") as batch_op:
        batch_op.drop_constraint("ck_qc_report_type", type_="check")
        batch_op.add_column(sa.Column("period_mode", sa.String(16), nullable=False, server_default="WEEK"))
        batch_op.add_column(sa.Column("period_key", sa.String(16), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("metric_version", sa.String(32), nullable=False, server_default="qc-metrics-v1"))
        batch_op.add_column(sa.Column("inspection_order_id", sa.String(96), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("inspection_event_id", sa.String(96), nullable=False, server_default=""))
        batch_op.create_check_constraint("ck_qc_report_type", f"report_type IN ({REPORT_TYPES})")
    op.execute("UPDATE qc_inspection_reports SET period_key = week_key WHERE period_key = ''")


def downgrade() -> None:
    legacy_types = (
        "'CUSTOMER_SUMMARY', 'WEEKLY_STATISTICS', "
        "'HUAXING_CUSTOMER_WEEKLY_DETAIL', 'HUAXING_WEEKLY_AGGREGATE', "
        "'GROUP_SUMMARY'"
    )
    with op.batch_alter_table("qc_inspection_reports") as batch_op:
        batch_op.drop_constraint("ck_qc_report_type", type_="check")
        batch_op.create_check_constraint("ck_qc_report_type", f"report_type IN ({legacy_types})")
        batch_op.drop_column("inspection_event_id")
        batch_op.drop_column("inspection_order_id")
        batch_op.drop_column("metric_version")
        batch_op.drop_column("period_key")
        batch_op.drop_column("period_mode")

    op.drop_index("ix_qc_document_sha256", table_name="qc_inspection_report_documents")
    op.drop_index("ix_qc_document_package", table_name="qc_inspection_report_documents")
    op.drop_table("qc_inspection_report_documents")
    op.drop_index("ix_qc_package_event", table_name="qc_inspection_report_packages")
    op.drop_table("qc_inspection_report_packages")
    op.drop_index("ix_qc_disposition_event_type", table_name="qc_inspection_dispositions")
    op.drop_table("qc_inspection_dispositions")
    op.drop_index("ix_qc_test_result_event", table_name="qc_inspection_test_results")
    op.drop_table("qc_inspection_test_results")
    op.drop_index("ix_qc_defect_event_severity", table_name="qc_inspection_defects")
    op.drop_table("qc_inspection_defects")
    op.drop_index("ix_qc_event_line_event", table_name="qc_inspection_event_lines")
    op.drop_table("qc_inspection_event_lines")
    op.drop_index("ix_qc_event_order_created", table_name="qc_inspection_events")
    op.drop_index("ix_qc_event_factory_date_result", table_name="qc_inspection_events")
    op.drop_table("qc_inspection_events")
