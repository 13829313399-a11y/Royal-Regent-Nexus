"""Repair one verified legacy SQLite state without editing historical migrations.

The supplier branch was recorded, while four pricing/quote tables were created
ahead of their migration records. Only matching tables can be adopted. Missing
indexes and immutable-snapshot triggers are restored from the original scripts.
The remaining schema changes still run through the real Alembic upgrade chain.
Run with the local API stopped; default mode is read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

import sqlalchemy as sa
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]
SUPPLIER_REVISION = "20260921_0118"
QUOTE_REVISION = "20260924_0119"
TABLES = (
    "customer_price_settings", "customer_price_settings_snapshots",
    "internal_quote_families", "internal_quote_alternatives",
)
SCRIPTS = (
    "20260922_0118_customer_price_settings.py",
    "20260924_0119_quote_alternatives.py",
)
IDENTITY_TABLES = {
    "employee_assignments", "iam_org_units", "iam_org_departments",
    "iam_role_versions", "iam_delegations", "iam_handover_items",
    "iam_outbox", "iam_mutation_receipts",
}


class RepairError(RuntimeError):
    pass


def quoted(name):
    return '"' + name.replace('"', '""') + '"'


def normalized_sql(sql):
    return re.sub(r"\s+", " ", sql.strip()).rstrip(";").casefold()


def contract(db, table):
    columns = {row[1]: (re.sub(r"\s+", "", row[2]).upper(), row[3], row[4], row[5])
               for row in db.execute(f"PRAGMA table_info({quoted(table)})")}
    foreign_keys = sorted(tuple(row[2:]) for row in db.execute(f"PRAGMA foreign_key_list({quoted(table)})"))
    indexes = {}
    unique_constraints = []
    for row in db.execute(f"PRAGMA index_list({quoted(table)})"):
        fields = tuple(r[2] for r in db.execute(f"PRAGMA index_info({quoted(row[1])})"))
        if row[3] == "u":
            unique_constraints.append(fields)
        elif row[3] != "pk":
            sql = db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (row[1],)).fetchone()[0]
            indexes[row[1]] = {"fields": fields, "unique": row[2], "partial": row[4], "sql": sql}
    triggers = dict(db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,)))
    return {"columns": columns, "foreign_keys": foreign_keys,
            "unique_constraints": sorted(unique_constraints), "indexes": indexes, "triggers": triggers}


def reference_contracts():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                for filename in SCRIPTS:
                    spec = importlib.util.spec_from_file_location("repair_reference_" + filename[:-3], BACKEND / "alembic/versions" / filename)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    module.upgrade()
            db = connection.connection.driver_connection
            return {table: contract(db, table) for table in TABLES}
    finally:
        engine.dispose()


def inspect_state(db):
    if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
        raise RepairError("Database integrity check failed")
    if db.execute("PRAGMA foreign_key_check").fetchall():
        raise RepairError("Existing foreign-key errors require separate review")
    revisions = [row[0] for row in db.execute("SELECT version_num FROM alembic_version ORDER BY version_num")]
    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
    head = script.get_current_head()
    current = revisions == [head]
    if current:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if IDENTITY_TABLES - tables:
            raise RepairError("Recorded head has missing identity tables; do not trust the revision alone")
        if "deleted_at" not in {row[1] for row in db.execute("PRAGMA table_info(carton_orders)")}:
            raise RepairError("Recorded head has missing carton deletion schema")
    elif revisions != [SUPPLIER_REVISION]:
        raise RepairError("Unsupported migration records: " + repr(revisions))
    ddl = []
    for table, expected in reference_contracts().items():
        actual = contract(db, table)
        for field in ("columns", "foreign_keys", "unique_constraints"):
            if actual[field] != expected[field]:
                raise RepairError(f"Schema mismatch: {table}.{field}; no migration records changed")
        for name, index in expected["indexes"].items():
            if name not in actual["indexes"]:
                ddl.append(index["sql"])
            elif any(actual["indexes"][name][key] != index[key] for key in ("fields", "unique", "partial")):
                raise RepairError("Index mismatch: " + name)
        for name, sql in expected["triggers"].items():
            if name not in actual["triggers"]:
                ddl.append(sql)
            elif normalized_sql(actual["triggers"][name]) != normalized_sql(sql):
                raise RepairError("Trigger mismatch: " + name)
    if current:
        if ddl:
            raise RepairError("Recorded head has missing migration indexes or triggers")
        return {"status": "already_current", "revision": head, "ddl": []}
    return {"status": "repair_required", "revision": revisions[0],
            "adopted_revisions": [SUPPLIER_REVISION, QUOTE_REVISION], "ddl": ddl}


def inspect_file(database):
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        return inspect_state(db)


def reconcile(database):
    """Validate, restore guards and stamp proven branches in one transaction."""
    engine = sa.create_engine(sa.URL.create("sqlite", database=str(database.resolve())))
    try:
        with engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                plan = inspect_state(connection.connection.driver_connection)
                if plan["status"] != "already_current":
                    for sql in plan["ddl"]:
                        connection.exec_driver_sql(sql)
                    context = MigrationContext.configure(connection)
                    script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
                    context.stamp(script, plan["adopted_revisions"])
                connection.commit()
                return plan
            except Exception:
                connection.rollback()
                raise
    finally:
        engine.dispose()


def apply_with_backup(database, backup_dir):
    database = database.resolve(strict=True)
    inspect_file(database)
    backup_dir.mkdir(parents=True, exist_ok=False)
    backup = backup_dir / "before-repair.db"
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RepairError("Backup verification failed")
    reconcile(database)
    env = dict(os.environ, DATABASE_URL="sqlite:///" + database.as_posix(), SEED_ADMIN_PASSWORD="")
    run = subprocess.run([sys.executable, "-m", "alembic", "-c", str(BACKEND / "alembic.ini"), "upgrade", "head"],
                         cwd=BACKEND, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180)
    (backup_dir / "upgrade.log").write_text(run.stdout + run.stderr, encoding="utf-8")
    if run.returncode:
        raise RepairError("Upgrade failed; API must remain stopped. Verified backup: " + str(backup))
    state = inspect_file(database)
    if state["status"] != "already_current":
        raise RepairError("Upgrade did not reach the current Alembic head")
    return {"status": "repaired", "revision": state["revision"], "backup": str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--backup-dir", type=Path)
    args = parser.parse_args()
    if args.apply and not args.backup_dir:
        parser.error("--apply requires a new --backup-dir; stop the local API first")
    if args.apply and args.backup_dir.resolve() == args.database.resolve():
        parser.error("Backup directory must be separate from the database")
    result = apply_with_backup(args.database, args.backup_dir) if args.apply else inspect_file(args.database)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
