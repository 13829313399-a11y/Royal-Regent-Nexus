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
THREE_D_PRINTING_REVISION = "20260729_0041"
THREE_D_PRINTING_PREVIOUS_REVISIONS = frozenset({"20260728_0039", "20260729_0040"})
INJECTION_SCHEDULING_PHASE2_REVISION = "20260731_0043"
INJECTION_SCHEDULING_PHASE2_PREVIOUS_REVISIONS = frozenset(
    {"20260729_0041", "20260731_0042"}
)
INJECTION_SCHEDULING_PHASE3_REVISION = "20260731_0044"
INJECTION_SCHEDULING_PHASE3_PREVIOUS_REVISIONS = frozenset({"20260731_0043"})
INJECTION_SCHEDULING_PHASE4_REVISION = "20260731_0045"
INJECTION_SCHEDULING_PHASE4_PREVIOUS_REVISIONS = frozenset({"20260731_0044"})
INJECTION_SCHEDULING_V2_PHASE0_REVISION = "20260804_0048"
INJECTION_SCHEDULING_V2_PHASE3_REVISION = "20260804_0050"
INJECTION_SCHEDULING_V2_PHASE4_REVISION = "20260804_0051"
INJECTION_SCHEDULING_V2_PHASE5_REVISION = "20260804_0052"
INJECTION_SCHEDULING_PROFILE_REVISION = "20260805_0056"
INJECTION_SCHEDULING_TAKEOVER_REVISION = "20260805_0057"
INJECTION_SCHEDULING_PUBLIC_PLANNING_REVISION = "20260807_0058"
INJECTION_SCHEDULING_DEMAND_SHARED_REVISION = "20260810_0063"
INJECTION_SCHEDULING_V2_REQUIRED_COLUMNS = {
    "injection_scheduling_machines": {
        "machine_class_raw",
        "machine_a_class",
        "normalization_status",
        "process_tags_json",
        "special_machine_type",
    },
    "injection_scheduling_molds": {
        "mold_class_raw",
        "mold_a_class",
        "normalization_status",
        "process_tags_json",
        "special_machine_type",
    },
}
INJECTION_SCHEDULING_V2_PHASE3_REQUIRED_TABLES = {
    "injection_scheduling_runs",
    "injection_scheduling_run_assignments",
    "injection_scheduling_transition_rules",
    "injection_scheduling_machine_calendars",
}
INJECTION_SCHEDULING_V2_PHASE3_TASK_COLUMNS = {
    "setup_minutes",
    "production_minutes",
    "planned_downtime_minutes",
    "changeover_type",
    "auto_schedule_run_id",
    "auto_score",
    "auto_explanation_json",
    "manual_adjusted",
}
INJECTION_SCHEDULING_V2_PHASE4_RUN_COLUMNS = {
    "requested_solver",
    "solver_status",
    "fallback_used",
    "fallback_reason",
    "scenario_group_id",
    "scenario_name",
    "alternative_no",
    "replay_of_run_id",
}
INJECTION_SCHEDULING_V2_PHASE5_REQUIRED_TABLES = {
    "injection_scheduling_integration_cursors",
    "injection_scheduling_external_events",
    "injection_scheduling_cycle_observations",
    "injection_scheduling_speed_models",
}
INJECTION_SCHEDULING_PROFILE_REQUIRED_TABLES = {
    "injection_scheduling_import_profiles",
    "injection_scheduling_import_profile_factories",
}
INJECTION_SCHEDULING_PROFILE_BATCH_COLUMNS = {
    "profile_id",
    "profile_revision",
    "profile_definition_sha256",
    "template_signature",
    "mapping_fingerprint",
    "batch_state",
}
INJECTION_SCHEDULING_TAKEOVER_REQUIRED_TABLES = {
    "injection_scheduling_plan_order_states",
    "injection_scheduling_progress_adjustments",
    "injection_scheduling_import_actions",
    "injection_scheduling_import_master_decisions",
}
INJECTION_SCHEDULING_TAKEOVER_REQUIRED_COLUMNS = {
    "injection_scheduling_plans": {
        "based_on_event_sequence",
        "based_on_report_watermark",
    },
    "injection_scheduling_tasks": {
        "allocated_quantity",
        "takeover_source_completed_quantity",
        "origin",
        "stable_order_key",
        "stable_row_key",
        "source_task_id",
        "inherited_report_counter",
        "completed_at_clone",
        "report_event_watermark",
        "profile_id",
        "profile_revision",
    },
    "injection_scheduling_import_batches": {
        "target_draft_plan_id",
        "target_draft_plan_revision",
        "reference_published_plan_id",
        "reference_published_plan_revision",
        "reference_published_event_sequence",
        "order_task_revision_digest",
        "action_fingerprint",
        "rule_revision",
        "master_revision_digest",
    },
}
INJECTION_SCHEDULING_PUBLIC_PLANNING_REQUIRED_TABLES = {
    "injection_scheduling_export_audits",
    "injection_scheduling_upload_artifacts",
}
INJECTION_SCHEDULING_PUBLIC_PLANNING_REQUIRED_COLUMNS = {
    "injection_scheduling_export_audits": {
        "rule_revision",
        "mapping_fingerprint",
        "reference_report_event_sequence",
        "signed_row_manifest_digest",
        "export_options_json",
    },
    "injection_scheduling_import_batches": {"preview_generation"},
    "injection_scheduling_import_issues": {"preview_generation"},
    "injection_scheduling_import_actions": {"preview_generation"},
    "injection_scheduling_plans": {
        "export_profile_id",
        "export_profile_revision",
        "export_profile_family",
        "export_renderer_code",
        "export_binding_source",
        "calculation_version",
    },
}
INJECTION_SCHEDULING_DEMAND_SHARED_REQUIRED_TABLES = {
    "injection_scheduling_company_scopes",
    "injection_scheduling_company_factory_memberships",
    "injection_scheduling_customer_identities",
    "injection_scheduling_customer_aliases",
    "injection_scheduling_mold_definitions",
    "injection_scheduling_mold_aliases",
    "injection_scheduling_mold_output_specs",
    "injection_scheduling_physical_mold_assets",
    "injection_scheduling_mold_asset_movements",
    "injection_scheduling_mold_reservations",
    "injection_scheduling_factory_mold_capabilities",
    "injection_scheduling_commercial_rate_rules",
    "injection_scheduling_master_data_proposals",
    "injection_scheduling_field_evidence",
    "injection_scheduling_demand_order_identities",
    "injection_scheduling_demand_order_versions",
    "injection_scheduling_demand_import_rows",
    "injection_scheduling_demand_resolution_snapshots",
    "injection_scheduling_legacy_mold_copy_bindings",
    "injection_scheduling_rollout_policies",
}
INJECTION_SCHEDULING_DEMAND_SHARED_REQUIRED_COLUMNS = {
    "injection_scheduling_import_profiles": {
        "document_kind",
        "source_namespace_id",
        "recognition_json",
    },
    "injection_scheduling_import_batches": {
        "document_kind",
        "source_namespace_id",
        "resolution_digest",
        "mapping_draft_json",
        "ui_state_json",
        "partial_confirmation_json",
        "artifact_rebind_count",
    },
    "injection_scheduling_machines": {"equipment_details_json", "remarks"},
    "injection_scheduling_molds": {"definition_id"},
    "injection_scheduling_orders": {"mold_definition_id", "mold_output_spec_id"},
    "injection_scheduling_tasks": {"physical_mold_asset_id"},
    "injection_scheduling_run_assignments": {"physical_mold_asset_id"},
    "injection_scheduling_plan_order_states": {
        "order_revision_id",
        "factory_readiness_status",
    },
}
QC_INSPECTION_REVISION = "20260812_0067"
QC_INSPECTION_REQUIRED_TABLES = {
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
}


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


