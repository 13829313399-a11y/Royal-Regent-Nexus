"""create factory-scoped QC inspection operations

Revision ID: 20260812_0067
Revises: 20260812_0066
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260812_0067"
down_revision: str | Sequence[str] | None = "20260812_0066"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


PERMISSIONS = (
    ("qc_inspection:read", "读取 QC 验货资料", "read", "normal"),
    ("qc_inspection:schedule_write", "导入及确认 QC 排期", "operate", "normal"),
    ("qc_inspection:order_write", "维护 QC 临时验货单", "operate", "normal"),
    ("qc_inspection:result_write", "填写 QC 验货结果", "operate", "normal"),
    ("qc_inspection:problem_write", "维护 QC 验货问题", "operate", "normal"),
    ("qc_inspection:report_export", "生成及下载本厂 QC 报表", "operate", "high"),
    ("qc_inspection:report_rename_preview", "预览验货报告改名", "operate", "normal"),
    ("qc_inspection:report_rename_execute", "执行验货报告批量改名", "operate", "high"),
    ("qc_inspection:customer_manage", "维护 QC 客户配置", "operate", "high"),
    ("qc_inspection:audit_read", "读取本厂 QC 审计", "read", "high"),
    ("qc_inspection:factory_summary", "管理本厂正式 QC 汇总", "operate", "high"),
    ("qc_inspection:group_summary", "生成及下载集团 QC 汇总", "operate", "high"),
)
QC_OPERATOR_ROLES = (
    "position_qc_inspector",
    "position_qc_supervisor",
    "position_qc_manager",
)
QC_SUPERVISOR_ROLES = ("position_qc_supervisor", "position_qc_manager")


def _seed_permissions() -> None:
    permissions = sa.table(
        "auth_permissions",
        sa.column("id", sa.String(96)),
        sa.column("code", sa.String(128)),
        sa.column("name", sa.String(128)),
        sa.column("description", sa.Text()),
    )
    permission_metadata = sa.table(
        "auth_permission_metadata",
        sa.column("permission_id", sa.String(96)),
        sa.column("module_code", sa.String(64)),
        sa.column("action", sa.String(64)),
        sa.column("risk_level", sa.String(32)),
        sa.column("access_kind", sa.String(16)),
        sa.column("scope_type", sa.String(32)),
        sa.column("status", sa.String(32)),
        sa.column("sort_order", sa.Integer()),
        sa.column("created_at", sa.String(32)),
        sa.column("updated_at", sa.String(32)),
    )
    roles = sa.table(
        "auth_roles",
        sa.column("id", sa.String(64)),
    )
    role_permissions = sa.table(
        "auth_role_permissions",
        sa.column("id", sa.String(128)),
        sa.column("role_id", sa.String(64)),
        sa.column("permission_id", sa.String(96)),
    )
    timestamp = "2026-08-12 00:00:00"
    operator_actions = {
        "read",
        "schedule_write",
        "order_write",
        "result_write",
        "problem_write",
        "report_export",
        "report_rename_preview",
        "report_rename_execute",
    }
    supervisor_actions = {"customer_manage", "audit_read", "factory_summary"}
    for sort_offset, (code, name, access_kind, risk_level) in enumerate(PERMISSIONS):
        permission_id = f"perm-{code.replace(':', '-')}"
        action = code.partition(":")[2]
        permission_lookup = permissions.alias("existing_permission")
        op.execute(
            permissions.insert().from_select(
                ["id", "code", "name", "description"],
                sa.select(
                    op.inline_literal(permission_id, type_=sa.String(96)),
                    op.inline_literal(code, type_=sa.String(128)),
                    op.inline_literal(name, type_=sa.String(128)),
                    op.inline_literal("QC 验货运营中心权限", type_=sa.Text()),
                ).where(
                    ~sa.exists().where(
                        permission_lookup.c.code
                        == op.inline_literal(code, type_=sa.String(128))
                    )
                ),
            )
        )
        permission = permissions.alias("permission")
        metadata_lookup = permission_metadata.alias("metadata")
        op.execute(
            permission_metadata.insert().from_select(
                [
                    "permission_id",
                    "module_code",
                    "action",
                    "risk_level",
                    "access_kind",
                    "scope_type",
                    "status",
                    "sort_order",
                    "created_at",
                    "updated_at",
                ],
                sa.select(
                    permission.c.id,
                    op.inline_literal("qc_inspection", type_=sa.String(64)),
                    op.inline_literal(action, type_=sa.String(64)),
                    op.inline_literal(risk_level, type_=sa.String(32)),
                    op.inline_literal(access_kind, type_=sa.String(16)),
                    op.inline_literal("factory_department", type_=sa.String(32)),
                    op.inline_literal("active", type_=sa.String(32)),
                    op.inline_literal(1200 + sort_offset, type_=sa.Integer()),
                    op.inline_literal(timestamp, type_=sa.String(32)),
                    op.inline_literal(timestamp, type_=sa.String(32)),
                )
                .select_from(permission)
                .where(
                    permission.c.code
                    == op.inline_literal(code, type_=sa.String(128)),
                    ~sa.exists().where(
                        metadata_lookup.c.permission_id == permission.c.id
                    ),
                ),
            )
        )
        role_ids = (
            QC_OPERATOR_ROLES
            if action in operator_actions
            else QC_SUPERVISOR_ROLES
            if action in supervisor_actions
            else ()
        )
        for role_id in role_ids:
            role = roles.alias("role")
            permission = permissions.alias("permission")
            binding = role_permissions.alias("binding")
            op.execute(
                role_permissions.insert().from_select(
                    ["id", "role_id", "permission_id"],
                    sa.select(
                        op.inline_literal(
                            f"{role_id}:{permission_id}", type_=sa.String(128)
                        ),
                        role.c.id,
                        permission.c.id,
                    )
                    .select_from(
                        role.join(
                            permission,
                            permission.c.code
                            == op.inline_literal(code, type_=sa.String(128)),
                        )
                    )
                    .where(
                        role.c.id
                        == op.inline_literal(role_id, type_=sa.String(64)),
                        ~sa.exists().where(
                            binding.c.role_id == role.c.id,
                            binding.c.permission_id == permission.c.id,
                        ),
                    ),
                )
            )


def _create_append_only_audit_guards() -> None:
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            CREATE TRIGGER trg_qc_inspection_audit_no_update
            BEFORE UPDATE ON qc_inspection_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'QC inspection audit events are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_qc_inspection_audit_no_delete
            BEFORE DELETE ON qc_inspection_audit_events
            BEGIN
              SELECT RAISE(ABORT, 'QC inspection audit events are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_qc_schedule_decision_no_update
            BEFORE UPDATE ON qc_schedule_change_decisions
            BEGIN
              SELECT RAISE(ABORT, 'QC schedule decisions are append-only');
            END
            """
        )
        op.execute(
            """
            CREATE TRIGGER trg_qc_schedule_decision_no_delete
            BEFORE DELETE ON qc_schedule_change_decisions
            BEGIN
              SELECT RAISE(ABORT, 'QC schedule decisions are append-only');
            END
            """
        )
    elif dialect == "postgresql":
        op.execute(
            """
            CREATE FUNCTION reject_qc_append_only_mutation() RETURNS trigger AS $$
            BEGIN
              RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        for table_name, trigger_name in (
            ("qc_inspection_audit_events", "trg_qc_inspection_audit_immutable"),
            ("qc_schedule_change_decisions", "trg_qc_schedule_decision_immutable"),
        ):
            op.execute(
                f"""
                CREATE TRIGGER {trigger_name}
                BEFORE UPDATE OR DELETE ON {table_name}
                FOR EACH ROW EXECUTE FUNCTION reject_qc_append_only_mutation()
                """
            )


def upgrade() -> None:
    op.create_table(
        "qc_customer_configs",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("customer_code", sa.String(64), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("is_caixing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_inspection_agency", sa.String(255), nullable=False, server_default=""),
        sa.Column("default_account_manager", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("factory_id", "customer_code", name="uq_qc_customer_config_factory_code"),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_customer_config_id_factory"),
        sa.CheckConstraint("revision >= 1", name="ck_qc_customer_config_revision"),
        sa.CheckConstraint("status IN ('ACTIVE', 'INACTIVE')", name="ck_qc_customer_config_status"),
    )
    op.create_index("ix_qc_customer_config_factory_name", "qc_customer_configs", ["factory_id", "customer_name"])

    op.create_table(
        "qc_schedule_import_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("week_key", sa.String(10), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_file_sha256", sa.String(64), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("parser_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PREVIEW"),
        sa.Column("row_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("blocking_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preview_user_id", sa.String(64), nullable=False),
        sa.Column("preview_request_id", sa.String(128), nullable=False),
        sa.Column("preview_payload_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_schedule_batch_id_factory"),
        sa.UniqueConstraint("factory_id", "preview_user_id", "preview_request_id", name="uq_qc_schedule_batch_preview_request"),
        sa.CheckConstraint("status IN ('PREVIEW', 'PARTIALLY_CONFIRMED', 'CONFIRMED', 'REJECTED')", name="ck_qc_schedule_batch_status"),
        sa.CheckConstraint("revision >= 1 AND source_size_bytes > 0 AND row_count >= 0 AND blocking_count >= 0", name="ck_qc_schedule_batch_counts"),
    )
    op.create_index("ix_qc_schedule_batch_factory_week_created", "qc_schedule_import_batches", ["factory_id", "week_key", "created_at"])

    op.create_table(
        "qc_schedule_import_rows",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("source_row_no", sa.Integer(), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("sales_contract_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("customer_item_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("customer_po_no", sa.String(128), nullable=False, server_default=""),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=True),
        sa.Column("packing", sa.String(255), nullable=False, server_default=""),
        sa.Column("carton_count", sa.String(64), nullable=False, server_default=""),
        sa.Column("report_status", sa.String(128), nullable=False, server_default=""),
        sa.Column("production_department", sa.String(128), nullable=False, server_default=""),
        sa.Column("export_country_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("shipment_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("planned_inspection_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("inspection_agency", sa.String(255), nullable=False, server_default=""),
        sa.Column("account_manager", sa.String(128), nullable=False, server_default=""),
        sa.Column("match_status", sa.String(32), nullable=False),
        sa.Column("candidate_order_ids_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("candidate_order_revisions_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("changes_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("validation_errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("decision_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("linked_order_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("raw_json", sa.Text(), nullable=False, server_default="{}"),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_schedule_row_id_factory"),
        sa.UniqueConstraint("batch_id", "source_row_no", name="uq_qc_schedule_row_batch_no"),
        sa.ForeignKeyConstraint(["batch_id", "factory_id"], ["qc_schedule_import_batches.id", "qc_schedule_import_batches.factory_id"], name="fk_qc_schedule_row_batch_factory", ondelete="CASCADE"),
        sa.CheckConstraint("source_row_no >= 1", name="ck_qc_schedule_row_no"),
        sa.CheckConstraint("match_status IN ('NEW', 'EXACT', 'MULTIPLE_MATCHES', 'INVALID')", name="ck_qc_schedule_row_match_status"),
        sa.CheckConstraint("decision_status IN ('PENDING', 'UPDATE', 'KEEP', 'CREATE', 'SKIP', 'UNCHANGED')", name="ck_qc_schedule_row_decision_status"),
    )
    op.create_index("ix_qc_schedule_row_candidate_key", "qc_schedule_import_rows", ["factory_id", "sales_contract_no", "customer_item_no"])

    op.create_table(
        "qc_inspection_orders",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("inspection_no", sa.String(64), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_import_row_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("week_key", sa.String(10), nullable=False),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("sales_contract_no", sa.String(128), nullable=False),
        sa.Column("customer_item_no", sa.String(128), nullable=False),
        sa.Column("customer_po_no", sa.String(128), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("quantity", sa.Numeric(18, 4), nullable=False),
        sa.Column("packing", sa.String(255), nullable=False, server_default=""),
        sa.Column("carton_count", sa.String(64), nullable=False, server_default=""),
        sa.Column("report_status", sa.String(128), nullable=False, server_default=""),
        sa.Column("production_department", sa.String(128), nullable=False, server_default=""),
        sa.Column("export_country_code", sa.String(16), nullable=False, server_default=""),
        sa.Column("shipment_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("planned_inspection_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("actual_inspection_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("inspection_result", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("inspection_agency", sa.String(255), nullable=False, server_default=""),
        sa.Column("account_manager", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="SCHEDULED"),
        sa.Column("manual_has_problem", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("note", sa.Text(), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_inspection_order_id_factory"),
        sa.UniqueConstraint("factory_id", "inspection_no", name="uq_qc_inspection_order_factory_no"),
        sa.CheckConstraint("length(trim(customer_po_no)) > 0", name="ck_qc_inspection_order_po"),
        sa.CheckConstraint("quantity > 0", name="ck_qc_inspection_order_quantity"),
        sa.CheckConstraint("revision >= 1", name="ck_qc_inspection_order_revision"),
        sa.CheckConstraint("source_type IN ('SCHEDULE_IMPORT', 'MANUAL')", name="ck_qc_inspection_order_source_type"),
        sa.CheckConstraint("status IN ('SCHEDULED', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED')", name="ck_qc_inspection_order_status"),
        sa.CheckConstraint("inspection_result IN ('PENDING', 'PASS', 'FAIL', 'REJECTED', 'CONDITIONAL_PASS', 'CANCELLED')", name="ck_qc_inspection_order_result"),
    )
    op.create_index("ix_qc_inspection_order_candidate_match", "qc_inspection_orders", ["factory_id", "sales_contract_no", "customer_item_no"])
    op.create_index("ix_qc_inspection_order_factory_week_date", "qc_inspection_orders", ["factory_id", "week_key", "planned_inspection_date"])

    op.create_table(
        "qc_inspection_problems",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("problem_no", sa.String(64), nullable=False),
        sa.Column("inspection_order_id", sa.String(96), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("source_key", sa.String(128), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="DRAFT"),
        sa.Column("category", sa.String(128), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("return_reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("corrective_action", sa.Text(), nullable=False, server_default=""),
        sa.Column("resolution", sa.Text(), nullable=False, server_default=""),
        sa.Column("primary_responsible_person", sa.String(128), nullable=False, server_default=""),
        sa.Column("secondary_responsible_person", sa.String(128), nullable=False, server_default=""),
        sa.Column("reported_date", sa.String(10), nullable=False, server_default=""),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(64), nullable=False),
        sa.Column("created_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("updated_by", sa.String(64), nullable=False),
        sa.Column("updated_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_problem_id_factory"),
        sa.UniqueConstraint("factory_id", "problem_no", name="uq_qc_problem_factory_no"),
        sa.ForeignKeyConstraint(["inspection_order_id", "factory_id"], ["qc_inspection_orders.id", "qc_inspection_orders.factory_id"], name="fk_qc_problem_order_factory", ondelete="RESTRICT"),
        sa.CheckConstraint("revision >= 1", name="ck_qc_problem_revision"),
        sa.CheckConstraint("source_type IN ('AUTO_RESULT', 'MANUAL')", name="ck_qc_problem_source_type"),
        sa.CheckConstraint("status IN ('DRAFT', 'OPEN', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'CANCELLED')", name="ck_qc_problem_status"),
    )
    op.create_index("uq_qc_problem_auto_source", "qc_inspection_problems", ["inspection_order_id", "source_key"], unique=True, sqlite_where=sa.text("source_key != ''"), postgresql_where=sa.text("source_key != ''"))
    op.create_index("ix_qc_problem_factory_status", "qc_inspection_problems", ["factory_id", "status", "reported_date"])

    op.create_table(
        "qc_schedule_change_decisions",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("row_id", sa.String(96), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("target_order_id", sa.String(96), nullable=False, server_default=""),
        sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.ForeignKeyConstraint(["batch_id", "factory_id"], ["qc_schedule_import_batches.id", "qc_schedule_import_batches.factory_id"], name="fk_qc_schedule_decision_batch_factory", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["row_id", "factory_id"], ["qc_schedule_import_rows.id", "qc_schedule_import_rows.factory_id"], name="fk_qc_schedule_decision_row_factory", ondelete="RESTRICT"),
        sa.UniqueConstraint("factory_id", "actor_user_id", "request_id", "row_id", name="uq_qc_schedule_decision_request_row"),
        sa.CheckConstraint("action IN ('UPDATE', 'KEEP', 'CREATE', 'SKIP')", name="ck_qc_schedule_decision_action"),
    )
    op.create_index("ix_qc_schedule_decision_batch_created", "qc_schedule_change_decisions", ["batch_id", "created_at"])

    op.create_table(
        "qc_inspection_reports",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("week_key", sa.String(10), nullable=False),
        sa.Column("report_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("is_formal_snapshot", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("snapshot_revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("source_revision_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("artifact_media_type", sa.String(128), nullable=False, server_default=""),
        sa.Column("artifact_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("artifact_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("artifact_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("generation_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=False, server_default=""),
        sa.Column("requested_by", sa.String(64), nullable=False),
        sa.Column("requested_by_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_report_id_factory"),
        sa.UniqueConstraint("factory_id", "week_key", "report_type", "snapshot_revision", name="uq_qc_report_scope_snapshot_revision"),
        sa.CheckConstraint("report_type IN ('CUSTOMER_SUMMARY', 'WEEKLY_STATISTICS', 'HUAXING_CUSTOMER_WEEKLY_DETAIL', 'HUAXING_WEEKLY_AGGREGATE', 'GROUP_SUMMARY')", name="ck_qc_report_type"),
        sa.CheckConstraint("status IN ('GENERATED', 'FAILED')", name="ck_qc_report_status"),
        sa.CheckConstraint("snapshot_revision >= 1 AND artifact_size_bytes >= 0", name="ck_qc_report_counts"),
    )
    op.create_index("ix_qc_report_scope_week_type", "qc_inspection_reports", ["factory_id", "week_key", "report_type", "created_at"])

    op.create_table(
        "qc_report_rename_batches",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="PREVIEWED"),
        sa.Column("rule_version", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("group_count", sa.Integer(), nullable=False),
        sa.Column("source_file_count", sa.Integer(), nullable=False),
        sa.Column("source_size_bytes", sa.Integer(), nullable=False),
        sa.Column("successful_group_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_group_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("preview_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("preview_user_id", sa.String(64), nullable=False),
        sa.Column("preview_request_id", sa.String(128), nullable=False),
        sa.Column("preview_payload_sha256", sa.String(64), nullable=False),
        sa.Column("execute_user_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("execute_request_id", sa.String(128), nullable=False, server_default=""),
        sa.Column("archive_file_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("archive_sha256", sa.String(64), nullable=False, server_default=""),
        sa.Column("archive_size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("archive_bytes", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("executed_at", sa.String(40), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_rename_batch_id_factory"),
        sa.UniqueConstraint("factory_id", "preview_user_id", "preview_request_id", name="uq_qc_rename_preview_request"),
        sa.CheckConstraint("status IN ('PREVIEWED', 'EXECUTED')", name="ck_qc_rename_batch_status"),
        sa.CheckConstraint("revision >= 1 AND group_count >= 1 AND source_file_count >= 1 AND source_size_bytes > 0", name="ck_qc_rename_batch_counts"),
    )
    op.create_index("uq_qc_rename_execute_request", "qc_report_rename_batches", ["factory_id", "execute_user_id", "execute_request_id"], unique=True, sqlite_where=sa.text("execute_request_id != ''"), postgresql_where=sa.text("execute_request_id != ''"))
    op.create_index("ix_qc_rename_batch_factory_created", "qc_report_rename_batches", ["factory_id", "created_at"])

    op.create_table(
        "qc_report_rename_groups",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("batch_id", sa.String(96), nullable=False),
        sa.Column("client_group_id", sa.String(128), nullable=False),
        sa.Column("is_caixing", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("export_country", sa.String(16), nullable=False, server_default=""),
        sa.Column("report_number", sa.String(128), nullable=False, server_default=""),
        sa.Column("item_number", sa.String(128), nullable=False),
        sa.Column("customer_po_no", sa.String(128), nullable=False),
        sa.Column("quantity", sa.String(64), nullable=False, server_default=""),
        sa.Column("actual_inspection_date", sa.String(10), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("base_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("issues_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_rename_group_id_factory"),
        sa.ForeignKeyConstraint(["batch_id", "factory_id"], ["qc_report_rename_batches.id", "qc_report_rename_batches.factory_id"], name="fk_qc_rename_group_batch_factory", ondelete="RESTRICT"),
        sa.UniqueConstraint("batch_id", "client_group_id", name="uq_qc_rename_group_client_id"),
        sa.CheckConstraint("status IN ('READY', 'BLOCKED')", name="ck_qc_rename_group_status"),
    )
    op.create_index("ix_qc_rename_group_batch_status", "qc_report_rename_groups", ["batch_id", "status"])

    op.create_table(
        "qc_report_rename_source_files",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(96), nullable=False),
        sa.Column("source_file_name", sa.String(255), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("source_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("target_file_name", sa.String(255), nullable=False, server_default=""),
        sa.UniqueConstraint("id", "factory_id", name="uq_qc_rename_source_id_factory"),
        sa.ForeignKeyConstraint(["group_id", "factory_id"], ["qc_report_rename_groups.id", "qc_report_rename_groups.factory_id"], name="fk_qc_rename_source_group_factory", ondelete="RESTRICT"),
        sa.CheckConstraint("size_bytes > 0", name="ck_qc_rename_source_size"),
    )
    op.create_index("ix_qc_rename_source_group", "qc_report_rename_source_files", ["group_id", "sequence"])

    op.create_table(
        "qc_inspection_audit_events",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(96), nullable=False),
        sa.Column("before_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("after_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("actor_user_id", sa.String(64), nullable=False),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default=""),
        sa.Column("created_at", sa.String(40), nullable=False),
    )
    op.create_index("ix_qc_inspection_audit_factory_entity", "qc_inspection_audit_events", ["factory_id", "entity_type", "entity_id", "created_at"])
    op.create_index("ix_qc_inspection_audit_factory_event", "qc_inspection_audit_events", ["factory_id", "event_type", "created_at"])

    op.create_table(
        "qc_inspection_idempotency_records",
        sa.Column("id", sa.String(96), primary_key=True),
        sa.Column("factory_id", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("operation", sa.String(64), nullable=False),
        sa.Column("request_id", sa.String(128), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="COMPLETED"),
        sa.Column("response_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.UniqueConstraint("user_id", "operation", "request_id", name="uq_qc_inspection_idempotency_request"),
        sa.CheckConstraint("status IN ('COMPLETED', 'FAILED')", name="ck_qc_idempotency_status"),
    )
    op.create_index("ix_qc_idempotency_factory_created", "qc_inspection_idempotency_records", ["factory_id", "created_at"])

    _create_append_only_audit_guards()
    _seed_permissions()


def downgrade() -> None:
    connection = op.get_bind()
    permission_bindings = connection.execute(
        sa.text(
            """
            SELECT binding.role_id, permission.code
            FROM auth_role_permissions binding
            JOIN auth_permissions permission ON permission.id = binding.permission_id
            WHERE permission.code LIKE 'qc_inspection:%'
            """
        )
    ).all()
    operator_actions = {
        "read",
        "schedule_write",
        "order_write",
        "result_write",
        "problem_write",
        "report_export",
        "report_rename_preview",
        "report_rename_execute",
    }
    supervisor_actions = operator_actions | {
        "customer_manage",
        "audit_read",
        "factory_summary",
    }
    expected_bindings = {
        (role_id, f"qc_inspection:{action}")
        for role_id in QC_OPERATOR_ROLES
        for action in (
            supervisor_actions if role_id in QC_SUPERVISOR_ROLES else operator_actions
        )
    }
    # The built-in admin role follows the application permission catalog and is
    # not a user-created QC delegation. Every other binding must be preserved by
    # refusing a destructive downgrade.
    custom_bindings = [
        (role_id, code)
        for role_id, code in permission_bindings
        if role_id != "admin" and (role_id, code) not in expected_bindings
    ]
    override_count = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM auth_user_permission_overrides override_record
            JOIN auth_permissions permission ON permission.id = override_record.permission_id
            WHERE permission.code LIKE 'qc_inspection:%'
            """
        )
    ).scalar_one()
    if custom_bindings or override_count:
        raise RuntimeError(
            "20260812_0067 cannot be downgraded while custom QC authorization exists: "
            f"role_bindings={custom_bindings}, user_overrides={override_count}"
        )
    protected_tables = (
        "qc_customer_configs",
        "qc_schedule_import_batches",
        "qc_schedule_import_rows",
        "qc_inspection_orders",
        "qc_inspection_problems",
        "qc_schedule_change_decisions",
        "qc_inspection_reports",
        "qc_report_rename_batches",
        "qc_report_rename_groups",
        "qc_report_rename_source_files",
        "qc_inspection_audit_events",
        "qc_inspection_idempotency_records",
    )
    populated = [
        table_name
        for table_name in protected_tables
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    ]
    if populated:
        raise RuntimeError(
            "20260812_0067 cannot be downgraded after QC inspection data exists: "
            + ",".join(populated)
        )
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for trigger_name in (
            "trg_qc_inspection_audit_no_update",
            "trg_qc_inspection_audit_no_delete",
            "trg_qc_schedule_decision_no_update",
            "trg_qc_schedule_decision_no_delete",
        ):
            op.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
    elif dialect == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS reject_qc_append_only_mutation() CASCADE")
    for table_name in (
        "qc_inspection_idempotency_records",
        "qc_inspection_audit_events",
        "qc_report_rename_source_files",
        "qc_report_rename_groups",
        "qc_report_rename_batches",
        "qc_inspection_reports",
        "qc_schedule_change_decisions",
        "qc_inspection_problems",
        "qc_inspection_orders",
        "qc_schedule_import_rows",
        "qc_schedule_import_batches",
        "qc_customer_configs",
    ):
        op.drop_table(table_name)
    for code, *_ in PERMISSIONS:
        permission_id = f"perm-{code.replace(':', '-')}"
        connection.execute(
            sa.text("DELETE FROM auth_role_permissions WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM auth_permission_metadata WHERE permission_id = :permission_id"),
            {"permission_id": permission_id},
        )
        connection.execute(
            sa.text("DELETE FROM auth_permissions WHERE id = :permission_id"),
            {"permission_id": permission_id},
        )
