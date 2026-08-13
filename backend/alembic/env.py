from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

if context.is_offline_mode():
    os.environ["ALEMBIC_OFFLINE_METADATA_ONLY"] = "1"

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings
from app.db import Base
from app.models import (
    ai_action,  # noqa: F401
    ai_artifact,  # noqa: F401
    ai_conversation,  # noqa: F401
    ai_guard,  # noqa: F401
    ai_observability,  # noqa: F401
    ai_task,  # noqa: F401
    auth,  # noqa: F401
    carton_procurement,  # noqa: F401
    customer_order,  # noqa: F401
    injection_scheduling,  # noqa: F401
    injection_scheduling_execution,  # noqa: F401
    injection_scheduling_export,  # noqa: F401
    injection_scheduling_import,  # noqa: F401
    injection_scheduling_phase5,  # noqa: F401
    injection_scheduling_scheduler,  # noqa: F401
    injection_scheduling_shared,  # noqa: F401
    internal_quote,  # noqa: F401
    molding_sample,  # noqa: F401
    pricing,  # noqa: F401
    raw_material,  # noqa: F401
    three_d_printing,  # noqa: F401
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_database_url() -> str:
    return settings.database_url.replace("%", "%%")


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
