import os
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    # Alembic offline SQL generation only needs metadata. Avoid importing the
    # configured PostgreSQL DBAPI so `alembic upgrade --sql` stays portable.
    if os.getenv("ALEMBIC_OFFLINE_METADATA_ONLY") == "1":
        return create_engine("sqlite://", future=True)

    database_url = settings.database_url

    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        sqlite_engine = create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(sqlite_engine, "connect")
        def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
            cursor = dbapi_connection.cursor()
            try:
                cursor.execute("PRAGMA foreign_keys=ON")
            finally:
                cursor.close()

        return sqlite_engine

    return create_engine(database_url, future=True)


engine = _create_engine()
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False
)

SQLITE_LEGACY_COLUMNS = {
    "auth_users": [
        ("avatar_png", "avatar_png BLOB"),
        ("avatar_version", "avatar_version VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
    "molding_sample_items": [
        ("production_machine", "production_machine VARCHAR(128) NOT NULL DEFAULT ''"),
        ("mold_dimensions", "mold_dimensions VARCHAR(128) NOT NULL DEFAULT ''"),
        (
            "mold_presence_status",
            "mold_presence_status VARCHAR(20) NOT NULL DEFAULT 'unknown'",
        ),
        ("material_components", "material_components JSON NOT NULL DEFAULT '[]'"),
        (
            "material_usage_type",
            "material_usage_type VARCHAR(20) NOT NULL DEFAULT 'production'",
        ),
        (
            "actual_material_cost_components",
            "actual_material_cost_components JSON NOT NULL DEFAULT '[]'",
        ),
    ],
    "molding_sample_audit_logs": [
        ("actor_user_id", "actor_user_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("actor_roles", "actor_roles TEXT NOT NULL DEFAULT ''"),
        ("factory_scope", "factory_scope VARCHAR(255) NOT NULL DEFAULT ''"),
    ],
    "molding_sample_sensitive_audit_logs": [
        ("actor_user_id", "actor_user_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("actor_roles", "actor_roles TEXT NOT NULL DEFAULT ''"),
        ("factory_scope", "factory_scope VARCHAR(255) NOT NULL DEFAULT ''"),
    ],
    "system_notifications": [
        ("target_department", "target_department VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
    "auth_permission_metadata": [
        ("access_kind", "access_kind VARCHAR(16) NOT NULL DEFAULT 'operate'"),
    ],
    "auth_role_metadata": [
        ("scope_mode", "scope_mode VARCHAR(32) NOT NULL DEFAULT 'own_factory'"),
    ],
    "internal_quotes": [
        (
            "initiator_department",
            "initiator_department VARCHAR(64) NOT NULL DEFAULT 'sales-business'",
        ),
        ("business_owner_id", "business_owner_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("business_owner_name", "business_owner_name VARCHAR(128) NOT NULL DEFAULT ''"),
        (
            "target_customer_price",
            "target_customer_price VARCHAR(128) NOT NULL DEFAULT '无'",
        ),
        ("target_date", "target_date VARCHAR(32) NOT NULL DEFAULT ''"),
        ("remark", "remark TEXT NOT NULL DEFAULT ''"),
        (
            "module_version",
            "module_version VARCHAR(32) NOT NULL DEFAULT 'legacy_rr2_compatible'",
        ),
        (
            "reference_snapshot_id",
            "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''",
        ),
        (
            "formula_version",
            "formula_version VARCHAR(64) NOT NULL DEFAULT 'legacy_rr2_compatible'",
        ),
        ("header_revision", "header_revision INTEGER NOT NULL DEFAULT 1"),
        (
            "cloned_from_quote_id",
            "cloned_from_quote_id VARCHAR(64) NOT NULL DEFAULT ''",
        ),
        ("archived_by", "archived_by VARCHAR(64) NOT NULL DEFAULT ''"),
        ("archived_at", "archived_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("archive_reason", "archive_reason TEXT NOT NULL DEFAULT ''"),
        (
            "final_release_status",
            "final_release_status VARCHAR(32) NOT NULL DEFAULT ''",
        ),
        (
            "final_submission_revision",
            "final_submission_revision INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "final_submission_manifest_json",
            "final_submission_manifest_json TEXT NOT NULL DEFAULT '{}'",
        ),
        ("final_submitted_by", "final_submitted_by VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "final_submitted_by_name",
            "final_submitted_by_name VARCHAR(128) NOT NULL DEFAULT ''",
        ),
        ("final_submitted_at", "final_submitted_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_reviewed_by", "final_reviewed_by VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "final_reviewed_by_name",
            "final_reviewed_by_name VARCHAR(128) NOT NULL DEFAULT ''",
        ),
        ("final_reviewed_at", "final_reviewed_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_review_comment", "final_review_comment TEXT NOT NULL DEFAULT ''"),
        ("final_release_revision", "final_release_revision INTEGER NOT NULL DEFAULT 0"),
        (
            "final_release_invalidated_at",
            "final_release_invalidated_at VARCHAR(32) NOT NULL DEFAULT ''",
        ),
        (
            "final_release_invalidation_reason",
            "final_release_invalidation_reason TEXT NOT NULL DEFAULT ''",
        ),
    ],
    "internal_quote_sections": [
        ("is_required", "is_required BOOLEAN NOT NULL DEFAULT 1"),
        (
            "calculation_status",
            "calculation_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
        ),
        ("calculation_hash", "calculation_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "calculation_formula_version",
            "calculation_formula_version VARCHAR(64) NOT NULL DEFAULT ''",
        ),
        (
            "calculation_reference_snapshot_id",
            "calculation_reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''",
        ),
        ("calculated_at", "calculated_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("dependency_hash", "dependency_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "dependency_status",
            "dependency_status VARCHAR(32) NOT NULL DEFAULT 'current'",
        ),
    ],
    "internal_quote_audit_logs": [
        ("factory_id", "factory_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("old_revision", "old_revision INTEGER"),
        ("new_revision", "new_revision INTEGER"),
        ("reason", "reason TEXT NOT NULL DEFAULT ''"),
        ("request_id", "request_id VARCHAR(96) NOT NULL DEFAULT ''"),
        ("ip_address", "ip_address VARCHAR(128) NOT NULL DEFAULT ''"),
    ],
    "internal_quote_section_revisions": [
        ("formula_version", "formula_version VARCHAR(64) NOT NULL DEFAULT ''"),
        ("input_hash", "input_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "reference_snapshot_id",
            "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''",
        ),
        ("dependency_hash", "dependency_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        ("warnings_json", "warnings_json TEXT NOT NULL DEFAULT '[]'"),
    ],
    "internal_quote_import_batches": [
        ("source_size_bytes", "source_size_bytes INTEGER NOT NULL DEFAULT 0"),
        (
            "preview_schema_version",
            "preview_schema_version VARCHAR(32) NOT NULL DEFAULT 'p3-v1'",
        ),
        ("target_revision", "target_revision INTEGER NOT NULL DEFAULT 0"),
        ("confirm_mode", "confirm_mode VARCHAR(16) NOT NULL DEFAULT ''"),
        ("confirmed_revision", "confirmed_revision INTEGER NOT NULL DEFAULT 0"),
    ],
    "internal_quote_export_files": [
        (
            "template_version",
            "template_version VARCHAR(64) NOT NULL DEFAULT 'internal-quote-p3-v1'",
        ),
        ("formula_version", "formula_version VARCHAR(64) NOT NULL DEFAULT ''"),
        (
            "reference_snapshot_id",
            "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''",
        ),
        ("header_revision", "header_revision INTEGER NOT NULL DEFAULT 0"),
        (
            "release_stage",
            "release_stage VARCHAR(32) NOT NULL DEFAULT 'p3_section_approved'",
        ),
        ("export_manifest_json", "export_manifest_json TEXT NOT NULL DEFAULT '{}'"),
    ],
}

MOLDING_SAMPLE_DISPATCH_REVISION = "20260720_0028"
MOLDING_SAMPLE_DISPATCH_PREVIOUS_REVISION = "20260720_0027"
MOLDING_SAMPLE_DISPATCH_REQUIRED_COLUMNS = {
    "molding_sample_orders": {
        "production_factory_id",
        "production_assigned_at",
        "production_assigned_by",
        "production_assignment_version",
    },
    "molding_sample_requisitions": {"factory_id"},
    "molding_sample_inventory_batches": {"factory_id"},
    "molding_sample_inventory_movements": {"factory_id"},
}
MOLDING_SAMPLE_DISPATCH_REQUIRED_TABLES = {"molding_sample_dispatch_logs"}
INTERNAL_QUOTE_CUSTOMER_REVISION = "20260721_0029"
INTERNAL_QUOTE_CUSTOMER_PREVIOUS_REVISION = "20260720_0028"
INTERNAL_QUOTE_CUSTOMER_TABLE = "internal_quote_customers"
INTERNAL_QUOTE_BASELINE_FREIGHT_REVISION = "20260723_0030"
INTERNAL_QUOTE_BASELINE_FREIGHT_PREVIOUS_REVISION = "20260721_0029"
INTERNAL_QUOTE_BASELINE_TABLE = "internal_quote_pricing_baselines"
INTERNAL_QUOTE_BASELINE_FREIGHT_COLUMN = "freight_routes_json"
THREE_D_PRINTING_REVISION = "20260917_0117"
THREE_D_PRINTING_PREVIOUS_REVISIONS = frozenset({"20260728_0039", "20260729_0040"})
THREE_D_PRINTING_V2_TABLES = {
    "three_d_printing_operations_items",
    "three_d_printing_sites", "three_d_printing_network_gateways",
    "three_d_printing_connector_instances", "three_d_printing_printer_connections",
    "three_d_printing_printer_state_events", "three_d_printing_material_aliases",
    "three_d_printing_migration_batches", "three_d_printing_migration_row_results",
}
THREE_D_PRINTING_V2_COLUMNS = {
    "three_d_printing_production_records": {
        "site_id", "device_job_key", "legacy_status", "run_status",
        "reconciliation_status", "data_quality_flags_json", "product_snapshot_json",
        "cost_profile_version", "calculated_cost_snapshot_json", "migration_batch_id", "source_system",
    },
    "three_d_printing_inventory_movements": {
        "idempotency_key", "movement_status", "reversal_of_movement_id", "reservation_id",
        "source_event_id", "migration_batch_id", "raw_material_name", "affects_balance",
    },
    "three_d_printing_printer_commands": {
        "connector_instance_id", "lease_id", "leased_until", "attempt_count", "next_attempt_at", "result_evidence_json",
    },
    "three_d_printing_printers": {"site_id"},
    "three_d_printing_product_images": {"legacy_sha256"},
    'three_d_printing_sites': {'timezone', 'name', 'updated_at', 'id', 'site_code', 'created_at', 'enabled', 'factory_id'},
    'three_d_printing_network_gateways': {'tunnel_address', 'packet_loss_percent', 'factory_id', 'advertised_cidr', 'status', 'site_id', 'last_error', 'config_revision', 'id', 'latency_ms', 'last_handshake_at', 'gateway_key', 'vpn_type'},
    'three_d_printing_connector_instances': {'capabilities_json', 'status', 'instance_id', 'site_id', 'last_error', 'id', 'started_at', 'last_seen_at', 'connector_key', 'leader_printer_count', 'version', 'factory_id'},
    'three_d_printing_printer_connections': {'last_disconnect_at', 'lan_host', 'printer_id', 'connection_revision', 'site_id', 'mqtt_port', 'leader_instance_id', 'leader_lease_id', 'leader_leased_until', 'connection_owner', 'credential_ref', 'certificate_fingerprint', 'connection_enabled', 'last_connect_at', 'factory_id', 'record_reconcile_enabled'},
    'three_d_printing_printer_state_events': {'connection_session_id', 'error_text', 'printer_id', 'machine_no', 'current_file', 'payload_version', 'raw_payload_json', 'observed_at', 'progress', 'id', 'temperatures_json', 'remaining_minutes', 'state', 'connector_instance_id', 'received_at', 'error_code', 'sequence', 'factory_id'},
    'three_d_printing_material_aliases': {'source', 'approved_by', 'raw_name', 'id', 'canonical_material_id', 'approved_at', 'normalized_name', 'factory_id'},
    'three_d_printing_migration_batches': {'image_count', 'checkpoint_json', 'started_at', 'source_updated_at_ms', 'source_sha256', 'summary_json', 'reconciliation_json', 'status', 'source_size_bytes', 'leased_until', 'id', 'error_code', 'factory_id', 'code_revision', 'migration_version', 'completed_at', 'site_id', 'image_bytes', 'source_system', 'lease_id', 'expected_counts_json'},
    'three_d_printing_migration_row_results': {'target_id', 'status', 'batch_id', 'updated_at', 'source_hash', 'id', 'legacy_id', 'error_code', 'entity_type', 'attempt_count', 'target_hash', 'factory_id'},
}
QC_INSPECTION_REVISION = "20260824_0082"
QC_INSPECTION_REQUIRED_TABLES = {
    "qc_customer_configs",
    "qc_schedule_import_batches",
    "qc_schedule_import_rows",
    "qc_inspection_orders",
    "qc_inspection_events",
    "qc_inspection_event_lines",
    "qc_inspection_defects",
    "qc_inspection_test_results",
    "qc_inspection_dispositions",
    "qc_inspection_report_packages",
    "qc_inspection_report_documents",
    "qc_inspection_problems",
    "qc_schedule_change_decisions",
    "qc_inspection_reports",
    "qc_report_rename_batches",
    "qc_report_rename_groups",
    "qc_report_rename_source_files",
    "qc_inspection_audit_events",
    "qc_inspection_idempotency_records",
}
CARTON_MARK_LIBRARY_REVISION = "20260819_0080"
CARTON_MARK_LIBRARY_REQUIRED_TABLES = {
    "carton_mark_customers",
    "carton_mark_templates",
    "carton_mark_documents",
}
def ensure_carton_mark_library_schema_ready() -> None:
    """Refuse to let create_all silently bypass the persistent library migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(CARTON_MARK_LIBRARY_REQUIRED_TABLES - table_names)
        if not missing:
            return
    raise RuntimeError(
        "检测到箱唛资料库尚未完整迁移 "
        f"{CARTON_MARK_LIBRARY_REVISION}；当前版本：{current_revision}；"
        f"缺少表：{', '.join(missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_qc_inspection_schema_ready() -> None:
    """Refuse to run a partially migrated QC inspection domain."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(QC_INSPECTION_REQUIRED_TABLES - table_names)
        if not missing:
            return
    raise RuntimeError(
        "检测到 QC 验货数据库尚未完整迁移 "
        f"{QC_INSPECTION_REVISION}；当前版本：{current_revision}；"
        f"缺少表：{', '.join(missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_molding_dispatch_schema_ready() -> None:
    """Refuse to mutate a pre-0028 database during application startup."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "molding_sample_orders" not in table_names:
            return

        missing_schema: list[str] = []
        if "alembic_version" in table_names:
            current_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
            if current_revision == MOLDING_SAMPLE_DISPATCH_PREVIOUS_REVISION:
                missing_schema.append(f"revision:{current_revision}")
        for (
            table_name,
            required_columns,
        ) in MOLDING_SAMPLE_DISPATCH_REQUIRED_COLUMNS.items():
            if table_name not in table_names:
                missing_schema.append(f"table:{table_name}")
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            missing_schema.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - existing_columns)
            )

        missing_schema.extend(
            f"table:{table_name}"
            for table_name in sorted(
                MOLDING_SAMPLE_DISPATCH_REQUIRED_TABLES - table_names
            )
        )
        if not missing_schema:
            return

    raise RuntimeError(
        "检测到啤办数据库尚未完成 Alembic 迁移 "
        f"{MOLDING_SAMPLE_DISPATCH_REVISION}；缺少："
        f"{', '.join(missing_schema)}。请先备份数据库并执行 Alembic 迁移 "
        f"{MOLDING_SAMPLE_DISPATCH_REVISION}，再启动应用。"
    )


def ensure_internal_quote_customer_schema_ready() -> None:
    """Refuse to let create_all bypass the factory-customer data migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "internal_quotes" not in table_names:
            return

        current_revision = None
        if "alembic_version" in table_names:
            current_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
        if (
            INTERNAL_QUOTE_CUSTOMER_TABLE in table_names
            and current_revision != INTERNAL_QUOTE_CUSTOMER_PREVIOUS_REVISION
        ):
            return

    missing = (
        f"revision:{current_revision}"
        if current_revision == INTERNAL_QUOTE_CUSTOMER_PREVIOUS_REVISION
        else f"table:{INTERNAL_QUOTE_CUSTOMER_TABLE}"
    )
    raise RuntimeError(
        "检测到内部报价数据库尚未完成厂区客户资料迁移 "
        f"{INTERNAL_QUOTE_CUSTOMER_REVISION}；缺少：{missing}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_internal_quote_baseline_freight_schema_ready() -> None:
    """Refuse to start an existing quote database before the freight-baseline migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if INTERNAL_QUOTE_BASELINE_TABLE not in table_names:
            return

        current_revision = None
        if "alembic_version" in table_names:
            current_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
        columns = {
            column["name"]
            for column in inspector.get_columns(INTERNAL_QUOTE_BASELINE_TABLE)
        }
        if (
            INTERNAL_QUOTE_BASELINE_FREIGHT_COLUMN in columns
            and current_revision != INTERNAL_QUOTE_BASELINE_FREIGHT_PREVIOUS_REVISION
        ):
            return

    missing = (
        f"revision:{current_revision}"
        if current_revision == INTERNAL_QUOTE_BASELINE_FREIGHT_PREVIOUS_REVISION
        else f"column:{INTERNAL_QUOTE_BASELINE_TABLE}.{INTERNAL_QUOTE_BASELINE_FREIGHT_COLUMN}"
    )
    raise RuntimeError(
        "检测到内部报价数据库尚未完成报价基数运费迁移 "
        f"{INTERNAL_QUOTE_BASELINE_FREIGHT_REVISION}；缺少：{missing}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_three_d_printing_schema_ready() -> None:
    """Reject partial/old schemas before create_all can disguise a missed migration."""
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "alembic_version" not in tables and not any(name.startswith("three_d_printing_") for name in tables):
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none() if "alembic_version" in tables else None
        missing = THREE_D_PRINTING_V2_TABLES - tables
        for table, required in THREE_D_PRINTING_V2_COLUMNS.items():
            if table not in tables:
                missing.add(table)
            else:
                missing.update(f"{table}.{name}" for name in required - {column["name"] for column in inspector.get_columns(table)})
    if not missing and current_revision not in THREE_D_PRINTING_PREVIOUS_REVISIONS:
        return
    raise RuntimeError(
        "检测到数据库尚未完成 3D 打印机管理迁移 "
        f"{THREE_D_PRINTING_REVISION}；当前版本：{current_revision}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_sqlite_legacy_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        for table_name, columns in SQLITE_LEGACY_COLUMNS.items():
            existing_columns = {
                row["name"]
                for row in connection.exec_driver_sql(
                    f"PRAGMA table_info({table_name})"
                ).mappings()
            }
            if not existing_columns:
                continue

            for column_name, column_ddl in columns:
                if column_name not in existing_columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}"
                    )

        # Adding the column defaults historical rows to the safe ``operate``
        # kind. Reconcile the known read-only permissions so an upgraded local
        # database does not silently lose cross-factory viewing access.
        permission_metadata_columns = {
            row["name"]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(auth_permission_metadata)"
            ).mappings()
        }
        permission_columns = {
            row["name"]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(auth_permissions)"
            ).mappings()
        }
        if (
            "access_kind" in permission_metadata_columns
            and {"id", "code"} <= permission_columns
        ):
            from app.services.iam_scope import READ_PERMISSION_CODES

            for permission_code in READ_PERMISSION_CODES:
                connection.exec_driver_sql(
                    "UPDATE auth_permission_metadata "
                    "SET access_kind = 'read' "
                    "WHERE permission_id = ("
                    "SELECT id FROM auth_permissions WHERE code = ?"
                    ")",
                    (permission_code,),
                )


def ensure_injection_v3_schema_ready() -> None:
    from app.models import injection_scheduling  # noqa: F401

    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = []
        for table in Base.metadata.sorted_tables:
            if not table.name.startswith("injection_v3_"):
                continue
            if table.name not in names:
                missing.append(table.name)
                continue
            columns = {c["name"] for c in inspector.get_columns(table.name)}
            missing.extend(f"{table.name}.{c.name}" for c in table.columns if c.name not in columns)
        if missing:
            raise RuntimeError(
                "注塑排产 V3 尚未迁移至 20260905_0100；请在备份与迁移演练后升级目标数据库。缺少："
                + ", ".join(missing)
            )


def ensure_carton_stocktake_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = []
        for name in ("carton_stocktakes", "carton_stocktake_lines"):
            if name not in names:
                missing.append(name)
            else:
                columns = {column["name"] for column in inspector.get_columns(name)}
                missing.extend(f"{name}.{column.name}" for column in Base.metadata.tables[name].columns if column.name not in columns)
        if missing:
            raise RuntimeError("库存盘点尚未迁移至 20260907_0102；请备份并完成迁移后启动。缺少：" + ", ".join(missing))


def ensure_carton_positions_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = [name for name in ("carton_locations", "carton_position_entries") if name not in names]
        for table, column in (("carton_receipt_lines", "location_allocations_json"), ("carton_inventory_movements", "issue_kind")):
            if table not in names or column not in {c["name"] for c in inspector.get_columns(table)}:
                missing.append(f"{table}.{column}")
        if missing:
            raise RuntimeError("分仓库存尚未迁移至 20260908_0103；请备份并完成迁移后启动。缺少：" + ", ".join(missing))


def ensure_carton_master_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = [name for name in ("carton_master_records", "carton_master_sources") if name not in names]
        for name, cols in (("carton_orders", ("master_config_id", "master_config_revision")), ("carton_locations", ("status", "revision")), ("carton_inventory_movements", ("workshop_id", "workshop_name"))):
            found = {c["name"] for c in inspector.get_columns(name)} if name in names else set()
            missing.extend(f"{name}.{c}" for c in cols if c not in found)
        if missing:
            raise RuntimeError("基础资料尚未迁移至 20260908_0104；请先备份并迁移。缺少：" + ", ".join(missing))


def ensure_carton_supplier_settlement_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = []
        name = "carton_supplier_settlements"
        if name not in names:
            missing.append(name)
        else:
            columns = {c["name"] for c in inspector.get_columns(name)}
            missing.extend(f"{name}.{c.name}" for c in Base.metadata.tables[name].columns if c.name not in columns)
        if "carton_receipts" not in names or "acceptance_date" not in {c["name"] for c in inspector.get_columns("carton_receipts")}:
            missing.append("carton_receipts.acceptance_date")
        if missing:
            raise RuntimeError("供应商月结尚未迁移至 20260909_0105；请先备份并迁移。缺少：" + ", ".join(missing))


def ensure_carton_explicit_quantity_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        required = {"carton_orders": ("product_order_quantity",), "carton_order_lines": ("usage_quantity",),
                    "carton_purchase_order_issues": ("before_product_quantity", "after_product_quantity", "product_quantity_delta")}
        missing = []
        for name, nullable_columns in required.items():
            columns = {c["name"]: c for c in inspector.get_columns(name)} if name in names else {}
            if name == "carton_orders" and "quantity_basis" not in columns:
                missing.append("carton_orders.quantity_basis")
            missing.extend(f"{name}.{column}" for column in nullable_columns if column not in columns or not columns[column]["nullable"])
        if missing:
            raise RuntimeError("历史订单显式纸品需求尚未迁移至 20260909_0106；请先备份并迁移。缺少：" + ", ".join(missing))


def ensure_carton_customer_po_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        if "carton_orders" not in names or "customer_po" not in {c["name"] for c in inspector.get_columns("carton_orders")}:
            raise RuntimeError("客户 PO 尚未迁移至 20260912_0108；请先备份数据库并执行迁移")


def ensure_document_tools_schema_ready() -> None:
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" not in names:
            return
        missing = []
        for name in ("document_tool_sources", "document_tool_jobs", "document_tool_artifacts", "document_tool_corrections"):
            if name not in names:
                missing.append(name)
            else:
                columns = {column["name"] for column in inspector.get_columns(name)}
                missing.extend(f"{name}.{column.name}" for column in Base.metadata.tables[name].columns if column.name not in columns)
        if missing:
            raise RuntimeError("文档工具尚未迁移至 20260908_0103_docs；请备份并迁移后启动。缺少：" + ", ".join(missing))


def ensure_collaborative_sheets_schema_ready() -> None:
    """Never create a new collaboration schema implicitly in an existing DB."""
    from app.models import collaborative_sheets  # noqa: F401
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if not names:
            return
        missing = []
        for name, table in Base.metadata.tables.items():
            if not name.startswith("collaborative_sheet"):
                continue
            if name not in names:
                missing.append(name)
            else:
                columns = {column["name"] for column in inspector.get_columns(name)}
                missing.extend(name + "." + column.name for column in table.columns if column.name not in columns)
        if missing:
            raise RuntimeError("协同填表需要迁移至 20261009_0121；请先备份并迁移。缺少：" + ", ".join(missing))


def init_db() -> None:
    from app.models import (
        spray_production,
        uv_printing,
        uv_finance,
        uv_ingest,
        uv_handover,
        document_tools,  # noqa: F401
        collaborative_sheets,  # noqa: F401
        auth,  # noqa: F401
        carton_mark,  # noqa: F401
        carton_procurement,  # noqa: F401
        carton_stocktake,  # noqa: F401
        carton_positions,
        carton_master,  # noqa: F401
        carton_supplier_settlement,  # noqa: F401
        customer_order,  # noqa: F401
        customer_order_ledger,  # noqa: F401
        internal_quote,  # noqa: F401
        injection_scheduling,  # noqa: F401
        molding_sample,  # noqa: F401
        pricing,  # noqa: F401
        qc_inspection,  # noqa: F401
        raw_material,  # noqa: F401
        three_d_printing,  # noqa: F401
    )
    from app.services.auth import seed_auth_defaults
    from app.services.carton_procurement import seed_carton_supplier_defaults
    from app.services.internal_quote_baseline import (
        seed_internal_quote_pricing_baseline_defaults,
    )
    from app.services.molding_sample import seed_molding_sample_defaults
    from app.services.raw_material import seed_raw_material_defaults
    from app.services.three_d_printing import seed_three_d_printing_defaults

    ensure_collaborative_sheets_schema_ready()
    ensure_molding_dispatch_schema_ready()
    ensure_internal_quote_customer_schema_ready()
    ensure_internal_quote_baseline_freight_schema_ready()
    ensure_three_d_printing_schema_ready()
    ensure_qc_inspection_schema_ready()
    ensure_carton_mark_library_schema_ready()
    ensure_injection_v3_schema_ready()
    ensure_carton_stocktake_schema_ready()
    ensure_carton_positions_schema_ready()
    ensure_carton_master_schema_ready()
    ensure_carton_supplier_settlement_schema_ready()
    ensure_carton_explicit_quantity_schema_ready()
    ensure_carton_customer_po_schema_ready()
    ensure_document_tools_schema_ready()
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" in names:
            missing = [name for name in Base.metadata.tables if name.startswith("order_ledger_") and name not in names]
            if missing:
                raise RuntimeError("客户订单台账需要迁移至 20260914_0112；请先备份并迁移。缺少：" + ", ".join(missing))
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if "alembic_version" in names:
            missing = [name for name in Base.metadata.tables if name.startswith("spray_") and name not in names]
            for table, column in [("spray_order_lines", "graph_route"),("spray_steps","predecessors"),("spray_tasks","shared_allocations"),("spray_resources","shared_requirements")]:
                if table in names and column not in {c["name"] for c in inspector.get_columns(table)}:
                    missing.append(table + "." + column)
            if missing:
                raise RuntimeError("喷油模块需要迁移至 20260911_0110；请先备份并迁移。缺少：" + ", ".join(missing))
    with engine.connect() as connection:
        inspector = inspect(connection)
        names = set(inspector.get_table_names())
        if settings.uv_printing_enabled and ("alembic_version" in names or any(name.startswith("uv_") for name in names)):
            missing = []
            for name, table in Base.metadata.tables.items():
                if not name.startswith("uv_"):
                    continue
                if name not in names:
                    missing.append(name)
                else:
                    columns = {c["name"] for c in inspector.get_columns(name)}
                    missing.extend(name + "." + c.name for c in table.columns if c.name not in columns)
            if missing:
                raise RuntimeError("UV模块需要迁移至 20260914_0115；请先备份并迁移。缺少：" + ", ".join(missing))
    Base.metadata.create_all(bind=engine, tables=[table for name, table in Base.metadata.tables.items()
                            if settings.uv_printing_enabled or not name.startswith("uv_")])
    ensure_sqlite_legacy_columns()

    with SessionLocal() as db:
        for factory_id in ("huaxing", "huakang-a", "huakang-b", "huadeng"):
            if db.get(spray_production.SprayFactory, factory_id) is None:
                db.add(spray_production.SprayFactory(factory_id=factory_id, revision=0))
        db.commit()
        from app.services.injection_scheduling.common import seed_settings
        seed_settings(db)
        seed_auth_defaults(db)
        seed_carton_supplier_defaults(db)
        seed_internal_quote_pricing_baseline_defaults(db)
        seed_molding_sample_defaults(db)
        seed_raw_material_defaults(db)
        seed_three_d_printing_defaults(db)
