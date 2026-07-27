from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect
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

        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return create_engine(database_url, future=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

SQLITE_LEGACY_COLUMNS = {
    "auth_users": [
        ("avatar_png", "avatar_png BLOB"),
        ("avatar_version", "avatar_version VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
    "molding_sample_items": [
        ("production_machine", "production_machine VARCHAR(128) NOT NULL DEFAULT ''"),
        ("mold_dimensions", "mold_dimensions VARCHAR(128) NOT NULL DEFAULT ''"),
        ("mold_presence_status", "mold_presence_status VARCHAR(20) NOT NULL DEFAULT 'unknown'"),
        ("material_components", "material_components JSON NOT NULL DEFAULT '[]'"),
        ("material_usage_type", "material_usage_type VARCHAR(20) NOT NULL DEFAULT 'production'"),
        ("actual_material_cost_components", "actual_material_cost_components JSON NOT NULL DEFAULT '[]'"),
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
        ("initiator_department", "initiator_department VARCHAR(64) NOT NULL DEFAULT 'sales-business'"),
        ("business_owner_id", "business_owner_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("business_owner_name", "business_owner_name VARCHAR(128) NOT NULL DEFAULT ''"),
        ("target_customer_price", "target_customer_price VARCHAR(128) NOT NULL DEFAULT '无'"),
        ("target_date", "target_date VARCHAR(32) NOT NULL DEFAULT ''"),
        ("remark", "remark TEXT NOT NULL DEFAULT ''"),
        ("module_version", "module_version VARCHAR(32) NOT NULL DEFAULT 'legacy_rr2_compatible'"),
        ("reference_snapshot_id", "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''"),
        ("formula_version", "formula_version VARCHAR(64) NOT NULL DEFAULT 'legacy_rr2_compatible'"),
        ("header_revision", "header_revision INTEGER NOT NULL DEFAULT 1"),
        ("cloned_from_quote_id", "cloned_from_quote_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("archived_by", "archived_by VARCHAR(64) NOT NULL DEFAULT ''"),
        ("archived_at", "archived_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("archive_reason", "archive_reason TEXT NOT NULL DEFAULT ''"),
        ("final_release_status", "final_release_status VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_submission_revision", "final_submission_revision INTEGER NOT NULL DEFAULT 0"),
        ("final_submission_manifest_json", "final_submission_manifest_json TEXT NOT NULL DEFAULT '{}'"),
        ("final_submitted_by", "final_submitted_by VARCHAR(64) NOT NULL DEFAULT ''"),
        ("final_submitted_by_name", "final_submitted_by_name VARCHAR(128) NOT NULL DEFAULT ''"),
        ("final_submitted_at", "final_submitted_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_reviewed_by", "final_reviewed_by VARCHAR(64) NOT NULL DEFAULT ''"),
        ("final_reviewed_by_name", "final_reviewed_by_name VARCHAR(128) NOT NULL DEFAULT ''"),
        ("final_reviewed_at", "final_reviewed_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_review_comment", "final_review_comment TEXT NOT NULL DEFAULT ''"),
        ("final_release_revision", "final_release_revision INTEGER NOT NULL DEFAULT 0"),
        ("final_release_invalidated_at", "final_release_invalidated_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("final_release_invalidation_reason", "final_release_invalidation_reason TEXT NOT NULL DEFAULT ''"),
    ],
    "internal_quote_sections": [
        ("is_required", "is_required BOOLEAN NOT NULL DEFAULT 1"),
        ("calculation_status", "calculation_status VARCHAR(32) NOT NULL DEFAULT 'pending'"),
        ("calculation_hash", "calculation_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        ("calculation_formula_version", "calculation_formula_version VARCHAR(64) NOT NULL DEFAULT ''"),
        ("calculation_reference_snapshot_id", "calculation_reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''"),
        ("calculated_at", "calculated_at VARCHAR(32) NOT NULL DEFAULT ''"),
        ("dependency_hash", "dependency_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        ("dependency_status", "dependency_status VARCHAR(32) NOT NULL DEFAULT 'current'"),
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
        ("reference_snapshot_id", "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''"),
        ("dependency_hash", "dependency_hash VARCHAR(64) NOT NULL DEFAULT ''"),
        ("warnings_json", "warnings_json TEXT NOT NULL DEFAULT '[]'"),
    ],
    "internal_quote_import_batches": [
        ("source_size_bytes", "source_size_bytes INTEGER NOT NULL DEFAULT 0"),
        ("preview_schema_version", "preview_schema_version VARCHAR(32) NOT NULL DEFAULT 'p3-v1'"),
        ("target_revision", "target_revision INTEGER NOT NULL DEFAULT 0"),
        ("confirm_mode", "confirm_mode VARCHAR(16) NOT NULL DEFAULT ''"),
        ("confirmed_revision", "confirmed_revision INTEGER NOT NULL DEFAULT 0"),
    ],
    "internal_quote_export_files": [
        ("template_version", "template_version VARCHAR(64) NOT NULL DEFAULT 'internal-quote-p3-v1'"),
        ("formula_version", "formula_version VARCHAR(64) NOT NULL DEFAULT ''"),
        ("reference_snapshot_id", "reference_snapshot_id VARCHAR(96) NOT NULL DEFAULT ''"),
        ("header_revision", "header_revision INTEGER NOT NULL DEFAULT 0"),
        ("release_stage", "release_stage VARCHAR(32) NOT NULL DEFAULT 'p3_section_approved'"),
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
INJECTION_SCHEDULE_PHASE4_REVISION = "20260725_0035"
INJECTION_SCHEDULE_PHASE3_REVISION = "20260723_0034"
INJECTION_SCHEDULE_PHASE2_REVISION = "20260723_0033"
INJECTION_SCHEDULE_REMOVAL_REVISION = "20260723_0031"
INJECTION_SCHEDULE_PHASE2_SCHEMA_REVISION = "20260723_0032"
INJECTION_SCHEDULE_PHASE2_REQUIRED_TABLES = {
    "injection_schedule_import_batches",
    "injection_schedule_import_issues",
    "injection_machine_masters",
    "injection_mold_masters",
    "injection_order_masters",
    "injection_schedule_factory_states",
    "injection_schedule_rule_configs",
    "injection_schedule_versions",
    "injection_schedule_tasks",
    "injection_schedule_validation_runs",
    "injection_schedule_validation_items",
    "injection_schedule_audit_events",
}
INJECTION_SCHEDULE_PHASE4_REQUIRED_TABLES = (
    INJECTION_SCHEDULE_PHASE2_REQUIRED_TABLES
    | {
        "injection_schedule_actual_corrections",
        "injection_schedule_replan_runs",
        "injection_schedule_shift_actuals",
    }
)
INJECTION_SCHEDULE_PHASE3_REQUIRED_COLUMNS = {
    "injection_machine_masters": {"screw_type"},
    "injection_mold_masters": {
        "mold_thickness_mm",
        "required_opening_stroke_mm",
        "required_screw_type",
    },
    "injection_order_masters": {
        "color_rank",
        "downstream_urgency",
        "warehouse_buffer_hours",
        "downstream_buffer_hours",
        "special_handling_reason",
    },
    "injection_schedule_versions": {"rule_config_revision"},
    "injection_schedule_tasks": {
        "delivery_due_date_snapshot",
        "color_snapshot",
        "color_rank_snapshot",
        "material_snapshot",
        "source",
        "recommendation_score",
        "score_breakdown_json",
        "constraint_snapshot_json",
        "recommendation_context_hash",
    },
}
INJECTION_SCHEDULE_PHASE4_REQUIRED_COLUMNS = {
    **INJECTION_SCHEDULE_PHASE3_REQUIRED_COLUMNS,
    "injection_order_masters": (
        INJECTION_SCHEDULE_PHASE3_REQUIRED_COLUMNS.get(
            "injection_order_masters",
            set(),
        )
        | {"priority_code"}
    ),
    "injection_schedule_tasks": (
        INJECTION_SCHEDULE_PHASE3_REQUIRED_COLUMNS.get(
            "injection_schedule_tasks",
            set(),
        )
        | {"execution_status", "protected"}
    ),
    "injection_schedule_replan_runs": {"affected_task_ids_json"},
    "injection_schedule_shift_actuals": {
        "source_version_id",
        "source_task_id",
        "lineage_sequence",
        "last_correction_request_id",
        "last_correction_payload_hash",
    },
    "injection_schedule_actual_corrections": {
        "actual_id",
        "request_id",
        "payload_hash",
        "response_json",
    },
}
INTERNAL_QUOTE_BASELINE_FREIGHT_REVISION = "20260723_0030"
INTERNAL_QUOTE_BASELINE_FREIGHT_PREVIOUS_REVISION = "20260721_0029"
INTERNAL_QUOTE_BASELINE_TABLE = "internal_quote_pricing_baselines"
INTERNAL_QUOTE_BASELINE_FREIGHT_COLUMN = "freight_routes_json"


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
        for table_name, required_columns in MOLDING_SAMPLE_DISPATCH_REQUIRED_COLUMNS.items():
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
            for table_name in sorted(MOLDING_SAMPLE_DISPATCH_REQUIRED_TABLES - table_names)
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


def ensure_injection_schedule_phase4_schema_ready() -> None:
    """Do not let create_all silently bypass the forward-only Phase 4 migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "auth_users" not in table_names:
            return

        current_revision = None
        if "alembic_version" in table_names:
            current_revision = connection.exec_driver_sql(
                "SELECT version_num FROM alembic_version"
            ).scalar_one_or_none()
        missing_tables = sorted(
            INJECTION_SCHEDULE_PHASE4_REQUIRED_TABLES - table_names
        )
        missing_columns: list[str] = []
        for table_name, required_columns in (
            INJECTION_SCHEDULE_PHASE4_REQUIRED_COLUMNS.items()
        ):
            if table_name not in table_names:
                continue
            existing_columns = {
                column["name"] for column in inspector.get_columns(table_name)
            }
            missing_columns.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - existing_columns)
            )
        pending_revision = current_revision in {
            INJECTION_SCHEDULE_REMOVAL_REVISION,
            INJECTION_SCHEDULE_PHASE2_SCHEMA_REVISION,
            INJECTION_SCHEDULE_PHASE2_REVISION,
            INJECTION_SCHEDULE_PHASE3_REVISION,
        }
        if not missing_tables and not missing_columns and not pending_revision:
            return

    missing = [f"table:{table_name}" for table_name in missing_tables]
    missing.extend(missing_columns)
    if pending_revision:
        missing.insert(0, f"revision:{current_revision}")
    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 Phase 4 Alembic 迁移 "
        f"{INJECTION_SCHEDULE_PHASE4_REVISION}；缺少："
        f"{', '.join(missing) or 'migration revision'}。"
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


def ensure_sqlite_legacy_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        for table_name, columns in SQLITE_LEGACY_COLUMNS.items():
            existing_columns = {
                row["name"]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").mappings()
            }
            if not existing_columns:
                continue

            for column_name, column_ddl in columns:
                if column_name not in existing_columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")

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
        if "access_kind" in permission_metadata_columns and {"id", "code"} <= permission_columns:
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


def init_db() -> None:
    from app.models import auth  # noqa: F401
    from app.models import internal_quote  # noqa: F401
    from app.models import injection_schedule  # noqa: F401
    from app.models import molding_sample  # noqa: F401
    from app.models import pricing  # noqa: F401
    from app.models import raw_material  # noqa: F401
    from app.services.auth import seed_auth_defaults
    from app.services.internal_quote_baseline import (
        seed_internal_quote_pricing_baseline_defaults,
    )
    from app.services.molding_sample import seed_molding_sample_defaults
    from app.services.raw_material import seed_raw_material_defaults

    ensure_molding_dispatch_schema_ready()
    ensure_internal_quote_customer_schema_ready()
    ensure_injection_schedule_phase4_schema_ready()
    ensure_internal_quote_baseline_freight_schema_ready()
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_legacy_columns()

    with SessionLocal() as db:
        seed_auth_defaults(db)
        seed_internal_quote_pricing_baseline_defaults(db)
        seed_molding_sample_defaults(db)
        seed_raw_material_defaults(db)
