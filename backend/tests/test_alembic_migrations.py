import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
BASE_MIGRATION_REVISION = "20260701_0001"
NOTIFICATION_MIGRATION_REVISION = "20260703_0002"
AUTH_MIGRATION_REVISION = "20260703_0003"
PROBLEM_MIGRATION_REVISION = "20260703_0004"
MIGRATION_REVISION = "20260706_0005"
INJECTION_SCHEDULE_MIGRATION_REVISION = "20260708_0006"
AUTH_REGISTRATION_MIGRATION_REVISION = "20260708_0007"
MOLD_METADATA_MIGRATION_REVISION = "20260710_0008"
AUTH_AVATAR_MIGRATION_REVISION = "20260710_0009"
CONFIGURABLE_IAM_MIGRATION_REVISION = "20260711_0010"
PRICING_MIGRATION_REVISION = "20260711_0011"
NOTIFICATION_DEPARTMENT_MIGRATION_REVISION = "20260712_0012"
RAW_MATERIAL_MIGRATION_REVISION = "20260714_0013"
TRIAL_REPORT_MIGRATION_REVISION = "20260714_0014"
MATERIAL_COMPONENT_MIGRATION_REVISION = "20260715_0015"
INTERNAL_QUOTE_WORKFLOW_MIGRATION_REVISION = "20260715_0016"
INTERNAL_QUOTE_WORKSHOP_MIGRATION_REVISION = "20260715_0017"
INTERNAL_QUOTE_ARTIFACT_MIGRATION_REVISION = "20260716_0018"
INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION = "20260716_0019"
INTERNAL_QUOTE_P1_MIGRATION_REVISION = "20260716_0020"
INTERNAL_QUOTE_P2_MIGRATION_REVISION = "20260716_0021"
INTERNAL_QUOTE_P3_MIGRATION_REVISION = "20260716_0022"
INTERNAL_QUOTE_P4_MIGRATION_REVISION = "20260716_0023"
MOLDING_SAMPLE_TABLES = [
    "molding_sample_orders",
    "molding_sample_items",
    "molding_sample_audit_logs",
    "molding_sample_material_prices",
    "molding_sample_settings",
    "molding_sample_sensitive_audit_logs",
    "molding_sample_requisitions",
    "molding_sample_inventory_batches",
    "molding_sample_inventory_movements",
    "molding_sample_notifications",
    "molding_sample_problems",
]
AUTH_TABLES = [
    "auth_users",
    "auth_roles",
    "auth_permissions",
    "auth_role_permissions",
    "auth_user_roles",
    "auth_sessions",
    "auth_audit_logs",
    "auth_registration_requests",
    "system_notifications",
]
CONFIGURABLE_IAM_TABLES = [
    "employee_profiles",
    "auth_permission_metadata",
    "auth_role_metadata",
    "auth_role_binding_metadata",
    "auth_user_permission_overrides",
    "auth_user_authorization_revisions",
    "auth_iam_state",
    "auth_access_requests",
    "auth_access_request_items",
    "auth_authorization_previews",
    "auth_authorization_events",
]
REMOVED_PIN_TABLES = [
    "molding_sample_auth_pins",
    "molding_sample_pin_attempts",
]


