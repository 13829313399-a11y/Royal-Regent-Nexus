from __future__ import annotations

import os
import runpy
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool, inspect, text

if context.is_offline_mode():
    os.environ["ALEMBIC_OFFLINE_METADATA_ONLY"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db import Base
from app.models import (
    indonesia_materials,  # noqa: F401
    collaboration,  # noqa: F401
    cutting_ops,  # noqa: F401
    cutting_settlement,  # noqa: F401
    cutting_payment,  # noqa: F401
    assistant,  # noqa: F401
    work_center,  # noqa: F401
    uv_operations,  # noqa: F401
    spray_ops,  # noqa: F401
    document_tools,  # noqa: F401
    collaborative_sheets,  # noqa: F401
    online_documents,  # noqa: F401
    auth,  # noqa: F401
    position_review,  # noqa: F401
    carton_mark,  # noqa: F401
    carton_feedback,  # noqa: F401
    carton_procurement,  # noqa: F401
    carton_materials,  # noqa: F401
    fabric_procurement,  # noqa: F401
    fabric_receiving,  # noqa: F401
    fabric_master,  # noqa: F401
    material_handover,  # noqa: F401
    warehouse_operations,  # noqa: F401
    carton_stocktake,  # noqa: F401
    carton_positions,
    carton_master,  # noqa: F401
    carton_customer_assignment,  # noqa: F401
    carton_supplier_settlement,  # noqa: F401
    carton_supplier_portal,  # noqa: F401
    carton_special_requests,  # noqa: F401
    carton_price_review,  # noqa: F401
    customer_order,  # noqa: F401
    customer_order_ledger,  # noqa: F401
    huakang_b_jp,  # noqa: F401
    internal_quote,  # noqa: F401
    module_feedback,  # noqa: F401
    customer_price_settings,  # noqa: F401
    injection_scheduling,  # noqa: F401
    molding_sample,  # noqa: F401
    pricing,  # noqa: F401
    qc_inspection,  # noqa: F401
    raw_material,  # noqa: F401
    three_d_printing,  # noqa: F401
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    # Retired workspace tables are historical data, not autogenerate drop targets.
    if type_ == "table" and reflected and compare_to is None and name.startswith("uv_"):
        return False
    return True


def get_database_url() -> str:
    return settings.database_url.replace("%", "%%")


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", get_database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        inspector = inspect(connection)
        revisions = set(connection.scalars(text('SELECT version_num FROM alembic_version'))) if inspector.has_table('alembic_version') else set()
        later_successors = {'20261022_0175', '20261023_0176', '20261026_0177', '20261026_0178', '20261026_0179', '20261026_0180', '20261026_0181', '20261026_0182', '20261026_0183', '20261026_0184', '20261028_0185', '20261028_0186'}
        collision_versions = {'20261015_0163', '20261016_0164', '20261016_0165', '20261016_0166',
                              '20261017_0167', '20261019_0167', '20261020_0168',
                              '20261019_0168', '20261019_0169', '20261019_0170', '20261020_0171',
                              '20261021_0169', '20261021_0172', '20261022_0173', '20261022_0174', '20261022_0175', '20261023_0176'}
        if revisions & (collision_versions | later_successors) or any(inspector.has_table(name) for name in (
            'cutting_ops_period_events', 'jp_intake_references', 'jp_intake_reference_events',
            'jp_intake_counters', 'jp_intake_exports', 'jp_intake_export_identities')):
            preflight = runpy.run_path(str(Path(__file__).parent / 'versions/20261017_0167_reconcile_cutting_jp_collision.py'))['preflight']
            # Extend successor recognition without rewriting the applied migration.
            if revisions in [{head} for head in later_successors] + [{'20261023_0176', '20261026_0177'}, {'20261023_0176', '20261026_0179'}, {'20261026_0178', '20261026_0179'}, {'20261023_0176', '20261026_0181'}, {'20261026_0178', '20261026_0181'}, {'20261026_0180', '20261026_0181'}, {'20261023_0176', '20261026_0183'}, {'20261026_0178', '20261026_0183'}, {'20261026_0180', '20261026_0183'}, {'20261026_0182', '20261026_0183'}]:
                preflight.__globals__['VALID_VERSIONS'].append(revisions)
            missing_groups = preflight(connection)
            if revisions & later_successors and any(missing_groups.values()):
                raise RuntimeError('Reconciled 0167 schema is incomplete; refusing automatic repair')
        if revisions & ({'20261021_0169', '20261021_0172', '20261022_0173', '20261022_0174'} | later_successors):
            validate_customer = runpy.run_path(str(Path(__file__).parent / 'versions/20261021_0172_merge_indonesia_customer_head.py'))['validate_customer_schema']
            validate_customer(connection)
        if revisions & ({'20261022_0173', '20261022_0174'} | later_successors):
            validate_options = runpy.run_path(str(Path(__file__).parent / 'versions/20261022_0173_indonesia_options.py'))['validate_options_schema']
            validate_options(connection)
        if revisions & ({'20261022_0174'} | later_successors):
            validate_shared = runpy.run_path(str(Path(__file__).parent / 'versions/20261022_0174_indonesia_shared_options.py'))['validate_shared_options_schema']
            validate_shared(connection)
        if revisions & later_successors:
            validate_rush = runpy.run_path(str(Path(__file__).parent / 'versions/20261022_0175_carton_order_rush_manual.py'))['validate_rush_schema']
            validate_rush(connection)
        if inspector.has_table('alembic_version') and inspector.has_table('warehouse_operations_documents'):
            revisions = set(connection.scalars(text('SELECT version_num FROM alembic_version')))
            if revisions & {'20261009_0150', '20261009_0151'}:
                if len(revisions) != 1:
                    raise RuntimeError('ambiguous warehouse revision collision; inspect history before upgrading')
                preflight = runpy.run_path(str(Path(__file__).parent / 'versions/20261009_0152_warehouse_operations.py'))['preflight_legacy']
                preflight(connection, before_cutting='20261009_0150' in revisions)
        # Reflection opens an implicit read transaction. Release it before
        # Alembic takes ownership of the actual migration transaction.
        connection.rollback()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
