import importlib
import sqlite3
import pytest
from test_carton_mark_assets_migration import _run_alembic


def test_feedback_migration_adds_private_tables_without_changing_business_data(tmp_path):
    path = tmp_path / "feedback.db"
    url = f"sqlite:///{path.as_posix()}"
    result = _run_alembic(url, "upgrade", "20261005_0135")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE preserved_business (id TEXT PRIMARY KEY, quantity INTEGER)")
        db.execute("INSERT INTO preserved_business VALUES ('existing', 17)")
    result = _run_alembic(url, "upgrade", "20261005_0136")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("SELECT * FROM preserved_business").fetchall() == [("existing", 17)]
        assert db.execute("SELECT COUNT(*) FROM carton_feedback").fetchone()[0] == 0
        db.execute("""INSERT INTO carton_feedback VALUES ('fb','huaxing','u','员工','问题','说明','/module','OPEN',1,'key','hash','now','now')""")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO carton_feedback_images VALUES ('image','huakang-a','fb','now',X'00',0)")
    result = _run_alembic(url, "downgrade", "20261005_0135")
    assert result.returncode != 0 and "RuntimeError" in result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT COUNT(*) FROM carton_feedback").fetchone()[0] == 1


def test_startup_guard_refuses_partial_feedback_schema(monkeypatch, tmp_path):
    from sqlalchemy import create_engine
    db_module = importlib.import_module("app.db")
    engine = create_engine(f"sqlite:///{tmp_path / 'partial.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE auth_users (id TEXT PRIMARY KEY)")
    monkeypatch.setattr(db_module, "engine", engine)
    with pytest.raises(RuntimeError, match="Alembic"):
        db_module.ensure_carton_feedback_schema_ready()
    engine.dispose()
