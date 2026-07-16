import os
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
IAM_POSITION_SCOPE_MIGRATION_REVISION = "20260716_0020"
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

    assert script.get_heads() == [IAM_POSITION_SCOPE_MIGRATION_REVISION]

    scope_revision = script.get_revision(IAM_POSITION_SCOPE_MIGRATION_REVISION)
    assert scope_revision.down_revision == INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION
    scope_content = Path(scope_revision.path).read_text(encoding="utf-8")
    assert "access_kind" in scope_content
    assert "scope_mode" in scope_content
    assert "cross_factory_read" in scope_content

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
    assert "add column access_kind" in sql
    assert "add column scope_mode" in sql
