from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

if context.is_offline_mode():
    os.environ["ALEMBIC_OFFLINE_METADATA_ONLY"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db import Base
from app.models import (
    collaboration,  # noqa: F401
    cutting_ops,  # noqa: F401
    assistant,  # noqa: F401
    work_center,  # noqa: F401
    uv_operations,  # noqa: F401
    spray_ops,  # noqa: F401
    document_tools,  # noqa: F401
    collaborative_sheets,  # noqa: F401
    auth,  # noqa: F401
    carton_mark,  # noqa: F401
    carton_feedback,  # noqa: F401
    carton_procurement,  # noqa: F401
    fabric_procurement,  # noqa: F401
    fabric_receiving,  # noqa: F401
    fabric_master,  # noqa: F401
    carton_stocktake,  # noqa: F401
    carton_positions,
    carton_master,  # noqa: F401
    carton_customer_assignment,  # noqa: F401
    carton_supplier_settlement,  # noqa: F401
    carton_supplier_portal,  # noqa: F401
    customer_order,  # noqa: F401
    customer_order_ledger,  # noqa: F401
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
