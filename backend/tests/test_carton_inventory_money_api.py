from decimal import Decimal as D
from test_molding_sample_api import make_client, login_as
from test_carton_procurement_api import _freeze_carton_time
from test_carton_transaction_guards_api import BASE, order, draft, confirm, outbound


def test_live_positions_and_paged_movements_share_full_valuation(monkeypatch):
    with make_client(monkeypatch) as client:
        login_as(client, 'admin')
        _freeze_carton_time(monkeypatch)
        row = order(client)
        assert confirm(client, draft(client, row, 10).json()).status_code == 200
        result = client.post(BASE + '/inventory/movements', json=outbound(row, 3))
        assert result.status_code == 201, result.text
        for endpoint in ['/inventory/positions', '/inventory/balances']:
            response = client.get(BASE + endpoint, params={'factory_id': 'huaxing'})
            assert response.status_code == 200, response.text
            stock = [r for r in response.json() if D(r['balance']) > 0][0]
            assert stock['cost_status'] == '已计价'
            assert D(stock['cost_amount']) == 14
            assert D(stock['cost_unit_price']) == 2
        response = client.get(BASE + '/inventory/movements', params={'factory_id': 'huaxing', 'limit': 1})
        assert response.status_code == 200, response.text
        item = response.json()['items'][0]
        assert item['movement_type'] == 'OUTBOUND'
        assert D(item['cost_amount']) == -6
        login_as(client, 'warehouse_keeper')
        assert client.get(BASE + '/inventory/positions', params={'factory_id': 'huadeng'}).status_code == 403
