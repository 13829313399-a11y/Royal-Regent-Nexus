"""Reconcile the local SQLite checkout that used the BOM revision ID for V3 retirement.

Inspect with --database PATH. After taking a backup, stop the API and use --apply
to create the missing BOM schema from its published migration. The Alembic
version and business records are preserved.
"""

import argparse
import runpy
import sqlite3
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


BOM_MIGRATION = Path(__file__).resolve().parents[1] / "alembic/versions/20261104_0190_engineering_bom.py"
REVISIONS = {"20261104_0190", "20261104_0191", "20261104_0192", "20261107_0193"}
LEGACY_TABLE_PREFIXES = ("injection_v3_", "injection_schedule_", "injection_scheduling_")
LEGACY_PERMISSION_PREFIXES = ("injection_schedule_center:", "injection_scheduling:", "production:injection_scheduling:")


def create_bom(connection):
    with Operations.context(MigrationContext.configure(connection)):
        runpy.run_path(str(BOM_MIGRATION))["upgrade"]()


def bom_schema(connection):
    return connection.exec_driver_sql(
        "SELECT type, name, tbl_name, sql FROM sqlite_schema "
        "WHERE tbl_name IN ('engineering_bom_documents', 'engineering_bom_events') "
        "ORDER BY type, name"
    ).all()


def repair(database: Path, *, apply: bool = False) -> str:
    uri = database.resolve(strict=True).as_uri() + ("?mode=rw" if apply else "?mode=ro")
    reference_engine = sa.create_engine("sqlite://")
    try:
        with reference_engine.begin() as reference:
            create_bom(reference)
            expected = bom_schema(reference)
    finally:
        reference_engine.dispose()

    engine = sa.create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE" if apply else "BEGIN")
            tables = set(connection.exec_driver_sql("SELECT name FROM sqlite_schema WHERE type='table'").scalars())
            required = {"alembic_version", "auth_permissions", "internal_quote_pricing_baselines", "nexus_assistant_run_metrics"}
            if not required <= tables or any(name.startswith(LEGACY_TABLE_PREFIXES) for name in tables):
                raise ValueError("Expected the retired injection scheduling SQLite schema")
            revisions = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalars().all()
            if len(revisions) != 1 or revisions[0] not in REVISIONS:
                raise ValueError("Unrecognized migration history for the 0190 collision")
            revision = revisions[0]
            if revision >= "20261104_0191" and not {"material_plan_drafts", "material_plan_events"} <= tables:
                raise ValueError("Recorded 0191 material plan schema is missing")
            if revision >= "20261104_0192" and not {"material_purchase_documents", "material_purchase_events"} <= tables:
                raise ValueError("Recorded 0192 material purchase schema is missing")
            if revision == "20261107_0193":
                columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(internal_quote_pricing_baselines)")}
                if "paper_prices_json" not in columns:
                    raise ValueError("Recorded 0193 paper catalog is missing")
            permissions = connection.exec_driver_sql("SELECT code FROM auth_permissions").scalars()
            if any(code.startswith(LEGACY_PERMISSION_PREFIXES) for code in permissions):
                raise ValueError("Legacy injection permissions are still present")
            actual = bom_schema(connection)
            if actual == expected:
                return "already_repaired"
            if actual:
                raise ValueError("Partial or divergent engineering BOM schema requires separate review")
            if not apply:
                return "repair_required"
            create_bom(connection)
            if bom_schema(connection) != expected:
                raise RuntimeError("BOM schema verification failed")
            return "repaired"
    finally:
        engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(repair(args.database, apply=args.apply))