def test_alembic_has_single_molding_sample_head():
    assert ALEMBIC_INI.exists()

    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [INTERNAL_QUOTE_P4_MIGRATION_REVISION]

    p4_revision = script.get_revision(INTERNAL_QUOTE_P4_MIGRATION_REVISION)
    assert p4_revision.down_revision == INTERNAL_QUOTE_P3_MIGRATION_REVISION
    p4_content = Path(p4_revision.path).read_text(encoding="utf-8")
    for expected in (
        "final_release_status",
        "final_submission_manifest_json",
        "internal_quote_final_reviews",
        "internal_quote_artifact_handoffs",
        "release_manifest_sha256",
        "consumer_reference",
        "uq_internal_quote_artifact_handoffs_quote_release",
    ):
        assert expected in p4_content

    p3_revision = script.get_revision(INTERNAL_QUOTE_P3_MIGRATION_REVISION)
    assert p3_revision.down_revision == INTERNAL_QUOTE_P2_MIGRATION_REVISION
    p3_content = Path(p3_revision.path).read_text(encoding="utf-8")
    for expected in (
        "source_size_bytes",
        "preview_schema_version",
        "target_revision",
        "confirm_mode",
        "confirmed_revision",
        "template_version",
        "reference_snapshot_id",
        "export_manifest_json",
    ):
        assert expected in p3_content

    p2_revision = script.get_revision(INTERNAL_QUOTE_P2_MIGRATION_REVISION)
    assert p2_revision.down_revision == INTERNAL_QUOTE_P1_MIGRATION_REVISION
    p2_content = Path(p2_revision.path).read_text(encoding="utf-8")
    for expected in (
        "internal_quote_reference_sets",
        "reference_snapshot_id",
        "formula_version",
        "calculation_status",
        "dependency_hash",
        "warnings_json",
    ):
        assert expected in p2_content

    p1_revision = script.get_revision(INTERNAL_QUOTE_P1_MIGRATION_REVISION)
    assert p1_revision.down_revision == INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION
    p1_content = Path(p1_revision.path).read_text(encoding="utf-8")
    for expected in (
        "header_revision",
        "business_owner_id",
        "internal_quote_section_revisions",
        "internal_quote_reviews",
        "old_revision",
        "request_id",
    ):
        assert expected in p1_content

    archive_revision = script.get_revision(INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION)
    assert archive_revision.down_revision == INTERNAL_QUOTE_ARTIFACT_MIGRATION_REVISION
    archive_content = Path(archive_revision.path).read_text(encoding="utf-8")
    assert "initiator_department" in archive_content
    assert "is_required" in archive_content

    artifact_revision = script.get_revision(INTERNAL_QUOTE_ARTIFACT_MIGRATION_REVISION)
    assert artifact_revision.down_revision == INTERNAL_QUOTE_WORKSHOP_MIGRATION_REVISION
    artifact_content = Path(artifact_revision.path).read_text(encoding="utf-8")
    for table_name in (
        "internal_quote_import_batches",
        "internal_quote_attachments",
        "internal_quote_export_files",
    ):
        assert table_name in artifact_content

    workshop_revision = script.get_revision(INTERNAL_QUOTE_WORKSHOP_MIGRATION_REVISION)
    assert workshop_revision.down_revision == INTERNAL_QUOTE_WORKFLOW_MIGRATION_REVISION
    assert "huaxing-workshop" in Path(workshop_revision.path).read_text(encoding="utf-8")

    workflow_revision = script.get_revision(INTERNAL_QUOTE_WORKFLOW_MIGRATION_REVISION)
    assert workflow_revision.down_revision == MATERIAL_COMPONENT_MIGRATION_REVISION
    workflow_content = Path(workflow_revision.path).read_text(encoding="utf-8")
    for table_name in (
        "internal_quotes",
        "internal_quote_sections",
        "internal_quote_audit_logs",
    ):
        assert table_name in workflow_content

    material_component_revision = script.get_revision(MATERIAL_COMPONENT_MIGRATION_REVISION)
    assert material_component_revision.down_revision == TRIAL_REPORT_MIGRATION_REVISION
    material_component_content = Path(material_component_revision.path).read_text(encoding="utf-8")
    assert "material_components" in material_component_content
    assert "material_usage_type" in material_component_content
    assert "actual_material_cost_components" in material_component_content

    trial_report_revision = script.get_revision(TRIAL_REPORT_MIGRATION_REVISION)
    assert trial_report_revision.down_revision == RAW_MATERIAL_MIGRATION_REVISION
    assert "molding_sample_trial_reports" in Path(trial_report_revision.path).read_text(encoding="utf-8")

    raw_material_revision = script.get_revision(RAW_MATERIAL_MIGRATION_REVISION)
    assert raw_material_revision.down_revision == NOTIFICATION_DEPARTMENT_MIGRATION_REVISION
    assert "raw_materials" in Path(raw_material_revision.path).read_text(encoding="utf-8")

    notification_department_revision = script.get_revision(NOTIFICATION_DEPARTMENT_MIGRATION_REVISION)
    assert notification_department_revision.down_revision == PRICING_MIGRATION_REVISION
    notification_department_content = Path(notification_department_revision.path).read_text(encoding="utf-8")
    assert "target_department" in notification_department_content

    pricing_revision = script.get_revision(PRICING_MIGRATION_REVISION)
    assert pricing_revision.down_revision == CONFIGURABLE_IAM_MIGRATION_REVISION
    pricing_migration_content = Path(pricing_revision.path).read_text(encoding="utf-8")
    assert "pricing_quotes" in pricing_migration_content

    iam_revision = script.get_revision(CONFIGURABLE_IAM_MIGRATION_REVISION)
    assert iam_revision.down_revision == AUTH_AVATAR_MIGRATION_REVISION
    iam_migration_content = Path(iam_revision.path).read_text(encoding="utf-8")
    for table_name in CONFIGURABLE_IAM_TABLES:
        assert table_name in iam_migration_content
    assert "op.add_column" not in iam_migration_content

    avatar_revision = script.get_revision(AUTH_AVATAR_MIGRATION_REVISION)
    assert avatar_revision.down_revision == MOLD_METADATA_MIGRATION_REVISION
    avatar_migration_content = Path(avatar_revision.path).read_text(encoding="utf-8")
    assert "avatar_png" in avatar_migration_content
    assert "avatar_version" in avatar_migration_content

    mold_metadata_revision = script.get_revision(MOLD_METADATA_MIGRATION_REVISION)
    assert mold_metadata_revision.down_revision == AUTH_REGISTRATION_MIGRATION_REVISION
    mold_metadata_content = Path(mold_metadata_revision.path).read_text(encoding="utf-8")
    assert "mold_dimensions" in mold_metadata_content
    assert "mold_presence_status" in mold_metadata_content

    auth_registration_revision = script.get_revision(AUTH_REGISTRATION_MIGRATION_REVISION)
    assert auth_registration_revision.down_revision == INJECTION_SCHEDULE_MIGRATION_REVISION
    auth_registration_content = Path(auth_registration_revision.path).read_text(encoding="utf-8")
    assert "auth_registration_requests" in auth_registration_content
    assert "system_notifications" in auth_registration_content

    injection_revision = script.get_revision(INJECTION_SCHEDULE_MIGRATION_REVISION)
    assert injection_revision.down_revision == MIGRATION_REVISION

    revision = script.get_revision(MIGRATION_REVISION)
    assert revision.down_revision == PROBLEM_MIGRATION_REVISION

    migration_content = Path(revision.path).read_text(encoding="utf-8")
    assert "production_machine" in migration_content

    problem_revision = script.get_revision(PROBLEM_MIGRATION_REVISION)
    assert problem_revision.down_revision == AUTH_MIGRATION_REVISION

    problem_migration_content = Path(problem_revision.path).read_text(encoding="utf-8")
    assert "molding_sample_problems" in problem_migration_content

    auth_revision = script.get_revision(AUTH_MIGRATION_REVISION)
    auth_migration_content = Path(auth_revision.path).read_text(encoding="utf-8")
    for table_name in [
        name
        for name in AUTH_TABLES
        if name not in {"auth_registration_requests", "system_notifications"}
    ]:
        assert table_name in auth_migration_content
    for table_name in REMOVED_PIN_TABLES:
        assert table_name in auth_migration_content

    base_revision = script.get_revision(BASE_MIGRATION_REVISION)
    base_migration_content = Path(base_revision.path).read_text(encoding="utf-8")
    for table_name in [
        name
        for name in MOLDING_SAMPLE_TABLES
        if name not in {"molding_sample_notifications", "molding_sample_problems"}
    ]:
        assert table_name in base_migration_content

    notification_revision = script.get_revision(NOTIFICATION_MIGRATION_REVISION)
    notification_migration_content = Path(notification_revision.path).read_text(encoding="utf-8")
    assert "molding_sample_notifications" in notification_migration_content


