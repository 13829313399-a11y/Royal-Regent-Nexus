import importlib.util
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text


def test_price_migration_preserves_original_receipts_and_refuses_evidence_loss():
    path = Path(__file__).parents[1] / 'alembic/versions/20261019_0170_carton_price_reviews.py'
    spec = importlib.util.spec_from_file_location('price_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE carton_receipt_lines (id TEXT PRIMARY KEY, factory_id TEXT NOT NULL, unit_price NUMERIC, UNIQUE(id,factory_id))'))
        connection.execute(text("INSERT INTO carton_receipt_lines VALUES ('RL1','huaxing',2)"))
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.execute(text('SELECT unit_price FROM carton_receipt_lines')).scalar_one() == 2
        assert connection.execute(text('SELECT COUNT(*) FROM carton_price_reviews')).scalar_one() == 0
        assert {'factory_id', 'supplier_id', 'receipt_line_id', 'original_unit_price', 'proposed_unit_price', 'revision'}.issubset({column['name'] for column in inspect(connection).get_columns('carton_price_reviews')})
        connection.execute(text("INSERT INTO carton_price_reviews VALUES ('CP1','huaxing','SUP1','RL1','REGULAR','SHIP1','SL1',2,3,'PROPOSED',1,'核价','u','u','2026-10-19')"))
        with pytest.raises(RuntimeError, match='Refusing'):
            module.downgrade()
