"""Canonical and unpublished-local migration paths on disposable databases."""
from io import StringIO
from pathlib import Path
import runpy
import warnings

from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
import pytest
import sqlalchemy as sa

BACKEND = Path(__file__).resolve().parents[1]
LEGACY = BACKEND / "alembic/legacy/20261013_0160_position_reviews.py"
PUBLISHED = BACKEND / "alembic/versions/20261013_0160_indonesia_materials.py"
CURRENT = BACKEND / "alembic/versions/20261014_0161_position_reviews.py"
HEAD = "20261014_0161"


def run_migration(path, connection):
    upgrade = runpy.run_path(str(path))["upgrade"]
    upgrade.__globals__["op"] = Operations(MigrationContext.configure(connection))
    upgrade()


@pytest.fixture
def database(tmp_path, monkeypatch):
    from app.core.config import settings

    url = f"sqlite:///{tmp_path / 'positions.db'}"
    monkeypatch.setattr(settings, "database_url", url)
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    engine = sa.create_engine(url)
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE auth_users(id VARCHAR(64) NOT NULL PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO auth_users VALUES ('original-user')")
        connection.exec_driver_sql("CREATE TABLE unrelated_business(id INTEGER PRIMARY KEY, payload TEXT)")
        connection.exec_driver_sql("INSERT INTO unrelated_business VALUES (1, 'preserve exactly')")
        connection.exec_driver_sql("CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)")
    yield engine, config
    engine.dispose()


def prepare(engine, *, legacy=False, material=False, version="20261013_0160"):
    with engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO alembic_version VALUES (:version)"), {"version": version})
        if material:
            run_migration(PUBLISHED, connection)
            connection.exec_driver_sql("INSERT INTO indonesia_material_records VALUES "
                "('original-material', 'huakang-a', 'material', 'original', 1, '{}', '2026-10-14')")
        if legacy:
            run_migration(LEGACY, connection)
            metadata = sa.MetaData()
            reviews = sa.Table("position_reviews", metadata, autoload_with=connection)
            values = {c.name: 1 if isinstance(c.type, sa.Integer) else "" for c in reviews.columns}
            values.update(id="original-review", user_id="original-user", initiator_user_id="original-user",
                reviewer_user_id=None, origin="employee", status="pending", declared_snapshot_json='{"position":"original"}')
            connection.execute(reviews.insert().values(**values))
            connection.exec_driver_sql("INSERT INTO position_review_events VALUES "
                "('original-event', 'original-review', 1, 'original-user', 'submitted', '{}', '{}', '', '2026-10-14')")


def snapshot(engine):
    with engine.connect() as connection:
        tables = sa.inspect(connection).get_table_names()
        quote = connection.dialect.identifier_preparer.quote
        return {
            "schema": connection.exec_driver_sql("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").all(),
            "rows": {table: connection.exec_driver_sql(f"SELECT * FROM {quote(table)}").all() for table in tables},
        }


def test_migration_graph_has_unique_revisions_and_canonical_parent():
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        script = ScriptDirectory.from_config(Config(str(BACKEND / "alembic.ini")))
        assert script.get_heads() == [HEAD]
        assert script.get_revision(HEAD).down_revision == "20261013_0160"
        assert script.get_revision("20261013_0160").down_revision == "20261012_0159"
        assert Path(script.get_revision("20261013_0160").path) == PUBLISHED


@pytest.mark.parametrize("parent", ["20261012_0159", "20261013_0160"])
def test_normal_upgrade_preserves_other_rows(database, parent):
    engine, config = database
    prepare(engine, material=parent == "20261013_0160", version=parent)
    before = snapshot(engine)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot(engine)
    for table, rows in before["rows"].items():
        if table != "alembic_version":
            assert after["rows"][table] == rows
    assert after["rows"]["alembic_version"] == [(HEAD,)]
    assert after["rows"]["position_reviews"] == []
    with engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize("material", [False, True])
def test_exact_local_schema_is_adopted_and_missing_published_migration_runs(database, material):
    engine, config = database
    prepare(engine, legacy=True, material=material)
    before = snapshot(engine)
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    after = snapshot(engine)
    for table, rows in before["rows"].items():
        if table != "alembic_version":
            assert after["rows"][table] == rows
    assert set(before["schema"]) <= set(after["schema"])
    assert after["rows"]["alembic_version"] == [(HEAD,)]
    with engine.begin() as connection:
        assert connection.exec_driver_sql("PRAGMA integrity_check").all() == [("ok",)]
        assert connection.exec_driver_sql("PRAGMA foreign_key_check").all() == []
        connection.exec_driver_sql("INSERT INTO indonesia_material_commands VALUES "
            "('command', 'huakang-a', 'original-user', 'create', 'fingerprint', '{}', '{}', '2026-10-14')")
        with pytest.raises(sa.exc.IntegrityError, match="immutable Indonesia material evidence"):
            connection.exec_driver_sql("DELETE FROM indonesia_material_commands")


@pytest.mark.parametrize("drift", [
    "ALTER TABLE position_reviews ADD COLUMN unexpected TEXT",
    "DROP INDEX uq_position_review_open",
    "CREATE UNIQUE INDEX unexpected_uniqueness ON position_reviews (user_id)",
    "CREATE TRIGGER unexpected_guard BEFORE DELETE ON position_reviews BEGIN SELECT RAISE(ABORT, 'unexpected'); END",
    "DROP TABLE position_review_events",
    "CREATE TABLE indonesia_material_records(id TEXT PRIMARY KEY)",
])
def test_legacy_drift_is_rejected_before_any_changes(database, drift):
    engine, config = database
    prepare(engine, legacy=True)
    with engine.begin() as connection:
        connection.exec_driver_sql(drift)
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="schema drift|Partial Indonesia"):
        command.upgrade(config, "head")
    assert snapshot(engine) == before