def test_alembic_offline_postgresql_sql_contains_molding_sample_schema():
    env = os.environ.copy()
    env["DATABASE_URL"] = "postgresql+psycopg://postgres:postgres@localhost:5432/royal_regent_nexus"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            "head",
            "--sql",
        ],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    sql = result.stdout.lower()

    for table_name in MOLDING_SAMPLE_TABLES:
        assert f"create table {table_name}" in sql
    for table_name in AUTH_TABLES:
        assert f"create table {table_name}" in sql
    for table_name in CONFIGURABLE_IAM_TABLES:
        assert f"create table {table_name}" in sql
    for table_name in REMOVED_PIN_TABLES:
        assert f"drop table {table_name}" in sql

    assert "foreign key(order_id) references molding_sample_orders" in sql
    assert "on delete cascade" in sql
    assert "create unique index ix_molding_sample_material_prices_material" in sql
    assert "create unique index ix_molding_sample_requisitions_req_number" in sql
    assert "mold_dimensions" in sql
    assert "mold_presence_status" in sql
    assert "avatar_png" in sql
    assert "avatar_version" in sql
    assert "target_department" in sql
    assert "create table pricing_quotes" in sql
    assert "create table raw_materials" in sql
    assert "create table molding_sample_trial_reports" in sql
    assert "material_components" in sql
    assert "material_usage_type" in sql
    assert "actual_material_cost_components" in sql
    assert "create table internal_quotes" in sql
    assert "create table internal_quote_sections" in sql
    assert "create table internal_quote_audit_logs" in sql
    assert "create table internal_quote_import_batches" in sql
    assert "create table internal_quote_attachments" in sql
    assert "create table internal_quote_export_files" in sql
    assert "create table internal_quote_section_revisions" in sql
    assert "create table internal_quote_reviews" in sql
    assert "header_revision" in sql
    assert "business_owner_id" in sql
    assert "create table internal_quote_reference_sets" in sql
    assert "calculation_status" in sql
    assert "dependency_hash" in sql
    assert "preview_schema_version" in sql
    assert "export_manifest_json" in sql
    assert "release_stage" in sql
    assert "final_release_status" in sql
    assert "final_submission_manifest_json" in sql
    assert "create table internal_quote_final_reviews" in sql
    assert "create table internal_quote_artifact_handoffs" in sql
    assert "uq_internal_quote_artifact_handoffs_quote_release" in sql


