import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_timeline_index_preserves_receive_order_and_rows(tmp_path):
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261012_0157_three_d_printer_timeline_index.py"
    spec = importlib.util.spec_from_file_location("timeline_index_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine(f"sqlite:///{tmp_path / 'timeline.db'}")
    table = module.TABLE
    query = f"SELECT id FROM {table} WHERE factory_id='huakang-a' AND printer_id='p1' ORDER BY received_at DESC LIMIT 100"
    with engine.begin() as connection:
        connection.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, factory_id TEXT, printer_id TEXT, received_at TEXT, observed_at TEXT)"))
        connection.execute(text(f"INSERT INTO {table} VALUES (:id,:factory,:printer,:received,:observed)"), [
            {"id":n,"factory":"huakang-a","printer":"p1" if n % 2 else "p2","received":f"2026-10-12T01:{n//60:02d}:{n%60:02d}Z","observed":f"2026-10-12T00:{(240-n)//60:02d}:{(240-n)%60:02d}Z"}
            for n in range(240)
        ])
        before = connection.execute(text(query)).scalars().all()
        with Operations.context(MigrationContext.configure(connection)):
            module.upgrade()
        index = next(i for i in inspect(connection).get_indexes(table) if i["name"] == module.INDEX)
        assert index["column_names"] == ["factory_id", "printer_id", "received_at"]
        plan = str(connection.execute(text("EXPLAIN QUERY PLAN " + query)).all())
        assert module.INDEX in plan
        assert "TEMP B-TREE" not in plan
        assert connection.execute(text(query)).scalars().all() == before
        assert len(before) == 100 and before[0] == 239
        with Operations.context(MigrationContext.configure(connection)):
            module.downgrade()
        assert connection.execute(text(query)).scalars().all() == before
        assert connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() == 240
    engine.dispose()
