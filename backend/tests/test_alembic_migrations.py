import os
import subprocess
import sys
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_DIR / "alembic.ini"
MIGRATION_REVISION = "20260701_0001"
MOLDING_SAMPLE_TABLES = [
    "molding_sample_orders",
    "molding_sample_items",
    "molding_sample_audit_logs",
    "molding_sample_material_prices",
    "molding_sample_settings",
    "molding_sample_auth_pins",
    "molding_sample_pin_attempts",
    "molding_sample_sensitive_audit_logs",
    "molding_sample_requisitions",
    "molding_sample_inventory_batches",
    "molding_sample_inventory_movements",
]


def test_alembic_has_single_molding_sample_head():
    assert ALEMBIC_INI.exists()

    config = Config(str(ALEMBIC_INI))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == [MIGRATION_REVISION]
    revision = script.get_revision(MIGRATION_REVISION)
    assert revision.down_revision is None

    migration_content = Path(revision.path).read_text(encoding="utf-8")
    for table_name in MOLDING_SAMPLE_TABLES:
        assert table_name in migration_content


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

    assert "foreign key(order_id) references molding_sample_orders" in sql
    assert "on delete cascade" in sql
    assert "create unique index ix_molding_sample_material_prices_material" in sql
    assert "create unique index ix_molding_sample_requisitions_req_number" in sql