def test_partial_index_predicate_drift_is_rejected(database):
    engine, config = database
    prepare(engine, legacy=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP INDEX uq_position_review_open")
        connection.exec_driver_sql("CREATE UNIQUE INDEX uq_position_review_open "
            "ON position_reviews (user_id, employment_epoch) WHERE status IN ('pending')")
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="schema drift"):
        command.upgrade(config, "head")
    assert snapshot(engine) == before


def test_missing_published_immutable_trigger_is_rejected(database):
    engine, config = database
    prepare(engine, legacy=True, material=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("DROP TRIGGER indonesia_material_assets_delete")
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="Published Indonesia material schema drift"):
        command.upgrade(config, "head")
    assert snapshot(engine) == before


def test_foreign_key_damage_is_rejected_before_missing_material_ddl(database):
    engine, config = database
    prepare(engine, legacy=True)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE position_review_events SET actor_id='missing-user'")
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="foreign-key damage"):
        command.upgrade(config, "head")
    assert snapshot(engine) == before


def test_original_published_ddl_failure_rolls_back_all_new_tables(database):
    engine, config = database
    prepare(engine, legacy=True)
    with engine.begin() as connection:
        # An unrelated pre-existing index occupies a canonical name. The
        # original migration fails after CREATE TABLE, which must roll back.
        connection.exec_driver_sql("CREATE INDEX ix_indonesia_material_records_factory_id "
            "ON unrelated_business (payload)")
    before = snapshot(engine)
    with pytest.raises(sa.exc.OperationalError, match="already exists"):
        command.upgrade(config, "head")
    assert snapshot(engine) == before


def test_populated_downgrade_preserves_both_domains(database):
    engine, config = database
    prepare(engine, legacy=True)
    command.upgrade(config, "head")
    before = snapshot(engine)
    with pytest.raises(RuntimeError, match="history exists"):
        command.downgrade(config, "20261013_0160")
    assert snapshot(engine) == before


def test_normal_postgresql_ddl_compiles_with_partial_unique_guard():
    output = StringIO()
    operation = Operations(MigrationContext.configure(dialect_name="postgresql", opts={"as_sql": True, "output_buffer": output}))
    upgrade = runpy.run_path(str(CURRENT))["upgrade"]
    upgrade.__globals__["op"] = operation
    upgrade()
    sql = output.getvalue()
    assert "CREATE TABLE position_reviews" in sql
    assert "CREATE TABLE position_review_events" in sql
    assert "CREATE UNIQUE INDEX uq_position_review_open" in sql
    assert "WHERE status IN ('pending','returned')" in sql
    assert "indonesia_material" not in sql
