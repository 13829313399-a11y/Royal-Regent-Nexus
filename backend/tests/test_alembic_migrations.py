import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine


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
IAM_POSITION_SCOPE_MIGRATION_REVISION = "20260717_0024"
INTERNAL_QUOTE_TARGET_PRICE_MIGRATION_REVISION = "20260718_0025"
INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION = "20260718_0026"
RAW_MATERIAL_SHARED_MIGRATION_REVISION = "20260720_0027"
MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION = "20260720_0028"
INTERNAL_QUOTE_CUSTOMER_MIGRATION_REVISION = "20260721_0029"
INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION = "20260723_0030"
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
    "molding_sample_trial_reports",
    "molding_sample_dispatch_logs",
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

    assert script.get_heads() == [INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION]

    freight_revision = script.get_revision(
        INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION
    )
    assert freight_revision.down_revision == INTERNAL_QUOTE_CUSTOMER_MIGRATION_REVISION
    freight_content = Path(freight_revision.path).read_text(encoding="utf-8")
    assert "internal_quote_pricing_baselines" in freight_content
    assert "freight_routes_json" in freight_content

    customer_revision = script.get_revision(
        INTERNAL_QUOTE_CUSTOMER_MIGRATION_REVISION
    )
    assert customer_revision.down_revision == MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION
    customer_content = Path(customer_revision.path).read_text(encoding="utf-8")
    for expected in (
        "internal_quote_customers",
        "uq_internal_quote_customers_factory_name",
        "DEFAULT_CUSTOMERS",
        "historical customers",
    ):
        assert expected in customer_content

    dispatch_revision = script.get_revision(
        MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION
    )
    assert dispatch_revision.down_revision == RAW_MATERIAL_SHARED_MIGRATION_REVISION
    dispatch_content = Path(dispatch_revision.path).read_text(encoding="utf-8")
    for expected in (
        "production_factory_id",
        "production_assigned_at",
        "production_assigned_by",
        "production_assignment_version",
        "molding_sample_dispatch_logs",
        "ix_molding_sample_orders_production_status_created_at",
        "ck_molding_sample_orders_production_factory",
        "BEGIN IMMEDIATE",
        "LOCK TABLE molding_sample_orders",
        "cannot run as offline SQL",
        "irreversible",
    ):
        assert expected in dispatch_content
    dispatch_upgrade_source = dispatch_content.split(
        "def upgrade() -> None:",
        1,
    )[1].split("def downgrade() -> None:", 1)[0]
    assert dispatch_upgrade_source.index("_load_preflight_plan(connection)") < (
        dispatch_upgrade_source.index("op.add_column")
    )

    raw_material_shared_revision = script.get_revision(
        RAW_MATERIAL_SHARED_MIGRATION_REVISION
    )
    assert (
        raw_material_shared_revision.down_revision
        == INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION
    )
    raw_material_shared_content = Path(
        raw_material_shared_revision.path
    ).read_text(encoding="utf-8")
    for expected in (
        "RAW_MATERIAL_BUSINESS_FIELDS",
        "BEGIN IMMEDIATE",
        "safety_stock_kg",
        "ORDER BY material_code, factory_id, id",
        "raw material master data conflict",
        "LOCK TABLE raw_materials IN ACCESS EXCLUSIVE MODE",
        "UPDATE raw_materials SET factory_id = '*'",
        "uq_raw_materials_material_code",
        "ck_raw_materials_global_factory",
        "irreversible",
    ):
        assert expected in raw_material_shared_content
    raw_material_upgrade_source = raw_material_shared_content.split(
        "def upgrade() -> None:",
        1,
    )[1].split("def downgrade() -> None:", 1)[0]
    assert raw_material_upgrade_source.index(
        "_acquire_sqlite_write_lock(connection)"
    ) < raw_material_upgrade_source.index("SELECT id, factory_id, material_code")

    pricing_baseline_revision = script.get_revision(
        INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION
    )
    assert pricing_baseline_revision.down_revision == INTERNAL_QUOTE_TARGET_PRICE_MIGRATION_REVISION
    pricing_baseline_content = Path(pricing_baseline_revision.path).read_text(encoding="utf-8")
    assert "internal_quote_pricing_baselines" in pricing_baseline_content
    assert "material_prices_json" in pricing_baseline_content
    assert "machine_prices_json" in pricing_baseline_content

    target_price_revision = script.get_revision(INTERNAL_QUOTE_TARGET_PRICE_MIGRATION_REVISION)
    assert target_price_revision.down_revision == IAM_POSITION_SCOPE_MIGRATION_REVISION
    target_price_content = Path(target_price_revision.path).read_text(encoding="utf-8")
    assert "target_customer_price" in target_price_content

    scope_revision = script.get_revision(IAM_POSITION_SCOPE_MIGRATION_REVISION)
    assert scope_revision.down_revision == INTERNAL_QUOTE_P4_MIGRATION_REVISION
    scope_content = Path(scope_revision.path).read_text(encoding="utf-8")
    assert "access_kind" in scope_content
    assert "scope_mode" in scope_content
    assert "cross_factory_read" in scope_content
    for permission_code in (
        "internal_quote:read",
        "internal_quote:summary_read",
        "internal_quote:timeline_read",
    ):
        assert permission_code in scope_content

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
        if name not in {
            "molding_sample_notifications",
            "molding_sample_problems",
            "molding_sample_trial_reports",
            "molding_sample_dispatch_logs",
        }
    ]:
        assert table_name in base_migration_content

    notification_revision = script.get_revision(NOTIFICATION_MIGRATION_REVISION)
    notification_migration_content = Path(notification_revision.path).read_text(encoding="utf-8")
    assert "molding_sample_notifications" in notification_migration_content


