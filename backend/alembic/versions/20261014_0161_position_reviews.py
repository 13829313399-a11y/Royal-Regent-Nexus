"""Publish position reviews after the published Indonesia material revision.

The unpublished local position 0160 is retained byte-for-byte in ../legacy.
Only its exact SQLite schema is adopted. If it shadowed the published 0160,
execute that original migration after all read-only checks, without stamping.
"""
from pathlib import Path
import runpy

from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa

revision = "20261014_0161"
down_revision = "20261013_0160"
branch_labels = None
depends_on = None

ROOT = Path(__file__).resolve().parent
LEGACY = ROOT.parent / "legacy" / "20261013_0160_position_reviews.py"
PUBLISHED = ROOT / "20261013_0160_indonesia_materials.py"
POSITION_TABLES = ("position_reviews", "position_review_events")
MATERIAL_TABLES = ("indonesia_material_records", "indonesia_material_commands", "indonesia_material_assets")


def _run(path, operation, direction="upgrade"):
    function = runpy.run_path(str(path))[direction]
    function.__globals__["op"] = operation
    function()


def _sqlite_contract(bind, table):
    # Compare original SQL verbatim, including literals, checks, partial-index
    # predicates and immutable triggers. Never casefold/strip SQL contents or
    # silently recreate missing guards on an already populated table.
    return [tuple(row) for row in bind.execute(sa.text(
        "SELECT type, name, sql FROM sqlite_master WHERE tbl_name=:table "
        "ORDER BY type, name"
    ), {"table": table})]


def _expected_contracts():
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            operation = Operations(MigrationContext.configure(connection))
            _run(LEGACY, operation)
            _run(PUBLISHED, operation)
            return {name: _sqlite_contract(connection, name) for name in (*POSITION_TABLES, *MATERIAL_TABLES)}
    finally:
        engine.dispose()


def preflight_legacy(bind):
    """Read-only validation of the sole supported unpublished local collision."""
    if bind.dialect.name != "sqlite":
        raise RuntimeError("Pre-existing position schema requires a separately reviewed migration outside SQLite")
    expected = _expected_contracts()
    for name in POSITION_TABLES:
        if _sqlite_contract(bind, name) != expected[name]:
            raise RuntimeError(f"Local position schema drift: {name}; no migration may be adopted")
    present = [bool(_sqlite_contract(bind, name)) for name in MATERIAL_TABLES]
    if any(present) and not all(present):
        raise RuntimeError("Partial Indonesia material schema; inspect migration history before upgrading")
    if all(present):
        for name in MATERIAL_TABLES:
            if _sqlite_contract(bind, name) != expected[name]:
                raise RuntimeError(f"Published Indonesia material schema drift: {name}")
    else:
        inspector = sa.inspect(bind)
        if not inspector.has_table("alembic_version") or list(bind.scalars(sa.text(
            "SELECT version_num FROM alembic_version ORDER BY version_num"
        ))) != [down_revision]:
            raise RuntimeError("Unknown position revision collision; refusing to infer migration history")
    if bind.exec_driver_sql("PRAGMA quick_check").all() != [("ok",)]:
        raise RuntimeError("Database integrity check failed; position migration refused")
    if bind.exec_driver_sql("PRAGMA foreign_key_check").first():
        raise RuntimeError("Existing foreign-key damage; position migration refused")
    return {"adopt_position_schema": True, "restore_published_material_schema": not all(present)}


def upgrade():
    if op.get_context().as_sql:
        # Offline SQL represents the normal published chain, not a data-aware
        # adoption of an unknown local database.
        _run(LEGACY, op)
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if any(inspector.has_table(name) for name in POSITION_TABLES):
        plan = preflight_legacy(bind)
        if plan["restore_published_material_schema"]:
            # SQLite DDL is protected by a real savepoint, so a failed original
            # migration cannot leave a half-created module during adoption.
            with bind.begin_nested():
                _run(PUBLISHED, op)
        return
    if not all(inspector.has_table(name) for name in MATERIAL_TABLES):
        raise RuntimeError("Published Indonesia material migration is missing; position migration refused")
    _run(LEGACY, op)


def downgrade():
    # The original guard refuses to discard any position history. Indonesia
    # remains owned by the preceding published migration in both upgrade paths.
    _run(LEGACY, op, "downgrade")
