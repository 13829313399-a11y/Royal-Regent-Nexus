"""Opt-in real PostgreSQL acceptance. Requires a dedicated cutting_test database."""
import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from uuid import uuid4
from decimal import Decimal
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from app.models.customer_order_ledger import OrderLedgerLine as Line
from app.services import cutting_orders as orders, cutting_ops as c, cutting_schemas as s, customer_order_ledger as ledger
from app.schemas.customer_order_ledger import AmendIn

URL = os.getenv('CUTTING_TEST_POSTGRES_URL', '')
pytestmark = pytest.mark.skipif(not URL, reason='需要独立 PostgreSQL cutting_test 数据库，未配置 CUTTING_TEST_POSTGRES_URL')


@pytest.fixture
def pg_engine():
    url = make_url(URL)
    assert url.get_backend_name() == 'postgresql' and 'cutting_test' in (url.database or ''), '只允许专用 cutting_test 测试库'
    name = 'cutting_test_' + uuid4().hex
    admin = create_engine(url)
    engine = create_engine(url, connect_args={'options': f'-csearch_path={name} -clock_timeout=10000 -cstatement_timeout=15000'})
    with admin.begin() as db:
        db.execute(text(f'CREATE SCHEMA "{name}"'))
    try:
        tables = [t for t in Line.metadata.sorted_tables if t.name.startswith('order_ledger_')]
        Line.metadata.create_all(engine, tables=tables + list(c.TABLES) + list(orders.TABLES))
        yield engine
    finally:
        engine.dispose()
        assert name.startswith('cutting_test_') and len(name) == len('cutting_test_')+32
        with admin.begin() as db:
            db.execute(text(f'DROP SCHEMA "{name}" CASCADE'))
        admin.dispose()


def test_upstream_row_lock_prevents_stale_downstream_write(pg_engine, monkeypatch):
    actor = SimpleNamespace(id='synthetic-pg-user')
    with Session(pg_engine) as db:
        line = Line(id='source', factory_id='huakang-c', customer_code='test', customer_name='合成测试', identity_key='test',
            reference_no='0001', product_no='0002', quantity=Decimal('100'), shipped_quantity=0, status='active', version=1,
            revision=1, data={'requested_ship_date': '2026-12-01'}, created_at='2026-10-09', updated_at='2026-10-09')
        db.add(line); db.flush(); ledger.publish(db, line, ['cutting'], actor.id); db.commit()
        dispatch = orders.latest(db, 'source')
        body = s.ReceiveOrder(factory_id=c.FACTORY, operation_id=uuid4().hex, expected_version=0, reason='合成签收', dispatch_id=dispatch.id)
        c.command(db, actor, body, 'order_receive:source', lambda: orders.receive(db, actor, 'source', body))
    called = Event()
    original = orders.lock_source
    def locked_source(db, line_id):
        called.set()
        return original(db, line_id)
    monkeypatch.setattr(orders, 'lock_source', locked_source)
    def downstream():
        with Session(pg_engine) as db:
            body = s.Command(factory_id=c.FACTORY, operation_id=uuid4().hex, expected_version=1, reason='竞争中的旧版提交')
            try:
                c.command(db, actor, body, 'probe:source', lambda: orders.writable(db, 'source', 1))
            except HTTPException as error:
                return error.status_code
            return 200
    with ThreadPoolExecutor(max_workers=1) as pool:
        try:
            with Session(pg_engine) as db:
                line = db.scalar(select(Line).where(Line.id == 'source').with_for_update())
                future = pool.submit(downstream)
                assert called.wait(5), '下游未进入来源行锁检查'
                ledger.amend(db, line, AmendIn(expected_revision=line.revision, quantity='120', requested_ship_date='2026-12-02', note='', reason='上游持锁修改订单'), actor.id)
                db.commit()
            assert future.result(timeout=20) == 409
        finally:
            called.set()
