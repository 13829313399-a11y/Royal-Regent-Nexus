"""Local recovery only: create the 0173 Indonesia option table when the DB is
already stamped 0173 but the table is missing.

This is not a replacement for a migration. Do not run it on production or any
database whose history you have not backed up and verified.
"""
from __future__ import annotations

import argparse
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

BACKEND_DIR = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND_DIR / 'alembic' / 'versions' / '20261022_0173_indonesia_options.py'
DEFAULT_DB = BACKEND_DIR / 'data' / 'royal_regent_nexus.db'


def load_migration():
    spec = spec_from_file_location('migration_0173', MIGRATION)
    module = module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', default=str(DEFAULT_DB), help='SQLite database path')
    parser.add_argument('--check', action='store_true', help='only report whether the table exists')
    args = parser.parse_args()

    engine = sa.create_engine('sqlite:///' + str(Path(args.database).resolve()))
    try:
        inspector = sa.inspect(engine)
        if inspector.has_table('indonesia_material_options'):
            print('indonesia_material_options already exists; nothing to do')
            return
        if args.check:
            print('indonesia_material_options is missing')
            return
        with engine.begin() as connection:
            with Operations.context(MigrationContext.configure(connection)):
                load_migration()._create_schema()
        print('created indonesia_material_options')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
