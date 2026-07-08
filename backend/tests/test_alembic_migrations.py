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
REMOVED_PIN_TABLES = [
    "molding_sample_auth_pins",
    "molding_sample_pin_attempts",
]


def test_alembic_has_single_molding_sample_head():
    assert ALEMBIC_INI.exists()

    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [AUTH_REGISTRATION_MIGRATION_REVISION]

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
    for table_name in REMOVED_PIN_TABLES:
        assert f"drop table {table_name}" in sql

    assert "foreign key(order_id) references molding_sample_orders" in sql
    assert "on delete cascade" in sql
    assert "create unique index ix_molding_sample_material_prices_material" in sql
    assert "create unique index ix_molding_sample_requisitions_req_number" in sql
