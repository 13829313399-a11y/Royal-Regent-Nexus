import importlib.util
from pathlib import Path
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text, inspect


def test_explicit_migration_preserves_calculated_orders_children_and_issued_snapshot():
    source = Path(__file__).parents[1] / "alembic/versions/20260909_0106_carton_explicit_quantities.py"
    spec = importlib.util.spec_from_file_location("explicit_migration", source)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE carton_orders (id TEXT PRIMARY KEY, product_order_quantity NUMERIC NOT NULL, CONSTRAINT ck_carton_order_product_quantity CHECK(product_order_quantity > 0))"))
        connection.execute(text("CREATE TABLE carton_order_lines (id TEXT PRIMARY KEY, order_id TEXT REFERENCES carton_orders(id), usage_quantity NUMERIC NOT NULL, required_quantity NUMERIC NOT NULL, CONSTRAINT ck_carton_order_line_usage CHECK(usage_quantity > 0), CONSTRAINT ck_carton_order_line_required CHECK(required_quantity > 0))"))
        connection.execute(text("CREATE TABLE carton_purchase_order_issues (id TEXT PRIMARY KEY, order_id TEXT REFERENCES carton_orders(id), before_product_quantity NUMERIC NOT NULL, after_product_quantity NUMERIC NOT NULL, product_quantity_delta NUMERIC NOT NULL, snapshot_json TEXT)"))
        connection.execute(text("INSERT INTO carton_orders VALUES ('O', 1200)"))
        connection.execute(text("INSERT INTO carton_order_lines VALUES ('L','O',12,100)"))
        connection.execute(text("INSERT INTO carton_purchase_order_issues VALUES ('I','O',0,1200,1200,'immutable')"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert tuple(connection.execute(text("SELECT * FROM carton_orders")).one()) == ('O',1200,'CALCULATED')
        assert tuple(connection.execute(text("SELECT * FROM carton_order_lines")).one()) == ('L','O',12,100)
        assert tuple(connection.execute(text("SELECT * FROM carton_purchase_order_issues")).one()) == ('I','O',0,1200,1200,'immutable')
        assert not connection.execute(text("PRAGMA foreign_key_check")).all()
        connection.execute(text("INSERT INTO carton_orders VALUES ('EX',NULL,'EXPLICIT')"))
        connection.execute(text("INSERT INTO carton_order_lines VALUES ('EL','EX',NULL,100)"))
        connection.execute(text("UPDATE carton_order_lines SET required_quantity=0 WHERE id='EL'"))
        with pytest.raises(Exception): connection.execute(text("INSERT INTO carton_orders VALUES ('BAD',NULL,'CALCULATED')"))
        with pytest.raises(Exception): connection.execute(text("INSERT INTO carton_orders VALUES ('BAD2',2,'GUESS')"))
        with pytest.raises(RuntimeError): migration.downgrade()
    engine.dispose()


def test_explicit_zero_is_only_accepted_when_preserving_a_preexisting_zero_line():
    from types import SimpleNamespace
    from decimal import Decimal
    from fastapi import HTTPException
    from app.schemas.carton_procurement import CartonOrderLineCreate
    from app.services.carton_procurement import _input_required
    row = CartonOrderLineCreate(packaging_type="外箱", unit="个", required_quantity=0)
    explicit = SimpleNamespace(quantity_basis="EXPLICIT", product_order_quantity=None)
    with pytest.raises(HTTPException): _input_required(explicit, row)
    assert _input_required(explicit, row, allow_zero=True) == 0
    calculated = SimpleNamespace(quantity_basis="CALCULATED", product_order_quantity=1200)
    with pytest.raises(HTTPException): _input_required(calculated, row)
    row.required_quantity = Decimal(101)
    row.usage_quantity = Decimal(12)
    row.paper_quality = "K3K"
    row.specification = "30*20*15"
    assert _input_required(explicit, row) == 101
    assert _input_required(calculated, row) == 100
