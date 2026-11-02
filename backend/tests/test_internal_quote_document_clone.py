import importlib
from copy import deepcopy

import pytest
from sqlalchemy import select, func

from test_internal_quote_api import make_client, login, logout
from test_internal_quote_alternatives import fill, fork, create
from test_internal_quote_series_export import series, request_body, image_bytes


def clone_body(quotes, suffix='COPY-ALL'):
    return dict(quote_no=suffix, version_label='V1.0', business_owner_id=quotes[0]['business_owner_id'],
        business_owner_name=quotes[0]['business_owner_name'], target_customer_price='无', target_date='',
        products=[dict(source_quote_id=q['id'], revision=q['header_revision'], product_name=q['product_name'], qty=q['qty']) for q in quotes])


@pytest.mark.parametrize('append_blank', [False, True])
def test_ordinary_customer_clone_can_issue_without_justplay_components(monkeypatch, append_blank):
    with make_client(monkeypatch) as client:
        login(client, 'ordinary-clone-owner', 'admin', '*', '*')
        source = fill(client, create(client, 'ORDINARY-CLONE'))
        assert source['customer'] == '测试客户'
        body = clone_body([source], 'ORDINARY-COPY')
        if append_blank:
            body['products'].append(dict(product_name='普通客新增款', qty=2000))
        response = client.post(f"/api/internal-quotes/{source['id']}/clone-document", json=body)
        assert response.status_code == 201, response.text
        copied = response.json()
        assert copied['customer'] == source['customer']
        assert copied['readiness']['state'] == 'ready'
        products = client.get(f"/api/internal-quotes/{copied['id']}/batch-products").json()
        assert len(products) == (2 if append_blank else 1)
        quotes = [client.get(f"/api/internal-quotes/{row['quote_id']}").json() for row in products]
        for quote in quotes:
            sales = next(s for s in quote['sections'] if s['department'] == 'sales')
            assert sales['payload'].get('pricing_mode') != 'component'
            assert not sales['payload'].get('pricing_components')
        if append_blank:
            assert quotes[1]['readiness']['state'] != 'ready'
            blocked = client.post(f"/api/internal-quotes/{copied['id']}/series-export", json=request_body(quotes))
            assert blocked.status_code == 409, blocked.text
            assert '普通客新增款' in blocked.json()['detail']['message']
            quotes[1] = fill(client, quotes[1])
            output = client.post(f"/api/internal-quotes/{copied['id']}/series-export", json=request_body(quotes))
        else:
            output = client.post(f"/api/internal-quotes/{copied['id']}/direct-issue", json={'revision': copied['header_revision']})
        assert output.status_code == 200, output.text
        original = client.get(f"/api/internal-quotes/{source['id']}").json()
        assert original['status'] == source['status']
        assert original['sections'] == source['sections']


def test_document_clone_preserves_independent_products_images_reference_and_issued_source(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'whole-cloner', 'admin', '*', '*')
        quotes = [fill(client, q) for q in series(client)]
        # Distinct costs catch accidental reuse of the first product's payloads.
        for index, code, key, name, price in [(1, 'engineering', 'materials', '第二款五金', 1.2),
                                              (2, 'sales', 'packaging_materials', '第三款彩盒', 3.25)]:
            q = quotes[index]
            section = next(s for s in q['sections'] if s['department'] == code)
            payload = deepcopy(section['payload'])
            payload[key][0].update(item=name, unit_price_rmb=price)
            saved = client.put(f"/api/internal-quotes/{q['id']}/sections/{code}", json={
                'revision': section['revision'], 'payload': payload})
            assert saved.status_code == 200, saved.text
            quotes[index] = client.get(f"/api/internal-quotes/{q['id']}").json()
        # One distinct version is chosen for the second product.
        quotes[1] = fork(client, quotes[1], 'version')
        attachment = client.post(f"/api/internal-quotes/{quotes[0]['id']}/product-image", data={'revision': quotes[0]['header_revision']},
            files={'file': ('paint.png', image_bytes(), 'image/png')})
        assert attachment.status_code == 201, attachment.text
        quotes[0] = client.get(f"/api/internal-quotes/{quotes[0]['id']}").json()
        response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/direct-issue", json={'revision': quotes[0]['header_revision']})
        assert response.status_code == 200, response.text
        quote_id = quotes[0]['id']
        issued_url = f"/api/internal-quotes/{quote_id}/exports/{response.json()['id']}/download"
        issued_bytes = client.get(issued_url).content
        quotes[0] = client.get(f'/api/internal-quotes/{quote_id}').json()
        original = deepcopy(quotes)
        body = clone_body(quotes)
        body['products'][1].update(product_name='改名后的第二款', qty=7000)
        body['products'].append(dict(product_name='新增空白款', qty=3000, pricing_components=['主体', '包装盘']))
        response = client.post(f'/api/internal-quotes/{quote_id}/clone-document', json=body)
        assert response.status_code == 201, response.text
        first = response.json()
        products = client.get(f"/api/internal-quotes/{first['id']}/batch-products").json()
        assert len(products) == 4
        copies = [client.get(f"/api/internal-quotes/{p['quote_id']}").json() for p in products]
        assert [q['product_name'] for q in copies] == [quotes[0]['product_name'], '改名后的第二款', quotes[2]['product_name'], '新增空白款']
        assert copies[1]['qty'] == 7000
        for source, target in zip(quotes, copies):
            assert target['cloned_from_quote_id'] == source['id']
            assert target['reference_snapshot_id'] != source['reference_snapshot_id']
            assert target['final_release_status'] != 'issued' and target['status'] == 'drafting'
            for s in source['sections']:
                t = next(x for x in target['sections'] if x['department'] == s['department'])
                assert t['is_required'] == s['is_required']
                assert t['payload'] == s['payload']
                if s['is_required']: assert t['calculation_status'] == 'valid'
        new_sales = next(s for s in copies[-1]['sections'] if s['department'] == 'sales')
        assert [p['name'] for p in new_sales['payload']['pricing_components']] == ['主体', '包装盘']
        assert new_sales['filled_at'] == ''
        attachments = client.get(f"/api/internal-quotes/{first['id']}/attachments").json()
        assert len(attachments) == 1 and attachments[0]['id'] != attachment.json()['id']
        assert products[0]['main_image']['id'] == attachments[0]['id']
        assert products[0]['main_image']['id'] != attachment.json()['id']
        db_module = importlib.import_module('app.db')
        model = importlib.import_module('app.models.internal_quote').InternalQuoteReferenceSet
        with db_module.SessionLocal() as db:
            for source, target in zip(quotes, copies):
                assert db.get(model, target['reference_snapshot_id']).snapshot_json == db.get(model, source['reference_snapshot_id']).snapshot_json
        assert client.get(issued_url).content == issued_bytes
        for source in original:
            current = client.get(f"/api/internal-quotes/{source['id']}").json()
            for key in ['header_revision', 'status', 'final_release_status', 'sections', 'reference_snapshot_id']:
                assert current[key] == source[key]


