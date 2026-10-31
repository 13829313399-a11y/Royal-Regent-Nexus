from dataclasses import replace
from decimal import Decimal
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _ensure_dickie_customer, _freeze_carton_time, _history_inventory_workbook_bytes


def test_policy_handoff_and_fresh_exception_authorization(monkeypatch):
    with make_client(monkeypatch) as client:
        base = '/api/carton-procurement'
        login_as(client, 'warehouse_keeper')
        _ensure_dickie_customer(client)
        login_as(client, 'warehouse_keeper')
        _freeze_carton_time(monkeypatch)
        content = _history_inventory_workbook_bytes([[
            'TIER-1', 'Dickie', '', 'TIER-C', 'TIER-I', '外箱', 'A33', '1*1*1',
            '个', 100, 20, 'CNY', 'A-01', '2026-08-01', 'OPEN-TIER', '', None]])
        response = client.post(base + '/inventory/history-imports', params={'factory_id': 'huaxing'}, files={'file': ('stock.xlsx', content)})
        assert response.status_code == 201, response.text
        policy = {'factory_id': 'huaxing', 'expected_revision': 0, 'amount_threshold': '501', 'ratio_threshold': '0.06', 'reason': '主管核对本厂盘点门槛'}
        assert client.get(base + '/stocktake-policy', params={'factory_id': 'huaxing'}).json()['amount_threshold'] == '500'
        assert client.put(base + '/stocktake-policy', json=policy).status_code == 403
        login_as(client, 'admin')
        updated = client.put(base + '/stocktake-policy', json=policy)
        assert updated.status_code == 200 and updated.json()['revision'] == 1, updated.text
        assert client.put(base + '/stocktake-policy', json=policy).status_code == 409
        assert client.get(base + '/stocktake-policy', params={'factory_id': 'huadeng'}).json()['revision'] == 0
        login_as(client, 'warehouse_keeper')
        balance = client.get(base + '/inventory/balances', params={'factory_id': 'huaxing'}).json()[0]
        doc = client.post(base + '/stocktakes', json={'factory_id': 'huaxing', 'reference_movement_ids': [balance['latest_movement_id']]}).json()
        path = base + '/stocktakes/' + doc['id']
        values = {'factory_id': 'huaxing', 'expected_revision': doc['revision'], 'action': 'CONFIRM', 'posting_confirmed': True,
                  'ledger_token': doc['ledger_token'], 'cutoff_acknowledged': True,
                  'lines': [{'id': doc['lines'][0]['id'], 'actual_quantity': '0', 'reason': '整仓差异请主管核实'}]}
        assert client.post(path + '/actions', json=values).status_code == 403
        doc = client.get(path, params={'factory_id': 'huaxing'}).json()
        assert doc['status'] == 'DRAFT' and Decimal(doc['lines'][0]['current_quantity']) == 100
        submitted = client.post(path + '/actions', json={**values, 'action': 'SUBMIT'})
        assert submitted.status_code == 200, submitted.text
        doc = submitted.json()
        login_as(client, 'admin')
        posted = client.post(path + '/actions', json={**values, 'expected_revision': doc['revision'], 'ledger_token': doc['ledger_token']})
        assert posted.status_code == 200, posted.text
        assert posted.json()['review_assessment']['policy']['revision'] == 1
        exception = client.get(base + '/exceptions', params={'factory_id': 'huaxing'}).json()['items'][0]
        assert exception['category'] == 'STOCKTAKE_REVIEW'
        update = {'factory_id': 'huaxing', 'expected_revision': exception['revision'], 'status': 'RESOLVED', 'resolution_note': ''}
        assert client.patch(base + '/exceptions/' + exception['id'], json=update).status_code == 422
        update['resolution_note'] = '主管复盘并核对凭证，确认该仓位实际无货'
        from app.db import SessionLocal
        from app.models.auth import AuthUser
        from app.services.auth import build_auth_context, AuthOverrideContext
        from app.api import carton_procurement as api
        identifier = client.get('/api/auth/me').json()['id']
        with SessionLocal() as db:
            actor = build_auth_context(db, db.get(AuthUser, identifier))
        fresh = api.get_current_user
        denied = replace(actor, overrides=actor.overrides + (AuthOverrideContext('revoked', 'carton_procurement:order_adjust', 'deny', 'huaxing', '*'),))
        monkeypatch.setattr(api, 'get_current_user', lambda **kwargs: denied)
        assert client.patch(base + '/exceptions/' + exception['id'], json=update).status_code == 403
        bulk = {'factory_id': 'huaxing', 'items': [{'id': exception['id'], 'expected_revision': exception['revision']}], 'status': 'RESOLVED', 'resolution_note': update['resolution_note']}
        assert client.post(base + '/exceptions/bulk-update', json=bulk).status_code == 403
        monkeypatch.setattr(api, 'get_current_user', fresh)
        assert client.post(base + '/exceptions/bulk-update', json=bulk).status_code == 200
        assert client.get(path, params={'factory_id': 'huaxing'}).json()['pending_review_count'] == 0