def test_internal_quote_p1_upgrade_preserves_existing_0019_records(tmp_path):
    database_path = tmp_path / "internal_quote_0019.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    def run_alembic(*arguments: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    run_alembic("upgrade", INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO internal_quotes (
                id, factory_id, workshop_code, workshop_name, quote_no,
                product_name, customer, qty, version_label, status,
                created_by, created_by_name, created_at, updated_at,
                initiator_department
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQ-LEGACY-P1",
                "huaxing",
                "huaxing-workshop",
                "华兴",
                "LEGACY-P1",
                "历史产品",
                "历史客户",
                1000,
                "V1",
                "draft",
                "legacy-user",
                "历史用户",
                "2026-07-16 08:00:00",
                "2026-07-16 08:00:00",
                "sales",
            ),
        )
        connection.execute(
            """
            INSERT INTO internal_quote_sections (
                id, quote_id, department, department_name, status,
                payload_json, calculation_json, revision, filled_by, filled_at,
                submitted_by, submitted_by_id, submitted_at, reviewed_by,
                reviewed_at, review_comment, updated_at, is_required
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQ-LEGACY-P1-sales",
                "IQ-LEGACY-P1",
                "sales",
                "业务部",
                "draft",
                "{}",
                "{}",
                1,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "2026-07-16 08:00:00",
                1,
            ),
        )
        connection.execute(
            """
            INSERT INTO internal_quote_audit_logs (
                id, quote_id, department, actor_id, actor_name, action, detail, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQA-LEGACY-P1",
                "IQ-LEGACY-P1",
                "sales",
                "legacy-user",
                "历史用户",
                "create",
                "历史审计",
                "2026-07-16 08:00:00",
            ),
        )
        connection.commit()

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        quote = connection.execute(
            """
            SELECT quote_no, initiator_department, module_version, header_revision
            FROM internal_quotes WHERE id = 'IQ-LEGACY-P1'
            """
        ).fetchone()
        assert quote == ("LEGACY-P1", "sales-business", "legacy_rr2_compatible", 1)
        audit = connection.execute(
            "SELECT factory_id, action FROM internal_quote_audit_logs WHERE id = 'IQA-LEGACY-P1'"
        ).fetchone()
        assert audit == ("huaxing", "create")
        assert connection.execute(
            "SELECT COUNT(*) FROM internal_quote_sections WHERE quote_id = 'IQ-LEGACY-P1'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_P4_MIGRATION_REVISION,
        )

    run_alembic("downgrade", INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION)
    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT quote_no FROM internal_quotes WHERE id = 'IQ-LEGACY-P1'"
        ).fetchone() == ("LEGACY-P1",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_P4_MIGRATION_REVISION,
        )


