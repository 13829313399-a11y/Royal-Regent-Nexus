"""A fixed, local-only trial database; never opens a Nexus database URL."""
from pathlib import Path

from fastapi import Request
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


APPLICATION_ID = 0x4A505452  # JPTR
SCHEMA_VERSION = 1
TABLES = frozenset({"order_ledger_sources", "jp_intake_references", "jp_intake_reference_events",
    "jp_intake_counters", "jp_intake_exports", "jp_intake_export_identities"})
IMMUTABLE = ("order_ledger_sources", "jp_intake_reference_events", "jp_intake_exports", "jp_intake_export_identities")
TRIGGERS = {f"{table}_no_{action}" for table in IMMUTABLE for action in ("update", "delete")}


class Database:
    def __init__(self, data_dir):
        # Import only the six trial tables, not the production model registry.
        from app.models import customer_order_ledger, huakang_b_jp  # noqa: F401

        directory = Path(data_dir).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "jp-trial.sqlite3"
        self.engine = create_engine("sqlite:///" + self.path.as_posix(),
            connect_args={"check_same_thread": False, "timeout": 5})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")

        try:
            self.initialize()
        except BaseException:
            self.engine.dispose()
            raise
        self.session = sessionmaker(self.engine, expire_on_commit=False, autoflush=False)

    def initialize(self):
        with self.engine.begin() as connection:
            identity = connection.exec_driver_sql("PRAGMA application_id").scalar()
            revision = connection.exec_driver_sql("PRAGMA user_version").scalar()
            names = set(inspect(connection).get_table_names())
            if identity == 0 and revision == 0 and not names:
                connection.exec_driver_sql("BEGIN IMMEDIATE")
                Base.metadata.create_all(connection)
                for table in IMMUTABLE:
                    for action in ("update", "delete"):
                        connection.exec_driver_sql(f"CREATE TRIGGER {table}_no_{action} BEFORE {action.upper()} ON {table} "
                            "BEGIN SELECT RAISE(ABORT, 'JP trial evidence is immutable'); END")
                connection.exec_driver_sql(f"PRAGMA application_id={APPLICATION_ID}")
                connection.exec_driver_sql(f"PRAGMA user_version={SCHEMA_VERSION}")
            elif identity != APPLICATION_ID or revision != SCHEMA_VERSION:
                raise RuntimeError("数据文件不是此版本的 JP 单机试用库，请保留原文件并联系提供者。")
            schema = inspect(connection)
            if set(schema.get_table_names()) != TABLES:
                raise RuntimeError("JP 试用库结构不完整；未自动重建或覆盖，请保留数据文件。")
            for name in TABLES:
                if {c["name"] for c in schema.get_columns(name)} != set(Base.metadata.tables[name].columns.keys()):
                    raise RuntimeError("JP 试用库字段不匹配；未覆盖已有数据。")
            actual = set(connection.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='trigger'").scalars())
            if not TRIGGERS.issubset(actual):
                raise RuntimeError("JP 试用库证据保护不完整；未自动修复已有数据。")

    def close(self):
        self.engine.dispose()


def get_db(request: Request):
    with request.app.state.database.session() as session:
        yield session
