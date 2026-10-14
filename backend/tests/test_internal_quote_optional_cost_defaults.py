import pytest

from test_internal_quote_api import create_payload, login, make_client
from test_internal_quote_alternatives import fork


def section(quote, code):
    return next(row for row in quote['sections'] if row['department'] == code)


@pytest.mark.parametrize('justplay', [False, True])
def test_new_products_default_costs_off_and_preserve_saved_choices_when_copied(monkeypatch, justplay):
    with make_client(monkeypatch) as client:
        login(client, 'optional-cost-owner', 'admin', '*', '*')
        body = create_payload(suffix=f'OPTIONAL-{justplay}')
        body.update(workflow_mode='direct_output', quote_type='series', products=[
            {'product_name': 'A款', 'qty': 1000}, {'product_name': 'B款', 'qty': 2000},
        ])
        if justplay:
            body.update(factory_id='huakang-b', workshop_code='huakang-b-workshop', customer='JustPlay', pricing_components=['主体'])
        created = client.post('/api/internal-quotes', json=body)
        assert created.status_code == 201, created.text
        quote = created.json()
        root = f"/api/internal-quotes/{quote['id']}"
        products = client.get(root + '/batch-products').json()
        assert len(products) == 2
        for product in products:
            saved = client.get(f"/api/internal-quotes/{product['quote_id']}").json()
            assert section(saved, 'engineering')['payload']['mold_allocation_enabled'] is False
            sales = section(saved, 'sales')['payload']
            assert sales['testing_fee_enabled'] is False
            assert sales['freight_calc'] == {'enabled': False, 'freight_enabled': False, 'lifting_enabled': False}
        engineering = section(quote, 'engineering')
        changed = client.put(root + '/sections/engineering', json={
            'revision': engineering['revision'], 'payload': {**engineering['payload'],
                'mold_allocation_enabled': True, 'production_mold_costs': [{'item': '模具费', 'cost_rmb': 7750}],
                'amortization_qty': 1000,
            },
        })
        assert changed.status_code == 200, changed.text
        sales = section(client.get(root).json(), 'sales')
        changed = client.put(root + '/sections/sales', json={
            'revision': sales['revision'], 'payload': {**sales['payload'],
                'testing_fee_enabled': True, 'testing_fee_total_usd': 100, 'testing_fee_moqs': [1000],
                'freight_calc': {'enabled': True, 'freight_enabled': True, 'lifting_enabled': False},
            },
        })
        assert changed.status_code == 200, changed.text
        saved = client.get(root).json()
        copied = fork(client, saved, 'version')
        for record in (saved, copied):
            assert section(record, 'engineering')['payload']['mold_allocation_enabled'] is True
            sales = section(record, 'sales')['payload']
            assert sales['testing_fee_enabled'] is True
            assert sales['testing_fee_total_usd'] == 100
            assert sales['freight_calc'] == {'enabled': True, 'freight_enabled': True, 'lifting_enabled': False}
