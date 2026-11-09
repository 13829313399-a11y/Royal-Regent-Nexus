"""Equivalent supplier reads with bounded SQL and fresh per-call inputs."""
from time import perf_counter

from sqlalchemy import event, select
from test_carton_asset_library_loading import isolated
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _order_payload, _submit_order
from test_carton_supplier_portal import setup_portal, accept_all, ship_payload, receive_payload


def test_supplier_workspace_and_change_tasks_match_canonical_reads_with_less_sql(monkeypatch):
    with make_client(monkeypatch) as client:
        setup_portal(client)
        order = accept_all(client)
        sent = client.post('/api/carton-supplier/shipments', json=ship_payload(order))
        assert sent.status_code == 201, sent.text
        login_as(client, 'admin')
        shipment = sent.json()
        received = client.post('/api/carton-supplier/internal/shipments/' + shipment['id'] + '/receive', json=receive_payload(client, shipment))
        assert received.status_code == 200, received.text
        for index in range(4):
            payload = _order_payload(); payload['contract_no'] = f'LOAD-{index}'
            created = client.post('/api/carton-procurement/orders', json=payload)
            assert created.status_code == 201, created.text
            _submit_order(client, created.json())
        from app.db import SessionLocal, engine
        from app.models.auth import AuthUser
        from app.models.carton_procurement import CartonOrder
        from app.services.auth import build_auth_context
        from app.services import carton_supplier_portal as portal, carton_supplier_changes as changes, carton_supplier_projection as inputs
        counts = []
        def measure(read):
            with SessionLocal() as db:
                actor = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == 'admin')))
                calls = [0]
                def counted(*args): calls[0] += 1
                event.listen(engine, 'before_cursor_execute', counted)
                started = perf_counter()
                try: result = read(db, actor)
                finally: event.remove(engine, 'before_cursor_execute', counted)
                counts.append((calls[0], round(perf_counter() - started, 3)))
                return result
        def canonical_order_page(db, orders, *, internal=False):
            return [item for row in orders if (item := portal.order_out(db, row, internal=internal)) is not None]
        with monkeypatch.context() as baseline:
            baseline.setattr(inputs, 'order_page_out', canonical_order_page)
            old = measure(lambda db, user: portal.workspace(db, user, 'huaxing', internal=True, responsibility_scope='ALL'))
        new = measure(lambda db, user: portal.workspace(db, user, 'huaxing', internal=True, responsibility_scope='ALL'))
        assert new == old
        assert counts[1][0] < counts[0][0] / 2, counts
        tasks = measure(lambda db, user: changes.workspace(db, user, 'huaxing', internal=True))
        def canonical_tasks(db, user):
            result = []
            for item in tasks['items']:
                owner, version = changes._source(db, user, 'huaxing', item['source_kind'], item['source_id'], internal=True)
                result.append(changes._task(db, user, owner, version, item['source_kind'], internal=True))
            return result
        assert measure(canonical_tasks) == tasks['items']
        assert counts[2][0] < counts[3][0], counts
        with SessionLocal() as db:
            user = build_auth_context(db, db.scalar(select(AuthUser).where(AuthUser.username == 'admin')))
            row = db.scalar(select(CartonOrder).where(CartonOrder.factory_id == 'huaxing'))
            issue = portal.latest_issue(db, row)
            changes.record_response(db, user, row.factory_id, 'REGULAR', issue.id, 'DISPUTED', reason='隔离测试更新')
            db.commit()
        fresh = measure(lambda db, user: changes.workspace(db, user, 'huaxing', internal=True))
        assert any(item['status'] == 'DISPUTED' for item in fresh['items'])
        print('SUPPLIER_READS_SQL_SECONDS', counts)
