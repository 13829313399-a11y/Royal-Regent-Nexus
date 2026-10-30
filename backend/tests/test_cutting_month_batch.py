"""Monthly shared evidence must equal full per-order reads and remain scoped."""
from sqlalchemy import event, update
from sqlalchemy.orm import Session
import pytest
from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order
from test_cutting_http_capacity import add_dispatched_orders
from cutting_capacity_fixture import expand_chains
from app.services import cutting_closing as preview, cutting_periods as periods
from app.services import cutting_usage as usage, warehouse_operations as wh
from app.services import cutting_orders as orders, cutting_period_guards as guards
from app.models.customer_order_ledger import OrderLedgerLine
from fastapi import HTTPException


def test_month_batch_matches_individual_contract_and_reads_ledgers_once(role_flow,monkeypatch):
    p=role_flow
    prepare_closed_order(p);add_dispatched_orders(p,3);expand_chains(p,3)
    queries=[]
    def record(conn,cursor,sql,params,context,many):queries.append(sql)
    event.listen(p.engine,'before_cursor_execute',record)
    try:
        with Session(p.engine) as db:
            optimized=periods.prepare(db,'2026-11')
            assert len(optimized['rows'])==6 and not optimized['blockers']
        for table in ('cutting_ops_material_events','warehouse_operations_documents','cutting_ops_production_events'):
            assert sum(('FROM '+table) in sql for sql in queries)==1, table
        assert sum('FROM cutting_ops_masters' in sql for sql in queries)==1
        count=len(queries)
        with Session(p.engine) as db:
            command_basis=periods.prepare(db,'2026-11',include_history=False)
        assert command_basis==dict(optimized,history=[])
        original=preview.month_reader
        def individual(db,line_ids,entries,history,uses):
            _,docs,versions=original(db,line_ids,entries,history,uses)
            return lambda line,month:preview.read(db,line,month,show_costs=True),docs,versions
        monkeypatch.setattr(preview,'month_reader',individual)
        queries.clear()
        with Session(p.engine) as db:
            baseline=periods.prepare(db,'2026-11')
        assert optimized==baseline
        assert count<len(queries)
    finally:event.remove(p.engine,'before_cursor_execute',record)


def test_shared_month_evidence_cannot_survive_transaction_or_scope_changes(role_flow):
    p=role_flow;prepare_closed_order(p)
    with Session(p.engine) as db:
        periods.prepare(db,'2026-11')
        _,entries=wh.projection(db,'fabric');history=usage.events(db)
        uses,_=usage.replay(entries,history)
        read,_,_=preview.month_reader(db,['line-1'],entries,history,uses)
        assert read('line-1','2026-11')['line_id']=='line-1'
        with pytest.raises(RuntimeError,match='scope'):read('unrelated','2026-11')
        db.rollback()
        with pytest.raises(RuntimeError,match='transactions'):read('line-1','2026-11')


def test_source_batch_preserves_missing_and_undispatched_version_fences(role_flow):
    p=role_flow;prepare_closed_order(p);add_dispatched_orders(p,3);expand_chains(p,3)
    ids=['line-1','http-capacity-1','http-capacity-2']
    with Session(p.engine) as db:
        orders.lock_sources(db,reversed(ids))
        for identifier in ids:orders.lock_source(db,identifier)
    with Session(p.engine) as db:
        db.execute(update(OrderLedgerLine).where(OrderLedgerLine.id==ids[1]).values(version=OrderLedgerLine.version+1));db.commit()
    for use_batch in (False,True):
        with Session(p.engine) as db:
            with pytest.raises(HTTPException) as error:
                orders.lock_sources(db,ids) if use_batch else orders.lock_source(db,ids[1])
            assert error.value.status_code==409 and '重新下发' in error.value.detail
        with Session(p.engine) as db:
            with pytest.raises(HTTPException) as error:
                orders.lock_sources(db,['not-in-factory']) if use_batch else orders.lock_source(db,'not-in-factory')
            assert error.value.status_code==404


def test_period_metadata_history_keeps_payload_deferred_until_explicitly_selected(role_flow):
    p=role_flow;prepare_closed_order(p)
    with Session(p.engine) as db:
        complete=guards.history(db)
        expected=[(e.id,e.month,e.version,e.action,e.data) for e in complete]
    from sqlalchemy import inspect
    with Session(p.engine) as db:
        summaries=guards.history(db,metadata_only=True)
        assert summaries and all('data' in inspect(e).unloaded for e in summaries)
        selected=summaries[-1]
        assert selected.data==expected[-1][-1]
        assert all('data' in inspect(e).unloaded for e in summaries[:-1])
        assert [(e.id,e.month,e.version,e.action) for e in summaries]==[e[:4] for e in expected]
    with Session(p.engine) as db:
        states=guards.history(db,state_only=True)
        assert all({'data','actor_name','reason','created_at'} <= inspect(e).unloaded for e in states)
        assert [(e.id,e.month,e.version,e.action) for e in states]==[e[:4] for e in expected]


def test_file_api_capture_matches_locked_contract_and_releases_writer(role_flow):
    p=role_flow;prepare_closed_order(p)
    with Session(p.engine) as db:
        expected=periods.read(db,'2026-10')
        expected_basis=periods.prepare(db,'2026-11')
    with Session(p.engine) as db:
        assert periods.read(db,'2026-10',release_read_lock=True)==expected
        assert not db.in_transaction()
    with Session(p.engine) as db:
        assert periods.prepare(db,'2026-11',release_read_lock=True)==expected_basis
        assert not db.in_transaction()


def test_captured_history_headers_exclude_later_immutable_events(role_flow):
    from copy import deepcopy
    from uuid import uuid4
    from app.models.cutting_period import CuttingPeriodEvent as E
    p=role_flow;prepare_closed_order(p)
    with Session(p.engine) as db:
        captured=guards.history(db)
        expected=periods.period_history(captured)
        last=captured[-1]
        later=dict(id=uuid4().hex,factory_id='huakang-c',month=last.month,version=last.version+1,
            action='reopen',data=deepcopy(last.data),actor_id='reviewer',actor_name='later actor',
            created_at=last.created_at,reason='later committed transition')
        db.rollback()
        with Session(p.engine) as writer:
            writer.add(E(**later));writer.commit()
        assert guards.frozen_headers(db,captured,guards.file_read(db,True))==expected
        assert not db.in_transaction()


def test_explicit_read_capture_does_not_discard_unsaved_business_objects(role_flow):
    from app.models.cutting_period import CuttingPeriodEvent as E
    p=role_flow
    with Session(p.engine) as db:
        pending=E(id='unsaved-test-only');db.add(pending)
        with pytest.raises(HTTPException) as error:guards.file_read(db,True)
        assert error.value.status_code==500 and pending in db.new


def test_migrated_header_index_keeps_full_and_selected_read_contract(role_flow):
    from app.services.cutting_period_header_index import NAME,COLUMNS
    p=role_flow;prepare_closed_order(p)
    with Session(p.engine) as db:
        expected=periods.read(db,'2026-10');event_id=expected['history'][0]['id']
        selected=periods.read(db,'2026-10',event_id)
    with p.engine.begin() as con:con.exec_driver_sql('CREATE INDEX '+NAME+' ON cutting_ops_period_events ('+','.join(COLUMNS)+')')
    with Session(p.engine) as db:
        assert periods.read(db,'2026-10',release_read_lock=True)==expected
        assert not db.in_transaction()
    with Session(p.engine) as db:
        assert periods.read(db,'2026-10',event_id,release_read_lock=True)==selected
        assert not db.in_transaction()
