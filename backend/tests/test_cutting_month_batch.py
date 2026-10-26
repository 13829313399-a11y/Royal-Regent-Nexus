"""Monthly shared evidence must equal full per-order reads and remain scoped."""
from sqlalchemy import event
from sqlalchemy.orm import Session
import pytest
from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order
from test_cutting_http_capacity import add_dispatched_orders
from cutting_capacity_fixture import expand_chains
from app.services import cutting_closing as preview, cutting_periods as periods
from app.services import cutting_usage as usage, warehouse_operations as wh


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
        count=len(queries)
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
