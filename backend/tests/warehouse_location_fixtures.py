"""Explicit formal location catalogs for isolated warehouse tests."""
from contextlib import contextmanager
from uuid import uuid4
import importlib
import json
from test_molding_sample_api import make_client as empty_client

CODES = ('A', 'A1', 'A01', 'A02', 'B1', 'B03', '退料位', '隔离区')


def seed_fabric_locations(db):
    master = importlib.import_module('app.models.fabric_master')
    for model in (master.FabricMasterRecord, master.FabricMasterChange, master.FabricChaseResolution):
        model.__table__.create(db.get_bind(), checkfirst=True)
    for code in CODES:
        db.add(master.FabricMasterRecord(id=f'fabric-{code}', factory_id='huakang-c', kind='LOCATION', code=code, name=code,
            status='ACTIVE', revision=1, data_json=json.dumps({'warehouse': '布料一仓'}), updated_at='2026-07-01'))
    db.commit()


@contextmanager
def make_client(monkeypatch):
    with empty_client(monkeypatch) as client:
        db_module = importlib.import_module('app.db')
        master = importlib.import_module('app.models.fabric_master').FabricMasterRecord
        operation = importlib.import_module('app.models.warehouse_operations').WarehouseOperation
        with db_module.SessionLocal() as db:
            seed_fabric_locations(db)
            for i, code in enumerate(CODES, 1):
                record = dict(id=f'semi-{code}', warehouse='半成品一仓', code=code, label=f'半成品一仓／{code}', status='ACTIVE', revision=1)
                db.add(operation(id=f'semi-{code}', factory_id='huakang-c', warehouse='semi', sequence=i, request_id=str(uuid4()), request_hash='fixture',
                    kind='MASTER_LOCATION', business_date='2026-07-01', payload_json=json.dumps({'location_record': record}),
                    actor_id='fixture', actor_name='fixture', occurred_at='2026-07-01'))
            db.commit()
        yield client