def test_internal_quote_customer_migration_seeds_factories_and_backfills_history(tmp_path):
    database_path = tmp_path / "internal_quote_customers_0029.db"
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
                "IQ-CUSTOMER-HISTORY",
                "huaxing",
                "huaxing-workshop",
                "华兴",
                "CUSTOMER-HISTORY",
                "历史客户产品",
                "历史客户",
                1000,
                "V1",
                "draft",
                "legacy-user",
                "历史用户",
                "2026-07-21 08:00:00",
                "2026-07-21 08:00:00",
                "sales",
            ),
        )
        connection.commit()

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,)
        assert "freight_routes_json" in {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('internal_quote_pricing_baselines')"
            ).fetchall()
        }
        counts = dict(connection.execute(
            """
            SELECT factory_id, COUNT(*)
            FROM internal_quote_customers
            GROUP BY factory_id
            ORDER BY factory_id
            """
        ).fetchall())
        assert counts == {
            "huakang-a": 5,
            "huakang-b": 5,
            "huakang-c": 5,
            "huakang-d": 5,
            "huadeng": 5,
            "huaxing": 6,
        }
        assert connection.execute(
            """
            SELECT name, normalized_name, revision
            FROM internal_quote_customers
            WHERE factory_id = 'huaxing' AND name = '历史客户'
            """
        ).fetchone() == ("历史客户", "历史客户", 1)

    run_alembic("downgrade", MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        assert "internal_quote_customers" not in tables
        assert connection.execute(
            "SELECT customer FROM internal_quotes WHERE id = 'IQ-CUSTOMER-HISTORY'"
        ).fetchone() == ("历史客户",)


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
            RAW_MATERIAL_SHARED_MIGRATION_REVISION,
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
        if table_name == "molding_sample_dispatch_logs":
            continue
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
    assert "target_customer_price" in sql
    assert "create table internal_quote_pricing_baselines" in sql
    assert "raw material master data conflict" in sql
    assert "lock table raw_materials in access exclusive mode" in sql
    assert "update raw_materials set factory_id = '*'" in sql
    assert "drop constraint uq_raw_materials_factory_code" in sql
    assert "add constraint uq_raw_materials_material_code unique (material_code)" in sql
    assert "add constraint ck_raw_materials_global_factory check (factory_id = '*')" in sql
    assert sql.index("lock table raw_materials in access exclusive mode") < sql.index(
        "raw material master data conflict"
    )


def test_raw_material_shared_sqlite_write_lock_blocks_competing_writer(tmp_path):
    database_path = tmp_path / "raw_material_shared_lock.db"
    with sqlite3.connect(database_path) as seed_connection:
        seed_connection.execute(
            "CREATE TABLE raw_materials (id TEXT PRIMARY KEY, factory_id TEXT NOT NULL)"
        )
        seed_connection.commit()

    config = Config(str(ALEMBIC_INI))
    migration_module = ScriptDirectory.from_config(config).get_revision(
        RAW_MATERIAL_SHARED_MIGRATION_REVISION
    ).module
    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as migration_connection:
            with migration_connection.begin():
                migration_module._acquire_sqlite_write_lock(migration_connection)
                assert migration_connection.connection.driver_connection.in_transaction

                with sqlite3.connect(database_path, timeout=0) as competing_connection:
                    try:
                        competing_connection.execute(
                            "INSERT INTO raw_materials (id, factory_id) VALUES (?, ?)",
                            ("RM-COMPETING", "huaxing"),
                        )
                        competing_connection.commit()
                    except sqlite3.OperationalError as error:
                        assert "locked" in str(error).lower()
                    else:
                        raise AssertionError(
                            "SQLite competing writer was not blocked by the 0027 write lock"
                        )
    finally:
        engine.dispose()


def test_raw_material_shared_sqlite_offline_has_controlled_online_only_error(
    tmp_path,
):
    database_path = tmp_path / "raw_material_shared_offline.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(ALEMBIC_INI),
            "upgrade",
            f"{INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION}:head",
            "--sql",
        ],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    output = f"{result.stdout}\n{result.stderr}".lower()
    assert "cannot run as sqlite offline sql" in output
    assert "run this revision in sqlite online mode" in output
    assert "notimplementederror" not in output
    assert "lock table raw_materials in access exclusive mode" not in output


