import json
from datetime import date, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models.customer_order_ledger import OrderLedgerLine
from app.models.shipping_mail import ShippingTask
from app.services.shipping_schedule_import import import_factory_schedule


def _session():
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_import_upserts_schedule_tasks_once():
    db = _session()
    ship_date = (date.today() + timedelta(days=10)).isoformat()
    db.add(OrderLedgerLine(
        id='line-1', factory_id='huaxing', customer_code='zuru', customer_name='ZURU',
        identity_key='idem-1', reference_no='SO-9001', product_no='77903TQ1',
        quantity=100, shipped_quantity=20, status='active', version=1, revision=1,
        data={
            'requested_ship_date': ship_date, 'port': '盐田', 'country': '德国',
            'contract_no': 'CT-9001', 'product_name_zh': '测试玩具', 'carton_count': 10,
        },
        created_at='2026-01-01T00:00:00', updated_at='2026-01-01T00:00:00',
    ))
    db.commit()

    first = import_factory_schedule(db, 'huaxing')
    assert first['created'] == 1
    task = db.scalar(select(ShippingTask).where(ShippingTask.factory_id == 'huaxing'))
    assert task is not None
    assert task.so_number == 'SO-9001'
    assert task.port == '盐田'
    assert task.destination_country == '德国'
    assert task.planned_ship_date == ship_date
    items = json.loads(task.items_json)
    assert items[0]['product_code'] == '77903TQ1'
    assert items[0]['quantity'] == 80
    assert items[0]['contract_no'] == 'CT-9001'

    second = import_factory_schedule(db, 'huaxing')
    assert second['created'] == 0
    assert second['updated'] == 1
    assert len(db.scalars(select(ShippingTask)).all()) == 1


def test_schedule_item_contract_fills_so_and_truck_lines():
    from app.services.shipping_bulk_truck import _line as bulk_line
    from app.services.shipping_loading import _line_from_item

    item = {'product_code': '77903TQ1', 'product_name': '测试玩具', 'quantity': 80,
            'cartons': 10, 'contract_no': 'CT-9001', 'customer_po': 'PO-1', 'country': '德国'}
    dk = _line_from_item(item, {})
    assert dk['contract'] == 'CT-9001'
    assert dk['quantity'] == 80
    truck = bulk_line(item, '', 'SO-9001')
    assert truck['contract'] == 'CT-9001'
    assert truck['so'] == 'SO-9001'


def test_history_mode_picks_old_shipped_orders():
    db = _session()
    db.add(OrderLedgerLine(
        id='line-old', factory_id='huaxing', customer_code='zuru', customer_name='ZURU',
        identity_key='idem-old', reference_no='SO-OLD-1', product_no='OLD-1',
        quantity=50, shipped_quantity=50, status='active', version=1, revision=1,
        data={'requested_ship_date': '2025-01-15', 'port': '盐田', 'country': '德国',
              'contract_no': 'CT-OLD', 'product_name_zh': '旧单玩具', 'carton_count': 5},
        created_at='2025-01-01T00:00:00', updated_at='2025-01-01T00:00:00',
    ))
    db.commit()

    daily = import_factory_schedule(db, 'huaxing')
    assert daily['created'] == 0

    history = import_factory_schedule(db, 'huaxing', include_history=True)
    assert history['created'] == 1
    task = db.scalar(select(ShippingTask).where(ShippingTask.so_number == 'SO-OLD-1'))
    assert task is not None
    items = json.loads(task.items_json)
    assert items[0]['quantity'] == 50
    assert items[0]['historical'] is True
