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


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from app.models import auth  # noqa: F401
    from app.models import molding_sample  # noqa: F401
    from app.services.auth import seed_auth_defaults
    from app.services.molding_sample import seed_molding_sample_defaults

    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        seed_auth_defaults(db)
        seed_molding_sample_defaults(db)
