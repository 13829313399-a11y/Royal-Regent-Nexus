"""Fair cutting admission must never replace or outlive the DB transaction."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.services import cutting_sqlite_queue as queue
from app.services.transaction_lock import lock_transaction


def queued(gate, count):
    deadline=monotonic()+3
    while monotonic()<deadline:
        with gate.condition:
            if len(gate.queue)==count:return
        sleep(.005)
    pytest.fail('Expected queued admission did not arrive')


@pytest.fixture
def engine(tmp_path):
    value=create_engine('sqlite:///'+str(tmp_path/'cutting.db'),connect_args={'check_same_thread':False,'timeout':.25})
    with value.begin() as db:db.exec_driver_sql('CREATE TABLE facts(id INTEGER PRIMARY KEY)')
    yield value
    value.dispose()


def test_fifo_prevents_new_readers_overtaking_waiters():
    gate=queue._Gate();owner=gate.acquire(0);order=[]
    def enter(i):
        token=gate.acquire(3)
        try:order.append(i)
        finally:gate.release(token)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[]
        for i in range(4):
            futures.append(pool.submit(enter,i));queued(gate,i+2)
        gate.release(owner)
        for future in futures:future.result(timeout=3)
    assert order==[0,1,2,3] and not gate.queue


def test_timed_out_waiter_does_not_block_following_admissions():
    gate=queue._Gate();owner=gate.acquire(0)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(gate.acquire,.02)
        with pytest.raises(TimeoutError):future.result(timeout=3)
    assert len(gate.queue)==1
    gate.release(owner);next_token=gate.acquire(0);gate.release(next_token)
    assert not gate.queue


@pytest.mark.parametrize('finish',['commit','rollback','close'])
def test_lease_lasts_to_root_completion_not_nested_savepoint(engine,finish):
    first=Session(engine);arrived=Event()
    lock_transaction(first,'cutting-master','huakang-c')
    gate=queue._engines[engine]
    def waiter():
        with Session(engine) as second:
            lock_transaction(second,'cutting-master','huakang-c');arrived.set();second.rollback()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future=pool.submit(waiter);queued(gate,2)
        with first.begin_nested():first.execute(text('INSERT INTO facts VALUES (1)'))
        assert not arrived.is_set() and len(gate.queue)==2
        getattr(first,finish)();future.result(timeout=3)
    first.close();assert arrived.is_set() and not gate.queue
    with Session(engine) as again:
        lock_transaction(again,'cutting-master','huakang-c');again.rollback()
        lock_transaction(again,'cutting-master','huakang-c');again.commit()
    assert not gate.queue


def test_external_database_writer_still_blocks_and_failure_releases_local_lease(engine):
    with engine.connect() as other,Session(engine) as db:
        other.exec_driver_sql('BEGIN IMMEDIATE')
        with pytest.raises(HTTPException) as error:lock_transaction(db,'cutting-master','huakang-c')
        assert error.value.status_code==409 and not db.in_transaction()
        assert not queue._engines[engine].queue
        other.rollback();lock_transaction(db,'cutting-master','huakang-c')
        assert db.connection().exec_driver_sql('PRAGMA busy_timeout').scalar_one()==250
        db.rollback()


def test_admission_timeout_rolls_back_without_releasing_the_actual_owner(engine):
    with Session(engine) as owner,Session(engine) as waiter:
        lock_transaction(owner,'cutting-master','huakang-c')
        with pytest.raises(HTTPException) as error:lock_transaction(waiter,'cutting-master','huakang-c')
        assert error.value.status_code==409 and not waiter.in_transaction()
        assert len(queue._engines[engine].queue)==1
        owner.rollback();lock_transaction(waiter,'cutting-master','huakang-c');waiter.rollback()
        assert not queue._engines[engine].queue


def test_existing_warehouse_writer_does_not_wait_for_cutting_queue(engine):
    gate=queue._Gate();token=gate.acquire(0)
    queue._engines[engine]=gate
    try:
        with Session(engine) as db:
            lock_transaction(db,'fabric-operations','huakang-c')
            lock_transaction(db,'cutting-master','huakang-c')
            assert queue._LEASE not in db.info
            db.rollback()
        assert len(gate.queue)==1
    finally:gate.release(token)


def test_engines_have_independent_local_queues(engine,tmp_path):
    other=create_engine('sqlite:///'+str(tmp_path/'other.db'))
    try:
        with Session(engine) as first,Session(other) as second:
            lock_transaction(first,'cutting-master','huakang-c')
            lock_transaction(second,'cutting-master','huakang-c')
            assert queue._engines[engine] is not queue._engines[other]
            second.rollback();first.rollback()
    finally:other.dispose()


def test_postgresql_keeps_its_database_advisory_lock(monkeypatch):
    monkeypatch.setattr(queue,'reserve',Mock(side_effect=AssertionError('SQLite queue used for PostgreSQL')))
    connection=Mock(dialect=SimpleNamespace(name='postgresql'));transaction=object()
    db=Mock(info={});db.connection.return_value=connection;db.get_transaction.return_value=transaction
    lock_transaction(db,'cutting-master','huakang-c')
    assert 'pg_advisory_xact_lock' in str(connection.execute.call_args.args[0])
    queue.reserve.assert_not_called();db.expire_all.assert_called_once()