def test_raw_material_shared_upgrade_merges_equivalent_rows_deterministically(
    tmp_path,
):
    database_path = tmp_path / "raw_material_shared_0026.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    def run_alembic(*arguments: str, expect_success: bool = True):
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if expect_success:
            assert result.returncode == 0, result.stderr
        return result

    run_alembic("upgrade", INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        rows = (
            (
                "RM-HX-91000001",
                "huaxing",
                "91000001",
                "ABS 750NSW",
                "ABS",
                "通用级",
                "KG/包",
                "供应商甲",
                50.0,
                "启用",
                "基准资料",
                "huaxing-seed",
                "2026-07-14 09:00:00",
                "2026-07-14 09:00:00",
            ),
            (
                "RM-HA-91000001",
                "huakang-a",
                "91000001",
                "ABS 750NSW",
                "ABS",
                "通用级",
                "KG/包",
                "供应商甲",
                50.0,
                "启用",
                "基准资料",
                "huakang-a-seed",
                "2026-07-14 10:00:00",
                "2026-07-14 10:00:00",
            ),
            (
                "RM-HX-92000030",
                "huaxing",
                "92000030",
                "单厂新增 PP",
                "PP",
                "共聚",
                "KG",
                "供应商乙",
                None,
                "启用",
                "只存在于一个厂区的额外资料",
                "user-engineer",
                "2026-07-20 09:00:00",
                "2026-07-20 09:00:00",
            ),
            (
                "RM-SHARED-93000001",
                "*",
                "93000001",
                "共享 PC",
                "PC",
                "透明",
                "KG",
                "供应商丙",
                10.0,
                "停用",
                "已归一资料",
                "shared-owner",
                "2026-07-20 08:00:00",
                "2026-07-20 08:00:00",
            ),
            (
                "RM-HD-93000001",
                "huadeng",
                "93000001",
                "共享 PC",
                "PC",
                "透明",
                "KG",
                "供应商丙",
                10.0,
                "停用",
                "已归一资料",
                "huadeng-owner",
                "2026-07-20 11:00:00",
                "2026-07-20 11:00:00",
            ),
        )
        connection.executemany(
            """
            INSERT INTO raw_materials (
                id, factory_id, material_code, material_name, category, spec,
                unit, supplier, safety_stock_kg, status, notes,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    run_alembic("upgrade", RAW_MATERIAL_SHARED_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        migrated = connection.execute(
            """
            SELECT id, factory_id, material_code, material_name, safety_stock_kg,
                   status, notes, created_by, created_at, updated_at
            FROM raw_materials
            ORDER BY material_code
            """
        ).fetchall()
        assert migrated == [
            (
                "RM-HA-91000001",
                "*",
                "91000001",
                "ABS 750NSW",
                50.0,
                "启用",
                "基准资料",
                "huakang-a-seed",
                "2026-07-14 10:00:00",
                "2026-07-14 10:00:00",
            ),
            (
                "RM-HX-92000030",
                "*",
                "92000030",
                "单厂新增 PP",
                None,
                "启用",
                "只存在于一个厂区的额外资料",
                "user-engineer",
                "2026-07-20 09:00:00",
                "2026-07-20 09:00:00",
            ),
            (
                "RM-SHARED-93000001",
                "*",
                "93000001",
                "共享 PC",
                10.0,
                "停用",
                "已归一资料",
                "shared-owner",
                "2026-07-20 08:00:00",
                "2026-07-20 08:00:00",
            ),
        ]
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RAW_MATERIAL_SHARED_MIGRATION_REVISION,)

        raw_material_table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'raw_materials'"
        ).fetchone()[0].lower()
        assert "constraint ck_raw_materials_global_factory check (factory_id = '*')" in (
            raw_material_table_sql
        )

        unique_index_columns = []
        for index_row in connection.execute("PRAGMA index_list('raw_materials')").fetchall():
            if index_row[2] != 1:
                continue
            unique_index_columns.append([
                column_row[2]
                for column_row in connection.execute(
                    f"PRAGMA index_info('{index_row[1]}')"
                ).fetchall()
            ])
        assert ["material_code"] in unique_index_columns
        assert ["factory_id", "material_code"] not in unique_index_columns

        insert_sql = """
            INSERT INTO raw_materials (
                id, factory_id, material_code, material_name, category, spec,
                unit, supplier, safety_stock_kg, status, notes,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        rejected_rows = (
            (
                "RM-INVALID-FACTORY",
                "huaxing",
                "94000001",
                "非法厂区原料",
            ),
            (
                "RM-DUPLICATE-CODE",
                "*",
                "91000001",
                "重复编号原料",
            ),
        )
        for material_id, factory_id, material_code, material_name in rejected_rows:
            try:
                connection.execute(
                    insert_sql,
                    (
                        material_id,
                        factory_id,
                        material_code,
                        material_name,
                        "ABS",
                        "",
                        "KG",
                        "",
                        None,
                        "启用",
                        "",
                        "test",
                        "2026-07-20 12:00:00",
                        "2026-07-20 12:00:00",
                    ),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
            else:
                raise AssertionError(
                    f"raw_materials constraints accepted invalid row {material_id}"
                )

    downgrade = run_alembic(
        "downgrade",
        INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION,
        expect_success=False,
    )
    assert downgrade.returncode != 0
    assert "irreversible" in f"{downgrade.stdout}\n{downgrade.stderr}"
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RAW_MATERIAL_SHARED_MIGRATION_REVISION,)


def test_raw_material_shared_upgrade_rejects_any_business_field_conflict(
    tmp_path,
):
    database_path = tmp_path / "raw_material_shared_conflict_0026.db"
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"

    def run_alembic(*arguments: str):
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    initial_upgrade = run_alembic(
        "upgrade",
        INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr

    base_values = {
        "material_name": "冲突基准原料",
        "category": "ABS",
        "spec": "通用级",
        "unit": "KG",
        "supplier": "供应商甲",
        "safety_stock_kg": 50.0,
        "status": "启用",
        "notes": "基准备注",
    }
    conflicting_values = {
        "material_name": "冲突后的原料名",
        "category": "PP",
        "spec": "高流动",
        "unit": "磅",
        "supplier": "供应商乙",
        "safety_stock_kg": None,
        "status": "停用",
        "notes": "不同备注",
    }
    conflict_codes: list[str] = []
    rows: list[tuple] = []
    for index, (field, conflicting_value) in enumerate(
        conflicting_values.items(),
        start=1,
    ):
        material_code = f"CONFLICT-{index:02d}"
        conflict_codes.append(material_code)
        for factory_id, suffix, overrides in (
            ("huakang-a", "A", {}),
            ("huaxing", "HX", {field: conflicting_value}),
        ):
            values = {**base_values, **overrides}
            rows.append(
                (
                    f"RM-{suffix}-{index:02d}",
                    factory_id,
                    material_code,
                    values["material_name"],
                    values["category"],
                    values["spec"],
                    values["unit"],
                    values["supplier"],
                    values["safety_stock_kg"],
                    values["status"],
                    values["notes"],
                    f"creator-{suffix}",
                    f"2026-07-20 {index:02d}:00:00",
                    f"2026-07-20 {index:02d}:30:00",
                )
            )

    with sqlite3.connect(database_path) as connection:
        connection.executemany(
            """
            INSERT INTO raw_materials (
                id, factory_id, material_code, material_name, category, spec,
                unit, supplier, safety_stock_kg, status, notes,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        connection.commit()

    rejected_upgrade = run_alembic("upgrade", "head")
    assert rejected_upgrade.returncode != 0
    migration_output = f"{rejected_upgrade.stdout}\n{rejected_upgrade.stderr}"
    assert "raw material master data conflict" in migration_output
    for material_code in conflict_codes:
        assert material_code in migration_output

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION,)
        assert connection.execute("SELECT COUNT(*) FROM raw_materials").fetchone() == (
            len(rows),
        )
        assert connection.execute(
            "SELECT COUNT(*) FROM raw_materials WHERE factory_id = '*'"
        ).fetchone() == (0,)


def test_iam_position_scope_upgrade_classifies_internal_quote_reads(tmp_path):
    database_path = tmp_path / "iam_position_scope_0023.db"
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

    run_alembic("upgrade", INTERNAL_QUOTE_P4_MIGRATION_REVISION)
    permission_codes = (
        "internal_quote:read",
        "internal_quote:summary_read",
        "internal_quote:timeline_read",
        "internal_quote:export",
    )
    with sqlite3.connect(database_path) as connection:
        for sort_order, permission_code in enumerate(permission_codes):
            permission_id = f"perm-{sort_order}"
            connection.execute(
                "INSERT INTO auth_permissions (id, code, name, description) VALUES (?, ?, ?, ?)",
                (permission_id, permission_code, permission_code, "migration test"),
            )
            connection.execute(
                """
                INSERT INTO auth_permission_metadata (
                    permission_id, module_code, action, risk_level, scope_type,
                    status, sort_order, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    permission_id,
                    "internal_quote",
                    permission_code.rsplit(":", 1)[-1],
                    "normal",
                    "factory",
                    "active",
                    sort_order,
                    "2026-07-17 00:00:00",
                    "2026-07-17 00:00:00",
                ),
            )
        connection.commit()

    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        access_kinds = dict(
            connection.execute(
                """
                SELECT permissions.code, metadata.access_kind
                FROM auth_permissions AS permissions
                JOIN auth_permission_metadata AS metadata
                  ON metadata.permission_id = permissions.id
                WHERE permissions.code LIKE 'internal_quote:%'
                """
            ).fetchall()
        )
        assert access_kinds == {
            "internal_quote:read": "read",
            "internal_quote:summary_read": "read",
            "internal_quote:timeline_read": "read",
            "internal_quote:export": "operate",
        }
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,
        )


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

    run_alembic("upgrade", INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION)
    with sqlite3.connect(database_path) as connection:
        quote = connection.execute(
            """
            SELECT quote_no, initiator_department, module_version, header_revision,
                   target_customer_price
            FROM internal_quotes WHERE id = 'IQ-LEGACY-P1'
            """
        ).fetchone()
        assert quote == ("LEGACY-P1", "sales-business", "legacy_rr2_compatible", 1, "无")
        audit = connection.execute(
            "SELECT factory_id, action FROM internal_quote_audit_logs WHERE id = 'IQA-LEGACY-P1'"
        ).fetchone()
        assert audit == ("huaxing", "create")
        assert connection.execute(
            "SELECT COUNT(*) FROM internal_quote_sections WHERE quote_id = 'IQ-LEGACY-P1'"
        ).fetchone() == (1,)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION,
        )

    run_alembic("downgrade", INTERNAL_QUOTE_ARCHIVE_MIGRATION_REVISION)
    run_alembic("upgrade", "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT quote_no FROM internal_quotes WHERE id = 'IQ-LEGACY-P1'"
        ).fetchone() == ("LEGACY-P1",)
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == (
            INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,
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

    run_alembic("upgrade", INTERNAL_QUOTE_PRICING_BASELINE_MIGRATION_REVISION)
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
            INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,
        )


def _run_dispatch_alembic(database_path: Path, *arguments: str):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *arguments],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_dispatch_init_db(database_path: Path):
    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    env["SEED_ADMIN_PASSWORD"] = "DispatchSchemaGate123!"
    env.pop("ALEMBIC_OFFLINE_METADATA_ONLY", None)
    return subprocess.run(
        [sys.executable, "-c", "from app.db import init_db; init_db()"],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _sqlite_schema_signature(database_path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(database_path) as connection:
        return connection.execute(
            """
            SELECT type, name, COALESCE(sql, '')
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """
        ).fetchall()


def test_sqlite_dispatch_schema_gate_preserves_0027_then_allows_alembic_upgrade(tmp_path):
    database_path = tmp_path / "molding_sample_dispatch_schema_gate.db"
    initial_upgrade = _run_dispatch_alembic(
        database_path,
        "upgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr
    schema_before_startup = _sqlite_schema_signature(database_path)

    blocked_startup = _run_dispatch_init_db(database_path)
    assert blocked_startup.returncode != 0
    startup_output = f"{blocked_startup.stdout}\n{blocked_startup.stderr}"
    assert MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION in startup_output
    assert "请先备份数据库并执行 Alembic 迁移" in startup_output
    assert _sqlite_schema_signature(database_path) == schema_before_startup

    migrated = _run_dispatch_alembic(database_path, "upgrade", "head")
    assert migrated.returncode == 0, migrated.stderr
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,)
        assert {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('molding_sample_orders')"
            ).fetchall()
        } >= {
            "production_factory_id",
            "production_assigned_at",
            "production_assigned_by",
            "production_assignment_version",
        }
        assert "molding_sample_dispatch_logs" in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def _insert_dispatch_test_order(
    connection: sqlite3.Connection,
    order_id: str,
    factory_id: str,
    status: str,
) -> None:
    connection.execute(
        """
        INSERT INTO molding_sample_orders (
            id, factory_id, order_number, doc_number, product_name, client_name,
            date, stage, order_type, workshop, send_to, supervisor, eng_name,
            reason, status, reject_reason, completed_date, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            order_id,
            factory_id,
            order_id,
            "",
            "迁移测试产品",
            "迁移测试客户",
            "2026-07-20",
            "T0",
            "啤办",
            "A车间",
            "",
            "迁移主管",
            "迁移工程师",
            "",
            status,
            "",
            "2026-07-20" if status == "已完成" else "",
            "2026-07-20 08:00:00",
            "2026-07-20 08:00:00",
        ),
    )


def _insert_dispatch_test_requisition(
    connection: sqlite3.Connection,
    requisition_id: str,
    order_id: str,
    batch_id: str,
    batch_no: str,
) -> None:
    connection.execute(
        """
        INSERT INTO molding_sample_requisitions (
            id, req_number, date, order_id, order_number, material,
            requested_weight_kg, applicant, notes, inventory_batch_id,
            inventory_batch_no, status, issued_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            requisition_id,
            f"REQ-{requisition_id}",
            "2026-07-20",
            order_id,
            order_id,
            "ABS",
            5.0,
            "迁移申请人",
            "",
            batch_id,
            batch_no,
            "已出库",
            "2026-07-20 09:00:00",
            "2026-07-20 08:30:00",
            "2026-07-20 09:00:00",
        ),
    )


def _insert_dispatch_test_batch(
    connection: sqlite3.Connection,
    batch_id: str,
    batch_no: str,
) -> None:
    connection.execute(
        """
        INSERT INTO molding_sample_inventory_batches (
            id, material, batch_no, location, initial_weight_kg,
            available_weight_kg, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            "ABS",
            batch_no,
            "测试仓",
            100.0,
            95.0,
            "2026-07-20 08:00:00",
            "2026-07-20 09:00:00",
        ),
    )


def _insert_dispatch_test_movement(
    connection: sqlite3.Connection,
    batch_id: str,
    batch_no: str,
    requisition_id: str = "",
    req_number: str = "",
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO molding_sample_inventory_movements (
            batch_id, batch_no, requisition_id, req_number, material,
            movement_type, quantity_kg, before_weight_kg, after_weight_kg,
            actor_name, reason, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            batch_id,
            batch_no,
            requisition_id,
            req_number,
            "ABS",
            "领料出库",
            5.0,
            100.0,
            95.0,
            "迁移仓管",
            "",
            "2026-07-20 09:00:00",
        ),
    )
    return int(cursor.lastrowid)


def test_molding_sample_dispatch_upgrade_backfills_scope_and_preserves_rows(tmp_path):
    database_path = tmp_path / "molding_sample_dispatch_0027.db"
    initial_upgrade = _run_dispatch_alembic(
        database_path,
        "upgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr

    order_rows = (
        ("ORDER-A", "huakang-a", "已完成"),
        ("ORDER-B", "huakang-b", "待审核"),
        ("ORDER-HD", "huadeng", "生产中"),
        ("ORDER-HX", "huaxing", "待生产"),
        ("ORDER-C-DRAFT", "huakang-c", "待审核"),
        ("ORDER-D-REJECTED", "huakang-d", "已驳回"),
    )
    with sqlite3.connect(database_path) as connection:
        for order_id, factory_id, status in order_rows:
            _insert_dispatch_test_order(connection, order_id, factory_id, status)

        _insert_dispatch_test_batch(connection, "BATCH-A", "LOT-A")
        _insert_dispatch_test_batch(connection, "BATCH-B", "LOT-B")
        _insert_dispatch_test_requisition(
            connection,
            "REQ-A",
            "ORDER-A",
            "BATCH-A",
            "LOT-A",
        )
        _insert_dispatch_test_requisition(
            connection,
            "REQ-B",
            "ORDER-B",
            "BATCH-B",
            "LOT-B",
        )
        movement_a = _insert_dispatch_test_movement(
            connection,
            "BATCH-A",
            "LOT-A",
            "REQ-A",
            "REQ-REQ-A",
        )
        movement_b = _insert_dispatch_test_movement(
            connection,
            "BATCH-B",
            "LOT-B",
            "REQ-B",
            "REQ-REQ-B",
        )
        tracked_tables = (
            "molding_sample_orders",
            "molding_sample_requisitions",
            "molding_sample_inventory_batches",
            "molding_sample_inventory_movements",
        )
        counts_before = {
            table_name: connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone()[0]
            for table_name in tracked_tables
        }
        connection.commit()

    migrated = _run_dispatch_alembic(database_path, "upgrade", "head")
    assert migrated.returncode == 0, migrated.stderr

    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (INTERNAL_QUOTE_BASELINE_FREIGHT_MIGRATION_REVISION,)
        assert connection.execute(
            """
            SELECT id, factory_id, production_factory_id,
                   production_assigned_at, production_assigned_by,
                   production_assignment_version
            FROM molding_sample_orders ORDER BY id
            """
        ).fetchall() == [
            ("ORDER-A", "huakang-a", "huakang-a", "", "", 0),
            ("ORDER-B", "huakang-b", "huakang-b", "", "", 0),
            ("ORDER-C-DRAFT", "huakang-c", None, "", "", 0),
            ("ORDER-D-REJECTED", "huakang-d", None, "", "", 0),
            ("ORDER-HD", "huadeng", "huadeng", "", "", 0),
            ("ORDER-HX", "huaxing", "huaxing", "", "", 0),
        ]
        assert connection.execute(
            "SELECT id, factory_id FROM molding_sample_requisitions ORDER BY id"
        ).fetchall() == [("REQ-A", "huakang-a"), ("REQ-B", "huakang-b")]
        assert connection.execute(
            "SELECT id, factory_id FROM molding_sample_inventory_batches ORDER BY id"
        ).fetchall() == [("BATCH-A", "huakang-a"), ("BATCH-B", "huakang-b")]
        assert connection.execute(
            "SELECT id, factory_id FROM molding_sample_inventory_movements ORDER BY id"
        ).fetchall() == [
            (movement_a, "huakang-a"),
            (movement_b, "huakang-b"),
        ]

        for table_name, expected_count in counts_before.items():
            assert connection.execute(
                f"SELECT COUNT(*) FROM {table_name}"
            ).fetchone() == (expected_count,)

        for table_name in (
            "molding_sample_requisitions",
            "molding_sample_inventory_batches",
            "molding_sample_inventory_movements",
        ):
            factory_column = next(
                row
                for row in connection.execute(
                    f"PRAGMA table_info('{table_name}')"
                ).fetchall()
                if row[1] == "factory_id"
            )
            assert factory_column[3] == 1
            assert (
                f"ix_{table_name}_factory_id"
                in {
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA index_list('{table_name}')"
                    ).fetchall()
                }
            )

        order_indexes = {
            row[1]
            for row in connection.execute(
                "PRAGMA index_list('molding_sample_orders')"
            ).fetchall()
        }
        assert "ix_molding_sample_orders_production_status_created_at" in order_indexes
        assert [
            row[2]
            for row in connection.execute(
                "PRAGMA index_info('ix_molding_sample_orders_production_status_created_at')"
            ).fetchall()
        ] == ["production_factory_id", "status", "created_at"]

        order_table_sql = connection.execute(
            """
            SELECT sql FROM sqlite_master
            WHERE type = 'table' AND name = 'molding_sample_orders'
            """
        ).fetchone()[0].lower()
        assert "ck_molding_sample_orders_production_factory" in order_table_sql
        assert "molding_sample_dispatch_logs" in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        dispatch_fk = connection.execute(
            "PRAGMA foreign_key_list('molding_sample_dispatch_logs')"
        ).fetchone()
        assert dispatch_fk[2] == "molding_sample_orders"
        assert dispatch_fk[6].upper() == "CASCADE"

        try:
            connection.execute(
                """
                UPDATE molding_sample_orders
                SET production_factory_id = 'huakang-c'
                WHERE id = 'ORDER-C-DRAFT'
                """
            )
            connection.commit()
        except sqlite3.IntegrityError:
            connection.rollback()
        else:
            raise AssertionError("production factory check accepted huakang-c")

    downgrade = _run_dispatch_alembic(
        database_path,
        "downgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert downgrade.returncode != 0
    assert "irreversible" in f"{downgrade.stdout}\n{downgrade.stderr}".lower()
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (MOLDING_SAMPLE_DISPATCH_MIGRATION_REVISION,)


def test_molding_sample_dispatch_preflight_rejects_huakang_cd_production_history(
    tmp_path,
):
    database_path = tmp_path / "molding_sample_dispatch_blocked_orders.db"
    initial_upgrade = _run_dispatch_alembic(
        database_path,
        "upgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr

    blocked_orders = (
        ("ORDER-C-WAITING", "huakang-c", "待生产"),
        ("ORDER-D-ACTIVE", "huakang-d", "生产中"),
        ("ORDER-C-DONE", "huakang-c", "已完成"),
    )
    with sqlite3.connect(database_path) as connection:
        for order_id, factory_id, status in blocked_orders:
            _insert_dispatch_test_order(connection, order_id, factory_id, status)
        connection.commit()

    rejected = _run_dispatch_alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    output = f"{rejected.stdout}\n{rejected.stderr}"
    assert "production destination must be assigned explicitly" in output
    for order_id, _, _ in blocked_orders:
        assert order_id in output

    with sqlite3.connect(database_path) as connection:
        order_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('molding_sample_orders')"
            ).fetchall()
        }
        assert "production_factory_id" not in order_columns
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RAW_MATERIAL_SHARED_MIGRATION_REVISION,)
        assert "molding_sample_dispatch_logs" not in {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }


def test_molding_sample_dispatch_preflight_rejects_unscoped_inventory(tmp_path):
    database_path = tmp_path / "molding_sample_dispatch_unscoped_inventory.db"
    initial_upgrade = _run_dispatch_alembic(
        database_path,
        "upgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr

    with sqlite3.connect(database_path) as connection:
        _insert_dispatch_test_batch(connection, "BATCH-UNKNOWN", "LOT-UNKNOWN")
        movement_id = _insert_dispatch_test_movement(
            connection,
            "BATCH-MISSING",
            "LOT-MISSING",
        )
        connection.commit()

    rejected = _run_dispatch_alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    output = f"{rejected.stdout}\n{rejected.stderr}"
    assert "cannot infer legacy inventory factory scope" in output
    assert "inventory_batches count=1" in output
    assert "BATCH-UNKNOWN" in output
    assert "inventory_movements count=1" in output
    assert str(movement_id) in output

    with sqlite3.connect(database_path) as connection:
        for table_name in (
            "molding_sample_requisitions",
            "molding_sample_inventory_batches",
            "molding_sample_inventory_movements",
        ):
            columns = {
                row[1]
                for row in connection.execute(
                    f"PRAGMA table_info('{table_name}')"
                ).fetchall()
            }
            assert "factory_id" not in columns
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RAW_MATERIAL_SHARED_MIGRATION_REVISION,)


def test_molding_sample_dispatch_preflight_does_not_treat_cd_origin_as_inventory_owner(
    tmp_path,
):
    database_path = tmp_path / "molding_sample_dispatch_cd_inventory.db"
    initial_upgrade = _run_dispatch_alembic(
        database_path,
        "upgrade",
        RAW_MATERIAL_SHARED_MIGRATION_REVISION,
    )
    assert initial_upgrade.returncode == 0, initial_upgrade.stderr

    with sqlite3.connect(database_path) as connection:
        _insert_dispatch_test_order(
            connection,
            "ORDER-C-DRAFT-INVENTORY",
            "huakang-c",
            "待审核",
        )
        _insert_dispatch_test_requisition(
            connection,
            "REQ-C-UNMAPPED",
            "ORDER-C-DRAFT-INVENTORY",
            "",
            "",
        )
        connection.commit()

    rejected = _run_dispatch_alembic(database_path, "upgrade", "head")
    assert rejected.returncode != 0
    output = f"{rejected.stdout}\n{rejected.stderr}"
    assert "cannot infer production factory scope" in output
    assert "REQ-C-UNMAPPED" in output

    with sqlite3.connect(database_path) as connection:
        assert "factory_id" not in {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info('molding_sample_requisitions')"
            ).fetchall()
        }
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == (RAW_MATERIAL_SHARED_MIGRATION_REVISION,)


def test_molding_sample_dispatch_offline_has_controlled_online_only_error(tmp_path):
    for database_url in (
        "postgresql+psycopg://postgres:postgres@localhost:5432/royal_regent_nexus",
        f"sqlite:///{(tmp_path / 'dispatch_offline.db').as_posix()}",
    ):
        env = os.environ.copy()
        env["DATABASE_URL"] = database_url
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "alembic",
                "-c",
                str(ALEMBIC_INI),
                "upgrade",
                f"{RAW_MATERIAL_SHARED_MIGRATION_REVISION}:head",
                "--sql",
            ],
            cwd=BACKEND_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode != 0
        output = f"{result.stdout}\n{result.stderr}".lower()
        assert "20260720_0028 cannot run as offline sql" in output
        assert "run this revision in online mode" in output
