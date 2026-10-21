"""Read-local reuse must still see later warehouse changes; writes stay fresh."""
from types import SimpleNamespace
import pytest
from sqlalchemy.orm import Session
from test_cutting_p5b_acceptance import client, flow, role_flow, prepare_closed_order, login, warehouse_post, BASE
from app.services import cutting_materials as materials
from app.services.transaction_lock import lock_transaction


def test_reader_is_lazy_transaction_bound_and_does_not_reuse_across_readers(monkeypatch):
    transaction = object()
    db = SimpleNamespace(get_transaction=lambda: transaction)
    calls = []
    monkeypatch.setattr(materials.wh, 'ensure_schema', lambda db: None)
    def projection(db, warehouse):
        calls.append(warehouse)
        return None, {'version':len(calls)}
    monkeypatch.setattr(materials.wh, 'projection', projection)
    reader = materials.receipt_reader(db)
    assert materials.receipt_evidence(db, {}, {}, receipt_entries=reader) == []
    assert not calls
    assert reader() == reader() and len(calls) == 1
    materials.receipt_reader(db)()
    assert len(calls) == 2
    transaction = object()
    with pytest.raises(RuntimeError, match='transactions'):
        reader()


def test_workspaces_reuse_one_projection_but_notice_next_request_return(role_flow, monkeypatch):
    p = role_flow
    prepare_closed_order(p)
    login(p, 'supervisor')
    original = materials.wh.projection
    calls = []
    def count(db, warehouse):
        calls.append(warehouse)
        return original(db, warehouse)
    monkeypatch.setattr(materials.wh, 'projection', count)
    def read(path, **params):
        calls.clear()
        result = p.get(BASE+'/workspace/'+path, params={'factory_id':'huakang-c', **params})
        assert result.status_code == 200, result.text
        assert calls == ['fabric']
        return result.json()
    assert read('planning')['stats']['scheduled'] == 1
    assert read('tasks', day='2026-10-15')['stats']['planned'] == 50
    login(p, 'warehouse')
    warehouse_post(p, 'RETURN', original_id=p.issue_id, quantity='1', location_id='bin', business_date='2026-12-14')
    login(p, 'supervisor')
    assert read('planning')['stats']['review'] == 1
    assert read('tasks', day='2026-10-15')['stats']['planned'] == 0
    with Session(p.engine) as db:
        lock_transaction(db, 'cutting-master', 'huakang-c')
        # Each reader belongs to this invocation, never session.info/global state.
        assert 'receipt_projection' not in db.info