def test_internal_quote_p3_upgrade_preserves_existing_0018_artifacts(tmp_path):
    database_path = tmp_path / "internal_quote_0018_artifacts.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    def run_alembic(*arguments: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    run_alembic("upgrade", INTERNAL_QUOTE_ARTIFACT_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            INSERT INTO internal_quotes (
                id, factory_id, workshop_code, workshop_name, quote_no,
                product_name, customer, qty, version_label, status,
                created_by, created_by_name, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQ-LEGACY-P3",
                "huaxing",
                "huaxing-workshop",
                "华兴",
                "LEGACY-P3",
                "历史文件产品",
                "历史客户",
                1000,
                "V1",
                "drafting",
                "legacy-user",
                "历史用户",
                "2026-07-16 08:00:00",
                "2026-07-16 08:00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO internal_quote_import_batches (
                id, quote_id, factory_id, import_type, target_department,
                source_file_name, source_sha256, status, preview_json,
                created_by, created_by_name, created_at,
                confirmed_by, confirmed_by_name, confirmed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQIMP-LEGACY",
                "IQ-LEGACY-P3",
                "huaxing",
                "mold",
                "engineering",
                "历史模具.xlsx",
                "a" * 64,
                "previewed",
                "{}",
                "legacy-user",
                "历史用户",
                "2026-07-16 08:00:00",
                "",
                "",
                "",
            ),
        )
        connection.execute(
            """
            INSERT INTO internal_quote_attachments (
                id, quote_id, factory_id, department, file_name, content_type,
                size_bytes, sha256, content, uploaded_by, uploaded_by_name, uploaded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQATT-LEGACY",
                "IQ-LEGACY-P3",
                "huaxing",
                "engineering",
                "历史附件.pdf",
                "application/pdf",
                11,
                "b" * 64,
                b"%PDF-legacy",
                "legacy-user",
                "历史用户",
                "2026-07-16 08:00:00",
            ),
        )
        connection.execute(
            """
            INSERT INTO internal_quote_export_files (
                id, quote_id, factory_id, file_name, content_type, size_bytes,
                sha256, section_revisions_json, status, content,
                exported_by, exported_by_name, exported_at, superseded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "IQEXP-LEGACY",
                "IQ-LEGACY-P3",
                "huaxing",
                "历史导出.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                6,
                "c" * 64,
                "{}",
                "current",
                b"PK-old",
                "legacy-user",
                "历史用户",
                "2026-07-16 08:00:00",
                "",
            ),
        )
        connection.commit()

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        imported = connection.execute(
            """
            SELECT source_sha256, source_size_bytes, preview_schema_version,
                   target_revision, confirm_mode, confirmed_revision
            FROM internal_quote_import_batches WHERE id = 'IQIMP-LEGACY'
            """
        ).fetchone()
        assert imported == ("a" * 64, 0, "p3-v1", 0, "", 0)
        exported = connection.execute(
            """
            SELECT template_version, formula_version, reference_snapshot_id,
                   header_revision, release_stage, export_manifest_json, content
            FROM internal_quote_export_files WHERE id = 'IQEXP-LEGACY'
            """
        ).fetchone()
        assert exported == (
            "internal-quote-p3-v1",
            "",
            "",
            0,
            "p3_section_approved",
            "{}",
            b"PK-old",
        )
        assert connection.execute(
            "SELECT content FROM internal_quote_attachments WHERE id = 'IQATT-LEGACY'"
        ).fetchone() == (b"%PDF-legacy",)
        assert connection.execute(
            """
            SELECT final_release_status, final_submission_revision,
                   final_submission_manifest_json, final_release_revision
            FROM internal_quotes WHERE id = 'IQ-LEGACY-P3'
            """
        ).fetchone() == ("", 0, "{}", 0)
        p4_tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "internal_quote_final_reviews" in p4_tables
        assert "internal_quote_artifact_handoffs" in p4_tables

    run_alembic("downgrade", INTERNAL_QUOTE_P2_MIGRATION_REVISION)
    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT source_file_name FROM internal_quote_import_batches WHERE id = 'IQIMP-LEGACY'"
        ).fetchone() == ("历史模具.xlsx",)
        assert connection.execute(
            "SELECT file_name FROM internal_quote_export_files WHERE id = 'IQEXP-LEGACY'"
        ).fetchone() == ("历史导出.xlsx",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_P4_MIGRATION_REVISION,
        )
