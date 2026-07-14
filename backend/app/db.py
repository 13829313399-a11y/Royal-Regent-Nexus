from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _create_engine():
    database_url = settings.database_url

    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)
        if db_path and db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        return create_engine(
            database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

    return create_engine(database_url, future=True)


engine = _create_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

SQLITE_LEGACY_COLUMNS = {
    "auth_users": [
        ("avatar_png", "avatar_png BLOB"),
        ("avatar_version", "avatar_version VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
    "molding_sample_items": [
        ("production_machine", "production_machine VARCHAR(128) NOT NULL DEFAULT ''"),
        ("mold_dimensions", "mold_dimensions VARCHAR(128) NOT NULL DEFAULT ''"),
        ("mold_presence_status", "mold_presence_status VARCHAR(20) NOT NULL DEFAULT 'unknown'"),
    ],
    "molding_sample_audit_logs": [
        ("actor_user_id", "actor_user_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("actor_roles", "actor_roles TEXT NOT NULL DEFAULT ''"),
        ("factory_scope", "factory_scope VARCHAR(255) NOT NULL DEFAULT ''"),
    ],
    "molding_sample_sensitive_audit_logs": [
        ("actor_user_id", "actor_user_id VARCHAR(64) NOT NULL DEFAULT ''"),
        ("actor_roles", "actor_roles TEXT NOT NULL DEFAULT ''"),
        ("factory_scope", "factory_scope VARCHAR(255) NOT NULL DEFAULT ''"),
    ],
    "system_notifications": [
        ("target_department", "target_department VARCHAR(64) NOT NULL DEFAULT ''"),
    ],
}


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ensure_sqlite_legacy_columns() -> None:
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as connection:
        for table_name, columns in SQLITE_LEGACY_COLUMNS.items():
            existing_columns = {
                row["name"]
                for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})").mappings()
            }
            if not existing_columns:
                continue

            for column_name, column_ddl in columns:
                if column_name not in existing_columns:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_ddl}")


def init_db() -> None:
    from app.models import auth  # noqa: F401
    from app.models import injection_schedule  # noqa: F401
    from app.models import molding_sample  # noqa: F401
    from app.models import pricing  # noqa: F401
    from app.models import raw_material  # noqa: F401
    from app.services.auth import seed_auth_defaults
    from app.services.molding_sample import seed_molding_sample_defaults
    from app.services.raw_material import seed_raw_material_defaults

    Base.metadata.create_all(bind=engine)
    ensure_sqlite_legacy_columns()

    with SessionLocal() as db:
        seed_auth_defaults(db)
        seed_molding_sample_defaults(db)
        seed_raw_material_defaults(db)