AI_CONVERSATION_REVISION = "20260813_0068"
AI_CONVERSATION_REQUIRED_TABLES = {
    "ai_conversations",
    "ai_messages",
    "ai_conversation_summaries",
}
AI_TASK_REVISION = "20260813_0070"
AI_TASK_REQUIRED_TABLES = {
    "ai_tasks",
    "ai_task_steps",
    "ai_task_events",
}
AI_GUARD_REVISION = "20260813_0071"
AI_GUARD_REQUIRED_TABLES = {
    "ai_guard_leases",
    "ai_guard_request_events",
    "ai_guard_daily_budgets",
    "ai_guard_disable_states",
}
AI_ARTIFACT_REVISION = "20260813_0072"
AI_ARTIFACT_REQUIRED_TABLES = {"ai_artifacts"}
AI_OBSERVABILITY_REVISION = "20260813_0073"
AI_OBSERVABILITY_REQUIRED_TABLES = {
    "ai_feedback",
    "ai_metric_events",
    "ai_eval_runs",
}
AI_ACTION_GATEWAY_REVISION = "20260813_0074"
AI_ACTION_GATEWAY_REQUIRED_COLUMNS = {
    "gateway_contract_version",
    "action_type",
    "handler_version",
    "approval_policy_version",
    "lifecycle_status",
    "approval_user_id",
    "approval_request_id",
    "approval_args_hash",
    "approval_entity_revision",
    "approval_expires_at",
    "execution_user_id",
    "domain_audit_id",
    "verification_result_json",
    "compensation_json",
}


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
    """Do not let create_all bypass the 3D schema or factory reassignment."""
    with engine.connect() as connection:
        inspector = inspect(connection)
        if "alembic_version" not in set(inspector.get_table_names()):
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if current_revision not in THREE_D_PRINTING_PREVIOUS_REVISIONS:
        return
    raise RuntimeError(
        "检测到数据库尚未完成 3D 打印机管理迁移 "
        f"{THREE_D_PRINTING_REVISION}；当前版本：{current_revision}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_phase2_schema_ready() -> None:
    """Do not let create_all bypass the injection-scheduling Phase 2 migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        if "alembic_version" not in set(inspector.get_table_names()):
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if current_revision not in INJECTION_SCHEDULING_PHASE2_PREVIOUS_REVISIONS:
        return
    raise RuntimeError(
        "检测到数据库尚未完成注塑排产阶段 2 主数据迁移 "
        f"{INJECTION_SCHEDULING_PHASE2_REVISION}；当前版本：{current_revision}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_phase3_schema_ready() -> None:
    """Do not let create_all bypass the Phase 3 execution migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        if "alembic_version" not in set(inspector.get_table_names()):
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if current_revision not in INJECTION_SCHEDULING_PHASE3_PREVIOUS_REVISIONS:
        return
    raise RuntimeError(
        "检测到数据库尚未完成注塑排产阶段 3 执行闭环迁移 "
        f"{INJECTION_SCHEDULING_PHASE3_REVISION}；当前版本：{current_revision}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_phase4_schema_ready() -> None:
    """Do not let create_all bypass the Phase 4 import migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        if "alembic_version" not in set(inspector.get_table_names()):
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
    if current_revision not in INJECTION_SCHEDULING_PHASE4_PREVIOUS_REVISIONS:
        return
    raise RuntimeError(
        "检测到数据库尚未完成注塑排产阶段 4 Excel 导入迁移 "
        f"{INJECTION_SCHEDULING_PHASE4_REVISION}；当前版本：{current_revision}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_v2_phase0_schema_ready() -> None:
    """Do not let create_all bypass the V2 rebuild after revision 0047."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing: list[str] = []
        for (
            table_name,
            required_columns,
        ) in INJECTION_SCHEDULING_V2_REQUIRED_COLUMNS.items():
            if table_name not in table_names:
                missing.append(f"table:{table_name}")
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - columns)
            )
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 V2 Phase 0 重建迁移 "
        f"{INJECTION_SCHEDULING_V2_PHASE0_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_v2_phase3_schema_ready() -> None:
    """Refuse to let create_all silently bypass the Phase 3 data migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = [
            f"table:{table_name}"
            for table_name in sorted(
                INJECTION_SCHEDULING_V2_PHASE3_REQUIRED_TABLES - table_names
            )
        ]
        if "injection_scheduling_tasks" in table_names:
            task_columns = {
                column["name"]
                for column in inspector.get_columns("injection_scheduling_tasks")
            }
            missing.extend(
                f"column:injection_scheduling_tasks.{column_name}"
                for column_name in sorted(
                    INJECTION_SCHEDULING_V2_PHASE3_TASK_COLUMNS - task_columns
                )
            )
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 V2 Phase 3 启发式排期迁移 "
        f"{INJECTION_SCHEDULING_V2_PHASE3_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_v2_phase4_schema_ready() -> None:
    """Refuse to let create_all silently bypass Phase 4 run metadata."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        if "injection_scheduling_runs" not in table_names:
            return
        run_columns = {
            column["name"]
            for column in inspector.get_columns("injection_scheduling_runs")
        }
        missing = sorted(INJECTION_SCHEDULING_V2_PHASE4_RUN_COLUMNS - run_columns)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 V2 Phase 4 求解器迁移 "
        f"{INJECTION_SCHEDULING_V2_PHASE4_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'column:injection_scheduling_runs.{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_v2_phase5_schema_ready() -> None:
    """Refuse to let create_all silently bypass Phase 5 integration tables."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(INJECTION_SCHEDULING_V2_PHASE5_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 V2 Phase 5 集成与分析迁移 "
        f"{INJECTION_SCHEDULING_V2_PHASE5_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_profile_schema_ready() -> None:
    """Refuse to let create_all silently bypass versioned import profiles."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(INJECTION_SCHEDULING_PROFILE_REQUIRED_TABLES - table_names)
        missing_columns: list[str] = []
        if "injection_scheduling_import_batches" in table_names:
            batch_columns = {
                column["name"]
                for column in inspector.get_columns(
                    "injection_scheduling_import_batches"
                )
            }
            missing_columns = sorted(
                INJECTION_SCHEDULING_PROFILE_BATCH_COLUMNS - batch_columns
            )
        if not missing and not missing_columns:
            return

    missing_items = [
        *(f"table:{item}" for item in missing),
        *(
            f"column:injection_scheduling_import_batches.{item}"
            for item in missing_columns
        ),
    ]
    raise RuntimeError(
        "检测到数据库尚未完成注塑排产 Profile/Canonical 迁移 "
        f"{INJECTION_SCHEDULING_PROFILE_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(missing_items)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_takeover_schema_ready() -> None:
    """Refuse to let create_all bypass plan-aware takeover data contracts."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = [
            f"table:{table_name}"
            for table_name in sorted(
                INJECTION_SCHEDULING_TAKEOVER_REQUIRED_TABLES - table_names
            )
        ]
        for (
            table_name,
            required_columns,
        ) in INJECTION_SCHEDULING_TAKEOVER_REQUIRED_COLUMNS.items():
            if table_name not in table_names:
                missing.append(f"table:{table_name}")
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - columns)
            )
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产计划接管迁移 "
        f"{INJECTION_SCHEDULING_TAKEOVER_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(dict.fromkeys(missing))}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_public_planning_schema_ready() -> None:
    """Refuse startup when recoverable planning artifacts were not migrated."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = [
            f"table:{table_name}"
            for table_name in sorted(
                INJECTION_SCHEDULING_PUBLIC_PLANNING_REQUIRED_TABLES - table_names
            )
        ]
        for (
            table_name,
            required_columns,
        ) in INJECTION_SCHEDULING_PUBLIC_PLANNING_REQUIRED_COLUMNS.items():
            if table_name not in table_names:
                missing.append(f"table:{table_name}")
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - columns)
            )
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产公共计划迁移 "
        f"{INJECTION_SCHEDULING_PUBLIC_PLANNING_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(dict.fromkeys(missing))}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_injection_scheduling_demand_shared_schema_ready() -> None:
    """Refuse startup when demand/shared-mold contracts were not migrated."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = [
            f"table:{table_name}"
            for table_name in sorted(
                INJECTION_SCHEDULING_DEMAND_SHARED_REQUIRED_TABLES - table_names
            )
        ]
        for (
            table_name,
            required_columns,
        ) in INJECTION_SCHEDULING_DEMAND_SHARED_REQUIRED_COLUMNS.items():
            if table_name not in table_names:
                missing.append(f"table:{table_name}")
                continue
            columns = {column["name"] for column in inspector.get_columns(table_name)}
            missing.extend(
                f"column:{table_name}.{column_name}"
                for column_name in sorted(required_columns - columns)
            )
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成注塑排产需求单/共享模具迁移 "
        f"{INJECTION_SCHEDULING_DEMAND_SHARED_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(dict.fromkeys(missing))}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_conversation_schema_ready() -> None:
    """Refuse to let create_all bypass the approved Conversation migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(AI_CONVERSATION_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI Conversation 迁移 "
        f"{AI_CONVERSATION_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_task_schema_ready() -> None:
    """Refuse to let create_all bypass the approved NIF-07 Task migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(AI_TASK_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI Task 迁移 "
        f"{AI_TASK_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_guard_schema_ready() -> None:
    """Refuse to let create_all bypass the accepted NIF-09 migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(AI_GUARD_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI 共享 Guard 迁移 "
        f"{AI_GUARD_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_artifact_schema_ready() -> None:
    """Refuse to let create_all bypass the accepted NIF-12 migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(AI_ARTIFACT_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI Artifact 迁移 "
        f"{AI_ARTIFACT_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_observability_schema_ready() -> None:
    """Refuse to let create_all bypass the NIF-17 metadata migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        missing = sorted(AI_OBSERVABILITY_REQUIRED_TABLES - table_names)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI 反馈与可观测元数据迁移 "
        f"{AI_OBSERVABILITY_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'table:{item}' for item in missing)}。"
        "请先备份数据库并执行 Alembic upgrade head，再启动应用。"
    )


def ensure_ai_action_gateway_schema_ready() -> None:
    """Refuse to let create_all bypass the accepted NIF-16 migration."""

    with engine.connect() as connection:
        inspector = inspect(connection)
        table_names = set(inspector.get_table_names())
        if "alembic_version" not in table_names:
            return
        current_revision = connection.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar_one_or_none()
        if "ai_action_confirmations" not in table_names:
            missing = sorted(AI_ACTION_GATEWAY_REQUIRED_COLUMNS)
        else:
            columns = {
                item["name"]
                for item in inspector.get_columns("ai_action_confirmations")
            }
            missing = sorted(AI_ACTION_GATEWAY_REQUIRED_COLUMNS - columns)
        if not missing:
            return

    raise RuntimeError(
        "检测到数据库尚未完成 AI Action Gateway 迁移 "
        f"{AI_ACTION_GATEWAY_REVISION}；当前版本：{current_revision}；"
        f"缺少：{', '.join(f'column:{item}' for item in missing)}。"
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


def init_db() -> None:
    from app.models import (
        ai_action,  # noqa: F401
        ai_artifact,  # noqa: F401
        ai_conversation,  # noqa: F401
        ai_guard,  # noqa: F401
        ai_observability,  # noqa: F401
        ai_task,  # noqa: F401
        auth,  # noqa: F401
        carton_procurement,  # noqa: F401
        customer_order,  # noqa: F401
        injection_scheduling,  # noqa: F401
        injection_scheduling_execution,  # noqa: F401
        injection_scheduling_export,  # noqa: F401
        injection_scheduling_import,  # noqa: F401
        injection_scheduling_phase5,  # noqa: F401
        injection_scheduling_scheduler,  # noqa: F401
        injection_scheduling_shared,  # noqa: F401
        internal_quote,  # noqa: F401
        molding_sample,  # noqa: F401
        pricing,  # noqa: F401
        qc_inspection,  # noqa: F401
        raw_material,  # noqa: F401
        three_d_printing,  # noqa: F401
    )
    from app.services.auth import seed_auth_defaults
    from app.services.carton_procurement import seed_carton_supplier_defaults
    from app.services.injection_scheduling import seed_injection_scheduling_defaults
    from app.services.injection_scheduling_profile_registry import (
        seed_builtin_import_profiles,
    )
    from app.services.internal_quote_baseline import (
        seed_internal_quote_pricing_baseline_defaults,
    )
    from app.services.molding_sample import seed_molding_sample_defaults
    from app.services.raw_material import seed_raw_material_defaults
    from app.services.three_d_printing import seed_three_d_printing_defaults

    ensure_molding_dispatch_schema_ready()
    ensure_internal_quote_customer_schema_ready()
    ensure_internal_quote_baseline_freight_schema_ready()
    ensure_three_d_printing_schema_ready()
    ensure_injection_scheduling_phase2_schema_ready()
    ensure_injection_scheduling_phase3_schema_ready()
    ensure_injection_scheduling_phase4_schema_ready()
    ensure_injection_scheduling_v2_phase0_schema_ready()
    ensure_injection_scheduling_v2_phase3_schema_ready()
    ensure_injection_scheduling_v2_phase4_schema_ready()
    ensure_injection_scheduling_v2_phase5_schema_ready()
    ensure_injection_scheduling_profile_schema_ready()
    ensure_injection_scheduling_takeover_schema_ready()
    ensure_injection_scheduling_public_planning_schema_ready()
    ensure_injection_scheduling_demand_shared_schema_ready()
    ensure_qc_inspection_schema_ready()
    ensure_ai_conversation_schema_ready()
    ensure_ai_task_schema_ready()
    ensure_ai_guard_schema_ready()
    ensure_ai_artifact_schema_ready()
    ensure_ai_observability_schema_ready()
    ensure_ai_action_gateway_schema_ready()
    Base.metadata.create_all(bind=engine)
    ensure_sqlite_legacy_columns()

    with SessionLocal() as db:
        seed_auth_defaults(db)
        seed_carton_supplier_defaults(db)
        seed_internal_quote_pricing_baseline_defaults(db)
        seed_injection_scheduling_defaults(db)
        seed_builtin_import_profiles(db)
        seed_molding_sample_defaults(db)
        seed_raw_material_defaults(db)
        seed_three_d_printing_defaults(db)
