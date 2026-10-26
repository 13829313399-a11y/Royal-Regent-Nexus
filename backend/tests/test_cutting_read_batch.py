"""Compare batch reads with the existing per-order contracts on real API facts."""
from datetime import date
from sqlalchemy import event
from sqlalchemy.orm import Session
from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order
from test_cutting_http_capacity import add_dispatched_orders
from cutting_capacity_fixture import expand_chains
from app.services import cutting_workspace as workspace, cutting_reporting as reporting
from app.services import cutting_read_batch, cutting_cost_allocation as allocation, cutting_usage as usage


def test_batch_matches_individual_reads_and_uses_composite_versions(role_flow, monkeypatch):
    p = role_flow
    prepare_closed_order(p)
    add_dispatched_orders(p, 3)
    expand_chains(p, 3)
    queries = []
    def record(conn, cursor, sql, params, context, many):
        if 'FROM cutting_ops_production_events' in sql:
            queries.append(sql)
    event.listen(p.engine, 'before_cursor_execute', record)
    try:
        with Session(p.engine) as db:
            optimized_tasks = workspace.task_board(db, date(2026, 10, 15))
            assert len(queries) == 1
            queries.clear()
            optimized_costs = workspace.cost_overview(db)
            assert len(queries) == 1
            identities, captured = workspace.capture_materials(db, costs=True)
            assert not db.in_transaction() and captured['production'][0]
            assert captured['production'][2]
            assert all(not hasattr(row, '_sa_instance_state') for row in captured['production'][2].values())
            for identity in identities:
                with Session(p.engine) as individual_db:
                    assert usage.read(None, identity['line_id'], show_costs=True, _snapshot=captured) == usage.read(
                        individual_db, identity['line_id'], show_costs=True)
            docs, versions = cutting_read_batch.production(db, ['line-1', 'http-capacity-1', 'http-capacity-2'], revisions=True)
            assert {key[0] for key in versions} == {'line-1', 'http-capacity-1', 'http-capacity-2'}
            for line, documents in docs.items():
                assert documents == reporting.documents(reporting.events(db, line))
            # Missing plan history remains blocked, never borrows another order's version.
            selected = usage.read(db, 'line-1')['issues'][0]['context']
            assert allocation.production_basis(db, 'line-1', selected, docs['line-1'], True, versions)[2] == ''
            missing = dict(versions)
            missing = {key: value for key, value in missing.items() if key[0] != 'line-1'}
            _, _, reason = allocation.production_basis(db, 'line-1', selected, docs['line-1'], True, missing)
            assert reason
        def individual(db, q='', *, snapshot=None):
            if snapshot is not None:
                snapshot.pop('production', None)
            for dispatch, order, revision in workspace.sources(db, q):
                docs = reporting.documents(reporting.events(db, order.line_id)) if order and revision else {}
                yield dispatch, order, revision, docs
        monkeypatch.setattr(workspace, 'production_sources', individual)
        with Session(p.engine) as db:
            assert workspace.task_board(db, date(2026, 10, 15)) == optimized_tasks
            assert workspace.cost_overview(db) == optimized_costs
    finally:
        event.remove(p.engine, 'before_cursor_execute', record)