def test_document_clone_rejects_incomplete_foreign_stale_and_unauthorized_sources(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'clone-boundaries', 'admin', '*', '*')
        quotes = series(client)
        endpoint = f"/api/internal-quotes/{quotes[0]['id']}/clone-document"
        body = clone_body(quotes)
        bad = deepcopy(body); bad['products'].pop()
        assert client.post(endpoint, json=bad).status_code == 409
        bad = deepcopy(body); bad['products'][1] = bad['products'][0]
        assert client.post(endpoint, json=bad).status_code == 409
        bad = deepcopy(body); bad['products'][1]['revision'] += 1
        assert client.post(endpoint, json=bad).status_code == 409
        foreign = series(client, 'ANOTHER-DOCUMENT')
        bad = deepcopy(body); bad['products'][1].update(source_quote_id=foreign[1]['id'])
        assert client.post(endpoint, json=bad).status_code == 409
        logout(client); login(client, 'no-clone-permission', 'warehouse_keeper', 'pmc-warehouse')
        assert client.post(endpoint, json=body).status_code == 403


def test_document_clone_rolls_back_entire_batch_on_later_failure(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'clone-atomic', 'admin', '*', '*')
        quotes = series(client)
        service = importlib.import_module('app.services.internal_quote_document_clone')
        original = service._create_sections
        calls = 0
        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: raise RuntimeError('second product failed')
            return original(*args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(service, '_create_sections', fail_second)
            with pytest.raises(RuntimeError, match='second product failed'):
                client.post(f"/api/internal-quotes/{quotes[0]['id']}/clone-document", json=clone_body(quotes, 'NO-PARTIAL-COPY'))
        db_module = importlib.import_module('app.db')
        model = importlib.import_module('app.models.internal_quote').InternalQuote
        with db_module.SessionLocal() as db:
            assert db.scalar(select(func.count()).select_from(model).where(model.batch_quote_no == 'NO-PARTIAL-COPY')) == 0


def test_saved_painting_blockers_and_series_errors_identify_all_products(monkeypatch):
    with make_client(monkeypatch) as client:
        login(client, 'readiness-owner', 'admin', '*', '*')
        quotes = [fill(client, q) for q in series(client)]
        for i in (1, 2):
            q = quotes[i]
            response = client.post(f"/api/internal-quotes/{q['id']}/participation", json={'revision': q['header_revision'], 'add_sections': ['painting']})
            assert response.status_code == 200, response.text
            q = client.get(f"/api/internal-quotes/{q['id']}").json()
            painting = next(s for s in q['sections'] if s['department'] == 'painting')
            response = client.put(f"/api/internal-quotes/{q['id']}/sections/painting", json={'revision': painting['revision'], 'payload': {
                'quote_mode': 'detail', 'rows': [{'name': '包装盘', 'cost_allocation': 'split', 'paint_cost_hkd': None,
                    'labor_cost_hkd': None, 'operations': {'clamp': {'quantity': 1, 'unit_price_hkd': 0.68}}}]}})
            assert response.status_code == 200 and response.json()['calculation_status'] == 'blocked', response.text
            quotes[i] = client.get(f"/api/internal-quotes/{q['id']}").json()
            assert '油漆、人工待填写' in quotes[i]['readiness']['blockers'][0]['reason']
        response = client.post(f"/api/internal-quotes/{quotes[0]['id']}/series-export", json=request_body(quotes))
        assert response.status_code == 409, response.text
        detail = response.json()['detail']
        assert len(detail['products']) == 2
        assert all(q['product_name'] in detail['message'] for q in quotes[1:])
        assert "'message':" not in detail['message']
        assert client.get(f"/api/internal-quotes/{quotes[0]['id']}/exports").json() == []
